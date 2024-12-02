from __future__ import annotations
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
if WITH_LXML:
    from lxml import etree
else:
    import xml.etree.ElementTree as etree
import numpy as np
from natsort import natsorted
import time
import pickle
import shutil
from collections import defaultdict
# from pympler import asizeof

class Master:
    def __init__(self, slaves: list[int]):
        if len(slaves) == 0:
            raise ValueError('Need at least one slave')

        self.comm = MPI.COMM_WORLD
        self.slaves = set(slaves)
        self.slaves_state = {slave: 'Waiting' for slave in self.slaves}
        self.create_contingency_list()
        self.job_queue = JobQueue(self.contingency_list)
        self.run()

    def create_contingency_list(self):
        base_contingency = Contingency.create_base_contingency()
        N_1_contingencies = Contingency.create_N_1_contingencies(with_normal_clearing=True)
        N_2_contingencies = Contingency.create_N_2_contingencies()

        self.contingency_list = base_contingency + N_1_contingencies + N_2_contingencies
        logger.logger.info('Considering {} contingencies: {} base, {} N-1, {} N-2'.format(len(self.contingency_list), len(base_contingency), len(N_1_contingencies), len(N_2_contingencies)))

    def run(self):
        init = True
        jobs_to_run, _ = self.job_queue.get_next_jobs(init=True)
        n_iter = 0
        try:
            while True:
                if len(jobs_to_run) == 0:  # No more jobs in queue, so repopulate it with get_next_jobs()
                    if init:
                        logger.logger.info('Launched all NB_MIN_RUNS jobs')
                        init = False
                    n_iter += 1
                    jobs_to_run, wait_for_data = self.job_queue.get_next_jobs(init=False)
                    logger.logger.info("")
                    logger.logger.info("Launching batch {} of simulations".format(n_iter))

                    while wait_for_data:
                        self.comm.probe(source=MPI.ANY_SOURCE, tag=MPI_TAGS.DONE.value, status=status)
                        self.get_data_from_slave(status)
                        jobs_to_run, wait_for_data = self.job_queue.get_next_jobs(init=False)

                    if len(jobs_to_run) == 0:  # No more jobs to run and not waiting for data just after call to get_next_job call(), so stop
                        break

                status = MPI.Status()
                self.comm.probe(source=MPI.ANY_SOURCE, tag=MPI.ANY_TAG, status=status)
                tag = status.Get_tag()

                if tag == MPI_TAGS.READY.value:
                    job = jobs_to_run.pop(0)
                    self.send_work_to_slave(job, status)
                elif tag == MPI_TAGS.DONE.value:
                    self.get_data_from_slave(status)
                else:
                    raise NotImplementedError("Unexpected tag:", tag)

            self.job_queue.write_saved_results()
            self.job_queue.write_analysis_output()

            logger.logger.info(("##############################################"))
            logger.logger.info(("# Statistical accuracy reached, running"))
            logger.logger.info(("# additional samples for critical contingencies"))
            logger.logger.info(("##############################################"))

            jobs_to_run = self.job_queue.get_additional_jobs()
            while len(jobs_to_run) > 0:
                status = MPI.Status()
                self.comm.probe(source=MPI.ANY_SOURCE, tag=MPI.ANY_TAG, status=status)
                tag = status.Get_tag()

                if tag == MPI_TAGS.READY.value:
                    job = jobs_to_run.pop(0)
                    self.send_work_to_slave(job, status)
                elif tag == MPI_TAGS.DONE.value:
                    self.get_data_from_slave(status)
                else:
                    raise NotImplementedError("Unexpected tag:", tag)

            self.terminate_slaves()
            self.job_queue.write_saved_results()
            self.job_queue.write_analysis_output(done=True)
            # self.show_memory_usage()
        except KeyboardInterrupt:
            self.job_queue.write_saved_results()
            self.job_queue.write_analysis_output()
            # self.show_memory_usage()

    """ def show_memory_usage(self):
        print('1  Job queue', asizeof.asizeof(self.job_queue) / 1e6)
        print('2  Job queue', asizeof.asizeof(self.job_queue.contingencies) / 1e6)
        print('3  Job queue', asizeof.asizeof(self.job_queue.contingencies_skipped) / 1e6)
        print('4  Job queue', asizeof.asizeof(self.job_queue.static_samples) / 1e6)
        print('5  Job queue', asizeof.asizeof(self.job_queue.static_samples_per_contingency) / 1e6)
        print('6  Job queue', asizeof.asizeof(self.job_queue.simulation_results) / 1e6)
        print('7  Job queue', asizeof.asizeof(self.job_queue.simulations_launched) / 1e6)
        print('8  Job queue', asizeof.asizeof(self.job_queue.risk_per_contingency) / 1e6)
        print('9  Job queue', asizeof.asizeof(self.job_queue.dynamic_seed_counters) / 1e6)
        print('10 Job queue', asizeof.asizeof(self.job_queue.priority_queue) / 1e6)
        print('11 Job queue', asizeof.asizeof(self.job_queue.saved_results) / 1e6)
        print('12 Contingency list', asizeof.asizeof(self.contingency_list) / 1e6)
        print('13 Slave state', asizeof.asizeof(self.slaves_state) / 1e6)

        for contingency_result in self.job_queue.simulation_results.values():
            for jobs in contingency_result.jobs.values():
                job = jobs[0]
                print('Completed job', asizeof.asizeof(job))
                break
            break
        for contingency_launched in self.job_queue.simulations_launched.values():
            for jobs in contingency_launched.dynamic_seeds.values():
                job = jobs[0]
                print('Init job', asizeof.asizeof(job))
                break
            break """


    def terminate_slaves(self):
        """
        Wait for slaves to finish their current job then kill them
        """
        for slave in self.slaves_state.keys():
            # Wait for slaves to finish running jobs
            if self.slaves_state[slave] == 'Working':
                status = MPI.Status()
                self.comm.probe(source=slave, tag=MPI_TAGS.DONE.value, status=status)
                self.get_data_from_slave(status)

            # Terminate slaves
            self.comm.send(obj=None, dest=slave, tag=MPI_TAGS.EXIT.value)
            self.comm.recv(source=slave, tag=MPI_TAGS.EXIT.value)


    def load_job_results(self, job: Job) -> Job:
        """
        Return job results if they exist in self.job_queue.saved_results, otherwise return None
        """
        if job.contingency.id in self.job_queue.saved_results:
            if job.static_id in self.job_queue.saved_results[job.contingency.id]:
                if job.dynamic_seed in self.job_queue.saved_results[job.contingency.id][job.static_id]:
                    if self.job_queue.saved_results[job.contingency.id][job.static_id][job.dynamic_seed].completed:
                        return self.job_queue.saved_results[job.contingency.id][job.static_id][job.dynamic_seed]
        return None


    def send_work_to_slave(self, job, status: MPI.Status):
        if REUSE_RESULTS:
            saved_job = self.load_job_results(job)
            if saved_job is not None:  # If save of job exist
                if saved_job.results.load_shedding <= 100.1:
                    self.job_queue.store_completed_job(saved_job, exists=True)
                    return  # Don't rerun job
                else:
                    pass  # Rerun timeouts and cancelled jobs

        slave = status.Get_source()
        self.comm.recv(source=slave, tag=MPI_TAGS.READY.value, status=status)
        logger.logger.log(logger.logging.TRACE, 'Master: sending input job {} to slave {}'.format(job, slave))
        self.comm.send(obj=job, dest=slave, tag=MPI_TAGS.START.value)
        self.slaves_state[slave] = 'Working'


    def get_data_from_slave(self, status: MPI.Status):
        slave = status.Get_source()
        job = self.comm.recv(source=slave, tag=MPI_TAGS.DONE.value)
        self.slaves_state[slave] = 'Waiting'
        logger.logger.log(logger.logging.TRACE, 'Master: slave {} returned {}'.format(slave, job))
        self.job_queue.store_completed_job(job)


class JobQueue:
    # Note that in the current implementation, it is assumed that all contingencies "make sense" for all static samples,
    # i.e. that all elements are always connected (no maintenance, transmission switching, constant substation,
    # configurations). Otherwise, one should first check for each contingency, for which static samples this
    # contingency is possible, and only samples from those + weigth the probability of the contingency accordingly

    def __init__(self, contingencies: list[Contingency]):
        self.contingencies = contingencies
        self.contingencies_skipped = []

        self.static_samples = []
        static_files = natsorted(glob.glob(f'../2-SCOPF/d-Final-dispatch/{CASE}_{NETWORK_NAME}/*.iidm'))  # glob gives files in arbitrary order, sort them to be deterministic
        for file in static_files:
            self.static_samples.append(os.path.basename(file).split('.')[0])
        self.static_samples_per_contingency = {}
        for contingency in self.contingencies:
            samples = self.static_samples.copy()
            random_generator = random.Random(hash(contingency.id))  # The same static ids are always used for a given contingency to make the algo deterministic
            random_generator.shuffle(samples)
            self.static_samples_per_contingency[contingency.id] = samples

        self.simulation_results: defaultdict[str, ContingencyResults] = defaultdict(ContingencyResults)
        self.simulations_launched : dict[str, ContingencyLaunched] = defaultdict(ContingencyLaunched)
        self.total_risk = 0
        self.total_cost = 0
        self.risk_per_contingency = defaultdict(int)
        self.cost_per_contingency = defaultdict(int)

        # To make the algorithm deterministic (in an MPI context), a seed is given to each set of (contingency, static_id, number of runs for this contingency and static id)
        self.dynamic_seed_counters = defaultdict(lambda: {static_sample: hash(static_sample) for static_sample in self.static_samples})

        self.priority_queue: list[Job]
        self.priority_queue = []

        self.saved_results_path = 'saved_results.pickle'
        self.saved_results_backup_path = 'saved_results_bak.pickle'
        self.load_saved_results()

    def load_saved_results(self):
        """
        Load results of past runs from the saved_results.pickle file to self.saved_results
        If REUSE_RESULTS_FAST_FORWARD, those results are directly included in the results of the analysis,
        otherwise, they are only included if the master requests to perform a job that exists in saved_results
        """
        self.saved_results: dict[str, dict[int, dict[int, Job]]]
        if os.path.exists(self.saved_results_path):
            with open(self.saved_results_path, 'rb') as file:
                try:
                    self.saved_results = pickle.load(file)
                except pickle.UnpicklingError:
                    with open(self.saved_results_backup_path, 'rb') as backup_file:
                        self.saved_results = pickle.load(backup_file)
        else:
            self.saved_results = {}

        if REUSE_RESULTS_FAST_FORWARD:
            self.fast_forward_load_job_results()
            self.write_analysis_output()

    def write_saved_results(self):
        t0 = time.time()
        # Pickle to a temp file to guarantee one correct version always exists if the program is interrupted
        with open(self.saved_results_backup_path, 'wb') as file:
            pickle.dump(self.saved_results, file, protocol=pickle.HIGHEST_PROTOCOL)
        shutil.copyfile(self.saved_results_backup_path, self.saved_results_path)
        delta_t = time.time() - t0
        logger.logger.info('Write saved results completed in {}s'.format(delta_t))

    def fast_forward_load_job_results(self):
        for contingency in self.contingencies:  # Only fast-forward base contingencies, not hidden-failures (otherwise can generate duplicate + allows to change MAX_TOTAL_HIDDEN_FAILURES and other similar parameters)
            if contingency.id in self.saved_results:
                logger.logger.info('Fast forward load of contingency {}'.format(contingency.id))
                for static_id in self.saved_results[contingency.id].values():
                    for saved_job in static_id.values():
                        self.simulations_launched[saved_job.contingency.id].add_job(saved_job)  # Emulate an actual job launch
                        self.store_completed_job(saved_job, exists=True)

    def add_job_to_priority_queue(self, job: Job):
        self.priority_queue.append(job)
        self.simulations_launched[job.contingency.id].add_job(job)

    def store_completed_job(self, job: Job, exists=False):
        if not exists:
            self.saved_results.setdefault(job.contingency.id, {})
            self.saved_results[job.contingency.id].setdefault(job.static_id, {})
            self.saved_results[job.contingency.id][job.static_id][job.dynamic_seed] = job

        self.simulation_results[job.contingency.id].add_job(job)

        if '~' in job.contingency.id:
            base_contingency_id = job.contingency.id.split('~')[0]
            total_cases_base = len(self.simulation_results[base_contingency_id].static_ids)
            total_cases = len(self.simulation_results[job.contingency.id].static_ids)
            conditional_probability = total_cases / total_cases_base if total_cases_base > 0 else 0
        else:
            conditional_probability = 1

        self.risk_per_contingency[job.contingency.id] = self.simulation_results[job.contingency.id].get_average_load_shedding() * job.contingency.frequency * conditional_probability
        self.cost_per_contingency[job.contingency.id] = self.simulation_results[job.contingency.id].get_average_cost() * job.contingency.frequency * conditional_probability
        self.total_risk = sum(self.risk_per_contingency.values())
        self.total_cost = sum(self.cost_per_contingency.values())

        if isinstance(job, SpecialJob):
            if job.variable_order or job.missing_events:
                for j in range(MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED - 1):
                    if not REUSE_RESULTS_FAST_FORWARD:
                        new_job = self.create_job(job.contingency, job.static_id)
                        self.add_job_to_priority_queue(new_job)
                    else:
                        dynamic_seed = self.dynamic_seed_counters[job.contingency.id][job.static_id]
                        self.dynamic_seed_counters[job.contingency.id][job.static_id] += 1

                        saved_job = self.saved_results.get(job.contingency.id, {}).get(job.static_id, {}).get(dynamic_seed, None)
                        if saved_job is not None:
                            saved_job = self.saved_results[job.contingency.id][job.static_id][dynamic_seed]
                            self.store_completed_job(saved_job, exists=True)
                        else:
                            self.add_job_to_priority_queue(Job(job.static_id, dynamic_seed, job.contingency))

        if WITH_HIDDEN_FAILURES:
            if job.results.load_shedding > 30:
                pass  # Don't model hidden failure for cases that already lead to load shedding (cascades ==> many possibilities for hidden failure would need to be considered, but low impact)
            elif job.contingency.order + 1 > MAX_HIDDEN_FAILURE_ORDER:
                pass  # Don't create new jobs with order higher than MAX_HIDDEN_FAILURE_ORDER
            else:
                excited_hidden_failures = list(set(job.results.excited_hidden_failures))
                excited_hidden_failures.sort()
                for parent_failure in job.contingency.protection_hidden_failures:
                    if parent_failure in excited_hidden_failures:
                        excited_hidden_failures.remove(parent_failure)

                if len(excited_hidden_failures) > MAX_POSSIBLE_PROTECTION_HIDDEN_FAILURES:
                    logger.logger.warning(f'{job.contingency.id}, {job.static_id}, {job.dynamic_seed}, can lead to more than {MAX_POSSIBLE_PROTECTION_HIDDEN_FAILURES} possible hidden failures ({len(excited_hidden_failures)}), skipping some.')

                # Create jobs with one additional hidden failure activated compared to the parent job
                for hidden_failure in excited_hidden_failures[:MAX_POSSIBLE_PROTECTION_HIDDEN_FAILURES]:
                    new_job = job.__class__.from_parent_and_protection_failure(job, hidden_failure)
                    self.launch_hidden_failure_job(job, new_job)

                # Create jobs with one hidden failure in a nearby generator
                for generator_failure in sorted(list(set(job.results.excited_generator_failures))):
                    if generator_failure in job.contingency.generator_failures:
                        continue
                    new_job = job.__class__.from_parent_and_generator_failure(job, generator_failure)
                    self.launch_hidden_failure_job(job, new_job)


    def launch_hidden_failure_job(self, parent_job: Job, hidden_failure_job: Job):
        # Search in launched simulations if same job does not already exists (e.g. job created with hidden failure A then B, vs. B then A are equivalent)
        job_already_exists = False
        if hidden_failure_job.static_id in self.simulations_launched[hidden_failure_job.contingency.id].static_ids:
            if hidden_failure_job.dynamic_seed in self.simulations_launched[hidden_failure_job.contingency.id].dynamic_seeds[hidden_failure_job.static_id]:
                job_already_exists = True

        if job_already_exists:
            pass  # Not needed to rerun it
        elif DOUBLE_MC_LOOP and not isinstance(parent_job, SpecialJob):
            pass  # Only allow special jobs to create jobs with additional hidden failures (avoid duplicates and remaining cases are a bit too specific (hidden failure activated only when the path of the cascade is affected by small protection uncertainties))
        else:
            if REUSE_RESULTS_FAST_FORWARD:
                saved_job = self.saved_results.get(hidden_failure_job.contingency.id, {}).get(hidden_failure_job.static_id, {}).get(hidden_failure_job.dynamic_seed, None)
                if saved_job is not None:
                    self.simulations_launched[saved_job.contingency.id].add_job(saved_job)  # Emulate an actual job launch
                    self.store_completed_job(saved_job, exists=True)
                else:
                    self.add_job_to_priority_queue(hidden_failure_job)
            else:
                self.add_job_to_priority_queue(hidden_failure_job)


    def create_job(self, contingency: Contingency, static_id):
        dynamic_seed = self.dynamic_seed_counters[contingency.id][static_id]
        self.dynamic_seed_counters[contingency.id][static_id] += 1
        return Job(static_id, dynamic_seed, contingency)


    def get_next_jobs(self, init: bool) -> tuple[list[Job], bool]:
        t0 = time.time()
        jobs = []
        nb_priority_jobs = len(self.priority_queue)
        logger.logger.info(("{} jobs in priority queue".format(nb_priority_jobs)))
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
            return jobs, False

        if init:
            # Run an arbitrary number of simulations to start up the algorithm (allow to have a first estimate of the total
            # risk and sampled variances)
            for contingency in self.contingencies:
                for i in range(MIN_NUMBER_STATIC_SEED):
                    static_sample = self.static_samples_per_contingency[contingency.id][i]

                    if DOUBLE_MC_LOOP:
                        job = SpecialJob(static_sample, 0, contingency)
                    else:
                        job = self.create_job(contingency, static_sample)

                    if REUSE_RESULTS_FAST_FORWARD:
                        if job.static_id in self.simulations_launched[contingency.id].static_ids:
                            if job.dynamic_seed in self.simulations_launched[contingency.id].dynamic_seeds[job.static_id]:
                                continue  # Init job already included in saved results, so don't relaunch it

                    self.simulations_launched[contingency.id].add_job(job)
                    jobs.append(job)

            wait_for_data = False
            return jobs, wait_for_data

        else:
            self.write_saved_results()
            self.write_analysis_output()

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
                init_completed = True
                if len(self.simulation_results[contingency.id].static_ids) < MIN_NUMBER_STATIC_SEED:
                    contingencies_waiting.append(contingency)
                    logger.logger.log(logger.logging.TRACE, 'Contingency {} waiting for first static seed runs'.format(contingency.id))
                    init_completed = False
                else:
                    if DOUBLE_MC_LOOP:  # Check if all dynamic runs of all initial runs have been completed
                        for static_id in self.simulation_results[contingency.id].static_ids[:MIN_NUMBER_STATIC_SEED]:
                            nb_completed_runs = len(self.simulation_results[contingency.id].jobs[static_id])
                            special_job = self.simulation_results[contingency.id].jobs[static_id][0]
                            if (special_job.variable_order or special_job.missing_events) and nb_completed_runs < MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED:
                                contingencies_waiting.append(contingency)
                                logger.logger.info('Contingency {} waiting for first dynamic seed runs'.format(contingency.id))
                                init_completed = False
                                break

                if not init_completed:
                    continue
                if self.is_statistical_accuracy_reached(contingency):
                    continue

                contingencies_to_run.append(contingency)

            if not contingencies_to_run and len(jobs) > 0:
                logger.logger.info("Only priority runs remaining")
                wait_for_data = False
                return jobs, wait_for_data

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

            logger.logger.debug("##############################################")
            logger.logger.debug("# Contingency weigths")
            logger.logger.debug("##############################################")
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
                # Only consider the statistical indicator that is the furthest from being satisfied
                limiting_indicator = np.argmax(distances_from_statistical_accuracy)
                weigth = max(distances_from_statistical_accuracy)
                assert weigth > 0  # Distance should be positive as only contingencies that have not converged yet are considered at this stage
                logger.logger.debug('Contingency {}: {}'.format(contingency.id, weigth))
                weigths.append(weigth)
                limiting_indicators[contingency.id] = limiting_indicator

            nb_runs_per_contingency = JobQueue.allocation(weigths, NB_RUNS_PER_INDICATOR_EVALUATION - nb_priority_jobs)


            for contingency, nb_runs in zip(contingencies_to_run, nb_runs_per_contingency):
                nb_static_ids = len(self.simulations_launched[contingency.id].static_ids)
                nb_runs = min(nb_runs, ceil(0.5 * nb_static_ids))  # Indicators might not be very accurate if we run many job compared to what has already be done + avoid overcommiting to a single contingency

                """ contingency_results = self.simulation_results[contingency.id]
                global_derivative, derivative_per_static_id = self.get_statistical_indicator_derivatives(contingency)
                limiting_indicator = limiting_indicators[contingency.id]
                global_derivative, derivative_per_static_id = global_derivative[limiting_indicator], derivative_per_static_id[limiting_indicator]

                cost_per_new_static_id = contingency_results.total_elapsed_time / len(contingency_results.static_ids)  # Average computation time for already run static ids
                weigth = global_derivative / cost_per_new_static_id

                run_static_ids = contingency_results.static_ids
                cost_per_new_dynamic_id = [contingency_results.elapsed_time[static_id] / len(contingency_results.jobs[static_id]) for static_id in run_static_ids]
                weigth_per_static_id = list(np.array(derivative_per_static_id) / np.array(cost_per_new_dynamic_id)

                allocations = JobQueue.allocation([weigth] + weigth_per_static_id, nb_runs)
                static_allocation = allocations[0]
                dynamic_allocations = allocations[1:] """
                # It is found best to only run the minimum of dynamic seeds per static samples, so no additional dynamic runs are allocated
                static_allocation = nb_runs
                dynamic_allocations = [0] * len(self.simulation_results[contingency.id].static_ids)

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

                for i in range(len(self.simulation_results[contingency.id].static_ids)):
                    static_sample = self.simulations_launched[contingency.id].static_ids[i]  # Not self.static_samples_per_contingency[contingency.id][i] as they are not necessarily in the same order
                    for j in range(dynamic_allocations[i]):
                        job = self.create_job(contingency, static_sample)
                        self.simulations_launched[contingency.id].add_job(job)
                        jobs.append(job)

            delta_t = time.time() - t0
            logger.logger.info("get_next_jobs completed in {}s".format(delta_t))
            wait_for_data = False
            return jobs, wait_for_data


    def get_additional_jobs(self) -> list[Job]:
        """
        Run at least MIN_NUMBER_STATIC_SEED_CRITICAL_CONTINGENCY for critical contingencies.
        Useful to train machine learning models in step 5-SecurityEnhancement
        """
        jobs = []
        worst_contingency_ids = [key for key, _ in sorted(self.cost_per_contingency.items(), key = lambda item:item[1], reverse=True)]
        worst_contingencies: list[Contingency]
        worst_contingencies = []
        for worst_contingency_id in worst_contingency_ids:
            for contingency in self.contingencies:
                if contingency.id == worst_contingency_id:
                    worst_contingencies.append(contingency)
                    break

        for critical_contingency in worst_contingencies[:10]:
            nb_static_ids_launched = len(self.simulations_launched[critical_contingency.id].static_ids)
            nb_static_ids_to_launch = MIN_NUMBER_STATIC_SEED_CRITICAL_CONTINGENCY - nb_static_ids_launched
            logger.logger.info("Launching {} jobs for critical contingency {}".format(max(0, nb_static_ids_to_launch), critical_contingency.id))

            if nb_static_ids_to_launch < 1:
                continue  # Enough samples launched for this contingency

            for i in range(1, nb_static_ids_to_launch + 1):
                if nb_static_ids_launched + i >= len(self.static_samples):
                    logger.logger.warn("MIN_NUMBER_STATIC_SEED_CRITICAL_CONTINGENCY larger than number of available static samples, stopping at {}".format(len(self.static_samples)))
                    break
                static_sample = self.static_samples_per_contingency[critical_contingency.id][nb_static_ids_launched + i]

                if DOUBLE_MC_LOOP:
                    job = SpecialJob(static_sample, 0, critical_contingency)
                else:
                    job = self.create_job(critical_contingency, static_sample)
                self.simulations_launched[critical_contingency.id].add_job(job)
                jobs.append(job)
        return jobs


    def write_analysis_output(self, done=False):
        """
        Write the (current) results of the analysis to the AnalysisOutput.xml file.
        """
        t0 = time.time()
        root = etree.Element('Analysis')
        root.set('total_risk', str(self.total_risk))
        root.set('total_cost', str(self.total_cost))
        root.set('interrupted', str(not done))
        total_computation_time = 0
        for contingency_results in self.simulation_results.values():
            total_computation_time += contingency_results.total_elapsed_time
        root.set('total_computation_time', str(total_computation_time))

        for contingency in self.contingencies:
            contingency_results = self.simulation_results[contingency.id]
            mean = contingency_results.get_average_load_shedding()
            max_shedding = contingency_results.get_maximum_load_shedding()
            mean_cost = contingency_results.get_average_cost()
            N = sum([len(contingency_results.jobs[static_id]) for static_id in contingency_results.static_ids])
            N_static = len(contingency_results.static_ids)
            indicators = self.get_statistical_indicators(contingency)
            total_cases = len(contingency_results.static_ids)
            cases_unsecure = sum([1 if contingency_results.get_average_cost_per_static_id(static_id) > 0 else 0 for static_id in contingency_results.static_ids])
            contingency_attrib = {'id': contingency.id,
                                  'frequency': '{:.6g}'.format(contingency.frequency),
                                  'mean_load_shed': '{:.4g}'.format(mean),
                                  'max_load_shed': '{:.4g}'.format(max_shedding),
                                  'risk': '{:.4g}'.format(contingency.frequency * mean),
                                  'cost': '{:.4g}'.format(contingency.frequency * mean_cost),
                                  'risk_w_hidden': '{:.4g}'.format(contingency.frequency * mean),  # Written here to book attrib order, updated later
                                  'cost_w_hidden': '{:.4g}'.format(contingency.frequency * mean_cost),  # Written here to book attrib order, updated later
                                  'N': str(N),
                                  'N_static': str(N_static),
                                  'share_unsecure': str(cases_unsecure / total_cases * 100) if total_cases > 0 else 'N/A'}
            for i, indicator in enumerate(indicators):
                contingency_attrib['ind_{}'.format(i+1)] = '{:.4g}'.format(indicator)
            contingency_element = etree.SubElement(root, 'Contingency', contingency_attrib)

            # Add all static_ids and dynamic_seeds simulated for the contingency as SubElements
            self.contingency_results_to_xml(contingency_element, contingency.frequency, contingency_results)

            # Add all child contingencies created by hidden failures
            risk_hidden = 0
            cost_hidden = 0
            for sub_contingency_id in self.simulation_results:
                if '~' not in sub_contingency_id:
                    continue  # Normal contingency (not generated by hidden failure)

                base_contingency_id = sub_contingency_id.split('~')[0]
                if base_contingency_id != contingency.id:
                    continue  # Child contingency (hidden failure) from another parent contingency

                contingency_results = self.simulation_results[sub_contingency_id]
                mean = contingency_results.get_average_load_shedding()
                max_shedding = contingency_results.get_maximum_load_shedding()
                mean_cost = contingency_results.get_average_cost()
                N = sum([len(contingency_results.jobs[static_id]) for static_id in contingency_results.static_ids])
                N_static = len(contingency_results.static_ids)
                total_cases_parent = len(self.simulation_results[contingency.id].static_ids)
                total_cases = len(contingency_results.static_ids)
                cases_unsecure = sum([1 if contingency_results.get_average_cost_per_static_id(static_id) > 0 else 0 for static_id in contingency_results.static_ids])
                frequency = contingency.frequency * HIDDEN_FAILURE_PROBA ** (len(sub_contingency_id.split('~')) - 1) * (total_cases / total_cases_parent)
                risk_hidden += frequency * mean
                cost_hidden += frequency * mean_cost
                sub_contingency_attrib = {'id': sub_contingency_id,
                                  'frequency': '{:.6g}'.format(frequency),
                                  'conditional_probability': '{:.3g}'.format(total_cases / total_cases_parent),  # How often the hidden failure is excited when the main contingency occurs
                                  'mean_load_shed': '{:.4g}'.format(mean),
                                  'max_load_shed': '{:.4g}'.format(max_shedding),
                                  'risk': '{:.4g}'.format(frequency * mean),
                                  'cost': '{:.4g}'.format(frequency * mean_cost),
                                  'N': str(N),
                                  'N_static': str(N_static),
                                  'share_unsecure': str(cases_unsecure / total_cases * 100) if total_cases > 0 else 'N/A'}
                sub_contingency_element = etree.SubElement(contingency_element, 'Contingency', sub_contingency_attrib)
                self.contingency_results_to_xml(sub_contingency_element, frequency, contingency_results)

            contingency_element.set('risk_w_hidden', '{:.4g}'.format(float(contingency_attrib['risk']) + risk_hidden))
            contingency_element.set('cost_w_hidden', '{:.4g}'.format(float(contingency_attrib['cost']) + cost_hidden))

        if WITH_LXML:
            with open('AnalysisOutput.xml', 'wb') as doc:
                doc.write(etree.tostring(root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
        else:
            tree = etree.ElementTree(root)
            etree.indent(tree, space="\t")  # Pretty-print
            tree.write('AnalysisOutput.xml', xml_declaration=True, encoding='UTF-8')

        root[:] = sorted(root, key=lambda element: element.get('cost_w_hidden'), reverse=True)  # Sort by decreasing order of cost
        short_root = root
        for i, element in enumerate(root):
            if i < 10:
                pass
            else:
                short_root.remove(element)

        if WITH_LXML:
            with open('AnalysisOutput_critical.xml', 'wb') as doc:
                doc.write(etree.tostring(short_root, pretty_print = True, xml_declaration = True, encoding='UTF-8'))
        else:
            tree = etree.ElementTree(short_root)
            etree.indent(tree, space="\t")  # Pretty-print
            tree.write('AnalysisOutput_critical.xml', xml_declaration=True, encoding='UTF-8')

        delta_t = time.time() - t0
        logger.logger.info('Write analysis output completed in {}s'.format(delta_t))


    def contingency_results_to_xml(self, contingency_element: etree.Element, frequency, contingency_results: ContingencyResults):
        for static_id in contingency_results.static_ids:
            min_shc = 999
            voltage_stable = True
            min_CCT = 999
            transient_stable = True
            max_RoCoF = 0
            max_power_loss_over_reserve = 0
            frequency_stable = True
            mean = contingency_results.get_average_load_shedding_per_static_id(static_id)
            mean_cost = contingency_results.get_average_cost_per_static_id(static_id)
            variance = contingency_results.get_cost_variance_per_static_id_allow_error(static_id, value_on_error=np.nan)
            N = len(contingency_results.jobs[static_id])
            static_id_attrib = {'static_id': static_id,
                                'mean_load_shed': '{:.4g}'.format(mean),
                                'risk': '{:.4g}'.format(mean * frequency),
                                'cost': '{:.4g}'.format(mean_cost * frequency),
                                'std_dev': '{:.4g}'.format(sqrt(variance)),
                                'N': '{:.4g}'.format(N)}
            if DOUBLE_MC_LOOP:
                special_job = contingency_results.jobs[static_id][0]
                static_id_attrib['variable_order'] = str(special_job.variable_order)
                static_id_attrib['missing_events'] = str(special_job.missing_events)

            job = contingency_results.jobs[static_id][0]
            tripped_models = job.results.get_sanitised_tripped_models()

            # Write first 3 elements to trip
            index = 0
            for tripped_model in tripped_models:
                static_id_attrib['trip_{}'.format(index)] = tripped_model
                index += 1
                if index >= 3:
                    break

            static_id_element = etree.SubElement(contingency_element, 'StaticId', static_id_attrib)

            for job in contingency_results.jobs[static_id]:
                job_attrib = {'dyn_id': str(job.dynamic_seed),
                            'simulation_time': '{:.2g}'.format(job.elapsed_time),
                            'timeout': str(job.timed_out)}
                if job.completed or job.timed_out:
                    job_attrib['load_shedding'] = '{:.2g}'.format(job.results.load_shedding)
                    job_attrib['cost'] = '{:.2g}'.format(job.results.cost)
                    if not job.voltage_stable:
                        voltage_stable = False
                    if not job.transient_stable:
                        transient_stable = False
                    if job.cct < min_CCT:
                        min_CCT = job.cct
                    if job.shc_ratio < min_shc:
                        min_shc = job.shc_ratio
                    if not job.frequency_stable:
                        frequency_stable = False
                    if job.RoCoF > max_RoCoF:
                        max_RoCoF = job.RoCoF
                    if job.power_loss_over_reserve > max_power_loss_over_reserve:
                        max_power_loss_over_reserve = job.power_loss_over_reserve

                # Write first 3 elements to trip
                tripped_models = job.results.get_sanitised_tripped_models()
                index = 0
                for tripped_model in tripped_models:
                    job_attrib['trip_{}'.format(index)] = tripped_model
                    index += 1
                    if index >= 3:
                        break
                etree.SubElement(static_id_element, 'Job', job_attrib)

            static_id_element.set('voltage_stable', str(voltage_stable))
            static_id_element.set('transient_stable', str(transient_stable))
            static_id_element.set('frequency_stable', str(frequency_stable))
            static_id_element.set('shc_ratio', '{:.4g}'.format(min_shc))
            static_id_element.set('CCT', '{:.4g}'.format(min_CCT))
            static_id_element.set('RoCoF', '{:.4g}'.format(max_RoCoF))
            static_id_element.set('dP_over_reserves', '{:.4g}'.format(max_power_loss_over_reserve))


    def is_statistical_accuracy_reached(self, contingency: Contingency) -> bool:
        indicators = self.get_statistical_indicators(contingency)

        accuracy_reached = True
        for i, indicator in enumerate(indicators):
            if indicator > 0.01 * self.total_cost:
                accuracy_reached = False
                logger.logger.info("Contingency {}: statistical indicator {} not satisfied: {} > {}".format(contingency.id, i+1, indicator, 0.01 * self.total_cost))

        if accuracy_reached:
            logger.logger.info("Contingency {}: statistical accuracy reached".format(contingency.id))

        if self.total_cost == 0:
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

        N = len(static_ids)

        mean_per_static_id = np.array([contingency_results.get_average_cost_per_static_id(static_id) for static_id in static_ids])
        mean = np.mean(mean_per_static_id)
        std_dev = sqrt(np.var(mean_per_static_id))  # TODO: add sqrt(N/(N-1)) factor and handle div by 0 in this case
        # TODO: account for hidden failures

        if N == 0:
            N += 1
            logger.logger.warn('Division by 0')

        # SE from sample variance
        indicator_1 = contingency.frequency * sqrt(std_dev**2 / N)

        # SE of risk from unobserved samples with 99% confidence
        max_consequences = MAX_CONSEQUENCES
        if contingency.order < 2 and 'DELAYED' not in contingency.id:
            max_consequences /= 10  # Be less conservative for simple N-1 contingencies to avoid wasting computation time
        p = 1 - 0.01**(1/N)
        b = max((max_consequences-mean)**2, (mean-0)**2)
        indicator_2 = contingency.frequency * sqrt(p*b/N)

        # Total SE
        indicator_3 = sqrt(indicator_1**2 + indicator_2**2)

        return indicator_1, indicator_2, indicator_3

    def get_distances_from_statistical_accuracy(self, contingency: Contingency):
        return [indicator - 0.01 * self.total_cost for indicator in self.get_statistical_indicators(contingency)]


    def get_statistical_indicator_derivatives(self, contingency: Contingency):
        """
        Evaluate the potential improvement in statistical indicators if the number of static runs (global derivatives) or
        dynamic runs (derivative_per_static_id) was increased
        """
        raise NotImplementedError('Actually implemented (and tested), but found better to simply run the minimum number of dynamic seeds')
        contingency_results = self.simulation_results[contingency.id]
        contingency_launched_jobs = self.simulations_launched[contingency.id]
        static_ids = contingency_results.static_ids

        mean_per_static_id = np.array([contingency_results.get_average_cost_per_static_id(static_id) for static_id in static_ids])
        mean = np.mean(mean_per_static_id)
        std_dev = sqrt(np.var(mean_per_static_id))  # TODO: add sqrt(N/(N-1)) factor and handle div by 0 in this case

        # Compute N and N_per_static_id from simulations "launched" not completed, this lowers priority of contingencies that have jobs currently running
        static_ids = contingency_launched_jobs.static_ids
        N = len(static_ids)
        variance_per_static_id = np.array([contingency_results.get_cost_variance_per_static_id_allow_error(static_id, value_on_error=0) for static_id in static_ids])
        N_per_static_id = [len(contingency_launched_jobs.dynamic_seeds[static_id]) for static_id in static_ids]
        N_per_static_id = np.array(N_per_static_id)

        global_derivative_1 = contingency.frequency * sqrt(std_dev**2 + np.mean(variance_per_static_id / N_per_static_id)) * (1/sqrt(N) - 1/sqrt(N+1))

        p = 1 - 0.01**(1/N)
        p2 = 1 - 0.01**(1/(N+1))
        b = max((100-mean)**2, (mean-0)**2)
        global_derivative_2 = contingency.frequency * (sqrt(p*b/N) - sqrt(p2*b/(N+1)))

        global_derivative_3 = global_derivative_1 + global_derivative_2

        return (global_derivative_1, global_derivative_2, global_derivative_3), (0, 0, 0)
        derivative_1_per_static_id = []
        derivative_2_per_static_id = []
        derivative_3_per_static_id = []
        SE = sqrt(std_dev**2 + np.mean(variance_per_static_id / N_per_static_id)) / sqrt(N)
        for i in range(len(contingency_results.static_ids)):
            if std_dev == 0:
                der_1 = 0
            else:
                N_per_static_id[i] += 1
                der_1 = contingency.frequency * (SE - (sqrt(std_dev**2 + np.mean(variance_per_static_id / N_per_static_id)) / sqrt(N)))
                N_per_static_id[i] -= 1
            der_2 = 0
            der_3 = der_1 + der_2
            derivative_1_per_static_id.append(der_1)
            derivative_2_per_static_id.append(der_2)
            derivative_3_per_static_id.append(der_3)

        return (global_derivative_1, global_derivative_2, global_derivative_3), (derivative_1_per_static_id, derivative_2_per_static_id, derivative_3_per_static_id)


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
            self.dynamic_seeds[static_id].append(job.dynamic_seed)
        else:
            self.static_ids.append(static_id)
            self.dynamic_seeds[static_id] = [job.dynamic_seed]


class ContingencyResults:
    def __init__(self):
        self.static_ids = []
        self.jobs: dict[int, list[Job]]
        self.jobs = {}
        self.sum_load_shedding = {}
        self.sum_load_shedding_squared = {}
        self.sum_cost = {}
        self.sum_cost_squared = {}
        self.elapsed_time = {}
        self.total_elapsed_time = 0

    def add_job(self, job: Job):
        static_id = job.static_id
        if static_id in self.static_ids:
            self.jobs[static_id].append(job)
            self.sum_load_shedding[static_id] += job.results.load_shedding
            self.sum_load_shedding_squared[static_id] += job.results.load_shedding ** 2
            self.sum_cost[static_id] += job.results.cost
            self.sum_cost_squared[static_id] += job.results.cost ** 2
            self.elapsed_time[static_id] += job.elapsed_time
        else:
            self.static_ids.append(static_id)
            self.jobs[static_id] = [job]
            self.sum_load_shedding[static_id] = job.results.load_shedding
            self.sum_load_shedding_squared[static_id] = job.results.load_shedding ** 2
            self.sum_cost[static_id] = job.results.cost
            self.sum_cost_squared[static_id] = job.results.cost ** 2
            self.sum_cost[static_id] = job.results.cost
            self.elapsed_time[static_id] = job.elapsed_time
        self.total_elapsed_time += job.elapsed_time

    def get_cost_variance_per_static_id_no_error(self, static_id):
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

        sum_ = self.sum_cost[static_id]
        sum_sq = self.sum_cost_squared[static_id]
        n = len(self.jobs[static_id])
        variance = (sum_sq - (sum_**2) / n) / (n - 1)
        if variance < 0 and variance > -1e-3:  # Avoids negative values caused by numerical errors
            variance = 0
        return variance

    def get_cost_variance_per_static_id_allow_error(self, static_id, value_on_error):
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
            return self.get_cost_variance_per_static_id_no_error(static_id)

    def get_average_load_shedding_per_static_id(self, static_id):
        return self.sum_load_shedding[static_id] / len(self.jobs[static_id])

    def get_average_load_shedding(self):
        average_load_shedding_per_static_id = [self.get_average_load_shedding_per_static_id(static_id) for static_id in self.static_ids]
        if len(average_load_shedding_per_static_id) > 0:
            return np.mean(average_load_shedding_per_static_id)
        else:
            return 0

    def get_maximum_load_shedding(self):
        average_load_shedding_per_static_id = [self.get_average_load_shedding_per_static_id(static_id) for static_id in self.static_ids]
        if len(average_load_shedding_per_static_id) > 0:
            return max(average_load_shedding_per_static_id)
        else:
            return 0

    def get_average_cost_per_static_id(self, static_id):
        return self.sum_cost[static_id] / len(self.jobs[static_id])

    def get_average_cost(self):
        average_cost_per_static_id = [self.get_average_cost_per_static_id(static_id) for static_id in self.static_ids]
        if len(average_cost_per_static_id) > 0:
            return np.mean(average_cost_per_static_id)
        else:
            return 0


def hash(string):
    """
    Deterministic hashing function, implementation does not really matter
    """
    return int(hashlib.sha1(bytes(string, 'utf-8')).hexdigest()[:10], 16) + 0  # Only use 10 firs bytes of the hexdigest because that's plenty enough
