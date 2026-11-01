#!/usr/bin/env python3
"""Close the calibration admission (E1-E5) against the ACTUAL freeze, in minutes.

Run right after check_e5_g2.py. Fills the mechanical fields of the q16 draft and
REFUSES (passed stays false, nonzero exit) unless everything verifies:
  actual_global_freeze   <- freeze.json path + content sha (what E5 bound to)
  e5_review_sha256       <- sha256 of the check_e5_g2.py receipt
  contract_evidence      <- E5 flipped to 'passed' ONLY; the runner requires
                            contract_evidence == {E1..E5:'passed'} EXACTLY, so
                            the receipt goes under a separate top-level e5_receipt key
  passed / verdict       <- true / PENDING_ROOT_SIGNATURE
Verified before flipping: E1-E4 already 'passed'; receipt checks_passed; every
required_byte_pins sha re-verifies locally; the draft's publication/frozen_2025
objects deep-equal the slice_decisions.publications of ALL 50 learned arms in
the freeze (exactly what runner.py calibration_ready() enforces at submit); the
review file still hashes right on the cluster.
ROOT then fills reviewer_worker/session/model + approval identity and signs.

usage (local machine — reads cluster over ssh like check_e5_g2.py):
  python3 fill_e5_admission.py --freeze-ref <CLUSTER_STORAGE>/.../g1-freeze-<STAMP>/freeze.json \
      --receipt <check_e5_g2.py --out file> [--host <BATCH_HOST>] [--out FILE]
"""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path

REPO = Path("<REPO>/.agents/operations")
LANE = REPO / "agy-lanes-20261027"
DEFAULT_DRAFT = LANE / "qwen/q16-calibration-admission/drafts/core-calibration-admission-E1-E5.json"
G2ROOT = "<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027"
STAGED_REVIEW = os.environ.get("BGB_G2_ROOT", G2ROOT) + "/docs/core-calibration-admission-E1-E5-review.json"
GROUP_DOCS = ("history", "stable", "timing", "h1", "h3", "origin", "count", "ordinary")

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def ssh_cat(host, path):
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", host, "cat " + path], capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"cannot read cluster file {path}: {p.stderr.decode()[:200]}")
    return p.stdout

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-ref", required=True, help="cluster path of published freeze.json")
    ap.add_argument("--receipt", required=True, help="check_e5_g2.py --out evidence json")
    ap.add_argument("--draft", default=str(DEFAULT_DRAFT))
    ap.add_argument("--host", default=os.environ.get("BGB_SSH_HOST", "<BATCH_HOST>"))
    ap.add_argument("--out", default=str(LANE / "g2r2/out/core-calibration-admission-E1-E5.json"))
    ap.add_argument("--staged-review", default=STAGED_REVIEW,
                    help="cluster path where the pinned review bytes are pre-staged")
    ap.add_argument("--local-review", default=str(LANE / "qwen/q16-calibration-admission/drafts/core-calibration-admission-E1-E5-review.json"))
    args = ap.parse_args()
    fails = []

    frez_raw = ssh_cat(args.host, args.freeze_ref)
    f = json.loads(frez_raw)
    base = args.freeze_ref.rsplit("/", 1)[0]
    groups = {}
    for g in GROUP_DOCS:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes", args.host, f"test -f {base}/{g}.json"],
                           capture_output=True)
        if p.returncode == 0:
            groups[g] = json.loads(ssh_cat(args.host, f"{base}/{g}.json"))
    receipt = json.loads(Path(args.receipt).read_bytes())
    draft = json.loads(Path(args.draft).read_bytes())

    if not receipt.get("checks_passed"):
        fails.append("E5 receipt checks_passed=false: " + str(receipt.get("failures")))
    ce = draft.get("contract_evidence", {})
    if {k: ce.get(k) for k in ("E1", "E2", "E3", "E4")} != {k: "passed" for k in ("E1", "E2", "E3", "E4")}:
        fails.append("E1-E4 not all 'passed' in draft")
    for name, pin in draft.get("required_byte_pins", {}).items():
        p = Path(pin["path"])
        if not p.is_file():
            fails.append(f"pin missing: {name}")
        elif sha(p.read_bytes()) != pin["sha256"]:
            fails.append(f"pin sha differs: {name}")
    # review must be present ON THE CLUSTER with its pinned sha (runner raw()-verifies it at submit).
    # If the draft's path is a retired namespace, accept the pre-staged copy at --staged-review (same bytes).
    review_ok = False
    try:
        got = ssh_cat(args.host, draft["review"]["path"])
        review_ok = sha(got) == draft["review"]["sha256"]
        if not review_ok:
            fails.append("cluster review sha differs")
    except SystemExit:
        try:
            got = ssh_cat(args.host, args.staged_review)
            if sha(got) == draft["review"]["sha256"]:
                draft["review"]["path"] = args.staged_review   # same bytes, reachable path
                draft["review"]["path_rewritten_by"] = "fill_e5_admission.py (old draft path unreachable)"
                review_ok = True
            else:
                fails.append("staged review sha differs")
        except SystemExit:
            fails.append(f"review unreachable on cluster at draft path or {args.staged_review}")
    if review_ok and sha(Path(args.local_review).read_bytes()) != draft["review"]["sha256"]:
        fails.append("local review copy differs from pinned sha")

    # deep-equal check exactly like the runner: all committed learned arms share one
    # publications object equal to the draft's publication (updated) / frozen_2025
    others = {a["arm_id"] for d in groups.values() for a in d.get("arms", [])}
    learned = [x for x in f["arms"] if x.get("status") == "committed_for_prediction"
               and x.get("role", {}).get("family") == "neural" and x["arm_id"] not in others]
    pubs = {json.dumps(x["slice_decisions"]["publications"], sort_keys=True) for x in learned}
    if len(learned) != 50 or len(pubs) != 1:
        fails.append(f"expected 50 learned arms with 1 shared publications object, got {len(learned)}/{len(pubs)}")
    elif pubs:
        got = json.loads(pubs.pop())
        if got.get("updated") != draft.get("publication"):
            fails.append("draft.publication != arms' publications.updated")
        if got.get("frozen_2025") != draft.get("frozen_2025"):
            fails.append("draft.frozen_2025 != arms' publications.frozen_2025")

    draft["actual_global_freeze"] = {
        "freeze_ref": args.freeze_ref,
        "freeze_json_sha256": sha(frez_raw),
        "freeze_dir": base,
        "global_freeze_sha256": receipt.get("actual_global_freeze", {}).get("sha256"),
        "frozen_at": f.get("frozen_at"),
        "arms_total": len(f["arms"]),
        "learned_arms": len(learned),
        "e5_receipt_sha256": sha(Path(args.receipt).read_bytes()),
    }
    draft["e5_review_sha256"] = draft["actual_global_freeze"]["e5_receipt_sha256"]
    draft["e5_receipt"] = receipt          # OUTSIDE contract_evidence (exact-5 rule)
    if fails:
        draft["passed"] = False
        draft["verdict"] = "BLOCKED: " + "; ".join(fails)[:180]
    else:
        ce["E5"] = "passed"
        draft["passed"] = True
        draft["all_five_admitted"] = True
        draft["verdict"] = "PENDING_ROOT_SIGNATURE"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(json.dumps(draft, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps({"written": str(out), "passed": draft["passed"], "failures": fails,
                      "verdict": draft["verdict"],
                      "admission_file_sha256": sha(out.read_bytes()),
                      "next": "ROOT: fill reviewer_worker/session/model + approval identity, sign, "
                              "upload to $R/docs/, put the file sha in ROOT-GO-G2.txt"}, indent=2))
    sys.exit(0 if not fails else 1)

if __name__ == "__main__":
    main()
