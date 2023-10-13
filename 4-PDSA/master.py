from mpi4py import MPI
from common import *
from job import Job, SpecialJob
from contingencies import Contingency
import glob
import os
import random
import logger
import hashlib
from math import sqrt, ceil
from lxml import etree
import numpy as np
from natsort import natsorted
import time

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
        N_1_contingencies = Contingency.create_N_1_contingencies()
        N_2_contingencies = Contingency.create_N_2_contingencies()

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
                    jobs_to_run, wait_for_data = self.job_queue.get_next_jobs(init=False)
                    logger.logger.info("")
                    logger.logger.info("Launching batch {} of simulations".format(n_iter))

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
            self.job_queue.write_analysis_output(err=True)

    def terminate_slaves(self):
        for s in self.slaves:
            self.comm.send(obj=None, dest=s, tag=MPI_TAGS.EXIT.value)
        for s in self.slaves:
            self.comm.recv(source=s, tag=MPI_TAGS.EXIT.value)


class JobQueue:
    # Note that in the current implementation, it is assumed that all contingencies "make sense" for all static samples,
    # i.e. that all elements are always connected (no maintenance, transmission switching, constant substation,
    # configurations). Otherwise, one should first check for each contingency, for which static samples this
    # contingency is possible, and only samples from those + weigth the probability of the contingency accordingly

    def __init__(self, contingencies: list[Contingency]):
        self.contingencies = contingencies
        self.contingencies_skipped = []

        self.static_samples = []
        static_files = natsorted(glob.glob('../2-SCOPF/d-Final-dispatch/' + CASE + '/*.iidm'))  # glob gives files in arbitrary order, sort them to be deterministic
        for file in static_files:
            self.static_samples.append(os.path.basename(file).split('.')[0])
        self.static_samples_per_contingency = {}
        for contingency in self.contingencies:
            samples = self.static_samples.copy()
            random_generator = random.Random(hash(contingency.id))  # The same static ids are always used for a given contingency to make the algo deterministic
            random_generator.shuffle(samples)
            self.static_samples_per_contingency[contingency.id] = samples

        self.simulation_results: dict[str, ContingencyResults]
        self.simulation_results = {}
        self.simulations_launched : dict[str, ContingencyLaunched]
        self.simulations_launched = {}
        self.total_risk = 0
        self.risk_per_contingency = {}
        for contingency in self.contingencies:
            self.simulation_results[contingency.id] = ContingencyResults()
            self.simulations_launched[contingency.id] = ContingencyLaunched()
            self.risk_per_contingency[contingency.id] = 0

        # To make the algorithm deterministic (in an MPI context), a seed is given to each set of (contingency, static_id, number of runs for this contingency and static id)
        self.dynamic_seed_counters = {}
        for contingency in self.contingencies:
            self.dynamic_seed_counters[contingency.id] = {}
            for static_sample in self.static_samples:
                self.dynamic_seed_counters[contingency.id][static_sample] = hash(static_sample)

        self.priority_queue: list[Job]
        self.priority_queue = []

    def add_job_to_priority_queue(self, job: Job):
        self.priority_queue.append(job)
        self.simulations_launched[job.contingency.id].add_job(job)

    def store_completed_job(self, job: Job):
        self.simulation_results[job.contingency.id].add_job(job)
        self.risk_per_contingency[job.contingency.id] = self.simulation_results[job.contingency.id].get_average_load_shedding() * job.contingency.frequency
        self.total_risk = sum(self.risk_per_contingency.values())

        if isinstance(job, SpecialJob):
            if job.variable_order or job.missing_events:
                for j in range(MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED - 1):
                    new_job = self.create_job(job.contingency, job.static_id)
                    self.add_job_to_priority_queue(new_job)

    def create_job(self, contingency: Contingency, static_id):
        dynamic_seed = self.dynamic_seed_counters[contingency.id][static_id]
        self.dynamic_seed_counters[contingency.id][static_id] += 1
        return Job(static_id, dynamic_seed, contingency)


    def get_next_jobs(self, init: bool) -> list[Job]:
        t0 = time.time()
        jobs = []
        nb_priority_jobs = len(self.priority_queue)
        while len(jobs) < NB_RUNS_PER_INDICATOR_EVALUATION and len(self.priority_queue) > 0:
            jobs.append(self.priority_queue.pop(0))
        if len(jobs) == NB_RUNS_PER_INDICATOR_EVALUATION:
            logger.logger.info(("##############################################"))
            logger.logger.info(("# Batch with only priority runs"))
            logger.logger.info(("##############################################"))
            return jobs, False
        elif len(jobs) > 0:
            logger.logger.info(("##############################################"))
            logger.logger.info(("# Launching {} priority runs".format(len(jobs))))
            logger.logger.info(("##############################################"))

        if init:
            # Run an arbitrary number of simulations to start up the algorithm (allow to have a first estimate of the total
            # risk and sampled variances)
            for contingency in self.contingencies:
                min_nb_static_seeds = JobQueue.get_minimum_number_of_static_seeds(contingency)
                for i in range(min_nb_static_seeds):
                    static_sample = self.static_samples_per_contingency[contingency.id][i]

                    if DOUBLE_MC_LOOP:
                        job = SpecialJob(static_sample, 0, contingency)
                    else:
                        job = self.create_job(contingency, static_sample)
                    self.simulations_launched[contingency.id].add_job(job)
                    jobs.append(job)

            wait_for_data = False
            return jobs, wait_for_data

        else:
            self.write_analysis_output(err=True)  # TODO: make signal handling work with SLURM and remove this (but, it is quite fast anyway)
            # Run simulations until requested statistical accuracy is reached
            contingencies_to_run = []
            contingencies_waiting = []  # Wait for the NB_MIN_RUNS of each contingency to be done before evaluating statistical indicators
            logger.logger.info("##############################################")
            logger.logger.info("# Contingency convergence")
            logger.logger.info("##############################################")
            for contingency in self.contingencies:
                if contingency in self.contingencies_skipped:
                    continue

                # Check if all initial runs have been completed
                min_nb_static_seeds = JobQueue.get_minimum_number_of_static_seeds(contingency)
                if len(self.simulation_results[contingency.id].static_ids) < min_nb_static_seeds:
                    contingencies_waiting.append(contingency)
                    logger.logger.log(logger.logging.TRACE, 'Contingency {} waiting for first static seed runs'.format(contingency.id))
                else:
                    if DOUBLE_MC_LOOP:
                        for static_id in self.simulation_results[contingency.id].static_ids[:min_nb_static_seeds]:
                            nb_completed_runs = len(self.simulation_results[contingency.id].jobs[static_id])
                            special_job = self.simulation_results[contingency.id].jobs[static_id][0]
                            if (special_job.variable_order or special_job.missing_events) and nb_completed_runs < MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED:
                                contingencies_waiting.append(contingency)
                                logger.logger.info('Contingency {} waiting for first dynamic seed runs'.format(contingency.id))
                                continue

                if self.is_statistical_accuracy_reached(contingency):
                    continue
                else:
                    contingencies_to_run.append(contingency)

            if not contingencies_to_run and not contingencies_waiting:
                logger.logger.info("##############################################")
                logger.logger.info("# Master process sucessfully terminated")
                logger.logger.info("##############################################")
                wait_for_data = False
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
            weigths = []
            limiting_indicators = {}
            for contingency in contingencies_to_run:
                # Prioritise contingencies that are far from reaching statistical accuracy
                # Note that in the end, all contingencies should reach statistical accuracy, so an optimal allocation
                # is not necessary. However, as the estimate of the total risk (used to define statistical convergence)
                # might slightly change during the analysis, it is best to prioritise contingencies that have definitively
                # not converged yet, to avoid unecessary simulations (e.g. avoid running simulations that are barely above
                # the convergence threshold, as the threshold might decrease if the total risk estimation decreases), and
                # to increase the speed at which the estimate of the total risk decreases.
                distances_from_statistical_accuracy = self.get_distances_from_statistical_accuracy(contingency)
                # Most often, indicators will be very different for a given contingency (indicator 1 is mostly meant for N-2 contingencies
                # while indicator 2 is mostly meant to N-1 dcontingencies), so only the indicator that is the furthest from convergence
                # is considered. It is not very useful to try to optimise to reduce both indicators at the same time
                limiting_indicator = np.argmax(distances_from_statistical_accuracy)
                weigth = max(distances_from_statistical_accuracy)
                assert weigth > 0  # Distance should be positive as only contingencies that have not converged yet are considered at this stage
                logger.logger.info('Contingency {}: {}'.format(contingency.id, weigth))
                weigths.append(weigth)
                limiting_indicators[contingency.id] = limiting_indicator

            nb_runs_per_contingency = JobQueue.allocation(weigths, NB_RUNS_PER_INDICATOR_EVALUATION - nb_priority_jobs)

            for contingency, nb_runs in zip(contingencies_to_run, nb_runs_per_contingency):

                nb_static_ids = len(self.simulations_launched[contingency.id].static_ids)
                nb_runs = min(nb_runs, ceil(0.5 * nb_static_ids))  # Derivatives might not be very accurate if we run many job compared to what has already be done + avoid overcommiting to a single contingency

                contingency_results = self.simulation_results[contingency.id]
                global_derivative, derivative_per_static_id = self.get_statistical_indicator_derivatives(contingency)
                limiting_indicator = limiting_indicators[contingency.id]
                global_derivative, derivative_per_static_id = global_derivative[limiting_indicator], derivative_per_static_id[limiting_indicator]

                cost_per_new_static_id = contingency_results.total_elapsed_time / len(contingency_results.static_ids)  # Average computation time for already run static ids
                weigth = global_derivative / cost_per_new_static_id

                run_static_ids = contingency_results.static_ids
                cost_per_new_dynamic_id = [contingency_results.elapsed_time[static_id] / len(contingency_results.jobs[static_id]) for static_id in run_static_ids]
                weigth_per_static_id = list(np.array(derivative_per_static_id) / np.array(cost_per_new_dynamic_id))

                allocations = JobQueue.allocation([weigth] + weigth_per_static_id, nb_runs)
                static_allocation = allocations[0]
                dynamic_allocations = allocations[1:]

                for i in range(1, static_allocation + 1):
                    if nb_static_ids + i >= len(self.static_samples):
                        logger.logger.critical("Contingency {} running out of static samples, skipping".format(contingency.id))
                        self.contingencies_skipped.append(contingency)
                        break

                    static_sample = self.static_samples_per_contingency[contingency.id][nb_static_ids + i]
                    if DOUBLE_MC_LOOP:
                        job = SpecialJob(static_sample, 0, contingency)
                    else:
                        job = self.create_job(contingency, static_sample)
                    self.simulations_launched[contingency.id].add_job(job)
                    jobs.append(job)

                for i in range(len(run_static_ids)):
                    static_sample = self.simulations_launched[contingency.id].static_ids[i]  # Not self.static_samples_per_contingency[contingency.id][i] as they are not necessarily in the same order
                    for j in range(dynamic_allocations[i]):
                        job = self.create_job(contingency, static_sample)
                        self.simulations_launched[contingency.id].add_job(job)
                        jobs.append(job)

            delta_t = time.time() - t0
            logger.logger.info("get_next_jobs completed in {}s".format(delta_t))
            wait_for_data = False
            return jobs, wait_for_data

    def write_analysis_output(self, err=False):
        t0 = time.time()
        root = etree.Element('Analysis')
        root.set('total_risk', str(self.total_risk))
        root.set('interrupted', str(err))
        total_computation_time = 0
        for contingency_results in self.simulation_results.values():
            total_computation_time += contingency_results.total_elapsed_time
        root.set('total_computation_time', str(total_computation_time))

        for contingency in self.contingencies:
            contingency_results = self.simulation_results[contingency.id]
            mean = contingency_results.get_average_load_shedding()
            max_shedding = contingency_results.get_maximum_load_shedding()
            N = sum([len(contingency_results.jobs[static_id]) for static_id in contingency_results.static_ids])
            N_static = len(contingency_results.static_ids)
            indicator_1, indicator_2 = self.get_statistical_indicators(contingency)
            contingency_attrib = {'id': contingency.id,
                                  'frequency': str(contingency.frequency),
                                  'mean_load_shed': str(mean),
                                  'max_load_shed': str(max_shedding),
                                  'risk': str(contingency.frequency * mean),
                                  'N': str(N),
                                  'N_static': str(N_static),
                                  'ind_1': str(indicator_1),
                                  'ind_2': str(indicator_2)}
            contingency_element = etree.SubElement(root, 'Contingency', contingency_attrib)

            for static_id in contingency_results.static_ids:
                mean = contingency_results.get_average_load_shedding_per_static_id(static_id)
                variance = contingency_results.get_variance_per_static_id_allow_error(static_id, value_on_error=np.nan)
                N = len(contingency_results.jobs[static_id])
                static_id_attrib = {'static_id': static_id,
                                    'mean_load_shed': str(mean),
                                    'risk': str(mean * contingency.frequency),
                                    'std_dev': str(sqrt(variance)),
                                    'N': str(N)}
                if DOUBLE_MC_LOOP:
                    special_job = contingency_results.jobs[static_id][0]
                    static_id_attrib['variable_order'] = str(special_job.variable_order)
                    static_id_attrib['missing_events'] = str(special_job.missing_events)

                job = contingency_results.jobs[static_id][0]
                static_id_element = etree.SubElement(contingency_element, 'StaticId', static_id_attrib)

                for job in contingency_results.jobs[static_id]:
                    job_attrib = {'dyn_id': str(job.dynamic_seed),
                                'simulation_time': '{:.2f}'.format(job.elapsed_time),
                                'timeout': str(job.timed_out)}
                    if job.completed or job.timed_out:
                        job_attrib['load_shedding'] = '{:.2f}'.format(job.results.load_shedding)
                    etree.SubElement(static_id_element, 'Job', job_attrib)

        with open('AnalysisOutput.xml', 'wb') as doc:
            doc.write(etree.tostring(root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
        delta_t = time.time() - t0
        logger.logger.info('Write analysis output completed in {}s'.format(delta_t))


    @staticmethod
    def get_minimum_number_of_static_seeds(contingency: Contingency):
        if contingency.frequency > OUTAGE_RATE_PER_KM * 1:  # Most likely a N-1 contingency
            min_nb_static_seeds = MIN_NUMBER_STATIC_SEED_N_1
        else:  # Most likely a N-2 contingency
            min_nb_static_seeds = MIN_NUMBER_STATIC_SEED_N_2
        return min_nb_static_seeds

    def is_statistical_accuracy_reached(self, contingency: Contingency) -> bool:
        indicator_1, indicator_2 = self.get_statistical_indicators(contingency)

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

    def get_statistical_indicators(self, contingency: Contingency):
        contingency_results = self.simulation_results[contingency.id]
        static_ids = contingency_results.static_ids.copy()

        if DOUBLE_MC_LOOP:
            for static_id in static_ids.copy():
                special_job = contingency_results.jobs[static_id][0]
                if (special_job.variable_order or special_job.missing_events) and len(contingency_results.jobs[static_id]) < MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED:
                    static_ids.remove(static_id)  # A static id is considered to be not yet run if if does not yet have MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED already finished (avoids div by 0)

        N_per_static_id = np.array([len(contingency_results.jobs[static_id]) for static_id in static_ids])
        N = len(static_ids)

        mean_per_static_id = np.array([contingency_results.get_average_load_shedding_per_static_id(static_id) for static_id in static_ids])
        mean = np.mean(mean_per_static_id)
        std_dev = sqrt(np.var(mean_per_static_id))  # TODO: add sqrt(N/(N-1)) factor and handle div by 0 in this case

        indicator_1 = contingency.frequency * sqrt(std_dev**2) / sqrt(N) #  + np.mean(variance_per_static_id / N_per_static_id)) / sqrt(N)
        if contingency.frequency > OUTAGE_RATE_PER_KM * 1:
            indicator_2 = contingency.frequency * (100 - mean) / N
        else:
            indicator_2 = contingency.frequency * (100 - mean) / N
        return indicator_1, indicator_2

    def get_distances_from_statistical_accuracy(self, contingency: Contingency):
        return [indicator - 0.01 * self.total_risk for indicator in self.get_statistical_indicators(contingency)]


    def get_statistical_indicator_derivatives(self, contingency: Contingency):
        """
        Evaluate the potential improvement in statistical indicators if the number of static runs (global derivatives) or
        dynamic runs (derivative_per_static_id) was increased
        """
        contingency_results = self.simulation_results[contingency.id]
        contingency_launched_jobs = self.simulations_launched[contingency.id]
        static_ids = contingency_results.static_ids

        mean_per_static_id = np.array([contingency_results.get_average_load_shedding_per_static_id(static_id) for static_id in static_ids])
        mean = np.mean(mean_per_static_id)
        std_dev = sqrt(np.var(mean_per_static_id))  # TODO: add sqrt(N/(N-1)) factor and handle div by 0 in this case

        # Compute N and N_per_static_id from simulations "launched" not completed, this lowers priority of contingencies that have jobs currently running
        static_ids = contingency_launched_jobs.static_ids
        N = len(static_ids)
        variance_per_static_id = np.array([contingency_results.get_variance_per_static_id_allow_error(static_id, value_on_error=0) for static_id in static_ids])
        N_per_static_id = [len(contingency_launched_jobs.dynamic_seeds[static_id]) for static_id in static_ids]
        N_per_static_id = np.array(N_per_static_id)

        global_derivative_1 = contingency.frequency * sqrt(std_dev**2 + np.mean(variance_per_static_id / N_per_static_id)) * (1/sqrt(N) - 1/sqrt(N+1))
        global_derivative_2 = contingency.frequency * ((100 - mean) / N - (100 - mean) / (N + 1))

        derivative_1_per_static_id = []
        derivative_2_per_static_id = []
        SE = sqrt(std_dev**2 + np.mean(variance_per_static_id / N_per_static_id)) / sqrt(N)
        for i in range(len(contingency_results.static_ids)):
            if std_dev == 0:
                der_1 = 0
                der_2 = 0
            else:
                N_per_static_id[i] += 1
                der_1 = contingency.frequency * (SE - (sqrt(std_dev**2 + np.mean(variance_per_static_id / N_per_static_id)) / sqrt(N)))
                N_per_static_id[i] -= 1
                der_2 = 0
            derivative_1_per_static_id.append(der_1)
            derivative_2_per_static_id.append(der_2)

        return (global_derivative_1, global_derivative_2), (derivative_1_per_static_id, derivative_2_per_static_id)


    @staticmethod
    def allocation(weigths, total_to_allocate: int):
        """
        Allocate an integer number of runs among multiple scenarios based on their weigths. Uses the d'Hondt/Jefferson method (avoids party fragmentation).
        """
        assert sum(weigths) > 0
        weigths = np.array(weigths)
        dividors = np.array([1] * len(weigths))

        for i in range(total_to_allocate):
            highest = np.argmax(weigths / dividors)
            dividors[highest] += 1

        allocations = dividors - 1
        return list(allocations)

class ContingencyLaunched:
    def __init__(self):
        self.static_ids = []
        self.dynamic_seeds = {}

    def add_job(self, job: Job):
        static_id = job.static_id
        if static_id in self.static_ids:
            self.dynamic_seeds[static_id].append(job)
        else:
            self.static_ids.append(static_id)
            self.dynamic_seeds[static_id] = [job]

class ContingencyResults:
    def __init__(self):
        self.static_ids = []
        self.jobs: dict[int, list(Job)]
        self.jobs = {}
        self.sum_load_shedding = {}
        self.sum_load_shedding_squared = {}
        self.elapsed_time = {}
        self.total_elapsed_time = 0

    def add_job(self, job: Job):
        static_id = job.static_id
        if static_id in self.static_ids:
            self.jobs[static_id].append(job)
            self.sum_load_shedding[static_id] += job.results.load_shedding
            self.sum_load_shedding_squared[static_id] += job.results.load_shedding ** 2
            self.elapsed_time[static_id] += job.elapsed_time
        else:
            self.static_ids.append(static_id)
            self.jobs[static_id] = [job]
            self.sum_load_shedding[static_id] = job.results.load_shedding
            self.sum_load_shedding_squared[static_id] = job.results.load_shedding ** 2
            self.elapsed_time[static_id] = job.elapsed_time
        self.total_elapsed_time += job.elapsed_time

    def get_variance_per_static_id_no_error(self, static_id):
        """
        Naive computation of the variance following https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance
        Since N should be at most 1000, and the variance at most two order of magnitudes below the average (and not
        both at the same time), numerical stability should not be an issue
        """
        if not DOUBLE_MC_LOOP:
            return 0
        if isinstance(self.jobs[static_id][0], SpecialJob):
            if not (self.jobs[static_id][0].variable_order or self.jobs[static_id][0].missing_events):
                return 0
        else:
            logger.logger.warn("First job for a given static id should always be a special job")

        sum_ = self.sum_load_shedding[static_id]
        sum_sq = self.sum_load_shedding_squared[static_id]
        n = len(self.jobs[static_id])
        variance = (sum_sq - (sum_**2) / n) / (n - 1)
        if variance < 0 and variance > -1e-6:  # Avoids negative values caused by numerical errors
            variance = 0
        return variance

    def get_variance_per_static_id_allow_error(self, static_id, value_on_error):
        if not DOUBLE_MC_LOOP:
            return 0
        if static_id not in self.jobs:
            return value_on_error
        if isinstance(self.jobs[static_id][0], SpecialJob):
            if not (self.jobs[static_id][0].variable_order or self.jobs[static_id][0].missing_events):
                return 0
        else:
            logger.logger.warn("First job for a given static id should always be a special job")

        n = len(self.jobs[static_id])
        if n < 2:
            return value_on_error
        else:
            return self.get_variance_per_static_id_no_error(static_id)

    def get_average_load_shedding_per_static_id(self, static_id):
        return self.sum_load_shedding[static_id] / len(self.jobs[static_id])

    def get_average_load_shedding(self):
        average_load_shedding_per_static_id = [self.get_average_load_shedding_per_static_id(static_id) for static_id in self.static_ids]
        return np.mean(average_load_shedding_per_static_id)  # For now, all static_id have the same weigth

    def get_maximum_load_shedding(self):
        average_load_shedding_per_static_id = [self.get_average_load_shedding_per_static_id(static_id) for static_id in self.static_ids]
        max = 0
        for load_shedding in average_load_shedding_per_static_id:
            if load_shedding > max and load_shedding <= 100:  # Disregard non convergence cases
                max = load_shedding
        return max


    # TODO: ctrl+h static_id -> static_seed, or reverse (because of the way they are generated), same for static_files ?

def hash(string):
    """
    Deterministic hashing function, implementation does not really matter
    """
    return int(hashlib.sha1(bytes(string, 'utf-8')).hexdigest()[:10], 16)  # Only use 10 firs bytes of the hexdigest because that's plenty enough
