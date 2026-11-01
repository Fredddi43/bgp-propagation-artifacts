#!/bin/bash
# D-A39 offline, label-free check: float32 vs float64 reproduction of every committed decision of the 281 non-baseline,
# non-origin sealed arms (r2_float32_scoring.py main). Reads sealed predictions + manifests only; writes $1 (must not exist).
#   sbatch --export=NIL r2_float32_offline.sbatch /abs/path/float32-offline-check.json
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=32
#SBATCH --mem=256000M
#SBATCH --time=04:00:00
#SBATCH --no-requeue
#SBATCH --job-name=r2-d-a39-f32
#SBATCH --output=<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-logs/%x-%j.out
#SBATCH --error=<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-logs/%x-%j.err
set -eu
F=<FORECAST_ROOT>
R=$F/newperiod-g2-inference-v1-20261027
CHAIN=<RESULTS_ROOT>/nobackup/g2-chain-20261029T001120Z/repo/.agents/operations/agy-lanes-20261027/g2r2/chain
cd /tmp
exec env -i PATH=/usr/bin:/bin LANG=C.UTF-8 OMP_NUM_THREADS=1 \
  $F/newperiod-gate-private-v1/venv/bin/python -I -B "$CHAIN/r2_float32_scoring.py" \
  --freeze $R/amend/amended-freeze.json --freeze-sha256 921fc9bb06888e39b2399735cd2bc673506116375b5be84ce16dfee59b33beaa \
  --seal $R/g3-seal-sharded-20261029T013648Z/seal.json --seal-sha256 8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f \
  --workers 24 --out "${1:?output path required}"
