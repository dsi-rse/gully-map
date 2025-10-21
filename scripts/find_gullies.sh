#!/bin/bash

#SBATCH -p general
#SBATCH --gres=gpu:1
#SBATCH --mem=100G
#SBATCH --cpus-per-task=1
#SBATCH --array=0-138
#SBATCH --output=/net/projects2/spun-hyper/oaec-found-gully/logs/find_gullies-%A-%a.out

export PYTHON=/home/jpivarski/miniforge3/bin/python
export SCRIPTS=/home/jpivarski/dsi/oaec-found-gully/scripts
export DIRECTORY=/net/projects2/spun-hyper/oaec-found-gully/

$PYTHON $SCRIPTS/find_gullies.py $DIRECTORY
