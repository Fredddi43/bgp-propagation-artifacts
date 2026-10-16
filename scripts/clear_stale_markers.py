"""Remove replay-by-day `_done` markers for the collector-days that a grown manifest needs again. A day marker says "every event of
this manifest on this day has its parts", which stops being true when the selection grows (2026-09-17: the 2026 label-free
stratum's recoveries were merged from days that had markers from the earlier, smaller selection, and 1,469 of 1,527 came out as
"no parts"). For every manifest event without a usable merged summary, the marker of its t0 day and of the following day is
removed for all collectors, so Snakemake re-extracts exactly those days.
usage: clear_stale_markers.py --manifest <tsv> [--tag recovery]"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import polars as pl

from bgbench import config
from bgbench.replay_day import load_manifest, roots

ap = argparse.ArgumentParser()
ap.add_argument("--manifest", required=True)
ap.add_argument("--tag", default="")
a = ap.parse_args()
man = load_manifest(config.DATA_ROOT / a.manifest if not a.manifest.startswith("/") else __import__("pathlib").Path(a.manifest))
parts_root, merged_root = roots(a.tag)
days: set[str] = set()
missing = 0
for e in man.iter_rows(named=True):
    f = merged_root / e["event_id"] / "summary.json"
    ok = False
    if f.exists():
        try:
            ok = json.loads(f.read_text()).get("error") != "no parts"
        except Exception:
            ok = False
    if not ok:
        missing += 1
        d0 = e["t0"].date() if hasattr(e["t0"], "date") else dt.date.fromisoformat(str(e["t0"])[:10])
        days.add(d0.isoformat()); days.add((d0 + dt.timedelta(days=1)).isoformat())
removed = 0
done = parts_root / "_done"
if done.exists():
    for coll in done.iterdir():
        for d in days:
            m = coll / f"{d}.json"
            if m.exists():
                m.unlink(); removed += 1
print(json.dumps({"tag": a.tag, "events_without_parts": missing, "days": len(days), "markers_removed": removed}))
