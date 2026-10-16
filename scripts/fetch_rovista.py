"""RoVista per-AS ROV enforcement history (api.rovista.netsecurelab.org, OpenAPI at rovista.netsecurelab.org/api-docs):
/rovista/api/world-rov-scores?type=cone-size&offset=&limit= lists ASes; /rovista/api/AS-rov-scores/{asn} gives the
(recordDate, total, filter, ratio) series since 2021-12. Writes DATA_ROOT/rpki/rovista/as_rov_series.parquet and
asn_list.parquet. Polite: sequential, small sleep. usage: fetch_rovista.py <out_dir> [max_asns]"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx
import polars as pl

API = "https://api.rovista.netsecurelab.org/rovista/api"


def main(out_dir: str, max_asns: int = 0) -> None:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    c = httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "bgbench/0.1 (research artifact)"})
    # RoVista has no public "list all ASes" endpoint (world-rov-scores returns per-country scores), so the AS universe
    # is ours: every AS in the CAIDA relationship tables we use (graphs/*.rel.parquet).
    from bgbench import config
    rels = sorted((config.DATA_ROOT / "graphs").glob("*.rel.parquet"))
    u = pl.concat([pl.read_parquet(f, columns=["u", "v"]) for f in rels])
    asns = [{"asn": int(a)} for a in sorted(set(u["u"].to_list()) | set(u["v"].to_list()))]
    pl.DataFrame(asns).write_parquet(out / "asn_list.parquet")
    print("asns", len(asns), flush=True)
    series = []
    done_f = out / "as_rov_series.parquet"
    have = set(pl.read_parquet(done_f)["asn"].unique().to_list()) if done_f.exists() else set()
    if done_f.exists():
        series.append(pl.read_parquet(done_f))
    todo = [a["asn"] for a in asns if a["asn"] not in have][: (max_asns or None)]
    buf = []
    for i, asn in enumerate(todo):
        try:
            r = c.get(f"{API}/AS-rov-scores/{asn}")
            if r.status_code == 429:
                time.sleep(30); r = c.get(f"{API}/AS-rov-scores/{asn}")
            r.raise_for_status()
            for x in r.json():
                buf.append({"asn": int(asn), "date": x["asnDateKey"]["recordDate"], "total": x.get("total"), "filter": x.get("filter"), "ratio": x.get("ratio")})
        except Exception as e:  # noqa: BLE001
            print("skip", asn, repr(e)[:80], flush=True)
        time.sleep(0.15)
        if (i + 1) % 1000 == 0:
            series.append(pl.DataFrame(buf)); buf = []
            pl.concat(series, how="diagonal_relaxed").write_parquet(done_f); print("saved", i + 1, flush=True)
    if buf:
        series.append(pl.DataFrame(buf))
    if series:
        pl.concat(series, how="diagonal_relaxed").write_parquet(done_f)
    print("done", done_f)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)
