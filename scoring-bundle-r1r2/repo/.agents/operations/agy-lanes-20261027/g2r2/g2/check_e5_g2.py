#!/usr/bin/env python3
"""E5 evidence for the learned/primary calibration admission, against the ACTUAL published G1 freeze.

The pinned E5 package (newperiod-core-e5-freeze-check-astra-v1-20261025/check_e5.py) is PATH-BOUND to the
retired complete-retention-v2 finalize namespace (its FREEZE/DONE constants at check_e5.py:12-13 plus a
done.json/g1-actual-acceptance ceremony the g1 lane's freeze_run.py never emits) — it structurally cannot
accept a freeze published at g1-freeze-<STAMP>. See ALERT-G2-E5.md (qwen/q37-g2-launch). This script verifies
the mechanically checkable E5 ASSERTION exactly as the LEARNED RUNNER consumes it
(newperiod-learned-custodian-runner-r2-20261023/runner.py:99-118 + q16 CHECKLIST B):

  E5(claimed) := the published global freeze carries 50 committed learned arms (role.family==neural, the q8
  load_arms selection), 40 updated + 10 frozen_2025, whose slice_decisions.publications are ALL IDENTICAL and
  deep-equal the q16 admission draft's pinned publication/frozen_2025 refs, decision_rules refs are canonical,
  and freeze.frozen_at postdates the accepted E1-E4 review.

Output (stdout JSON): evidence document, kind newperiod_g2_e5_freeze_evidence_v1, checks_passed true/false +
bindings{actual_global_freeze, e1_e4_review, admission_draft} + learned_bindings_sha256 (same row encoding as
check_e5.check_bytes). Exit 0 only if checks_passed. ROOT then fills/attests the admission
(fill_e5_admission.py) — this script asserts NOTHING under any identity.
usage: check_e5_g2.py --freeze-ref <CLUSTER_STORAGE>/.../g1-freeze-<STAMP>/freeze.json [--host <BATCH_HOST>]
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANE = HERE.parents[1]
Q16 = LANE / "qwen" / "q16-calibration-admission" / "drafts" / "core-calibration-admission-E1-E5.json"
GROUP_DOCS = ("history", "stable", "timing", "h1", "h3", "origin", "count", "ordinary")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(doc):
    return (json.dumps(doc, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def ssh_cat(host, path):
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", host, "cat " + path], capture_output=True)
    if p.returncode != 0:
        raise SystemExit(f"cannot read cluster file {path}: {p.stderr.decode()[:200]}")
    return p.stdout


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--freeze-ref", required=True, help="cluster path of the published freeze.json")
    a.add_argument("--host", default=None)
    a.add_argument("--out", help="write the evidence document here (default: stdout only)")
    args = a.parse_args()
    host = args.host or None
    import os
    host = host or os.environ.get("BGB_SSH_HOST", "<BATCH_HOST>")
    checks, fails = [], []

    def check(name, ok):
        checks.append((name, bool(ok)))
        if not ok:
            fails.append(name)

    frez_raw = ssh_cat(host, args.freeze_ref)
    f = json.loads(frez_raw)
    base = args.freeze_ref.rsplit("/", 1)[0]
    groups = {g: json.loads(ssh_cat(host, f"{base}/{g}.json")) for g in GROUP_DOCS if True}  # missing doc -> fail
    others = {arm["arm_id"] for d in groups.values() for arm in d.get("arms", [])}
    committed = [x for x in f["arms"] if x.get("status") == "committed_for_prediction"]
    learned = [x for x in committed if x.get("role", {}).get("family") == "neural" and x["arm_id"] not in others]
    learned.sort(key=lambda x: x["arm_id"])
    check("50 learned arms", len(learned) == 50)
    check("40 updated + 10 frozen_2025",
          sum(x["role"].get("training") == "updated" for x in learned) == 40
          and sum(x["role"].get("training") == "frozen_2025" for x in learned) == 10)
    draft = json.loads(Q16.read_bytes())
    pubs = {json.dumps(x["slice_decisions"]["publications"], sort_keys=True) for x in learned}
    check("all 50 slice_decisions.publications identical (one admission doc serves all 50)", len(pubs) == 1)
    if len(pubs) == 1:
        got = json.loads(pubs.pop())
        check("publication == q16-pinned updated publication",
              got.get("updated") == draft["publication"])
        check("frozen_2025 == q16-pinned frozen_2025 slice rule",
              got.get("frozen_2025") == draft["frozen_2025"])
    check("decision_rules refs canonical",
          all(isinstance(x.get("decision_rules"), dict) and set(x["decision_rules"]) == {"path", "sha256"}
              and len(x["decision_rules"]["sha256"]) == 64 for x in learned))
    # every unique decision_rules ref exists ON THE CLUSTER with the pinned sha (deduplicated)
    uniq = {x["decision_rules"]["path"]: x["decision_rules"]["sha256"] for x in learned}
    lines = subprocess.run(["ssh", "-o", "BatchMode=yes", host,
                            "sha256sum " + " ".join(sorted(uniq))], capture_output=True, text=True).stdout
    got_shas = dict(reversed(ln.split(None, 1)) for ln in lines.splitlines())
    check("decision_rules files exist and hash right",
          all(got_shas.get(k.strip()) == v for k, v in uniq.items()))
    try:
        # The accepted E1-E4 admission (reviewer-sol-h3t2-20261027, no timestamp field) predates the freeze by
        # construction; E1-E4 was accepted 2026-10-27, so a valid freeze must postdate that day AND be in the past.
        frozen_at = datetime.fromisoformat(f["frozen_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        check("frozen_at postdates accepted E1-E4 (2026-10-27) and is not in the future",
              frozen_at >= datetime(2026, 10, 27) and frozen_at <= datetime.now())
    except Exception as e:  # noqa: BLE001
        check("frozen_at parseable: " + str(e)[:120], False)

    rows = [{"arm_id": x["arm_id"], "role": x["role"], "decision_rules": x["decision_rules"]} for x in learned]
    evidence = {"kind": "newperiod_g2_e5_freeze_evidence_v1",
                "checks_passed": not fails, "failures": fails,
                "actual_global_freeze": {"path": args.freeze_ref, "sha256": sha(frez_raw)},
                "admission_draft_sha256": sha(Q16.read_bytes()),
                "learned_roles": len(learned), "full_roles": len(f["arms"]),
                "frozen_at": f.get("frozen_at"),
                "learned_bindings_sha256": sha(encode(rows)),
                "author": "g2 lane driver check_e5_g2.py (metadata-only; asserts NOTHING — root attests)",
                "learned_rows": rows}
    text = json.dumps(evidence, sort_keys=True, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)
    print(f"E5 CHECK: {'PASS' if not fails else 'FAIL ' + str(fails)}  evidence sha256 {sha(text.encode())}",
          file=sys.stderr)
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
