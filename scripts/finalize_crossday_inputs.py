"""Prepare and publish a complete, isolated cross-midnight repair snapshot.

The default waits for all task reports, merges and compares, then stops for
inspection. --publish performs the coordinated source/table publication and
refreshes summaries using already validated historical labels. It never writes
the original archive trees.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path)
    ap.add_argument("--repair-root", type=Path, help="Use an immutable final repair view instead of the original repair tree")
    ap.add_argument("--publish", action="store_true")
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--leak-only", action="store_true", help="Freeze the complete 2023–2025 leak cohort first")
    scope.add_argument("--forecast-only", action="store_true", help="Freeze complete 2024 origin/withdrawal inputs for remaining models")
    args = ap.parse_args()
    run = args.run.resolve()
    code = run / "code"
    repair = (args.repair_root or run / "crossday-repair").resolve()
    if not repair.is_relative_to(run):
        raise ValueError("Repair root must remain inside the isolated correction run")
    plan_file = run / "crossday-repair-plan.json"
    plan = json.loads(plan_file.read_text())
    selected = [e for e in plan["events"].values()
                if (not args.leak_only or e["tag"] == "leak" and e["year"] in (2023, 2024, 2025))
                and (not args.forecast_only or e["year"] == 2024 and e["tag"] in ("", "withdrawal"))]
    task_ids = {i for event in selected for i in event["tasks"]}
    stem = "-leak-2023-2025" if args.leak_only else "-forecast-2024" if args.forecast_only else ""
    filters = (["--years", "2023", "2024", "2025", "--tags", "leak", "--report-stem", "leak-2023-2025"] if args.leak_only else
               ["--years", "2024", "--tags", "origin", "withdrawal", "--report-stem", "forecast-2024"] if args.forecast_only else [])
    review_file = run / f"crossday{stem}-review-ready.json"
    changes_file = repair / f"input-changes{stem}.json"
    merge_file = repair / f"merge{stem}.json"
    env = {**os.environ, "BGBENCH_DATA_ROOT": str(run / "data"),
           "BGBENCH_WORK_ROOT": str(run / "work"), "PYTHONPATH": str(code / "src"),
           "POLARS_MAX_THREADS": os.environ.get("POLARS_MAX_THREADS", "2"), "OPENBLAS_NUM_THREADS": "1"}
    logs = run / "logs" / f"crossday-finalize{stem}"
    logs.mkdir(parents=True, exist_ok=True)

    def command(label, script, *arguments):
        with (logs / (label + ".log")).open("w") as stream:
            subprocess.run([sys.executable, str(code / "scripts" / script), *map(str, arguments)],
                           cwd=code, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
        print(json.dumps({"finished": label}), flush=True)

    if not args.publish:
        while True:
            present = {int(p.stem) for p in (repair / "tasks").glob("*.json")}
            missing = task_ids - present
            print(json.dumps({"task_reports": len(present), "pending": len(missing)}), flush=True)
            if not missing:
                break
            time.sleep(30)
        command("merge", "repair_crossday_replays.py", "merge", "--plan", plan_file,
                "--output", repair, "--merge-workers", 16, "--exclude-incomplete", *filters)
        merged = json.loads(merge_file.read_text())
        if len(merged) != len(selected) or any(r["status"] not in ("merged", "excluded") for r in merged):
            raise ValueError("Repair is not complete; publication is prohibited")
        command("compare", "repair_crossday_replays.py", "compare", "--plan", plan_file, "--output", repair, *filters)
        review_file.write_text(json.dumps({
            "events": len(merged), "merged": sum(r["status"] == "merged" for r in merged),
            "excluded": sum(r["status"] == "excluded" for r in merged),
            "changes_sha256": hashlib.sha256(changes_file.read_bytes()).hexdigest()}, indent=2))
        return

    review = json.loads(review_file.read_text())
    if review["changes_sha256"] != hashlib.sha256(changes_file.read_bytes()).hexdigest():
        raise ValueError("Input comparison changed after preparation")
    if not args.leak_only and not args.forecast_only:
        command("verify-archive-boundaries-pre", "verify_archive_boundaries.py", "pre", run,
                "--repair-root", repair)
        boundary = json.loads((run / "boundary-prepublication-verification.json").read_text())
        if boundary.get("status") != "passed":
            raise ValueError("Archive boundary verification has not passed")
    command("publish-overlay", "replay_overlay.py", "publish", "--overlay", run / "replay-overlays",
            "--repair", repair, "--report", merge_file)
    command("publish-tables", "repair_crossday_replays.py", "publish", "--plan", plan_file, "--output", repair, *filters)
    followup_args = (["--years", "2023", "2024", "2025", "--tags", "leak"] if args.leak_only else
                     ["--years", "2024", "--tags", "origin", "withdrawal"] if args.forecast_only else [])
    command("exclude-incomplete-followup", "exclude_incomplete_followup.py", *followup_args,
            "--report", run / f"followup-exclusions{stem or '-all'}.json")
    if not args.leak_only:
        def validity_summaries(year):
            command(f"validity-summary-{year}", "rpki_validity_events.py", year, "--reuse-validation")
            command(f"validity-summary-paper-{year}", "rpki_validity_events.py", year, "--reuse-validation",
                    "--exclude-reason", "rpki_invalid_sample", "--suffix", "_labelled")
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(validity_summaries, [2024] if args.forecast_only else range(2022, 2027)))
    published_tables = ({f"{y}_leak" for y in (2023, 2024, 2025)} if args.leak_only
                        else {"2024", "2024_withdrawal"} if args.forecast_only
                        else {str(y) + suffix for y in range(2022, 2027)
                              for suffix in ("", "_leak", "_withdrawal")})
    # PCH and paired-transition tables have separate producers and completion
    # proofs. Their later refresh must not invalidate this source publication.
    hashes = {}
    for table in sorted(published_tables):
        p = run / "data" / "eventset" / table / "events.parquet"
        hashes[str(p.relative_to(run / "data"))] = hashlib.sha256(p.read_bytes()).hexdigest()
    marker = ("crossday-leak-2023-2025-complete.json" if args.leak_only else
              "forecast-origin-withdrawal-complete.json" if args.forecast_only else "crossday-source-complete.json")
    boundary_binding = {}
    if not args.leak_only and not args.forecast_only:
        command("verify-archive-boundaries", "verify_archive_boundaries.py", "final", run,
                "--repair-root", repair)
        boundary_path = run / "boundary-source-verification.json"
        boundary = json.loads(boundary_path.read_text())
        if boundary.get("status") != "passed" or boundary.get("published_event_tables_sha256") != hashes:
            raise ValueError("Published tables differ from archive boundary proof")
        boundary_binding["boundary_verification_sha256"] = hashlib.sha256(boundary_path.read_bytes()).hexdigest()
    (run / marker).write_text(json.dumps({
        **review, **boundary_binding, "repair_root": str(repair.relative_to(run)), "event_tables_sha256": hashes,
        "historical_validation": "reused unchanged prefix/origin/date labels"}, indent=2))


if __name__ == "__main__":
    main()
