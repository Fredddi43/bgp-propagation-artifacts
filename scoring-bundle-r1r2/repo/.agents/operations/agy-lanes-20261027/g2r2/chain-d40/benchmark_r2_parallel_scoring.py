#!/usr/bin/env python3
"""Measured synthetic benchmark for the two r2_parallel_scoring adapters.

Representative large-candidate rows scored by the REAL pinned scorers, serial vs the fork parallel
adapter. Reports wall-clock speedup and honest memory: peak child RSS and the low-water mark of
system MemAvailable during each run (fork copy-on-write dirties pages as workers read the Python
list-of-floats inputs, so the workers' combined footprint grows with the worker count — measured, not
assumed). Runs ONLY here, on synthetic data; reads no labels, launches nothing on the cluster.

Machine note: this host is 16 cores / 20 GB. The target node is a 64-CPU / 1.95 TB allocation, so
absolute times and headroom differ; the SPEEDUP SHAPE and per-worker memory behaviour are what
transfer. --mode membership scores score_membership; --mode per-event-rows scores per_event_rows (the
earlier serial origin tail, which recomputes the ranking twice per event).

Usage:
  .venv/bin/python benchmark_r2_parallel_scoring.py [--mode membership|per-event-rows]
      [--events N] [--candidates C] [--workers 2,4,8] [--chunks 4] [--quick]
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "src" / "bgbench").is_dir())  # repo root, from performance/ or chain-d39-v2/
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from bgbench.forecast_retrospective_scoring import score_membership  # noqa: E402
from bgbench.forecast_custodian_eval import per_event_rows  # noqa: E402
import r2_parallel_scoring as P  # noqa: E402


def build_membership_case(n, candidates, seed=20261030):
    """Neural score_membership rows: probabilities as Python float lists (as from the JSON), committed
    decision consistent with the float64 comparison, one issue-time signature per event."""
    rng = np.random.default_rng(seed)
    predictions, events = [], []
    threshold = 0.5  # a real cell shares one global threshold with every row (rules enforce it)
    for i in range(n):
        cands = list(range(i * candidates + 1, i * candidates + 1 + candidates))
        seeds = cands[:3]
        probs = [1.0, 1.0, 1.0] + [float(x) for x in rng.random(candidates - 3)]
        predicted = sorted(set(seeds) | {c for c, p in zip(cands, probs) if p >= threshold})
        predictions.append(
            {
                "event_id": f"e{i:07d}",
                "candidate_asns": cands,
                "seed_asns": seeds,
                "predicted_asns": predicted,
                "threshold": threshold,
                "probabilities": probs,
            }
        )
        events.append(
            {
                "event_id": f"e{i:07d}",
                "asn": np.asarray(cands, dtype=np.int64),
                "seed_asns": np.asarray(seeds, dtype=np.int64),
                "target_asns": np.asarray(
                    sorted({*seeds, *[c for c in cands[3:] if c % 5 == 0]}), dtype=np.int64
                ),
                "history_signature": np.asarray(
                    np.log1p([4.0, 7.0, 10.0 + i % 3]), dtype=np.float64
                ),
            }
        )
    rules = {
        "global_threshold": 0.5,
        "slice_rule": {"variable": "early_growth", "cut": 3},
        "slice_threshold": 0.4,
        "remainder_threshold": 0.6,
    }
    return (predictions, events, rules)


def build_per_case(n, candidates, seed=20261030):
    """Neural matched per_event_rows rows: inputs/candidates matched, one abstention and one censored
    event every so often; committed decision and inputs consistent.

    Like build_membership_case this mirrors a REAL committed cell: ONE global decision threshold for
    the whole arm (the old fixture rotated 0.5..0.9 per row and recorded nothing — no committed cell
    ever produced such rows). per_event_rows itself does not police the threshold, so the fixture must
    be honest by construction: predicted_asns are recomputed from probabilities at that threshold."""
    rng = np.random.default_rng(seed)
    predictions, manifest, labels, inputs = [], [], {}, {}
    threshold = 0.5  # a real cell shares one global threshold with every row (rules enforce it)
    for i in range(n):
        eid = f"e{i:07d}"
        cands = list(range(i * candidates + 1, i * candidates + 1 + candidates))
        seeds = cands[:3]
        abstain = i % 41 == 0
        if abstain:
            predictions.append(
                {"event_id": eid, "seed_asns": seeds, "candidate_asns": [], "predicted_asns": []}
            )
            manifest.append({"event_id": eid, "input_status": "source_failure"})
        else:
            probs = [1.0, 1.0, 1.0] + [float(x) for x in rng.random(candidates - 3)]
            predicted = sorted(set(seeds) | {c for c, p in zip(cands, probs) if p >= threshold})
            predictions.append(
                {
                    "event_id": eid,
                    "seed_asns": seeds,
                    "candidate_asns": cands,
                    "predicted_asns": predicted,
                    "probabilities": probs,
                    "threshold": threshold,
                }
            )
            manifest.append({"event_id": eid})
            inputs[eid] = {"event_id": eid, "asn": cands, "seed_asns": seeds}
        target = sorted({*seeds, *[c for c in cands[3:] if c % 5 == 0]})
        labels[eid] = {
            "target_status": "censored" if i % 53 == 0 else "scorable",
            "target_asns": target,
        }
    return (predictions, manifest, labels, inputs)


def rss_kib(pid="self"):
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return -1


def mem_available_kib():
    with open("/proc/meminfo") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    return -1


class MemSampler(threading.Thread):
    """Records the low-water mark of MemAvailable while a run is in flight."""

    def __init__(self, interval=0.015):
        super().__init__(daemon=True)
        self.interval, self.stop_evt = interval, threading.Event()
        self.min_available = 1 << 62

    def run(self):
        while not self.stop_evt.is_set():
            self.min_available = min(self.min_available, mem_available_kib())
            time.sleep(self.interval)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.min_available = min(self.min_available, mem_available_kib())
        self.stop_evt.set()
        self.join(timeout=1.0)


def _fallback(v):
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, (set, frozenset)):
        return sorted(v)
    raise TypeError(type(v).__name__)


def canonical(rows):
    return json.dumps(
        rows, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_fallback
    )


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["membership", "per-event-rows"], default="membership")
    p.add_argument("--events", type=int, default=16000)
    p.add_argument("--candidates", type=int, default=600)
    p.add_argument("--workers", default="2,4,8")
    p.add_argument("--chunks", type=int, default=4)
    p.add_argument("--quick", action="store_true", help="tiny sizes, just to exercise the harness")
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args(argv)
    if a.quick:
        a.events, a.candidates = 4000, 120
    if a.out is None:
        a.out = HERE / f"benchmark-results-{a.mode.replace('-', '_')}.json"
    worker_counts = [int(w) for w in a.workers.split(",") if w.strip()]

    n_rows = a.events
    print(
        f"mode={a.mode}  building case: events={a.events} candidates={a.candidates} "
        f"-> ~{a.events * a.candidates / 1e6:.1f}M candidate elements"
    )
    t0 = time.perf_counter()
    if a.mode == "membership":
        case = build_membership_case(a.events, a.candidates)

        def serial_call():
            return score_membership(*case)

        def par_call(w):
            return P.parallel_score_membership(score_membership, *case, force=True, workers=w, chunks_per_worker=a.chunks)
    else:
        case = build_per_case(a.events, a.candidates)
        predictions, manifest, labels, inputs = case

        def serial_call():
            return per_event_rows(predictions, manifest, labels, baseline=False, inputs=inputs, candidates="matched")

        def par_call(w):
            return P.parallel_per_event_rows(per_event_rows, predictions, manifest, labels, baseline=False,
                                             inputs=inputs, candidates="matched", force=True, workers=w,
                                             chunks_per_worker=a.chunks)
    build_s = time.perf_counter() - t0
    parent_kib = rss_kib()
    total_kib = mem_available_kib()
    print(
        f"built in {build_s:.1f}s; parent VmRSS={parent_kib / 1e6:.2f} GiB; MemAvailable={total_kib / 1e6:.2f} GiB; "
        f"logical cores={os.cpu_count()} affinity={len(os.sched_getaffinity(0))}\n"
    )

    t_serial = time.perf_counter()
    reference = serial_call()
    serial_s = time.perf_counter() - t_serial
    ref_hash = canonical(reference)
    print(f"serial: {serial_s:8.2f}s  ({len(reference)} rows, {n_rows / serial_s:,.0f} events/s)")

    results = {
        "mode": a.mode,
        "host": {
            "cores": os.cpu_count(),
            "affinity": len(os.sched_getaffinity(0)),
            "mem_available_gib": round(total_kib / 1e6, 2),
            "python": sys.version.split()[0],
            "numpy": np.__version__,
        },
        "case": {
            "events": a.events,
            "candidates": a.candidates,
            "elements_m": round(a.events * a.candidates / 1e6, 2),
            "parent_rss_mib": round(parent_kib / 1024, 1),
            "rows_serial": len(reference),
        },
        "serial_seconds": round(serial_s, 3),
        "runs": [],
    }

    for w in worker_counts:
        avail_before = mem_available_kib()
        with MemSampler() as samp:
            t = time.perf_counter()
            out = par_call(w)
            wall = time.perf_counter() - t
        child_peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        ok = canonical(out) == ref_hash
        consumed = (avail_before - samp.min_available) / 1024 / 1024
        speedup = serial_s / wall
        row = {
            "workers": w,
            "seconds": round(wall, 3),
            "speedup": round(speedup, 2),
            "efficiency": round(speedup / w, 2),
            "events_per_s": round(n_rows / wall),
            "peak_child_rss_mib": round(child_peak / 1024, 1),
            "mem_available_low_gib": round(samp.min_available / 1e6, 2),
            "mem_consumed_gib": round(consumed, 2),
            "exact_equal_serial": bool(ok),
        }
        results["runs"].append(row)
        print(
            f"workers={w:>2}: {wall:7.2f}s  speedup={speedup:5.2f}x  eff={speedup / w:4.2f}  "
            f"peak_child_rss={child_peak / 1024:7.1f}MiB  consumed≈{consumed:4.2f}GiB  "
            f"min_avail={samp.min_available / 1e6:4.2f}GiB  exact={ok}"
        )
        if not ok:
            results["verdict"] = "FAIL: parallel output differs from serial — do not integrate"

    best = max(results["runs"], key=lambda r: r["speedup"]) if results["runs"] else None
    if best and best["speedup"] < 1.15:
        verdict = "NO meaningful speedup at this size on this host — report, do not integrate (per the brief)."
    elif best:
        verdict = (
            f"Best speedup {best['speedup']}x at {best['workers']} workers (efficiency {best['efficiency']}/worker). "
            f"Memory scales with workers via fork COW; watch the consumed-GB column."
        )
    else:
        verdict = "no runs"
    results["verdict"] = results.get("verdict", verdict)

    print("\nverdict:", verdict)
    a.out.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
