#!/bin/bash
#SBATCH --time=5:00:00                 # walltime in h
#SBATCH --nodes=1                       # number of nodes
#SBATCH --ntasks-per-node=128                   # number of cpus
#SBATCH -J BN_bs_fatbs_dos                 # job name
#SBATCH --error=slurm.out               # stdout
#SBATCH --output=slurm.err              # stderr
#SBATCH --partition=romeo
##SBATCH --gres=gpu:4
#SBATCH --exclusive

module use /home/kempt/Roman_AIMS_env/modules
module load aims_env

echo "slurm job ID: $SLURM_JOB_ID"

source srun_aims > aims.out
