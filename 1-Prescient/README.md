In this step, time-series realisation of wind/solar/hydro availability and load (from RTS-Data/timeseries_data_files) are injected in the [Prescient](https://github.com/grid-parity-exchange/Prescient) market/unit commitment model to generate credible dispatches of the RTS. The generated dispatches are written as csv in year_week_output_N_1/ and are used in the next step.

Note that only 1 year of time-series is available in the original RTS-GMLC data, so we only use 1 "Monte Carlo year" in the analysis.


# Requirements

Install Prescient
```
python -m pip install gridx-prescient
```

Optional: a pyomo-compatible MILP solver, e.g. Gurobi (note that a licence is required (free for academics))
```
python -m pip install gurobipy
```


# Usage

## Data preparation

The following scripts have to be run at least once and should be rerun if the input data in /RTS-Data is modified.

```
cd RTS-Data
python source_to_iidm.py
cd timeseries_data_files/Load
python extrapolate.py
cd ../WIND
python extrapolate.py
```

## Prescient

```
cd 1-Prescient
python populate_prescient_inputs.py
python simulate_with_network_deterministic.py year
python prescient_outputs_to_csv.py year
```

year can be replaced by january or july if the analysis is to be performed for these months only.