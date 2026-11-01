#!/usr/bin/env bash
# G2 coordinated submit (lane driver q37, 2026-10-28): submits ALL ten G2 arrays in the correct ORDER and records
# every job id. Order is a RUNNER requirement, not a convention (G2-DESIGN.md:22, PLAN-SPEC §3, h1-h3-timing
# README "Order constraints"):
#   1. g2-learned-core (the 50 primary core arms) submitted FIRST;
#   2. everything else submitted immediately (the scheduler runs them concurrently);
#   3. g2-timing-REUSE20 with --dependency=afterok:<learned array id> — the r4 reuse arms read the core arms'
#      committed predictions via custody.verify_arm. If any core arm FAILS the array never reaches afterok: the
#      reuse array stays held; root decides (a failed primary arm blocks R2 anyway). Releasing by hand = resubmit
#      the reuse spec without the dependency (never cancel core arms).
# Each submission: g2_submit.py --dry-run ON THE CLUSTER (writes the exact .sbatch into the spec work dir and
# prints the sbatch line), then that exact line runs on <SUBMIT_HOST> under the launch flock; sacct is the 60-s
# verification (done by monitor_g2.sh). --export=NIL, partition cpu, no requeue are baked into g2_submit.
#
# usage: submit_all_g2.sh [--dry] [--root R] [--host python-host] [--slurm <SUBMIT_HOST>] [--go FILE]
#   --dry  rehearsal mode: generate every .sbatch + print every sbatch line (with the dependency placeholder),
#          submit NOTHING. Real mode refuses unless the go file exists on the cluster and is non-empty, AND
#          refuses if $R/g2-jobs.tsv already has ids (double-submit protection; --force acknowledges a resume).
set -euo pipefail
REPO=<REPO>
B=<FORECAST_ROOT>
R=${BGB_G2_ROOT:-$B/newperiod-g2-inference-v1-20261027}
HOST=${BGB_SSH_HOST:-<BATCH_HOST>}   # <BATCH_HOST> unreachable since 2026-10-28; same <CLUSTER_STORAGE> mount
SLURM=${BGB_SLURM_HOST:-<SUBMIT_HOST>}
VENV=$B/newperiod-gate-private-v1/venv/bin/python
GO=$R/ROOT-GO-G2.txt
DRY=0
FORCE=0
while [[ $# -gt 0 ]]; do case "$1" in
  --dry) DRY=1;; --force) FORCE=1;; --root) R=$2; shift;; --host) HOST=$2; shift;; --slurm) SLURM=$2; shift;; --go) GO=$2; shift;;
  *) echo "usage: $0 [--dry] [--force] [--root R] [--host H] [--slurm S] [--go FILE]" >&2; exit 2;;
esac; shift; done
JOBS=$R/g2-jobs.tsv
rssh(){ ssh -o BatchMode=yes "$HOST" "$@"; }

# name|stage|spec-relative|cpus|mem_mib|wall|concurrency|job_name  (fallback shapes; spec submit/job_submit blocks
# override per-array values when present — RESOURCE-POLICY over-reserve values, verified against the three READMEs)
ARRAYS=(
 "learned|core|$R/gen/q8-learned/spec-learned.json|32|500000|1-00:00:00|50|g2-learned-core"
 "baseline|parallel|$R/gen/q8-baseline/spec-baseline.json|64|1000000|1-00:00:00|12|g2-baseline"
 "ordinary|parallel|$R/gen/q8-ordinary/spec-ordinary.json|32|500000|1-00:00:00|12|g2-ordinary"
 "history|parallel|$R/gen/q9-history/g2.spec.json|64|1000000|1-00:00:00|48|g2-history"
 "stable|parallel|$R/gen/q9-stable/g2.spec.json|32|500000|1-00:00:00|24|g2-stable"
 "origin|parallel|$R/gen/q9-origin/g2.spec.json|32|900000|1-00:00:00|40|g2-origin"
 "h1|parallel|$R/h1/g2.spec.json|64|1000000|1-00:00:00|20|g2-h1-arms"
 "h3|parallel|$R/h3/g2.spec.json|64|1000000|1-00:00:00|52|g2-h3-arms"
 "timing-newfit|parallel|$R/timing/g2.spec-newfit.json|64|1000000|1-00:00:00|40|g2-timing-NEWFIT40"
 "timing-reuse|dependent:$R/gen/q8-learned/spec-learned.json|$R/timing/g2.spec-core-reuse.json|64|1000000|1-00:00:00|20|g2-timing-REUSE20"
)


submit_one(){ local name=$1 stage=$2 spec=$3 cpus=$4 mem=$5 wall=$6 conc=$7 job=$8 dep=${9:-}
  local line
  line=$(rssh "python3 -B $R/g2/g2_submit.py --spec $spec --python $VENV --cpus $cpus --mem-mib $mem --wall $wall --concurrency $conc --job-name $job --dry-run" | tail -1)
  [[ "$line" == sbatch* ]] || { echo "FAIL $name: g2_submit printed: $line" >&2; return 1; }
  if [[ "$stage" == dependent:* ]]; then
    if [[ -z "$dep" ]]; then echo "DRY: $name  <- $line  (dependency id filled at real submit: afterok:<learned array>)"; return 0; fi
    line=${line/sbatch /sbatch --dependency=afterok:$dep }
  fi
  if [[ $DRY -eq 1 ]]; then echo "DRY: $name  <- $line"
  else
    local id; id=$(ssh -o BatchMode=yes "$SLURM" "mkdir -p <AGENT_TMP> && flock -w 1800 <AGENT_TMP>/bgb-launch.lock $line")
    echo -e "$(date -u +%FT%TZ)\t$name\t$job\t${id%%;*}\t$spec" >> "$JOBS"
    echo "SUBMITTED $name: $id"
  fi
}

if [[ $DRY -eq 0 ]]; then
  rssh "test -s $GO" || { echo "REFUSED: $GO missing/empty — G2 not authorized (ROOT-GO-G2.txt)" >&2; exit 1; }
  if rssh "test -s $JOBS" && [[ $FORCE -eq 0 ]]; then
    echo "REFUSED: $JOBS already has submitted job ids — double-submit guard (rerun with --force only on root's call):" >&2
    rssh "cat $JOBS" >&2; exit 1
  fi
fi
echo "== G2 submit pass on $R (host $HOST, slurm $SLURM, dry=$DRY)"
LEARNED_ID=""
for entry in "${ARRAYS[@]}"; do IFS='|' read -r name stage spec cpus mem wall conc job <<< "$entry"
  cpus=$(rssh "python3 -B -c 'import json;d=json.load(open(\"$spec\"));s=d.get(\"submit\") or d.get(\"job_submit\") or {};print(s.get(\"cpus\",$cpus))'")
  mem=$(rssh "python3 -B -c 'import json;d=json.load(open(\"$spec\"));s=d.get(\"submit\") or d.get(\"job_submit\") or {};print(s.get(\"mem_mib\",$mem))'")
  wall=$(rssh "python3 -B -c 'import json;d=json.load(open(\"$spec\"));s=d.get(\"submit\") or d.get(\"job_submit\") or {};print(s.get(\"wall\",\"$wall\"))'")
  conc=$(rssh "python3 -B -c 'import json;d=json.load(open(\"$spec\"));s=d.get(\"submit\") or d.get(\"job_submit\") or {};print(s.get(\"concurrency\",min($conc,len(d[\"arms\"]))))'")
  job=$(rssh "python3 -B -c 'import json;d=json.load(open(\"$spec\"));s=d.get(\"submit\") or d.get(\"job_submit\") or {};print(s.get(\"job_name\",\"$job\"))'")
  dep=""
  if [[ "$stage" == dependent:* ]]; then
    if [[ $DRY -eq 1 ]]; then dep=""
    else
      [[ -n "$LEARNED_ID" ]] || { echo "REFUSED: no learned core job id recorded this run; reuse must not go without its dependency" >&2; exit 1; }
      dep="$LEARNED_ID"
    fi
  fi
  submit_one "$name" "$stage" "$spec" "$cpus" "$mem" "$wall" "$conc" "$job" "$dep"
  if [[ "$stage" == core && $DRY -eq 0 ]]; then
    LEARNED_ID=$(tail -1 "$JOBS" | cut -f4)
  fi
done
[[ $DRY -eq 1 ]] || echo "job ids recorded in $JOBS — run monitor_g2.sh (sacct verification after 60 s is mandatory)"
