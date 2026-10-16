"""Verify a narrow completion-preserving fill of four redundant ASN counts.

Private mode compares retained full input snapshots. Public mode reconstructs
those exact decoded tables from released final data plus original count columns.
No other value change is accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import polars as pl

COLUMNS = ["asns_d30s", "asns_d1m", "asns_d5m", "asns_d15m"]
TRANSFORMATION = "fill_missing_early_asn_counts_from_sets_v1"
BRIDGE_PATH = "analysis/derived-count-fill-bridge.json"
PROOF_PATH = "analysis/derived-count-fill-verification.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hash(table):
    return hashlib.sha256(table.sort("event_id").select(sorted(table.columns)).write_json().encode()).hexdigest()


def verify_tables(before, after, changed=None):
    assert before["event_id"].n_unique() == before.height
    assert after["event_id"].n_unique() == after.height
    before, after = before.sort("event_id"), after.sort("event_id")
    assert before["event_id"].to_list() == after["event_id"].to_list(), "changed event population"
    assert set(before.columns) == set(after.columns), "changed table columns"
    others = sorted(set(before.columns) - set(COLUMNS))
    assert before.select(others).equals(after.select(others)), "changed non-count values"
    actual_changes = {}
    for column in COLUMNS:
        horizon = "set_" + column.removeprefix("asns_")
        old, new = before[column], after[column]
        wanted = before[horizon].list.len()
        usable = before["error"].is_null()
        assert (old.is_null() | old.eq_missing(wanted)).all(), (column, "old non-null count disagrees with set")
        assert ((~usable) | (new.is_not_null() & wanted.is_not_null() & new.eq_missing(wanted))).all(), (column, "new count not materialized")
        assert (usable | old.eq_missing(new)).all(), (column, "changed excluded row")
        assert (old.is_null() | old.eq_missing(new)).all(), (column, "changed known count")
        actual_changes[column] = before.filter(~old.eq_missing(new))["event_id"].to_list()
    if changed is not None:
        assert set(changed) == set(COLUMNS)
        assert all(sorted(changed[c]) == actual_changes[c] for c in COLUMNS), "changed-row manifest mismatch"
    return actual_changes


def verify_bridge(data: Path, bridge_path: Path, proof_path: Path, private_run: Path | None = None, boundary_tables=None):
    bridge = json.loads(bridge_path.read_text())
    assert bridge["schema_version"] == 1 and bridge["transformation"] == TRANSFORMATION
    records = bridge["tables"]
    assert records and len({record["path"] for record in records}) == len(records)
    previous = None if private_run else json.loads(proof_path.read_text())
    if previous:
        assert previous["status"] == "passed" and previous["mode"] == "private_source_audit"
        assert previous["evidence_sha256"][BRIDGE_PATH] == sha(bridge_path), "bridge proof hash mismatch"
    sources, originals, checked = {}, {}, []
    if private_run:
        marker = private_run / bridge["source_completion_marker"]
        marker_hash = bridge.get("source_completion_marker_sha256", bridge.get("source_completion_sha256"))
        assert marker_hash is not None and sha(marker) == marker_hash, "completion marker changed"
        originals[bridge["source_completion_marker"]] = marker_hash
    for record in records:
        assert record["columns"] == COLUMNS
        path, counts_path = data / record["path"], data / record["before_counts_path"]
        published, counts = pl.read_parquet(path), pl.read_parquet(counts_path)
        after = (boundary_tables or {}).get(record["path"], published)
        assert after.height == record["rows"]
        assert counts["event_id"].n_unique() == counts.height == after.height
        assert set(counts.columns) == {"event_id", *COLUMNS}
        assert content_hash(counts) == record["before_counts_content_sha256"], "original count sidecar changed"
        assert set(counts["event_id"]) == set(after["event_id"])
        assert set(record["before_columns"]) == set(after.columns)
        before = after.drop(COLUMNS).join(counts, on="event_id", how="left", validate="1:1").select(record["before_columns"])
        assert content_hash(before) == record["before_content_sha256"], "reconstructed original content differs"
        assert content_hash(after) == record["after_content_sha256"], "current content differs from bridge"
        changes = verify_tables(before, after, record["changed_event_ids_by_column"])
        for relative in (record["path"], record["before_counts_path"]):
            sources[relative] = sha(data / relative)
            if previous:
                assert previous["source_sha256"].get(relative) == sources[relative], ("released source hash mismatch", relative)
        if private_run:
            original_path = private_run / record["before_path"]
            assert sha(original_path) == record["before_sha256"]
            # A later publication may reencode the same decoded table. The
            # migration-time byte hash stays in the bridge; content equality
            # above plus this proof's current byte hash binds the final input.
            assert sha(counts_path) == record["before_counts_sha256"]
            original = pl.read_parquet(original_path)
            assert content_hash(original) == record["before_content_sha256"]
            verify_tables(original, after, changes)
            assert original.select(sorted(original.columns)).sort("event_id").equals(before.select(sorted(before.columns)).sort("event_id"))
            originals[record["before_path"]] = record["before_sha256"]
        checked.append({"path": record["path"], "rows": after.height,
                        "before_content_sha256": record["before_content_sha256"],
                        "after_content_sha256": record["after_content_sha256"],
                        "published_content_sha256": content_hash(published),
                        "changed_counts": {key: len(value) for key, value in changes.items()}})
    if previous:
        assert set(previous["source_sha256"]) == set(sources)
    result = {"status": "passed", "mode": "private_source_audit", "transformation": TRANSFORMATION,
              "tables": checked, "source_sha256": sources, "original_source_sha256": originals,
              "evidence_sha256": {BRIDGE_PATH: sha(bridge_path)}}
    if private_run:
        assert all(sha(data / path) == digest for path, digest in sources.items()), "inputs changed during audit"
        assert all(sha(private_run / path) == digest for path, digest in originals.items()), "originals changed during audit"
        proof_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = proof_path.with_suffix(".pending.json")
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.replace(proof_path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--private-run", type=Path)
    parser.add_argument("--boundary-bridge",action="store_true")
    parser.add_argument("--wait-for-marker", type=Path, action="append", default=[])
    args = parser.parse_args()
    while not all(path.is_file() for path in args.wait_for_marker):
        time.sleep(10)
    if args.private_run:
        args.proof.unlink(missing_ok=True)
    boundary_tables=None
    if args.boundary_bridge:
        from boundary_input_bridge import restore_table
        assert args.private_run is not None
        boundary=json.loads((args.private_run/"boundary-input-bridge.json").read_text())
        boundary_proof=json.loads((args.private_run/"boundary-input-verification.json").read_text())
        assert boundary_proof["status"]=="passed"
        assert boundary_proof["evidence_sha256"]["analysis/boundary-input-bridge.json"]==sha(args.private_run/"boundary-input-bridge.json")
        boundary_tables={r["path"]:restore_table(pl.read_parquet(args.data/r["path"]),r) for r in boundary["tables"]}
    result = verify_bridge(args.data, args.bridge, args.proof, args.private_run,boundary_tables)
    print(json.dumps({"status": result["status"], "tables": len(result["tables"])}), flush=True)
