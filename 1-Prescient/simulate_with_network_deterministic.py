from prescient.simulator import Prescient
import sys

case = sys.argv[1]
network_name = sys.argv[2]
output_dir = f'{case}_{network_name}_week_output_N_1'

if case == 'january':
    start = "01-01-2020"
    num_days = 30
elif case == 'july':
    start = "07-01-2020"  # US date system
    num_days = 30
elif case == 'year':
    start = "01-01-2020"
    num_days = 364
else:
    raise NotImplementedError()

Prescient().simulate(
    data_path = f"data-{network_name}",
    input_format = "rts-gmlc",
    simulate_out_of_sample = True, # This option directs the simulator to use different forecasts from actuals.
    run_sced_with_persistent_forecast_errors = True,    # This option directs the simulator to use forecasts
                                                        # (adjusted by the current forecast error) for SCED
                                                        # look-ahead periods, instead of using the actuals
                                                        # for SCED look-ahead periods.
    output_directory = output_dir, # Where to write the output data
    start_date = start, # Date to start the simulation on, must be within the range of the data.
    num_days = num_days, # Number of days to simulate, including the start date. All days must be in the data.
    sced_horizon = 4, # Number of look-ahead periods (in sced_frequency_minutes) in the real-time SCED
    ruc_mipgap = 0.01, # mipgap for the day-ahead unit commitment
    symbolic_solver_labels = True, # Whether to use symbol names derived from the model when interfacing with the solver.
    reserve_factor = 0.0, # Additional reserve factor *not* included in the data, fraction of load at every time step
    deterministic_ruc_solver = "gurobi", # MILP solver to use for unit commitment
    sced_solver = "gurobi", # (MI)LP solver to use for the SCED
    output_solver_logs = False, # If True, outputs the logs from the unit commitment and SCED solves
    ruc_horizon = 36, # Number of hours in unit commitment. Typically needs to be at least 24 (default = 48).
    monitor_all_contingencies = True,
)

# print outs only
# --output-sced-initial-conditions
# --output-sced-loads
# --output-ruc-initial-conditions
# --output-ruc-solutions
# --output-solver-logs
