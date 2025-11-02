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
    LINE_RECLOSE = 4

# DYNAWO_PATH = '/home/fsabot/Desktop/dynawo_new/myEnvDynawo.sh'
DYNAWO_PATH = '/home/ulb/beams_energy/fsabot/dynawo/dynawo.sh'
DYNAWO_NAMESPACE = 'http://www.rte-france.com/dynawo'
WITH_LXML = False  # Use lxml instead of the default python xml handler, better looking prints but leaks memory

RANDOMISE_DYN_DATA = True  # Whether or not to account for protection-related uncertainty
NETWORK_NAME = 'RTS'
CASE = 'year'
if NETWORK_NAME == 'RTS':
    CONTINGENCY_MINIMUM_VOLTAGE_LEVEL = 220e3  # Lines with a base voltage lower than 220kV are not considered in the security assessment
    DISTANCE_PROTECTION_MINIMUM_VOLTAGE_LEVEL = 0
    JOB_TIMEOUT_S = 300  # Timeout for a single job in seconds
elif NETWORK_NAME == 'Texas':
    CONTINGENCY_MINIMUM_VOLTAGE_LEVEL = 340e3
    DISTANCE_PROTECTION_MINIMUM_VOLTAGE_LEVEL = 340e3  # To computationally expensive to model distance protection everywhere (model could be improved)
    JOB_TIMEOUT_S = 1800  # Timeout for a single job in seconds
else:
    raise NotImplementedError

REUSE_RESULTS = True  # If true, don't rerun cases already simulated, note that setting this to False does not delete old versions of saved_results.pickle and saved_results_bak.pickle
REUSE_RESULTS_FAST_FORWARD = True  # If True, load all results from saved_results.pickle even if not relevant
WITH_SCREENING = False
BYPASS_SCREENING = True  # If True, simulate scenarios which are deemed secure by the screening process (necessary to estimate false negative rate)

MIN_NUMBER_STATIC_SEED = 5  # Minimum number of random operating conditions considered per contingency
MIN_NUMBER_STATIC_SEED_CRITICAL_CONTINGENCY = 1000  # Minimum for worst 10 critical contingencies (useful for ML-based security enhancement)
MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED = 5  # Number of protection samples per scenario that is sensitive to protection-related uncertainty
NB_RUNS_PER_INDICATOR_EVALUATION = 5000  # Number of simulations performed between each update of statistical indicators (e.g. total risk) by the master, note: slightly less runs migth be done per indicator evaluation due to capping
DOUBLE_MC_LOOP = True  # Whether to use an indicator to predict the scenarios that are sensitive the protection-related uncertainties
# and run multiple (MIN_NUMBER_DYNAMIC_RUNS_PER_STATIC_SEED) MC simulations for them. Otherwise, a single sample of protection parameters
# is taken per sample of operating conditions

if NETWORK_NAME == 'RTS':
    MAX_CONSEQUENCES = 500  # Average consequences of a full blackout, i.e. result of load_shedding_to_cost(100, average_load), with average load = 4348 MW
elif NETWORK_NAME == 'Texas':
    MAX_CONSEQUENCES = 5000
else:
    raise NotImplementedError

if not RANDOMISE_DYN_DATA:
    DOUBLE_MC_LOOP = False

# System parameters
BASEMVA = 100
BASEFREQUENCY = 60

# Contingency parameters
T_INIT = 5  # Fault time
T_CLEARING = T_INIT + 0.1
T_BACKUP = T_INIT + 0.2
T_RECLOSE = T_INIT + 0.2
T_END = 20  # End of simulation time
R_FAULT = 0.001  # In pu
X_FAULT = 0.001

OUTAGE_RATE_PER_KM = 2.5 / 100  # French 400kV statistics from Calmet, B, "Protection des réseaux de transport et de répartition : présentation - D4800"
DELAYED_CLEARING_RATE = 0.1  # On-demand probability of delayed-clearing
CB_FAILURE_RATE = 0.01  # Based on (9 + 6 + 2) CB failures to open in 10 years with around 300 faults per year (17/3000 = 0.0056 rounded to 0.01) according to Table 5.1 of Haarla et. al. "Transmission Grid Security: A PSA approach"

CSV_SEPARATOR = ','

WITH_HIDDEN_FAILURES = True
HIDDEN_FAILURE_PROBA = 0.1
MAX_HIDDEN_FAILURE_ORDER = 2  # Maximum order of contingencies caused by hidden failure (e.g. if set to 3, an N-1 contingency can lead to up to 2 consecutive hidden failures, and an N-2 contingency, to 1 hidden failure (2+1=3))
MAX_POSSIBLE_PROTECTION_HIDDEN_FAILURES = 100  # Maximum number of different possible protection hidden failures to simulate for a given scenario (if more possibilities are found, they will be skipped and a warning printed)
GENERATOR_HIDDEN_FAILURE_MINIMUM_OUTPUT_MVA = 30  # The hidden failure of generators with a smaller output (absolute value in MVA) will not be considered as it has a low impact on the network
if NETWORK_NAME == 'Texas':
    GENERATOR_HIDDEN_FAILURE_MINIMUM_OUTPUT_MVA = 200
NEGLECT_NORMAL_FAULT_RISK = True  # Neglect consequences of N-1 contingencies with fault cleared in normal time (still simulated to generate hidden failures). Because of the way operating conditions are generated, the system is not always dispatched in an N-1 secure way while this could be avoided in practice in real-time operations
