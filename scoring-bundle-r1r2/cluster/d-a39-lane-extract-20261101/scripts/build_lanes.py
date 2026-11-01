"""Build paper/generated/newperiod-lanes.{json,tex} from the D-A39 extraction (no metric is recomputed).

Inputs (copied read-only from <BATCH_HOST>, d-a39-lane-extract-20261101/out and the run log):
  extract-full.json      recorded per-family summaries (scripts/extract_lanes.py)
  stable-narrow-v2.json  label-free bound on the stable failure (scripts/stable_narrow.py)
  sha256-small.txt, manifests/, completion.json, r2-d-a39-v2-52728251.out, validate-*.jsonl
Values copied from the record: cell statuses/counts, scorable events, recorded per-seed mean_difference of each paired
contrast. The table shows, per group, the min and max of the recorded per-seed values (a range, not an interval).
usage: python3 -I build_lanes.py <in-dir> <out.json> <out.tex>
"""
import collections, json, math, re, sys
from datetime import datetime, timezone

IN, OUT_JSON, OUT_TEX = sys.argv[1], sys.argv[2], sys.argv[3]
X = json.load(open(f"{IN}/extract-full.json"))
NARROW = json.load(open(f"{IN}/stable-narrow-v2.json"))
COMPLETION = json.load(open(f"{IN}/completion.json"))
F = X["families"]
RUN_OUT = "<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-rescore-D-A39-logs/r2-d-a39-v2-52728251.out"
RECORDS = "<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39"
EXTRACT_DIR = "<FORECAST_ROOT>/d-a39-lane-extract-20261101"

# ----------------------------------------------------------------------------------------------- verification
log_families = {}
for line in open(f"{IN}/r2-d-a39-v2-52728251.out"):
    rec = json.loads(line).get("d_a39", {})
    if "family" in rec:
        log_families[rec["family"]["family"]] = rec["family"]
part_sha = {}
for line in open(f"{IN}/sha256-small.txt"):
    digest, path = line.split()
    m = re.search(r"/families/(.+)\.pkl\.part0000$", path)
    if m:
        part_sha[m.group(1)] = digest
sizes = {}
for line in open(f"{IN}/stat.txt"):
    p, size = line.split()[:2]
    m = re.search(r"/families/(.+)\.pkl\.part0000$", p)
    if m:
        sizes[m.group(1)] = int(size)
verification = {}
for name in sorted(F):
    man = json.load(open(f"{IN}/manifests/{name}.manifest.json"))
    logged = log_families[name]
    extracted = F[name]["receipt"]
    verification[name] = {
        "parts": man["parts"], "bytes": man["bytes"], "sha256": man["sha256_of_concatenated_parts"],
        "size_on_disk_matches_manifest": sizes[name] == man["bytes"],
        "sha256sum_matches_manifest": part_sha[name] == man["sha256_of_concatenated_parts"],
        "manifest_equals_run_log_receipt": logged["persisted"] == man,
        "extraction_load_verified": extracted["verified_sha256"] == man["sha256_of_concatenated_parts"]
                                    and extracted["bytes"] == man["bytes"],
        "run_log_status": logged["status"], "run_log_seconds": logged["seconds"]}
all_verified = all(v["size_on_disk_matches_manifest"] and v["sha256sum_matches_manifest"] and v["manifest_equals_run_log_receipt"]
                   and v["extraction_load_verified"] for v in verification.values())


def validator(path):
    rows = [json.loads(l) for l in open(path)]
    summary = next((r for r in rows if "summary" in r), None)
    failed = {r["check"]: {k: v for k, v in r.items() if k not in ("check", "ok", "note")} for r in rows
              if "check" in r and r.get("ok") is False}
    return {"summary": summary, "checks_reported": sum(1 for r in rows if "check" in r), "failed_checks": failed,
            "passed_checks": sorted(r["check"] for r in rows if "check" in r and r.get("ok") is True)}


# -------------------------------------------------------------------------------------------------- helpers
def cells_of(name, stratum=None):
    f = F[name]
    return f["strata"][stratum]["cells"] if stratum else f.get("cells", [])


def status_counts(cells):
    return dict(collections.Counter(c["status"] for c in cells))


def events_by_horizon(cells):
    out = collections.defaultdict(set)
    for c in cells:
        if c["status"] == "scored":
            out[str(c["role"]["horizon_seconds"])].add(c["scorable_events"])
    return {h: sorted(v) for h, v in sorted(out.items(), key=lambda kv: int(kv[0]))}


def contrast_groups(name, label_fn):
    f = F[name]
    roles = {c["arm_id"]: c["role"] for c in f["cells"]}
    groups = collections.OrderedDict()
    for c in f["contrasts"]:
        r = roles[c["arm_id"]]
        key = label_fn(c, r)
        g = groups.setdefault(key, {"group": dict(key), "events": set(), "comparators": set(), "status": set(), "by_seed": []})
        g["events"].add(c["events"])
        g["comparators"].add(json.dumps(c["comparator"]))
        g["status"].add(c["status"])
        g["by_seed"].append([r.get("seed"), c["mean_difference"]])
    out = []
    for g in groups.values():
        vals = [s[1] for s in g["by_seed"]]
        out.append({**g["group"], "events": sorted(g["events"]), "status": sorted(g["status"]),
                    "comparator_example": json.loads(sorted(g["comparators"])[0]), "n": len(vals),
                    "min_recorded": min(vals), "max_recorded": max(vals), "seed_mean_difference": g["by_seed"]})
    return out


def lane(key, paper, family, cells, *, comparator=None, metric=None, cohort=None, groups=None, reasons=None, extra=None):
    sc = status_counts(cells)
    scored = sc.get("scored", 0)
    entry = {"lane": key, "paper_name": paper, "internal_family": family, "roles": len(cells), "scored": scored,
             "not_scored": len(cells) - scored, "cell_status_counts": sc, "scorable_events_per_cell": events_by_horizon(cells),
             "censored_events_total": sum(c.get("censored_events") or 0 for c in cells),
             "not_scored_reasons": reasons or {}}
    if groups is not None:
        entry["contrast"] = {"definition": comparator, "metric": metric, "cohort": cohort, "intervals_recorded": False,
                             "groups": groups}
    else:
        entry["contrast"] = None
    if extra:
        entry.update(extra)
    return entry


def flags(name, stratum=None):
    f = F[name]["strata"][stratum] if stratum else F[name]
    return {k: f.get(k) for k in ("kind", "intervals_computed", "formal_tests", "selection_performed", "declares_primary_finding")
            if k in f}


# ---------------------------------------------------------------------------------------------------- lanes
lanes = []
h1 = contrast_groups("membership-h1", lambda c, r: (("metric", c["metric"]), ("cohort", c["cohort"]),
                                                    ("model", r["message_passing"]), ("horizon_s", r["horizon_seconds"])))
lanes.append(lane("candidate_expansion", "Candidate expansion (H1)", "membership-h1", cells_of("membership-h1"),
                  comparator="H1 arm (original candidates plus the top-500 completed-history ASNs) minus the updated core arm "
                             "with history, same message passing, horizon and training seed (original candidates)",
                  metric="full_target_jaccard and committed_two_threshold_jaccard", cohort="full_reference", groups=h1,
                  extra={"flags": flags("membership-h1")}))
h3 = contrast_groups("membership-h3", lambda c, r: (("cohort", c["cohort"]), ("stage", r["stage"]), ("panel", r["panel"]),
                                                    ("model", r["message_passing"]), ("horizon_s", r["horizon_seconds"])))
lanes.append(lane("reduced_collectors", "Seven of ten collectors (H3)", "membership-h3", cells_of("membership-h3"),
                  comparator="seven-collector input arm (ris7: RIS only; mixed7: three RouteViews + four RIS; stage frozen = "
                             "the matching ten-collector core checkpoint reused (producer checks checkpoint_sha256 equality), refit = refitted) minus the ten-collector updated core arm, same message passing, "
                             "horizon and seed; both scored on the ten-collector target",
                  metric="full_target_jaccard", cohort="full_reference, common_available, common_complete", groups=h3,
                  extra={"flags": flags("membership-h3"), "h3_cohort_sizes": F["membership-h3"].get("h3_cohort_sizes")}))
stable_roles = 24   # stable consumer roles(): sage/none x 30/60 x 5 seeds + persistence/history-knn-mean x 30/60
stable_cells = [{"status": "failed"} for _ in range(stable_roles)]
first = NARROW["possible_failing_cells"]
lanes.append({"lane": "stable_peers", "paper_name": "Stable peers", "internal_family": "stable", "roles": stable_roles, "scored": 0,
              "not_scored": stable_roles, "cell_status_counts": {"family_failed_no_cell_results": stable_roles},
              "scorable_events_per_cell": {}, "censored_events_total": None,
              "roles_source": "stable consumer roles() (24) and the validator section count; the failed record holds no cells",
              "not_scored_reasons": {"family_failed": F["stable"]["error"]}, "contrast": None})
tm = contrast_groups("membership-timing", lambda c, r: (("cohort", c["cohort"]), ("model", r["message_passing"]),
                                                        ("horizon_s", r["horizon_seconds"])))
lanes.append(lane("input_timing", "Input timing", "membership-timing", cells_of("membership-timing"),
                  comparator="timing arm at horizon d minus the same message passing and seed at 30 s (timing family), fixed cohort",
                  metric="full_target_jaccard", cohort="fixed_timing", groups=tm,
                  extra={"flags": flags("membership-timing"),
                         "broader_training_reused_at_30_60_seconds": F["membership-timing"].get("broader_training_reused_at_30_60_seconds")}))
origin_cells = cells_of("origin", "origin_change_invalid") + cells_of("origin", "origin_change_valid")
lanes.append(lane("origin_changes", "Origin changes", "origin", origin_cells,
                  extra={"strata": {s: {"roles": len(cells_of("origin", s)), "cell_status_counts": status_counts(cells_of("origin", s)),
                                        "scorable_events_per_cell": events_by_horizon(cells_of("origin", s)),
                                        **{k: F["origin"]["strata"][s].get(k) for k in ("incident_count", "actor_day_collapsed_count",
                                           "limited_independent_support", "interpretation")},
                                        "flags": flags("origin", s)}
                                    for s in ("origin_change_invalid", "origin_change_valid")},
                         "valid_family_branch": F["origin"].get("valid_family_branch"),
                         "contrast_note": "the origin report records per-event scores per cell only; no paired contrast is recorded"}))
hist = contrast_groups("membership-history", lambda c, r: (("cohort", c["cohort"]), ("variant", r["variant"]),
                                                           ("arm", r.get("message_passing") or f"history-knn-mean/{r.get('candidates')}"),
                                                           ("horizon_s", r["horizon_seconds"])))
lanes.append(lane("history_service", "History delay and withholding", "membership-history", cells_of("membership-history"),
                  comparator="history-service variant (delay900, delay1800, withhold) minus the matched updated core arm with history "
                             "(neural, same message passing/horizon/seed) or the primary online history-knn-mean baseline (same candidates)",
                  metric="full_target_jaccard", cohort="full_reference", groups=hist, extra={"flags": flags("membership-history")}))
ordi = cells_of("membership-ordinary")
lanes.append(lane("ordinary_models", "Ordinary temporal models", "membership-ordinary", ordi,
                  reasons={"not_estimable": "TGN and mean-aggregation roles (20): retained R1 failures (failure chain: "
                                            "retrospective-2025-v6b-tuning-r2 selection.json + ledger.json)"},
                  extra={"flags": flags("membership-ordinary"), "planned_seed_population": F["membership-ordinary"].get("planned_seed_population"),
                         "contrast_note": "no contrast is declared for ordinary models (consumer: 'Ordinary methods have no newly declared contrasts')"}))
cnt = cells_of("counts")
lanes.append(lane("count_forecasts", "Count forecasts", "counts", cnt,
                  reasons={"not_estimable": "count and Chronos roles (34): retained failures, failure chain "
                                            "complete-retention-bindings-astra-v1/count-rb-disposition.json"},
                  extra={"flags": {"kind": F["counts"].get("kind"), "declares_primary_finding": F["counts"].get("declares_primary_finding")},
                         "targets_s": F["counts"].get("targets_s")}))
lanes.append(lane("additional_baselines", "Additional baselines", "additional_baselines", cells_of("additional_baselines"),
                  extra={"flags": flags("additional_baselines"),
                         "contrast_note": "the additional-baseline report records per-event scores per cell only; no paired contrast is recorded"}))

totals = {k: sum(l[k] for l in lanes) for k in ("roles", "scored", "not_scored")}

stable_failure = {
    "error": F["stable"]["error"],
    "raised_at": "forecast_custodian_eval.py:409 _jaccard, called from per_event_rows line 514 ('jaccard': _jaccard(truth, predicted)) "
                 "via stable reviewed_membership.score_cell line 247 and stable consumer.evaluate line 135 (non-persistence branch)",
    "event_id_recorded": False,
    "why_not_recorded": "neither the failed family record (error + traceback) nor the run log names the event, horizon or arm",
    "label_free_bound": {
        "source": NARROW["checkpoint"]["path"], "checkpoint_sha256": NARROW["checkpoint"]["sha256"],
        "checkpoint_matches_run_log": NARROW["checkpoint"]["matches_run_log"],
        "scoring_order_first_cell": NARROW["cells_in_scoring_order"][0]["arm_id"],
        "empty_predictions_are_exactly_no_input_abstentions": all(
            c.get("empty_prediction_events") == c.get("empty_prediction_abstentions") for c in NARROW["cells_in_scoring_order"]),
        "abstention_sets_identical_across_cells_per_horizon": NARROW["abstention_sets_identical_across_cells_per_horizon"],
        "abstention_events": {"30": NARROW["cells_in_scoring_order"][0]["empty_prediction_abstentions"],
                              "60": next(c for c in NARROW["cells_in_scoring_order"] if c["role"]["horizon_seconds"] == 60)["empty_prediction_abstentions"]},
        "abstention_overlap_30_60": NARROW["abstention_overlap_30_60"],
        "possible_failing_cells": [{"order": p["order"], "arm_id": p["arm_id"], "horizon_s": p["role"]["horizon_seconds"],
                                    "candidate_events": p["candidates_in_scoring_order"]} for p in first],
        "conclusion": ("The trigger is a certified no-input abstention event (input_status unavailable_no_input, committed prediction "
                       "empty by rule) whose stable-peer target is scorable and empty. The arm is stable-d30-history-knn-mean (the first "
                       "cell scored) if any of its 29 abstention events has such a target, otherwise stable-d60-history-knn-mean "
                       "(25 candidates). Which event cannot be fixed without opening the stable targets, which this extraction did not do."),
    },
}

validators = {}
for tag in ("explore", "require-complete"):
    try:
        validators[tag] = validator(f"{IN}/validate-{tag}.jsonl")
    except FileNotFoundError:
        pass

doc = {
    "kind": "newperiod_r2_secondary_lanes_D-A39_extract_v1",
    "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "records": RECORDS, "run_log": RUN_OUT, "job_id": COMPLETION.get("job_id"),
    "completion": {k: COMPLETION.get(k) for k in ("passed", "blocking", "errors", "label_reads", "outcome_release_authorized", "utc",
                                                    "secondary_result", "raw_result")},
    "extraction": {"cluster_dir": EXTRACT_DIR, "scripts": ["scripts/extract_lanes.py", "scripts/stable_narrow.py", "scripts/build_lanes.py"],
                   "rule": "values are copied from the family pickles; per group the table shows min..max of the recorded per-seed "
                           "mean_difference (range, not an interval); no metric is recomputed; labels were not opened"},
    "family_verification": {"all_verified": all_verified, "families": verification},
    "validator": {"path": "scratch/experiment-finish-20261030/audit/validate_final_data.py",
                  "sha256": "e1302c03c56fdab57092851cfbafeb007def814ff5be4560263395f5a214fad2", "runs": validators},
    "lane_mapping": {
        "source": ["paper/sections/08-forecast.tex (five lanes: expand the candidates, seven of ten collectors, stable peers, "
                   "input timing, origin changes)", "docs/paper/forecasting-improvement-20261017/NEW-PERIOD-PROTOCOL.md (H3, candidate "
                   "expansion, temporal models, timing and family arms; history delivery delay sensitivity at 900/1800 s)",
                   "CANDIDATE-EXPANSION.md (H1 = candidate expansion)", "H3-PANEL-BUILDER.md (ris7 / mixed7 panels)",
                   "FAMILY-FEASIBILITY.md (RFC 6811 validity strata)"],
        "map": {"membership-h1": "candidate_expansion", "membership-h3": "reduced_collectors", "stable": "stable_peers",
                "membership-timing": "input_timing", "origin": "origin_changes (origin_change_invalid, origin_change_valid)",
                "membership-history": "history_service (secondary, not one of the five lanes)",
                "membership-ordinary": "ordinary_models (secondary, not one of the five lanes)",
                "counts": "count_forecasts (secondary, not one of the five lanes)",
                "additional_baselines": "additional_baselines (secondary, not one of the five lanes)"}},
    "totals": totals,
    "lanes": lanes,
    "stable_failure": stable_failure,
}
with open(OUT_JSON, "w") as f:
    json.dump(doc, f, indent=1, sort_keys=False)
    f.write("\n")


# ---------------------------------------------------------------------------------------------------- LaTeX
def num(x, d):
    return f"{x:+.{d}f}".replace("-", "$-$")


def rng(g, d):
    a, b = num(g["min_recorded"], d), num(g["max_recorded"], d)
    return a if a == b else f"{a} to {b}"


def pick(groups, **want):
    hits = [g for g in groups if all(g.get(k) == v for k, v in want.items())]
    assert len(hits) == 1, (want, len(hits))
    return hits[0]


def thou(n):
    return f"{n:,}".replace(",", "{,}")


L = {l["lane"]: l for l in lanes}
ev = lambda key, h="30": thou(L[key]["scorable_events_per_cell"][h][0])
h1s = [pick(h1, metric="full_target_jaccard", model="sage", horizon_s=s) for s in (30, 60)]
h1n = max(max(abs(g["min_recorded"]), abs(g["max_recorded"])) for g in h1 if g["model"] == "none" and g["metric"] == "full_target_jaccard")
h1n_bound = math.ceil(h1n * 1e4) / 1e4      # rounded UP so the printed bound holds
h3row = lambda panel, stage: " / ".join(rng(pick(h3, cohort="full_reference", stage=stage, panel=panel, model="sage", horizon_s=s), 3)
                                       for s in (30, 60))
tim = ", ".join(f"{s}\\,s {rng(pick(tm, model='sage', horizon_s=s), 3)}" for s in (5, 10, 60, 300, 900))
hmax = max(max(abs(g["min_recorded"]), abs(g["max_recorded"])) for g in hist)
hmax_bound = math.ceil(hmax * 1e4) / 1e4
oi, ov = L["origin_changes"]["strata"]["origin_change_invalid"], L["origin_changes"]["strata"]["origin_change_valid"]

rows = [
    ("Candidate expansion (H1)", "candidate_expansion",
     f"SAGE {rng(h1s[0], 4)} (30\\,s), {rng(h1s[1], 4)} (60\\,s); no message passing $|\\Delta|<{h1n_bound:.4f}$; {ev('candidate_expansion')} events"),
    ("Seven of ten collectors (H3)", "reduced_collectors",
     f"SAGE, 30\\,s / 60\\,s: RIS only, same weights {h3row('ris7', 'frozen')}; RIS only, refitted {h3row('ris7', 'refit')}; "
     f"mixed, same weights {h3row('mixed7', 'frozen')}; mixed, refitted {h3row('mixed7', 'refit')}; {ev('reduced_collectors')} events"),
    ("Stable peers", "stable_peers",
     "not scored: the scorer stopped on a no-input event whose stable-peer target and prediction were both empty (Jaccard undefined)"),
    ("Input timing", "input_timing", f"SAGE minus the same seed at 30\\,s: {tim}; {ev('input_timing')} events"),
    ("Origin changes", "origin_changes",
     f"no contrast recorded; RPKI-invalid {thou(oi['scorable_events_per_cell']['30'][0])}, "
     f"valid {thou(ov['scorable_events_per_cell']['30'][0])} events per role"),
    None,
    ("History delay, withholding", "history_service",
     f"all {sum(g['n'] for g in hist)} contrasts $|\\Delta|<{hmax_bound:.4f}$; {ev('history_service')} events"),
    ("Ordinary temporal models", "ordinary_models",
     "no contrast declared; TGN and mean aggregation (20 roles) are retained R1 failures"),
    ("Count forecasts", "count_forecasts", "not estimable: retained count and Chronos failures"),
    ("Additional baselines", "additional_baselines", f"no contrast recorded; {ev('additional_baselines')} events per role"),
]

lines = [
    "% Generated by build_lanes.py (copy: " + EXTRACT_DIR + "/scripts/) from the D-A39 family records; do not edit by hand.",
    "% Values: recorded per-seed mean full-target Jaccard differences (lane arm minus matched comparator), shown as the range",
    "% over the five training seeds (one value when both ends round alike); no lane records an interval or a test.",
    "% src: paper/generated/newperiod-lanes.json",
    "\\begin{table*}[t]",
    "\\footnotesize",
    "\\centering",
    "\\begin{tabular}{@{}lrrrp{0.59\\textwidth}@{}}",
    "\\toprule",
    "Lane & Roles & Scored & Not scored & Recorded paired difference in full-target \\Jac\\ (range over five seeds) \\\\",
    "\\midrule",
]
for r in rows:
    if r is None:
        lines.append("\\midrule")
        continue
    name, key, text = r
    l = L[key]
    lines.append(f"{name} & {l['roles']} & {l['scored']} & {l['not_scored']} & {text} \\\\")
lines += [
    "\\midrule",
    f"Total & {totals['roles']} & {totals['scored']} & {totals['not_scored']} & \\\\",
    "\\bottomrule",
    "\\end{tabular}",
    "\\caption{Secondary lanes of the disclosed re-scoring (R2). A role is one retained model configuration, horizon and seed. "
    "H1, H3 and the history lane compare each role with the matching updated model with history (same message passing, "
    "horizon and seed), or with the online history baseline, on the same events. "
    "H3 feeds seven collectors (RIS only, or mixed) instead of ten to the same weights or to a refitted model "
    "and scores against the ten-collector target. "
    "The timing lane compares each horizon with 30\\,s on one fixed cohort. "
    "The evaluator records no interval or test for any lane.}",
    "\\label{tab:r2-lanes}",
    "\\end{table*}",
]
with open(OUT_TEX, "w") as f:
    f.write("\n".join(lines) + "\n")
print("all_verified", all_verified, "totals", totals)
for r in rows:
    if r:
        print(r[0], "|", L[r[1]]["roles"], L[r[1]]["scored"], L[r[1]]["not_scored"], "|", r[2])
