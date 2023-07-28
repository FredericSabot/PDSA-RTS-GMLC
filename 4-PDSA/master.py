from mpi4py import MPI
from common import *
from job import Job
from contingencies import *
import glob
import os
import random
import time
from math import sqrt, ceil

class Master:
    def __init__(self, slaves):
        if len(slaves) == 0:
            raise ValueError('Need at least one slave')

        self.comm = MPI.COMM_WORLD
        self.slaves = set(slaves)
        self.create_contingency_list()
        self.job_queue = JobQueue(self.contingency_list)
        self.run()

    def create_contingency_list(self):
        base_contingency = Contingency.create_base_contingency()
        N_1_contingencies = Contingency.create_N_1_contingencies()[0:2]
        N_2_contingencies = Contingency.create_N_2_contingencies()[0:2]  # Limit number of contingencies for first tests

        self.contingency_list = base_contingency + N_1_contingencies + N_2_contingencies
        logging.info('Considering {} contingencies: {} base, {} N-1, {} N-2'.format(len(self.contingency_list), len(base_contingency), len(N_1_contingencies), len(N_2_contingencies)))

    def run(self):
        for job in self.job_queue.get_next_job():  # The master is directly stopped regardless of whether slaves are still running
            status = MPI.Status()
            self.comm.probe(source=MPI.ANY_SOURCE, tag=MPI.ANY_TAG, status=status)
            slave = status.Get_source()
            tag = status.Get_tag()

            if tag == MPI_TAGS.READY.value:
                self.comm.recv(source=slave, tag=MPI_TAGS.READY.value, status=status)

                logging.debug('Master: sending input job {} to slave {}'.format(job, slave))
                self.comm.send(obj=job, dest=slave, tag=MPI_TAGS.START.value)

            elif tag == MPI_TAGS.DONE.value:
                # Read data
                self.comm.probe(source=MPI.ANY_SOURCE, tag=MPI_TAGS.DONE.value, status=status)
                slave = status.Get_source()
                job = self.comm.recv(source=slave, tag=MPI_TAGS.DONE.value)
                logging.debug('Master: slave {} returned {}'.format(slave, job))
                self.job_queue.store_completed_job(job)

            else:
                raise NotImplementedError("Unexpected tag:", tag)

        self.terminate_slaves()

    def terminate_slaves(self):
        for s in self.slaves:
            self.comm.send(obj=None, dest=s, tag=MPI_TAGS.EXIT.value)
        for s in self.slaves:
            self.comm.recv(source=s, tag=MPI_TAGS.EXIT.value)


class JobQueue:
    # Note that in the current implementation, it is assumed that all contingencies "make sense" for all static samples,
    # i.e. that all elements are always connected (no maintenance, transmission switching, constant substation,
    # configurations). Otherwise, one should first check for each contingency, for which static samples this
    # contingency is possible, and only samples from those + weight the probability of the contingency accordingly

    def __init__(self, contingencies: list[Contingency]):
        self.random = random.Random()
        self.random.seed(0)

        self.running_jobs = []
        self.contingencies = contingencies

        self.static_samples = []
        static_files = glob.glob('../2-SCOPF/d-Final-dispatch/' + CASE + '/*.iidm')
        for file in static_files:
            self.static_samples.append(os.path.basename(file).split('.')[0])

        self.simulation_results: dict[str, ContingencyResults]
        self.simulation_results = {}
        self.total_risk = 0
        self.risk_per_contingency = {}
        for contingency in self.contingencies:
            self.simulation_results[contingency.id] = ContingencyResults()
            self.risk_per_contingency[contingency.id] = 0

        # To make the algorithm deterministic (in an MPI context), a seed is given to each set of (contingency, static_id, number of runs for this contingency and static id)
        self.dynamic_seed_counters = {}
        for contingency in self.contingencies:
            self.dynamic_seed_counters[contingency.id] = {}
            for static_sample in self.static_samples:
                self.dynamic_seed_counters[contingency.id][static_sample] = hash(static_sample)


    def store_completed_job(self, job: Job):
        self.simulation_results[job.contingency.id].add_job(job)
        self.risk_per_contingency[job.contingency.id] = self.simulation_results[job.contingency.id].get_average_load_shedding() * job.contingency.frequency
        self.total_risk = sum(self.risk_per_contingency.values())

        for i in range(len(self.running_jobs)):
            if self.running_jobs[i].id == job.id:
                del self.running_jobs[i]
                return
        raise RuntimeError('Job', job, 'not in running_jobs list', self.running_jobs)


    def get_next_job(self) -> Job:
        # Run an arbitrary number of simulations to start up the algorithm (allow to have a first estimate of the total
        # risk and sampled variances)
        for contingency in self.contingencies:
            min_nb_runs = JobQueue.get_minimum_number_of_runs(contingency)
            for i in range(min_nb_runs):
                static_sample = self.random.choice(self.static_samples)  # TODO: best to shuffle then pick if no dynamic uncertainty (or if use indicator)

                dynamic_seed = self.dynamic_seed_counters[contingency.id][static_sample]
                self.dynamic_seed_counters[contingency.id][static_sample] += 1

                dynamic_seed = 0  # No dynamic uncertainty to start with
                job = Job(static_sample, dynamic_seed, contingency)
                self.running_jobs.append(job)
                yield job
        logging.info('Launched all NB_MIN_RUNS jobs')

        # Run simulations until requested statistical accuracy is reached
        while True:
            contingencies_to_run = []
            contingencies_waiting = []
            for contingency in self.contingencies:
                nb_completed_runs = self.simulation_results[contingency.id].nb_run_jobs
                min_nb_runs = JobQueue.get_minimum_number_of_runs(contingency)
                if nb_completed_runs < min_nb_runs:
                    contingencies_waiting.append(contingency)
                    logging.debug('Contingency %s waiting for %d remaining MIN_NUMBER runs' % (contingency.id, min_nb_runs - nb_completed_runs))
                    continue  # Perform at least the minimum number of runs before evaluating statistical indicators

                if self.is_statistical_accuracy_reached(contingency):
                    continue
                else:
                    contingencies_to_run.append(contingency)

            if not contingencies_to_run and not contingencies_waiting:
                break

            if not contingencies_to_run and contingencies_waiting:
                logging.warn('Convergence criteria satisfied before end of starting runs')
                logging.warn('This is typically caused by a high number of slaves compared to the number of contingencies (typically in testing)')
                logging.warn('Or a high MIN_NUMBER_RUN compared to the requested statistical accuracy')
                logging.warn('Set logging level to debug to see which contingencies are blocking')

                time.sleep(5)  # Wait for the MIN_NUMBER_RUN jobs to complete
                # Could also preventivelly run new jobs for contingencies with min_nb_runs < MIN_NB_RUNS


            # Prioritise contingencies that have the most impact on the accuracy of the indicators
            weights = {}
            sum_weigths = 0
            for contingency in contingencies_to_run:
                weigth = self.get_statistical_indicator_derivative(contingency)
                weights[contingency.id] = weigth
                sum_weigths += weigth

            for contingency in contingencies_to_run:
                nb_runs = weigth / sum_weigths * MAX_RUNS_WITHOUT_INDICATOR_EVALUATION

                nb_already_run_jobs = self.simulation_results[contingency.id].nb_run_jobs
                nb_runs = max(nb_runs, 0.2 * nb_already_run_jobs)  # Derivative might not be very accurate if we run many job compared to what has already be done + avoid overcommiting to a single contingency
                nb_runs = ceil(nb_runs)  # At least one run

                for i in range(nb_runs):
                    static_sample = self.random.choice(self.static_samples)  # TODO: best to shuffle then pick if no dynamic uncertainty (or if use indicator)

                    dynamic_seed = self.dynamic_seed_counters[contingency.id][static_sample]
                    self.dynamic_seed_counters[contingency.id][static_sample] += 1

                    dynamic_seed = 0  # No dynamic uncertainty to start with
                    job = Job(static_sample, dynamic_seed, contingency)
                    self.running_jobs.append(job)
                    yield job

            # Update indicators # TODO: check when it is actually done




    @staticmethod
    def get_minimum_number_of_runs(contingency: Contingency):
        if contingency.frequency > OUTAGE_RATE_PER_KM:  # Most likely a N-1 contingency
            min_nb_runs = MIN_NUMBER_RUN_N_1
            min_nb_runs = 5  # Low for first tests
        else:  # Most likely a N-2 contingency
            min_nb_runs = MIN_NUMBER_RUN_N_2
            min_nb_runs = 5  # Low for first tests
        return min_nb_runs

    def is_statistical_accuracy_reached(self, contingency: Contingency) -> bool:
        contingency_results = self.simulation_results[contingency.id]
        mean = contingency_results.get_average_load_shedding()
        std_dev = contingency_results.get_std_dev()
        N = contingency_results.nb_run_jobs

        if contingency.frequency * std_dev / sqrt(N) > 0.01 * self.total_risk:
            return False

        if contingency.frequency * (100 - mean) / N > 0.01 * self.total_risk:
            return False

        return True

    def get_statistical_indicator_derivative(self, contingency: Contingency) -> float:
        contingency_results = self.simulation_results[contingency.id]
        mean = contingency_results.get_average_load_shedding()
        std_dev = contingency_results.get_std_dev()
        N = contingency_results.nb_run_jobs

        derivative_1 = contingency.frequency * std_dev / sqrt(N) - contingency.frequency * std_dev / sqrt(N + 1)
        derivative_2 = contingency.frequency * (100 - mean) / N - contingency.frequency * (100 - mean) / (N + 1)

        return max(derivative_1, derivative_2)


class ContingencyResults:
    def __init__(self):
        self.jobs: list[Job]
        self.jobs = []
        self.sum_load_shedding = 0
        self.sum_load_shedding_squared = 0
        self.nb_run_jobs = 0

    def add_job(self, job: Job):
        self.jobs.append(job)
        self.sum_load_shedding += job.results.load_shedding
        self.sum_load_shedding_squared = self.sum_load_shedding ** 2
        self.nb_run_jobs += 1

    def get_variance(self):
        """
        Naive computation of the variance following https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance
        Since N should be at most 1000, and the variance at most two order of magnitudes below the average (and not
        event both at the same time), numerical stability should not be an issue
        """
        sum_ = self.sum_load_shedding
        sum_sq = self.sum_load_shedding_squared
        n = self.nb_run_jobs
        return (sum_sq - (sum_**2) / n) / (n - 1)

    def get_std_dev(self):
        return sqrt(self.get_variance())

    def get_average_load_shedding(self):
        return self.sum_load_shedding / self.nb_run_jobs
