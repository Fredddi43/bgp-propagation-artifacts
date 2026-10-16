"""Did the hijacked prefix have a covering less-specific route during the hijack? For each hijack → recovery pair, look up the
nearest weekly RIB snapshot before the hijack (ribs/rrc00 by default; any retained collector) and test whether a strict supernet of
the prefix was present (with the legitimate origin, and with any origin). If most hijacked prefixes have a covering route, the
"silent recoverers" kept reachability through it; if not, they were cut off. usage: recovery_covering.py <year> [collector]"""
from __future__ import annotations

import ipaddress
import json
import re
import sys

import polars as pl

from bgbench import config

year = int(sys.argv[1]); collector = sys.argv[2] if len(sys.argv) > 2 else "rrc00"
sel = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "recovery_replay_selection.parquet").select("event_id", "hijack_id", "prefix", pl.col("new_origin").alias("legit_origin"))
sel = sel.with_columns(pl.col("hijack_id").str.slice(0, 8).alias("h_day"))
ribs = sorted((config.DATA_ROOT / "ribs" / collector).glob(f"{year}-*.parquet"))
rib_days = [re.match(r"(\d{4}-\d{2}-\d{2})", f.name).group(1) for f in ribs]
if not ribs:
    sys.exit(f"no retained RIBs for {collector} {year}")
cache: dict[str, tuple[set, dict]] = {}


def rib_state(day: str):
    """(set of prefixes, {prefix: set(origins)}) from the latest snapshot ≤ day."""
    cands = [d for d in rib_days if d <= day] or rib_days[:1]
    k = cands[-1]
    if k not in cache:
        cache.clear()
        t = pl.read_parquet(ribs[rib_days.index(k)], columns=["prefix", "origin_asn"]).unique()
        origins: dict[str, set] = {}
        for p, o in t.iter_rows():
            origins.setdefault(p, set()).add(int(o) if o is not None else -1)
        cache[k] = (set(origins), origins)
    return cache[k]


rows = []
for r in sel.sort("h_day").iter_rows(named=True):
    day = f"{r['h_day'][:4]}-{r['h_day'][4:6]}-{r['h_day'][6:8]}"
    pfxs, origins = rib_state(day)
    net = ipaddress.ip_network(r["prefix"], strict=False)
    floor = 8 if net.version == 4 else 16
    cover_any = cover_legit = False
    for plen in range(net.prefixlen - 1, floor - 1, -1):
        sup = str(net.supernet(new_prefix=plen))
        if sup in pfxs:
            cover_any = True
            if int(r["legit_origin"]) in origins.get(sup, ()):
                cover_legit = True
            break
    rows.append({"event_id": r["event_id"], "cover_any": cover_any, "cover_legit": cover_legit, "rib_day": day})
d = pl.DataFrame(rows)
out = {"year": year, "collector": collector, "pairs": d.height, "covering_less_specific_any_origin": round(float(d["cover_any"].mean()), 4), "covering_less_specific_legit_origin": round(float(d["cover_legit"].mean()), 4)}
print(json.dumps(out, indent=1))
d.write_parquet(config.DATA_ROOT / "eventset" / f"{year}_recovery" / "covering.parquet")
(config.DATA_ROOT / "eventset" / f"{year}_recovery" / "covering_summary.json").write_text(json.dumps(out, indent=1))
