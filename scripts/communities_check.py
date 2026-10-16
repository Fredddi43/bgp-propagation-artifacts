"""Communities check (collaborator suggestion, 2026-09-15): on the March-2025 communities-preserving replays (tags comm, leakcomm),
test whether BGP communities carry information about anomalies.
  (a) presence and count of communities on hijack announcements (new origin) vs the legitimate route's announcements of the same
      prefix in the same window, by RPKI validity of the new origin;
  (b) RPKI-state marking communities from transits and route servers (table in docs/research/rpki_marking_communities.json:
      {"<asn>:<value>" or "<asn>:<fn>:<lp>": "valid|invalid|unknown", ...}) on invalid vs valid new origins — a "valid" marking on an
      RPKI-invalid announcement is the collaborator's misleading case;
  (c) well-known communities: BLACKHOLE 65535:666 (RFC 7999), NO_EXPORT 65535:65281, NO_ADVERTISE 65535:65282, GRACEFUL_SHUTDOWN 65535:0;
  (d) leaks: communities on leaked announcements vs the same prefixes' announcements through other paths that day;
  (e) does community presence at onset relate to 2-h extent (Spearman) within class.
usage: communities_check.py [year=2025]"""
from __future__ import annotations

import json
import sys
from collections import Counter

import numpy as np
import polars as pl
from scipy.stats import spearmanr

from bgbench import config
from bgbench.replay_day import roots

year = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
D = config.DATA_ROOT
mark_f = config.REPO_ROOT / "docs" / "research" / "rpki_marking_communities.json" if hasattr(config, "REPO_ROOT") else None
table: dict = {}
for cand in [mark_f, "docs/research/rpki_marking_communities.json"]:
    try:
        table = json.load(open(cand)); break
    except Exception:
        continue
marks: dict[str, str] = dict(table.get("marks", {}))
EUROIX = table.get("euroix_rs_large_suffix", {})
BLACKHOLE = set(table.get("blackhole", ["65535:666"]))
REL = table.get("relationship_tags", {})
import re
def mark_of(c: str) -> str | None:
    """RPKI state a community claims, or None. Handles operator tags and the Euro-IX RS large-community scheme RS:1000:X."""
    if c in marks:
        return marks[c]
    m = re.fullmatch(r"(\d+):1000:(\d)", c)
    if m and m.group(2) in EUROIX:
        return EUROIX[m.group(2)]
    return None
print("marking communities known:", len(marks), "+ Euro-IX RS scheme; blackhole values:", len(BLACKHOLE), flush=True)
WELL = {"65535:666": "blackhole", "65535:65281": "no_export", "65535:65282": "no_advertise", "65535:0": "graceful_shutdown", "65535:65283": "no_export_subconfed"}
val = pl.read_parquet(D / "eventset" / str(year) / "rpki_validity.parquet").select("event_id", "validity")
ev = pl.read_parquet(D / "eventset" / str(year) / "events.parquet").select("event_id", "asns_final_2h").join(val, on="event_id")
parts_root, root = roots("comm")
rows = []
for r in ev.iter_rows(named=True):
    d = root / r["event_id"]
    if not (d / "anomalous.parquet").exists():
        continue
    # the per-collector parts hold every announcement of the prefix in the window (any origin); anomalous.parquet keeps only the
    # new-origin rows, so the legitimate route's rows come from the parts
    pfiles = list((parts_root / r["event_id"]).glob("*.parquet")) if (parts_root / r["event_id"]).exists() else []
    a = pl.concat([pl.read_parquet(f) for f in pfiles], how="diagonal_relaxed") if pfiles else pl.read_parquet(d / "anomalous.parquet")
    if "communities" not in a.columns or a.is_empty():
        continue
    new_origin = int(r["event_id"].rsplit("_", 1)[1])
    def stats(df: pl.DataFrame) -> dict:
        if df.is_empty():
            return {"n": 0}
        comm = df["communities"].fill_null([]).to_list()
        flat = Counter(c for cs in comm for c in cs)
        n = len(comm)
        return {"n": n, "with_any": sum(1 for cs in comm if cs) / n, "mean_count": float(np.mean([len(cs) for cs in comm])),
                "distinct": len(flat), "well": {k: sum(1 for cs in comm if k in cs) / n for k in WELL},
                "mark_valid": sum(1 for cs in comm if any(mark_of(c) == "valid" for c in cs)) / n,
                "mark_invalid": sum(1 for cs in comm if any(mark_of(c) == "invalid" for c in cs)) / n,
                "mark_unknown": sum(1 for cs in comm if any(mark_of(c) == "unknown" for c in cs)) / n,
                "any_blackhole": sum(1 for cs in comm if any(c in BLACKHOLE for c in cs)) / n,
                "rfc8097_like": sum(1 for cs in comm if any(re.search(r"(?i)rpki|0x43|^17152:[012]$|^67:0:|^0:67:", c) for c in cs)) / n,
                "ext_top": Counter(c for cs in comm for c in cs if c.count(":") == 3).most_common(3),
                "rel_customer": sum(1 for cs in comm if any(REL.get(c) == "customer" for c in cs)) / n,
                "rel_peer": sum(1 for cs in comm if any(REL.get(c) == "peer" for c in cs)) / n,
                "top": flat.most_common(5)}
    hij = a.filter(pl.col("origin_asn") == new_origin)
    legit = a.filter(pl.col("origin_asn") != new_origin)     # the previous origin's announcements of the same prefix in the same window
    hs, ls = stats(hij), stats(legit)
    def plen(df):
        return float(np.mean([len(p.split()) for p in df["as_path"].to_list()])) if df.height else float("nan")
    def per_hop(df):
        c = df["communities"].fill_null([]).to_list(); L = [len(p.split()) for p in df["as_path"].to_list()]
        return float(np.mean([len(cs) / max(l, 1) for cs, l in zip(c, L)])) if c else float("nan")
    rows.append({"event_id": r["event_id"], "validity": r["validity"], "asns_final_2h": r["asns_final_2h"], "hijack": hs, "legit": ls,
                 "paired": {"count_diff": hs["mean_count"] - ls["mean_count"], "withany_diff": hs["with_any"] - ls["with_any"],
                            "shared_top": len(set(c for c, _ in hs["top"]) & set(c for c, _ in ls["top"])),
                            "plen_diff": plen(hij) - plen(legit), "perhop_diff": per_hop(hij) - per_hop(legit),
                            "hij_plen": plen(hij), "leg_plen": plen(legit), "hij_perhop": per_hop(hij), "leg_perhop": per_hop(legit)} if hs["n"] and ls["n"] else None})
print("events with communities:", len(rows), flush=True)
def agg(cls: str, side: str) -> dict:
    xs = [x[side] for x in rows if x["validity"] == cls and x[side]["n"] > 0]
    if not xs:
        return {"events": 0}
    out = {"events": len(xs), "with_any": round(float(np.mean([x["with_any"] for x in xs])), 3), "mean_count": round(float(np.mean([x["mean_count"] for x in xs])), 2),
           "mark_valid": round(float(np.mean([x["mark_valid"] for x in xs])), 4), "mark_invalid": round(float(np.mean([x["mark_invalid"] for x in xs])), 4), "mark_unknown": round(float(np.mean([x["mark_unknown"] for x in xs])), 4),
           "events_with_valid_mark": sum(1 for x in xs if x["mark_valid"] > 0), "events_with_invalid_mark": sum(1 for x in xs if x["mark_invalid"] > 0),
           "any_blackhole": round(float(np.mean([x["any_blackhole"] for x in xs])), 4), "rfc8097_like": round(float(np.mean([x["rfc8097_like"] for x in xs])), 4),
           "rel_customer": round(float(np.mean([x["rel_customer"] for x in xs])), 4), "rel_peer": round(float(np.mean([x["rel_peer"] for x in xs])), 4)}
    for k, name in WELL.items():
        out[name] = round(float(np.mean([x["well"][k] for x in xs])), 4)
    top = Counter()
    for x in xs:
        for c, n in x["top"]:
            top[c] += n
    out["top_communities"] = top.most_common(10)
    ext = Counter()
    for x in xs:
        for c, n in x.get("ext_top", []):
            ext[c] += n
    out["top_extended"] = ext.most_common(8)
    return out
summary = {"year": year, "month": "2025-03", "events": len(rows), "by_class": {cls: {"hijack_rows": agg(cls, "hijack"), "legit_rows": agg(cls, "legit")} for cls in ("invalid", "unknown", "valid")}}
for cls in ("invalid", "unknown", "valid"):
    pr = [x["paired"] for x in rows if x["validity"] == cls and x["paired"]]
    if pr:
        summary["by_class"][cls]["paired"] = {"events": len(pr), "hijack_minus_legit_count_mean": round(float(np.mean([p["count_diff"] for p in pr])), 2),
                                             "hijack_fewer_frac": round(float(np.mean([p["count_diff"] < 0 for p in pr])), 3),
                                             "hijack_minus_legit_withany_mean": round(float(np.mean([p["withany_diff"] for p in pr])), 3),
                                             "shared_top_mean": round(float(np.mean([p["shared_top"] for p in pr])), 2),
                                             "path_len_hijack_vs_legit": [round(float(np.nanmean([p["hij_plen"] for p in pr])), 2), round(float(np.nanmean([p["leg_plen"] for p in pr])), 2)],
                                             "hijack_shorter_frac": round(float(np.mean([p["plen_diff"] < 0 for p in pr])), 3),
                                             "communities_per_hop_hijack_vs_legit": [round(float(np.nanmean([p["hij_perhop"] for p in pr])), 2), round(float(np.nanmean([p["leg_perhop"] for p in pr])), 2)],
                                             "hijack_fewer_per_hop_frac": round(float(np.mean([p["perhop_diff"] < 0 for p in pr])), 3),
                                             "spearman_countdiff_vs_plendiff": [round(float(x), 3) for x in spearmanr([p["count_diff"] for p in pr], [p["plen_diff"] for p in pr])[:2]]}
# (e) community presence at onset vs extent, within class
from scipy.stats import spearmanr
for cls in ("invalid", "unknown", "valid"):
    xs = [(x["hijack"]["with_any"], x["asns_final_2h"]) for x in rows if x["validity"] == cls and x["hijack"]["n"] > 0 and x["asns_final_2h"] is not None]
    if len(xs) > 20:
        rho, p = spearmanr([a for a, _ in xs], [b for _, b in xs]); summary["by_class"][cls]["spearman_withany_vs_extent"] = [round(float(rho), 3), round(float(p), 4), len(xs)]
# (d) leaks
_, lroot = roots("leakcomm")
lrows = []
for d in sorted(lroot.glob("*")):
    f = d / "anomalous.parquet"
    if not f.exists():
        continue
    a = pl.read_parquet(f)
    if "communities" not in a.columns or a.is_empty():
        continue
    comm = a["communities"].fill_null([]).to_list(); n = len(comm)
    lrows.append({"event_id": d.name, "n": n, "with_any": sum(1 for cs in comm if cs) / n, "mean_count": float(np.mean([len(cs) for cs in comm])),
                  "blackhole": sum(1 for cs in comm if any(c in BLACKHOLE for c in cs)) / n, "no_export": sum(1 for cs in comm if "65535:65281" in cs) / n,
                  "rel_customer": sum(1 for cs in comm if any(REL.get(c) == "customer" for c in cs)) / n, "rel_peer": sum(1 for cs in comm if any(REL.get(c) == "peer" for c in cs)) / n,
                  "mark_valid": sum(1 for cs in comm if any(mark_of(c) == "valid" for c in cs)) / n, "mark_invalid": sum(1 for cs in comm if any(mark_of(c) == "invalid" for c in cs)) / n})
if lrows:
    summary["leaks"] = {"events": len(lrows), "with_any": round(float(np.mean([x["with_any"] for x in lrows])), 3), "mean_count": round(float(np.mean([x["mean_count"] for x in lrows])), 2),
                        "blackhole": round(float(np.mean([x["blackhole"] for x in lrows])), 4), "no_export": round(float(np.mean([x["no_export"] for x in lrows])), 4),
                        "rel_customer": round(float(np.mean([x["rel_customer"] for x in lrows])), 4), "rel_peer": round(float(np.mean([x["rel_peer"] for x in lrows])), 4),
                        "events_with_peer_tag": sum(1 for x in lrows if x["rel_peer"] > 0), "events_with_customer_tag": sum(1 for x in lrows if x["rel_customer"] > 0),
                        "mark_valid": round(float(np.mean([x["mark_valid"] for x in lrows])), 4), "mark_invalid": round(float(np.mean([x["mark_invalid"] for x in lrows])), 4)}
out = D / "inventory" / str(year) / "communities_check.json"
out.write_text(json.dumps(summary, indent=1, default=str)); print(json.dumps(summary, indent=1, default=str))
