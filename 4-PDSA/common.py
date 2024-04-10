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

# DYNAWO_PATH = '/home/fsabot/Desktop/dynawo_new/myEnvDynawo.sh'
DYNAWO_PATH = '/home/ulb/beams_energy/fsabot/dynawo/dynawo.sh'
DYNAWO_NAMESPACE = 'http://www.rte-france.com/dynawo'

RANDOMISE_DYN_DATA = True
NETWORK_NAME = 'RTS'
CASE = 'year'

REUSE_RESULTS = True  # If true, don't rerun cases already simulated, note that setting this to False does not delete old versions of saved_results.pickle and saved_results_bak.pickle
REUSE_RESULTS_FAST_FORWARD = True
BYPASS_SCREENING = True

MIN_NUMBER_STATIC_SEED = 5
MIN_NUMBER_STATIC_SEED_CRITICAL_CONTINGENCY = 1000
MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED = 5
NB_RUNS_PER_INDICATOR_EVALUATION = 1000  # Note: slightly less runs migth be done per indicator evaluation due to capping
DOUBLE_MC_LOOP = True

BASEMVA = 100
BASEFREQUENCY = 60

# Contingency parameters
T_INIT = 5
T_CLEARING = T_INIT + 0.1
T_BACKUP = T_INIT + 0.2
T_END = 20
R_FAULT = 0.001
X_FAULT = 0.001

OUTAGE_RATE_PER_KM = 0.27 / 100
DELAYED_CLEARING_RATE = 0.1
CB_FAILURE_RATE = 0.01

CSV_SEPARATOR = ','
