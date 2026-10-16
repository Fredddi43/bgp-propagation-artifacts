"""Fetch RIPE's daily ROA archive (per TAL: ripencc, arin, apnic, lacnic, afrinic) for a date range and store one Parquet
per day with (prefix, max_len, asn, tal). Source layout: https://ftp.ripe.net/rpki/<tal>.tal/<YYYY>/<MM>/<DD>/roas.csv.xz
(see docs/research/2026-09-09-open-items-data-sources.md). usage: fetch_roas.py <start> <end> <out_dir> [workers]"""
from __future__ import annotations

import datetime as dt
import io
import lzma
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import polars as pl

TALS = ["ripencc", "arin", "apnic", "lacnic", "afrinic"]
BASE = "https://ftp.ripe.net/rpki/{tal}.tal/{y:04d}/{m:02d}/{d:02d}/roas.csv.xz"


def fetch_day(day: dt.date, out_dir: Path) -> str:
    out = out_dir / f"{day.isoformat()}.parquet"
    if out.exists():
        return f"{day} exists"
    frames = []
    with httpx.Client(timeout=120, follow_redirects=True, transport=httpx.HTTPTransport(local_address="0.0.0.0", retries=3)) as c:
        for tal in TALS:
            url = BASE.format(tal=tal, y=day.year, m=day.month, d=day.day)
            r = c.get(url)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            txt = lzma.decompress(r.content).decode("utf-8", errors="replace")
            df = pl.read_csv(io.StringIO(txt), has_header=True, infer_schema_length=0)
            cols = {c.lower().strip(): c for c in df.columns}
            asn_c = cols.get("asn"); pfx_c = cols.get("ip prefix") or cols.get("prefix"); ml_c = cols.get("max length") or cols.get("maxlength")
            if not (asn_c and pfx_c and ml_c):
                continue
            frames.append(df.select(pl.col(pfx_c).alias("prefix"), pl.col(ml_c).cast(pl.Int32, strict=False).alias("max_len"),
                                    pl.col(asn_c).str.replace("AS", "").cast(pl.UInt32, strict=False).alias("asn")).with_columns(tal=pl.lit(tal)))
    if not frames:
        return f"{day} no data"
    pl.concat(frames).unique().write_parquet(out, compression="zstd")
    return f"{day} ok {sum(f.height for f in frames)} ROAs"


def main(start: str, end: str, out_dir: str, workers: int = 6) -> None:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    days = [s + dt.timedelta(days=i) for i in range((e - s).days + 1)]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for msg in ex.map(lambda d: fetch_day(d, out), days):
            if "ok" not in msg:
                print(msg, flush=True)
    print("done", len(days), "days; files:", len(list(out.glob("*.parquet"))))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 6)
