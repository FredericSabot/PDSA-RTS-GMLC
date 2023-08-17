import logging
from mpi4py import MPI

# Add an additional log level
logging.TRACE = logging.DEBUG - 5
logger = logging.getLogger()

logger.setLevel(logging.DEBUG)  # CRITICAL, ERROR, WARNING, INFO, DEBUG, TRACE, NOTSET

formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
# Remove default handler
logger.handlers = []
# Send all log messages to a file
rank = MPI.COMM_WORLD.Get_rank()
file_handler = logging.FileHandler('log{}.log'.format(rank), mode='w')
file_handler.setLevel(logging.TRACE)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
# Send important log messages to stdout
stderr_handler = logging.StreamHandler()
stderr_handler.setLevel(logging.WARNING)
stderr_handler.setFormatter(formatter)
logger.addHandler(stderr_handler)