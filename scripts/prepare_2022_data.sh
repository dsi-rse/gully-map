#!/bin/bash

#SBATCH -p general
#SBATCH --mem=80G
#SBATCH --array=0-138
#SBATCH --output=/net/projects2/spun-hyper/oaec-found-gully/logs/prepare_2022_data-%A-%a.out

export NAME=`/home/jpivarski/miniforge3/bin/python -c 'import pathlib, os; print(sorted(pathlib.Path("/net/projects2/spun-hyper/oaec-found-gully/bare-earth-hydroflattened-2013/").glob("*.tif"))[int(os.environ["SLURM_ARRAY_TASK_ID"])].name)'`

export CORNERS=`/home/jpivarski/miniforge3/bin/gdalinfo -json -proj4 "/net/projects2/spun-hyper/oaec-found-gully/bare-earth-hydroflattened-2013/$NAME" | jq .wgs84Extent.coordinates[] | /home/jpivarski/miniforge3/bin/python -c 'import numpy as np; import sys; import json; a = np.asarray(json.load(sys.stdin)); print(a[:, 0].min() - 0.001, a[:, 1].min() - 0.001, a[:, 0].max() + 0.001, a[:, 1].max() + 0.001)'`

/home/jpivarski/miniforge3/bin/gdalwarp -te_srs EPSG:4326 -te $CORNERS /net/projects2/spun-hyper/oaec-found-gully/Sonoma_DTM_2022/SONOMA_DTM_2020.tif "/net/projects2/spun-hyper/oaec-found-gully/bare-earth-hydroflattened-2022/$NAME"
