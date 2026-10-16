"""Agreement between Cloudflare Radar's per-event RPKI tags (rpki_new_origin_{valid,invalid,unknown}) and our same-day ROA
validation of the new origin (eventset/<year>/rpki_validity.parquet). Radar events are matched to replayed events on
hijacker_asn == new origin, prefix ∈ Radar prefixes, |min_hijack_ts − t₀| ≤ 10 min. Also prints Radar's overall tag
distribution (how many of its hijack events have an RPKI-valid new origin at all — the down-weighting question).
usage: radar_rpki_agreement.py <year>  → eventset/<year>/radar_rpki_agreement.json"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from collections import Counter

import polars as pl

from bgbench import config

year = int(sys.argv[1])
E = config.DATA_ROOT / "eventset" / str(year)
LB = config.DATA_ROOT / "labels" / f"{year}-01-01_{year + 1}-01-01"
cf = pl.read_parquet(LB / "cloudflare_hijacks.parquet")


def rpki_tag(t: str) -> str:
    try:
        for x in json.loads(t):
            if x["name"].startswith("rpki_new_origin_"):
                return x["name"].removeprefix("rpki_new_origin_")
    except Exception:  # noqa: BLE001
        pass
    return "none"


cf = cf.with_columns(pl.col("tags").map_elements(rpki_tag, return_dtype=pl.Utf8).alias("radar_rpki"),
                     pl.col("hijacker_asn").cast(pl.Int64, strict=False), pl.col("min_hijack_ts").str.to_datetime(time_zone="UTC", strict=False).dt.replace_time_zone(None))
overall = Counter(cf["radar_rpki"].to_list())

val = pl.read_parquet(E / "rpki_validity.parquet").select("event_id", "validity")
man = pl.read_csv(config.DATA_ROOT / "inventory" / str(year) / "replay_manifest.tsv", separator="\t").select(
    "event_id", "prefix", pl.col("new_origin").cast(pl.Int64), pl.col("t0").str.to_datetime(strict=False))
ours = man.join(val, on="event_id", how="inner")
# candidate pairs on ASN, then prefix membership and time window
j = ours.join(cf.select("id", "hijacker_asn", "prefixes", "min_hijack_ts", "radar_rpki", "confidence_score"), left_on="new_origin", right_on="hijacker_asn", how="inner")
j = j.filter((pl.col("t0") - pl.col("min_hijack_ts")).dt.total_seconds().abs() <= 600)
rows = []
for r in j.iter_rows(named=True):
    pfx = set(re.findall(r"[0-9a-fA-F:.]+/\d+", r["prefixes"] or ""))
    if r["prefix"] in pfx:
        rows.append({"event_id": r["event_id"], "radar_id": r["id"], "ours": r["validity"], "radar": r["radar_rpki"], "confidence": r["confidence_score"]})
m = pl.DataFrame(rows).unique("event_id", keep="first") if rows else pl.DataFrame()
conf = Counter((a, b) for a, b in zip(m["ours"].to_list(), m["radar"].to_list())) if m.height else Counter()
agree = sum(v for (a, b), v in conf.items() if a == b)
out = {"year": year, "radar_events": cf.height, "radar_rpki_new_origin_tags": dict(overall), "matched_events": m.height,
       "agreement": round(agree / m.height, 4) if m.height else None,
       "confusion_ours_vs_radar": {f"{a}|{b}": v for (a, b), v in sorted(conf.items(), key=lambda kv: -kv[1])}}
print(json.dumps(out, indent=1))
(E / "radar_rpki_agreement.json").write_text(json.dumps(out, indent=1))
if m.height:
    m.write_parquet(E / "radar_rpki_agreement.parquet")
