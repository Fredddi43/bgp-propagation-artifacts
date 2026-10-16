"""Independent arithmetic checks for declared cascade, curve and prefix outputs.

This module deliberately imports no experiment scoring code. Curve targets come
from the released event sets; prefix truth comes from the raw-derived floor
table. Stored predictions permit recomputation without rerunning trained models.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import numpy as np
import polars as pl


def smape(a, b):
    return 2 * abs(a-b) / max(abs(a)+abs(b), 1e-9)


def jaccard(a, b):
    return len(a & b) / len(a | b) if a | b else 0.0


def average_precision(labels, scores):
    """Integrate precision over recall changes at distinct score thresholds."""
    labels, scores = np.asarray(labels, dtype=bool), np.asarray(scores, dtype=float)
    if not labels.sum():
        return float("nan")
    order = np.argsort(-scores, kind="stable")
    labels, scores = labels[order], scores[order]
    end = np.r_[np.flatnonzero(scores[1:] != scores[:-1]), len(scores)-1]
    true_positives = np.cumsum(labels)[end]
    increments = np.diff(np.r_[0, true_positives])
    return float(np.sum(increments * true_positives / (end+1)) / labels.sum())


def verify_curve_eligibility(spec, saved, source, require, check, raw_sources=False):
    """Bind exact minute-zero growth eligibility to a separate raw-source audit."""
    relative=spec.get("eligibility")
    check(bool(relative),"missing_curve_eligibility_contract",file=spec["summary"])
    if not relative:
        return set()
    path=require(relative)
    if path is None:
        return set()
    if raw_sources:
        path.with_suffix(".verification.json").unlink(missing_ok=True)
    table=pl.read_parquet(path)
    records=table.sort("event_id").to_dicts()
    content_hash=hashlib.sha256(json.dumps(records,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    problems=[]
    def checked(condition,kind,**details):
        check(condition,kind,file=relative,**details)
        if not condition:
            problems.append(kind)
    base=source.filter(pl.col("error").is_null() & (pl.col("asns_final_2h")>=saved["min_asns"]))
    if "leak" in spec["event_table"]:
        base=base.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s")>=-60))
    wanted={r["event_id"]:r for r in base.iter_rows(named=True)}
    checked(table["event_id"].n_unique()==table.height,"duplicate_curve_eligibility")
    checked(set(table["event_id"])==set(wanted),"curve_eligibility_base_population")
    for row in records:
        event=wanted.get(row["event_id"])
        if event is None:
            continue
        checked(row["split"]==event["split"] and row["t0_obs"]==event["t0_obs"],"curve_eligibility_source_metadata",event=row["event_id"])
        checked(row["final_count"]==len(set(event["set_final_2h"])),"curve_eligibility_final_count",event=row["event_id"])
        checked(0<=row["observed_zero_count"]<=row["final_count"],"curve_eligibility_invalid_count",event=row["event_id"])
        checked(row["eligible_growth"]==(row["final_count"]>row["observed_zero_count"]),"curve_eligibility_growth",event=row["event_id"])
        if raw_sources:
            member=require(f"events_replay_leak/{row['event_id']}/membership.parquet")
            if member is None:
                problems.append("missing_raw_membership")
                continue
            checked(hashlib.sha256(member.read_bytes()).hexdigest()==row["membership_sha256"],"curve_eligibility_membership_hash",event=row["event_id"])
            membership=pl.read_parquet(member)
            onset=dt.datetime.fromisoformat(event["t0_obs"])
            count=membership.filter(pl.col("first_seen")<=pl.lit(onset))["asn"].n_unique()
            final=membership.filter(pl.col("first_seen")<=pl.lit(onset+dt.timedelta(hours=2)))["asn"].n_unique()
            checked(count==row["observed_zero_count"] and final==row["final_count"],"curve_eligibility_raw_counts",event=row["event_id"])
    proof_relative=str(Path(relative).with_suffix(".verification.json"))
    if raw_sources:
        if not problems:
            source_path=require(f"eventset/{spec['event_table']}/events.parquet")
            if source_path is not None:
                path.with_suffix(".verification.json").write_text(json.dumps({
                    "status":"passed","mode":"private_raw_membership_audit","rows":table.height,
                    "eligibility_content_sha256":content_hash,
                    "source_event_table_sha256":hashlib.sha256(source_path.read_bytes()).hexdigest(),
                    "hash_scope":"Canonical decoded eligibility rows sorted by event_id, JSON sorted keys and compact separators; unchanged by Parquet reencoding. Source hash records pre-anonymization input bytes."
                },indent=2)+"\n")
    else:
        proof_path=require(proof_relative)
        if proof_path is not None:
            proof=json.loads(proof_path.read_text())
            checked(proof.get("status")=="passed" and proof.get("mode")=="private_raw_membership_audit"
                    and proof.get("rows")==table.height and proof.get("eligibility_content_sha256")==content_hash,
                    "curve_eligibility_proof_mismatch")
    return {r["event_id"] for r in records if r["split"]=="test" and r["eligible_growth"]}



def verify_cascade_bootstrap(expected, require, check, close, raw_sources=False):
    relative=expected.get("cascade_bootstrap")
    if not relative:
        return
    path=require(relative)
    if path is None:
        return
    saved=json.loads(path.read_text())
    protocol={"schema_version":1,"comparison":"cascade_minus_persistence_jaccard",
              "resampling_unit":"event","paired":True,"resamples":2000,"seed":0,
              "seed_reset_per_configuration":True,"interval":"two_sided_percentile_95",
              "quantile_method":"linear","event_order":"event_id_ascending"}
    for key,value in protocol.items():
        check(saved.get(key)==value,"cascade_bootstrap_protocol",file=relative,field=key)
    wanted={s["rows"] for s in expected.get("nongraph_tables",[]) if s["kind"]=="cascade" and s["event_table"]=="2025_leak"}
    configurations=saved.get("configurations",[])
    actual=[r["source_rows"] for r in configurations]
    check(len(actual)==len(set(actual)) and set(actual)==wanted,"cascade_bootstrap_population",file=relative)
    check({r.get("task_index") for r in configurations}==set(range(49,60)),"cascade_bootstrap_configurations",file=relative)
    columns=["event_id","cascade_jaccard","persist_jaccard"]
    for record in configurations:
        source=require(record["source_rows"])
        completion=require(str(Path(record["source_rows"]).with_name("complete.json")))
        if source is None or completion is None:
            continue
        task=json.loads(completion.read_text())["task"]
        if raw_sources:
            check(record.get("source_rows_sha256")==hashlib.sha256(source.read_bytes()).hexdigest(),
                  "cascade_bootstrap_original_byte_hash",file=relative,source=record["source_rows"])
        details={"file":relative,"source":record["source_rows"]}
        check(record.get("configuration")==task["args"] and record.get("task_index")==task["index"],
              "cascade_bootstrap_configuration_provenance",**details)
        rows=pl.read_parquet(source).select(sorted(columns)).sort("event_id")
        check(rows.height>0 and rows["event_id"].n_unique()==rows.height,"cascade_bootstrap_duplicate_events",**details)
        check(record.get("metric_columns")==columns,"cascade_bootstrap_metric_columns",**details)
        digest=hashlib.sha256(rows.write_json().encode()).hexdigest()
        check(record.get("metric_content_sha256")==digest,"cascade_bootstrap_content_hash",**details)
        check(record.get("events")==rows.height and record.get("event_ids")==rows["event_id"].to_list(),
              "cascade_bootstrap_event_population",**details)
        cascade=rows["cascade_jaccard"].to_numpy(); persistence=rows["persist_jaccard"].to_numpy()
        check(np.isfinite(cascade).all() and np.isfinite(persistence).all(),"cascade_bootstrap_nonfinite_metrics",**details)
        difference=cascade-persistence
        rng=np.random.default_rng(0)
        means=np.asarray([difference[rng.integers(0,len(difference),len(difference))].mean() for _ in range(2000)])
        ci=np.percentile(means,[2.5,97.5])
        for key,value in (("cascade_jaccard_mean",cascade.mean()),("persistence_jaccard_mean",persistence.mean()),
                          ("mean_paired_difference",difference.mean())):
            check(close(record.get(key),value,1e-10),"cascade_bootstrap_mean",metric=key,**details)
        actual_ci=record.get("paired_difference_ci95",[])
        check(len(actual_ci)==2 and all(close(a,b,1e-10) for a,b in zip(actual_ci,ci)),
              "cascade_bootstrap_interval",**details)


def verify_nongraph(expected, require, events, check, close, raw_sources=False, data_root=None):
    bridges = {}
    boundary = None
    if expected.get("boundary_input_bridge"):
        contract=expected["boundary_input_bridge"]
        paths=[require(contract[key]) for key in ("manifest","equivalence","verification")]
        if all(path is not None for path in paths):
            try:
                from verify_boundary_inputs import verify as verify_boundary
                floor=require("eventset/2025_leak/prefix_floor.parquet")
                boundary=verify_boundary(data_root,*paths,floor_path=floor)
                for relative in boundary["proof"]["source_sha256"]:require(relative)
            except Exception as error:
                check(False,"boundary_input_verification_failed",error=type(error).__name__,detail=str(error))
    if expected.get("nongraph_release"):
        release_path=require(expected["nongraph_release"])
        if release_path is not None:
            release=json.loads(release_path.read_text())
            revisions=release.get("revisions",[])
            check(release.get("status")=="complete" and release.get("data_root")=="nongraph-release", "nongraph_release_status")
            check(len(revisions)==1 and revisions[0].get("index")==62 and revisions[0].get("year")==2025
                  and revisions[0].get("original_folder")=="2025/062_prefix_floor"
                  and revisions[0].get("replacement_folder")=="2025/062_prefix_floor_boundary_v2", "nongraph_release_revision")
            if expected.get("boundary_input_bridge"):
                equivalence_path=require(expected["boundary_input_bridge"]["equivalence"])
                if equivalence_path is not None:
                    check(release.get("boundary_input_equivalence_sha256")==hashlib.sha256(equivalence_path.read_bytes()).hexdigest(), "nongraph_release_equivalence_hash")
            selected=release.get("selected_artifact_sha256",{})
            check(bool(selected),"nongraph_release_empty_artifacts")
            for relative,digest in selected.items():
                safe=not Path(relative).is_absolute() and ".." not in Path(relative).parts
                check(safe,"nongraph_release_unsafe_path",file=relative)
                path=require("analysis/nongraph/"+relative) if safe else None
                if path is not None:check(hashlib.sha256(path.read_bytes()).hexdigest()==digest,"nongraph_release_file_hash",file=relative)
            for revision in revisions:
                relative=revision["replacement_folder"]+"/complete.json"
                check(selected.get(relative)==revision.get("completion_sha256"),"nongraph_release_completion_hash",file=relative)
                completion_path=require("analysis/nongraph/"+relative)
                if completion_path is not None:
                    replacement=json.loads(completion_path.read_text()).get("replacement_for",{})
                    original=revision["original_folder"]+"/complete.json"
                    private_hashes=release.get("pre_anonymization_selected_artifact_sha256",selected)
                    check(replacement.get("path")=="nongraph-final/"+original and replacement.get("sha256")==private_hashes.get(original),
                          "nongraph_release_original_completion_binding",file=relative)
    if expected.get("derived_count_bridge"):
        contract = expected["derived_count_bridge"]
        bridge_path, proof_path = require(contract["manifest"]), require(contract["verification"])
        if bridge_path is not None and proof_path is not None:
            try:
                from verify_derived_counts import verify_bridge
                proof = verify_bridge(data_root, bridge_path, proof_path, boundary_tables=boundary["restored_tables"] if boundary else None)
                bridges = {item["path"]: item for item in proof["tables"]}
                for relative in proof["source_sha256"]:
                    require(relative)
            except Exception as error:
                check(False, "derived_count_bridge_verification_failed", error=type(error).__name__, detail=str(error))
    content_hashes = {}
    for relative in expected.get("required_files", []):
        if not relative.startswith("analysis/nongraph/") or not relative.endswith("/complete.json"):
            continue
        marker = require(relative)
        if marker is None:
            continue
        provenance = json.loads(marker.read_text()).get("correction_run", {})
        check(provenance.get("inputs_unchanged") is True and provenance.get("code_unchanged") is True,
              "nongraph_unstable_execution_inputs", file=relative)
        historical = provenance.get("input_content_sha256", {})
        check(bool(historical) and set(historical) == set(provenance.get("inputs", {})) == set(provenance.get("inputs_after", {})),
              "nongraph_missing_input_provenance", file=relative)
        for input_name, old_digest in historical.items():
            if input_name not in content_hashes:
                path = require(input_name)
                if path is None:
                    continue
                table = pl.read_parquet(path)
                if "event_id" in table.columns:
                    table = table.sort("event_id")
                content_hashes[input_name] = hashlib.sha256(table.select(sorted(table.columns)).write_json().encode()).hexdigest()
            current = content_hashes[input_name]
            restored = None
            if boundary:
                if input_name in boundary["restored_tables"]:
                    restored=boundary["tables"][input_name]["before_content_sha256"]
                elif input_name==boundary["prefix_floor"]["path"]:
                    restored=boundary["prefix_floor"]["before_content_sha256"]
            bridge = bridges.get(input_name, {})
            accepted = current == old_digest or restored == old_digest or (old_digest == bridge.get("before_content_sha256") and (restored or current) == bridge.get("after_content_sha256"))
            check(accepted, "nongraph_execution_source_changed", file=relative, source=input_name,
                  original_content_sha256=old_digest, current_content_sha256=current)
    verify_cascade_bootstrap(expected, require, check, close, raw_sources)
    reports = []
    for spec in expected.get("nongraph_tables", []):
        relative, kind = spec["summary"], spec["kind"]
        summary_path, rows_path = require(relative), require(spec["rows"])
        if summary_path is None or rows_path is None:
            continue
        saved, rows = json.loads(summary_path.read_text()), pl.read_parquet(rows_path)
        source_table = events(spec["event_table"])
        if source_table is None:
            continue
        # Keep full Polars tables for cohort checks, but avoid repeatedly
        # materializing millions of unused set members as Python objects.
        wanted_ids=set(rows["event_id"]) | set(saved.get("sampled_event_ids",[]))
        if kind == "cascade":
            source_columns=["event_id","set_"+saved["delta"],"set_"+saved["target"]]
        elif kind == "prefix_floor":
            source_columns=["event_id","split","set_final_2h"]
        elif kind == "prefix_model":
            source_columns=["event_id"]
        else:
            source_columns=[c for c in ("event_id", "set_d1m", "set_T5m", "set_T15m", "set_T60m", "set_final_2h") if c in source_table.columns]
        selected=source_table.filter(pl.col("error").is_null() & pl.col("event_id").is_in(list(wanted_ids)))
        source={row["event_id"]:row for row in selected.select(list(dict.fromkeys(source_columns))).iter_rows(named=True)}

        def metric(actual, wanted, name, tolerance=.000051):
            check(close(actual, wanted, tolerance), "nongraph_metric", file=relative, metric=name,
                  actual=actual, expected=wanted)

        check(rows.height > 0, "empty_nongraph_table", file=relative)
        check(set(rows["event_id"]) <= source.keys(), "nongraph_missing_source_events", file=relative)
        if kind in ("curve_naive", "tsfm", "chronos_lora"):
            keys = ["event_id", "model", "delta_min", "horizon_min"]
            check(rows.unique(keys).height == rows.height, "duplicate_curve_predictions", file=relative)
            check(rows.filter(pl.col("horizon_min")<=pl.col("delta_min")).is_empty(),
                  "nongraph_nonfuture_curve_horizon",file=relative)
            horizons = {1: "d1m", 5: "T5m", 15: "T15m", 60: "T60m", 120: "final_2h"}
            for row in rows.iter_rows(named=True):
                event = source.get(row["event_id"])
                if event is None:
                    continue
                truth = len(set(event["set_"+horizons[row["horizon_min"]]]))
                last = len(set(event["set_"+horizons[row["delta_min"]]]))
                check(np.isfinite(row["prediction"]) and np.isfinite(row["smape"]), "nonfinite_curve_prediction", file=relative, event=row["event_id"])
                metric(row["truth"], truth, "curve_full_target", 1e-8)
                if "observed_delta_count" in row:
                    metric(row["observed_delta_count"], last, "curve_observed_count", 1e-8)
                metric(row["smape"], smape(row["prediction"], truth), "curve_event_smape", 1e-8)
                if row["model"] == "persistence":
                    metric(row["prediction"], last, "curve_persistence_count", 1e-8)
                if row.get("persistence_smape") is not None:
                    metric(row["persistence_smape"], smape(last, truth), "curve_paired_persistence", 1e-8)
            for (model, delta, horizon), group in rows.group_by("model", "delta_min", "horizon_min", maintain_order=True):
                if kind == "curve_naive":
                    value = saved.get(f"d{delta}m", {}).get(f"{model}:T{horizon}m")
                    tolerance = .00051
                elif kind == "chronos_lora":
                    value = saved.get("by_delta", {}).get(f"d{delta}m", {}).get(model, {}).get(f"T{horizon}m")
                    tolerance = .000051
                else:
                    value = saved.get(f"{model}@d{delta}m", {}).get(f"T{horizon}m")
                    tolerance = .000051
                metric(value, group["smape"].mean(), f"{model}@d{delta}m:T{horizon}m", tolerance)
            if kind in ("curve_naive", "tsfm"):
                cohort = source_table.filter(pl.col("error").is_null() & (pl.col("split")=="test")
                    & (pl.col("asns_final_2h") >= saved["min_asns"])
                    & (pl.col("asns_final_2h") > pl.col("asns_T5m")))
                if saved.get("set_tag", "").startswith("leak"):
                    cohort = cohort.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
                sampled = [cohort["event_id"][int(i)] for i in np.random.default_rng(11).choice(cohort.height, min(spec["sample"], cohort.height), replace=False)]
                check(sampled == saved.get("sampled_event_ids"), "curve_sample_population", file=relative)
                check(set(rows["event_id"]) <= set(sampled), "curve_unselected_event", file=relative)
                if kind == "curve_naive":
                    check(set(rows["event_id"]) == set(sampled), "curve_missing_selected_event", file=relative)
                    metric(saved.get("events_used"), len(sampled), "curve_events_used", 0)
            else:
                expected_test=verify_curve_eligibility(spec,saved,source_table,require,check,raw_sources)
                check(set(saved["test_event_ids"])==expected_test,"curve_test_eligibility_population",file=relative)
                check(set(rows["event_id"]) == expected_test, "curve_test_population", file=relative)
                metric(saved["test_series"], rows["event_id"].n_unique(), "curve_test_series", 0)
            # Each claimed result cell must contain its entire declared cohort.
            cells = []
            if kind == "curve_naive":
                for dk, values in saved.items():
                    if dk.startswith("d") and dk.endswith("m") and dk[1:-1].isdigit():
                        cells.extend((key.split(":")[0],int(dk[1:-1]),int(key.split(":T")[1][:-1])) for key in values)
            elif kind == "chronos_lora":
                for dk, models in saved["by_delta"].items():
                    cells.extend((model,int(dk[1:-1]),int(horizon[1:-1])) for model,values in models.items() for horizon in values)
            else:
                for key, values in saved.items():
                    if "@d" in key:
                        model, delta = key.split("@d")
                        cells.extend((model,int(delta[:-1]),int(horizon[1:-1])) for horizon in values if horizon.startswith("T"))
                if saved.get("required_models"):
                    check(set(saved["required_models"]) <= set(rows["model"]) | {item["model"] for item in saved.get("failures",[])},
                          "missing_required_curve_model", file=relative)
            for model,delta,horizon in cells:
                wanted = set(saved["test_event_ids"] if kind=="chronos_lora" else saved["sampled_event_ids"])
                if kind=="tsfm":
                    wanted = {eid for eid in wanted if len(set(source[eid]["set_"+horizons[delta]]))>0}
                    failed = {row["event_id"] for row in saved.get("failures",[]) if row["model"]==model and row["delta_min"]==delta}
                    wanted -= failed
                present=set(rows.filter((pl.col("model")==model)&(pl.col("delta_min")==delta)&(pl.col("horizon_min")==horizon))["event_id"])
                check(present==wanted,"curve_cell_population",file=relative,model=model,delta=delta,horizon=horizon,missing=len(wanted-present),unexpected=len(present-wanted))
        elif kind == "cascade":
            check(rows["event_id"].n_unique() == rows.height, "duplicate_cascade_events", file=relative)
            metric(saved["events_scored"], rows.height, "events_scored", 0)
            if "sample_requested" in saved and "sampling_seed" in saved:
                pool=source_table.filter(pl.col("error").is_null() & (pl.col("split")=="test")
                    & pl.col("set_"+saved["delta"]).is_not_null()
                    & (pl.col("set_"+saved["target"]).list.len()>pl.col("set_"+saved["delta"]).list.len()))
                if saved.get("min_asns"):
                    pool=pool.filter(pl.col("asns_final_2h")>=saved["min_asns"])
                if saved.get("set_tag", "").startswith("leak"):
                    pool=pool.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s")>=-60))
                indices=np.random.default_rng(saved["sampling_seed"]).choice(pool.height,min(saved["sample_requested"],pool.height),replace=False)
                wanted={pool["event_id"][int(i)] for i in indices}
                excluded={item["event_id"] for item in saved.get("excluded_events",[])}
                check(not (set(rows["event_id"]) & excluded) and set(rows["event_id"]) | excluded == wanted,
                      "cascade_sample_population",file=relative)
                metric(saved["growing_test_events_total"],pool.height,"cascade_eligible_population_count",0)
            for row in rows.iter_rows(named=True):
                event = source.get(row["event_id"])
                if event is None:
                    continue
                seed, final = set(event["set_"+saved["delta"]]), set(event["set_"+saved["target"]])
                for name, value in {"seeds": len(seed), "final": len(final),
                    "persist_jaccard": jaccard(seed, final), "persist_recall": len(seed & final)/max(len(final), 1),
                    "persist_size_smape": smape(len(seed), len(final)),
                    "cascade_size_smape": smape(row["cascade_expected_size"], len(final))}.items():
                    metric(row[name], value, name, 1e-8)
                check("scored_asns" in row and "scored_probabilities" in row,
                      "missing_cascade_predictions", file=relative, event=row["event_id"])
                if "scored_asns" not in row or "scored_probabilities" not in row:
                    continue
                asns, probabilities = row["scored_asns"], row["scored_probabilities"]
                check(len(asns)==len(probabilities) and len(asns)==len(set(asns)), "invalid_cascade_prediction_shape", file=relative)
                check(all(np.isfinite(p) and 0<=p<=1 for p in probabilities), "invalid_cascade_probabilities", file=relative)
                check(seed | final <= set(asns), "cascade_pruned_truth_or_seeds", file=relative, event=row["event_id"])
                pred = {asn for asn,p in zip(asns, probabilities) if p >= .5}
                check(seed <= pred, "cascade_dropped_seeds", file=relative, event=row["event_id"])
                check("prediction_candidate_asns" in row,"missing_cascade_candidate_universe",file=relative,event=row["event_id"])
                if "prediction_candidate_asns" in row:
                    candidates=set(row["prediction_candidate_asns"])
                    check(seed <= candidates and pred <= candidates and all(p==0 for asn,p in zip(asns,probabilities) if asn not in candidates),
                          "cascade_oracle_candidate_leakage",file=relative,event=row["event_id"])
                    metric(row["cascade_expected_size"],sum(probabilities),"cascade_candidate_expected_size",1e-8)
                for name, value in {"cascade_jaccard": jaccard(pred, final),
                    "cascade_precision": len(pred & final)/max(len(pred),1),
                    "cascade_recall": len(pred & final)/max(len(final),1),
                    "cascade_auprc": average_precision([a in final for a in asns], probabilities)}.items():
                    metric(row[name], value, name)
            for column in rows.columns:
                if column+"_mean" in saved:
                    metric(saved[column+"_mean"], rows[column].mean(), column+"_mean")
            metric(saved["cascade_beats_persistence_frac"], (rows["cascade_jaccard"] > rows["persist_jaccard"]).mean(), "cascade_beats_persistence_frac")
        elif kind == "prefix_floor":
            check(rows["event_id"].n_unique()==rows.height, "duplicate_prefix_events", file=relative)
            pool=source_table.filter(pl.col("error").is_null())
            if "observation_lag_s" in pool.columns:
                pool=pool.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s")>=-60))
            check(set(rows["event_id"])==set(pool["event_id"]),"prefix_floor_population",file=relative)
            metric(saved["events"], rows.height, "prefix_events", 0)
            test = rows.filter(pl.col("split")=="test")
            metric(saved["test"], test.height, "prefix_test_events", 0)
            for row in rows.iter_rows(named=True):
                final = set(row["set_final_2h"])
                if row["event_id"] in source:
                    event=source[row["event_id"]]
                    metric(row["asns_2h"],len(set(event["set_final_2h"])),"prefix_source_AS_count",0)
                    check(row["split"]==event["split"],"prefix_source_split",file=relative,event=row["event_id"])
                metric(row["prefixes_2h"], len(final), "prefix_full_target", 0)
                for horizon in ("d30s", "d1m", "d5m", "d15m"):
                    seed = set(row["set_"+horizon])
                    check(seed <= final, "nonnested_prefix_target", file=relative, event=row["event_id"])
                    metric(row["j_"+horizon], jaccard(seed,final), "prefix_j_"+horizon, 1e-8)
                    check(row["grow_"+horizon] == (len(final)>len(seed)), "prefix_growth_flag", file=relative)
            for horizon, value in saved["persistence_prefix_jaccard_test"].items():
                metric(value, test["j_"+horizon].mean(), "prefix_test_"+horizon)
                metric(saved["still_growing_prefixes"][horizon], rows["grow_"+horizon].mean(), "prefix_growing_"+horizon)
            for q,value in zip((.5,.9),saved["prefixes_2h_p50_p90"]):
                metric(value, rows["prefixes_2h"].quantile(q), f"prefix_q{q}")
            for label, predicate in (("large_leaks_ge200",pl.col("asns_2h")>=200), ("multi_prefix_ge10",pl.col("prefixes_2h")>=10)):
                if label not in saved:
                    continue
                subset=rows.filter(predicate); subtest=subset.filter(pl.col("split")=="test")
                metric(saved[label]["events"], subset.height, label+".events",0)
                metric(saved[label]["test"], subtest.height,label+".test",0)
                for horizon,value in saved[label]["persistence_prefix_jaccard_test"].items():
                    metric(value,subtest["j_"+horizon].mean(),label+"."+horizon)
                if "prefixes_2h_p50" in saved[label]:
                    metric(saved[label]["prefixes_2h_p50"],subset["prefixes_2h"].median(),label+".p50")
        elif kind == "prefix_model":
            floor_path = require(spec["prefix_floor"])
            prediction_paths = [require(f"{spec['predictions_dir']}/{eid}.parquet") for eid in rows["event_id"]]
            if any(path is None for path in prediction_paths) or floor_path is None:
                continue
            predictions=pl.concat([pl.read_parquet(path) for path in prediction_paths])
            check(all(np.isfinite(p) and 0<=p<=1 for p in predictions["p"]), "invalid_prefix_probabilities", file=relative)
            floor={r["event_id"]:r for r in pl.read_parquet(floor_path).iter_rows(named=True)}
            if "excluded_event_ids" in saved:
                wanted={eid for eid,r in floor.items() if r["prefixes_2h"]>=10 and r["split"]=="test"}
                wanted-=set(saved["excluded_event_ids"])
                check(set(rows["event_id"])==wanted,"prefix_model_population",file=relative)
            check(predictions.unique(["event_id","prefix"]).height==predictions.height, "duplicate_prefix_predictions",file=relative)
            check(rows["event_id"].n_unique()==rows.height, "duplicate_prefix_model_events",file=relative)
            check(set(predictions["event_id"])==set(rows["event_id"]), "prefix_prediction_population",file=relative)
            metric(saved["events_test"],rows.height,"prefix_model_events",0)
            indexed={r["event_id"]:r for r in rows.iter_rows(named=True)}
            for (eid,), group in predictions.group_by("event_id",maintain_order=True):
                row=indexed.get(eid); baseline=floor.get(eid)
                if row is None or baseline is None:
                    check(False,"missing_prefix_source",file=relative,event=eid); continue
                truth=set(group.filter(pl.col("y")==1)["prefix"])
                seed=set(group.filter(pl.col("seen_delta")==1)["prefix"])
                check(truth==set(baseline["set_final_2h"]) and seed==set(baseline["set_d30s"]),"prefix_pruned_truth_or_seeds",file=relative,event=eid)
                for name,value in {"n_cand":int(group["in_candidate"].sum()),"n_leaked":len(truth),"n_seen":len(seed),
                    "unreachable_truth":group.filter((pl.col("in_candidate")==0)&(pl.col("y")==1)).height}.items():
                    metric(row[name],value,name,0)
                rules={"j_persist":pl.col("seen_delta")==1,"j_rule_src":pl.col("share_src")>.5,
                    "j_rule_nonprov":(pl.col("share_src")>.5)|(pl.col("share_peer")>.5)|(pl.col("share_prov")>.5),"j_model":pl.col("p")>=saved["threshold"]}
                for name,rule in rules.items():
                    pred=set(group.filter(rule&(pl.col("in_candidate")==1))["prefix"])|seed
                    metric(row[name],jaccard(pred,truth),name,1e-8)
            for name,value in saved["jaccard_test_mean"].items():
                metric(value,rows[name].mean(),name)
            metric(saved["candidates_per_event_p50"],rows["n_cand"].median(),"prefix_candidates_median")
            metric(saved["leaked_per_event_p50"],rows["n_leaked"].median(),"prefix_truth_median")
            rng=np.random.default_rng(0)
            for name,column in (("model_minus_persist_ci95","j_model"),("rule_src_minus_persist_ci95","j_rule_src")):
                values=(rows[column]-rows["j_persist"]).to_numpy()
                interval=np.percentile([rng.choice(values,len(values)).mean() for _ in range(1000)], [2.5,97.5])
                check(len(saved[name])==2 and all(close(a,b) for a,b in zip(saved[name],interval)),"prefix_bootstrap_interval",file=relative,metric=name)
        else:
            check(False,"unknown_nongraph_kind",file=relative,experiment_kind=kind)
        reports.append({"summary":relative,"summary_sha256":hashlib.sha256(summary_path.read_bytes()).hexdigest(),
                        "prediction_table":spec["rows"],"prediction_sha256":hashlib.sha256(rows_path.read_bytes()).hexdigest(),
                        "kind":kind,"rows":rows.height})
    return reports


if __name__ == "__main__":
    import argparse
    import time
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data",type=Path)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--wait-for-marker",type=Path,action="append",default=[],help="wait for every declared marker (repeatable)")
    parser.add_argument("--run-layout",action="store_true",help="read analysis/nongraph from the sibling nongraph-final run directory")
    parser.add_argument("--derived-count-bridge",action="store_true",help="require the explicit independently verified four-column source bridge")
    args=parser.parse_args()
    while not all(marker.exists() for marker in args.wait_for_marker):
        time.sleep(10)
    manifest_bytes=args.manifest.read_bytes()
    expected=json.loads(manifest_bytes)
    if args.derived_count_bridge:
        expected["derived_count_bridge"]={"manifest":"analysis/derived-count-fill-bridge.json", "verification":"analysis/derived-count-fill-verification.json"}
    nongraph_root=args.data.parent/"nongraph-final"
    if args.run_layout and expected.get("nongraph_release"):
        release=json.loads((args.data.parent/Path(expected["nongraph_release"]).name).read_text())
        root=Path(release["data_root"])
        assert not root.is_absolute() and ".." not in root.parts
        nongraph_root=args.data.parent/root
    file_hashes={}
    failures=[]
    def check(condition,kind,**details):
        if not condition:
            failures.append({"kind":kind,**details})
    def require(relative):
        if args.run_layout and relative.startswith("analysis/nongraph/"):
            path=nongraph_root/relative.removeprefix("analysis/nongraph/")
        elif args.run_layout and relative=="eventset/2025_leak/prefix_floor.parquet" and expected.get("nongraph_release"):
            floor_spec=next(s for s in expected["nongraph_tables"] if s["kind"]=="prefix_floor" and s["event_table"]=="2025_leak")
            path=nongraph_root/floor_spec["rows"].removeprefix("analysis/nongraph/")
        elif args.run_layout and relative=="analysis/nongraph-boundary-input-equivalence.json":
            path=args.data.parent/"boundary-audit/nongraph-input-equivalence.json"
        elif args.run_layout and relative in {"analysis/boundary-input-bridge.json", "analysis/boundary-input-verification.json", "analysis/nongraph-release-complete.json","analysis/derived-count-fill-bridge.json", "analysis/derived-count-fill-verification.json", "analysis/nongraph-cascade-bootstrap.json"}:
            path=args.data.parent/Path(relative).name
        else:
            path=args.data/relative
        check(path.is_file(),"missing_required_file",file=relative)
        if path.is_file() and relative not in file_hashes:
            file_hashes[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
        return path if path.is_file() else None
    cache={}
    def events(name):
        if name not in cache:
            path=require(f"eventset/{name}/events.parquet")
            cache[name]=pl.read_parquet(path) if path else None
        return cache[name]
    def close(a,b,tolerance=.000051):
        if a is None or b is None:
            return a is None and b is None
        return bool(abs(a-b)<=tolerance or np.isnan(a) and np.isnan(b))
    check(bool(expected.get("nongraph_tables")),"empty_nongraph_manifest")
    for relative in expected.get("required_files",[]):
        require(relative)
    reports=verify_nongraph(expected,require,events,check,close,raw_sources=args.run_layout,data_root=args.data)
    if args.run_layout:
        for spec in expected["nongraph_tables"]:
            if spec.get("eligibility"):
                require(str(Path(spec["eligibility"]).with_suffix(".verification.json")))
    manifest_hash=hashlib.sha256(manifest_bytes).hexdigest()
    check(hashlib.sha256(args.manifest.read_bytes()).hexdigest()==manifest_hash,"nongraph_manifest_changed_during_verification")
    result={"scope":"Declared nongraph outputs only; not full release sign-off","tables":reports,"failures":failures,
            "manifest_sha256":manifest_hash,"file_sha256":file_hashes,"derived_count_bridge":expected.get("derived_count_bridge"),"cascade_bootstrap":expected.get("cascade_bootstrap"),"boundary_input_bridge":expected.get("boundary_input_bridge"),"nongraph_release":expected.get("nongraph_release")}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"tables":len(reports),"failures":len(failures)}))
    raise SystemExit(bool(failures))
