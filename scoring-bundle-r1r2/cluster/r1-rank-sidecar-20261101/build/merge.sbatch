#!/bin/bash -p
#SBATCH -p cpu
#SBATCH -c 4
#SBATCH --mem=96G
#SBATCH -t 0-02:00:00
#SBATCH --job-name=r1-rank-sidecar-merge
#SBATCH -o <FORECAST_ROOT>/r1-rank-sidecar-20261101/work/logs/%x_%j.log
# sbatch --export=NIL merge.sbatch   (after every cell has a done record)
set -euo pipefail
export PATH=/usr/bin:/bin
for name in ${!PYTHON@} ${!BGBENCH@}; do unset "$name"; done
export POLARS_MAX_THREADS=4 OMP_NUM_THREADS=1
cd /tmp
exec /usr/bin/time -v <RESULTS_ROOT>/work/<PROJECT>/venv/bin/python -I -B \
  <FORECAST_ROOT>/r1-rank-sidecar-20261101/build/build_sidecar.py merge
