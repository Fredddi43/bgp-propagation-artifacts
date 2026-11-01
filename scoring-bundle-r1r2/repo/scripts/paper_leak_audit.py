#!/usr/bin/env python3
"""Bounded benchmark-validity audit of the R1 test leaks (revision analysis, review round 5, Codex W1).

Population: the R1 test cohort (the 3,543 test events of the R1 manifests, identical at 30 and 60 s), joined to the
released 2025 leak table (data/corrected-release-20261016/eventset/2025_leak/events.parquet). Strata: selection reason
(``labelled`` = Radar-matched, ``top`` = volume-selected) x identifier date (the YYYYMMDD prefix of event_id: the 1st of
a month vs any other day). Sample: up to ``--per-stratum`` events per stratum (all if fewer), drawn without replacement by
numpy default_rng(seed 1701), strata in fixed order, events sorted by event_id within a stratum.

Evidence per sampled event (all from data the pipeline already holds; nothing is downloaded):

* identifier record (leak_events/<month>/events_leak_like_m2.parquet, ``bgbench leak-events``): t0, t_last, bins,
  identifier duration, triples, collectors, messages, upstreams, sources, prefixes, Radar match flag;
* leaking triples (identifier2/<month>/leakcheck4_m2/new_triples_classified.parquet, ``bgbench leakcheck4``): the
  valley-violating triples (x, a, b) of leaker a with first_ts in [t0 - 1 min, t_last + 5 min], exactly the window of
  bgbench.select_leak_replay (checked against the replay manifest's sources/upstreams);
* CAIDA serial-1 relationships (graphs/YYYYMM01.rel.parquet, bgbench.leakcheck.relationship_table) of the event month
  (the month the identifier classified with, jobs/inventory_year.sh ``--month $Y$m``; recomputed and checked) and of
  the FOLLOWING month; the previous month is recorded as context only;
* whether each triple was also a valley-violating new triple in the PREVIOUS month's classified triples (the identifier
  tests novelty per calendar month, so a long-lived path reappears every month);
* Cloudflare Radar leak labels (labels/2025-01-01_2026-01-01/cloudflare_leaks.parquet), matched as the pipeline does
  (leaker = leak_seg[1], |t0 - min_ts| <= 10 min), with the label's peer count, prefix count, leak type and whether
  its segment {leak_seg[0], leak_seg[2]} equals {x, b} of one of the event's triples;
* the released table: replay observation lag (negative = the anomalous route was already visible before the identifier
  time; -3600 s is the start of the one-hour look-back), collectors, sessions, leaked prefixes, final reach.

AS-to-organisation siblings (``--as2org``, revision round 6, Codex W1; evidence the identifier does not use, downloaded
for this audit and not part of the pipeline data): CAIDA AS Organizations snapshots
(https://publicdata.caida.org/datasets/as-organizations/, YYYYMM01.as-org2info.txt.gz,
doi:10.21986/CAIDA.DATA.AS-TO-ORG-MAPPING), which CAIDA builds monthly from RIR/NIR WHOIS records plus a hand-kept
families list, not from BGP paths. Each event uses the latest snapshot dated on or before the first day of its identifier
month (20250901, 20251001, 20251101, 20251201 for the R1 test months); the header date must equal the file name's month.
Per recovered triple (x, a, b): the org_id of x, a and b, and whether x~a and a~b are siblings (same org_id; None if an AS
is absent from the snapshot). Per event: whether any triple has a sibling adjacency, and a sibling status over the
triples that are ``violating`` next month: ``independent`` (at least one has no sibling adjacency), ``sibling_only``
(every one has a sibling adjacency, so the valley violation may be a route inside one organisation: a likely false
positive by evidence independent of the relationship files), ``no_violating_triple`` (rules A0, A1, F1, F2);
``status_strict`` counts a triple as independent only if x, a and b are all in the snapshot. The status is a descriptor:
it does not enter the rules below. It is cross-tabulated with the class per stratum (Wilson 95 %) and weighted by stratum
size like the cohort estimate. Limits: the snapshots are themselves inferred from WHOIS, so they miss siblings registered
under different organisation records, and a sibling adjacency does not show intent. Without ``--as2org`` the sibling
fields read ``not_evaluable``.

Classification rules, applied in this order; the first that fires is recorded (``rule``):

  A0 ambiguous   / no_triple          no valley-violating triple of the leaker is recovered in the event window.
  Next-month status of a triple: ``violating`` (both adjacencies known next month, both provider or peer);
  ``valley_free`` (at least one adjacency is a customer link next month, so a's export is valley-free);
  ``missing`` (otherwise: an adjacency absent from next month's file).
  A1 ambiguous   / radar_conflict     no triple is ``violating`` next month, but Radar matched the event.
  F1 likely FP   / rel_changed_next   no triple is ``violating`` next month and at least one is ``valley_free``:
                                      the valley-free violation rests on a relationship CAIDA infers differently a
                                      month later (inference instability or a complex relationship).
  F2 likely FP   / rel_missing_next   every triple has an adjacency missing from next month's file: the violation
                                      rests on adjacencies that do not persist.
  A2 ambiguous   / preexisting_path   some triple is ``violating`` in both months, but the replay saw the anomalous
                                      route from the start of its one-hour look-back (observation lag <= -3540 s) and
                                      every such triple was already a valley-violating new triple in the previous
                                      month: the path predates the event, so a long-lived leak and a recurring benign
                                      configuration cannot be told apart.
  C1 credible    / stable_violation   some triple is ``violating`` in both months and A2 does not fire (``radar``
                                      corroboration recorded separately).

Proportions: per stratum with Wilson 95 % intervals; a cohort estimate weighted by stratum size, with the same weights
applied to the per-stratum Wilson bounds (conservative descriptive bounds, not a joint interval). Sensitivity (sample-based, descriptive): the
published R1 AP contrasts C2@30 (SAGE with history - online history, shared candidates) and native@30 (SAGE with
history - online history on its native candidates), plus the same at 60 s, recomputed (1) on all eligible events (must
reproduce the published values, else stop), (2) excluding the sampled events classified likely FP, (3) within each
stratum, (4) on the sampled events only, all and credible only. Statistic and interval are those of
scripts/paper_month_boundary.py: paired training-seed then incident-day-block bootstrap, blocks rebuilt from the kept
events, 10,000 repetitions, seed 1701; ordinary 95 % intervals, unadjusted, descriptive.

Independent-evidence class (``--ris``, revision round 7, review-r6 W1 item 1; needs ``--as2org``). A second, separately
named class (``independent_class``: ``supported`` / ``contradicted`` / ``uncertain``) that uses no CAIDA relationship file
in any rule. The rules were fixed (2026-11-01 03:57 UTC) before the RIS histories of the sample were fetched and before any
contrast on a new subset was computed; they read no arm result. Inputs per event:

* T: the recovered triples above, NOT filtered by next-month status (the event as the identifier defines it);
* sibling(t): x~a or a~b share an org_id in the event month's AS Organizations snapshot (the ``--as2org`` descriptor);
* family(t): IPv6 if the triple's example_prefix contains ':', else IPv4 (the example prefix is the prefix of the first
  message that carried the triple, so a triple that also carried the other family is classed by its first message);
* Radar segment match on t: a Radar label matched to the event has {leak_seg[0], leak_seg[2]} == {x, b};
* onset triples Q: the first 3 triples of T in (first_ts, x, b) order among the IPv4 triples without a sibling adjacency;
* RIS path history: RIPEstat BGPlay (https://stat.ripe.net/data/bgplay/data.json, public, no credentials) of each Q
  triple's example prefix over [t0 - 1 h, t0 + 2 h], t0 the identifier time to the second; a RIS path carries q if, after
  collapsing AS prepending, it holds x, a, b as consecutive hops (collector side first). Files and a manifest with URL,
  fetch time and sha256 are in the ``--ris`` directory; ``--ris-fetch`` downloads the missing ones. When RIPEstat cannot
  answer the three-hour query (gateway timeout), the window is fetched as 3 contiguous one-hour parts, then as 9
  twenty-minute parts, and merged (``Ris.get``, ``merge_parts``; ``RIS_SPLITS``).

Per onset triple q (event-specific path evolution): P1 (x, a, b) is not among the previous month's classified new triples
in any class (relationship-free month novelty); P2 the replay observation lag is > -3540 s (the route was not visible at the
start of the one-hour look-back); P3 no RIS peer's path for the prefix carries q at t0 - 1 h; P4 some RIS announcement in
the window carries q; P5 no RIS peer's path carries q at t0 + 2 h. q reason: ``preexisting`` (P1, P2 or P3 fails),
``not_seen_in_ris`` (P4 fails), ``long_lived`` (P5 fails), else ``supported``. Missing data (added 2026-11-01 after
RIPEstat failed on a few busy prefixes, before any contrast on a new subset): if RIPEstat cannot serve the window at any
split level, it is recorded ``unavailable``; q is then ``preexisting`` if P1 or P2 fails (RIS cannot change that) and
``ris_unavailable`` otherwise (P3 to P5 undecidable, so q cannot support the event). Data integrity (same time): BGPlay
returned event lists that do not replay to the next part's initial state, so a q that passes P1 to P5 on the event list
also needs RIPEstat's own state at t0 + 2 h (initial state of a 60-s query, ``ris_end_state``) to show no peer carrying
q; otherwise long_lived (or ris_unavailable if that query fails). An incomplete event list can then only lose support.
The window is the replay window of the benchmark (one-hour look-back, two-hour target): a path that is new in it and gone
at its end is an anomaly of this event,
as a leak that an operator corrects would be. A path still present at t0 + 2 h may be a long-lived leak or a stable
configuration, so it is uncertain, not contradicted. A new, short path is consistent with a corrected leak but also with
other transient routing; it is evidence beyond the relationship test, not proof.

Event rules, first that fires (``independent_rule``):

  I0 uncertain    / no_triple              T is empty.
  I1 contradicted / sibling_only           every triple of T has a sibling adjacency and no Radar segment matches a triple:
                                           a route inside one organisation (AS2Org used only to exclude, never to support).
  I2 uncertain    / sibling_radar_conflict every triple has a sibling adjacency, but a Radar segment matches a triple.
  I3 supported    / radar_segment          a Radar segment matches a triple without a sibling adjacency (an independent
                                           detector names the same segment; any address family).
  I4 uncertain    / ipv6_only              every triple of T has an IPv6 example prefix: the identifier applies the CAIDA
                                           file inferred from IPv4 paths, which cannot judge IPv6 exports (round-7 domain
                                           reviewer: lateral IPv6 exports of open IPv6 peers).
  I5 supported    / path_evolution         some q passes P1 to P5.
  I6 uncertain    / no_eligible_triple, ris_unavailable, long_lived, not_seen_in_ris or preexisting (Q empty; else the
                                           first of these, in this order, that some q has).

Limits: Radar is a separate detector, but by its method page
(https://blog.cloudflare.com/route-leak-detection-with-cloudflare-radar/) it combines CAIDA relationships with its own and
reads the same RouteViews and RIS updates, so I3 is corroboration, not ground truth. RIS is one of the pipeline's collector
projects, so I5 is independent of the relationship inference, not of the BGP data. The class is not a precision estimate:
120 events, rules not validated against labelled truth. Descriptor only (no rule): CAIDA serial-1 ``as-rel.v6-stable``
relationships (``--asrel-v6``, https://publicdata.caida.org/datasets/as-relationships/serial-1/) of the event month and the
next month for the IPv6 triples, with the next_status rule above. Proportions, cohort weighting and the C2/native
contrasts on the supported subset (``sample_independently_supported``, 30 and 60 s) as for the existing class. Paths in the
JSON are written as ``<data>/...``, ``<as2org>/<file>``, ``<asrel-v6>/<file>``, ``<ris>/<file>`` or repo-relative.

Usage (repo root; the cluster files copied read-only into a local directory):
    .venv/bin/python -B scripts/paper_leak_audit.py \
        --events data/corrected-release-20261016/eventset/2025_leak/events.parquet \
        --data <copy holding leak_events/, triples/ (identifier2 month dirs, leakcheck4_m2 files), graphs/, labels/> \
        --r1-report .agents/operations/r1-v11-posteval-20261024/evidence/released/report.json \
        --r1-per-event <local copy of results/per_event> \
        --r1-arm-spec .agents/operations/r1-arm-spec-20261020/arm-spec.json \
        --r1-manifest-30 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d30.json \
        --r1-manifest-60 .agents/operations/r1-v11-posteval-20261024/evidence/released/retrospective-2025-v6-d60.json \
        --as2org <dir>/20250901.as-org2info.txt.gz <dir>/20251001.as-org2info.txt.gz \
                 <dir>/20251101.as-org2info.txt.gz <dir>/20251201.as-org2info.txt.gz \
        --out-json paper/generated/leak_audit.json --out-tex paper/generated/leak_audit.tex \
        --out-csv paper/generated/leak_audit_sample.csv \
        [--asrel-v6 <dir>/YYYYMM01.as-rel.v6-stable.txt.bz2 ... --ris <dir> [--ris-fetch]]
(the AS Organizations, relationship and RIPEstat files are untrusted downloads: run with ``python -I -B`` and pass them as
paths.)
"""
from __future__ import annotations

import argparse
import bz2
import datetime as dt
import gzip
import hashlib
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bgbench.forecast_analysis import incident_day_blocks  # noqa: E402
from bgbench.forecast_ranking import paired_bootstrap, ranking_contrast  # noqa: E402
import paper_month_boundary as mb  # noqa: E402  (R1 loader, hash helper, require)

REPS = 10_000
SEED = 1701
PER_STRATUM = 30
STRATA = (("labelled", True), ("labelled", False), ("top", True), ("top", False))
STRATUM_NAME = {("labelled", True): "radar_day1", ("labelled", False): "radar_other",
                ("top", True): "volume_day1", ("top", False): "volume_other"}
STRATUM_TEX = {"radar_day1": "Radar, day 1", "radar_other": "Radar, other days", "volume_day1": "Volume, day 1",
               "volume_other": "Volume, other days"}
CLASSES = ("credible", "likely_false_positive", "ambiguous")
SENS_CONTRASTS = {"C2": ("sage_on", "online_history"), "native": ("sage_on", "online_history_native")}
LEAKY = ("provider", "peer")
LOOKBACK_EDGE_S = -3540.0  # within 60 s of the start of the one-hour replay look-back
RADAR_SLACK_MIN = 10       # bgbench.leak_events.match_labels
SIB_STATUS = ("independent", "sibling_only", "no_violating_triple")
AS2ORG_NAME = re.compile(r"(\d{8})\.as-org2info\.txt(\.gz)?$")
ASREL6_NAME = re.compile(r"(\d{8})\.as-rel\.v6-stable\.txt\.bz2$")
IND_CLASSES = ("supported", "contradicted", "uncertain")
IND_FAMILIES = ("ipv4_only", "ipv6_only", "mixed", "none")
UNCERTAIN_ORDER = ("ris_unavailable", "long_lived", "not_seen_in_ris", "preexisting")  # I6 reason precedence
RIS_MISSING = {k: None for k in ("ris_peers", "ris_split_parts", "ris_parts_consistent", "peers_carrying_at_start",
                                 "first_announcement_carrying", "peers_carrying_max", "peers_carrying_at_end",
                                 "last_stop_carrying", "P3_absent_at_start", "P4_seen_in_window", "P5_absent_at_end")}
ONSET_TRIPLES = 3
RIS_BEFORE_S, RIS_AFTER_S = 3600, 7200  # [t0 - 1 h, t0 + 2 h]: the replay look-back and the two-hour target
RIS_URL = "https://stat.ripe.net/data/bgplay/data.json"
RIS_SPLITS = (1, 3, 9)                # whole window, then 1-h parts, then 20-min parts (RIPEstat gateway timeouts)
RIS_TRIES = {1: 2, 3: 2, 9: 4}
RIS_END_S = 60                         # end-state query [t0 + 2 h, t0 + 2 h + 60 s]: RIPEstat's own state at t0 + 2 h
RADAR_METHOD_URL = "https://blog.cloudflare.com/route-leak-detection-with-cloudflare-radar/"
RULES_FIXED_UTC = "2026-11-01T03:57:38Z"
REPO = Path(__file__).resolve().parents[1]
require = mb.require


class Anon:
    """Path strings for the JSON without session or user directories: ``<data>/...`` under --data, ``<as2org>/<file>``,
    ``<asrel-v6>/<file>``, ``<ris>/<file>``, repo-relative inside the repository; anything else stops the run."""

    def __init__(self, args):
        self.named = {}
        for tag, paths in (("as2org", args.as2org or []), ("asrel-v6", args.asrel_v6 or [])):
            for p in paths:
                self.named[str(Path(p).resolve())] = f"<{tag}>/{Path(p).name}"
        self.roots = [(Path(args.ris).resolve(), "<ris>")] if args.ris else []
        self.roots += [(Path(args.data).resolve(), "<data>"), (REPO, None)]

    def __call__(self, path):
        p = Path(path).resolve()
        if str(p) in self.named:
            return self.named[str(p)]
        for root, tag in self.roots:
            if p.is_relative_to(root):
                rel = p.relative_to(root).as_posix()
                return f"{tag}/{rel}" if tag else rel
        require(False, f"{path}: outside --data, --ris and the repository; cannot write it anonymously")


# ----------------------------------------------------------------------------- helpers

def month_dir(day: dt.date) -> str:
    last = (day.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return f"{day.replace(day=1).isoformat()}_{last.isoformat()}"


def shift_month(day: dt.date, k: int) -> dt.date:
    y, m = divmod(day.year * 12 + day.month - 1 + k, 12)
    return dt.date(y, m + 1, 1)


def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, centre - half), min(1.0, centre + half)]


def rel_lookup(path):
    r = pl.read_parquet(path)
    return {(int(u), int(v)): k for u, v, k in zip(r["u"].to_list(), r["v"].to_list(), r["kind"].to_list())}


def status(lf, et):
    if lf == "customer" or et == "customer":
        return "valley_free"
    if lf in LEAKY and et in LEAKY:
        return "violating"
    return "missing"


# ----------------------------------------------------------------------------- population and sample

def cohort(args):
    m30 = json.loads(Path(args.r1_manifest_30).read_text())
    m60 = json.loads(Path(args.r1_manifest_60).read_text())
    t30 = {e["event_id"]: e for e in m30["events"] if e["split"] == "test"}
    t60 = {e["event_id"] for e in m60["events"] if e["split"] == "test"}
    require(set(t30) == t60, "R1 test cohorts differ between 30 and 60 s")
    ev = pl.read_parquet(args.events)
    require(set(ev["reason"].unique().to_list()) <= {"labelled", "top"}, "Unexpected selection reasons")
    c = ev.filter(pl.col("event_id").is_in(list(t30)))
    require(c.height == len(t30), f"{len(t30) - c.height} R1 test events missing from the released table")
    require((c["split"] == "test").all(), "R1 test event not in the table's test split")
    c = c.with_columns(day1=pl.col("event_id").str.slice(6, 2) == "01",
                       id_t0=pl.col("event_id").str.slice(0, 15).str.to_datetime("%Y%m%dT%H%M%S", time_zone="UTC"))
    require((c["a"].cast(pl.String) == c["event_id"].str.split("_").list.get(2)).all(), "leaker differs from event_id")
    obs = {e: t30[e]["observation_lag_s"] for e in t30}
    require(all(abs(o - obs[e]) < 1e-6 for e, o in zip(c["event_id"].to_list(), c["observation_lag_s"].to_list())),
            "observation lag differs between the manifest and the released table")
    return c, {"table_test_rows": int((ev["split"] == "test").sum()), "cohort_events": c.height,
               "table_test_rows_outside_cohort": int((ev["split"] == "test").sum()) - c.height}


def draw(c, per_stratum, seed):
    rng = np.random.default_rng(seed)
    out, sizes = [], {}
    for reason, day1 in STRATA:
        name = STRATUM_NAME[(reason, day1)]
        ids = sorted(c.filter((pl.col("reason") == reason) & (pl.col("day1") == day1))["event_id"].to_list())
        k = min(per_stratum, len(ids))
        pick = sorted(ids[i] for i in rng.choice(len(ids), size=k, replace=False))
        sizes[name] = {"population": len(ids), "sampled": k}
        out += [(e, name) for e in pick]
    return out, sizes


# ----------------------------------------------------------------------------- evidence

class Evidence:
    def __init__(self, data: Path):
        self.data = data
        self._ev, self._tr, self._rel = {}, {}, {}
        self.radar = pl.read_parquet(data / "labels" / "cloudflare_leaks.parquet").with_columns(
            min_ts=pl.col("min_ts").str.to_datetime(time_zone="UTC", strict=False),
            max_ts=pl.col("max_ts").str.to_datetime(time_zone="UTC", strict=False))
        seg = [re.sub(r"[\[\]\" ]", "", v).split(",") for v in self.radar["leak_seg"].to_list()]
        self.radar = self.radar.with_columns(
            pl.Series("seg0", [int(s[0]) if len(s) >= 3 else None for s in seg], dtype=pl.Int64),
            pl.Series("leaker", [int(s[1]) if len(s) >= 2 else 0 for s in seg], dtype=pl.Int64),
            pl.Series("seg2", [int(s[2]) if len(s) >= 3 else None for s in seg], dtype=pl.Int64))
        manifest = data / "labels" / "leak_replay_manifest.tsv"
        self.manifest = ({r["event_id"]: r for r in pl.read_csv(manifest, separator="\t",
                                                                 schema_overrides={"sources": pl.String,
                                                                                   "upstreams": pl.String}).iter_rows(named=True)}
                         if manifest.exists() else {})
        self.files = {}

    def _file(self, path):
        if str(path) not in self.files:
            self.files[str(path)] = mb.sha(path)
        return path

    def events(self, month):
        if month not in self._ev:
            self._ev[month] = {r["event_id"]: r for r in pl.read_parquet(
                self._file(self.data / "leak_events" / month / "events_leak_like_m2.parquet")).iter_rows(named=True)}
        return self._ev[month]

    def triples(self, month):
        if month not in self._tr:
            t = pl.read_parquet(self._file(self.data / "triples" / month / "new_triples_classified.parquet"))
            self._tr[month] = t.filter(pl.col("leak_like"))
        return self._tr[month]

    def any_class_triples(self, month):
        """(x, a, b) of every classified new triple of the month, whatever its relationship class (rule P1)."""
        if month not in getattr(self, "_all", {}):
            self._all = getattr(self, "_all", {})
            t = pl.read_parquet(self._file(self.data / "triples" / month / "new_triples_classified.parquet"),
                                columns=["x", "a", "b"])
            self._all[month] = set(zip(*(t[c].cast(pl.Int64).to_list() for c in ("x", "a", "b"))))
        return self._all[month]

    def rel(self, first_day: dt.date):
        key = first_day.strftime("%Y%m")
        if key not in self._rel:
            self._rel[key] = rel_lookup(self._file(self.data / "graphs" / f"{key}01.rel.parquet"))
        return self._rel[key]

    def radar_match(self, a, t0):
        lo, hi = t0 - dt.timedelta(minutes=RADAR_SLACK_MIN), t0 + dt.timedelta(minutes=RADAR_SLACK_MIN)
        return self.radar.filter((pl.col("leaker") == a) & (pl.col("min_ts") >= lo) & (pl.col("min_ts") <= hi))


def gather(ev: Evidence, row):
    eid, a = row["event_id"], int(row["a"])
    day = row["id_t0"].date()
    month = month_dir(day)
    idrec = ev.events(month).get(eid)
    require(idrec is not None, f"{eid}: not in the identifier's leak events of {month}")
    t0 = idrec["t0"]  # full precision; event_id carries it truncated to the second
    require(int(idrec["a"]) == a and t0.replace(microsecond=0) == row["id_t0"], f"{eid}: identifier record differs (a, t0)")
    cur, nxt, prv = ev.rel(day.replace(day=1)), ev.rel(shift_month(day, 1)), ev.rel(shift_month(day, -1))
    tr = ev.triples(month).filter((pl.col("a") == a) & (pl.col("first_ts") >= t0 - dt.timedelta(minutes=1))
                                  & (pl.col("first_ts") <= idrec["t_last"] + dt.timedelta(minutes=5)))
    prev_month = month_dir(shift_month(day, -1))
    prev = ev.triples(prev_month).filter(pl.col("a") == a)
    prev_keys = {(int(x), int(b)) for x, b in zip(prev["x"].to_list(), prev["b"].to_list())}
    triples = {}
    for r in tr.sort("first_ts").iter_rows(named=True):
        key = (int(r["x"]), int(r["b"]))
        if key in triples:
            triples[key]["collectors_max"] = max(triples[key]["collectors_max"], r["n_collectors"])
            continue
        x, b = key
        lf, et = cur.get((a, b)), cur.get((a, x))
        require(lf == r["learned_from"] and et == r["exported_to"],
                f"{eid}: event-month relationships differ from the identifier's classification for {(x, a, b)}")
        triples[key] = {"x": x, "a": a, "b": b, "first_ts": r["first_ts"].isoformat(), "collectors_max": r["n_collectors"],
                        "example_prefix": r["example_prefix"],
                        "month": {"learned_from": lf, "exported_to": et},
                        "next": {"learned_from": nxt.get((a, b)), "exported_to": nxt.get((a, x))},
                        "prev": {"learned_from": prv.get((a, b)), "exported_to": prv.get((a, x))},
                        "in_prev_month_leaky_new_triples": key in prev_keys}
        t = triples[key]
        t["next_status"] = status(t["next"]["learned_from"], t["next"]["exported_to"])
        t["prev_status"] = status(t["prev"]["learned_from"], t["prev"]["exported_to"])
    triples = list(triples.values())
    # consistency with the replay selection (sources = b, upstreams = x)
    man = ev.manifest.get(eid)
    manifest_ok = None
    if man is not None and triples:
        manifest_ok = (sorted({t["b"] for t in triples}) == sorted(int(s) for s in str(man["sources"]).split("|") if s)
                       and sorted({t["x"] for t in triples}) == sorted(int(s) for s in str(man["upstreams"]).split("|") if s))
    lab = ev.radar_match(a, t0)
    require(bool(lab.height) == bool(idrec["labelled"]), f"{eid}: Radar match differs from the identifier's flag")
    require(bool(row["labelled"]) == bool(idrec["labelled"]), f"{eid}: Radar flag differs from the released table")
    pairs = {(t["x"], t["b"]) for t in triples}
    seg_match = any((s0, s2) in pairs or (s2, s0) in pairs for s0, s2 in zip(lab["seg0"].to_list(), lab["seg2"].to_list()))
    return {
        "event_id": eid, "leaker": a, "identifier_t0": t0.isoformat(), "month": month,
        "identifier": {k: (idrec[k].isoformat() if isinstance(idrec[k], dt.datetime) else idrec[k])
                       for k in ("t_last", "bins", "duration_min", "n_triples", "n_collectors", "n_msgs", "n_upstreams",
                                 "n_sources", "n_prefixes", "labelled", "label_peer_count")},
        "triples": triples, "manifest_sources_upstreams_match": manifest_ok,
        "radar": {"matched": bool(lab.height), "labels": lab.height,
                  "ids": lab["id"].to_list(), "peer_count_max": max(map(int, lab["peer_count"].to_list()), default=None),
                  "prefix_count_max": max(map(int, lab["prefix_count"].to_list()), default=None),
                  "leak_types": sorted(set(lab["leak_type"].to_list())),
                  "duration_min_max": max(((m2 - m1).total_seconds() / 60 for m1, m2 in
                                          zip(lab["min_ts"].to_list(), lab["max_ts"].to_list()) if m1 and m2), default=None),
                  "segment_matches_a_triple": bool(seg_match) if lab.height else None},
        "replay": {k: row[k] for k in ("observation_lag_s", "max_collectors", "collectors_seeing", "sessions_carrying",
                                       "leaked_prefixes", "duration_min", "n_msgs", "anomalous_msgs", "vp_final_2h",
                                       "asns_final_2h")},
    }


class As2Org:
    """CAIDA AS Organizations snapshots (YYYYMMDD.as-org2info.txt[.gz], pipe-separated, sections opened by ``# format:``
    lines). Parsed as data only: AS number -> org_id of the ``aut`` section; organisation rows are counted, not used."""

    def __init__(self, paths):
        self.snap = {}
        for p in map(Path, paths):
            m = AS2ORG_NAME.match(p.name)
            require(m, f"{p}: not a CAIDA YYYYMMDD.as-org2info.txt[.gz] file")
            day = dt.datetime.strptime(m.group(1), "%Y%m%d").date()
            require(day not in self.snap, f"{p}: two AS Organizations snapshots dated {day}")
            self.snap[day] = self._parse(p, day)

    @staticmethod
    def _parse(path, day):
        org, orgs, section, head = {}, 0, None, {}
        with (gzip.open(path, "rt", encoding="utf-8", errors="replace") if path.suffix == ".gz"
              else path.open(encoding="utf-8", errors="replace")) as stream:
            for line in stream:
                line = line.rstrip("\n")
                if line.startswith("#"):
                    s = line[1:].strip()
                    if s.startswith("format:"):
                        cols = s[len("format:"):].strip()
                        section = "aut" if cols.startswith("aut|") else "org" if cols.startswith("org_id|") else None
                        require(section, f"{path}: unknown section format {cols!r}")
                    elif s.startswith("date:"):
                        head["date"] = s[len("date:"):].strip()
                    elif s.startswith("file creation time:"):
                        head["created"] = s[len("file creation time:"):].strip()
                    continue
                if not line:
                    continue
                require(section, f"{path}: record before a format line")
                f = line.split("|")
                if section == "org":
                    orgs += 1
                    continue
                require(len(f) == 6 and f[0].isdigit() and f[3], f"{path}: malformed AS row {line[:80]!r}")
                require(org.get(int(f[0]), f[3]) == f[3], f"{path}: AS{f[0]} has two org_ids")
                org[int(f[0])] = f[3]
        require(head.get("date") == day.strftime("%Y%m"), f"{path}: header date {head.get('date')} differs from the file name")
        require(org and orgs, f"{path}: no AS or organisation rows")
        return {"org": org, "path": str(path), "sha256": mb.sha(path), "header_date": head["date"],
                "file_creation_time": head.get("created"), "ases": len(org), "organisations": orgs}

    def for_month(self, first_day: dt.date):
        days = [d for d in self.snap if d <= first_day]
        require(days, f"no AS Organizations snapshot dated on or before {first_day}")
        return max(days)


def siblings(e, as2org: As2Org):
    """Annotate the event's triples with AS2Org org_ids and sibling adjacencies; returns nothing, changes no class."""
    day = as2org.for_month(dt.date.fromisoformat(e["month"][:10]))
    org = as2org.snap[day]["org"]

    def same(u, v):
        return None if u not in org or v not in org else org[u] == org[v]
    for t in e["triples"]:
        t["as2org"] = {"org_x": org.get(t["x"]), "org_a": org.get(t["a"]), "org_b": org.get(t["b"]),
                       "sibling_x_a": same(t["x"], t["a"]), "sibling_a_b": same(t["a"], t["b"])}
    sib = lambda t: t["as2org"]["sibling_x_a"] is True or t["as2org"]["sibling_a_b"] is True  # noqa: E731
    mapped = lambda t: t["as2org"]["sibling_x_a"] is not None and t["as2org"]["sibling_a_b"] is not None  # noqa: E731
    viol = [t for t in e["triples"] if t["next_status"] == "violating"]
    free = [t for t in viol if not sib(t)]
    strict = [t for t in free if mapped(t)]
    state = lambda f: "no_violating_triple" if not viol else "independent" if f else "sibling_only"  # noqa: E731
    e["as2org"] = {"snapshot": day.strftime("%Y%m%d"), "any_sibling_adjacency": any(map(sib, e["triples"])),
                   "triples_sibling_adjacent": sum(map(sib, e["triples"])),
                   "triples_with_unmapped_as": sum(not mapped(t) for t in e["triples"]),
                   "violating_triples": len(viol), "violating_triples_non_sibling": len(free),
                   "violating_triples_non_sibling_all_mapped": len(strict),
                   "non_sibling_violating_triple": bool(free), "status": state(free), "status_strict": state(strict)}


class Rel6:
    """CAIDA serial-1 YYYYMM01.as-rel.v6-stable.txt.bz2 (``p|c|-1``, ``p|p|0``), read as the identifier's directed rows
    (u, v) -> kind of v for u. Descriptor only."""

    def __init__(self, paths):
        self.rel, self.meta = {}, {}
        for p in map(Path, paths):
            m = ASREL6_NAME.match(p.name)
            require(m, f"{p}: not a CAIDA YYYYMMDD.as-rel.v6-stable.txt.bz2 file")
            key = m.group(1)[:6]
            require(m.group(1).endswith("01") and key not in self.rel, f"{p}: not a first-of-month file, or two for {key}")
            rows, dates = {}, set()
            with bz2.open(p, "rt", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if line.startswith("#"):
                        f = line.split("|")
                        if line.startswith("# source:topology") and len(f) > 2:
                            dates.add(f[2][:6])
                        continue
                    f = line.strip().split("|")
                    require(len(f) >= 3 and f[0].isdigit() and f[1].isdigit() and f[2] in ("-1", "0"),
                            f"{p}: malformed row {line[:60]!r}")
                    u, v = int(f[0]), int(f[1])
                    pairs = ((v, u, "provider"), (u, v, "customer")) if f[2] == "-1" else ((u, v, "peer"), (v, u, "peer"))
                    for a, b, k in pairs:
                        rows.setdefault((a, b), k)
            require(dates == {key}, f"{p}: source dates {sorted(dates)} differ from the file name")
            self.rel[key] = rows
            self.meta[key] = {"path": str(p), "sha256": mb.sha(p), "directed_rows": len(rows)}

    def describe(self, e):
        """Per IPv6 triple: v6 relationships of the event month and the next month and their status."""
        day = dt.date.fromisoformat(e["month"][:10])
        cur, nxt = day.strftime("%Y%m"), shift_month(day, 1).strftime("%Y%m")
        require(cur in self.rel and nxt in self.rel, f"{e['event_id']}: no v6-stable file for {cur} or {nxt}")
        out = []
        for t in e["triples"]:
            if t["family"] != "ipv6":
                continue
            r = {"month": {"learned_from": self.rel[cur].get((t["a"], t["b"])), "exported_to": self.rel[cur].get((t["a"], t["x"]))},
                 "next": {"learned_from": self.rel[nxt].get((t["a"], t["b"])), "exported_to": self.rel[nxt].get((t["a"], t["x"]))}}
            r["month_status"] = status(r["month"]["learned_from"], r["month"]["exported_to"])
            r["next_status"] = status(r["next"]["learned_from"], r["next"]["exported_to"])
            t["rel_v6"] = r
            out.append(r)
        return {"files": [cur, nxt], "ipv6_triples": len(out),
                **{f"ipv6_triples_{w}_{s}": sum(r[f"{w}_status"] == s for r in out)
                   for w in ("month", "next") for s in ("violating", "valley_free", "missing")},
                "ipv6_triples_violating_both": sum(r["month_status"] == r["next_status"] == "violating" for r in out)}


# ----------------------------------------------------------------------------- independent evidence (rules I0..I6)

def collapse(path):
    """BGPlay path -> list of AS numbers with prepending collapsed; a non-integer hop (AS set) becomes None."""
    out = []
    for h in path:
        h = h if isinstance(h, int) else None
        if not out or out[-1] != h or h is None:
            out.append(h)
    return out


def carries(path, seg):
    p = collapse(path)
    return any(p[i:i + 3] == seg for i in range(len(p) - 2))


def ris_name(event_id, prefix):
    return f"{event_id}__{prefix.replace('/', '_').replace(':', '-')}.json"


def ris_window(e):
    t0 = dt.datetime.fromisoformat(e["identifier_t0"]).replace(microsecond=0, tzinfo=None)
    return t0 - dt.timedelta(seconds=RIS_BEFORE_S), t0 + dt.timedelta(seconds=RIS_AFTER_S)


def onset_triples(e):
    ok = [t for t in e["triples"] if t["family"] == "ipv4" and not t["as2org"]["sibling_x_a"] and not t["as2org"]["sibling_a_b"]]
    return sorted(ok, key=lambda t: (dt.datetime.fromisoformat(t["first_ts"]), t["x"], t["b"]))[:ONSET_TRIPLES]


class Ris:
    """RIPEstat BGPlay files of the onset triples' example prefixes; ``fetch`` downloads a missing file and records it in
    MANIFEST.json (url, fetched_utc, sha256, bytes). Responses are parsed as data only."""

    def __init__(self, root, fetch=False):
        self.root, self.fetch = Path(root), fetch
        self.root.mkdir(parents=True, exist_ok=True) if fetch else require(self.root.is_dir(), f"{root}: no --ris directory")
        self.manifest_path = self.root / "MANIFEST.json"
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {}
        self.used = {}

    def _url(self, prefix, start, end):  # self unused (also called as Ris._url(None, ...))
        return (f"{RIS_URL}?resource={urllib.parse.quote(prefix, safe='')}&starttime={start.isoformat()}"
                f"&endtime={end.isoformat()}&sourceapp=bgbench-leak-audit")

    def _download(self, name, url, start, tries=4):
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(url, timeout=300) as r:
                    body = r.read()
                d = json.loads(body)
                if d.get("status") == "ok" and d["data"]["query_starttime"] == start.isoformat():
                    (self.root / name).write_bytes(body)
                    self.manifest[name] = {"url": url, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                                           "fetched_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
                    self.manifest_path.write_text(json.dumps(self.manifest, indent=1, sort_keys=True) + "\n")
                    time.sleep(1)
                    return True
            except (OSError, ValueError) as err:  # retried below
                print(f"RIS {name}: {err}", flush=True)
            time.sleep(5 * (attempt + 1))
        return False

    def _load(self, name, url, start, end):
        path = self.root / name
        rec = self.manifest.get(name)
        require(rec is not None and rec["url"] == url and rec["sha256"] == mb.sha(path), f"{name}: not as recorded in MANIFEST.json")
        self.used[name] = rec
        d = json.loads(path.read_text())
        require(d.get("status") == "ok" and d["data"]["query_starttime"] == start.isoformat()
                and d["data"]["query_endtime"] == end.isoformat(), f"{name}: window or status differs")
        return d["data"]

    def get(self, e, prefix):
        """The BGPlay data of the window, or None if RIPEstat could not serve it (recorded as ``unavailable``). When the
        three-hour query fails (RIPEstat's gateway times out on busy prefixes), the window is fetched as RIS_SPLITS
        contiguous parts and merged (``merge_parts``)."""
        start, end = ris_window(e)
        name = ris_name(e["event_id"], prefix)
        levels = {n: ris_parts(name, prefix, start, end, n) for n in RIS_SPLITS}
        done = lambda n: all((self.root / x[0]).exists() for x in levels[n])  # noqa: E731
        if not any(map(done, RIS_SPLITS)) and not self.manifest.get(name, {}).get("unavailable"):
            require(self.fetch, f"{name}: missing; run with --ris-fetch")
            for n in RIS_SPLITS:
                if all((self.root / x[0]).exists() or self._download(x[0], x[1], x[2], RIS_TRIES[n]) for x in levels[n]):
                    break
            else:
                self.manifest[name] = {"unavailable": True, "url": self._url(prefix, start, end), "splits_tried": list(RIS_SPLITS),
                                       "attempted_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
                self.manifest_path.write_text(json.dumps(self.manifest, indent=1, sort_keys=True) + "\n")
        n = next((n for n in RIS_SPLITS if done(n)), None)
        if n is None:
            rec = self.manifest.get(name, {})
            require(rec.get("unavailable") and rec["url"] == self._url(prefix, start, end), f"{name}: neither data nor an unavailable record")
            self.used[name] = rec
            return None
        return merge_parts([self._load(*x) for x in levels[n]], prefix)


def ris_end_state(ris, e, prefix):
    """RIPEstat's state at t0 + 2 h (the initial state of a 60-s query), or None if it could not be served (recorded
    ``unavailable``). Checks P5 against an incomplete event list: BGPlay returned event lists that do not replay to the
    next part's initial state (``parts_consistent`` false), while its initial states come from RIBs."""
    _, end = ris_window(e)
    stop = end + dt.timedelta(seconds=RIS_END_S)
    name = ris_name(e["event_id"], prefix)[:-5] + "__end.json"
    url = Ris._url(None, prefix, end, stop)
    path = ris.root / name
    if not path.exists() and not ris.manifest.get(name, {}).get("unavailable"):
        require(ris.fetch, f"{name}: missing; run with --ris-fetch")
        if not ris._download(name, url, end, RIS_TRIES[9]):
            ris.manifest[name] = {"unavailable": True, "url": url,
                                  "attempted_utc": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
            ris.manifest_path.write_text(json.dumps(ris.manifest, indent=1, sort_keys=True) + "\n")
    if not path.exists():
        rec = ris.manifest.get(name, {})
        require(rec.get("unavailable") and rec["url"] == url, f"{name}: neither data nor an unavailable record")
        ris.used[name] = rec
        return None
    return ris._load(name, url, end, stop)


def ris_parts(name, prefix, start, end, n):
    """(file name, url, start, end) of the n contiguous parts of the window; n = 1 is the whole window."""
    step = (end - start) / n
    bounds = [start + k * step for k in range(n)] + [end]
    require(all(b.microsecond == 0 for b in bounds), "RIS part bounds must be whole seconds")
    return [(name if n == 1 else name[:-5] + f"__part{k}of{n}.json", Ris._url(None, prefix, bounds[k], bounds[k + 1]),
             bounds[k], bounds[k + 1]) for k in range(n)]


def merge_parts(data, prefix):
    """One window from contiguous BGPlay parts: the first part's initial state, all events (deduplicated by seq).
    ``parts_consistent``: every later part's initial state equals the state replayed from the earlier parts."""
    if len(data) == 1:
        return data[0] | {"split_parts": 1, "parts_consistent": None}
    consistent = True
    for k in range(1, len(data)):
        state = {s["source_id"]: s["path"] for s in data[0]["initial_state"] if s["target_prefix"] == prefix}
        for ev in sorted({ev["seq"]: ev for d in data[:k] for ev in d["events"] if ev["attrs"]["target_prefix"] == prefix}.values(),
                         key=lambda ev: (ev["timestamp"], ev["seq"])):
            if ev["type"] == "A":
                state[ev["attrs"]["source_id"]] = ev["attrs"]["path"]
            else:
                state.pop(ev["attrs"]["source_id"], None)
        consistent &= {s["source_id"]: s["path"] for s in data[k]["initial_state"] if s["target_prefix"] == prefix} == state
    return {"initial_state": data[0]["initial_state"], "sources": [x for d in data for x in d["sources"]],
            "events": list({ev["seq"]: ev for d in data for ev in d["events"]}.values()), "split_parts": len(data),
            "parts_consistent": consistent}


def ris_evidence(data, prefix, seg):
    """P3, P4, P5 for one triple on one prefix: carried at the window start, announced in it, carried at its end."""
    state = {}
    for s in data["initial_state"]:
        if s["target_prefix"] == prefix:
            state[s["source_id"]] = s["path"]
    on = {k for k, p in state.items() if carries(p, seg)}
    at_start = sorted(on)
    first, last_on, peak = None, None, len(on)
    events = sorted((ev for ev in data["events"] if ev["attrs"]["target_prefix"] == prefix),
                    key=lambda ev: (ev["timestamp"], ev["seq"]))
    for ev in events:
        src = ev["attrs"]["source_id"]
        require(ev["type"] in ("A", "W"), f"{prefix}: unknown BGPlay event type {ev['type']!r}")
        was = src in on
        if ev["type"] == "A" and carries(ev["attrs"]["path"], seg):
            on.add(src)
            first = first or ev["timestamp"]
        else:
            on.discard(src)
        if was and src not in on:
            last_on = ev["timestamp"]
        peak = max(peak, len(on))
    at_end = sorted(on)
    return {"ris_peers": len({s["id"] for s in data["sources"]}), "ris_split_parts": data["split_parts"],
            "ris_parts_consistent": data["parts_consistent"], "peers_carrying_at_start": len(at_start),
            "first_announcement_carrying": first, "peers_carrying_max": peak, "peers_carrying_at_end": len(at_end),
            "last_stop_carrying": last_on if not at_end else None,
            "P3_absent_at_start": not at_start, "P4_seen_in_window": first is not None, "P5_absent_at_end": not at_end}


def independent_class(e, ev: Evidence, ris: Ris):
    """Rules I0..I6 (docstring). Reads triples, AS2Org siblings, Radar, the replay lag and RIS; no relationship file and
    no arm result."""
    T = e["triples"]
    sib = lambda t: bool(t["as2org"]["sibling_x_a"]) or bool(t["as2org"]["sibling_a_b"])  # noqa: E731
    fams = {t["family"] for t in T}
    family = "none" if not T else "ipv6_only" if fams == {"ipv6"} else "ipv4_only" if fams == {"ipv4"} else "mixed"
    lab = ev.radar_match(e["leaker"], dt.datetime.fromisoformat(e["identifier_t0"]))
    segs = {frozenset((s0, s2)) for s0, s2 in zip(lab["seg0"].to_list(), lab["seg2"].to_list()) if s0 is not None}
    radar_hit = [t for t in T if frozenset((t["x"], t["b"])) in segs]
    rec = {"family": family, "triples": len(T), "ipv6_triples": sum(t["family"] == "ipv6" for t in T),
           "sibling_adjacent_triples": sum(map(sib, T)), "radar_segment_triples": len(radar_hit),
           "radar_segment_triples_non_sibling": sum(not sib(t) for t in radar_hit), "onset": []}
    prev = ev.any_class_triples(month_dir(shift_month(dt.date.fromisoformat(e["month"][:10]), -1)))
    lag_ok = e["replay"]["observation_lag_s"] > LOOKBACK_EDGE_S
    for q in onset_triples(e) if T else []:
        data = ris.get(e, q["example_prefix"])
        r = {"x": q["x"], "a": q["a"], "b": q["b"], "first_ts": q["first_ts"], "example_prefix": q["example_prefix"],
             "ris_file": ris_name(e["event_id"], q["example_prefix"]), "ris_available": data is not None,
             "P1_not_in_prev_month_any_class": (q["x"], q["a"], q["b"]) not in prev, "P2_replay_lag_after_lookback_start": lag_ok,
             **(ris_evidence(data, q["example_prefix"], [q["x"], q["a"], q["b"]]) if data is not None else RIS_MISSING)}
        r["reason"] = ("preexisting" if not (r["P1_not_in_prev_month_any_class"] and lag_ok)
                       else "ris_unavailable" if data is None  # P3 to P5 undecidable: the event cannot be supported by q
                       else "preexisting" if not r["P3_absent_at_start"]
                       else "not_seen_in_ris" if not r["P4_seen_in_window"]
                       else "long_lived" if not r["P5_absent_at_end"] else None)
        if r["reason"] is None:  # P1 to P5 pass on the event list: P5 must also hold in RIPEstat's own end state
            end = ris_end_state(ris, e, q["example_prefix"])
            r["end_state_available"] = end is not None
            r["end_state_peers_carrying"] = (None if end is None else sum(
                carries(x["path"], [q["x"], q["a"], q["b"]]) for x in end["initial_state"] if x["target_prefix"] == q["example_prefix"]))
            r["P5_absent_at_end_state"] = None if end is None else r["end_state_peers_carrying"] == 0
            r["reason"] = ("ris_unavailable" if end is None else "long_lived" if not r["P5_absent_at_end_state"]
                           else "supported")
        rec["onset"].append(r)
    reasons = {r["reason"] for r in rec["onset"]}
    if not T:
        c, rule = "uncertain", "I0_no_triple"
    elif all(map(sib, T)):
        c, rule = ("uncertain", "I2_sibling_radar_conflict") if radar_hit else ("contradicted", "I1_sibling_only")
    elif any(not sib(t) for t in radar_hit):
        c, rule = "supported", "I3_radar_segment"
    elif family == "ipv6_only":
        c, rule = "uncertain", "I4_ipv6_only"
    elif "supported" in reasons:
        c, rule = "supported", "I5_path_evolution"
    elif not rec["onset"]:
        c, rule = "uncertain", "I6_no_eligible_triple"
    else:
        c, rule = "uncertain", "I6_" + next(x for x in UNCERTAIN_ORDER if x in reasons)
    rec["class"], rec["rule"] = c, rule
    return rec


def onset_summary(rec):
    """One word for the onset triples of an event: path_evolution_also_passes, no_onset_triple, or the first of
    long_lived, not_seen_in_ris, preexisting that some onset triple has (the I6 order)."""
    reasons = {q["reason"] for q in rec["onset"]}
    if "supported" in reasons:
        return "path_evolution_also_passes"
    return next((x for x in UNCERTAIN_ORDER if x in reasons), "no_onset_triple")


def independent_table(records, sizes):
    """Independent class per stratum (Wilson 95 %), weighted like ``proportions``; IPv6-only counts; cross-tab."""
    per = {}
    for name in [STRATUM_NAME[s] for s in STRATA]:
        rs = [r for r in records if r["stratum"] == name]
        n = len(rs)
        k = lambda c, rs=rs: sum(r["independent"]["class"] == c for r in rs)  # noqa: E731
        per[name] = {"population": sizes[name]["population"], "sampled": n,
                     **{c: {"count": k(c), "share": k(c) / n if n else None, "wilson95": wilson(k(c), n)} for c in IND_CLASSES},
                     "rules": {x: sum(r["independent"]["rule"] == x for r in rs)
                               for x in sorted({r["independent"]["rule"] for r in rs})},
                     "family": {f: {c: sum(r["independent"]["family"] == f and r["independent"]["class"] == c for r in rs)
                                    for c in IND_CLASSES} for f in IND_FAMILIES},
                     "by_relationship_class": {o: {c: sum(r["class"] == o and r["independent"]["class"] == c for r in rs)
                                                   for c in IND_CLASSES} for o in CLASSES},
                     "family_by_relationship_class": {f: {o: sum(r["independent"]["family"] == f and r["class"] == o for r in rs)
                                                          for o in CLASSES} for f in IND_FAMILIES}}

    def combine(parts):
        tot = sum(v["population"] for v in parts.values())
        w = [(v["population"] / tot, v) for v in parts.values() if v["sampled"]]
        return {c: {"share": sum(x * v[c]["share"] for x, v in w),
                    "wilson_weighted_bounds": [sum(x * v[c]["wilson95"][0] for x, v in w),
                                               sum(x * v[c]["wilson95"][1] for x, v in w)]} for c in IND_CLASSES}
    ids = lambda c: [r["event_id"] for r in records if r["independent"]["class"] == c]  # noqa: E731
    return {
        "per_stratum": per,
        "cohort_estimate": {"cohort_events": sum(v["population"] for v in per.values()),
                            "weighted_by_stratum_size": combine(per),
                            "weighted_by_selection": {sel: combine({k: v for k, v in per.items() if k.startswith(sel)})
                                                      for sel in ("radar", "volume")}},
        "sample_totals": {c: sum(per[k][c]["count"] for k in per) for c in IND_CLASSES},
        "rule_totals": {x: sum(per[k]["rules"].get(x, 0) for k in per) for x in sorted({x for v in per.values() for x in v["rules"]})},
        "family_totals": {f: {c: sum(per[k]["family"][f][c] for k in per) for c in IND_CLASSES} for f in IND_FAMILIES},
        "family_by_relationship_class_totals": {f: {o: sum(per[k]["family_by_relationship_class"][f][o] for k in per)
                                                    for o in CLASSES} for f in IND_FAMILIES},
        "crosstab_relationship_class": {o: {c: sum(per[k]["by_relationship_class"][o][c] for k in per) for c in IND_CLASSES}
                                        for o in CLASSES},
        "radar_segment_events_by_onset_evidence": {  # descriptor: what RIS path evolution alone says about the I3 events
            x: sum(r["independent"]["rule"] == "I3_radar_segment" and onset_summary(r["independent"]) == x for r in records)
            for x in ("path_evolution_also_passes", *UNCERTAIN_ORDER, "no_onset_triple")},
        "supported_events": ids("supported"), "contradicted_events": ids("contradicted")}


def classify(e):
    t = e["triples"]
    if not t:
        return "ambiguous", "A0_no_triple"
    viol = [x for x in t if x["next_status"] == "violating"]
    if not viol:
        if e["radar"]["matched"]:
            return "ambiguous", "A1_radar_conflict"
        if any(x["next_status"] == "valley_free" for x in t):
            return "likely_false_positive", "F1_rel_changed_next"
        return "likely_false_positive", "F2_rel_missing_next"
    if e["replay"]["observation_lag_s"] <= LOOKBACK_EDGE_S and all(x["in_prev_month_leaky_new_triples"] for x in viol):
        return "ambiguous", "A2_preexisting_path"
    return "credible", "C1_stable_violation"


# ----------------------------------------------------------------------------- proportions

def proportions(records, sizes):
    out = {}
    for name in [STRATUM_NAME[s] for s in STRATA]:
        rs = [r for r in records if r["stratum"] == name]
        n = len(rs)
        out[name] = {"population": sizes[name]["population"], "sampled": n,
                     **{c: {"count": sum(r["class"] == c for r in rs),
                            "share": (sum(r["class"] == c for r in rs) / n) if n else None,
                            "wilson95": wilson(sum(r["class"] == c for r in rs), n)} for c in CLASSES},
                     "rules": {k: sum(r["rule"] == k for r in rs) for k in sorted({r["rule"] for r in rs})},
                     "descriptors": {
                         "radar_segment_matches_a_triple": sum(bool(r["radar"]["segment_matches_a_triple"]) for r in rs),
                         "recurring_triple": sum(any(t["in_prev_month_leaky_new_triples"] and t["next_status"] == "violating"
                                                     for t in r["triples"]) for r in rs),
                         "route_visible_from_lookback_start": sum(r["replay"]["observation_lag_s"] <= LOOKBACK_EDGE_S
                                                                  for r in rs),
                         "triples_median": float(np.median([len(r["triples"]) for r in rs])) if rs else None}}
    total = sum(v["population"] for v in out.values())

    def combine(parts):
        tot = sum(v["population"] for v in parts.values())
        res = {}
        for c in CLASSES:
            w = [(v["population"] / tot, v) for v in parts.values() if v["sampled"]]
            res[c] = {"share": sum(x * v[c]["share"] for x, v in w),
                      "wilson_weighted_bounds": [sum(x * v[c]["wilson95"][0] for x, v in w),
                                                 sum(x * v[c]["wilson95"][1] for x, v in w)]}
        return res
    weighted = combine(out)
    by_selection = {sel: combine({k: v for k, v in out.items() if k.startswith(sel)}) for sel in ("radar", "volume")}
    return out, {"cohort_events": total, "weighted_by_stratum_size": weighted,
                 "weighted_by_selection": by_selection,
                 "note": "share = sum over strata of (stratum population / population) x stratum share; "
                         "wilson_weighted_bounds = the same weights applied to the per-stratum Wilson 95 % bounds "
                         "(conservative descriptive bounds, not a joint 95 % interval)"}


def sibling_table(records, sizes, as2org: As2Org):
    """Class x AS2Org sibling status per stratum, weighted like ``proportions``; descriptive, the classes are unchanged."""
    per = {}
    for name in [STRATUM_NAME[s] for s in STRATA]:
        rs = [r for r in records if r["stratum"] == name]
        n = len(rs)
        cell = lambda c, s, key="status", rs=rs: sum(r["class"] == c and r["as2org"][key] == s for r in rs)  # noqa: E731
        per[name] = {"population": sizes[name]["population"], "sampled": n,
                     **{c: {s: {"count": cell(c, s), "share": cell(c, s) / n if n else None, "wilson95": wilson(cell(c, s), n),
                                "count_strict": cell(c, s, "status_strict")} for s in SIB_STATUS} for c in CLASSES},
                     "any_sibling_adjacency": sum(r["as2org"]["any_sibling_adjacency"] for r in rs)}

    def combine(parts):
        tot = sum(v["population"] for v in parts.values())
        w = [(v["population"] / tot, v) for v in parts.values() if v["sampled"]]
        return {c: {s: {"share": sum(x * v[c][s]["share"] for x, v in w),
                        "wilson_weighted_bounds": [sum(x * v[c][s]["wilson95"][0] for x, v in w),
                                                   sum(x * v[c][s]["wilson95"][1] for x, v in w)]} for s in SIB_STATUS}
                for c in CLASSES}
    used = sorted({r["as2org"]["snapshot"] for r in records})
    pick = lambda c, s: [r["event_id"] for r in records if r["class"] == c and r["as2org"]["status"] == s]  # noqa: E731
    return {
        "source": "CAIDA AS Organizations (https://publicdata.caida.org/datasets/as-organizations/, "
                  "doi:10.21986/CAIDA.DATA.AS-TO-ORG-MAPPING), inferred by CAIDA from RIR/NIR WHOIS records",
        "snapshots": {day.strftime("%Y%m%d"): {k: v for k, v in s.items() if k != "org"} | {"used": day.strftime("%Y%m%d") in used}
                      for day, s in sorted(as2org.snap.items())},
        "status_rule": {
            "sibling_adjacency": "x~a or a~b with the same org_id in the event month's snapshot (absent AS: not a sibling)",
            "independent": "at least one triple violating next month has no sibling adjacency",
            "sibling_only": "every triple violating next month has a sibling adjacency (a route inside one organisation "
                            "is possible: likely false positive by evidence independent of the relationship files)",
            "no_violating_triple": "no triple violating next month (rules A0, A1, F1, F2)",
            "status_strict": "as status, but a triple with an AS absent from the snapshot does not count as independent"},
        "per_stratum": per, "cohort_estimate": {"weighted_by_stratum_size": combine(per),
                                                "weighted_by_selection": {sel: combine({k: v for k, v in per.items()
                                                                                        if k.startswith(sel)})
                                                                          for sel in ("radar", "volume")}},
        "sample_totals": {c: {s: sum(per[k][c][s]["count"] for k in per) for s in SIB_STATUS} for c in CLASSES},
        "events_any_sibling_adjacency": [r["event_id"] for r in records if r["as2org"]["any_sibling_adjacency"]],
        "credible_sibling_only_events": pick("credible", "sibling_only"),
        "ambiguous_sibling_only_events": pick("ambiguous", "sibling_only"),
        "status_strict_differs": [r["event_id"] for r in records if r["as2org"]["status"] != r["as2org"]["status_strict"]],
        "note": "descriptive; the sibling status does not enter the classification rules. Weighting as cohort_estimate "
                "(stratum population shares applied to stratum shares and to stratum Wilson 95 % bounds; not a joint "
                "interval). AS2Org is itself inferred from WHOIS: it misses siblings under different organisation records, "
                "and a sibling adjacency does not show intent."}


# ----------------------------------------------------------------------------- sensitivity

def masked_contrast(left_seeds, right_seeds, rows, keep_ids, repetitions, seed):
    left = np.array([[e["average_precision"] for e in s] for s in left_seeds], dtype=float)
    right = np.array([[e["average_precision"] for e in s] for s in right_seeds], dtype=float)
    masks = [np.array([e["eligible"] for e in s]) for s in list(left_seeds) + list(right_seeds)]
    require(all((m == masks[0]).all() for m in masks), "Arms or seeds disagree on the eligible cohort")
    keep = masks[0] & np.array([r["event_id"] in keep_ids for r in rows])
    kept = [r for r, k in zip(rows, keep) if k]
    if len({b for b in incident_day_blocks(kept)}) < 2:
        return {"difference": None, "ci95": None, "eligible_events": int(keep.sum()), "blocks": len(set(incident_day_blocks(kept)))}
    res = paired_bootstrap(left[:, keep], right[:, keep], incident_day_blocks(kept), repetitions=repetitions, seed=seed)
    return {"difference": res["difference"], "ci95": res["ci95"], "p_value": res["p_value"],
            "eligible_events": int(keep.sum()), "blocks": res["blocks"],
            "left_mean": float(left[:, keep].mean(axis=1).mean()), "right_mean": float(right[:, keep].mean(axis=1).mean())}


def novolume_sensitivity(args, c, repetitions, seed):
    """R1 C2/native contrasts at 30 s on the Radar-matched events only (reason == labelled; every volume-selected event
    excluded), same bootstrap and settings as ``sensitivity``. Needs no event evidence."""
    arms, rows, published, provenance = mb.load_r1(args)
    ids = set(c.filter(pl.col("reason") == "labelled")["event_id"].to_list())
    out = {}
    for cid in ("C2", "native"):
        left, right = SENS_CONTRASTS[cid]
        key = f"{cid}@30"
        out[key] = {"left": left, "right": right, "radar_matched_only": masked_contrast(
            arms[left][30], arms[right][30], rows[30], ids, repetitions, seed),
            "all": masked_contrast(arms[left][30], arms[right][30], rows[30], set(c["event_id"].to_list()), repetitions, seed)}
    return {"kind": "leak_audit_no_volume_selected_sensitivity", "confirmatory": False,
            "population": {"radar_matched_events": len(ids), "cohort_events": c.height},
            "settings": {"repetitions": repetitions, "seed": seed, "bootstrap": "paired training-seed then incident-day-block, "
                         "blocks rebuilt from the kept events, ordinary 95 % interval, unadjusted"},
            "sensitivity": out, "r1_provenance": provenance, "source_sha256": mb.sha(__file__)}


def sensitivity(args, c, records, repetitions, seed):
    arms, rows, published, provenance = mb.load_r1(args)
    all_ids = set(c["event_id"].to_list())
    fp = {r["event_id"] for r in records if r["class"] == "likely_false_positive"}
    sampled = {r["event_id"] for r in records}
    credible = {r["event_id"] for r in records if r["class"] == "credible"}
    stratum_ids = {STRATUM_NAME[(reason, d1)]: set(c.filter((pl.col("reason") == reason) & (pl.col("day1") == d1))["event_id"].to_list())
                   for reason, d1 in STRATA}
    populations = {"all": all_ids, "excluding_sampled_likely_fp": all_ids - fp,
                   **{f"stratum_{k}": v for k, v in stratum_ids.items()},
                   "sample_all": sampled, "sample_credible": credible, "sample_not_likely_fp": sampled - fp}
    if all("independent" in r for r in records):  # classes fixed above, before any arm result is read
        populations["sample_independently_supported"] = {r["event_id"] for r in records
                                                         if r["independent"]["class"] == "supported"}
    out = {}
    for delta in (30, 60):
        for cid, (left, right) in SENS_CONTRASTS.items():
            key = f"{cid}@{delta}"
            a, b = arms[left][delta], arms[right][delta]
            entry = {"left": left, "right": right}
            for name, ids in populations.items():
                entry[name] = masked_contrast(a, b, rows[delta], ids, repetitions, seed)
            pub = published[key]
            got = entry["all"]
            ref = ranking_contrast(a, b, rows[delta], metric="average_precision", repetitions=repetitions, seed=seed)
            require(abs(got["difference"] - pub["difference"]) < 1e-12 and abs(ref["difference"] - got["difference"]) < 1e-12
                    and np.allclose(got["ci95"], pub["ci95"], atol=1e-12, rtol=0)
                    and got["eligible_events"] == pub["eligible_events"] and got["blocks"] == pub["blocks"],
                    f"R1 {key} does not reproduce the published value: {got['difference']} {got['ci95']} vs "
                    f"{pub['difference']} {pub['ci95']}")
            entry["published"] = {k: pub[k] for k in ("difference", "ci95", "eligible_events", "blocks")}
            entry["reproduced_exactly"] = True
            out[key] = entry
            print(f"{key}: " + "  ".join(f"{n} {v['difference']:+.4f} [{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}] n={v['eligible_events']}"
                                         if v.get("difference") is not None else f"{n} n={v['eligible_events']} (too few blocks)"
                                         for n, v in entry.items() if isinstance(v, dict) and "eligible_events" in v),
                  flush=True)
    return out, provenance, {"excluded_likely_fp_events": sorted(fp)}


# ----------------------------------------------------------------------------- outputs

def flat(e):
    t = e["triples"]
    fmt = lambda f: "|".join(f(x) for x in t)  # noqa: E731
    sib = e.get("as2org")
    word = {True: "sibling", False: "other", None: "unmapped"}
    return {
        "event_id": e["event_id"], "stratum": e["stratum"], "class": e["class"], "rule": e["rule"],
        "leaker": e["leaker"], "identifier_t0": e["identifier_t0"],
        "radar_matched": e["radar"]["matched"], "radar_label_ids": "|".join(e["radar"]["ids"]),
        "radar_peer_count_max": e["radar"]["peer_count_max"], "radar_prefix_count_max": e["radar"]["prefix_count_max"],
        "radar_leak_types": "|".join(e["radar"]["leak_types"]),
        "radar_duration_min_max": e["radar"]["duration_min_max"],
        "radar_segment_matches_triple": e["radar"]["segment_matches_a_triple"],
        "identifier_duration_min": e["identifier"]["duration_min"], "identifier_bins": e["identifier"]["bins"],
        "identifier_collectors": e["identifier"]["n_collectors"], "identifier_prefixes": e["identifier"]["n_prefixes"],
        "identifier_msgs": e["identifier"]["n_msgs"], "identifier_triples": e["identifier"]["n_triples"],
        "triples_recovered": len(t),
        "triples_xab": fmt(lambda x: f"{x['x']}-{x['a']}-{x['b']}"),
        "rel_month_learned_exported": fmt(lambda x: f"{x['month']['learned_from']}/{x['month']['exported_to']}"),
        "rel_next_learned_exported": fmt(lambda x: f"{x['next']['learned_from']}/{x['next']['exported_to']}"),
        "rel_prev_learned_exported": fmt(lambda x: f"{x['prev']['learned_from']}/{x['prev']['exported_to']}"),
        "next_status": fmt(lambda x: x["next_status"]),
        "triples_violating_next": sum(x["next_status"] == "violating" for x in t),
        "triples_valley_free_next": sum(x["next_status"] == "valley_free" for x in t),
        "triples_missing_next": sum(x["next_status"] == "missing" for x in t),
        "triples_in_prev_month": sum(x["in_prev_month_leaky_new_triples"] for x in t),
        "manifest_sources_upstreams_match": e["manifest_sources_upstreams_match"],
        "observation_lag_s": e["replay"]["observation_lag_s"], "replay_max_collectors": e["replay"]["max_collectors"],
        "replay_collectors_seeing": e["replay"]["collectors_seeing"],
        "replay_sessions_carrying": e["replay"]["sessions_carrying"], "leaked_prefixes": e["replay"]["leaked_prefixes"],
        "replay_duration_min": e["replay"]["duration_min"], "vp_final_2h": e["replay"]["vp_final_2h"],
        "asns_final_2h": e["replay"]["asns_final_2h"], "siblings_as2org": sib["status"] if sib else "not_evaluable",
        **({"as2org_snapshot": sib["snapshot"], "as2org_status_strict": sib["status_strict"],
            "as2org_any_sibling_adjacency": sib["any_sibling_adjacency"],
            "as2org_triples_sibling_adjacent": sib["triples_sibling_adjacent"],
            "as2org_violating_triples_non_sibling": sib["violating_triples_non_sibling"],
            "as2org_sibling_xa_ab": fmt(lambda x: f"{word[x['as2org']['sibling_x_a']]}/{word[x['as2org']['sibling_a_b']]}")}
           if sib else {}),
        # new columns (round 7, independent evidence); appended after the existing ones
        **({"triples_family": fmt(lambda x: x["family"])} if all("family" in x for x in t) else {}),
        **({"rel_v6_ipv6_triples": e["rel_v6"]["ipv6_triples"],
            "rel_v6_month_next_status": fmt(lambda x: f"{x['rel_v6']['month_status']}/{x['rel_v6']['next_status']}"
                                            if "rel_v6" in x else "ipv4"),
            "rel_v6_ipv6_triples_violating_both": e["rel_v6"]["ipv6_triples_violating_both"]} if "rel_v6" in e else {}),
        **({"independent_class": e["independent"]["class"], "independent_rule": e["independent"]["rule"],
            "independent_family": e["independent"]["family"], "independent_ipv6_triples": e["independent"]["ipv6_triples"],
            "independent_radar_segment_triples_non_sibling": e["independent"]["radar_segment_triples_non_sibling"],
            "independent_onset_xab": "|".join(f"{q['x']}-{q['a']}-{q['b']}" for q in e["independent"]["onset"]),
            "independent_onset_prefix": "|".join(q["example_prefix"] for q in e["independent"]["onset"]),
            "independent_onset_reason": "|".join(q["reason"] for q in e["independent"]["onset"]),
            "independent_onset_ris_carrying_start_max_end": "|".join(
                f"{q['peers_carrying_at_start']}/{q['peers_carrying_max']}/{q['peers_carrying_at_end']}"
                for q in e["independent"]["onset"]),
            "independent_onset_ris_first_carrying": "|".join(str(q["first_announcement_carrying"]) for q in e["independent"]["onset"]),
            "independent_onset_ris_last_stop": "|".join(str(q["last_stop_carrying"]) for q in e["independent"]["onset"]),
            "independent_onset_end_state_carrying": "|".join(str(q.get("end_state_peers_carrying")) for q in e["independent"]["onset"])}
           if "independent" in e else {}),
    }


def pct(x):
    return f"{100 * x:.0f}"


def signed(x):
    return f"{x:+.4f}".replace("-", "$-$")


def write_tex(path, props, weighted, sens, sib=None, ind=None):
    lines = ["% Generated by scripts/paper_leak_audit.py; do not edit by hand.",
             "% Panel A: audited sample of R1 test leaks by stratum: credible / likely false positive / ambiguous, counts and",
             "% shares with Wilson 95% intervals; cohort row: shares weighted by stratum size, with the same weights applied to",
             "% the stratum Wilson bounds (conservative descriptive bounds, not a joint interval). Panel B: R1 AP contrasts at 30 s, paired training-seed and incident-day-block",
             "% bootstrap (10,000 repetitions, seed 1701), ordinary 95% intervals; sample-based sensitivity, descriptive."]
    if sib:
        used = [d for d, s in sib["snapshots"].items() if s["used"]]
        w = sib["cohort_estimate"]["weighted_by_stratum_size"]
        lines += [f"% Comment only, not printed: AS2Org siblings (CAIDA AS Organizations {used[0]} to {used[-1]}), descriptors that no rule",
                  "% uses. Counts independent / sibling_only / no_violating_triple per class (leak_audit.json siblings):"]
        for name, v in sib["per_stratum"].items():
            lines.append(f"%   {STRATUM_TEX[name]}: " + ", ".join(
                f"{c} {'/'.join(str(v[c][s]['count']) for s in SIB_STATUS)}" for c in CLASSES))
        share = lambda c: "/".join(f"{100 * w[c][s]['share']:.1f}" for s in SIB_STATUS)  # noqa: E731
        lines.append("%   Cohort, weighted: " + ", ".join(f"{c} {share(c)} %" for c in CLASSES))
    if ind:
        lines += ["% Panel C (round 7): independent-evidence class of the same sample (leak_audit.json independent): supported /",
                  "% contradicted / uncertain by rules that use no CAIDA relationship file (exact Radar segment, RIS path evolution;",
                  "% AS2Org only to exclude; IPv6-only events uncertain); shares and weights as panel A. Panel B row \"Audited,",
                  "% independently supported\": the same contrasts on the supported events of the sample."]
    lines += ["\\begin{tabular}{@{}lrrlll@{}}", "\\toprule",
             "Stratum & Events & Audited & \\hd{Relationship-\\\\consistent} & \\hd{Relationship changed\\\\or missing} & Ambiguous \\\\", "\\midrule"]
    for name, v in props.items():
        cells = []
        for c in CLASSES:
            lo, hi = v[c]["wilson95"]
            cells.append(f"{v[c]['count']} ({pct(v[c]['share'])}\\,\\%; {pct(lo)}--{pct(hi)})")
        n = f"{v['population']:,}".replace(",", "{,}")
        lines.append(f"{STRATUM_TEX[name]} & {n} & {v['sampled']} & " + " & ".join(cells) + " \\\\")
    w = weighted["weighted_by_stratum_size"]
    lines.append("Cohort, weighted & " + f"{weighted['cohort_events']:,}".replace(",", "{,}") + " & & " + " & ".join(
        f"{100 * w[c]['share']:.1f}\\,\\% ({pct(w[c]['wilson_weighted_bounds'][0])}--{pct(w[c]['wilson_weighted_bounds'][1])})"
        for c in CLASSES) + " \\\\")
    lines += ["\\midrule", "Population (AP, 30\\,s) & Eligible & & C2 & Native & \\\\", "\\midrule"]
    rows = [("all", "All (published)"), ("excluding_sampled_likely_fp", "Without the sampled changed or missing"),
            ("stratum_radar_day1", "Radar, day 1"), ("stratum_radar_other", "Radar, other days"),
            ("stratum_volume_day1", "Volume, day 1"), ("stratum_volume_other", "Volume, other days"),
            ("sample_all", "Audited sample"), ("sample_credible", "Audited, relationship-consistent")]
    if ind:
        rows.append(("sample_independently_supported", "Audited, independently supported"))
    for key, label in rows:
        c2, nat = sens["C2@30"][key], sens["native@30"][key]

        def cell(v):
            if v.get("difference") is None:
                return "--"
            return f"{signed(v['difference'])} [{signed(v['ci95'][0])}, {signed(v['ci95'][1])}]"
        n = f"{c2['eligible_events']:,}".replace(",", "{,}")
        lines.append(f"{label} & {n} & & {cell(c2)} & {cell(nat)} & \\\\")
    if ind:
        lines += ["\\midrule",
                  "Stratum & Events & Audited & \\hd{Independently\\\\supported} & \\hd{Independently\\\\contradicted} & Uncertain \\\\",
                  "\\midrule"]
        for name, v in ind["per_stratum"].items():
            cells = [f"{v[c]['count']} ({pct(v[c]['share'])}\\,\\%; {pct(v[c]['wilson95'][0])}--{pct(v[c]['wilson95'][1])})"
                     for c in IND_CLASSES]
            n = f"{v['population']:,}".replace(",", "{,}")
            lines.append(f"{STRATUM_TEX[name]} & {n} & {v['sampled']} & " + " & ".join(cells) + " \\\\")
        w = ind["cohort_estimate"]["weighted_by_stratum_size"]
        lines.append("Cohort, weighted & " + f"{ind['cohort_estimate']['cohort_events']:,}".replace(",", "{,}") + " & & " + " & ".join(
            f"{100 * w[c]['share']:.1f}\\,\\% ({pct(w[c]['wilson_weighted_bounds'][0])}--{pct(w[c]['wilson_weighted_bounds'][1])})"
            for c in IND_CLASSES) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", ""]
    Path(path).write_text("\n".join(lines))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("events", "data", "r1-report", "r1-per-event", "r1-arm-spec", "r1-manifest-30", "r1-manifest-60",
                 "out-json", "out-tex", "out-csv"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--novolume-only", help="write only the Radar-matched-only sensitivity JSON to this path and exit "
                   "(--out-* and --data are still required arguments but are not written or read)")
    p.add_argument("--as2org", nargs="+", help="CAIDA AS Organizations snapshots (YYYYMMDD.as-org2info.txt[.gz]) for the "
                   "sibling descriptors; without it the sibling fields read not_evaluable")
    p.add_argument("--asrel-v6", nargs="+", help="CAIDA serial-1 YYYYMM01.as-rel.v6-stable.txt.bz2 files (event and next "
                   "months) for the IPv6 relationship descriptor; no rule uses them")
    p.add_argument("--ris", help="directory of RIPEstat BGPlay files (MANIFEST.json) for the independent-evidence class; "
                   "needs --as2org")
    p.add_argument("--ris-fetch", action="store_true", help="download the missing RIPEstat files into --ris")
    p.add_argument("--per-stratum", type=int, default=PER_STRATUM)
    p.add_argument("--repetitions", type=int, default=REPS)
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args()

    c, population = cohort(args)
    if args.novolume_only:
        res = novolume_sensitivity(args, c, args.repetitions, args.seed)
        Path(args.novolume_only).write_text(json.dumps(res, indent=1, default=str) + "\n")
        print(json.dumps({k: v["radar_matched_only"] for k, v in res["sensitivity"].items()}, default=str))
        return
    sample, sizes = draw(c, args.per_stratum, args.seed)
    rows = {r["event_id"]: r for r in c.iter_rows(named=True)}
    ev = Evidence(Path(args.data))
    as2org = As2Org(args.as2org) if args.as2org else None
    require(not args.ris or as2org, "--ris needs --as2org (rules I1 to I3 and the onset triples use the sibling descriptor)")
    rel6 = Rel6(args.asrel_v6) if args.asrel_v6 else None
    ris = Ris(args.ris, args.ris_fetch) if args.ris else None
    anon = Anon(args)
    records = []
    for eid, stratum in sample:
        e = gather(ev, rows[eid])
        e["stratum"] = stratum
        e["class"], e["rule"] = classify(e)
        if as2org:
            siblings(e, as2org)  # after classify: a descriptor, never an input of the rules
        for t in e["triples"]:
            require(t["example_prefix"], f"{eid}: triple without an example prefix")
            t["family"] = "ipv6" if ":" in t["example_prefix"] else "ipv4"
        if rel6:
            e["rel_v6"] = rel6.describe(e)  # descriptor only
        if ris:
            e["independent"] = independent_class(e, ev, ris)  # before any arm result is read (sensitivity below)
        records.append(e)
    props, weighted = proportions(records, sizes)
    for k, v in props.items():
        print(k, v["population"], v["sampled"], {cl: (v[cl]["count"], [round(x, 3) for x in v[cl]["wilson95"]]) for cl in CLASSES},
              v["rules"], flush=True)
    print("weighted", json.dumps(weighted["weighted_by_stratum_size"]), flush=True)
    sib = sibling_table(records, sizes, as2org) if as2org else None
    if sib:
        for k, v in sib["per_stratum"].items():
            print("siblings", k, {c: [v[c][s]["count"] for s in SIB_STATUS] for c in CLASSES}, flush=True)
        print("siblings weighted", json.dumps({c: {s: round(x["share"], 6) for s, x in v.items()}
                                               for c, v in sib["cohort_estimate"]["weighted_by_stratum_size"].items()}), flush=True)
    ind = independent_table(records, sizes) if ris else None
    if ind:
        for k, v in ind["per_stratum"].items():
            print("independent", k, {cl: (v[cl]["count"], [round(x, 3) for x in v[cl]["wilson95"]]) for cl in IND_CLASSES},
                  v["rules"], flush=True)
        print("independent weighted", json.dumps(ind["cohort_estimate"]["weighted_by_stratum_size"]), flush=True)
        print("independent x relationship class", json.dumps(ind["crosstab_relationship_class"]), flush=True)
        print("independent family", json.dumps(ind["family_totals"]), flush=True)
    if sib:
        for s in sib["snapshots"].values():
            s["path"] = anon(s["path"])
    flat_rows = [flat(e) for e in records]
    pl.DataFrame(flat_rows, infer_schema_length=None).write_csv(args.out_csv)
    sens, provenance, excluded = sensitivity(args, c, records, args.repetitions, args.seed)
    triple_stats = {s: sum(sum(x["next_status"] == s for x in e["triples"]) for e in records)
                    for s in ("violating", "valley_free", "missing")}
    out = {
        "kind": "leak_benchmark_validity_audit_revision_analysis", "confirmatory": False,
        "replaces_published_values": False,
        "population": population, "strata": sizes,
        "sampling": {"per_stratum": args.per_stratum, "rng": f"numpy default_rng({args.seed})",
                     "order": [STRATUM_NAME[s] for s in STRATA], "within_stratum": "event_ids sorted, choice without replacement"},
        "rules": {
            "A0_no_triple": "ambiguous: no valley-violating triple of the leaker in [t0 - 1 min, t_last + 5 min]",
            "next_status": "per triple, next month's CAIDA: violating (both adjacencies provider/peer), valley_free (an "
                           "adjacency is a customer link), missing (an adjacency absent)",
            "A1_radar_conflict": "ambiguous: no triple violating next month, but Radar matched the event",
            "F1_rel_changed_next": "likely false positive: no triple violating next month, at least one valley-free",
            "F2_rel_missing_next": "likely false positive: no triple violating next month, all have a missing adjacency",
            "A2_preexisting_path": "ambiguous: a triple violating in both months, but the replay saw the route from the "
                                   f"start of its one-hour look-back (observation lag <= {LOOKBACK_EDGE_S:.0f} s) and every "
                                   "such triple was already a valley-violating new triple in the previous month",
            "C1_stable_violation": "credible: a triple violating in both months and A2 does not fire",
            "siblings": ("descriptor, not a rule: CAIDA AS Organizations sibling status of the triples violating next month "
                         "(independent / sibling_only / no_violating_triple), see siblings.status_rule" if sib else
                         "not evaluable: no CAIDA AS Organizations (as2org) file in the repository or the data root")},
        "proportions": props, "cohort_estimate": weighted,
        "triple_next_month_status_totals": triple_stats,
        **({"siblings": sib} if sib else {}),
        **({"independent": {
            "kind": "independent_evidence_class", "rules_fixed_utc": RULES_FIXED_UTC,
            "blind_to_arm_results": "classes assigned in the event loop, before sensitivity() reads any R1 arm",
            "rules": {
                "inputs": "T = recovered triples (not filtered by next-month status); sibling(t) = x~a or a~b share an org_id "
                          "(AS2Org, event month); family(t) = IPv6 if the example prefix contains ':'; Radar segment match = "
                          "a matched Radar label with {leak_seg[0], leak_seg[2]} == {x, b}; onset triples Q = first "
                          f"{ONSET_TRIPLES} of T by (first_ts, x, b) among IPv4 triples without a sibling adjacency; RIS = "
                          f"RIPEstat BGPlay of each Q example prefix over [t0 - {RIS_BEFORE_S} s, t0 + {RIS_AFTER_S} s], a "
                          "path carries q if x, a, b are consecutive hops after collapsing prepending",
                "P1": "q is not among the previous month's classified new triples (any class)",
                "P2": f"replay observation lag > {LOOKBACK_EDGE_S:.0f} s", "P3": "no RIS peer carries q at the window start",
                "P4": "a RIS announcement in the window carries q", "P5": "no RIS peer carries q at the window end",
                "I0_no_triple": "uncertain: T empty",
                "I1_sibling_only": "contradicted: every triple has a sibling adjacency, no Radar segment matches a triple",
                "I2_sibling_radar_conflict": "uncertain: every triple has a sibling adjacency, a Radar segment matches one",
                "I3_radar_segment": "supported: a Radar segment matches a triple without a sibling adjacency",
                "I4_ipv6_only": "uncertain: every triple has an IPv6 example prefix (IPv4-inferred relationships cannot judge it)",
                "I5_path_evolution": "supported: some onset triple passes P1 to P5",
                "I6": "uncertain: no_eligible_triple (Q empty), else the first of ris_unavailable (P1 and P2 pass, RIPEstat "
                      "could not serve the window), long_lived (P5 fails), not_seen_in_ris (P4 fails), preexisting (P1, P2 or "
                      "P3 fails) that some onset triple has",
                "missing_data": "added 2026-11-01 after RIPEstat failed on busy prefixes, before any contrast on a new "
                                "subset: whole window, then 3 and 9 contiguous parts; a window no level serves is recorded "
                                "unavailable",
                "P5_end_state": "added at the same time (BGPlay event lists can be incomplete): a q passing P1 to P5 on the "
                                "event list also needs no peer carrying q in RIPEstat's own state at t0 + 2 h (initial state "
                                f"of a {RIS_END_S}-s query); else long_lived, or ris_unavailable if that query fails"},
            "sources": {"ripestat_bgplay": RIS_URL, "ris_files": dict(sorted(ris.used.items())),
                        "radar_method": RADAR_METHOD_URL,
                        "radar_method_note": "Radar combines CAIDA relationships with Cloudflare's own and reads RouteViews "
                                             "and RIS updates: I3 is corroboration by a separate detector, not ground truth"},
            **ind,
            "rel_v6": ({"source": "https://publicdata.caida.org/datasets/as-relationships/serial-1/ "
                                  "YYYYMM01.as-rel.v6-stable.txt.bz2 (descriptor only; no rule uses it)",
                        "files": {k: {**m, "path": anon(m["path"])} for k, m in sorted(rel6.meta.items())},
                        "ipv6_triple_totals": {k: sum(e["rel_v6"][k] for e in records)
                                               for k in records[0]["rel_v6"] if k.startswith("ipv6_triples")},
                        "by_independent_class": {cl: {k: sum(e["rel_v6"][k] for e in records if e["independent"]["class"] == cl)
                                                      for k in records[0]["rel_v6"] if k.startswith("ipv6_triples")}
                                                 for cl in IND_CLASSES}} if rel6 else "not evaluated"),
            "note": "Not a precision estimate: 120 sampled events, rules not validated against labelled truth. Radar segment "
                    "and RIS path evolution are evidence beyond the CAIDA relationship test, not proof of a leak. Weighting "
                    "as cohort_estimate (not a joint interval). Contrasts: sensitivity[*].sample_independently_supported "
                    "(few events and day blocks, so the intervals are wide)."}} if ind else {}),
        "ambiguous_cases": [flat(e) for e in records if e["class"] == "ambiguous"],
        "likely_false_positive_cases": [flat(e) for e in records if e["class"] == "likely_false_positive"],
        "manifest_check": {"events_checked": sum(e["manifest_sources_upstreams_match"] is not None for e in records),
                           "matching": sum(bool(e["manifest_sources_upstreams_match"]) for e in records)},
        "sensitivity": sens, "sensitivity_note": (
            "Sample-based: only sampled events are classified, so excluding the sampled likely false positives removes a "
            "lower bound of the cohort's likely false positives; the stratum rows give the contrasts within each stratum "
            "on all its eligible events. Paired training-seed and incident-day-block bootstrap (blocks rebuilt from the "
            "kept events), ordinary 95 % intervals, unadjusted."),
        **excluded,
        "inputs_sha256": {**{anon(k): v for k, v in ev.files.items()}, anon(args.events): mb.sha(args.events),
                          anon(Path(args.data) / "labels" / "cloudflare_leaks.parquet"):
                              mb.sha(Path(args.data) / "labels" / "cloudflare_leaks.parquet"),
                          **({anon(s["path"]): s["sha256"] for s in as2org.snap.values()} if as2org else {}),
                          **({anon(m["path"]): m["sha256"] for m in rel6.meta.values()} if rel6 else {}),
                          **({anon(ris.manifest_path): mb.sha(ris.manifest_path)} if ris else {})},
        "r1_provenance": provenance, "events": records, "source_sha256": mb.sha(__file__)}
    Path(args.out_json).write_text(json.dumps(out, indent=1, default=str) + "\n")
    write_tex(args.out_tex, props, weighted, sens, sib, ind)
    print("wrote", args.out_json, args.out_tex, args.out_csv)


if __name__ == "__main__":
    main()
