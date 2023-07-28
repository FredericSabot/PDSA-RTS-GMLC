from common import *
from mpi4py import MPI

import os
import subprocess
import dynawo_inputs
from job import Job
from dynawo_outputs import get_job_results
import time

class Slave:
    def __init__(self):
        self.comm = MPI.COMM_WORLD
        self.rank = MPI.COMM_WORLD.Get_rank()
        self.run()

    def run(self):
        status = MPI.Status()

        while True:
            self.comm.send(None, dest=0, tag=MPI_TAGS.READY.value)
            job = self.comm.recv(source=0, tag=MPI.ANY_TAG, status=status)
            tag = status.Get_tag()

            if tag == MPI_TAGS.START.value:
                logging.debug('\tSlave {}: received input job {}'.format(self.rank, job))
                result = self.do_work(job)
                logging.debug('\tSlave {} completed job {}'.format(self.rank, job))
                self.comm.isend(result, dest=0, tag=MPI_TAGS.DONE.value)  # Non-blocking as the master might no longer be listening
            elif tag == MPI_TAGS.EXIT.value:
                break

        self.comm.send(None, dest=0, tag=MPI_TAGS.EXIT.value)

    def do_work(self, job):
        self.call_dynawo(job)
        return job

    def call_dynawo(self, job : Job):
        t0 = time.time()

        working_dir = dynawo_inputs.write_job_files(job)

        log_file = os.path.join(working_dir, 'outputs', 'logs', 'dynawo.log')
        timeline_file = os.path.join(working_dir, 'outputs', 'timeLine', 'timeline.log')  # TODO: read paths from .jobs instead of hardcoding them
        if REUSE_RESULTS and os.path.exists(log_file) and os.path.exists(timeline_file):
            pass
        else:
            cmd = [DYNAWO_PATH, 'jobs', os.path.join(working_dir, NETWORK_NAME + '.jobs')]
            logging.debug('Launching job %s' % job)
            proc = subprocess.Popen(cmd)

            try:
                proc.communicate(timeout=JOB_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                job.timeout()
                return

        delta_t = time.time() - t0
        # TODO: can save the job results instead of the simulation ones (probably easy with pickle, less flexible so can save both)
        job.complete(delta_t, get_job_results(working_dir))
