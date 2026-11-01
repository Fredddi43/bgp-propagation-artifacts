"""Immutable forecasting split manifests; never inspect prediction outcomes.

This module uses onset/actor/source metadata only. Source target completeness is
recorded separately from input-time eligibility, and every exclusion is retained.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path


def utc(value) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError(f"Timestamp has no timezone: {value}")
    return result.astimezone(timezone.utc)


# Issue-time input availability (docs/paper/forecasting-improvement-20261017/WHOLE-SECOND-CUTOFF.md, rule A).
# RIS collectors stamp whole seconds: a record stamped S arrived somewhere in [S, S + 1 s), so it is available
# to a forecaster only from S + 1 s. RouteViews stamps microseconds and is available at its stamp. The two lists
# are the reference panel, classified from the measured 2025 development data (0 RIS rows with sub-second digits,
# 0 RouteViews rows without); check_timestamp_precision fails closed if that ever stops holding or an
# unclassified collector appears. Inputs use availability time; labels and targets keep the raw first_seen.
WHOLE_SECOND_COLLECTORS = ("rrc00", "rrc01", "rrc03", "rrc12", "rrc15", "rrc20", "rrc25")
MICROSECOND_COLLECTORS = ("route-views.linx", "route-views2", "route-views3")
WHOLE_SECOND_ALLOWANCE = timedelta(seconds=1)
INPUT_CUTOFF_RULE_ID = "availability_v1_whole_second_plus_1s"
INPUT_CUTOFF_RULE = {
    "id": INPUT_CUTOFF_RULE_ID,
    "rule": "whole-second sources admitted iff ts + 1 s <= issue; microsecond sources iff ts <= issue",
    "whole_second_collectors": list(WHOLE_SECOND_COLLECTORS),
    "microsecond_collectors": list(MICROSECOND_COLLECTORS),
    "labels": "raw first_seen, unchanged",
}


def timestamp_precision(collector: str) -> str:
    if collector in WHOLE_SECOND_COLLECTORS:
        return "whole_second"
    if collector in MICROSECOND_COLLECTORS:
        return "microsecond"
    raise ValueError(f"No declared timestamp precision for collector {collector!r}; classify it before use")


def available_at(ts: datetime, collector: str) -> datetime:
    """Earliest time a record stamped ``ts`` by ``collector`` can have reached a live forecaster."""
    if timestamp_precision(collector) == "whole_second":
        if ts.microsecond:
            raise ValueError(f"Whole-second collector {collector} has a sub-second timestamp {ts.isoformat()}; "
                             "the parser changed and the availability rule must be revisited")
        return ts + WHOLE_SECOND_ALLOWANCE
    return ts


def available_at_expr(ts_column: str = "ts", collector_column: str = "collector"):
    """Polars form of ``available_at``; call ``check_timestamp_precision`` on the frame first."""
    import polars as pl
    whole = pl.col(collector_column).is_in(list(WHOLE_SECOND_COLLECTORS))
    return pl.col(ts_column) + pl.when(whole).then(pl.duration(seconds=1)).otherwise(pl.duration(seconds=0))


def check_timestamp_precision(frame, ts_column: str = "ts", collector_column: str = "collector"):
    """Guard: every collector is classified and no whole-second collector carries sub-second digits."""
    import polars as pl
    if frame.is_empty():
        return frame
    unknown = set(frame[collector_column].unique().to_list()) - set(WHOLE_SECOND_COLLECTORS) - set(MICROSECOND_COLLECTORS)
    if unknown:
        raise ValueError(f"No declared timestamp precision for collectors {sorted(map(str, unknown))}")
    bad = frame.filter(pl.col(collector_column).is_in(list(WHOLE_SECOND_COLLECTORS))
                       & (pl.col(ts_column).dt.nanosecond() != 0))
    if bad.height:
        raise ValueError(f"{bad.height} whole-second collector rows have sub-second {ts_column} "
                         f"(e.g. {bad.row(0, named=True)}); the parser changed and the availability rule must be revisited")
    return frame


def admit_available(frame, issue_time, ts_column: str = "ts", collector_column: str = "collector"):
    """Rows available at ``issue_time`` under the declared rule (guarded); a pure row filter."""
    import polars as pl
    check_timestamp_precision(frame, ts_column, collector_column)
    return frame.filter(available_at_expr(ts_column, collector_column) <= pl.lit(issue_time))


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class SplitWindows:
    train_start: str
    validation_start: str
    test_start: str
    test_end: str

    def boundaries(self):
        values = tuple(utc(getattr(self, k)) for k in ("train_start", "validation_start", "test_start", "test_end"))
        if any(a >= b for a, b in zip(values, values[1:])):
            raise ValueError("Split boundaries must be strictly increasing")
        return values


def manifest(rows, windows: SplitWindows, *, protocol: str, delta_s: int,
             graph_root: Path, family: str, incident_gap_s: int = 300,
             availability_delay_s: int = 0, locked_test: bool = False,
             history_feature_indices=(10,), source_receipts=None):
    """Group consecutive same-actor onsets, purge crossing groups and immature labels.

    Gap grouping uses metadata across the full declared input, so midnight does
    not split one burst. It is an evaluation grouping, never a model feature.
    """
    start, val, test, end = windows.boundaries()
    if delta_s <= 0 or availability_delay_s < 0 or incident_gap_s < 0:
        raise ValueError("Invalid time parameter")
    by_actor = defaultdict(list)
    seen = set()
    source_failures = []
    for source in rows:
        eid = str(source["event_id"])
        if eid in seen:
            raise ValueError(f"Duplicate event: {eid}")
        seen.add(eid)
        row = dict(source)
        if row.get("error"):
            source_failures.append({"event_id": eid, "reasons": ["source_replay_error"],
                                    "source_error": str(row["error"])})
            continue
        row["onset"] = utc(row.get("onset", row.get("t0_obs")))
        actor = row.get("actor", row.get("a", row.get("new_origin")))
        if actor is None:
            raise ValueError(f"Missing actor metadata for incident grouping: {eid}")
        row["actor"] = str(actor)
        by_actor[(family, str(actor))].append(row)
    groups = []
    for key, events in sorted(by_actor.items()):
        current = []
        for row in sorted(events, key=lambda x: (x["onset"], x["event_id"])):
            if current and (row["onset"] - current[-1]["onset"]).total_seconds() > incident_gap_s:
                groups.append((key, current))
                current = []
            current.append(row)
        if current:
            groups.append((key, current))

    def split(t):
        if start <= t < val:
            return "train"
        if val <= t < test:
            return "validation"
        if test <= t < end:
            return "test"
        return "outside"

    included, excluded = [], []
    for key, group in groups:
        incident_id = digest([*key, group[0]["event_id"], group[0]["onset"].isoformat()])[:24]
        splits = {split(r["onset"]) for r in group}
        crosses = len(splits) > 1
        for row in group:
            sp = split(row["onset"])
            onset = row["onset"]
            maturity = utc(row["label_available_at"]) if row.get("label_available_at") else onset + timedelta(seconds=7200 + availability_delay_s)
            if maturity < onset + timedelta(hours=2):
                raise ValueError(f"Label precedes target endpoint: {row['event_id']}")
            item = {
                "event_id": row["event_id"], "split": sp, "onset": onset.isoformat(),
                "actor": row["actor"], "incident_id": incident_id,
                "issue_time": (onset + timedelta(seconds=delta_s)).isoformat(),
                "label_available_at": maturity.isoformat(),
                "label_availability_basis": "recorded" if row.get("label_available_at") else "target_endpoint_plus_declared_delay",
                "graph_path": str(graph_root / f"{row['event_id']}.pt"),
            }
            reasons = []
            if sp == "outside":
                reasons.append("outside_split_window")
            if crosses:
                reasons.append("incident_crosses_split_boundary")
            if sp == "train" and maturity > val:
                reasons.append("training_label_not_mature_at_validation")
            if sp == "validation" and maturity > test:
                reasons.append("validation_label_not_mature_at_test")
            if row.get("input_eligible") is False:
                reasons.append("input_time_ineligible")
            item["label_complete"] = row.get("label_complete")
            item["observation_lag_s"] = row.get("observation_lag_s")
            # Missing later labels are retained, not silently called zero growth.
            if reasons:
                excluded.append(item | {"reasons": reasons})
            else:
                included.append(item)
    included.sort(key=lambda r: (r["onset"], r["event_id"]))
    excluded.sort(key=lambda r: (r["onset"], r["event_id"]))
    result = {
        "schema_version": 1, "protocol": protocol, "locked_test": locked_test,
        "family": family, "delta_s": delta_s, "target_horizon_s": 7200,
        "windows": windows.__dict__, "history_feature_indices": list(history_feature_indices),
        "incident_grouping": {"key": "family_and_actor", "consecutive_onset_gap_s": incident_gap_s},
        "availability_delay_s": availability_delay_s,
        "source_receipts": source_receipts or {}, "events": included, "excluded": excluded,
        "source_failures": sorted(source_failures, key=lambda r: r["event_id"]),
        "source_row_count": len(seen),
        "counts": dict(Counter(r["split"] for r in included)),
        "independent_incidents": {sp: len({r["incident_id"] for r in included if r["split"] == sp})
                                  for sp in ("train", "validation", "test")},
    }
    result["manifest_sha256"] = digest(result)
    return result


def write_manifest(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # A frozen manifest can never be silently replaced by a rerun.
    with path.open("x") as out:
        json.dump(data, out, indent=2, allow_nan=False)
        out.write("\n")


def read_metadata(paths):
    import polars as pl
    rows, receipts = [], {}
    names = ["event_id", "t0_obs", "onset", "actor", "a", "new_origin",
             "label_available_at", "input_eligible", "label_complete", "error", "observation_lag_s"]
    for path in paths:
        path = Path(path)
        receipts[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        schema = pl.read_parquet_schema(path)
        rows.extend(pl.read_parquet(path, columns=[n for n in names if n in schema]).to_dicts())
    return rows, receipts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--events", action="append", required=True)
    p.add_argument("--graphs", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--protocol", required=True)
    p.add_argument("--family", default="leak")
    p.add_argument("--delta", type=int, default=30)
    p.add_argument("--train-start", required=True)
    p.add_argument("--validation-start", required=True)
    p.add_argument("--test-start", required=True)
    p.add_argument("--test-end", required=True)
    p.add_argument("--availability-delay", type=int, default=0)
    p.add_argument("--locked-test", action="store_true")
    args = p.parse_args()
    rows, receipts = read_metadata(args.events)
    win = SplitWindows(args.train_start, args.validation_start, args.test_start, args.test_end)
    data = manifest(rows, win, protocol=args.protocol, delta_s=args.delta, graph_root=args.graphs,
                    family=args.family, availability_delay_s=args.availability_delay,
                    locked_test=args.locked_test, source_receipts=receipts)
    write_manifest(args.out, data)
    print(json.dumps({k: data[k] for k in ("manifest_sha256", "counts", "independent_incidents")}))


if __name__ == "__main__":
    main()
