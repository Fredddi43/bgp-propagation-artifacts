"""RPKI origin validation (RFC 6811) of every replayed origin-change event's new origin against the ROAs published on
that day (rpki/roas/<day>.parquet from the RIPE archive), and how propagation differs by validity state.
Writes eventset/<year>/rpki_validity.parquet (event_id, validity, n_covering, split) and rpki_validity_summary.json:
per validity state — events, share, median 2-h extent, persistence Jaccard 30 s → 2 h, still-growing fraction at 30 s.
usage: rpki_validity_events.py <year>"""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import sys
from collections import Counter, defaultdict

import polars as pl

from bgbench import config

year = int(sys.argv[1])
E = config.DATA_ROOT / "eventset" / str(year)
ev = pl.read_parquet(E / "events.parquet").filter(pl.col("error").is_null())
man = pl.read_csv(config.DATA_ROOT / "inventory" / str(year) / "replay_manifest.tsv", separator="\t").select(
    "event_id", "prefix", pl.col("new_origin").cast(pl.Int64), pl.col("t0").str.to_datetime(strict=False))
ev = ev.join(man, on="event_id", how="inner").with_columns(pl.col("event_id").str.slice(0, 8).alias("day8"))
inv = pl.read_parquet(config.DATA_ROOT / "inventory" / str(year) / "events_ranked.parquet").with_columns(
    (pl.col("first_ts").dt.strftime("%Y%m%dT%H%M%S") + "_" + pl.col("prefix").str.replace("/", "-") + "_" + pl.col("new_origin").cast(pl.Utf8)).alias("event_id"),
    pl.col("prev_origins").cast(pl.Utf8).str.extract(r"(\d+)", 1).cast(pl.Int64, strict=False).alias("prev_origin")).select("event_id", "prev_origin", "plen").unique("event_id")
ev = ev.join(inv, on="event_id", how="left")
roa_cache: dict[str, dict | None] = {}


def roas_for(day: str):
    if day in roa_cache:
        return roa_cache[day]
    roa_cache.clear()          # one day's table at a time (events are processed in day order); 366 tables OOM'd at 48 GB
    f = config.DATA_ROOT / "rpki" / "roas" / f"{day}.parquet"
    if not f.exists():        # a gap day: use the nearest earlier day within a week
        d0 = dt.date.fromisoformat(day)
        for k in range(1, 8):
            g = config.DATA_ROOT / "rpki" / "roas" / f"{(d0 - dt.timedelta(days=k)).isoformat()}.parquet"
            if g.exists():
                f = g
                break
        else:
            roa_cache[day] = None
            return None
    tab = defaultdict(list)
    for p, ml, a in pl.read_parquet(f).select("prefix", "max_len", "asn").iter_rows():
        tab[p].append((int(ml), int(a)))
    roa_cache[day] = tab
    return tab


def validity(prefix: str, origin: int, tab) -> tuple[str, int, str]:
    """(state, n_covering, reason): RFC 6811 with the invalid reason split into invalid_length (a ROA names this origin but its
    maxLength is shorter than the announced prefix — the classic TE more-specific) vs invalid_asn (no ROA names the origin)."""
    net = ipaddress.ip_network(prefix, strict=False)
    covering = 0
    valid = False
    asn_match_too_long = False
    floor = 8 if net.version == 4 else 16
    for plen in range(net.prefixlen, floor - 1, -1):
        sup = net if plen == net.prefixlen else net.supernet(new_prefix=plen)
        for ml, a in tab.get(str(sup), ()):
            if net.prefixlen <= ml:
                covering += 1
                if a == origin:
                    valid = True
            elif a == origin:
                asn_match_too_long = True
    state = "valid" if valid else ("invalid" if covering else "unknown")
    reason = "" if state != "invalid" else ("invalid_length" if asn_match_too_long else "invalid_asn")
    return state, covering, reason


rows = []
for r in ev.select("event_id", "prefix", "new_origin", "prev_origin", "day8", "split").sort("day8").iter_rows(named=True):
    day = f"{r['day8'][:4]}-{r['day8'][4:6]}-{r['day8'][6:8]}"
    tab = roas_for(day)
    if tab is None:
        rows.append({"event_id": r["event_id"], "validity": "no_roa_data", "n_covering": 0, "invalid_reason": "", "prev_validity": "no_roa_data", "split": r["split"]})
        continue
    v, n, reason = validity(r["prefix"], int(r["new_origin"]), tab)
    pv = validity(r["prefix"], int(r["prev_origin"]), tab)[0] if r["prev_origin"] is not None else "unknown_prev"
    rows.append({"event_id": r["event_id"], "validity": v, "n_covering": n, "invalid_reason": reason, "prev_validity": pv, "split": r["split"]})
val = pl.DataFrame(rows)

# origin cone size (CAIDA ppdc-ases) and provider count (CAIDA as-rel p2c) of the new origin, from the event's month
from bgbench.diffusion import load_cone  # noqa: E402

cone_cache: dict[str, dict] = {}
prov_cache: dict[str, dict] = {}


def cone_and_upstreams(month: str, asn: int) -> tuple[int | None, int | None]:
    if month not in cone_cache:
        cone_cache.clear(); prov_cache.clear()
        try:
            cone_cache[month] = load_cone(month.replace("-", ""))      # load_cone takes "YYYYMM"
        except Exception:  # noqa: BLE001
            cone_cache[month] = {}
        f = config.DATA_ROOT / "graphs" / f"{month.replace('-', '')}01.rel.parquet"
        pc = defaultdict(int)
        if f.exists():
            for u, v, kind in pl.read_parquet(f).iter_rows():   # kind "provider": v is a provider of u
                if kind == "provider":
                    pc[int(u)] += 1
        prov_cache[month] = pc
    return cone_cache[month].get(asn), prov_cache[month].get(asn, 0)


cu = [cone_and_upstreams(f"{r['day8'][:4]}-{r['day8'][4:6]}", int(r["new_origin"])) for r in ev.select("day8", "new_origin").sort("day8").iter_rows(named=True)]
ids_sorted = ev.sort("day8")["event_id"].to_list()
val = val.join(pl.DataFrame({"event_id": ids_sorted, "cone": [c for c, _ in cu], "n_providers": [u for _, u in cu]}), on="event_id", how="left")

# GRIP as a second labeller: MOAS events with attackers == new origin, the prefix listed, |view_ts − t₀| ≤ 30 min; its newcomer RPKI tag
gf = config.DATA_ROOT / "labels" / f"{year}-01-01_{year + 1}-01-01" / "grip.parquet"
if gf.exists():
    import re
    g = pl.read_parquet(gf).filter(pl.col("event_type") == "moas").with_columns(pl.col("attackers").cast(pl.Utf8).str.extract(r"(\d+)", 1).cast(pl.Int64, strict=False).alias("attacker"),
                                                                                pl.col("view_ts").dt.replace_time_zone(None))
    cand = ev.select("event_id", "prefix", pl.col("new_origin").cast(pl.Int64), pl.col("t0")).join(
        g.select("id", "attacker", "prefixes", "view_ts", "tags"), left_on="new_origin", right_on="attacker", how="inner").filter((pl.col("t0") - pl.col("view_ts")).dt.total_seconds().abs() <= 1800)
    grows = []
    for r in cand.iter_rows(named=True):
        if r["prefix"] in set(re.findall(r"[0-9a-fA-F:.]+/\d+", r["prefixes"] or "")):
            tag = next((t for t in (r["tags"] or "").split(",") if t.startswith("rpki-") and "newcomer" in t), "")
            grows.append({"event_id": r["event_id"], "grip_id": r["id"], "grip_rpki_newcomer": tag})
    gm = pl.DataFrame(grows).unique("event_id", keep="first") if grows else pl.DataFrame({"event_id": [], "grip_id": [], "grip_rpki_newcomer": []}, schema={"event_id": pl.Utf8, "grip_id": pl.Utf8, "grip_rpki_newcomer": pl.Utf8})
    val = val.join(gm, on="event_id", how="left").with_columns(pl.col("grip_id").is_not_null().alias("grip_labelled"))
else:
    val = val.with_columns(pl.lit(None, dtype=pl.Utf8).alias("grip_id"), pl.lit(None, dtype=pl.Utf8).alias("grip_rpki_newcomer"), pl.lit(False).alias("grip_labelled"))
val.write_parquet(E / "rpki_validity.parquet")


def jacc(a, b):
    sa, sb = set(a or []), set(b or [])
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 1.0


j = ev.join(val.select("event_id", "validity", "prev_validity", "invalid_reason", "cone", "n_providers", "grip_labelled", "grip_rpki_newcomer"), on="event_id").with_columns(
    pl.struct(["set_d30s", "set_final_2h"]).map_elements(lambda s: jacc(s["set_d30s"], s["set_final_2h"]), return_dtype=pl.Float64).alias("j30"),
    (pl.col("set_final_2h").list.len().fill_null(0) > pl.col("set_d30s").list.len().fill_null(0)).alias("growing30"))
summ = {"year": year, "events": j.height, "by_validity": {}}
for (v,), g in j.group_by("validity"):
    t = g.filter(pl.col("split") == "test")
    summ["by_validity"][v] = {
        "n": g.height, "share": round(g.height / j.height, 4), "labelled_share": round(float(g["labelled"].mean()), 4),
        "asns_final_2h_p50": float(g["asns_final_2h"].median()), "asns_final_2h_p90": float(g["asns_final_2h"].quantile(0.9)),
        "collectors_seeing_p50": float(g["collectors_seeing"].median()),
        "persist_j30_test_mean": round(float(t["j30"].mean()), 4) if t.height else None, "n_test": t.height,
        "growing_at_30s_frac": round(float(g["growing30"].mean()), 4), "duration_min_p50": float(g["duration_min"].median())}


def strat(g: pl.DataFrame) -> dict:
    t = g.filter(pl.col("split") == "test")
    return {"n": g.height, "asns_final_2h_p50": float(g["asns_final_2h"].median()), "duration_min_p50": float(g["duration_min"].median()),
            "persist_j30_test_mean": round(float(t["j30"].mean()), 4) if t.height else None, "n_test": t.height,
            "growing_at_30s_frac": round(float(g["growing30"].mean()), 4), "labelled_share": round(float(g["labelled"].mean()), 4)}


# controls: the displaced origin's validity (invalid displacing a valid origin = the textbook hijack ROV is meant to stop),
# prefix length, Radar label
summ["by_validity_x_prev"] = {f"{v}|prev={pv}": strat(g) for (v, pv), g in j.group_by("validity", "prev_validity") if g.height >= 50}
j = j.with_columns(pl.when(pl.col("plen") <= 16).then(pl.lit("<=16")).when(pl.col("plen") <= 22).then(pl.lit("17-22")).when(pl.col("plen") == 24).then(pl.lit("24"))
                     .when(pl.col("plen") < 24).then(pl.lit("23")).otherwise(pl.lit("v6/other")).alias("plen_bucket"))
summ["by_validity_x_plen"] = {f"{v}|/{pb}": strat(g) for (v, pb), g in j.group_by("validity", "plen_bucket") if g.height >= 50}
summ["by_validity_x_labelled"] = {f"{v}|radar={lab}": strat(g) for (v, lab), g in j.group_by("validity", "labelled") if g.height >= 50}
summ["by_invalid_reason"] = {f"{v}|{rs or '-'}": strat(g) for (v, rs), g in j.group_by("validity", "invalid_reason") if g.height >= 50}
j = j.with_columns(pl.when(pl.col("cone").is_null()).then(pl.lit("cone=?")).when(pl.col("cone") <= 1).then(pl.lit("cone=1 (stub)")).when(pl.col("cone") <= 10).then(pl.lit("cone 2-10"))
                     .when(pl.col("cone") <= 100).then(pl.lit("cone 11-100")).otherwise(pl.lit("cone >100")).alias("cone_bucket"),
                   pl.when(pl.col("n_providers") <= 1).then(pl.lit("1 provider")).when(pl.col("n_providers") <= 3).then(pl.lit("2-3 providers")).otherwise(pl.lit(">3 providers")).alias("prov_bucket"))
summ["by_validity_x_cone"] = {f"{v}|{cb}": strat(g) for (v, cb), g in j.group_by("validity", "cone_bucket") if g.height >= 50}
summ["by_validity_x_providers"] = {f"{v}|{pb}": strat(g) for (v, pb), g in j.group_by("validity", "prov_bucket") if g.height >= 50}
# incident-level view: one origin re-originating many prefixes within the same hour is one incident, not N events; report
# floors averaged first within incident then across incidents so a single mass event cannot dominate a class
j = j.with_columns((pl.col("new_origin").cast(pl.Utf8) + "@" + pl.col("event_id").str.slice(0, 11)).alias("incident"))
inc = (j.group_by("validity", "incident").agg(n_events=pl.len(), j30=pl.col("j30").mean(), reach=pl.col("asns_final_2h").median(), growing=pl.col("growing30").mean(),
                                               test=(pl.col("split") == "test").mean()))
summ["by_validity_incident_weighted"] = {}
for (v,), g in inc.group_by("validity"):
    t = g.filter(pl.col("test") > 0)
    summ["by_validity_incident_weighted"][v] = {"incidents": g.height, "events": int(g["n_events"].sum()), "events_per_incident_p50_p90_max": [float(g["n_events"].quantile(q)) for q in (0.5, 0.9)] + [int(g["n_events"].max())],
                                                 "largest_incident": g.sort("n_events", descending=True)["incident"][0],
                                                 "persist_j30_incident_mean": round(float(t["j30"].mean()), 4) if t.height else None, "reach_p50_of_incident_medians": float(g["reach"].median()),
                                                 "growing_at_30s_incident_mean": round(float(g["growing"].mean()), 4)}
summ["grip"] = {"grip_labelled_share_by_validity": {v: round(float(g["grip_labelled"].mean()), 4) for (v,), g in j.group_by("validity")},
                "grip_newcomer_rpki_tag_by_validity": {v: dict(Counter(g.filter(pl.col("grip_labelled"))["grip_rpki_newcomer"].to_list()).most_common(4)) for (v,), g in j.group_by("validity")}}
print(json.dumps(summ, indent=1))
(E / "rpki_validity_summary.json").write_text(json.dumps(summ, indent=1))
