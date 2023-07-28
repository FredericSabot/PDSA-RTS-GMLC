from common import *
from mpi4py import MPI
from master import Master
from slave import Slave

def main():
    rank = MPI.COMM_WORLD.Get_rank()
    size = MPI.COMM_WORLD.Get_size()

    if rank == 0:
        Master(slaves=range(1, size))
    else:
        Slave()

    logging.debug('Task completed (rank %d)' % (rank))

if __name__ == "__main__":
    main()
