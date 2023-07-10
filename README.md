
# PDSA-RTS-GMLC

This repo contains a collection of scripts to prepare a probabilistic dynamic security assessment (PDSA) of the Reliability Test Sytem - Grid Modernization Lab Consortium version (RTS-GMLC).

It consists in:

1. A market model/unit commitment model based on [Prescient](https://github.com/grid-parity-exchange/Prescient). Prescient iterates between day-ahead and hourly dispatch. A (DC) nodal market (considering N-1 limits) is used here.
2. A preventive security constained AC optimal power flow (PSCACOPF) to refine individual hourly dispatches
3. Work in progress (dynamic data, scripts for the DPSA itself?)

# Usage

## Data preparation

The following scripts should be rerun if the input data in /RTS-Data is modified

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
python simulate_with_network_deterministic.py january
python prescient_outputs_to_csv.py january
```

## OPF

```
cd ../2-SCOPF
./run.sh
```
Note that a SLURM-based runner (run_cluster.sh) is also available for use in high-performing computing


# Requirements

## Prescient

Prescient
```
python -m pip install gridx-prescient
```

Optional: a pyomo-compatible MILP solver, e.g. Gurobi (note that a licence is required (free for academics))
```
python -m pip install gurobipy
```

## OPF

Pypowsybl
```
python -m pip install pypowsybl
```

[GAMS](https://www.gams.com/download/) and GAMS Python bindings. Note that depending on the GAMS version, different installation procedures are sugggested for the python bindings, e.g. [link](https://www.gams.com/36/docs/API_PY_TUTORIAL.html) or [link](https://www.gams.com/43/docs/API_PY_GETTING_STARTED.html).

Tested with Python 3.9 and GAMS 36. Note that older versions of GAMS might not support recent versions of Python and that Pypowsybl requires Python >= 3.7
