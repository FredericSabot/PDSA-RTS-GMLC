from common import *
from mpi4py import MPI
from master import Master
from slave import Slave
import logger
import signal

def main():
    rank = MPI.COMM_WORLD.Get_rank()
    size = MPI.COMM_WORLD.Get_size()

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
    main()
