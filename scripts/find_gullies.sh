#!/bin/bash

#SBATCH -p general
#SBATCH --gres=gpu:1
#SBATCH --array=0-138
#SBATCH --output=/net/projects2/spun-hyper/oaec-found-gullies/logs/find_gullies-%A-%a.out

/home/jpivarski/miniforge3/bin/python /home/jpivarski/dsi/oaec-found-gully/scripts/find_gullies.py
