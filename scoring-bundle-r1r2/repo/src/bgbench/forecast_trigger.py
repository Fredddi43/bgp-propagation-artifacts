"""Online collector-agreement triggers with an explicit emission clock.

Unlike batch grouping, a trigger is emitted only when the required collector
evidence has arrived. Prefix/edge records are candidates, not confirmed attacks.
Source clocks must be labeled: historical first-seen tables support event-time
replay, while online use requires actual arrival timestamps and causal state.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
from pathlib import Path

from .forecast_protocol import utc


@dataclass(frozen=True)
class TriggerConfig:
    min_collectors: int = 2
    agreement_window_s: int = 300
    cooldown_s: int = 300
    clock: str = "event_time_replay"

    def __post_init__(self):
        if self.min_collectors < 1 or min(self.agreement_window_s, self.cooldown_s) < 0:
            raise ValueError("Invalid trigger parameters")
        if self.clock not in ("event_time_replay", "arrival_time"):
            raise ValueError("Unknown clock")


class CollectorAgreement:
    def __init__(self, config=TriggerConfig()):
        self.config = config
        self.evidence = {}
        self.last_fired = {}
        self.last_clock = None

    def push(self, record):
        kind = record["kind"]
        observed = utc(record["observed_at"])
        available = utc(record["arrival_at"]) if self.config.clock == "arrival_time" else observed
        if self.last_clock is not None and available < self.last_clock:
            raise ValueError("Input must be ordered by availability time")
        if available < observed:
            raise ValueError("Arrival precedes collector observation; resolve clock skew")
        self.last_clock = available
        if kind == "origin_change":
            key = (kind, str(record["prefix"]), int(record["new_origin"]))
        elif kind == "edge_candidate":
            key = (kind, int(record["a"]), int(record["b"]))
        else:
            raise ValueError(f"Unknown candidate kind: {kind}")
        cutoff = available - timedelta(seconds=self.config.agreement_window_s)
        evidence = self.evidence.get(key, {})
        for c, observations in list(evidence.items()):
            while observations and observations[0]["available"] < cutoff:
                observations.popleft()
            if not observations:
                del evidence[c]
        collector = str(record["collector"])
        # Retain every distinct observation until it expires. Later observations
        # remain valid after the first expires, but never add collector votes.
        observations = evidence.setdefault(collector, deque())
        observation = {"available": available, "observed": observed}
        if not observations or observations[-1] != observation:
            observations.append(observation)
        self.evidence[key] = evidence
        if len(evidence) < self.config.min_collectors:
            return None
        last = self.last_fired.get(key)
        if last is not None and available <= last + timedelta(seconds=self.config.cooldown_s):
            return None
        self.last_fired[key] = available
        first = min(e["observed"] for observations in evidence.values() for e in observations)
        token = json.dumps([key, available.isoformat()], separators=(",", ":"))
        result = {
            "trigger_id": "trigger-" + hashlib.sha256(token.encode()).hexdigest()[:24],
            "kind": kind, "trigger_at": available.isoformat(), "first_observed_at": first.isoformat(),
            "trigger_delay_s": (available - first).total_seconds(),
            "clock": self.config.clock, "collectors_at_trigger": sorted(evidence),
            "n_collectors_at_trigger": len(evidence), "event_key": list(key),
        }
        if kind == "origin_change":
            result.update(prefix=key[1], actor=key[2])
        else:
            result.update(a=key[1], b=key[2])
        return result


def replay(records, config=TriggerConfig()):
    trigger = CollectorAgreement(config)
    for record in records:
        result = trigger.push(record)
        if result is not None:
            yield result


def side_table_records(paths, kind):
    """Use only first-observation columns, never completed-bin counts or labels."""
    import polars as pl
    columns = (["ts", "collector", "prefix", "new_origin"] if kind == "origin_change"
               else ["first_ts", "collector", "a", "b"])
    time_col = columns[0]
    tables = [pl.read_parquet(path, columns=columns).with_columns(pl.col("collector").cast(pl.String)) for path in paths]
    if not tables:
        return
    table = pl.concat(tables, how="vertical_relaxed").sort(time_col, "collector")
    for row in table.iter_rows(named=True):
        yield {"kind": kind, "observed_at": row.pop(time_col), **row}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, action="append", required=True)
    p.add_argument("--kind", choices=["origin_change", "edge_candidate"], required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--min-collectors", type=int, default=2)
    p.add_argument("--window", type=int, default=300)
    p.add_argument("--cooldown", type=int, default=300)
    args = p.parse_args()
    config = TriggerConfig(args.min_collectors, args.window, args.cooldown)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with args.out.open("x") as out:
        for event in replay(side_table_records(args.input, args.kind), config):
            out.write(json.dumps(event) + "\n")
            count += 1
    receipt = {"config": config.__dict__, "triggers": count, "source_files": [str(x) for x in args.input],
               "clock_limit": "Historical side tables do not establish original message delivery time.",
               "candidate_limit": "Daily first-edge records cannot establish all raw-stream edge episodes.",
               "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest()}
    args.out.with_suffix(args.out.suffix + ".receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
