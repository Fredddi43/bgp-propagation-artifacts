#!/usr/bin/env bash
# monitor_g2.sh — one-shot status of the G2 arrays from $R/g2-jobs.tsv (squeue+sacct+work dirs).
# Run after submit; repeat at will (or `watch -n 60`). Read-only; safe before submission too.
#   BGB_SSH_HOST (default <BATCH_HOST>), BGB_G2_ROOT (default real root)
set -euo pipefail
HOST="${BGB_SSH_HOST:-<BATCH_HOST>}"
R="${BGB_G2_ROOT:-<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027}"

ssh -o BatchMode=yes "$HOST" bash -s "$R" <<'REMOTE'
set -u
R="$1"; T="$R/g2-jobs.tsv"
[ -f "$T" ] || { echo "no $T yet — nothing submitted"; exit 0; }
ids=$(awk -F'\t' '$4!="" {print $4}' "$T" | paste -sd, -)   # tsv cols: time, name, job_name, id, spec
[ -n "$ids" ] || { echo "job ids empty — nothing submitted"; exit 0; }
echo "job ids: $ids"

echo; echo "=== queued/running now (squeue, this user) ==="
squeue -u "$(id -un)" -o "%.12i %.9P %.32j %.8T %.10M %.6D %.22R" 2>/dev/null | head -40 || echo "(none pending/running)"

echo; echo "=== per-array sacct rollup over OUR job ids (array task rows) ==="
sacct -n -P -S 2026-10-28T00:00:00 --format=JobID,JobName,State,Exit 2>/dev/null | awk -F'|' -v ids="$ids" '
  BEGIN { n=split(ids,a,","); for (i=1;i<=n;i++) want[a[i]]=1 }
  $1 ~ /^[0-9]+_[0-9]+$/ {                       # task rows only: <arrayid>_<task>
    id=$1; sub(/_.*/,"",id)
    if (!(id in want)) next
    fam=$2; st=$3; ex=$4
    done[fam]++
    if (st=="COMPLETED" && ex=="0:0") ok[fam]++
    else if (st=="RUNNING"||st=="PENDING"||st=="CONFIGURING"||st=="SPECIAL_EXIT") run[fam]++
    else bad[fam]++
  }
  END { for (k in done) printf "%-26s tasks=%-4d ok=%-4d run/pend=%-4d BAD=%d\n", k, done[k], ok[k]+0, run[k]+0, bad[k]+0 }' \
 | sort

echo; echo "=== failed/cancelled tasks (rerun pointers) ==="
sacct -n -P -S 2026-10-28T00:00:00 --format=JobID,JobName,State,Exit 2>/dev/null | awk -F'|' -v ids="$ids" '
  BEGIN { n=split(ids,a,","); for (i=1;i<=n;i++) want[a[i]]=1 }
  $1 ~ /^[0-9]+_[0-9]+$/ { id=$1; sub(/_.*/,"",id)
    if ((id in want) && ($3=="FAILED"||$3=="TIMEOUT"||$3~/CANCEL/||$4!="0:0")) print }' \
 | sort | head -40

echo; echo "=== family progress from work dirs ==="
for f in learned baseline ordinary history stable origin timing-newfit timing-reuse h1 h3; do
  d="$R/work/$f"
  [ -d "$d" ] || continue
  n=$(find "$d" -maxdepth 2 -name completed.json 2>/dev/null | wc -l)
  i=$(find "$d" -maxdepth 2 -name intent.json 2>/dev/null | wc -l)
  printf "%-14s intents=%-4s completed=%-4s\n" "$f" "$i" "$n"
done
REMOTE
