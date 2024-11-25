#!/bin/bash
# Submission script for Nic5
#SBATCH --job-name=DPSA
#SBATCH --time=04:00:00 # hh:mm:ss
#SBATCH --time-min=01:00:00 # hh:mm:ss
#
#SBATCH --ntasks=100
#SBATCH --mem-per-cpu=6000 # megabytes
#SBATCH --partition=batch
#
#SBATCH --signal=USR1@60  #Send USR1 signal 60s before job end
#
#SBATCH --mail-user=frederic.sabot@ulb.be
#SBATCH --mail-type=END,FAIL

if false
then
    # Modules on lemaitre3
    module load releases/2022a
    module load Python/3.9
    module load SciPy-bundle  # Contains mpi4py, and IntelMPI
else
    # Modules on nic5
    module load releases/2022b
    module load Python/3.10
    module load OpenMPI
    module load SciPy-bundle  # For Scipy itself
fi


# cp -r PDSA-RTS-GMLC $GLOBALSCRATCH
# cd $GLOBALSCRATCH/PDSA-RTS-GMLC/4-PDSA
# cd PDSA-RTS-GMLC/4-PDSA

# timeout 3550
# mpiexec -n $SLURM_NTASKS -env I_MPI_JOB_SIGNAL_PROPAGATION=enable python main.py  # Intel MPI flags to propagate signals to subprocesses
mpiexec --verbose -mca orte_abort_on_non_zero_status 1 -n $SLURM_NTASKS python -m mpi4py main.py
# cp AnalysisOutput.xml $HOME/ # $SLURM_JOB_ID
