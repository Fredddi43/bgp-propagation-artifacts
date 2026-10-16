"""ASN → country from the NRO delegated-extended statistics (all five RIRs in one file) and RoVista's per-country ROV scores.
Writes graphs/asn_country.parquet (asn, cc, rir) and rpki/rovista/country_scores.json ({cc: rovScore})."""
from __future__ import annotations

import json

import httpx
import polars as pl

from bgbench import config

out = config.DATA_ROOT / "graphs" / "asn_country.parquet"
r = httpx.get("https://ftp.ripe.net/pub/stats/ripencc/nro-stats/latest/nro-delegated-stats", timeout=300, follow_redirects=True); r.raise_for_status()
rows = []
for line in r.text.splitlines():
    f = line.split("|")
    if len(f) < 7 or f[2] != "asn" or f[0].startswith("#") or f[1] == "*":
        continue
    try:
        start, n = int(f[3]), int(f[4])
    except ValueError:
        continue
    if n > 100000:
        continue
    for a in range(start, start + n):
        rows.append((a, f[1].lower(), f[0]))
d = pl.DataFrame(rows, schema=["asn", "cc", "rir"], orient="row").unique("asn")
d.write_parquet(out); print("asn→country", d.height, "ASNs;", d["cc"].n_unique(), "countries")
c = httpx.get("https://api.rovista.netsecurelab.org/rovista/api/world-rov-scores", params={"type": "cone-size"}, timeout=60, follow_redirects=True)
c.raise_for_status()
scores = {x["countryCode"].lower(): float(x["rovScore"]) for x in c.json() if x.get("countryCode")}
(config.DATA_ROOT / "rpki" / "rovista" / "country_scores.json").write_text(json.dumps(scores, indent=1)); print("country ROV scores", len(scores))
