#!/bin/bash
# Submission script for Lemaitre3
#SBATCH --job-name=PSCACOPF
#SBATCH --array=0-4
#SBATCH --time=00:30:00 # hh:mm:ss
#
#SBATCH --ntasks=1
#SBATCH --mem-per-cpu=1000 # megabytes
#SBATCH --partition=batch,debug
#
#SBATCH --mail-user=frederic.sabot@ulb.be
#SBATCH --mail-type=END

module purge
module load Python/3.9

cd PDSA-RTS-GMLC/2-SCOPF

case="january"
echo 'Running case' $case $SLURM_ARRAY_TASK_ID
time -p python PSCACOPF.py $SLURM_ARRAY_TASK_ID $case
