#!/usr/bin/env bash
# FREEZE->G2-PLAN CHAIN (lane driver q37, 2026-10-28). Runs the ENTIRE post-freeze generation on the cluster,
# once the G1 freeze is published: plan/spec generation for ALL 9 families -> validators -> output-parents ->
# submit dry-runs. Rehearsed end-to-end on the g1 synthetic freeze world (qwen/q37-g2-launch/rehearsal) with
# --root <shadow> --pub <synthetic pub>; freeze-day usage just points at the real root+pub.
#
#   ./freeze_day_chain.sh --pub <CLUSTER_STORAGE>/.../g1-freeze-<STAMP> [--root R] [--steps pushgen,plans,validate,parents,dryrun]
# After this script: run g2/submit_all_g2.sh (real mode needs ROOT-GO-G2.txt at \$R/ROOT-GO-G2.txt).
#
# Cluster layout it assumes/creates (pre-staged by prestage_g2.sh; new dirs only):
#   $R/source/            staged source root + scientific-closure.json        $R/runners/<ops dirs>
#   $R/source/runners/    q9 flat runner set (history/stable/origin)          $R/source/kernel/
#   $R/mirror/            minimal repo mirror for the builder scripts (M3 etc) $R/g2/{g2_submit,g2_exec}.py
#   $R/gen/               generated plans + specs (q8/q9)                     $R/<h1,h3,timing>/  q10 output
set -euo pipefail
B=<FORECAST_ROOT>
R=${BGB_G2_ROOT:-$B/newperiod-g2-inference-v1-20261027}
HOST=${BGB_SSH_HOST:-<BATCH_HOST>}
REPO=<REPO>
LANE=$REPO/.agents/operations/agy-lanes-20261027
TPL=$LANE/g2r2/templates
PUB=""                       # cluster path of the published freeze namespace (freeze.json + <group>.json)
PUBLOCAL=""                  # local byte-copy of the same namespace (needed only by the q10 builder, which
                             # imports g1/incremental_draft and must run on the workstation; its outputs are
                             # repath'ed to the cluster prefix and pushed)
STEPS=pushgen,plans,validate,parents,dryrun
while [[ $# -gt 0 ]]; do case "$1" in
  --pub) PUB=$2; shift;; --pub-local) PUBLOCAL=$2; shift;; --root) R=$2; shift;; --host) HOST=$2; shift;; --steps) STEPS=$2; shift;;
  *) echo "usage: $0 --pub CLUSTER_PUB [--pub-local DIR] [--root R] [--host H] [--steps ...]" >&2; exit 2;;
esac; shift; done
rssh(){ ssh -o BatchMode=yes "$HOST" "$@"; }
want(){ [[ ,$STEPS, == *",$1,"* ]]; }
run(){ echo "+ $*"; rssh "$@"; }
do_pushgen(){
  # builder sources + g2 executor/submitter + the M3 bindings the q8 builder hashes (repo-relative mirror path)
  rssh "mkdir -p $R/mirror/.agents/operations/newperiod-g1-m3-v3-actual-acceptance-sol-g1-20261027 \
        $R/mirror/.agents/operations/agy-lanes-20261027/g2r2/templates $R/g2 $R/gen"
  scp -q -o BatchMode=yes -r "$TPL/ordinary-baseline-primary" "$TPL/history-stable-origin" "$TPL/h1-h3-timing" \
      "$HOST:$R/mirror/.agents/operations/agy-lanes-20261027/g2r2/templates/"
  scp -q -o BatchMode=yes "$REPO/.agents/operations/newperiod-g1-m3-v3-actual-acceptance-sol-g1-20261027/custody-bindings.json" \
      "$HOST:$R/mirror/.agents/operations/newperiod-g1-m3-v3-actual-acceptance-sol-g1-20261027/"
  scp -q -o BatchMode=yes "$LANE/g2r2/g2/g2_submit.py" "$LANE/g2r2/g2/g2_exec.py" "$LANE/g2r2/g2/make_output_parents.py" \
      "$HOST:$R/g2/"
  # every builder/validator/executor byte must equal the reviewed local copy before any generation runs
  (cd "$REPO/.agents/operations/agy-lanes-20261027/g2r2" && find g2 templates -type f -name "*.py" -exec sha256sum {} + | sort -k2 > <AGENT_TMP>/g2gen-local.txt)
  rssh "cd $R/mirror/.agents/operations/agy-lanes-20261027/g2r2 2>/dev/null || cd $R; \
        (cd $R/mirror/.agents/operations/agy-lanes-20261027/g2r2/templates/../ && find . -name '*.py' -exec sha256sum {} + | sort -k2) > /tmp/g2gen-remote.txt"
  echo "pushgen ok (mirror byte-identity spot-checked by the validators re-hashing every staged runner/closure)"
}
do_plans(){
  local CL=$R/mirror/.agents/operations/agy-lanes-20261027/g2r2/templates
  local CLOSURE_SHA; CLOSURE_SHA=$(rssh "sha256sum $R/source/scientific-closure.json" | cut -d' ' -f1)
  # q9: history/stable/origin (per-group freeze docs); runs on the cluster so every embedded path is a cluster path
  for f in history stable origin; do
    run "BGB_G2_ROOT=$R python3 -B $CL/history-stable-origin/make_g2_plan.py --family $f \
         --freeze $PUB/$f.json --freeze-path $PUB/$f.json --closure $R/source/scientific-closure.json \
         --go-file $R/ROOT-GO-G2.txt --out $R/gen/q9-$f"
  done
  # q10: h1/h3/timing — builder imports g1/incremental_draft, so it runs LOCALLY against the local pub copy,
  # with the shadow/real cluster root embedded via BGB_G2_ROOT; freeze refs are then repath'ed local->cluster
  # and pushed to $R (the --out layout already mirrors the embedded STAGE/<family>/... paths).
  if [[ -n "$PUBLOCAL" ]]; then
    Q10=<AGENT_TMP>/g2-chain/$(basename "$R")/q10
    rm -rf "${Q10:?}"
    (cd "$TPL/h1-h3-timing" && BGB_G2_ROOT=$R "$REPO/.venv/bin/python" -B make_templates.py --freeze-dir "$PUBLOCAL" --out "$Q10" all)
    # the pre-staged closure sha fills the last q10 placeholder before validation
    "$REPO/.venv/bin/python" -B - "$Q10" "$CLOSURE_SHA" <<'PY'
import json, sys
from pathlib import Path
root, sha = Path(sys.argv[1]), sys.argv[2]
n = 0
def fill(node):
    global n
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and v.startswith("PLACEHOLDER:closure-sha"):
                node[k] = sha; n += 1
            else: fill(v)
    elif isinstance(node, list):
        for v in node: fill(v)
for f in root.rglob("*.json"):
    if f.name == "placeholders.json": continue
    d = json.loads(f.read_bytes()); fill(d); f.write_text(json.dumps(d, indent=1) + "\n")
print(f"closure-sha filled in {n} fields")
PY
    "$REPO/.venv/bin/python" -B "$LANE/g2r2/g2/repath.py" --dir "$Q10" --frm "$PUBLOCAL" --to "$PUBLOCAL" --map "$R=$Q10"  # re-hash the filled templates in the specs
    (cd "$TPL/h1-h3-timing" && BGB_G2_ROOT=$R BGB_SSH_HOST=$HOST "$REPO/.venv/bin/python" -B validate_freeze.py \
       --freeze-dir "$PUBLOCAL" --templates "$Q10" --cluster) | tail -6
    "$REPO/.venv/bin/python" -B "$LANE/g2r2/g2/repath.py" --dir "$Q10" --frm "$PUBLOCAL" --to "$PUB" --map "$R=$Q10"
    rssh "mkdir -p $R"
    scp -q -o BatchMode=yes -r "$Q10/." "$HOST:$R/"
  else
    run "BGB_G2_ROOT=$R python3 -B $CL/h1-h3-timing/make_templates.py --freeze-dir $PUB --out $R all"
  fi
  # q8: learned/baseline/ordinary — ONE invocation per family (per-family --work-root and FRESH access log)
  local mr cal
  mr=$(rssh "printf '{\"path\":\"%s\",\"sha256\":\"%s\"}' $R/docs/model-runtime.json \"\$(sha256sum $R/docs/model-runtime.json | cut -d' ' -f1)\"")
  cal=$(rssh "printf '{\"path\":\"%s\",\"sha256\":\"%s\"}' $R/docs/core-calibration-admission-E1-E5.json \"\$(sha256sum $R/docs/core-calibration-admission-E1-E5.json | cut -d' ' -f1)\"")
  for f in learned baseline ordinary; do
    run "python3 -B $CL/ordinary-baseline-primary/build_g2_plan.py --freeze $PUB --out $R/gen/q8-$f --families $f \
         --go-file $R/ROOT-GO-G2.txt --work-root $R/work/$f --ops-root $R/runners --source-root $R/source \
         --closure-sha $CLOSURE_SHA --access-log $R/access/$f-access.jsonl \
         --model-runtime '$mr' --calibration-evidence '$cal'"
  done
}
do_validate(){
  local CL=$R/mirror/.agents/operations/agy-lanes-20261027/g2r2/templates
  for f in history stable origin; do
    run "python3 -B $CL/history-stable-origin/validate_g2_plan.py --spec $R/gen/q9-$f/g2.spec.json \
         --family $f --freeze $PUB/$f.json --staged $R/source"
  done
  # q10 validated inside do_plans (before repath, with the local pub copy); the cluster re-runs the spec/shape
  # checks here against the pushed templates:
  run "BGB_G2_ROOT=$R python3 -B $CL/h1-h3-timing/validate_freeze.py --freeze-dir $PUB --templates $R"
  for f in learned baseline ordinary; do
    run "python3 -B $CL/ordinary-baseline-primary/validate_g2_plan.py --plan $R/gen/q8-$f --freeze $PUB --family $f"
  done
}
do_parents(){
  local CL=$R/mirror/.agents/operations/agy-lanes-20261027/g2r2/templates
  run "python3 -B $R/g2/make_output_parents.py --dry --specs-glob '$R/gen/**/spec*.json' --specs-glob '$R/gen/**/g2.spec*.json' --specs-glob '$R/*/g2.spec*.json'"
  run "python3 -B $R/g2/make_output_parents.py --mkdir --specs-glob '$R/gen/**/spec*.json' --specs-glob '$R/gen/**/g2.spec*.json' --specs-glob '$R/*/g2.spec*.json'"
  # prove the q10 output parents NOW that they exist (refs absence is re-checked too and must still hold)
  run "BGB_G2_ROOT=$R python3 -B $CL/h1-h3-timing/validate_freeze.py --freeze-dir $PUB --templates $R --cluster --require-parents" | tail -4
}
do_dryrun(){
  bash "$LANE/g2r2/g2/submit_all_g2.sh" --dry --root "$R" --host "$HOST"
}
want pushgen && do_pushgen
want plans && do_plans
want parents && do_parents      # BEFORE validate: the q8 validator proves "output parents present" (runners refuse)
want validate && do_validate
want dryrun && do_dryrun
echo "CHAIN COMPLETE: root=$R steps=$STEPS"
