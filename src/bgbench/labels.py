"""Label sources (ADR-0015): GRIP (hijacks; epoch timestamps ONLY) and Cloudflare Radar (hijacks + leaks)."""

from __future__ import annotations

import datetime as dt
import time
import os
from pathlib import Path

import httpx
import polars as pl

from . import config

GRIP_BASE = "https://api.grip.inetintel.cc.gatech.edu/v1/json"  # /json 301s to /v1/json since 2026
CF_BASE = "https://api.cloudflare.com/client/v4/radar/bgp"


def _epoch(t: dt.datetime) -> int:
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    return int(t.timestamp())


def grip_events(
    start: dt.datetime,
    end: dt.datetime,
    event_type: str = "all",
    min_susp: int = 60,
    client: httpx.Client | None = None,
) -> pl.DataFrame:
    """All GRIP events with view_ts in [start, end) and suspicion ≥ min_susp (server-side — GRIP caps any
    query at 10,000 newest events, and a week of submoas alone exceeds that). Queried in one-day chunks.
    GRIP silently ignores ISO timestamps → epoch only; every page's view_ts is asserted inside the window."""
    own = client is None
    client = client or httpx.Client(timeout=120, follow_redirects=True)
    frames = []
    skipped: list[str] = []
    try:
        day = start
        while day < end:
            nxt = min(day + dt.timedelta(days=1), end)
            for attempt in range(4):                      # GRIP returns 5xx for some 2023 days; one bad day must not kill a year
                try:
                    frames.append(_grip_chunk(client, day, nxt, event_type, min_susp))
                    break
                except (httpx.HTTPError, ValueError) as e:
                    if attempt == 3:
                        print(f"[grip] skipped {day.date()}: {type(e).__name__}: {str(e)[:120]}", flush=True)
                        skipped.append(day.date().isoformat())
                    else:
                        time.sleep(10 * (attempt + 1))
            day = nxt
    finally:
        if own:
            client.close()
    grip_events.last_skipped = skipped                    # reported by fetch_all_labels
    frames = [f for f in frames if f.height]
    return (
        pl.concat(frames, how="diagonal_relaxed")
        if frames
        else pl.DataFrame(
            schema={"id": pl.String, "event_type": pl.String, "view_ts": pl.Datetime("us", "UTC")}
        )
    )


def _grip_chunk(
    client: httpx.Client, start: dt.datetime, end: dt.datetime, event_type: str, min_susp: int
) -> pl.DataFrame:
    rows, off, length = [], 0, 1000
    if True:
        while True:
            r = client.get(
                f"{GRIP_BASE}/events",
                params={
                    "event_type": event_type,
                    "ts_start": _epoch(start),
                    "ts_end": _epoch(end),
                    "start": off,
                    "length": length,
                    "min_susp": min_susp,
                },
            )
            r.raise_for_status()
            body = r.json()
            data = body.get("data", [])
            for e in data:
                vt = e.get("view_ts")
                vts = (
                    dt.datetime.fromisoformat(vt.replace("Z", "+00:00"))
                    if isinstance(vt, str)
                    else dt.datetime.fromtimestamp(vt, dt.UTC)
                )
                if vts.tzinfo is None:
                    vts = vts.replace(tzinfo=dt.UTC)
                if not (start <= vts < end + dt.timedelta(days=1)):
                    raise RuntimeError(
                        f"GRIP returned view_ts {vts} outside the requested window — timestamp filter not honoured"
                    )
                sm = e.get("summary", {}) or {}
                rows.append(
                    {
                        "id": None if e.get("id") is None else str(e.get("id")),
                        "event_type": e.get("event_type"),
                        "view_ts": vts,
                        "finished_ts": None if e.get("finished_ts") is None else str(e.get("finished_ts")),
                        "duration": None if e.get("duration") is None else float(e.get("duration")),
                        "victims": ",".join(map(str, sm.get("victims", []) or [])),
                        "attackers": ",".join(map(str, sm.get("attackers", []) or [])),
                        "prefixes": ",".join(sm.get("prefixes", []) or []),
                        "tags": ",".join(
                            t if isinstance(t, str) else t.get("name", "")
                            for t in (sm.get("tags", []) or [])
                        ),
                        "inference": ",".join(
                            i.get("inference_id", "") if isinstance(i, dict) else str(i)
                            for i in (sm.get("inference_result", {}) or {}).get("inferences", [])
                            or []
                        ),
                        "suspicion": (sm.get("inference_result", {}) or {})
                        .get("primary_inference", {})
                        .get("suspicion_level")
                        if isinstance(sm.get("inference_result"), dict)
                        else None,
                        "confidence": (sm.get("inference_result", {}) or {})
                        .get("primary_inference", {})
                        .get("confidence")
                        if isinstance(sm.get("inference_result"), dict)
                        else None,
                        "insert_ts": None if e.get("insert_ts") is None else str(e.get("insert_ts")),
                    }
                )
            total = int(body.get("recordsTotal", body.get("recordsFiltered", 0)) or 0)
            off += len(data)
            if not data or off >= total or off >= 10000:
                if off >= 10000 and off < total:
                    print(
                        f"[grip] WARNING: {start:%F} chunk hit the 10k cap ({total} total) — narrow the chunk or raise min_susp"
                    )
                break
    schema = {
        "id": pl.String, "event_type": pl.String, "view_ts": pl.Datetime("us", "UTC"), "finished_ts": pl.String,
        "duration": pl.Float64, "victims": pl.String, "attackers": pl.String, "prefixes": pl.String, "tags": pl.String,
        "inference": pl.String, "suspicion": pl.Int64, "confidence": pl.Int64, "insert_ts": pl.String,
    }
    if not rows:
        return pl.DataFrame(schema=schema)
    # explicit schema: GRIP mixes ints and strings in the same field across events (finished_ts, insert_ts),
    # and inference from the first rows then rejects later ones
    rows = [{k: (str(v) if schema[k] == pl.String and v is not None else v) for k, v in r.items()} for r in rows]
    return pl.DataFrame(rows, schema=schema, strict=False)


def _cf_token() -> str:
    tok = os.environ.get("CLOUDFLARE_RADAR_TOKEN")
    if not tok:
        env = Path(config.SECRETS_DIR) / "cloudflare-radar.env"
        for line in env.read_text().splitlines():
            if line.startswith("CLOUDFLARE_RADAR_TOKEN="):
                tok = line.split("=", 1)[1].strip()
    if not tok:
        raise RuntimeError(
            "Cloudflare Radar token not found (env CLOUDFLARE_RADAR_TOKEN or secrets/cloudflare-radar.env)"
        )
    return tok


def cloudflare_events(
    kind: str, start: dt.datetime, end: dt.datetime, client: httpx.Client | None = None
) -> pl.DataFrame:
    """kind = 'hijacks' | 'leaks'. Absolute dateStart/dateEnd (verified to reach 2023)."""
    own = client is None
    client = client or httpx.Client(timeout=120, headers={"Authorization": f"Bearer {_cf_token()}"})
    rows, page = [], 1
    try:
        while True:
            for attempt in range(8):                  # Radar rate-limits (429) when two label runs overlap; back off, honour Retry-After
                r = client.get(
                    f"{CF_BASE}/{kind}/events",
                    params={
                        "dateStart": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "dateEnd": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "per_page": 1000,
                        "page": page,
                        "format": "json",
                    },
                )
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 7:
                    wait = float(r.headers.get("Retry-After") or 30 * (attempt + 1))
                    time.sleep(min(wait, 300))
                    continue
                break
            r.raise_for_status()
            body = r.json()
            if not body.get("success"):
                raise RuntimeError(f"Cloudflare Radar error: {body.get('errors')}")
            ev = body["result"].get("events", [])
            rows += ev
            info = body.get("result_info") or body["result"].get("result_info") or {}
            if (
                not ev
                or len(ev) < 1000
                or (info.get("total_count") and len(rows) >= info["total_count"])
            ):
                break
            page += 1
    finally:
        if own:
            client.close()
    if not rows:
        return pl.DataFrame()
    import json as _json

    # Cloudflare mixes scalar types across rows within a field (e.g. ints and strings in the same column over
    # a year of events), which breaks schema inference. Nested values are JSON-serialised; every other non-null
    # scalar is stringified — consumers cast what they need (timestamps, counts) with strict=False.
    flat = [
        {k: (_json.dumps(v) if isinstance(v, (list, dict)) else (None if v is None else str(v))) for k, v in r.items()}
        for r in rows
    ]
    return pl.DataFrame(flat, strict=False, infer_schema_length=None)


def fetch_all_labels(start: str, end: str, out_dir: Path | None = None, min_susp: int = 60) -> dict:
    s = dt.datetime.fromisoformat(start).replace(tzinfo=dt.UTC)
    e = dt.datetime.fromisoformat(end).replace(tzinfo=dt.UTC)
    out_dir = out_dir or (config.DATA_ROOT / "labels" / f"{start}_{end}")
    out_dir.mkdir(parents=True, exist_ok=True)
    res = {}
    g = grip_events(s, e, min_susp=min_susp)
    g.write_parquet(out_dir / "grip.parquet")
    res["grip_days_skipped"] = getattr(grip_events, "last_skipped", [])
    res["grip"] = {
        "events": g.height,
        "by_type": g.group_by("event_type").len().to_dicts() if g.height else [],
    }
    for kind in ("hijacks", "leaks"):
        df = cloudflare_events(kind, s, e)
        df.write_parquet(out_dir / f"cloudflare_{kind}.parquet")
        res[f"cloudflare_{kind}"] = df.height
    res["out"] = str(out_dir)
    return res


def load_cf_leaks(labels_dir: Path) -> pl.DataFrame | None:
    """Cloudflare leak labels with min_ts parsed, or None when the table is missing or empty (Radar has no leak
    events before 2024 — every leak evaluation must then be skipped, not crash)."""
    f = Path(labels_dir) / "cloudflare_leaks.parquet"
    if not f.exists():
        return None
    d = pl.read_parquet(f)
    if d.height == 0 or "min_ts" not in d.columns:
        return None
    return d.with_columns(pl.col("min_ts").str.to_datetime(time_zone="UTC", strict=False))
