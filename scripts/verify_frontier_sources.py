"""Independently reconstruct frontier membership from CAIDA and historical RoVista.

The public check binds released event/label tables and frontier evidence to the
successful private audit. Raw CAIDA/RoVista hashes remain recorded as provenance.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import polars as pl


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_year(data: Path, summaries: list[str]) -> dict:
    year = Path(summaries[0]).parent.name
    source_hashes, raw_hashes, evidence_hashes = {}, {}, {}

    def read(relative, category, parquet=True):
        path = data / relative
        category[relative] = sha(path)
        return pl.read_parquet(path) if parquet else json.loads(path.read_text())

    events = read(f"eventset/{year}/events.parquet", source_hashes)
    labels = read(f"eventset/{year}/rpki_validity.parquet", source_hashes)
    assert events["event_id"].n_unique() == events.height
    assert labels["event_id"].n_unique() == labels.height
    events = events.filter(pl.col("error").is_null()).join(
        labels.select("event_id", "validity"), on="event_id", how="left", validate="1:1")
    assert events["validity"].null_count() == 0
    events = events.filter(pl.col("set_final_2h").list.len() > 0).sort("event_id")
    rov = read("rpki/rovista/as_rov_series.parquet", raw_hashes).with_columns(pl.col("date").cast(pl.String))
    variants = []
    for relative in summaries:
        saved = read(relative, evidence_hashes, False)
        rows = read(str(Path(relative).with_suffix(".parquet")), evidence_hashes)
        assert rows["event_id"].n_unique() == rows.height, relative
        eligible = events
        if saved.get("only_reason"):
            eligible = eligible.filter(pl.col("reason") == saved["only_reason"])
        if saved.get("exclude_reason"):
            eligible = eligible.filter(pl.col("reason") != saved["exclude_reason"])
        assert set(rows["event_id"]) == set(eligible["event_id"]), (relative, "population")
        history = rov
        if saved.get("freeze_date"):
            history = history.filter(pl.col("date") <= saved["freeze_date"])
        if saved.get("min_total"):
            history = history.filter(pl.col("total") >= saved["min_total"])
        series = {}
        for (asn,), group in history.sort("asn", "date").group_by("asn", maintain_order=True):
            series[int(asn)] = (group["date"].to_list(), group["ratio"].to_list())
        variants.append({"file": relative, "saved": saved, "rows": {r["event_id"]: r for r in rows.to_dicts()},
                         "series": series, "date": None, "future_counts": defaultdict(lambda: [0, 0])})
    month, neighbours = None, {}
    for event in events.iter_rows(named=True):
        eid = event["event_id"]
        next_month = eid[:6]
        if next_month != month:
            edges = read(f"graphs/{next_month}01.rel.parquet", raw_hashes)
            neighbours = defaultdict(set)
            for u, v in edges.select("u", "v").iter_rows():
                neighbours[int(u)].add(int(v))
                neighbours[int(v)].add(int(u))
            month = next_month
        carriers = set(map(int, event["set_final_2h"]))
        frontier = set()
        for asn in carriers:
            frontier.update(neighbours.get(asn, ()))
        frontier.difference_update(carriers)
        day = f"{eid[:4]}-{eid[4:6]}-{eid[6:8]}"
        for variant in variants:
            if eid not in variant["rows"]:
                continue
            if variant["date"] != day:
                measured, enforcing, future = set(), set(), set()
                for asn, (dates, ratios) in variant["series"].items():
                    index = bisect_right(dates, day) - 1
                    if index < 0:
                        future.add(asn)
                    else:
                        measured.add(asn)
                        if ratios[index] >= variant["saved"]["threshold"]:
                            enforcing.add(asn)
                variant.update(date=day, measured=measured, enforcing=enforcing, future=future)
            row = variant["rows"][eid]
            expected = {"carriers": len(carriers), "frontier": len(frontier)}
            for name, members in (("carriers", carriers), ("frontier", frontier)):
                expected[name + "_measured"] = len(members & variant["measured"])
                expected[name + "_enforcing"] = len(members & variant["enforcing"])
            assert row["validity"] == event["validity"] and row["split"] == event["split"], (variant["file"], eid, "labels")
            for key, value in expected.items():
                assert row[key] == value, (variant["file"], eid, key, row[key], value)
            cm, fm = expected["carriers_measured"], expected["frontier_measured"]
            if cm and fm:
                # Odds with a half-count in each cell, computed directly.
                ce, fe = expected["carriers_enforcing"], expected["frontier_enforcing"]
                odds = np.log((fe + .5) * (cm - ce + .5) / ((fm - fe + .5) * (ce + .5)))
                assert np.isclose(row["log_odds"], odds, atol=1e-12), (variant["file"], eid, "odds")
            else:
                assert row["log_odds"] is None, (variant["file"], eid, "undefined odds")
            counts = variant["future_counts"][event["validity"]]
            counts[0] += len(carriers & variant["future"])
            counts[1] += len(frontier & variant["future"])
    for variant in variants:
        for validity, (carrier_future, frontier_future) in variant["future_counts"].items():
            saved = variant["saved"]["by_validity"][validity]
            assert saved["future_only_carrier_observations_excluded"] == carrier_future
            assert saved["future_only_frontier_observations_excluded"] == frontier_future
    for hashes in (source_hashes, raw_hashes, evidence_hashes):
        assert all(sha(data / name) == digest for name, digest in hashes.items()), "inputs changed during audit"
    return {"source_sha256": source_hashes, "raw_source_sha256": raw_hashes, "evidence_sha256": evidence_hashes,
            "variants": [{"file": v["file"], "rows": len(v["rows"])} for v in variants]}


def verify_public(data: Path, proof_path: Path, summaries: list[str]) -> dict:
    proof = json.loads(proof_path.read_text())
    assert proof["status"] == "passed" and proof["mode"] == "private_source_audit"
    assert sorted(v["file"] for v in proof["variants"]) == sorted(summaries), "frontier audit variant mismatch"
    required_evidence = set(summaries) | {str(Path(p).with_suffix(".parquet")) for p in summaries}
    assert set(proof["evidence_sha256"]) == required_evidence
    required_sources = {f"eventset/{Path(p).parent.name}/{name}" for p in summaries for name in ("events.parquet", "rpki_validity.parquet")}
    assert set(proof["source_sha256"]) == required_sources
    for field in ("source_sha256", "evidence_sha256"):
        for relative, digest in proof[field].items():
            assert sha(data / relative) == digest, ("frontier audit hash mismatch", relative)
    return {"status": "passed", "variants": len(summaries), "rows": sum(v["rows"] for v in proof["variants"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", type=Path)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--wait-for-marker", type=Path, action="append", default=[])
    args = ap.parse_args()
    while not all(p.is_file() for p in args.wait_for_marker):
        time.sleep(10)
    summaries = json.loads(args.manifest.read_text())["frontier_tables"]
    assert summaries and len(summaries) == len(set(summaries))
    args.output.unlink(missing_ok=True)
    by_year = defaultdict(list)
    for relative in summaries:
        by_year[Path(relative).parent.name].append(relative)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(audit_year, args.data, group) for group in by_year.values()]
        results = [future.result() for future in futures]
    proof = {"status": "passed", "mode": "private_source_audit", "variants": [],
             "source_sha256": {}, "raw_source_sha256": {}, "evidence_sha256": {},
             "manifest_sha256": sha(args.manifest)}
    for result in results:
        proof["variants"].extend(result["variants"])
        for field in ("source_sha256", "raw_source_sha256", "evidence_sha256"):
            proof[field].update(result[field])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    pending = args.output.with_suffix(".pending.json")
    pending.write_text(json.dumps(proof, indent=2) + "\n")
    pending.replace(args.output)
    print(json.dumps(verify_public(args.data, args.output, summaries)), flush=True)


if __name__ == "__main__":
    main()
