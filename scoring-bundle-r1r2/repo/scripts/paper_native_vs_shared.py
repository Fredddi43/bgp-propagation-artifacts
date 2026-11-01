#!/usr/bin/env python3
"""Native minus shared candidates of online history: paired AP difference with an interval (revision analysis).

Section 7.2 prints that the two history arms use the same score and that the native one reaches 0.029 AP more than the
shared one in R1 (a difference of arm means). This script gives that difference its paired interval, with the statistic
of scripts/paper_month_boundary.py (training seeds, then incident-day blocks, 10,000 repetitions, seed 1701; one seed per
history arm), on all eligible events, for R1 and R2 at 30 and 60 s. Descriptive, unadjusted, not part of a test family.
It reuses the hash-checked loaders of paper_month_boundary.py and computes nothing else.

Usage (repo root):
    .venv/bin/python -B scripts/paper_native_vs_shared.py \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --r2-scores <local copy of primary-scores.json> \
        --r2-report docs/paper/r2-report-20261030/primary.json \
        --out-json paper/generated/native_vs_shared.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_month_boundary as mb  # noqa: E402  (hash-checked R1/R2 loaders and the subset statistic)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("r1-report", "r1-per-event", "r1-arm-spec", "r1-manifest-30", "r1-manifest-60", "r2-scores", "r2-report",
                 "out-json"):
        p.add_argument("--" + name, required=True)
    args = p.parse_args()
    out = {"kind": "native_vs_shared_history_revision_analysis", "confirmatory": False, "replaces_published_values": False,
           "contrast": "online_history_native minus online_history (shared candidates), average precision",
           "statistic": "event-macro mean AP difference; paired training-seed then incident-day-block percentile bootstrap, "
                        "ordinary 95 %, unadjusted, descriptive (scripts/paper_month_boundary.py subset_contrast)",
           "repetitions": mb.REPS, "rng_seed": mb.SEED, "source_sha256": mb.sha(Path(__file__)), "results": {}}
    for period, loader in (("R1", mb.load_r1), ("R2", mb.load_r2)):
        arms, rows, _, provenance = loader(args)
        out["results"][period] = {"provenance": provenance}
        for d in mb.HORIZONS:
            r = mb.subset_contrast(arms["online_history_native"][d], arms["online_history"][d], rows[d], set(),
                                   mb.REPS, mb.SEED)
            out["results"][period][str(d)] = {k: r[k] for k in ("difference", "ci95", "eligible_events", "left_mean",
                                                                 "right_mean") if k in r}
            print(period, d, f"{r['difference']:+.4f}", [round(x, 4) for x in r["ci95"]], r["eligible_events"], flush=True)
    Path(args.out_json).write_text(json.dumps(out, indent=1) + "\n")
    print("wrote", args.out_json)


if __name__ == "__main__":
    main()
