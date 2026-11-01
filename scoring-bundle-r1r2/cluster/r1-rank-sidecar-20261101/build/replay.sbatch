#!/bin/bash -p
#SBATCH -p cpu
#SBATCH -c 1
#SBATCH --mem=96G
#SBATCH -t 0-04:00:00
#SBATCH --job-name=r1-rank-sidecar
#SBATCH -o <FORECAST_ROOT>/r1-rank-sidecar-20261101/work/logs/%x_%A_%a.log
# Full build:  sbatch --export=NIL --array=0-63 replay.sbatch
#              one array element per R1 scoring lane, the lane's cells in the original order.
# Dry run:     sbatch --export=NIL --array=0-<n-1> replay.sbatch CELLS_FILE
#              element i replays the cell on line i+1 of CELLS_FILE.
set -euo pipefail
export PATH=/usr/bin:/bin
for name in ${!PYTHON@} ${!BGBENCH@}; do unset "$name"; done
unset POLARS_ENGINE_AFFINITY POLARS_FORCE_STREAMING POLARS_AUTO_STREAMING POLARS_PARQUET_DECODE_TARGET_VALUES_PER_THREAD
export CUDA_VISIBLE_DEVICES=''
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 POLARS_MAX_THREADS=1
cd /tmp
PY=<RESULTS_ROOT>/work/<PROJECT>/venv/bin/python
SCRIPT=<FORECAST_ROOT>/r1-rank-sidecar-20261101/build/build_sidecar.py
if [ "$#" -ge 1 ]; then
  mapfile -t list < "$1"
  exec /usr/bin/time -v "$PY" -I -B "$SCRIPT" replay --cells "${list[$SLURM_ARRAY_TASK_ID]}"
else
  exec /usr/bin/time -v "$PY" -I -B "$SCRIPT" replay --lane "$SLURM_ARRAY_TASK_ID"
fi
