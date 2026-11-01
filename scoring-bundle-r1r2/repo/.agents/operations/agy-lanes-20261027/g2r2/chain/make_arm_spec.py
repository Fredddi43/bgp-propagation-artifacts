#!/usr/bin/env python3
"""Author the frozen evaluation arm spec for the single R2 (mechanical derivation from the retention list).

Arms are derived exactly as the PINNED persistence runner derives them (private role_arm).
Reads only label-free files: the freeze, the binding extension decision, the frozen slice rule and issue-time tables.
Repetitions, alpha and bootstrap seed are the protocol constants (10000, 0.05, 1701) and are bound into the spec.
"""
import argparse
import json
import types
from pathlib import Path

from common import REPO, require, sha, write_new
import amend_wiring

PERSIST = REPO / ".agents/operations/newperiod-single-r2-persistence-20261024/runner.py"


def private_derivation(ev, freeze=None):
    """The persistence runner evaluates with a private copy whose role_arm ignores non-core baseline variants; the spec must be
    derived the same way or evaluate_new_period's check_arm_spec refuses (history/stable/... roles otherwise clash)."""
    module = types.ModuleType("r2_persistence_runner")
    module.__file__ = str(PERSIST)
    exec(compile(PERSIST.read_bytes(), str(PERSIST), "exec"), module.__dict__)
    if freeze is not None:   # amended freeze (frozen d30 retained failure): d60-only evaluator copy; a full freeze keeps `ev` as is
        ev = amend_wiring.evaluator_for(ev, freeze)
    count = module.components()["composition"].components()["count"]
    return count.private_primary(ev).derive_new_period_arms


def main(argv=None):
    from bgbench import forecast_custodian_eval as ev
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--extension-decision", type=Path, required=True)
    p.add_argument("--slice-rules", type=Path, required=True)
    p.add_argument("--issue-time-table", nargs=2, action="append", metavar=("DELTA", "PATH"), required=True)
    p.add_argument("--repetitions", type=int, default=10000)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    decision = json.loads(a.extension_decision.read_bytes())
    ev.evaluation_window(decision)  # refuses a non-binding decision or a wrong end date
    tables = {d: sha(path) for d, path in a.issue_time_table}
    require(set(tables) == {"30", "60"}, "issue-time tables of both horizons required")
    freeze = json.loads(a.freeze.read_bytes())
    spec = {"kind": "frozen_evaluation_arm_spec", "population": "new_period", "custody_spec_sha256": sha(a.freeze),
            "seed_pairing": "training_seed", "online_history": "history-knn-mean/matched/online",
            "arms": private_derivation(ev, freeze)(freeze),
            "slice_rules_sha256": sha(a.slice_rules), "issue_time_tables": tables,
            "extension_decision_sha256": sha(a.extension_decision), "repetitions": a.repetitions,
            "alpha": 0.05, "bootstrap_seed": 1701, "evaluation_end_exclusive": decision["evaluation_end_exclusive"]}
    digest = write_new(a.out, spec)
    print(json.dumps({"arm_spec": str(a.out.resolve()), "sha256": digest}))


if __name__ == "__main__":
    main()
