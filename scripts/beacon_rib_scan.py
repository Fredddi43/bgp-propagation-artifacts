"""Scan-and-discard beacon reach for years without retained weekly RIBs: for one collector, every Monday 00:00 of <year>, ingest
the nearest RIB into RAM, count sessions / path-ASes carrying each beacon prefix, delete the RIB. Appends rows to
rpki/beacon_reach_scan/<collector>_<year>.parquet (resumable: existing weeks are skipped).
usage: beacon_rib_scan.py <year> <collector>   (array job: one task per collector)"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import sys

import polars as pl

from bgbench import config
from bgbench.ribs import ingest_rib

BEACONS = {
    # RIPE NCC RPKI beacons (RRC03, AS12654, since 2011): valid / invalid (ROA names AS196615) / unknown twins
    "93.175.146.0/24": "ripe_v4_valid", "93.175.147.0/24": "ripe_v4_invalid", "84.205.83.0/24": "ripe_v4_unknown",
    "2001:7fb:fd02::/48": "ripe_v6_valid", "2001:7fb:fd03::/48": "ripe_v6_invalid", "2001:7fb:ff03::/48": "ripe_v6_unknown",
    # Cloudflare isbgpsafeyet beacons: invalid_length (AS0 ROA /23) and invalid_asn
    "103.21.244.0/24": "cloudflare_v4_invalid_length", "2606:4700:7000::/48": "cloudflare_v6_invalid_asn",
    # Job Snijders (AS15562) invalid beacons
    "194.32.71.0/24": "snijders_v4_invalid", "209.24.0.0/24": "snijders_v4_invalid_2",
}
year, collector = int(sys.argv[1]), sys.argv[2]
out_dir = config.DATA_ROOT / "rpki" / "beacon_reach_scan"; out_dir.mkdir(parents=True, exist_ok=True)
out_f = out_dir / f"{collector}_{year}.parquet"
rows = pl.read_parquet(out_f).to_dicts() if out_f.exists() else []
done = {r["monday"] for r in rows}
d0 = dt.date(year, 1, 1); d0 += dt.timedelta(days=(7 - d0.weekday()) % 7)
mondays = [d0 + dt.timedelta(weeks=i) for i in range(53) if (d0 + dt.timedelta(weeks=i)).year == year]
shm = config.shm_dir() / "beacon_scan" / collector
for m in mondays:
    key = m.isoformat()
    if key in done:
        continue
    shm.mkdir(parents=True, exist_ok=True)
    res = ingest_rib(collector, dt.datetime(m.year, m.month, m.day, tzinfo=dt.timezone.utc), out_dir=shm)
    if res.get("error") or not res.get("path"):
        rows.append({"collector": collector, "monday": key, "rib_ts": None, "prefix": None, "beacon": None, "peers_carrying": None, "peer_asns_carrying": None, "peers_total": None, "ases_on_paths": None, "error": res.get("error", "no path")})
        print(key, "ERROR", res.get("error"), flush=True)
    else:
        lf = pl.scan_parquet(res["path"])
        n_peers = lf.select(pl.col("peer_ip").n_unique()).collect()[0, 0]
        sub = lf.filter(pl.col("prefix").is_in(list(BEACONS))).select("prefix", "peer_ip", "peer_asn", "as_path").collect()
        for pfx, lab in BEACONS.items():
            s = sub.filter(pl.col("prefix") == pfx)
            ases = set()
            for path in s["as_path"].to_list():
                if path:
                    ases.update(int(x) for x in re.findall(r"\d+", path))
            rows.append({"collector": collector, "monday": key, "rib_ts": res["rib_ts"], "prefix": pfx, "beacon": lab, "peers_carrying": s["peer_ip"].n_unique(), "peer_asns_carrying": s["peer_asn"].n_unique(),
                         "peers_total": int(n_peers), "ases_on_paths": len(ases), "error": None})
        print(key, {lab: r["peers_carrying"] for lab, r in zip(BEACONS.values(), rows[-len(BEACONS):])}, "of", n_peers, flush=True)
    shutil.rmtree(shm, ignore_errors=True)
    pl.DataFrame(rows).write_parquet(out_f)
print("done", out_f, len(rows), "rows")
