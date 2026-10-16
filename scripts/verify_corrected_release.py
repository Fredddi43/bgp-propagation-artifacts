"""Independently verify the declared paper-result files in a corrected snapshot.

The JSON manifest declares event_tables (directory names), pair_tables and
model_tables (paths relative to data), optional required_files, and optional
model_targets {CSV: {event_table or event_tables, horizon}} for full-target
persistence checks. Optional membership_source {replay_family, collector} derives
collector-conditioned targets directly from retained replay membership files.
An explicit target_table path instead checks exported target sidecars. Optional
event_selections {table: {file, key}} declares frozen event-ID completeness.
Optional file_sha256 entries bind exported target sidecars to their provenance.
A missing manifest or an empty required category cannot produce sign-off.
Unlisted files are explicitly reported as outside the verification scope.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl
from verify_nongraph_release import verify_nongraph


HORIZONS = {"d30s": 30, "d1m": 60, "d5m": 300, "T5m": 300,
            "d15m": 900, "T15m": 900, "T60m": 3600, "final_2h": 7200}


def jac(a, b):
    a, b = set(a or []), set(b or [])
    return len(a & b) / len(a | b) if a | b else 0.0


def close(a, b, tolerance=0.000051):
    if a is None or b is None:
        return a is None and b is None
    return bool((np.isnan(a) and np.isnan(b)) or abs(a - b) <= tolerance)


def finite(values):
    values = np.asarray(values, dtype=float)
    return values[np.isfinite(values)]


def bootstrap_difference(values):
    values = finite(values)
    if not len(values):
        return {"mean": float("nan"), "ci95": [float("nan")] * 2, "n": 0}
    rng = np.random.default_rng(0)
    means = [values[rng.integers(0, len(values), len(values))].mean() for _ in range(2000)]
    return {"mean": values.mean(), "ci95": np.percentile(means, [2.5, 97.5]), "n": len(values)}


def verify_model_membership(row, seed, truth, predictions, check, relative):
    """Score exported full predictions against independently retrieved full truth."""
    details = {"file":relative,"event":row["event_id"]}
    for suffix,column in predictions.items():
        valid = column in row and isinstance(row[column], str)
        values = None
        if valid:
            try:
                values = json.loads(row[column])
                valid = isinstance(values,list) and all(type(v) is int for v in values)
            except (TypeError,ValueError):
                valid = False
        check(valid,"missing_model_membership_evidence",column=column,**details)
        if not valid:
            continue
        prediction = set(values)
        check(len(prediction)==len(values),"duplicate_model_predicted_asns",column=column,**details)
        check(seed<=prediction,"model_prediction_missing_seeds",column=column,**details)
        intersection = len(prediction & truth)
        metrics = {"jaccard":intersection/max(len(prediction|truth),1),
                   "precision":intersection/max(len(prediction),1),
                   "recall":intersection/max(len(truth),1),
                   "size_ratio":len(prediction)/max(len(truth),1)}
        check("jaccard_"+suffix in row,"missing_model_membership_metric",metric="jaccard_"+suffix,**details)
        for name,value in metrics.items():
            key = name+"_"+suffix
            if key in row:
                check(close(row[key],value,1e-8),"model_membership_metric_disagreement",metric=key,**details)
    if "new_pos" in row:
        check(row["new_pos"]==len(truth-seed),"model_new_target_size",**details)



def verify_model_probabilities(row, payload, seed, truth, threshold, check, relative):
    """Recompute candidate non-seed AP and thresholded sets from saved inference."""
    details = {"file":relative,"event":row["event_id"]}
    valid = isinstance(payload,(tuple,list)) and len(payload)==2
    check(valid,"invalid_model_probability_payload",**details)
    if not valid:
        return
    asns,probability = map(np.asarray,payload)
    valid = (asns.ndim==probability.ndim==1 and len(asns)==len(probability)
             and np.issubdtype(asns.dtype,np.integer) and np.issubdtype(probability.dtype,np.number))
    check(valid,"invalid_model_probability_arrays",**details)
    if not valid:
        return
    candidates=set(map(int,asns))
    check(len(candidates)==len(asns),"duplicate_probability_asns",**details)
    check(bool(np.isfinite(probability).all() and ((probability>=0)&(probability<=1)).all()),
          "invalid_model_probabilities",**details)
    check(row.get("n")==len(asns),"model_candidate_count",**details)
    for column,value in (("candidate_target_coverage",len(truth&candidates)/max(1,len(truth))),
                         ("true_outside_candidates",len(truth-candidates))):
        check(column in row and close(row[column],value,1e-8),"model_candidate_target_evidence",metric=column,**details)
    mask=np.asarray([int(asn) not in seed for asn in asns],dtype=bool)
    y=np.asarray([int(asn) in truth for asn in asns[mask]],dtype=np.int64)
    scores=probability[mask]
    positives=int(y.sum())
    ap=float("nan")
    if 0<positives<len(y):
        order=np.argsort(-scores,kind="stable")
        ordered_scores=scores[order]
        cumulative=np.cumsum(y[order])
        endpoints=np.r_[np.flatnonzero(ordered_scores[1:]!=ordered_scores[:-1]),len(y)-1]
        true_positives=cumulative[endpoints]
        increments=np.diff(np.r_[0,true_positives])
        ap=float(np.sum(increments*(true_positives/(endpoints+1)))/positives)
    check("auprc_new" in row and close(row["auprc_new"],ap,1e-8),"model_probability_ap",**details)
    check(isinstance(threshold,(int,float)) and 0<=threshold<=1,"missing_tuned_probability_threshold",**details)
    for column,cutoff in (("predicted_asns_at05",.5),("predicted_asns_tuned",threshold)):
        if cutoff is None:
            continue
        prediction=seed|set(map(int,asns[probability>=cutoff]))
        actual=json.loads(row[column]) if isinstance(row.get(column),str) else []
        check(set(actual)==prediction,"model_probability_prediction",column=column,**details)


def verify_model_counts(row, counts, n_seed, mode, check, relative, cutoff=None):
    """Recompute count errors from full source targets, independently of trainers."""
    details = {"file": relative, "event": row["event_id"]}
    if mode == "curve" or "curve_smape_model" in row:
        required = [f"curve_{name}_{i}" for i in range(4) for name in ("true", "pred", "lo", "hi")]
        required += [f"curve_evaluated_{i}" for i in range(4)] + ["observation_cutoff_s"]
        required += ["curve_true_2h", "curve_pred_2h", "curve_smape_model", "curve_smape_persist",
                     "curve_smape_2h_model", "curve_smape_2h_persist", "curve_cover80"]
        missing = sorted(set(required)-row.keys())
        check(not missing, "missing_model_count_evidence", missing=missing, **details)
        if missing:
            return
        if cutoff is None:
            raise ValueError("Curve verification requires a declared observation cutoff")
        evaluated = np.asarray([300,900,3600,7200]) > cutoff
        check(row["observation_cutoff_s"]==cutoff,"model_curve_observation_cutoff",**details)
        check(all(type(row[f"curve_evaluated_{i}"]) is bool and row[f"curve_evaluated_{i}"]==bool(evaluated[i])
                  for i in range(4)),"model_curve_horizon_mask",**details)
        truth = np.asarray(counts, dtype=float)
        lo, pred, hi = (np.asarray([row[f"curve_{name}_{i}"] for i in range(4)], dtype=float)
                        for name in ("lo", "pred", "hi"))
        check(all(row[f"curve_true_{i}"] == counts[i] for i in range(4))
              and row["curve_true_2h"] == counts[-1], "model_curve_target_count", **details)
        check(np.isfinite([lo, pred, hi]).all(), "model_curve_nonfinite", **details)
        tolerance = 1e-6 * np.maximum(1., np.maximum(np.abs(lo), np.abs(hi)))
        check(np.all(lo + tolerance >= n_seed), "model_curve_seed_floor", **details)
        check(np.all(lo <= pred + tolerance) and np.all(pred <= hi + tolerance),
              "model_curve_quantile_order", **details)
        check(np.isclose(row["curve_pred_2h"], pred[-1], rtol=1e-6, atol=1e-6),
              "model_curve_alias_disagreement", **details)
        smape = lambda a,b: float(np.mean(2*np.abs(a-b)/np.maximum(np.abs(a)+np.abs(b),1e-9)))
        persistence = np.full(4, float(n_seed))
        derived = {"curve_smape_model":smape(pred[evaluated],truth[evaluated]), "curve_smape_persist":smape(persistence[evaluated],truth[evaluated]),
                   "curve_smape_2h_model":smape(pred[-1:],truth[-1:]),
                   "curve_smape_2h_persist":smape(persistence[-1:],truth[-1:]),
                   "curve_cover80":float(np.mean(((truth>=lo)&(truth<=hi))[evaluated]))}
        for key,value in derived.items():
            check(np.isclose(row[key], value, rtol=1e-6, atol=1e-6),
                  "model_curve_metric_disagreement", metric=key, **details)
    if mode == "final" or "pred_final" in row:
        required = {"pred_final", "true_final", "smape_2h_hist", "smape_2h_persist"}
        missing = sorted(required-row.keys())
        check(not missing, "missing_model_count_evidence", missing=missing, **details)
        if missing:
            return
        prediction = row["pred_final"]
        truth = counts[-1]
        check(np.isfinite(prediction) and prediction + 1e-6*max(1,n_seed)>=n_seed,
              "model_final_seed_floor", **details)
        for key,pred in (("smape_2h_hist",prediction),("smape_2h_persist",n_seed)):
            value = 2*abs(pred-truth)/max(abs(pred)+abs(truth),1e-9)
            check(np.isclose(row[key],value,rtol=1e-6,atol=1e-6),
                  "model_final_metric_disagreement",metric=key,**details)


def verify(data: Path, expected: dict | None = None, model_data: Path | None = None) -> dict:
    problems, tables, models, pairs, frontiers, beacon_delays = [], [], [], [], [], []
    checked_files = set()

    def check(condition, kind, **details):
        if not condition:
            problems.append({"kind": kind, **details})

    def require(relative):
        root = model_data if model_data is not None and str(relative).startswith("tgn/") else data
        path = root / relative
        check(path.is_file(), "missing_required_file", file=str(relative))
        if path.is_file():
            checked_files.add(str(relative))
        return path if path.is_file() else None

    inventory = {"event_tables": sorted(str(p.relative_to(data)) for p in (data / "eventset").glob("*/events.parquet")),
                 "pair_tables": sorted(str(p.relative_to(data)) for p in (data / "eventset").glob("*_recovery_first_transition/pairs*.parquet")),
                 "model_tables": sorted(str(p.relative_to(model_data or data)) for p in ((model_data or data) / "tgn").glob("*/*/_results/*_test_per_event.csv"))}
    if expected is None:
        check(False, "missing_expected_manifest", detail="Inventory discovery alone cannot certify completeness")
        expected = {"event_tables": [Path(p).parent.name for p in inventory["event_tables"]],
                    "pair_tables": inventory["pair_tables"], "model_tables": inventory["model_tables"]}
    for category in ("event_tables", "pair_tables", "model_tables"):
        check(bool(expected.get(category)), "empty_required_manifest_category", category=category)
    for relative in expected.get("required_files", []):
        require(relative)
    for relative, digest in expected.get("file_sha256", {}).items():
        path = require(relative)
        if path:
            check(hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                  "file_hash_disagreement", file=relative)

    withdrawal_baseline = None
    permitted_empty_tables = set()
    if expected.get("withdrawal_baseline"):
        contract=expected["withdrawal_baseline"]
        paths={key:require(contract[key]) for key in ("revision","availability","verification")}
        if all(path is not None for path in paths.values()):
            try:
                from verify_withdrawal_baselines import verify as verify_withdrawal
                withdrawal_baseline=verify_withdrawal(data,paths["revision"],paths["availability"],paths["verification"])
                check(withdrawal_baseline["status"]=="passed" and not withdrawal_baseline["failures"],
                      "withdrawal_baseline_verification_failed",details=withdrawal_baseline["failures"])
                for relative in withdrawal_baseline["source_sha256"]:require(relative)
                if withdrawal_baseline["status"]=="passed" and not withdrawal_baseline["failures"]:
                    revision=json.loads(paths["revision"].read_text())
                    permitted_empty_tables={Path(t["path"]).parent.name for t in revision["tables"] if t["usable_after"]==0}
            except Exception as error:
                check(False,"withdrawal_baseline_verification_failed",error=type(error).__name__,detail=str(error))

    event_cache, membership_cache = {}, {}
    def events(name):
        if name not in event_cache:
            path = require(f"eventset/{name}/events.parquet")
            if path is None:
                return None
            event_cache[name] = pl.read_parquet(path)
        return event_cache[name]

    for name in expected.get("event_tables", []):
        table = events(name)
        if table is None:
            continue
        check(table["event_id"].n_unique() == table.height, "duplicate_event_ids", table=name)
        selection = expected.get("event_selections", {}).get(name)
        if selection:
            selected_path = require(selection["file"])
            if selected_path:
                if selected_path.suffix == ".parquet":
                    selected = pl.read_parquet(selected_path)
                else:
                    selected = pl.read_csv(selected_path, separator="\t" if selected_path.suffix==".tsv" else ",")
                selected_ids = set(selected[selection.get("key", "event_id")])
                observed_ids = set(table["event_id"])
                check(observed_ids == selected_ids, "event_population_completeness", table=name,
                      missing=len(selected_ids-observed_ids), unexpected=len(observed_ids-selected_ids),
                      examples_missing=sorted(selected_ids-observed_ids)[:5])
        ok = table.filter(pl.col("error").is_null())
        check(ok.height > 0 or name in permitted_empty_tables, "no_usable_events", table=name)
        for column in table.columns:
            if column.startswith("asns_") and "set_" + column[5:] in table.columns:
                bad = ok.filter(pl.col(column).ne_missing(pl.col("set_" + column[5:]).list.len())).height
                check(bad == 0, "extent_count_disagreement", table=name, column=column, rows=bad)
        for horizon in HORIZONS:
            col = "set_" + horizon
            if col in ok.columns:
                check(ok[col].null_count() == 0, "null_membership_set", table=name, horizon=horizon)
                bad = ok.filter(pl.col(col).list.len() != pl.col(col).list.n_unique()).height
                check(bad == 0, "duplicate_asn_within_set", table=name, horizon=horizon, rows=bad)
        for first, first_s in HORIZONS.items():
            for last, last_s in HORIZONS.items():
                if first != last and first_s <= last_s and all("set_" + x in ok.columns for x in (first, last)):
                    bad = ok.filter(pl.col("set_" + first).list.set_difference(pl.col("set_" + last)).list.len() > 0).height
                    check(bad == 0, "inconsistent_horizon_sets", table=name, first=first, last=last, rows=bad)
        for split in ("train", "test"):
            if not ok.filter(pl.col("split") == split).height:
                continue
            scores = require(f"eventset/{name}/persistence_{split}.csv")
            if scores is None:
                continue
            if scores.stat().st_size < 5:
                check(False, "empty_persistence_table", table=name, split=split)
                continue
            for row in pl.read_csv(scores).iter_rows(named=True):
                sub = ok.filter(pl.col("split") == split).drop_nulls(["set_" + row["delta"], "set_" + row["target"]])
                values = [jac(a, b) for a, b in sub.select("set_" + row["delta"], "set_" + row["target"]).iter_rows()]
                score = np.mean(values) if values else None
                check(sub.height == row["events"] and close(score, row["jaccard_mean"]),
                      "persistence_aggregation", table=name, split=split, delta=row["delta"], target=row["target"])
        if "first_transition" in name:
            check("measurement_definition" in ok.columns and ok["measurement_definition"].null_count() == 0,
                  "missing_transition_definition", table=name)
            check(ok.filter(pl.col("observation_lag_s") < 0).is_empty(), "pre_identifier_transition", table=name)
            check(ok.filter(pl.col("set_final_2h").list.len() == 0).is_empty(), "empty_transition_footprint", table=name)
            check(ok["t90_s"].null_count() == 0 and ok.filter((pl.col("t90_s") < 0) | (pl.col("t90_s") > 7200)).is_empty(),
                  "invalid_transition_t90", table=name)
        path = data / "eventset" / name / "events.parquet"
        tables.append({"table": name, "rows": table.height, "usable": ok.height,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    for relative in expected.get("pair_tables", []):
        path = require(relative)
        if path is None:
            continue
        frame = pl.read_parquet(path)
        check(frame.height > 0, "empty_pair_table", file=relative)
        check(frame.unique(["event_id", "hijack_id"]).height == frame.height, "multiplied_pair_links", file=relative)
        year = path.parent.name[:4]
        ht = events(f"{year}_hijack_first_transition")
        rt = events(path.parent.name)
        if ht is None or rt is None:
            continue
        for source, table in (("hijack", ht), ("recovery", rt)):
            check(table["event_id"].n_unique() == table.height, "duplicate_pair_source", file=relative, source=source)
        h = {row["event_id"]: row for row in ht.filter(pl.col("error").is_null()).iter_rows(named=True)}
        r = {row["event_id"]: row for row in rt.filter(pl.col("error").is_null()).iter_rows(named=True)}
        source_bad, chronology_bad, metric_bad, links = [], [], [], set()
        for row in frame.iter_rows(named=True):
            hid, rid = row["hijack_id"], row["event_id"]
            links.add((rid, hid))
            if hid not in h or rid not in r or not h[hid].get("t0_obs") or not r[rid].get("t0_obs"):
                source_bad.append((rid, hid)); continue
            if dt.datetime.fromisoformat(r[rid]["t0_obs"]) < dt.datetime.fromisoformat(h[hid]["t0_obs"]):
                chronology_bad.append((rid, hid))
            check(h[hid].get("measurement_definition") == r[rid].get("measurement_definition") is not None,
                  "unmatched_pair_measurement_definition", file=relative, hijack=hid, recovery=rid)
            for prefix, source in (("h", h[hid]), ("r", r[rid])):
                expected_metrics = {"reach": len(set(source["set_final_2h"])), "j30": jac(source["set_d30s"], source["set_final_2h"]),
                                    "t90_s": source["t90_s"]}
                for key, value in expected_metrics.items():
                    if not close(row.get(prefix + "_" + key), value, 1e-8):
                        metric_bad.append({"event": source["event_id"], "metric": prefix + "_" + key})
        check(not source_bad, "unusable_or_missing_pair_source", file=relative, rows=len(source_bad), examples=source_bad[:5])
        check(not chronology_bad, "return_before_hijack", file=relative, rows=len(chronology_bad), examples=chronology_bad[:5])
        check(not metric_bad, "pair_source_metric_disagreement", file=relative, rows=len(metric_bad), examples=metric_bad[:5])
        summary_path = require(str(path.with_name(path.stem.replace("pairs", "pairs_summary", 1) + ".json").relative_to(data)))
        if summary_path is None:
            continue
        saved = json.loads(summary_path.read_text())
        check(saved["pairs"] == frame.height, "pair_count", file=relative)
        for prefix, section in (("h", "hijack"), ("r", "recovery")):
            metrics = {"j30_mean": np.mean(frame[prefix + "_j30"].to_numpy()),
                       "reach_p50": np.median(frame[prefix + "_reach"].to_numpy()),
                       "t90_s_p50": np.median(finite(frame[prefix + "_t90_s"].to_numpy())),
                       "t90_gt_5min_frac": np.mean(finite(frame[prefix + "_t90_s"].to_numpy()) > 300)}
            for key, value in metrics.items():
                check(close(saved[section].get(key), value), "pair_summary_metric", file=relative, metric=section + "." + key)
        if frame.height:
            values = (frame["r_j30"] - frame["h_j30"]).to_numpy()
            check(close(saved["paired_j30_diff_recovery_minus_hijack"]["mean"], values.mean()), "pair_difference", file=relative)
            # Independent graph traversal verifies the stored cluster partition.
            adjacency = {}
            for rid, hid in links:
                adjacency.setdefault(rid, set()).add(hid); adjacency.setdefault(hid, set()).add(rid)
            components, component = {}, 0
            for node in sorted(adjacency):
                if node in components: continue
                stack = [node]
                while stack:
                    n = stack.pop()
                    if n in components: continue
                    components[n] = component; stack.extend(adjacency[n] - components.keys())
                component += 1
            if "bootstrap_component" not in frame.columns:
                check(False, "missing_pair_bootstrap_clusters", file=relative)
            else:
                groups = frame["bootstrap_component"].to_list()
                label_to_component, component_to_label = {}, {}
                valid_partition = True
                for rid, label in zip(frame["event_id"], groups):
                    c = components[rid]
                    valid_partition &= label_to_component.setdefault(label, c) == c
                    valid_partition &= component_to_label.setdefault(c, label) == label
                check(valid_partition, "incorrect_pair_bootstrap_partition", file=relative)
                labels = sorted(set(groups))
                interval = None
                if len(labels) >= 20:
                    aggregation = {label: [0.0, 0] for label in labels}
                    for label, value in zip(groups, values):
                        aggregation[label][0] += value
                        aggregation[label][1] += 1
                    totals = np.array([aggregation[label][0] for label in labels])
                    sizes = np.array([aggregation[label][1] for label in labels])
                    rng = np.random.default_rng(0)
                    draws = []
                    for _ in range(1000):
                        sample = rng.integers(0, len(labels), len(labels))
                        draws.append(totals[sample].sum() / sizes[sample].sum())
                    interval = np.percentile(draws, [2.5, 97.5])
                stored = saved["paired_j30_diff_recovery_minus_hijack"].get("ci95")
                check((stored is None and interval is None) or (stored is not None and interval is not None and all(close(a, b) for a, b in zip(stored, interval))),
                      "pair_cluster_bootstrap_ci", file=relative)
                check(saved.get("bootstrap_components") == component, "pair_cluster_count", file=relative)
        # A pair table cannot silently omit surviving selected links.
        selection_path = require(f"inventory/{year}/recovery_replay_selection.parquet")
        if selection_path:
            selected = pl.read_parquet(selection_path).select("event_id", "hijack_id").unique()
            origin = events(year)
            reason = dict(origin.select("event_id", "reason").iter_rows()) if origin is not None else {}
            valid_ids = None
            if saved.get("pair_population", {}).get("require_valid_hijack"):
                vp = require(f"eventset/{year}/rpki_validity.parquet")
                if vp:
                    valid_ids = set(pl.read_parquet(vp).filter((pl.col("validity") == "invalid") & (pl.col("prev_validity") == "valid"))["event_id"])
            expected_links, excluded_links = set(), set()
            for rid, hid in selected.iter_rows():
                if hid not in h or rid not in r: continue
                if saved.get("only_reason") and reason.get(hid) != saved["only_reason"]: continue
                if saved.get("exclude_reason") and reason.get(hid) == saved["exclude_reason"]: continue
                if valid_ids is not None and hid not in valid_ids: continue
                if dt.datetime.fromisoformat(r[rid]["t0_obs"]) < dt.datetime.fromisoformat(h[hid]["t0_obs"]):
                    excluded_links.add((rid, hid)); continue
                expected_links.add((rid, hid))
            reported_exclusions = {(x["event_id"], x["hijack_id"]) for x in saved.get("chronologically_unmatched_links", [])}
            check(reported_exclusions == excluded_links and saved.get("chronologically_unmatched_count") == len(excluded_links),
                  "chronology_exclusion_accounting", file=relative, expected=len(excluded_links), reported=len(reported_exclusions))
            check(links == expected_links, "pair_selection_completeness", file=relative,
                  missing=len(expected_links-links), unexpected=len(links-expected_links))
        pairs.append({"file": relative, "links": frame.height, "source_checks": frame.height * 6})

    for relative in expected.get("frontier_tables", []):
        summary_path = require(relative)
        if summary_path is None: continue
        path = require(str(Path(relative).with_suffix(".parquet")))
        if path is None: continue
        saved = json.loads(summary_path.read_text())
        frame = pl.read_parquet(path)
        check(frame.height > 0 and frame["event_id"].n_unique() == frame.height, "frontier_unique_events", file=relative)
        origin = events(str(saved["year"]))
        if origin is not None:
            selected = origin.filter(pl.col("error").is_null() & (pl.col("set_final_2h").list.len() > 0))
            if saved.get("only_reason"): selected = selected.filter(pl.col("reason") == saved["only_reason"])
            if saved.get("exclude_reason"): selected = selected.filter(pl.col("reason") != saved["exclude_reason"])
            check(set(frame["event_id"]) == set(selected["event_id"]), "frontier_population_completeness", file=relative)
            counts = dict(selected.select("event_id", pl.col("set_final_2h").list.len()).iter_rows())
            check(all(counts.get(eid) == n for eid, n in frame.select("event_id", "carriers").iter_rows()),
                  "frontier_carrier_source_count", file=relative)
        validity_path = require(f"eventset/{saved['year']}/rpki_validity.parquet")
        if validity_path:
            labels = dict(pl.read_parquet(validity_path).select("event_id", "validity").iter_rows())
            check(all(labels.get(eid) == validity for eid, validity in frame.select("event_id", "validity").iter_rows()),
                  "frontier_source_validity", file=relative)
        rng = np.random.default_rng(0)
        for validity, record in saved["by_validity"].items():
            subset = frame.filter(pl.col("validity") == validity)
            check(subset.height == record["events"], "frontier_event_count", file=relative, validity=validity)
            for side in ("carriers", "frontier"):
                total, measured, enforcing = [subset[c].sum() for c in (side, side+"_measured", side+"_enforcing")]
                bad = subset.filter((pl.col(side+"_enforcing") > pl.col(side+"_measured")) | (pl.col(side+"_measured") > pl.col(side))).height
                check(bad == 0, "frontier_measurement_counts", file=relative, side=side)
                check(close(record[side+"_measured_share"], measured/max(total,1), .00051), "frontier_coverage", file=relative, side=side)
                check(close(record["enforcing_share_"+side], enforcing/measured if measured else None), "frontier_enforcing_share", file=relative, side=side)
            values = []
            for row in subset.iter_rows(named=True):
                value = None
                if row["carriers_measured"] and row["frontier_measured"]:
                    pc = (row["carriers_enforcing"]+.5)/(row["carriers_measured"]+1)
                    pf = (row["frontier_enforcing"]+.5)/(row["frontier_measured"]+1)
                    value = np.log((pf/(1-pf))/(pc/(1-pc)))
                    values.append(value)
                check(close(row["log_odds"], value, 1e-8), "frontier_event_odds", file=relative, event=row["event_id"])
            check(record["events_with_both_measured"] == len(values), "frontier_measured_event_count", file=relative)
            check(close(record["log_odds_frontier_vs_carriers_mean"], np.mean(values) if values else None, .00051), "frontier_mean_odds", file=relative)
            interval = np.percentile([np.mean(rng.choice(values, size=len(values))) for _ in range(1000)], [2.5,97.5]) if len(values)>20 else None
            old = record["log_odds_mean_ci95_bootstrap"]
            check((old is None and interval is None) or (old is not None and interval is not None and len(old)==2 and all(close(a,b,.00051) for a,b in zip(old, interval))),
                  "frontier_bootstrap_interval", file=relative, validity=validity)
        frontiers.append({"file": relative, "events": frame.height, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    for relative in expected.get("beacon_delay_tables", []):
        summary_path = require(relative)
        cycle_path = require(str(Path(relative).with_name("cycles.parquet")))
        if summary_path is None or cycle_path is None:
            continue
        saved = json.loads(summary_path.read_text())
        cycles = pl.read_parquet(cycle_path)
        check(cycles.unique(["prefix","slot_ts","collector","peer_ip","peer_asn","origin_known"]).height==cycles.height,
              "duplicate_beacon_cycles",file=relative)
        for name, first, origin in (("a_delay_s","first_a_ts","orig_ts"),("w_delay_s","first_w_ts","sched_wd_ts")):
            derived=(pl.col(first)-pl.col(origin)).dt.total_microseconds()/1e6
            check(cycles.filter(pl.col(name).ne_missing(derived)).is_empty(),"beacon_delay_timestamp_disagreement",file=relative,column=name)
        origin_slot=pl.when(pl.col("kind")=="fast").then(pl.col("orig_ts").dt.truncate("20m")).otherwise(pl.col("orig_ts").dt.truncate("4h"))
        check(cycles.filter(pl.col("orig_ts").is_not_null() & (origin_slot!=pl.col("slot_ts"))).is_empty(),
              "beacon_origin_slot_disagreement",file=relative)
        eligible=cycles.filter(pl.col("a_delay_s").is_between(0,3600)&~pl.col("first_a_origin_ambiguous"))
        counts={"cycles":cycles.height,"eligible_cycles":eligible.height,"excluded_cycles":cycles.height-eligible.height,
                "excluded_late_announcement":cycles.filter(pl.col("a_delay_s")>3600).height,
                "excluded_negative_delay":cycles.filter(pl.col("a_delay_s")<0).height,
                "excluded_missing_origin":cycles["a_delay_s"].null_count(),
                "ambiguous_first_origin_cycles":cycles.filter(pl.col("first_a_origin_ambiguous")).height,
                "first_arrival_in_different_cycle":cycles.filter(pl.col("first_a_arrival_slot_ts")!=pl.col("slot_ts")).height}
        for key,value in counts.items():
            check(saved.get(key)==value,"beacon_delay_population",file=relative,metric=key)
        for name,column in (("announcement","a_delay_s"),("withdrawal","w_delay_s")):
            values=eligible[column].drop_nulls()
            check(saved["statistics"][name]["n"]==len(values),"beacon_delay_sample_count",file=relative,metric=name)
            # Nearest quantiles reproduce Polars' explicit stored convention.
            ordered=np.sort(values.to_numpy())
            for q in (.5,.9,.99):
                value=float(ordered[int(np.floor((len(ordered)-1)*q+.5))])
                check(close(saved["statistics"][name][f"p{int(q*100)}_s"],value,1e-8),"beacon_delay_quantile",file=relative,metric=f"{name}.p{int(q*100)}")
        per_vp_path = require(str(Path(relative).with_name("per_vp_summary.parquet")))
        if per_vp_path is not None:
            saved_vp = pl.read_parquet(per_vp_path)
            keys = ["collector", "kind", "setup"]
            groups = {tuple(row[key] for key in keys):row for row in saved_vp.iter_rows(named=True)}
            check(len(groups)==saved_vp.height,"duplicate_beacon_summary_groups",file=relative)
            expected_groups = set()
            for key, group in eligible.group_by(keys):
                expected_groups.add(key)
                row = groups.get(key)
                check(row is not None,"missing_beacon_summary_group",file=relative,group=list(key))
                if row is None:
                    continue
                values = {"n_cycles":group["slot_ts"].n_unique(),"n_peers":group["peer_ip"].n_unique(),
                          "frac_cycles_with_w":group["first_w_ts"].is_not_null().mean()}
                for prefix,column in (("a_delay","a_delay_s"),("w_delay","w_delay_s")):
                    ordered = np.sort(group[column].drop_nulls().to_numpy())
                    for q in (.5,.9):
                        values[f"{prefix}_p{int(q*100)}"] = float(ordered[int(np.floor((len(ordered)-1)*q+.5))]) if len(ordered) else None
                    if prefix=="a_delay":
                        values["a_delay_max"]=float(ordered[-1]) if len(ordered) else None
                for metric,value in values.items():
                    check(close(row[metric],value,1e-8),"beacon_per_vp_aggregation",file=relative,group=list(key),metric=metric)
            check(set(groups)==expected_groups,"beacon_per_vp_population",file=relative)
        beacon_delays.append({"file":relative,"cycles":cycles.height,"eligible":eligible.height})

    ci_columns = {"diff_tuned_minus_persistence": ("jaccard_model_tuned", "jaccard_persist"),
                  "diff_at05_minus_persistence": ("jaccard_model", "jaccard_persist"),
                  "diff_hist_minus_persistence": ("jaccard_hist", "jaccard_persist"),
                  "diff_curve_smape_model_minus_persist": ("curve_smape_model", "curve_smape_persist")}
    for relative in expected.get("model_tables", []):
        path = require(relative)
        if path is None: continue
        summary_path = require(str(Path(relative).with_name(path.name.replace("_test_per_event.csv", "_summary.json"))))
        if summary_path is None: continue
        outer = json.loads(summary_path.read_text()); saved = outer.get("final_test", outer)
        frame = pl.read_csv(path)
        check(frame.height > 0, "empty_model_table", file=relative)
        check(frame["event_id"].n_unique() == frame.height, "duplicate_model_events", file=relative)
        cohort = expected.get("model_cohorts", {}).get(relative)
        if cohort:
            cohort_ids = set()
            for index_file in cohort["index_tables"]:
                index_path = require(index_file)
                if index_path is None:
                    continue
                index = pl.read_csv(index_path)
                if cohort["split"] != "all":
                    index = index.filter(pl.col("split") == cohort["split"])
                cohort_ids.update(index["event_id"])
            actual_ids = set(frame["event_id"])
            check(actual_ids == cohort_ids, "model_population_completeness", file=relative,
                  missing=len(cohort_ids-actual_ids), unexpected=len(actual_ids-cohort_ids))
        n = saved.get("events", outer.get("test_events"))
        check(n == frame.height, "model_event_count", file=relative, declared=n, rows=frame.height)
        count, intervals = 0, 0
        for column, dtype in frame.schema.items():
            if not dtype.is_numeric(): continue
            key = next((key for key in (column + "_mean", column) if isinstance(saved.get(key), (int, float))), None)
            if key is not None:
                values = frame[column].drop_nulls().cast(pl.Float64).drop_nans()
                value = values.mean() if len(values) else float("nan")
                check(close(value, saved[key]), "model_aggregation", file=relative, metric=key)
                count += 1
        check(count > 0, "no_model_aggregate_checks", file=relative)
        for key,column in (("model_beats_persistence_frac","jaccard_model"),
                           ("tuned_beats_persistence_frac","jaccard_model_tuned")):
            if key in saved:
                value = (frame[column]>frame["jaccard_persist"]).mean()
                check(close(saved[key],value),"model_derived_aggregation",file=relative,metric=key)
        if "size_ratio_tuned_p50" in saved:
            check(close(saved["size_ratio_tuned_p50"],frame["size_ratio_tuned"].median()),
                  "model_derived_aggregation",file=relative,metric="size_ratio_tuned_p50")
        for key, (a, b) in ci_columns.items():
            if key not in saved: continue
            result = bootstrap_difference((frame[a] - frame[b]).to_numpy()); old = saved[key]
            check(old.get("n") == result["n"] and close(old.get("mean"), result["mean"])
                  and all(close(x, y) for x, y in zip(old.get("ci95", []), result["ci95"])) and len(old.get("ci95", [])) == 2,
                  "model_bootstrap_interval", file=relative, metric=key)
            intervals += 1
        target = expected.get("model_targets", {}).get(relative)
        check(bool(target), "missing_model_target_contract", file=relative)
        probability_hash = None
        if target:
            probability_evidence = None
            if target.get("probability_evidence"):
                probability_path = require(target["probability_evidence"])
                if probability_path is not None:
                    import torch
                    probability_evidence = torch.load(probability_path,map_location="cpu",weights_only=False)
                    check(isinstance(probability_evidence,dict),"invalid_probability_evidence",file=relative)
                    check(set(probability_evidence)==set(frame["event_id"]),"model_probability_population",file=relative)
                    probability_hash = hashlib.sha256(probability_path.read_bytes()).hexdigest()
            truth = {}
            requested_events = frame["event_id"].to_list()
            if target.get("target_table"):
                check(not target.get("membership_source"), "ambiguous_model_target_contract", file=relative)
                source_path = require(target["target_table"])
                source_tables = [pl.read_parquet(source_path)] if source_path else []
            else:
                names = target.get("event_tables") or [target["event_table"]]
                source_tables = [events(name) for name in names]
            for table in source_tables:
                if table is None: continue
                for source in table.filter(pl.col("error").is_null() & pl.col("event_id").is_in(requested_events)).iter_rows(named=True):
                    check(source["event_id"] not in truth, "duplicate_model_target_event", file=relative, event=source["event_id"])
                    truth[source["event_id"]] = source
            for row in frame.iter_rows(named=True):
                source = truth.get(row["event_id"])
                check(source is not None, "missing_model_target_event", file=relative, event=row["event_id"])
                if source is None: continue
                if target.get("membership_source"):
                    spec = target["membership_source"]
                    family, collector = spec["replay_family"], spec["collector"]
                    key = (family, collector, row["event_id"])
                    if key not in membership_cache:
                        root = {"origin": "events_replay", "leak": "events_replay_leak", "withdrawal": "events_replay_withdrawal"}[family]
                        member_path = require(f"{root}/{row['event_id']}/membership.parquet")
                        if member_path is None: continue
                        members = pl.read_parquet(member_path).filter(pl.col("collector") == collector)
                        onset = dt.datetime.fromisoformat(source["t0_obs"])
                        membership_cache[key] = {
                            horizon: set(members.filter(pl.col("first_seen") <= pl.lit(onset+dt.timedelta(seconds=seconds)))["asn"])
                            for horizon,seconds in HORIZONS.items()}
                    source_sets = membership_cache[key]
                    seed, final = source_sets[target["horizon"]], source_sets["final_2h"]
                else:
                    source_sets = {key[4:]:set(value) for key,value in source.items() if key.startswith("set_") and value is not None}
                    seed, final = source_sets[target["horizon"]], source_sets["final_2h"]
                check(bool(final),"model_empty_full_target",file=relative,event=row["event_id"])
                check(seed<=final,"model_source_seed_outside_final",file=relative,event=row["event_id"])
                for column in ("true_size", "true_final", "pos"):
                    if column in row:
                        check(row[column] == len(final), "model_full_target_size", file=relative, event=row["event_id"], column=column)
                if "n_seed" in row:
                    check(row["n_seed"] == len(seed), "model_full_seed_size", file=relative, event=row["event_id"])
                check(close(row["jaccard_persist"], jac(seed, final), 1e-8),
                      "model_full_target_persistence", file=relative, event=row["event_id"])
                verify_model_membership(row,seed,final,target.get("membership_predictions",{}),check,relative)
                if probability_evidence is not None:
                    verify_model_probabilities(row,probability_evidence.get(row["event_id"]),seed,final,
                                               outer.get("threshold_tuned_on_train"),check,relative)
                mode = target.get("count_forecast")
                if mode == "curve" or "curve_smape_model" in row:
                    horizons = ("T5m", "T15m", "T60m", "final_2h")
                    missing = [h for h in horizons if h not in source_sets]
                    check(not missing, "missing_model_curve_source", file=relative, event=row["event_id"], missing=missing)
                    if not missing:
                        verify_model_counts(row, [len(source_sets[h]) for h in horizons], len(seed), mode, check, relative, cutoff=HORIZONS[target["horizon"]])
                elif mode == "final" or "pred_final" in row:
                    verify_model_counts(row, [len(final)], len(seed), mode, check, relative)
        models.append({"file": relative, "rows": frame.height, "aggregate_checks": count, "interval_checks": intervals,
                       "full_target_checked": bool(target), "probability_evidence": target.get("probability_evidence") if target else None,
                       "probability_sha256": probability_hash, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    nongraph = verify_nongraph(expected, require, events, check, close, data_root=data)
    frontier_source_audit = None
    if expected.get("frontier_source_verification"):
        proof = require(expected["frontier_source_verification"])
        if proof is not None:
            try:
                from verify_frontier_sources import verify_public
                frontier_source_audit = verify_public(data, proof, expected.get("frontier_tables", []))
            except Exception as error:
                frontier_source_audit = {"status": "failed", "error": str(error)}
                check(False, "frontier_source_verification_failed", error=type(error).__name__, detail=str(error))
    propagation_controls = None
    if expected.get("propagation_controls_verification"):
        proof = require(expected["propagation_controls_verification"])
        if proof is not None:
            try:
                from verify_propagation_controls import verify_public
                propagation_controls = verify_public(data, proof)
            except Exception as error:
                propagation_controls = {"status": "failed", "error": str(error)}
                check(False, "propagation_controls_verification_failed", error=type(error).__name__, detail=str(error))
    radar_agreement = None
    if expected.get("radar_agreement_verification"):
        proof = require(expected["radar_agreement_verification"])
        if proof is not None:
            try:
                from verify_radar_agreement import verify_public
                radar_agreement = verify_public(data, proof)
            except Exception as error:
                radar_agreement = {"status": "failed", "error": str(error)}
                check(False, "radar_agreement_verification_failed", error=type(error).__name__, detail=str(error))
    auxiliary = None
    if expected.get("auxiliary_verification"):
        contract = require(expected["auxiliary_verification"])
        if contract is not None:
            try:
                from verify_graph_auxiliary import verify_auxiliary
                auxiliary = verify_auxiliary(data,contract,public=True)
                check(auxiliary.get("status")=="passed","auxiliary_verification_failed",detail=auxiliary)
            except Exception as error:
                auxiliary = {"status":"failed","error":str(error)}
                check(False,"auxiliary_verification_failed",error=type(error).__name__,detail=str(error))
    outside = {key: [p for p in paths if p not in checked_files] for key, paths in inventory.items()}
    return {"event_tables": tables, "pair_tables": pairs, "model_tables": models, "failures": problems,
            "frontier_tables": frontiers, "beacon_delay_tables": beacon_delays, "nongraph_tables": nongraph,
            "auxiliary_verification": auxiliary, "frontier_source_verification": frontier_source_audit,
            "propagation_controls_verification": propagation_controls, "radar_agreement_verification": radar_agreement, "withdrawal_baseline_verification": withdrawal_baseline,
            "unverified_inventory": outside, "scope": "Declared snapshot arithmetic and target invariants; not a fresh model-inference proof"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    parser.add_argument("--manifest", type=Path, help="explicit expected paper-result files; required for sign-off")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-data", type=Path, help="explicit separate root for final tgn models and cohort indices")
    args = parser.parse_args()
    result = verify(args.data, json.loads(args.manifest.read_text()) if args.manifest else None, args.model_data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"tables": len(result["event_tables"]), "pairs": len(result["pair_tables"]),
                      "models": len(result["model_tables"]), "nongraph": len(result["nongraph_tables"]), "failures": len(result["failures"])}))
    raise SystemExit(bool(result["failures"]))
