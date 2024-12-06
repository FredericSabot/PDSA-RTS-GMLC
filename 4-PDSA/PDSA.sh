#!/bin/bash
# Submission script for Nic5
#SBATCH --job-name=DPSA
#SBATCH --time=08:00:00 # hh:mm:ss
#SBATCH --time-min=04:00:00 # hh:mm:ss
#
#SBATCH --ntasks=320
#SBATCH --mem-per-cpu=8000 # megabytes
#SBATCH --partition=batch
#
#SBATCH --signal=USR1@600  #Send USR1 signal 10min (+/- 1min) before job end
#
#SBATCH --mail-user=frederic.sabot@ulb.be
#SBATCH --mail-type=END,FAIL

date
cd $SLURM_SUBMIT_DIR

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

echo Creating tar
tar --exclude-vcs --exclude 4-PDSA/simulations -cf PDSA-RTS-GMLC.tar PDSA-RTS-GMLC
echo Copying tar to LOCALSCRATCH
srun -n $SLURM_JOB_NUM_NODES --ntasks-per-node=1 cp "$SLURM_SUBMIT_DIR/PDSA-RTS-GMLC.tar" "$LOCALSCRATCH/PDSA-RTS-GMLC.tar"
rm "$SLURM_SUBMIT_DIR/PDSA-RTS-GMLC.tar"

echo Extracting archive
cd "$LOCALSCRATCH"
srun -n $SLURM_JOB_NUM_NODES --ntasks-per-node=1 tar -xf PDSA-RTS-GMLC.tar
srun -n $SLURM_JOB_NUM_NODES --ntasks-per-node=1 rm "$LOCALSCRATCH/PDSA-RTS-GMLC.tar"
cd "$LOCALSCRATCH/PDSA-RTS-GMLC/4-PDSA"

echo Launching process
mpiexec --verbose -mca orte_abort_on_non_zero_status 1 -n $SLURM_NTASKS python -m mpi4py main.py

echo Saving output files  # Note: the script (and thus cp) is only executed on the first allocated node (so cp *.log would only give part of the logs)
cp "$LOCALSCRATCH/PDSA-RTS-GMLC/4-PDSA/log0.log" "$SLURM_SUBMIT_DIR/PDSA-RTS-GMLC/4-PDSA/"
cp "$LOCALSCRATCH/PDSA-RTS-GMLC/4-PDSA/saved_results.pickle" "$SLURM_SUBMIT_DIR/PDSA-RTS-GMLC/4-PDSA/"  # Does not work well with wildcards
cp "$LOCALSCRATCH/PDSA-RTS-GMLC/4-PDSA/saved_results_bak.pickle" "$SLURM_SUBMIT_DIR/PDSA-RTS-GMLC/4-PDSA/"
cp "$LOCALSCRATCH/PDSA-RTS-GMLC/4-PDSA/AnalysisOutput.xml"    "$SLURM_SUBMIT_DIR/PDSA-RTS-GMLC/4-PDSA/"
cp "$LOCALSCRATCH/PDSA-RTS-GMLC/4-PDSA/AnalysisOutput_critical.xml"    "$SLURM_SUBMIT_DIR/PDSA-RTS-GMLC/4-PDSA/"

echo Deleting temp files
rm -rf "$LOCALSCRATCH"
