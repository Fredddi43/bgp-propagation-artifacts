#!/bin/bash
# D-A39 secondary re-scoring of R2 (r2_rescore_secondary.py). ONE singleton job on the cpu partition, cleared environment
# (the pinned runner checks SLURM_*, the thread variables == cpus and CUSTODIAN_ACCESS_LOG).
#   dry run (label-free, stops before the label opening):
#     sbatch --export=NIL r2_rescore_secondary.sbatch dry-run
#   the one label-opening run (needs the owner's approval file binding the dry run's ready.json):
#     sbatch --export=NIL r2_rescore_secondary.sbatch open-labels-D-A39 /abs/path/APPROVAL-D-A39.json
#SBATCH --partition=cpu
#SBATCH --cpus-per-task=64
#SBATCH --mem=1950000M
#SBATCH --time=1-00:00:00
#SBATCH --no-requeue
#SBATCH --job-name=r2-d-a39
#SBATCH --output=<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-logs/%x-%j.out
#SBATCH --error=<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-logs/%x-%j.err
set -eu
F=<FORECAST_ROOT>
CHAIN=<RESULTS_ROOT>/nobackup/g2-chain-20261029T001120Z/repo/.agents/operations/agy-lanes-20261027/g2r2/chain
PY=$F/newperiod-gate-private-v1/venv/bin/python
case "${1:-}" in
  dry-run) ARGS=(--dry-run) ;;
  open-labels-D-A39) ARGS=(--open-labels-D-A39 --approval "${2:?approval file path required}") ;;
  *) echo "usage: sbatch --export=NIL $0 dry-run | open-labels-D-A39 APPROVAL" >&2; exit 2 ;;
esac
cd /tmp
exec env -i PATH=/usr/bin:/bin LANG=C.UTF-8 \
  CUSTODIAN_ACCESS_LOG=$F/data-custodian/newperiod-identification-v1/access-log.jsonl \
  OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:?}" MKL_NUM_THREADS="$SLURM_CPUS_PER_TASK" OPENBLAS_NUM_THREADS="$SLURM_CPUS_PER_TASK" \
  POLARS_MAX_THREADS="$SLURM_CPUS_PER_TASK" \
  SLURM_JOB_ID="${SLURM_JOB_ID:?}" SLURM_JOB_PARTITION="${SLURM_JOB_PARTITION:?}" SLURM_CPUS_PER_TASK="$SLURM_CPUS_PER_TASK" \
  SLURM_MEM_PER_NODE="${SLURM_MEM_PER_NODE:?}" SLURM_RESTART_COUNT="${SLURM_RESTART_COUNT:-0}" \
  "$PY" -I -B "$CHAIN/r2_rescore_secondary.py" "${ARGS[@]}"
