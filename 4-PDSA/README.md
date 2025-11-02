In this step, the security assessment is actually performed. The code is written in a master-slave architecture, i.e. one thread (the master) collects all the information and decides what are the next simulations to perform (in Master.JobQueue.get_next_jobs()), and all the others (the slaves) perform those simulations. The results of the PDSA are written to AnalysisOutput.xml. These results can be visualised using software that shows XML files in grid view, such as Ximple ([http://www.ximple.cz/](http://www.ximple.cz/), Windows only).

All the main parameters of the analysis are defined in common.py

# Requirements

```
python -m pip install pypowsybl lxml logger mpi4py natsort scipy
```

Install [dynawo](https://dynawo.github.io/) and set DYNAWO_PATH in 4-PDSA/common.py accordingly. Currently, the dynamic models used are only available on my fork of Dynawo on the branch [30_RTQ2024](https://github.com/FredericSabot/dynawo/tree/30_RTS2024). You can compile it from source, or I can make release on demand.


# Usage

```
cd ../4-PDSA
mpiexec -n 2 main.py
```

to run locally. However, HPC is almost mandatory for PDSA (except if a limited number of contingencies/operating conditions is considered), so use the following command instead

```
sbatch PDSA.sh
```

Note: in the current implementation, all the results which are output in AnalysisOutput.xml are always loaded in RAM by the master process (in master.job_queue.simulation_results and master.job_queue.simulations_launched). To scale to larger grids, it would be needed for the master to only remember the information needed to schedule new jobs (i.e. load shedding/cost + protection sensitivity for each job). All the remaining information (output in AnalysisOutput.xml) should be stored in a database/on disk instead. Optimisation of some computations in Master.JobQueue.get_next_jobs() might also be useful. (For the RTS system, the master needs up to 4Go of RAM in the current implementation, while the slaves need only 1.)
