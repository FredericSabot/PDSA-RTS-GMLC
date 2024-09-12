#!/bin/bash
# Submission script for Nic5
#SBATCH --job-name=PSCACOPF
#SBATCH --array=0-176
#SBATCH --time=47:00:00 # hh:mm:ss
#
#SBATCH --ntasks=1
#SBATCH --mem-per-cpu=16000 # megabytes
#SBATCH --partition=batch
#
#SBATCH --mail-user=frederic.sabot@ulb.be
#SBATCH --mail-type=END

module purge
module load Python/3.9
module load SciPy-bundle

cd PDSA-RTS-GMLC/2-SCOPF

case="year"
network="Texas"

for i in {0..49}
do
# Used to have IDs larger than the max job array size (default 1001, but 8735 hours in a year)
ID=$(echo $SLURM_ARRAY_TASK_ID*50+$i | bc)
echo 'Running case' $case $ID $network
time -p python PSCACOPF.py $ID $case $network $LOCALSCRATCH

# Delete temporary files
rm -r a-PSCDCOPF/$ID/ &> /dev/null
rm -r b-ACOPF/$ID/ &> /dev/null
rm -r c-PSADCOPF/$ID/ &> /dev/null  #  &> /dev/null because folder does not necessarily exist

rm -r $LOCALSCRATCH/a-PSCDCOPF/$ID/ &> /dev/null
rm -r $LOCALSCRATCH/b-ACOPF/$ID/ &> /dev/null
rm -r $LOCALSCRATCH/c-PSADCOPF/$ID/ &> /dev/null

done
