"""Day-block bootstrap intervals for class differences of the 30-s floor, all events and near-onset events
(observation_lag_s >= -60), catalogue population, test split. Blocks are UTC days of the event identifier
(first 8 characters of event_id). 2,000 repetitions, seed 1701. Inputs hash-checked as in paper_onset_sensitivity.py.
usage: python3 -B scripts/paper_onset_sensitivity_ci.py data/corrected-release-20261016 paper/generated"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paper_propagation_tables import scores  # noqa: E402

REPS, SEED, LAG = 2000, 1701, -60.0


def diff_ci(frame, a, b, rng):
    f = frame.with_columns(pl.col("event_id").str.slice(0, 8).alias("day"))
    days = f["day"].unique().sort().to_list()
    idx = {d: i for i, d in enumerate(days)}
    day = np.array([idx[d] for d in f["day"].to_list()])
    J = f["J_d30s"].to_numpy()
    cls = f["validity"].to_numpy()
    A = cls == a; B = cls == b
    nd = len(days)
    # per-day sums and counts
    sa = np.bincount(day, weights=J * A, minlength=nd); ca = np.bincount(day, weights=A, minlength=nd)
    sb = np.bincount(day, weights=J * B, minlength=nd); cb = np.bincount(day, weights=B, minlength=nd)
    point = sa.sum() / ca.sum() - sb.sum() / cb.sum()
    draws = rng.integers(0, nd, size=(REPS, nd))
    w = np.apply_along_axis(lambda r: np.bincount(r, minlength=nd), 1, draws)
    boot = (w @ sa) / (w @ ca) - (w @ sb) / (w @ cb)
    lo, hi = np.nanpercentile(boot, [2.5, 97.5])
    return [round(float(point), 4), round(float(lo), 4), round(float(hi), 4)]


def main(data, out):
    facts = json.loads((out / "propagation-facts.json").read_text())
    rng = np.random.default_rng(SEED)
    res = {"reps": REPS, "seed": SEED, "rule": f"observation_lag_s >= {LAG}", "years": {}}
    for year in range(2022, 2027):
        base = data / "eventset" / str(year)
        for name in ("events.parquet", "rpki_validity.parquet"):
            if facts["inputs_sha256"][f"eventset/{year}/{name}"] != hashlib.sha256((base / name).read_bytes()).hexdigest():
                raise SystemExit("input differs")
        e = scores(pl.read_parquet(base / "events.parquet")).join(
            pl.read_parquet(base / "rpki_validity.parquet").select("event_id", "validity"), on="event_id", validate="1:1")
        test = e.filter((pl.col("reason") != "rpki_invalid_sample") & (pl.col("split") == "test"))
        near = test.filter(pl.col("observation_lag_s") >= LAG)
        y = {}
        for label, frame in (("all", test), ("near", near)):
            y[label] = {"invalid-unknown": diff_ci(frame, "invalid", "unknown", rng),
                        "invalid-valid": diff_ci(frame, "invalid", "valid", rng),
                        "unknown-valid": diff_ci(frame, "unknown", "valid", rng),
                        "share_near": {c: near.filter(pl.col("validity") == c).height / max(1, test.filter(pl.col("validity") == c).height)
                                       for c in ("invalid", "unknown", "valid")}}
        res["years"][str(year)] = y
        print(year, "ALL", y["all"]["invalid-unknown"], y["all"]["invalid-valid"], "NEAR", y["near"]["invalid-unknown"], y["near"]["invalid-valid"], y["near"]["unknown-valid"], {k: round(v, 2) for k, v in y["near"]["share_near"].items()})
    (out / "onset_sensitivity_ci.json").write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
