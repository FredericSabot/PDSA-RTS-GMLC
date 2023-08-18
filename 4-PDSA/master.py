from mpi4py import MPI
from common import *
from job import Job
from contingencies import Contingency
import glob
import os
import random
import logger
from math import sqrt, ceil
from lxml import etree

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
        logger.logger.info('Considering {} contingencies: {} base, {} N-1, {} N-2'.format(len(self.contingency_list), len(base_contingency), len(N_1_contingencies), len(N_2_contingencies)))

    def run(self):
        init = True
        jobs_to_run, _ = self.job_queue.get_next_jobs(init=True)
        n_iter = 0
        try:
            while True:
                status = MPI.Status()
                self.comm.probe(source=MPI.ANY_SOURCE, tag=MPI.ANY_TAG, status=status)
                slave = status.Get_source()
                tag = status.Get_tag()

                if tag == MPI_TAGS.READY.value:
                    job = jobs_to_run.pop(0)
                    self.comm.recv(source=slave, tag=MPI_TAGS.READY.value, status=status)

                    logger.logger.log(logger.logging.TRACE, 'Master: sending input job {} to slave {}'.format(job, slave))
                    self.comm.send(obj=job, dest=slave, tag=MPI_TAGS.START.value)

                elif tag == MPI_TAGS.DONE.value:
                    # Read data
                    self.comm.probe(source=MPI.ANY_SOURCE, tag=MPI_TAGS.DONE.value, status=status)
                    slave = status.Get_source()
                    job = self.comm.recv(source=slave, tag=MPI_TAGS.DONE.value)
                    logger.logger.log(logger.logging.TRACE, 'Master: slave {} returned {}'.format(slave, job))
                    self.job_queue.store_completed_job(job)

                else:
                    raise NotImplementedError("Unexpected tag:", tag)

                if len(jobs_to_run) == 0:
                    if init:
                        logger.logger.info('Launched all NB_MIN_RUNS jobs')
                        init = False
                    n_iter += 1
                    logger.logger.info("Launching batch {} of simulations".format(n_iter))
                    jobs_to_run, wait_for_data = self.job_queue.get_next_jobs(init=False)

                    while wait_for_data:
                        self.comm.probe(source=MPI.ANY_SOURCE, tag=MPI_TAGS.DONE.value, status=status)
                        slave = status.Get_source()
                        job = self.comm.recv(source=slave, tag=MPI_TAGS.DONE.value)
                        logger.logger.log(logger.logging.TRACE, 'Master: slave {} returned {}'.format(slave, job))
                        self.job_queue.store_completed_job(job)
                        jobs_to_run, wait_for_data = self.job_queue.get_next_jobs(init=False)

                    if len(jobs_to_run) == 0:  # No more jobs to run and not waiting for data
                        break  # Note that the master is directly stopped when statistical indicators are satisfied even if some slaves are still running

            self.job_queue.write_analysis_output()
            self.terminate_slaves()
        except KeyboardInterrupt:
            self.job_queue.write_analysis_output()

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

        list[Job]: self.running_jobs
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


    def get_next_jobs(self, init: bool) -> list[Job]:
        jobs = []
        wait_for_data = False
        if init:
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
                    jobs.append(job)
            return jobs, wait_for_data

        else:
            # Run simulations until requested statistical accuracy is reached
            contingencies_to_run = []
            contingencies_waiting = []  # Wait for the NB_MIN_RUNS of each contingency to be done before evaluating statistical indicators
            logger.logger.info("##############################################")
            logger.logger.info("# Contingency convergence")
            logger.logger.info("##############################################")
            for contingency in self.contingencies:
                nb_completed_runs = self.simulation_results[contingency.id].nb_run_jobs
                min_nb_runs = JobQueue.get_minimum_number_of_runs(contingency)
                if nb_completed_runs < min_nb_runs:
                    contingencies_waiting.append(contingency)
                    logger.logger.log(logger.logging.TRACE, 'Contingency {} waiting for {} remaining MIN_NUMBER runs'.format(contingency.id, min_nb_runs - nb_completed_runs))
                    continue

                if self.is_statistical_accuracy_reached(contingency):
                    continue
                else:
                    contingencies_to_run.append(contingency)

            if not contingencies_to_run and not contingencies_waiting:
                logger.logger.info("##############################################")
                logger.logger.info("# Master process sucessfully terminated")
                logger.logger.info("##############################################")
                return [], wait_for_data

            if not contingencies_to_run and contingencies_waiting:
                logger.logger.warn('Convergence criteria satisfied before end of starting runs')
                logger.logger.warn('This is typically caused by a high number of slaves compared to the number of contingencies (typically in testing)')
                logger.logger.warn('Or a high MIN_NUMBER_RUN compared to the requested statistical accuracy')
                logger.logger.warn('Blocking contingencies: {}'.format([contingency.id for contingency in contingencies_waiting]))

                wait_for_data = True
                return [], wait_for_data

            logger.logger.info("##############################################")
            logger.logger.info("# Contingency weigths")
            logger.logger.info("##############################################")
            # Prioritise contingencies that have the most impact on the accuracy of the indicators
            weights = {}
            sum_weigths = 0
            for contingency in contingencies_to_run:
                weigth = self.get_statistical_indicator_derivative(contingency)
                logger.logger.info('Contingency {}: {}'.format(contingency.id, weigth))
                weights[contingency.id] = weigth
                sum_weigths += weigth

            for contingency in contingencies_to_run:
                nb_runs = weigth / sum_weigths * NB_RUNS_PER_INDICATOR_EVALUATION

                nb_already_run_jobs = self.simulation_results[contingency.id].nb_run_jobs
                nb_runs = max(nb_runs, 0.2 * nb_already_run_jobs)  # Derivative might not be very accurate if we run many job compared to what has already be done + avoid overcommiting to a single contingency
                nb_runs = ceil(nb_runs)  # At least one run
                # TODO: if too many contingencies with nb_runs << 1 rounded up to 1, can select a reduced number (while keeping deterministic behaviour)

                for i in range(nb_runs):
                    static_sample = self.random.choice(self.static_samples)  # TODO: best to shuffle then pick if no dynamic uncertainty (or if use indicator)

                    dynamic_seed = self.dynamic_seed_counters[contingency.id][static_sample]
                    self.dynamic_seed_counters[contingency.id][static_sample] += 1

                    dynamic_seed = 0  # No dynamic uncertainty to start with
                    job = Job(static_sample, dynamic_seed, contingency)
                    self.running_jobs.append(job)
                    jobs.append(job)
            return jobs, wait_for_data

    def write_analysis_output(self):
        root = etree.Element('Analysis')  # TODO: use real code, add global attribute convergence = 'CONVERGED', 'USER INTERRUPT' or 'TIMEOUT'

        for contingency in self.contingencies:
            contingency_results = self.simulation_results[contingency.id]
            mean = contingency_results.get_average_load_shedding()
            N = contingency_results.nb_run_jobs
            indicator_1, indicator_2 = self.get_statistical_indivators(contingency)

            contingency_attrib = {'id': contingency.id,
                                  'frequency': str(contingency.frequency),
                                  'mean_load_shed': str(mean),
                                  'risk': str(contingency.frequency * mean),
                                  'N': str(N),
                                  'ind_1': str(indicator_1),
                                  'ind_2': str(indicator_2)}
            contingency_element = etree.SubElement(root, 'Contingency', contingency_attrib)

            for job in contingency_results.jobs:
                job_attrib = {'static_id': str(job.static_id),
                              'dyn_id': str(job.dynamic_seed),
                              'simulation_time': '{:.2f}'.format(job.elapsed_time),
                              'timeout': str(job.timed_out)}
                if job.completed:
                    job_attrib['load_shedding'] = '{:.2f}'.format(job.results.load_shedding)
                etree.SubElement(contingency_element, 'Job', job_attrib)

        with open('AnalysisOutput.xml', 'wb') as doc:
            doc.write(etree.tostring(root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))


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
        indicator_1, indicator_2 = self.get_statistical_indivators(contingency)

        accuracy_reached = True
        if indicator_1 > 0.01 * self.total_risk:
            accuracy_reached = False
            logger.logger.info("Contingency {}: statistical indicator 1 not satisfied: {} > {}".format(contingency.id, indicator_1, 0.01 * self.total_risk))

        if indicator_2 > 0.01 * self.total_risk:
            accuracy_reached = False
            logger.logger.info("Contingency {}: statistical indicator 2 not satisfied: {} > {}".format(contingency.id, indicator_2, 0.01 * self.total_risk))

        if accuracy_reached:
            logger.logger.info("Contingency {}: statistical accuracy reached".format(contingency.id))

        if self.total_risk == 0:
            logger.logger.critical('Total risk is 0, so statistical indicators cannot be satisfied')
            # accuracy_reached = True

        return accuracy_reached

    def get_statistical_indivators(self, contingency: Contingency):
        contingency_results = self.simulation_results[contingency.id]
        mean = contingency_results.get_average_load_shedding()
        std_dev = contingency_results.get_std_dev()
        N = contingency_results.nb_run_jobs

        indicator_1 = contingency.frequency * std_dev / sqrt(N)
        indicator_2 = contingency.frequency * (100 - mean) / N
        return indicator_1, indicator_2


    def get_statistical_indicator_derivatives(self, contingency: Contingency):
        contingency_results = self.simulation_results[contingency.id]
        mean = contingency_results.get_average_load_shedding()
        std_dev = contingency_results.get_std_dev()
        N = contingency_results.nb_run_jobs
        for running_job in self.running_jobs:
            if running_job.contingency.id == contingency.id:  # Lower priority of contingencies that have jobs currently running
                N += 1

        derivative_1 = contingency.frequency * std_dev / sqrt(N) - contingency.frequency * std_dev / sqrt(N + 1)
        derivative_2 = contingency.frequency * (100 - mean) / N - contingency.frequency * (100 - mean) / (N + 1)

        return derivative_1, derivative_2

    def get_statistical_indicator_derivative(self, contingency: Contingency):
        return max(self.get_statistical_indicator_derivatives(contingency))

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
        both at the same time), numerical stability should not be an issue
        """
        sum_ = self.sum_load_shedding
        sum_sq = self.sum_load_shedding_squared
        n = self.nb_run_jobs
        return (sum_sq - (sum_**2) / n) / (n - 1)

    def get_std_dev(self):
        return sqrt(self.get_variance())

    def get_average_load_shedding(self):
        return self.sum_load_shedding / self.nb_run_jobs
