from common import *
from mpi4py import MPI
from master import Master
from slave import Slave
import logger
import signal
import sys

def mpiabort_excepthook(type, value, traceback):
    """
    Hook to abord all processes if one raises an unhandled error, from https://stackoverflow.com/a/50198848
    """
    sys.__excepthook__(type, value, traceback)
    MPI.COMM_WORLD.Abort()

def main():
    rank = MPI.COMM_WORLD.Get_rank()
    size = MPI.COMM_WORLD.Get_size()

    # Catches SIGTERM, SIGINT, SIGUSR1, and SIGUSR2 and gracefully terminate when received
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGUSR1, terminate)
    signal.signal(signal.SIGUSR2, terminate)

    if rank == 0:
        Master(slaves=range(1, size))
    else:
        Slave()

    logger.logger.debug('Task completed (rank %d)' % (rank))

def terminate(self, *args):
    raise KeyboardInterrupt

if __name__ == "__main__":
    sys.excepthook = mpiabort_excepthook
    main()
    sys.excepthook = sys.__excepthook__
