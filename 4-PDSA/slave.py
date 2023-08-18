from common import *
from mpi4py import MPI
from job import Job
import logger

class Slave:
    def __init__(self):
        self.comm = MPI.COMM_WORLD
        self.rank = MPI.COMM_WORLD.Get_rank()
        self.run()

    def run(self):
        status = MPI.Status()

        try:
            while True:
                self.comm.send(None, dest=0, tag=MPI_TAGS.READY.value)
                job = self.comm.recv(source=0, tag=MPI.ANY_TAG, status=status)
                tag = status.Get_tag()

                if tag == MPI_TAGS.START.value:
                    logger.logger.log(logger.logging.TRACE, 'Slave {}: received input job {}'.format(self.rank, job))
                    result = self.do_work(job)
                    logger.logger.debug('Slave {} completed job {}'.format(self.rank, job))
                    self.comm.isend(result, dest=0, tag=MPI_TAGS.DONE.value)  # Non-blocking as the master might no longer be listening
                elif tag == MPI_TAGS.EXIT.value:
                    break

            self.comm.send(None, dest=0, tag=MPI_TAGS.EXIT.value)

        except KeyboardInterrupt:
            self.comm.isend(None, dest=0, tag=MPI_TAGS.READY.value)  # Non-blocking as the master might no longer be listening


    def do_work(self, job: Job):
        job.run()
        return job
