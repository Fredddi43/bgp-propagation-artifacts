"""Provenance check of the ROA day files behind the paper's RPKI validation: does every daily ROA file that a validated event
read hold all five RIPE-archived trust anchors (ripencc, arin, apnic, lacnic, afrinic), each at its usual size?

Why: scripts/fetch_roas.py writes rpki/roas/<day>.parquet from https://ftp.ripe.net/rpki/<tal>.tal/YYYY/MM/DD/roas.csv.xz and
silently skips a TAL on HTTP 404 or when its CSV lacks the asn/prefix/max-length columns (and a header-only CSV adds no rows).
On such a day the missing anchor's address space validates as unknown instead of possibly invalid or valid.

Stage 1, `collect` (read-only, prints one JSON document to stdout, writes nothing):
  1. every ROA day file of each validation root (<root>/rpki/roas/*.parquet): rows per tal (the tal column only), null counts of
     prefix/max_len/asn from the Parquet statistics, resolved path; flags a file when a TAL is absent, or has fewer than
     SHORT_RATIO x the median rows of the same TAL in the +-NEIGHBOURS neighbouring files ("short"), or has nulls;
  2. the day rule of src/bgbench/rpki_validate.py roas_for (the file of the event's UTC day, else the nearest earlier file within
     7 days, else no_roa_data) applied to every validated event: development eventset/<year>/rpki_validity.parquet (day = event_id
     [:8], scripts/rpki_validity_events.py) and the new-period eventset/2026/rpki_validity.parquet (day = first_ts UTC day of
     inventory/2026/replay_selection.parquet, finalize kernel validate_origins); also every calendar day of the replay range and of
     the R2 window, and the t0+7 / t0+30 days that scripts/later_validity.py reads;
  3. re-validation, with a verbatim copy of rpki_validate.validity, of every validated event against the file its day resolves to
     (stored labels must be reproduced exactly), and of every event on a flagged file against a repaired table: the event day's
     ROAs of the unaffected TALs plus the affected TAL's ROAs from the nearest earlier (and, separately, later) unflagged file.
     A label change counts as caused by the flagged TAL only when both repairs agree on it (assess); a change under one repair
     only is ROA churn on the adjacent day.
Stage 2, `ripe-check` (needs internet, reads only https://ftp.ripe.net): for every flagged (file, TAL) that an event or a window
  day resolves to, count the rows of RIPE's archived roas.csv.xz now and compare with the stored row count, to separate an
  archive-side short or empty TAL from a fetch-side drop; and the HTTP status of all five TALs on each day that read the fallback
  file. Both stages write `summary` (one sentence) and `summary_detail`.

usage:
  ssh <BATCH_HOST> 'cd /tmp && <RESULTS_ROOT>/work/<PROJECT>/venv/bin/python -B -I - collect \
      --dev-root <MODELS_ROOT>/nobackup/<PROJECT>/corrections-20261016/data \
      --r2-root  <FORECAST_ROOT>/data-custodian/newperiod-origin-replay-v2-finalize-r2/records/finalize-0000/output' \
      < scripts/paper_roa_anchor_check.py > <scratch>/collect.json
  python -B scripts/paper_roa_anchor_check.py ripe-check <scratch>/collect.json > paper/generated/roa_anchor_check.json
Both stages also run locally on copied roots with local paths. New-period event ids are never written (counts only).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import lzma
import os
import platform
import statistics
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TALS = ("ripencc", "arin", "apnic", "lacnic", "afrinic")
FALLBACK_DAYS = 7          # rpki_validate.roas_for: nearest earlier archive within one week
SHORT_RATIO = 0.9          # a TAL below 90 % of its local median is flagged "short"
NEAR_EMPTY_RATIO = 0.5     # reported band within short
NEIGHBOURS = 15            # files on each side for the local median
NEIGHBOUR_SEARCH = 7       # days searched for unflagged neighbour files in the re-validation
RIPE = "https://ftp.ripe.net/rpki/{tal}.tal/{y}/{m}/{d}/roas.csv.xz"
VALIDITY_SHA256 = "817f435fdaaf25031bf3e1b37e6e2a4f702bfb0e8c75eaba3a9f3a250261b342"


def validity(prefix: str, origin: int, tab) -> tuple[str, int, str]:
    """Verbatim copy of src/bgbench/rpki_validate.py validity (file sha256 817f435f..., commit d4a79db1)."""
    net = ipaddress.ip_network(prefix, strict=False)
    covering = 0
    valid = False
    asn_match_too_long = False
    # RFC 6811 section 2: coverage is prefix containment, independent of
    # maxLength. A covered but too-specific announcement is Invalid, not
    # NotFound. Include /0; there is no family-specific minimum ROA length.
    for plen in range(net.prefixlen, -1, -1):
        sup = net if plen == net.prefixlen else net.supernet(new_prefix=plen)
        for ml, a in tab.get(str(sup), ()):
            covering += 1
            if net.prefixlen <= ml:
                if a == origin and a != 0:
                    valid = True
            elif a == origin:
                asn_match_too_long = True
    state = "valid" if valid else ("invalid" if covering else "unknown")
    reason = "" if state != "invalid" else ("invalid_length" if asn_match_too_long else "invalid_asn")
    return state, covering, reason


def supernets(prefix: str) -> list[str]:
    net = ipaddress.ip_network(prefix, strict=False)
    return [str(net if p == net.prefixlen else net.supernet(new_prefix=p)) for p in range(net.prefixlen, -1, -1)]


def sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


# ---------------------------------------------------------------------------------------------------------------- ROA files
def list_days(directory: Path) -> dict[str, Path]:
    out = {}
    for name in os.listdir(directory):
        if name.endswith(".parquet") and len(name) == len("YYYY-MM-DD.parquet"):
            out[name[:10]] = directory / name
    return dict(sorted(out.items()))


def file_stats(path: Path) -> dict:
    import polars as pl
    import pyarrow.parquet as pq
    meta = pq.ParquetFile(path).metadata
    names = [meta.schema.column(i).name for i in range(meta.num_columns)]
    nulls = {}
    for col in ("prefix", "max_len", "asn", "tal"):
        if col not in names:
            nulls[col] = "column_missing"
            continue
        j = names.index(col)
        total = 0
        for g in range(meta.num_row_groups):
            st = meta.row_group(g).column(j).statistics
            if st is None or not st.has_null_count:
                total = None
                break
            total += st.null_count
        nulls[col] = total
    tal = pl.scan_parquet(path).group_by("tal").agg(pl.len().alias("n")).collect()
    return {"path": str(path), "resolved": os.path.realpath(path), "bytes": os.path.getsize(path), "rows": meta.num_rows,
            "tal_rows": {t: int(n) for t, n in tal.iter_rows()}, "nulls": nulls}


def scan(directory: Path, cache: dict) -> dict[str, dict]:
    days = list_days(directory)
    todo = [p for p in days.values() if os.path.realpath(p) not in cache]
    with ThreadPoolExecutor(max_workers=16) as ex:
        for p, st in zip(todo, ex.map(file_stats, todo)):
            cache[os.path.realpath(p)] = st
    out = {}
    for day, p in days.items():
        st = dict(cache[os.path.realpath(p)])
        st["path"] = str(p)
        out[day] = st
    return out


def flag_files(stats: dict[str, dict]) -> dict[str, dict]:
    """Per day: TALs absent, TALs below SHORT_RATIO x local median, unexpected TAL values, nonzero nulls."""
    days = list(stats)
    flags = {}
    for i, day in enumerate(days):
        s = stats[day]
        missing = [t for t in TALS if s["tal_rows"].get(t, 0) == 0]
        extra = sorted(t for t in s["tal_rows"] if t not in TALS)
        short = {}
        window = days[max(0, i - NEIGHBOURS): i] + days[i + 1: i + 1 + NEIGHBOURS]
        for t in TALS:
            ref = [stats[d]["tal_rows"].get(t, 0) for d in window if stats[d]["tal_rows"].get(t, 0) > 0]
            n = s["tal_rows"].get(t, 0)
            if ref and n > 0:
                med = statistics.median(ref)
                if n < SHORT_RATIO * med:
                    short[t] = {"rows": n, "local_median": med, "ratio": round(n / med, 4)}
        nulls = {k: v for k, v in s["nulls"].items() if v not in (0, None)}
        if missing or extra or short or nulls:
            flags[day] = {"missing_tals": missing, "short_tals": short, "extra_tals": extra, "nonzero_nulls": nulls}
    return flags


def affected_tals(flag: dict) -> list[str]:
    return sorted(set(flag["missing_tals"]) | set(flag["short_tals"]))


def resolve(day: str, available) -> str | None:
    """rpki_validate.roas_for: the day's file, else the nearest earlier file within FALLBACK_DAYS days, else None."""
    if day in available:
        return day
    d0 = dt.date.fromisoformat(day)
    for k in range(1, FALLBACK_DAYS + 1):
        g = (d0 - dt.timedelta(days=k)).isoformat()
        if g in available:
            return g
    return None


def calendar(start: str, end_inclusive: str) -> list[str]:
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end_inclusive)
    return [(s + dt.timedelta(days=i)).isoformat() for i in range((e - s).days + 1)]


def band(flag: dict) -> str:
    if flag["missing_tals"]:
        return "tal_absent"
    if any(v["ratio"] < NEAR_EMPTY_RATIO for v in flag["short_tals"].values()):
        return "tal_below_0.5_of_local_median"
    if flag["short_tals"]:
        return "tal_0.5_to_0.9_of_local_median"
    return "other(nulls/extra)"


def day_coverage(days: list[str], available, flags: dict, detail: bool = True) -> dict:
    resolved = {d: resolve(d, available) for d in days}
    fallback = {d: r for d, r in resolved.items() if r is not None and r != d}
    none = [d for d, r in resolved.items() if r is None]
    bad = {d: r for d, r in resolved.items() if r is not None and r in flags}
    out = {"days_checked": len(days), "first": days[0] if days else None, "last": days[-1] if days else None,
           "days_with_own_file": sum(1 for d, r in resolved.items() if r == d),
           "days_on_fallback_file": len(fallback), "days_with_no_file_within_7d": len(none),
           "days_resolving_to_unflagged_file": sum(1 for r in resolved.values() if r is not None and r not in flags),
           "days_resolving_to_flagged_file": len(bad),
           "days_resolving_to_flagged_file_by_band": dict(Counter(band(flags[r]) for r in bad.values())),
           "days_resolving_to_file_with_tal_absent": sum(1 for r in bad.values() if flags[r]["missing_tals"])}
    if detail:
        out["fallback"] = fallback
        out["no_file"] = none
        out["flagged_days"] = [{"day": d, "file": r, "band": band(flags[r]), "missing_tals": flags[r]["missing_tals"],
                                "short_tals": flags[r]["short_tals"]} for d, r in bad.items()]
    return out


# ---------------------------------------------------------------------------------------------------------------- events
def first_prev(dtype):
    import polars as pl
    if isinstance(dtype, pl.List):
        return pl.col("prev_origins").list.first().cast(pl.Int64, strict=False).alias("prev_origin")
    return pl.col("prev_origins").cast(pl.Utf8).str.extract(r"(\d+)", 1).cast(pl.Int64, strict=False).alias("prev_origin")


def dev_events(root: Path, year: int):
    """Every row of eventset/<year>/rpki_validity.parquet with the inputs scripts/rpki_validity_events.py used."""
    import polars as pl
    E = root / "eventset" / str(year)
    val = pl.read_parquet(E / "rpki_validity.parquet").select("event_id", "validity", "n_covering", "invalid_reason", "prev_validity")
    man = pl.read_csv(root / "inventory" / str(year) / "replay_manifest.tsv", separator="\t").select(
        "event_id", "prefix", pl.col("new_origin").cast(pl.Int64), pl.col("t0").str.to_datetime(strict=False))
    inv = pl.read_parquet(root / "inventory" / str(year) / "events_ranked.parquet", columns=["first_ts", "prefix", "new_origin", "prev_origins"])
    inv = inv.with_columns((pl.col("first_ts").dt.strftime("%Y%m%dT%H%M%S") + "_" + pl.col("prefix").str.replace("/", "-") + "_"
                            + pl.col("new_origin").cast(pl.Utf8)).alias("event_id"), first_prev(inv["prev_origins"].dtype)).select(
        "event_id", "prev_origin").unique("event_id")
    reason = pl.read_parquet(E / "events.parquet", columns=["event_id", "reason"])
    df = val.join(man, on="event_id", how="left").join(inv, on="event_id", how="left").join(reason, on="event_id", how="left")
    day8 = pl.col("event_id").str.slice(0, 8)
    return df.with_columns((day8.str.slice(0, 4) + "-" + day8.str.slice(4, 2) + "-" + day8.str.slice(6, 2)).alias("day"),
                           pl.lit(str(year)).alias("group"))


def r2_events(root: Path):
    """Every row of the new-period eventset/2026/rpki_validity.parquet with the inputs of the finalize kernel validate_origins."""
    import polars as pl
    val = pl.read_parquet(root / "eventset" / "2026" / "rpki_validity.parquet").select(
        "event_id", "validity", "n_covering", "invalid_reason", "prev_validity")
    sel = pl.read_parquet(root / "inventory" / "2026" / "replay_selection.parquet",
                          columns=["event_id", "prefix", "new_origin", "first_ts", "prev_origins", "reason"])
    sel = sel.with_columns(pl.col("first_ts").dt.strftime("%Y-%m-%d").alias("day"), first_prev(sel["prev_origins"].dtype),
                           pl.col("new_origin").cast(pl.Int64)).drop("prev_origins", "first_ts")
    df = val.join(sel, on="event_id", how="left")
    day8 = pl.col("event_id").str.slice(0, 8)
    return df.with_columns((day8.str.slice(0, 4) + "-" + day8.str.slice(4, 2) + "-" + day8.str.slice(6, 2)).alias("day_from_id"),
                           pl.lit("newperiod-2026").alias("group"))


def load_rows(path: Path, needed: set[str]) -> list[tuple]:
    import polars as pl
    f = pl.scan_parquet(path).filter(pl.col("prefix").is_in(sorted(needed))).select("prefix", "max_len", "asn", "tal").collect()
    return list(f.iter_rows())


def table(rows: list[tuple], keep=None):
    tab = defaultdict(list)
    for p, ml, a, t in rows:
        if keep is None or keep(t):
            tab[p].append((int(ml), int(a)))
    return tab


def needed_prefixes(rows: list[dict]) -> set[str]:
    needed = set()
    for r in rows:
        if r["prefix"] is not None:
            needed.update(supernets(r["prefix"]))
    return needed


def validate_rows(rows: list[dict], tab) -> list[tuple]:
    out = []
    for r in rows:
        if r["prefix"] is None or r["new_origin"] is None:
            out.append(("input_missing", None, None, None))
            continue
        s, c, why = validity(r["prefix"], int(r["new_origin"]), tab)
        prev = validity(r["prefix"], int(r["prev_origin"]), tab)[0] if r["prev_origin"] is not None else "unknown_prev"
        out.append((s, c, why, prev))
    return out


def reproduce(df, available: dict[str, Path], workers: int, ids_ok: bool) -> dict:
    """Re-validate every event against the file its day resolves to; compare with the stored labels."""
    import polars as pl
    groups = [(fd, g.to_dicts()) for (fd,), g in df.filter(pl.col("file_day").is_not_null()).group_by("file_day")]

    def work(item):
        fd, rows = item
        return fd, rows, validate_rows(rows, table(load_rows(available[fd], needed_prefixes(rows))))

    mism = Counter()
    examples = []
    checked = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fd, rows, res in ex.map(work, groups):
            for r, (s, c, why, prev) in zip(rows, res):
                checked += 1
                key = [name for name, a, b in (("validity", s, r["validity"]), ("n_covering", c, r["n_covering"]),
                                               ("invalid_reason", why or "", r["invalid_reason"] or ""), ("prev_validity", prev, r["prev_validity"])) if a != b]
                if key:
                    mism["+".join(key)] += 1
                    if len(examples) < 10:
                        examples.append({"event_id": r["event_id"] if ids_ok else None, "file_day": fd,
                                         "stored": [r["validity"], r["n_covering"], r["invalid_reason"], r["prev_validity"]], "recomputed": [s, c, why, prev]})
    no_file = df.filter(pl.col("file_day").is_null())
    return {"events_revalidated": checked, "events_reproduced_exactly": checked - sum(mism.values()), "mismatches": dict(mism),
            "mismatch_examples": examples, "events_without_file": no_file.height,
            "stored_class_of_events_without_file": dict(Counter(no_file["validity"].to_list()))}


def clean_neighbour(fd: str, available, flags: dict, step: int) -> str | None:
    d0 = dt.date.fromisoformat(fd)
    for k in range(1, NEIGHBOUR_SEARCH + 1):
        g = (d0 + dt.timedelta(days=step * k)).isoformat()
        if g in available and g not in flags:
            return g
    return None


def revalidate_flagged(df, available, flags: dict, ids_ok: bool) -> dict:
    """Events on a flagged file: re-validate with the affected TAL's ROAs taken from the nearest unflagged earlier / later file and
    the event day's ROAs of every other TAL ("repaired" table)."""
    import polars as pl
    sub = df.filter(pl.col("file_day").is_in(list(flags)))
    if sub.height == 0:
        return {"events": 0}
    trans = {"earlier": Counter(), "later": Counter()}
    prev_trans = {"earlier": Counter(), "later": Counter()}
    both = Counter()
    per_file = {}
    changed = []
    by_year_changes = defaultdict(Counter)
    for (fd,), g in sub.sort("file_day").group_by("file_day", maintain_order=True):
        rows = g.to_dicts()
        bad = affected_tals(flags[fd])
        need = needed_prefixes(rows)
        own = load_rows(available[fd], need)
        own_tab = table(own)
        base = validate_rows(rows, own_tab)
        info = {"events": len(rows), "affected_tals": bad, "band": band(flags[fd]), "stored": dict(Counter(r["validity"] for r in rows))}
        repaired = {}
        for side, step in (("earlier", -1), ("later", 1)):
            nd = clean_neighbour(fd, available, flags, step)
            info[f"{side}_unflagged_file"] = nd
            if nd is None or not bad:
                repaired[side] = None
                trans[side]["no_unflagged_neighbour_within_7d"] += len(rows)
                continue
            nb = load_rows(available[nd], need)
            rep_tab = table([x for x in own if x[3] not in bad] + [x for x in nb if x[3] in bad])
            repaired[side] = validate_rows(rows, rep_tab)
            for r, (s, _, _, pv) in zip(rows, repaired[side]):
                trans[side][f"{r['validity']}->{s}"] += 1
                prev_trans[side][f"{r['prev_validity']}->{pv}"] += 1
        n_changed = 0
        for i, r in enumerate(rows):
            e = repaired["earlier"][i] if repaired["earlier"] else None
            l = repaired["later"][i] if repaired["later"] else None
            states = {x[0] for x in (e, l) if x is not None}
            pstates = {x[3] for x in (e, l) if x is not None}
            if states and (states != {r["validity"]} or pstates != {r["prev_validity"]}):
                n_changed += 1
                key = f"{r['validity']}->{'/'.join(sorted(states))}"
                if len(states) == 1 and e is not None and l is not None:
                    both[key] += 1
                by_year_changes[r["group"]][key] += 1
                changed.append({"event_id": r["event_id"] if ids_ok else None, "event_day": r["day"], "file_day": fd, "affected_tals": bad,
                                "stored": [r["validity"], r["prev_validity"]], "repaired_earlier": [e[0], e[3]] if e else None,
                                "repaired_later": [l[0], l[3]] if l else None, "reason": r.get("reason")})
        info["events_with_any_label_change"] = n_changed
        info["recomputed_on_own_file_matches_stored"] = sum(1 for r, b in zip(rows, base) if b[0] == r["validity"] and b[3] == r["prev_validity"])
        per_file[fd] = info
    return {"events": sub.height, "files": len(per_file), "by_file": per_file,
            "validity_transitions_stored_to_repaired": {k: dict(v) for k, v in trans.items()},
            "prev_validity_transitions_stored_to_repaired": {k: dict(v) for k, v in prev_trans.items()},
            "validity_changes_where_earlier_and_later_repairs_agree": dict(both),
            "events_with_any_label_change": len(changed), "label_changes_by_group": {k: dict(v) for k, v in by_year_changes.items()},
            "changed_events": changed if len(changed) <= 500 else changed[:500]}


def class_counts(df) -> dict:
    import polars as pl
    out = {"validity": dict(Counter(df["validity"].to_list())),
           "invalid_reason": dict(Counter(r or "" for r in df.filter(pl.col("validity") == "invalid")["invalid_reason"].to_list())),
           "prev_validity": dict(Counter(df["prev_validity"].to_list()))}
    if "reason" in df.columns:
        out["validity_by_selection_reason"] = {str(k): dict(Counter(g["validity"].to_list())) for (k,), g in df.group_by("reason")}
    return out


# ---------------------------------------------------------------------------------------------------------------- collect
def collect(a) -> dict:
    import polars as pl
    cache: dict = {}
    out = {"kind": "roa_anchor_check_v1", "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "host": platform.node(), "polars": pl.__version__, "tals_expected": list(TALS),
           "rules": {"fetch": "scripts/fetch_roas.py: one roas.csv.xz per TAL and day from https://ftp.ripe.net/rpki/<tal>.tal/YYYY/MM/DD/; "
                              "a TAL with HTTP 404 or without asn/prefix/max-length columns is skipped silently, a header-only CSV adds no rows; "
                              "a day file is never re-fetched once written",
                     "day_selection": "src/bgbench/rpki_validate.py roas_for(day): <root>/rpki/roas/<day>.parquet, else the nearest earlier day file "
                                      "within 7 days, else no_roa_data",
                     "development_event_day": "scripts/rpki_validity_events.py: event_id[:8] (first_ts UTC day of the selected origin change)",
                     "newperiod_event_day": "finalize kernel validate_origins (.agents/operations/newperiod-family-history-stage-r3-20261024/execution/"
                                            "package-v1/kernel/replay.py): first_ts UTC day of inventory/2026/replay_selection.parquet",
                     "classes": "validity of the new origin: valid | invalid (invalid_asn | invalid_length) | unknown, no_roa_data without a file; "
                                "prev_validity of the displaced origin (unknown_prev when none)",
                     "flags": f"tal absent; tal 'short' = rows < {SHORT_RATIO} x median rows of that tal in the +-{NEIGHBOURS} neighbouring files "
                              f"(band below {NEAR_EMPTY_RATIO} reported separately); nonzero nulls; unexpected tal values",
                     "repair": "events on a flagged file are re-validated with the event day's ROAs of the unaffected TALs plus the affected TAL's ROAs "
                               f"of the nearest unflagged earlier (later) file within {NEIGHBOUR_SEARCH} days",
                     "validity_function": f"verbatim copy of src/bgbench/rpki_validate.py validity (file sha256 {VALIDITY_SHA256})"},
           "script_sha256": sha256(Path(sys.argv[0])) if sys.argv[0] not in ("-", "") and Path(sys.argv[0]).is_file() else "run from stdin"}

    # ---- development (replay 2022-01 .. 2026-08)
    dev_dir = a.dev_root / "rpki" / "roas"
    dev_stats = scan(dev_dir, cache)
    dev_flags = flag_files(dev_stats)
    dev_av = {d: Path(s["path"]) for d, s in dev_stats.items()}
    used_from = min(resolve(d, dev_av) or d for d in calendar(*a.replay_range))
    dv = out["development"] = {
        "data_root": str(a.dev_root), "roa_dir": str(dev_dir), "roa_dir_resolved": os.path.realpath(dev_dir),
        "roa_files": len(dev_stats), "first_file": next(iter(dev_stats)), "last_file": list(dev_stats)[-1],
        "roa_bytes": sum(s["bytes"] for s in dev_stats.values()),
        "files_with_tal_absent_all": {d: f["missing_tals"] for d, f in dev_flags.items() if f["missing_tals"]},
        "files_with_tal_absent_from_first_used_file": {d: f["missing_tals"] for d, f in dev_flags.items() if f["missing_tals"] and d >= used_from},
        "files_with_nulls_from_first_used_file": {d: f["nonzero_nulls"] for d, f in dev_flags.items() if f["nonzero_nulls"] and d >= used_from},
        "files_flagged_from_first_used_file": {d: f for d, f in dev_flags.items() if d >= used_from},
        "files_flagged_before_first_used_file": len([d for d in dev_flags if d < used_from]),
        "first_used_file": used_from,
        "calendar_replay_range": day_coverage(calendar(*a.replay_range), dev_av, dev_flags, detail=False)}
    dev = pl.concat([dev_events(a.dev_root, y) for y in a.dev_years], how="diagonal_relaxed")
    dev = dev.with_columns(pl.col("day").map_elements(lambda d: resolve(d, dev_av), return_dtype=pl.Utf8).alias("file_day"))
    dv["validity_files"] = {str(y): {"path": str(a.dev_root / "eventset" / str(y) / "rpki_validity.parquet"),
                                     "sha256": sha256(a.dev_root / "eventset" / str(y) / "rpki_validity.parquet")} for y in a.dev_years}
    dv["events"] = dev.height
    dv["events_missing_inputs"] = dev.filter(pl.col("prefix").is_null() | pl.col("new_origin").is_null()).height
    dv["event_days"] = day_coverage(sorted(set(dev["day"].to_list())), dev_av, dev_flags)
    dv["event_days_by_year"] = {}
    for (g,), sub in sorted(dev.group_by("group"), key=lambda x: x[0]):
        cov = day_coverage(sorted(set(sub["day"].to_list())), dev_av, dev_flags, detail=False)
        bad = sub.filter(pl.col("file_day").is_in(list(dev_flags)))
        dv["event_days_by_year"][g] = {**cov, "events": sub.height, "classes": class_counts(sub),
                                       "events_on_flagged_files": bad.height, "classes_on_flagged_files": class_counts(bad) if bad.height else {}}
    bad_dev = dev.filter(pl.col("file_day").is_in(list(dev_flags)))
    dv["events_on_flagged_files"] = {"events": bad_dev.height, "classes": class_counts(bad_dev) if bad_dev.height else {},
                                     "by_band": {b: class_counts(bad_dev.filter(pl.col("file_day").is_in([d for d in dev_flags if band(dev_flags[d]) == b])))
                                                 for b in sorted({band(dev_flags[d]) for d in set(bad_dev["file_day"].to_list())})}}
    later = dev.filter((pl.col("validity") == "invalid") & pl.col("t0").is_not_null())
    later_days = sorted({(t + dt.timedelta(days=h)).strftime("%Y-%m-%d") for t in later["t0"].to_list() for h in a.later_days})
    dv["later_validity_days"] = day_coverage(later_days, dev_av, dev_flags)
    dv["later_validity_days"].pop("fallback", None)
    if not a.no_reproduce:
        dv["reproduction"] = reproduce(dev, dev_av, a.workers, ids_ok=True)
        dv["revalidation_on_flagged_files"] = revalidate_flagged(dev, dev_av, dev_flags, ids_ok=True)

    # ---- new period (R2 window and the new-period origin validation)
    if a.r2_root:
        r2_dir = a.r2_root / "rpki" / "roas"
        r2_stats = scan(r2_dir, cache)
        first = next(iter(r2_stats))
        ctx = {**{d: s for d, s in dev_stats.items() if d < first}, **r2_stats}       # earlier files as context for the local median
        r2_flags = {d: f for d, f in flag_files(ctx).items() if d in r2_stats}
        r2_av = {d: Path(s["path"]) for d, s in r2_stats.items()}
        nv = out["newperiod"] = {
            "data_root": str(a.r2_root), "roa_dir": str(r2_dir), "roa_files": len(r2_stats), "first_file": first, "last_file": list(r2_stats)[-1],
            "resolved_file_dirs": dict(Counter(str(Path(s["resolved"]).parent) for s in r2_stats.values())),
            "files_with_tal_absent": {d: f["missing_tals"] for d, f in r2_flags.items() if f["missing_tals"]},
            "files_flagged": r2_flags,
            "calendar_r2_window": day_coverage(calendar(*a.r2_window), r2_av, r2_flags)}
        r2 = r2_events(a.r2_root)
        r2 = r2.with_columns(pl.col("day").map_elements(lambda d: resolve(d, r2_av), return_dtype=pl.Utf8).alias("file_day"))
        nv["validity_file"] = {"path": str(a.r2_root / "eventset" / "2026" / "rpki_validity.parquet"),
                               "sha256": sha256(a.r2_root / "eventset" / "2026" / "rpki_validity.parquet")}
        nv["events"] = r2.height
        nv["events_first_ts_day_differs_from_event_id_day"] = r2.filter(pl.col("day") != pl.col("day_from_id")).height
        nv["events_missing_inputs"] = r2.filter(pl.col("prefix").is_null() | pl.col("new_origin").is_null()).height
        nv["event_days"] = day_coverage(sorted(set(r2["day"].drop_nulls().to_list())), r2_av, r2_flags)
        nv["classes"] = class_counts(r2)
        bad_r2 = r2.filter(pl.col("file_day").is_in(list(r2_flags)))
        nv["events_on_flagged_files"] = {"events": bad_r2.height, "classes": class_counts(bad_r2) if bad_r2.height else {}}
        if not a.no_reproduce:
            nv["reproduction"] = reproduce(r2, r2_av, a.workers, ids_ok=False)
            nv["revalidation_on_flagged_files"] = revalidate_flagged(r2, r2_av, r2_flags, ids_ok=False)

    # ---- per-day TAL rows (evidence): day -> [ripencc, arin, apnic, lacnic, afrinic]
    out["per_day_tal_rows"] = {"columns": list(TALS), "development": {d: [s["tal_rows"].get(t, 0) for t in TALS] for d, s in dev_stats.items()}}
    if a.r2_root:
        out["per_day_tal_rows"]["newperiod"] = {d: [s["tal_rows"].get(t, 0) for t in TALS] for d, s in r2_stats.items()}
    return out


# ---------------------------------------------------------------------------------------------------------------- ripe-check
def ripe_rows(day: str, tal: str) -> dict:
    y, m, d = day.split("-")
    url = RIPE.format(tal=tal, y=y, m=m, d=d)
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        return {"url": url, "http_status": e.code}
    text = lzma.decompress(raw).decode("utf-8", errors="replace")
    lines = [x for x in text.splitlines() if x.strip()]
    return {"url": url, "http_status": 200, "bytes": len(raw), "header": lines[0] if lines else None, "data_rows": max(len(lines) - 1, 0)}


def ripe_check(doc: dict) -> dict:
    targets = {}
    for per, cov_keys in (("development", ("event_days", "later_validity_days")), ("newperiod", ("event_days", "calendar_r2_window"))):
        if per not in doc:
            continue
        for key in cov_keys:
            for f in doc[per][key].get("flagged_days", []):
                for t in sorted(set(f["missing_tals"]) | set(f["short_tals"])):
                    stored = doc["per_day_tal_rows"][per][f["file"]][list(TALS).index(t)]
                    targets[(per, f["file"], t)] = stored
    rows = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        keys = sorted(targets)
        for (per, day, tal), res in zip(keys, ex.map(lambda k: ripe_rows(k[1], k[2]), keys)):
            res.update(period=per, file_day=day, tal=tal, stored_rows=targets[(per, day, tal)])
            res["stored_equals_ripe_rows"] = res.get("data_rows") is not None and res["data_rows"] == res["stored_rows"]
            rows.append(res)
    # days that read the 7-day fallback file: is the day absent from RIPE's archive for every TAL?
    gaps = sorted({d for per, key in (("development", "event_days"), ("newperiod", "event_days"), ("newperiod", "calendar_r2_window"))
                   if per in doc for d in doc[per][key].get("fallback", {})})
    pairs = [(d, t) for d in gaps for t in TALS]
    with ThreadPoolExecutor(max_workers=6) as ex:
        status = list(ex.map(lambda k: ripe_status(*k), pairs))
    fallback_days = {d: {t: s for (dd, t), s in zip(pairs, status) if dd == d} for d in gaps}
    return {"checked_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "tal_days": len(rows),
            "stored_equals_ripe": sum(r["stored_equals_ripe_rows"] for r in rows),
            "ripe_header_only": [f"{r['file_day']} {r['tal']}" for r in rows if r.get("data_rows") == 0],
            "not_200": [f"{r['file_day']} {r['tal']} {r.get('http_status')}" for r in rows if r.get("http_status") != 200],
            "rows": rows,
            "fallback_days_ripe_http_status": fallback_days,
            "fallback_days_absent_at_ripe_for_all_tals": [d for d, v in fallback_days.items() if all(s == 404 for s in v.values())]}


def ripe_status(day: str, tal: str) -> int:
    y, m, d = day.split("-")
    try:
        with urllib.request.urlopen(urllib.request.Request(RIPE.format(tal=tal, y=y, m=m, d=d), method="HEAD"), timeout=60) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def assess(rv: dict) -> dict:
    """Separate label changes caused by the flagged anchor from ROA churn on the adjacent day: a change counts as anchor-caused only
    when the earlier and the later repair agree and differ from the stored label."""
    out = {"new_origin_both_repairs_agree_and_differ": Counter(), "displaced_origin_both_repairs_agree_and_differ": Counter(),
           "stored_unknown_covered_under_both_repairs_but_class_differs": 0, "one_repair_only_adjacent_day_roa_change": 0,
           "by_band": defaultdict(Counter), "by_group": defaultdict(Counter), "events": []}
    for c in rv.get("changed_events", []):
        e, l = c.get("repaired_earlier"), c.get("repaired_later")
        s, sp = c["stored"]
        if e and l and e[0] == l[0] != s:
            k = f"{s}->{e[0]}"
            out["new_origin_both_repairs_agree_and_differ"][k] += 1
            out["by_band"][rv["by_file"][c["file_day"]]["band"]][k] += 1
            out["by_group"][c["event_day"][:4]][k] += 1
            out["events"].append({**c, "assessment": "anchor_caused"})
        elif s == "unknown" and e and l and e[0] != "unknown" and l[0] != "unknown":
            out["stored_unknown_covered_under_both_repairs_but_class_differs"] += 1
            out["events"].append({**c, "assessment": "anchor_caused_class_ambiguous"})
        else:
            out["one_repair_only_adjacent_day_roa_change"] += 1
        if e and l and e[1] == l[1] != sp:
            out["displaced_origin_both_repairs_agree_and_differ"][f"{sp}->{e[1]}"] += 1
    return {k: (dict(v) if isinstance(v, Counter) else {kk: dict(vv) for kk, vv in v.items()} if isinstance(v, defaultdict) else v)
            for k, v in out.items()}


def summary(doc: dict) -> tuple[str, str]:
    """(one paper-usable sentence, a longer account)."""
    dv = doc["development"]
    e = dv["event_days"]
    rv = dv.get("revalidation_on_flagged_files", {})
    asm = rv.get("assessment", {})
    absent = [f for f in e["flagged_days"] if f["missing_tals"]]
    short = [f for f in e["flagged_days"] if not f["missing_tals"]]
    ratios = [v["ratio"] for f in short for v in f["short_tals"].values()]
    absent_events = sum(rv.get("by_file", {}).get(f["file"], {}).get("events", 0) for f in absent)
    absent_changes = sum(rv.get("by_file", {}).get(f["file"], {}).get("events_with_any_label_change", 0) for f in absent)
    short_events = rv.get("events", 0) - absent_events
    agree = asm.get("new_origin_both_repairs_agree_and_differ", {})
    amb = asm.get("stored_unknown_covered_under_both_repairs_but_class_differs", 0)
    rc = doc.get("ripe_archive_check", {})
    nv = doc.get("newperiod")
    absent_txt = "; ".join(f"{f['file']} ({', '.join(t.upper() for t in f['missing_tals'])})" for f in absent) or "none"
    empty_at_ripe = bool(rc) and all(f"{f['file']} {t}" in rc.get("ripe_header_only", []) for f in absent for t in f["missing_tals"])
    short_match_ripe = bool(rc) and rc.get("stored_equals_ripe") == rc.get("tal_days")
    changes = ", ".join(f"{v} {k.split('->')[0]} to {k.split('->')[1]}" for k, v in sorted(agree.items())) or "no label"
    if absent:
        one = (f"Every ROA day file read by the validation holds all five trust anchors except {absent_txt}"
               + (", whose set in RIPE's archive is empty" if empty_at_ripe else "")
               + f" ({absent_events} events; " + ("no label changes" if absent_changes == 0 else f"{absent_changes} change class")
               + " with that anchor from the adjacent days)")
    else:
        one = "Every ROA day file read by the validation holds all five trust anchors"
    if short:
        one += (f"; on {len(short)} further days {'RIPE archived' if short_match_ripe else 'the file holds'} one anchor at "
                f"{min(ratios):.0%}-{max(ratios):.0%} of its usual size, and re-validating those {short_events} events with that anchor from the "
                f"adjacent days changes {changes}"
                + (" (one more unknown origin is covered on both adjacent days)" if amb == 1 else f" ({amb} more unknown origins are covered on both adjacent days)" if amb else "")
                + f", of {dv['events']:,} events in all")
    if nv:
        one += (f"; the {nv['calendar_r2_window']['days_checked']} R2-window days and all {nv['roa_files']} new-period files are complete"
                if not nv["files_flagged"] else f"; new period: {len(nv['files_flagged'])} flagged files")
    one += "."
    stored_changed = sorted(k for k in agree if k.split("->")[0] in ("invalid", "valid"))
    long = (f"Development (replay 2022-01-01..2026-08-31): of {e['days_checked']} event days, {e['days_with_own_file']} read their own ROA day file, "
            f"{e['days_on_fallback_file']} the 7-day fallback file ({', '.join(f'{k}->{v}' for k, v in e['fallback'].items())}) and "
            f"{e['days_with_no_file_within_7d']} no file. Stored labels of all {dv['reproduction']['events_revalidated']:,} events are reproduced "
            f"exactly from these files ({dv['reproduction']['events_reproduced_exactly']:,} identical). "
            f"{len(absent)} file lacks an anchor ({absent_txt}); {len(short)} files hold one anchor below {SHORT_RATIO:.0%} of its local median "
            f"({sum(1 for f in short if band(f) == 'tal_below_0.5_of_local_median')} below 50%). {rv.get('events', 0)} events fall on these "
            f"{e['days_resolving_to_flagged_file']} days. Repairing the affected anchor from the nearest unflagged earlier and later day: "
            f"new-origin changes where both repairs agree {agree or 'none'}, displaced-origin {asm.get('displaced_origin_both_repairs_agree_and_differ') or 'none'}, "
            f"{amb} stored unknown covered under both repairs with differing class, {asm.get('one_repair_only_adjacent_day_roa_change', 0)} changes under "
            f"one repair only (ROA churn on the adjacent day). Stored valid or invalid labels that change under both repairs: "
            f"{', '.join(stored_changed) or 'none'}. ")
    if rc:
        long += (f"RIPE archive today: {rc['stored_equals_ripe']} of {rc['tal_days']} flagged anchor-days match the archived roas.csv row count"
                 + (f"; header-only at RIPE: {', '.join(rc['ripe_header_only'])}" if rc["ripe_header_only"] else "")
                 + (f"; not HTTP 200: {', '.join(rc['not_200'])}" if rc["not_200"] else "") + ". ")
        fb = rc.get("fallback_days_ripe_http_status", {})
        if fb:
            long += (f"Of the {len(fb)} days that read the fallback file, {len(rc['fallback_days_absent_at_ripe_for_all_tals'])} are absent from "
                     f"RIPE's archive for all five anchors (HTTP 404). ")
    lv = dv["later_validity_days"]
    long += (f"later_validity.py (t0+7/t0+30 of invalid events) reads {lv['days_checked']} days: {lv['days_resolving_to_flagged_file']} on flagged files, "
             f"{lv['days_with_no_file_within_7d']} without file ({', '.join(lv['no_file'][:1] + ['..'] + lv['no_file'][-1:]) if lv['no_file'] else 'none'}). ")
    if nv:
        w, ne = nv["calendar_r2_window"], nv["event_days"]
        long += (f"New period: {nv['roa_files']} files {nv['first_file']}..{nv['last_file']}, {len(nv['files_flagged'])} flagged; the {w['days_checked']} R2-window "
                 f"days and {ne['days_checked']} event days all read their own file; stored labels of {nv['reproduction']['events_revalidated']:,} new-period "
                 f"events reproduced exactly ({nv['reproduction']['events_reproduced_exactly']:,}).")
    return one, long.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--dev-root", type=Path, required=True, help="data root of the corrected release (eventset/<year>, inventory/<year>, rpki/roas)")
    c.add_argument("--dev-years", type=int, nargs="+", default=[2022, 2023, 2024, 2025, 2026])
    c.add_argument("--replay-range", nargs=2, default=["2022-01-01", "2026-08-31"])
    c.add_argument("--r2-root", type=Path, help="new-period finalize output root (eventset/2026, inventory/2026, rpki/roas)")
    c.add_argument("--r2-window", nargs=2, default=["2026-09-01", "2026-10-15"], help="inclusive; primary.json evaluation_window end_exclusive 2026-10-16")
    c.add_argument("--later-days", type=int, nargs="+", default=[7, 30])
    c.add_argument("--workers", type=int, default=12)
    c.add_argument("--no-reproduce", action="store_true")
    r = sub.add_parser("ripe-check")
    r.add_argument("collected", type=Path)
    r.add_argument("--offline", action="store_true", help="skip the RIPE downloads, only add the summary")
    a = ap.parse_args()
    if a.cmd == "collect":
        doc = collect(a)
    else:
        doc = json.loads(a.collected.read_text())
        doc["script_sha256"] = sha256(Path(__file__))
        doc["collected_from"] = str(a.collected)
        if not a.offline:
            doc["ripe_archive_check"] = ripe_check(doc)
    for per in ("development", "newperiod"):
        rv = doc.get(per, {}).get("revalidation_on_flagged_files")
        if rv and rv.get("events"):
            rv["assessment"] = assess(rv)
    one, long = summary(doc)
    doc.pop("summary", None)
    doc.pop("summary_detail", None)
    doc = {"summary": one, "summary_detail": long, **doc}
    json.dump(doc, sys.stdout, indent=1, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
