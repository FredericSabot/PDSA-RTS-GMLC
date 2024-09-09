#!/bin/bash
# Submission script for Lemaitre3
#SBATCH --job-name=PSCACOPF
#SBATCH --array=0-999
#SBATCH --time=00:10:00 # hh:mm:ss
#
#SBATCH --ntasks=1
#SBATCH --mem-per-cpu=1000 # megabytes
#SBATCH --partition=batch,debug
#
#SBATCH --mail-user=frederic.sabot@ulb.be
#SBATCH --mail-type=END

module purge
module load Python/3.9
module load SciPy-bundle

cd PDSA-RTS-GMLC/2-SCOPF

# Used to have IDs larger than the max job array size (default 1001, but 8735 hours in a year)
ID=`expr $SLURM_ARRAY_TASK_ID + 1000`

case="year"
network="Texas"
echo 'Running case' $case $ID
time -p python PSCACOPF.py $ID $case $network

# Delete temporary files
rm -r a-PSCDCOPF/$ID/
rm -r b-ACOPF/$ID/
rm -r c-PSADCOPF/$ID/ &> /dev/null  # Folder does not necessarily exist
