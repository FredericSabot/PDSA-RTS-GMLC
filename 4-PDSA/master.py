from __future__ import annotations
from mpi4py import MPI
from common import *
from contingencies import Contingency
from job_queue import JobQueue

import os
import logger
# from pympler import asizeof

class Master:
    def __init__(self, slaves: list[int]):
        if len(slaves) == 0:
            raise ValueError('Need at least one slave')

        self.comm = MPI.COMM_WORLD
        self.slaves = set(slaves)
        self.slaves_state = {slave: 'Waiting' for slave in self.slaves}
        self.contingency_list = Master.create_contingency_list()
        self.job_queue = JobQueue(self.contingency_list)
        self.run()

    @staticmethod
    def create_contingency_list():
        base_contingency = Contingency.create_base_contingency()
        if WITH_HIDDEN_FAILURES or not NEGLECT_NORMAL_FAULT_RISK:
            N_1_contingencies = Contingency.create_N_1_contingencies(with_normal_clearing=True)
        else:
            N_1_contingencies = Contingency.create_N_1_contingencies(with_normal_clearing=False)
        N_2_contingencies = Contingency.create_N_2_contingencies()

        contingency_list = base_contingency + N_1_contingencies + N_2_contingencies
        logger.logger.info('Considering {} contingencies: {} base, {} N-1, {} N-2'.format(len(contingency_list), len(base_contingency), len(N_1_contingencies), len(N_2_contingencies)))
        return contingency_list

    def run(self):
        init = True
        jobs_to_run, _ = self.job_queue.get_next_jobs(init=True)
        logger.logger.info(f"Launching first {len(jobs_to_run)} simulations for initialisation")
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
                    logger.logger.info(f"Launching batch {n_iter} of simulations (with {len(jobs_to_run)} jobs)")

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

                if os.name == 'nt':
                    if os.path.exists("stop.txt"):  # MS MPI does not pass signals to processes (https://stackoverflow.com/a/39399235)
                        print("Interrupted", flush=True)
                        # So, as cringe as it may seem, to gracefully interrupt the simulation, we must create a "stop.txt" file
                        os.remove("stop.txt")
                        raise KeyboardInterrupt

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
            logger.logger.warning("Simulation interrupted by user")
            self.job_queue.write_saved_results()
            self.job_queue.write_analysis_output()
            # self.show_memory_usage()
            if os.name == 'nt':  # With MS MPI, only the master gets interrupted, so abort to stop the other processes
                MPI.COMM_WORLD.Abort(1)

    """ def show_memory_usage(self):
        print('1  Job queue', asizeof.asizeof(self.job_queue) / 1e6)
        print('2  Job queue', asizeof.asizeof(self.job_queue.contingencies) / 1e6)
        print('3  Job queue', asizeof.asizeof(self.job_queue.contingencies_skipped) / 1e6)
        print('4  Job queue', asizeof.asizeof(self.job_queue.static_samples) / 1e6)
        print('5  Job queue', asizeof.asizeof(self.job_queue.static_samples_per_contingency) / 1e6)
        print('6  Job queue', asizeof.asizeof(self.job_queue.simulation_results) / 1e6)
        print('7  Job queue', asizeof.asizeof(self.job_queue.simulations_launched) / 1e6)
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


    def send_work_to_slave(self, job, status: MPI.Status):
        if REUSE_RESULTS:
            saved_job = self.job_queue.get_saved_job(job)
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
