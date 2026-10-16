"""AS paths of the RIPE beacons at the ten collectors on selected 2024 weeks: which upstream of the beacon origin (AS12654) carries
the invalid twin, before and after the April 2024 step and around the August blip. Prints per week the count of sessions carrying
the invalid / valid beacon by first upstream (the AS next to the origin) and by path length.
usage: beacon_paths.py [weeks...] (default: the April step and August weeks)"""
from __future__ import annotations

import re
import sys
from collections import Counter

import polars as pl

from bgbench import config

TEN = ["rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx"]
INV, VAL = "93.175.147.0/24", "93.175.146.0/24"
weeks = sys.argv[1:] or ["2024-01-15", "2024-04-08", "2024-04-15", "2024-04-22", "2024-04-29", "2024-05-06", "2024-08-05", "2024-08-12", "2024-08-19", "2024-12-30"]
rows = []
for f in sorted((config.DATA_ROOT / "ribs").glob("*/*.parquet")):
    c = f.parent.name; m = re.match(r"(\d{4}-\d{2}-\d{2})T", f.name)
    if c not in TEN or not m or m.group(1) not in weeks:
        continue
    sub = pl.scan_parquet(str(f)).filter(pl.col("prefix").is_in([INV, VAL])).select("prefix", "peer_ip", "peer_asn", "as_path").collect()
    for pfx, ip, asn, path in sub.iter_rows():
        hops = [int(x) for x in re.findall(r"\d+", path or "")]
        up = hops[-2] if len(hops) >= 2 else None       # AS adjacent to the origin
        rows.append({"day": m.group(1), "collector": c, "prefix": pfx, "peer_asn": int(asn), "upstream": up, "plen": len(hops), "path": path})
d = pl.DataFrame(rows); d.write_parquet(config.DATA_ROOT / "rpki" / "beacon_paths_2024.parquet")
for day in weeks:
    for pfx, lab in ((INV, "invalid"), (VAL, "valid")):
        s = d.filter((pl.col("day") == day) & (pl.col("prefix") == pfx))
        ups = Counter(s["upstream"].to_list()).most_common(6)
        print(f"{day} {lab:7s} sessions={s.height:4d} path_len_p50={s['plen'].median()} upstream-of-origin: {ups}")
