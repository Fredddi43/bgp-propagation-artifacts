#!/usr/bin/env bash
# G2 PRE-STAGE (lane driver, 2026-10-28). Everything that does NOT depend on the G1 freeze, staged ONCE under
# the models tree; the freeze-day flow only regenerates plans/templates and submits. Writes ONLY NEW paths under
#   R = <CLUSTER_STORAGE>/.../<PROJECT>/forecasting-20261017/newperiod-g2-inference-v1-20261027
# (root decision 09:55Z: G2 work/ops/source roots under the models tree). Refuses if R already exists (new dirs
# only). Checks the models-free floor (>400 GB) before writing. Read commands on the cluster otherwise unaffected.
#
#   BGB_SSH_HOST (default <BATCH_HOST>; 2026-10-28 uses <BATCH_HOST> — same <CLUSTER_STORAGE> NFS, <BATCH_HOST> unreachable)
#   BGB_G2_ROOT  optional override for the rehearsal shadow root.
#   steps: stage | push | verify | runtime | all
set -euo pipefail
HOST=${BGB_SSH_HOST:-<BATCH_HOST>}
REPO=<REPO>
OPS=$REPO/.agents/operations
LANE=$OPS/agy-lanes-20261027
PY=$REPO/.venv/bin/python
B=<FORECAST_ROOT>
R=${BGB_G2_ROOT:-$B/newperiod-g2-inference-v1-20261027}
LOCAL=${BGB_PRESTAGE_LOCAL:-<AGENT_TMP>/g2-prestage}
SRC=$LOCAL/source            # local mirror of R/source
OPSdir=$LOCAL/runners        # local mirror of R/runners
VENV=$B/newperiod-gate-private-v1/venv/bin/python3

# runner dirs staged WHOLE (the runner hashes its HERE siblings): q8 learned/baseline/ordinary, q9 history/stable/origin(-r3), q10 timing-r4/h3, plus the h1 successor
FAMILIES=(newperiod-learned-custodian-runner-r2-20261023 newperiod-baseline-custodian-runner-20261023
          newperiod-ordinary-inference-20261023 newperiod-history-inference-20261023
          newperiod-stable-inference-20261023 newperiod-origin-inference-r3-parallel-20261027
          newperiod-timing-inference-r4-20261027 newperiod-h3-inference-20261023)
WORKS=(learned baseline ordinary history stable origin timing-newfit timing-reuse h1 h3 r2)

need() { [[ $1 -eq 0 ]] || { echo "REFUSED: $2" >&2; exit 1; }; }

step_stage() {
  mkdir -p "$LOCAL"
  # 1) one scientific closure for ALL family dirs (working-tree bytes; every pins.json/SCIENCE sha verified)
  local args=()
  for f in "${FAMILIES[@]}"; do args+=(--family-dir "$OPS/$f"); done
  args+=(--family-dir "$LANE/g2r2/h1-successor")
  rm -rf "$SRC"; mkdir -p "$SRC"
  (cd "$LOCAL" && "$PY" -B "$LANE/g2r2/g2/stage_source.py" "${args[@]}" --dest "$SRC" --final-root "$R/source")
  # 2) whole ops dirs for the q8/q10 spec layout: R/runners/<dir>/<entry>
  rm -rf "$OPSdir"; mkdir -p "$OPSdir"
  for f in "${FAMILIES[@]}"; do rsync -a --exclude '__pycache__' "$OPS/$f/" "$OPSdir/$f/"; done
  rsync -a --exclude '__pycache__' "$LANE/g2r2/h1-successor/" "$OPSdir/h1-successor/"
  # 3) the q9 legacy layout the make_g2_plan spec pins: closure-root/runners/<family>-runner.py WITH its HERE
  #    siblings beside it (runners exec reviewed_*.py/pins.json from Path(__file__).parent) + kernel/<f>.py
  mkdir -p "$SRC/runners" "$SRC/kernel" "$SRC/access"
  cp "$OPS/newperiod-history-inference-20261023/runner.py"        "$SRC/runners/history-runner.py"
  cp "$OPS/newperiod-stable-inference-20261023/runner.py"         "$SRC/runners/stable-runner.py"
  cp "$OPS/newperiod-origin-inference-r3-parallel-20261027/runner.py" "$SRC/runners/origin-runner.py"
  for s in reviewed_runner.py reviewed_helpers.py reviewed_baseline.py pins.json; do
    cp "$OPS/newperiod-origin-inference-r3-parallel-20261027/$s" "$SRC/runners/$s"   # shared bytes (shas verified below)
  done
  for s in reviewed_family.py reviewed_membership.py reviewed_parallel.py; do
    cp "$OPS/newperiod-origin-inference-r3-parallel-20261027/$s" "$SRC/runners/$s"
  done
  cp "$OPS/newperiod-history-inference-20261023/history.py" "$SRC/runners/history.py"
  cp "$OPS/newperiod-stable-inference-20261023/stable.py"   "$SRC/runners/stable.py"
  cp "$SRC/runners/history.py" "$SRC/kernel/history.py"; cp "$SRC/runners/stable.py" "$SRC/kernel/stable.py"
  # local pin assertions (same constants the runners/validators enforce)
  $PY -B - "$SRC" <<'PY'
import hashlib, sys
from pathlib import Path
src = Path(sys.argv[1])
def sha(p): return hashlib.sha256((src / p).read_bytes()).hexdigest()
expect = {
 "runners/history-runner.py": "06eefa377630f58b5085eff661bd6a8030e4ca294158c6d4d6ce28a6c28c5a24",
 "runners/stable-runner.py":  "43e8579b36b95e1550caf8f1ee05f57d73216ec457f32344c6a56f7abc253788",
 "runners/origin-runner.py":  "cc63a91cc98c46dfc5928ee46977e6c7c4c2e311aa191d725f5eb9daefcde9d8",
 "runners/reviewed_parallel.py": "1222d49e575df39a3f3f3e67ae6dcf4f3c5efabe3c5f45f395c609be81e00c8c",
 "runners/reviewed_runner.py": "ed420e4cab1b16401870e7d9b9e84a8811733a9cb77d9abefe11e48fb7f149c3",
 "runners/reviewed_helpers.py": "9c41f26746205037f3561f836fa51e91c1ab609a18368caf1fcf57b57a3db307",
 "runners/reviewed_baseline.py": "71731649caaba4a0954a4853a012a6d98058c9a96c6ddb082d259e6bfff32158",
 "runners/pins.json": "b06fd04fcb91b7b432434a04a1eea08fa4b255fdb88e00ea0f9cbecb98b434a9",
 "kernel/history.py": "433d2d6356920f62f70b0ae5c338f9a1b003052c32db75fa32c2f0e4851e3f6e",
 "kernel/stable.py":  "3375dcff1a007ee043b5e254fec5392cba4c282c2a6c16e4cfb54337ef2e3e54",
}
bad = [p for p, h in expect.items() if sha(p) != h]
print("closure sha256:", sha("scientific-closure.json"))
sys.exit("PIN MISMATCH: " + ", ".join(bad) if bad else "local pin assertions: all OK")
PY
}

step_push() {
  local free; free=$(ssh -o BatchMode=yes "$HOST" "df -BG <MODELS_ROOT> | tail -1 | awk '{print \$4}'" | tr -dc '0-9')
  if (( free <= 400 )); then echo "REFUSED: models free ${free}G <= 400 GB floor" >&2; exit 1; fi
  echo "models free: ${free}G (floor 400G ok)"
  if ssh -o BatchMode=yes "$HOST" "test -e $R"; then echo "REFUSED: R already exists on cluster: $R (new dirs only — pick a fresh root)" >&2; exit 1; fi
  ssh -o BatchMode=yes "$HOST" "mkdir -p $R/source"
  tar -C "$SRC" -c . | ssh -o BatchMode=yes "$HOST" "tar -C $R/source -x"
  ssh -o BatchMode=yes "$HOST" "mkdir -p $R/runners"
  tar -C "$OPSdir" -c . | ssh -o BatchMode=yes "$HOST" "tar -C $R/runners -x"
  local dirs=(); for w in "${WORKS[@]}"; do dirs+=("$R/work/$w" "$R/work/$w/logs"); done
  ssh -o BatchMode=yes "$HOST" "mkdir -p $R/access $R/docs ${dirs[*]}"
}

step_verify() {
  # remote closure/entry shas must equal the local ones (byte-identity through the tar pipe)
  local lf rf
  lf=$(sha256sum "$SRC/scientific-closure.json" | cut -d' ' -f1)
  rf=$(ssh -o BatchMode=yes "$HOST" "sha256sum $R/source/scientific-closure.json" | cut -d' ' -f1)
  if [[ "$lf" != "$rf" ]]; then echo "REFUSED: closure differs local $lf remote $rf" >&2; exit 1; fi
  echo "closure sha256 (G2_CLOSURE_SHA): $lf"
  # full byte-identity check: every file under source/ and runners/, local vs remote
  (cd "$LOCAL" && find source runners -type f -exec sha256sum {} + | sort -k2 > local-shas.txt)
  ssh -o BatchMode=yes "$HOST" "cd $R && find source runners -type f -exec sha256sum {} + | sort -k2" > "$LOCAL/remote-shas.txt"
  diff -u "$LOCAL/local-shas.txt" "$LOCAL/remote-shas.txt" && echo "PRESTAGE VERIFY: every staged byte identical local==remote"
}

step_runtime() {
  # ordinary's model_runtime document, produced with the SAME private venv python g2_submit --python will use.
  # Writes R/docs/model-runtime.json (new file under the models tree). Read-only imports; see make_model_runtime.py.
  ssh -o BatchMode=yes "$HOST" "$VENV -I -B -" < "$LANE/g2r2/templates/ordinary-baseline-primary/make_model_runtime.py" > "$LOCAL/model-runtime.json"
  if [[ ! -s "$LOCAL/model-runtime.json" ]]; then echo "REFUSED: empty model_runtime output" >&2; exit 1; fi
  cat "$LOCAL/model-runtime.json" | ssh -o BatchMode=yes "$HOST" "cat > $R/docs/model-runtime.json"
  echo "model_runtime path: $R/docs/model-runtime.json"
  echo "model_runtime sha: $(sha256sum "$LOCAL/model-runtime.json" | cut -d' ' -f1)"
}

case "${1:-all}" in
  stage) step_stage;; push) step_push;; verify) step_verify;; runtime) step_runtime;;
  all) step_stage; step_push; step_verify; step_runtime;;
  *) echo "usage: $0 [stage|push|verify|runtime|all]" >&2; exit 2;;
esac
