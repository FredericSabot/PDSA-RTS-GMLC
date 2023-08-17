from enum import Enum

class MPI_TAGS(Enum):
    READY = 1
    START = 2
    DONE = 3
    EXIT = 4

class INIT_EVENT_CATEGORIES(Enum):
    BUS_FAULT = 1
    LINE_DISC = 2
    GEN_DISC = 3

JOB_TIMEOUT_S = 300  # Timeout for a single job in seconds

DYNAWO_PATH = '/home/fsabot/Desktop/dynawo_new/myEnvDynawo.sh'
DYNAWO_NAMESPACE = 'http://www.rte-france.com/dynawo'

RANDOMISE_DYN_DATA = False
NETWORK_NAME = 'RTS'
CASE = 'january'

REUSE_RESULTS = True  # If true, don't run simulations if there is already an 'outputs' directory in the working dir of a given job
# TODO: read outputdir from .jobs instead of assuming it is 'outputs'
# TODO: delete previous simulations outputs if REUSE_RESULTS = False (with confirmation prompt, only for case CASE)

MIN_NUMBER_RUN_N_1 = 50
MIN_NUMBER_RUN_N_2 = 10
NB_RUNS_PER_INDICATOR_EVALUATION = 10

# Contingency parameters
T_INIT = 5
T_CLEARING = T_INIT + 0.1
T_BACKUP = T_INIT + 0.2
R_FAULT = 0.0001
X_FAULT = 0.0001

OUTAGE_RATE_PER_KM = 0.27 / 100
CB_FAILURE_RATE = 0.01

CSV_SEPARATOR = ','