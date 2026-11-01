#!/usr/bin/env python3
"""The single R2: one label opening, 10000 repetitions, seed 1701, alpha 0.05, one attempt.

Refuses unless root's go file exists. All label-free checks, the one-time marker and the access log are inside
bgbench.forecast_custodian_eval.evaluate_new_period (unchanged). Writes the report and a run receipt; never retries.
"""
import argparse
import json
from pathlib import Path

from common import GO_FILE, require, sha, write_new


def main(argv=None):
    from bgbench.forecast_custodian_eval import evaluate_new_period
    from custodian_access_log import log_read
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seal", type=Path, required=True)
    p.add_argument("--arm-spec", type=Path, required=True)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--extension-decision", type=Path, required=True)
    p.add_argument("--slice-rules", type=Path, required=True)
    p.add_argument("--issue-time-table", nargs=2, action="append", metavar=("DELTA", "PATH"), required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--repetitions", type=int, default=10000)
    p.add_argument("--go-file", type=Path, default=GO_FILE)
    a = p.parse_args(argv)
    require(a.go_file.is_file() and a.go_file.stat().st_size > 0, f"root go file {a.go_file} missing: R2 not authorized")
    require(a.repetitions == 10000 or a.go_file != GO_FILE, "R2 uses 10000 repetitions")
    require(not a.out.exists(), "report already exists: one attempt only")
    tables = {d: {"path": path, "sha256": sha(path)} for d, path in a.issue_time_table}
    receipt = {"kind": "r2_run_receipt", "go_file_sha256": sha(a.go_file), "seal_sha256": sha(a.seal),
               "labels_sha256": sha(a.labels), "arm_spec_sha256": sha(a.arm_spec), "repetitions": a.repetitions,
               "bootstrap_seed": 1701, "alpha": 0.05, "attempt": 1}
    write_new(a.out.with_name(a.out.stem + ".attempt.json"), receipt)  # a second attempt fails here
    report = evaluate_new_period(
        a.seal, receipt["seal_sha256"], a.arm_spec, receipt["arm_spec_sha256"], a.labels, receipt["labels_sha256"],
        a.out, extension_decision_path=a.extension_decision, expected_extension_decision_sha256=sha(a.extension_decision),
        slice_rules_path=a.slice_rules, expected_slice_rules_sha256=sha(a.slice_rules), issue_time_tables=tables,
        repetitions=a.repetitions, access_log=lambda path, purpose: log_read(path, purpose))
    done = dict(receipt, report=str(a.out.resolve()), report_sha256=sha(a.out), population=report["population"],
                primary_family_size=report["families"]["primary_ap"]["holm_family_size"])
    write_new(a.out.with_name(a.out.stem + ".complete.json"), done)
    print(json.dumps(done))


if __name__ == "__main__":
    main()
