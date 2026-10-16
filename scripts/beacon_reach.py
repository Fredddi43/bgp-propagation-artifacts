"""Reach of the RPKI test beacons at our collectors, from the weekly RIB snapshots (ribs/<collector>/<ts>.parquet: peer, prefix,
as_path, origin). For each snapshot and beacon prefix: peers (sessions) carrying it, distinct ASes on its paths, origin ASNs
seen. The valid/invalid beacon pairs are permanent controlled announcements, so their per-collector reach over time is a
calibration curve for "how far does a known-invalid route get" that carries no event semantics.
Beacon list (confirmed in docs/research/2026-09-09-rpki-rov-propagation-prior-art.md §2): RIPE valid/invalid/unknown twins,
Cloudflare's invalid_length / invalid_asn beacons, Job Snijders' invalid beacons; pass others with --prefix.
usage: beacon_reach.py [--prefix P ...]  → rpki/beacon_reach.parquet and a printed summary."""
from __future__ import annotations

import argparse
import re

import polars as pl

from bgbench import config

DEFAULT = {
    # RIPE NCC RPKI beacons (RRC03, AS12654, since 2011): valid / invalid (ROA names AS196615) / unknown twins
    "93.175.146.0/24": "ripe_v4_valid", "93.175.147.0/24": "ripe_v4_invalid", "84.205.83.0/24": "ripe_v4_unknown",
    "2001:7fb:fd02::/48": "ripe_v6_valid", "2001:7fb:fd03::/48": "ripe_v6_invalid", "2001:7fb:ff03::/48": "ripe_v6_unknown",
    # Cloudflare isbgpsafeyet beacons: invalid_length (AS0 ROA /23) and invalid_asn
    "103.21.244.0/24": "cloudflare_v4_invalid_length", "2606:4700:7000::/48": "cloudflare_v6_invalid_asn",
    # Job Snijders (AS15562) invalid beacons
    "194.32.71.0/24": "snijders_v4_invalid", "209.24.0.0/24": "snijders_v4_invalid_2",
}

ap = argparse.ArgumentParser()
ap.add_argument("--prefix", action="append", default=[], help="extra prefix[=label]")
a = ap.parse_args()
beacons = dict(DEFAULT)
for p in a.prefix:
    k, _, lab = p.partition("=")
    beacons[k] = lab or k

rows = []
for f in sorted((config.DATA_ROOT / "ribs").glob("*/*.parquet")):
    collector = f.parent.name
    m = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{4})", f.name)
    if not m:
        continue
    rib_ts = f"{m.group(1)}T{m.group(2)[:2]}:{m.group(2)[2:]}"
    try:
        sub = (pl.scan_parquet(str(f)).filter(pl.col("prefix").is_in(list(beacons))).select("prefix", "peer_ip", "peer_asn", "as_path", "origin_asn")
               .collect(engine="streaming"))
    except Exception as e:  # noqa: BLE001
        print("skip", f, repr(e)[:80], flush=True)
        continue
    # total peers in the snapshot, for a normalised reach (share of sessions carrying the beacon)
    n_peers = pl.scan_parquet(str(f)).select(pl.col("peer_ip").n_unique()).collect()[0, 0]
    for pfx, lab in beacons.items():
        s = sub.filter(pl.col("prefix") == pfx)
        ases = set()
        for path in s["as_path"].to_list():
            if path:
                ases.update(int(x) for x in re.findall(r"\d+", path))
        rows.append({"collector": collector, "rib_ts": rib_ts, "prefix": pfx, "beacon": lab, "peers_carrying": s["peer_ip"].n_unique(), "peer_asns_carrying": s["peer_asn"].n_unique(),
                     "peers_total": int(n_peers), "ases_on_paths": len(ases), "origins": sorted(set(int(o) for o in s["origin_asn"].drop_nulls().to_list()))})
    print(collector, rib_ts, {lab: r["peers_carrying"] for lab, r in zip(beacons.values(), rows[-len(beacons):])}, "of", n_peers, flush=True)

out = pl.DataFrame(rows)
(config.DATA_ROOT / "rpki").mkdir(exist_ok=True)
out.write_parquet(config.DATA_ROOT / "rpki" / "beacon_reach.parquet")
summ = (out.with_columns((pl.col("peers_carrying") / pl.col("peers_total")).alias("share"))
          .group_by("beacon").agg(snapshots=pl.len(), share_p50=pl.col("share").median().round(3), share_p10=pl.col("share").quantile(0.1).round(3),
                                  share_p90=pl.col("share").quantile(0.9).round(3), ases_p50=pl.col("ases_on_paths").median()).sort("beacon"))
print(summ)
print(out.with_columns((pl.col("peers_carrying") / pl.col("peers_total")).round(3).alias("share")).group_by("collector", "beacon").agg(share=pl.col("share").median()).sort("beacon", "collector"))
