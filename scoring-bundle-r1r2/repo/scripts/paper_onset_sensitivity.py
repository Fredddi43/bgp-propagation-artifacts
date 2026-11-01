"""Onset-proximity sensitivity of the RPKI-class persistence floors (review round 1, Codex W1).

The replay onset of an origin change is the first observation of the new origin in a window that starts one hour
before the identifier. For valid origins it is often far earlier than the identifier (median -700 to -1,800 s),
so the 30-s set can precede the identified change. This repeats the class floors of the catalogue population on
events whose observed onset is at most 60 s before the identifier (the clean-onset rule of the leaks), on the same
test split and the same set scores as scripts/paper_propagation_tables.py. Inputs must match the hashes recorded
in paper/generated/propagation-facts.json.

usage: python3 -B scripts/paper_onset_sensitivity.py data/corrected-release-20261016 paper/generated
"""
import hashlib
import json
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_propagation_tables import scores  # noqa: E402

YEARS = range(2022, 2027)
LAG = -60.0


def summary(frame):
    test = frame.filter(pl.col("split") == "test")
    out = {"events": frame.height, "test": test.height,
           "floor_d30s": test["J_d30s"].mean() if test.height else None,
           "lag_p10_p50_p90_test": [test["observation_lag_s"].quantile(q) for q in (.1, .5, .9)] if test.height else None}
    return out


def main(data, out):
    facts = json.loads((out / "propagation-facts.json").read_text())
    result = {"rule": f"observation_lag_s >= {LAG}", "years": {}}
    for year in YEARS:
        base = data / "eventset" / str(year)
        for name in ("events.parquet", "rpki_validity.parquet"):
            rel = f"eventset/{year}/{name}"
            digest = hashlib.sha256((base / name).read_bytes()).hexdigest()
            if facts["inputs_sha256"].get(rel) != digest:
                raise SystemExit(f"{rel} differs from the input of propagation-facts.json")
        e = scores(pl.read_parquet(base / "events.parquet"))
        v = pl.read_parquet(base / "rpki_validity.parquet").select("event_id", "validity")
        e = e.join(v, on="event_id", how="left", validate="1:1")
        paper = e.filter(pl.col("reason") != "rpki_invalid_sample")
        stratum = e.filter(pl.col("reason") == "rpki_invalid_sample")
        y = {}
        for label, frame in (("all", paper), ("near", paper.filter(pl.col("observation_lag_s") >= LAG))):
            y[label] = {cls: summary(frame.filter(pl.col("validity") == cls)) for cls in ("invalid", "unknown", "valid")}
            y[label]["pooled"] = summary(frame)
        y["stratum_near"] = summary(stratum.filter(pl.col("observation_lag_s") >= LAG))
        y["stratum_all"] = summary(stratum)
        result["years"][str(year)] = y
    (out / "onset_sensitivity.json").write_text(json.dumps(result, indent=1) + "\n")
    for year, y in result["years"].items():
        cells = []
        for cls in ("invalid", "unknown", "valid"):
            a, n = y["all"][cls], y["near"][cls]
            cells.append(f"{cls}: {a['floor_d30s'] or float('nan'):.3f}->{n['floor_d30s'] or float('nan'):.3f} (test {a['test']}->{n['test']})")
        print(year, " | ".join(cells), "| stratum", f"{y['stratum_all']['floor_d30s']:.3f}->{y['stratum_near']['floor_d30s']:.3f}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
