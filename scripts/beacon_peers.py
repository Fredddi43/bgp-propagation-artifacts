"""Which peer sessions stopped carrying the RIPE invalid beacon in 2024? From the retained weekly RIBs at the ten collectors, record
per snapshot the set of (collector, peer_asn) carrying the invalid beacon and the valid twin; report peers that carried both in
Jan–Feb 2024 and only the valid one in Jun–Dec 2024 (switched to invalid = reject), and the reverse. Writes
rpki/beacon_peers_2024.parquet and prints the switchers with their session counts. usage: beacon_peers.py"""
from __future__ import annotations

import re

import polars as pl

from bgbench import config

TEN = ["rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx"]
INV, VAL = "93.175.147.0/24", "93.175.146.0/24"
rows = []
for f in sorted((config.DATA_ROOT / "ribs").glob("*/*.parquet")):
    c = f.parent.name
    m = re.match(r"(\d{4}-\d{2}-\d{2})T", f.name)
    if c not in TEN or not m or not m.group(1).startswith("2024"):
        continue
    sub = pl.scan_parquet(str(f)).filter(pl.col("prefix").is_in([INV, VAL])).select("prefix", "peer_ip", "peer_asn").collect()
    for pfx, ip, asn in sub.iter_rows():
        rows.append({"collector": c, "day": m.group(1), "prefix": pfx, "peer_ip": ip, "peer_asn": int(asn)})
    print(c, m.group(1), sub.height, flush=True)
d = pl.DataFrame(rows)
d.write_parquet(config.DATA_ROOT / "rpki" / "beacon_peers_2024.parquet")
early = d.filter(pl.col("day") < "2024-03-01"); late = d.filter(pl.col("day") >= "2024-06-01")


def carriers(x, pfx):
    return set(x.filter(pl.col("prefix") == pfx).select("collector", "peer_ip", "peer_asn").unique().iter_rows())


e_inv, e_val, l_inv, l_val = carriers(early, INV), carriers(early, VAL), carriers(late, INV), carriers(late, VAL)
stopped = (e_inv & l_val) - l_inv          # carried invalid early, still carries valid late, no longer carries invalid
started = (l_inv & e_val) - e_inv
print("sessions carrying valid twin early/late:", len(e_val), len(l_val), " invalid early/late:", len(e_inv), len(l_inv))
print("sessions that STOPPED carrying the invalid beacon (kept the valid one):", len(stopped))
print(pl.DataFrame([{"collector": c, "peer_asn": a} for c, _, a in stopped]).group_by("peer_asn").agg(sessions=pl.len(), collectors=pl.col("collector").n_unique()).sort("sessions", descending=True).head(25))
print("sessions that STARTED carrying it:", len(started))
print(pl.DataFrame([{"collector": c, "peer_asn": a} for c, _, a in started]).group_by("peer_asn").agg(sessions=pl.len()).sort("sessions", descending=True).head(10) if started else "-")
# week-by-week count of invalid-carrying sessions, to date the step
wk = d.filter(pl.col("prefix") == INV).group_by("day").agg(sessions=pl.n_unique("peer_ip")).sort("day")
print(wk.to_pandas().to_string() if hasattr(wk, "to_pandas") else wk)
