"""The release gate must fail closed and independently detect altered artifacts."""
import importlib.util
import math
import json
import os
from pathlib import Path
import subprocess
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("release_verifier", ROOT / "scripts/verify_corrected_release.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_release_requires_declared_inputs(tmp_path):
    report = module.verify(tmp_path)
    assert {x["kind"] for x in report["failures"]} == {"missing_expected_manifest", "empty_required_manifest_category"}


def test_release_recomputes_sources_and_detects_corruption(tmp_path):
    for name in ("2024", "2024_hijack_first_transition", "2024_recovery_first_transition"):
        folder = tmp_path / "eventset" / name
        folder.mkdir(parents=True)
        recovery = "recovery" in name
        row = {"event_id": "r" if recovery else "h", "error": None, "reason": "catalogue", "split": "test",
               "duration_min": 3.0, "observation_lag_s": 0.0, "measurement_definition": "first_transition",
               "t0_obs": "2024-01-01T00:01:00+00:00" if recovery else "2024-01-01T00:00:00+00:00",
               "set_d30s": [1], "set_final_2h": [1, 2], "asns_d30s": 1, "asns_final_2h": 2, "t90_s": 40.5}
        pl.DataFrame([row]).write_parquet(folder / "events.parquet")
        pl.DataFrame({"delta": ["d30s"], "target": ["final_2h"], "events": [1], "jaccard_mean": [0.5]}).write_csv(folder / "persistence_test.csv")
    inv = tmp_path / "inventory/2024"
    inv.mkdir(parents=True)
    pl.DataFrame({"event_id": ["r"], "hijack_id": ["h"], "gap_s": [60], "split": ["test"]}).write_parquet(inv / "recovery_replay_selection.parquet")
    out = tmp_path / "eventset/2024_recovery_first_transition"
    subprocess.run([sys.executable, str(ROOT / "scripts/recovery_pairs_full.py"), "2024", "--hijack-events",
                    str(tmp_path / "eventset/2024_hijack_first_transition/events.parquet"), "--recovery-events", str(out / "events.parquet"),
                    "--output-dir", str(out), "--require-matched-definition"], env={**os.environ, "BGBENCH_DATA_ROOT": str(tmp_path)}, check=True, capture_output=True)
    models = tmp_path / "tgn/demo/d30s/_results"
    models.mkdir(parents=True)
    pl.DataFrame({"event_id": ["h"], "jaccard_persist": [0.5], "jaccard_model": [0.7]}).write_csv(models / "gcn_test_per_event.csv")
    (models / "gcn_summary.json").write_text(json.dumps({"events": 1, "jaccard_persist_mean": 0.5, "jaccard_model_mean": 0.7}))
    manifest = {"event_tables": ["2024", "2024_hijack_first_transition", "2024_recovery_first_transition"],
                "pair_tables": ["eventset/2024_recovery_first_transition/pairs.parquet"],
                "model_tables": ["tgn/demo/d30s/_results/gcn_test_per_event.csv"],
                "model_targets": {"tgn/demo/d30s/_results/gcn_test_per_event.csv": {"event_table": "2024", "horizon": "d30s"}}}
    pl.DataFrame({"event_id": ["h"], "validity": ["invalid"]}).write_parquet(tmp_path / "eventset/2024/rpki_validity.parquet")
    frontier = tmp_path / "eventset/2024/rov_frontier.json"
    frontier.write_text(json.dumps({"year": 2024, "by_validity": {"invalid": {"events": 1,
        "carriers_measured_share": .5, "frontier_measured_share": .667, "enforcing_share_carriers": 0,
        "enforcing_share_frontier": .5, "events_with_both_measured": 1,
        "log_odds_frontier_vs_carriers_mean": round(math.log(3), 3), "log_odds_mean_ci95_bootstrap": None}}}))
    pl.DataFrame({"event_id": ["h"], "validity": ["invalid"], "carriers": [2], "carriers_measured": [1],
                  "carriers_enforcing": [0], "frontier": [3], "frontier_measured": [2], "frontier_enforcing": [1],
                  "log_odds": [math.log(3)]}).write_parquet(frontier.with_suffix(".parquet"))
    manifest["frontier_tables"] = ["eventset/2024/rov_frontier.json"]
    baseline = tmp_path / "verification/frozen-ids/2024.parquet"
    baseline.parent.mkdir(parents=True)
    pl.DataFrame({"event_id": ["h"]}).write_parquet(baseline)
    manifest["event_selections"] = {"2024": {"file": "verification/frozen-ids/2024.parquet", "key": "event_id"}}
    index_path = tmp_path / "tgn/demo/d30s/index.csv"
    pl.DataFrame({"event_id": ["h", "training"], "split": ["test", "train"]}).write_csv(index_path)
    manifest["model_cohorts"] = {"tgn/demo/d30s/_results/gcn_test_per_event.csv": {
        "index_tables": ["tgn/demo/d30s/index.csv"], "split": "test"}}
    assert module.verify(tmp_path, manifest)["failures"] == []
    manifest["model_cohorts"]["tgn/demo/d30s/_results/gcn_test_per_event.csv"]["split"] = "all"
    assert "model_population_completeness" in {x["kind"] for x in module.verify(tmp_path, manifest)["failures"]}
    manifest["model_cohorts"]["tgn/demo/d30s/_results/gcn_test_per_event.csv"]["split"] = "test"
    pl.DataFrame({"event_id": ["h", "missing-baseline-event"]}).write_parquet(baseline)
    assert "event_population_completeness" in {x["kind"] for x in module.verify(tmp_path, manifest)["failures"]}
    pl.DataFrame({"event_id": ["h"]}).write_parquet(baseline)
    pl.read_parquet(frontier.with_suffix(".parquet")).with_columns(log_odds=pl.lit(0.0)).write_parquet(frontier.with_suffix(".parquet"))
    assert "frontier_event_odds" in {x["kind"] for x in module.verify(tmp_path, manifest)["failures"]}
    table = pl.read_parquet(out / "events.parquet").with_columns(asns_final_2h=pl.lit(999), t90_s=pl.lit(11.0))
    table.write_parquet(out / "events.parquet")
    failures = {x["kind"] for x in module.verify(tmp_path, manifest)["failures"]}
    assert {"extent_count_disagreement", "pair_source_metric_disagreement"} <= failures
    (models / "gcn_test_per_event.csv").unlink()
    assert "missing_required_file" in {x["kind"] for x in module.verify(tmp_path, manifest)["failures"]}


def test_model_target_union_and_collector_membership_are_independent(tmp_path):
    import datetime as dt
    onset = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    for year, eid in ((2024, "h1"), (2025, "h2")):
        folder = tmp_path / "eventset" / f"{year}_leak"
        folder.mkdir(parents=True)
        pl.DataFrame({"event_id": [eid], "error": [None], "t0_obs": [onset.isoformat()],
                      "set_d30s": [[1]], "set_final_2h": [[1, 2]]}).write_parquet(folder / "events.parquet")
        replay = tmp_path / "events_replay_leak" / eid
        replay.mkdir(parents=True)
        pl.DataFrame({"asn": [1, 2, 3, 4, 5], "collector": ["rrc00", "rrc00", "rrc00", "rrc01", "rrc00"],
                      "first_seen": [onset+dt.timedelta(seconds=s) for s in (0, 40, 100, 0, 8000)]}).write_parquet(replay / "membership.parquet")
    models = tmp_path / "tgn/demo/d30s/_results"
    models.mkdir(parents=True)
    curve_evidence = {f"curve_{name}_{i}":[value,value] for i in range(4)
                      for name,value in (("true",3),("pred",3.),("lo",1.),("hi",5.))}
    curve_evidence.update({f"curve_evaluated_{i}":[True,True] for i in range(4)})
    curve_evidence["observation_cutoff_s"]=[30,30]
    curve_evidence.update({"curve_true_2h":[3,3],"curve_pred_2h":[3.,3.],"n_seed":[1,1],
                           "curve_smape_model":[0.,0.],"curve_smape_persist":[1.,1.],
                           "curve_smape_2h_model":[0.,0.],"curve_smape_2h_persist":[1.,1.],"curve_cover80":[1.,1.],
                           "predicted_asns_tuned":["[1,2,3]","[1,2,3]"],"jaccard_model_tuned":[1.,1.]})
    pl.DataFrame({"event_id": ["h1", "h2"], "jaccard_persist": [1/3, 1/3], "true_size": [3, 3],
                  **curve_evidence}).write_csv(models / "gcn_test_per_event.csv")
    (models / "gcn_summary.json").write_text(json.dumps({"events": 2, "jaccard_persist_mean": 1/3}))
    relative = "tgn/demo/d30s/_results/gcn_test_per_event.csv"
    manifest = {"event_tables": [], "pair_tables": [], "model_tables": [relative], "model_targets": {relative: {
        "event_tables": ["2024_leak", "2025_leak"], "horizon": "d30s",
        "membership_source": {"replay_family": "leak", "collector": "rrc00"},
        "count_forecast":"curve","membership_predictions":{"model_tuned":"predicted_asns_tuned"}}}}
    # Only the deliberately omitted release categories fail; both model years and
    # collector-specific targets are checked against raw retained membership.
    assert {x["kind"] for x in module.verify(tmp_path, manifest)["failures"]} == {"empty_required_manifest_category"}
    import shutil
    final_models=tmp_path.parent/(tmp_path.name+"-final-model-data")
    shutil.copytree(tmp_path/"tgn",final_models/"tgn")
    original_model=(tmp_path/relative).read_bytes()
    pl.DataFrame({"event_id":["stale"],"jaccard_persist":[0.]}).write_csv(tmp_path/relative)
    assert {x["kind"] for x in module.verify(tmp_path,manifest,final_models)["failures"]} == {"empty_required_manifest_category"}
    (tmp_path/relative).write_bytes(original_model)
    target_spec = importlib.util.spec_from_file_location("release_targets", ROOT / "scripts/materialize_release_targets.py")
    target_module = importlib.util.module_from_spec(target_spec)
    target_spec.loader.exec_module(target_module)
    release = tmp_path / "public"
    public_manifest = target_module.materialize(tmp_path, release, manifest)
    target_path = release / public_manifest["model_targets"][relative]["target_table"]
    targets = pl.read_parquet(target_path)
    assert targets["set_final_2h"].to_list() == [[1, 2, 3], [1, 2, 3]]
    assert targets["set_d1m"].to_list() == [[1, 2], [1, 2]]
    assert targets["set_T5m"].to_list() == [[1,2,3],[1,2,3]]
    assert public_manifest["model_targets"][relative]["count_forecast"]=="curve"
    assert public_manifest["model_targets"][relative]["membership_predictions"]=={"model_tuned":"predicted_asns_tuned"}
    public_model = release / relative
    public_model.parent.mkdir(parents=True)
    shutil.copy2(tmp_path / relative, public_model)
    shutil.copy2(models / "gcn_summary.json", public_model.with_name("gcn_summary.json"))
    assert not (release / "events_replay_leak").exists()
    assert {x["kind"] for x in module.verify(release, public_manifest)["failures"]} == {"empty_required_manifest_category"}
    assert "membership_source" in manifest["model_targets"][relative]
    assert "membership_source" not in public_manifest["model_targets"][relative]
    targets.with_columns(pl.Series("set_final_2h", [[1], [1]])).write_parquet(target_path)
    assert {"model_full_target_persistence", "file_hash_disagreement"} <= {x["kind"] for x in module.verify(release, public_manifest)["failures"]}
    manifest["model_targets"][relative].pop("membership_source")
    kinds = {x["kind"] for x in module.verify(tmp_path, manifest)["failures"]}
    assert {"model_full_target_persistence", "model_full_target_size"} <= kinds


def test_beacon_delays_are_recomputed_from_paired_timestamps(tmp_path):
    import datetime as dt
    onset=dt.datetime(2024,6,10,tzinfo=dt.timezone.utc)
    folder=tmp_path/"rpki/beacon-delay/demo"
    folder.mkdir(parents=True)
    row={"prefix":"192.0.2.0/24","slot_ts":onset,"collector":"rrc00","peer_ip":"192.0.2.1","peer_asn":1,
        "kind":"normal","setup":"test","origin_known":True,"first_a_arrival_slot_ts":onset,"orig_ts":onset,"first_a_ts":onset+dt.timedelta(seconds=2),"a_delay_s":2.,
        "sched_wd_ts":onset+dt.timedelta(hours=2),"first_w_ts":onset+dt.timedelta(hours=2,seconds=97),"w_delay_s":97.,
        "first_a_origin_ambiguous":False}
    pl.DataFrame([row]).write_parquet(folder/"cycles.parquet")
    saved={"cycles":1,"eligible_cycles":1,"excluded_cycles":0,"excluded_late_announcement":0,
        "excluded_negative_delay":0,"excluded_missing_origin":0,"ambiguous_first_origin_cycles":0,"first_arrival_in_different_cycle":0,
        "statistics":{"announcement":{"n":1,"p50_s":2.,"p90_s":2.,"p99_s":2.},
                      "withdrawal":{"n":1,"p50_s":97.,"p90_s":97.,"p99_s":97.}}}
    (folder/"summary.json").write_text(json.dumps(saved))
    pl.DataFrame({"collector":["rrc00"],"kind":["normal"],"setup":["test"],"n_cycles":[1],"n_peers":[1],
                  "a_delay_p50":[2.],"a_delay_p90":[2.],"a_delay_max":[2.],"w_delay_p50":[97.],
                  "w_delay_p90":[97.],"frac_cycles_with_w":[1.]}).write_parquet(folder/"per_vp_summary.parquet")
    expected={"beacon_delay_tables":["rpki/beacon-delay/demo/summary.json"]}
    assert {x["kind"] for x in module.verify(tmp_path,expected)["failures"]}=={"empty_required_manifest_category"}
    row["orig_ts"]=onset-dt.timedelta(days=1)
    pl.DataFrame([row]).write_parquet(folder/"cycles.parquet")
    assert "beacon_delay_timestamp_disagreement" in {x["kind"] for x in module.verify(tmp_path,expected)["failures"]}


def test_count_evidence_uses_full_truth_and_full_seed_floor():
    row={"event_id":"e","observation_cutoff_s":30,**{f"curve_evaluated_{i}":True for i in range(4)},"curve_true_2h":4,"curve_pred_2h":3.,
         "curve_smape_model":2/7,"curve_smape_persist":2/7,
         "curve_smape_2h_model":2/7,"curve_smape_2h_persist":2/7,"curve_cover80":1.}
    for i in range(4):
        row.update({f"curve_true_{i}":4,f"curve_pred_{i}":3.,f"curve_lo_{i}":3.,f"curve_hi_{i}":5.})
    failures=[]
    check=lambda ok,kind,**details: failures.append(kind) if not ok else None
    module.verify_model_counts(row,[4]*4,3,"curve",check,"model.csv",cutoff=30)
    assert not failures
    module.verify_model_counts(row,[5]*4,3,"curve",check,"model.csv",cutoff=30)
    assert {"model_curve_target_count","model_curve_metric_disagreement"}<=set(failures)
    failures.clear()
    row["curve_lo_0"]=2.
    module.verify_model_counts(row,[4]*4,3,"curve",check,"model.csv",cutoff=30)
    assert "model_curve_seed_floor" in failures
    failures.clear()
    module.verify_model_counts({"event_id":"e"},[4]*4,3,"curve",check,"model.csv",cutoff=30)
    assert failures==["missing_model_count_evidence"]
    failures.clear()
    historical={"event_id":"e","pred_final":2.,"true_final":4,"smape_2h_hist":2/3,"smape_2h_persist":2/7}
    module.verify_model_counts(historical,[4],3,"final",check,"model.csv",cutoff=30)
    assert failures==["model_final_seed_floor"]


def test_membership_predictions_are_rescored_against_full_sources():
    row={"event_id":"e","predicted":"[1, 2, 9]","jaccard_model":.5,
         "recall_model":2/3,"precision_model":2/3,"size_ratio_model":1.,"new_pos":2}
    failures=[]
    check=lambda ok,kind,**details: failures.append(kind) if not ok else None
    module.verify_model_membership(row,{1},{1,2,3},{"model":"predicted"},check,"model.csv")
    assert not failures
    row["predicted"]="[2, 3, 9]"
    module.verify_model_membership(row,{1},{1,2,3},{"model":"predicted"},check,"model.csv")
    assert "model_prediction_missing_seeds" in failures
    failures.clear()
    row["predicted"]="[1, 2, 3]"
    module.verify_model_membership(row,{1},{1,2,3},{"model":"predicted"},check,"model.csv")
    assert "model_membership_metric_disagreement" in failures
    failures.clear()
    row.pop("predicted")
    module.verify_model_membership(row,{1},{1,2,3},{"model":"predicted"},check,"model.csv")
    assert failures==["missing_model_membership_evidence"]


def test_auxiliary_proof_is_required_by_declared_contract(tmp_path):
    contract=tmp_path/"analysis/expected-graph-auxiliary.json"
    contract.parent.mkdir()
    contract.write_text(json.dumps({"auxiliary_files":[]}))
    report=module.verify(tmp_path,{"auxiliary_verification":"analysis/expected-graph-auxiliary.json"})
    assert "auxiliary_verification_failed" in {r["kind"] for r in report["failures"]}
    assert report["auxiliary_verification"]["status"]=="failed"


def test_only_future_curve_horizons_enter_error_and_coverage():
    row={"event_id":"e","observation_cutoff_s":900,"curve_true_2h":5,"curve_pred_2h":3.,
         "curve_smape_model":(2/7+.5)/2,"curve_smape_persist":(2/7+.5)/2,
         "curve_smape_2h_model":.5,"curve_smape_2h_persist":.5,"curve_cover80":1.}
    for i,truth in enumerate([2,3,4,5]):
        row.update({f"curve_evaluated_{i}":i>=2,f"curve_true_{i}":truth,
                    f"curve_pred_{i}":3.,f"curve_lo_{i}":3.,f"curve_hi_{i}":6.})
    failures=[]
    check=lambda ok,kind,**details: failures.append(kind) if not ok else None
    module.verify_model_counts(row,[2,3,4,5],3,"curve",check,"model.csv",cutoff=900)
    assert not failures
    row["curve_evaluated_0"]=True
    module.verify_model_counts(row,[2,3,4,5],3,"curve",check,"model.csv",cutoff=900)
    assert failures==["model_curve_horizon_mask"]


def test_probability_ap_uses_tied_thresholds_and_full_source_membership():
    import numpy as np
    row={'event_id':'e','n':4,'candidate_target_coverage':.75,'true_outside_candidates':1,
         'auprc_new':2/3,'predicted_asns_at05':'[1,2,3,4,9]', 'predicted_asns_tuned':'[1,9]'}
    failures=[]
    def check(ok,kind,**details):
        if not ok: failures.append(kind)
    payload=(np.array([1,2,3,4]),np.array([.1,.8,.8,.8]))
    module.verify_model_probabilities(row,payload,{1,9},{1,2,3,9},.9,check,'model.csv')
    assert failures==[]
    row['auprc_new']=5/6 # incorrect tie-breaking that ranks positives first
    module.verify_model_probabilities(row,payload,{1,9},{1,2,3,9},.9,check,'model.csv')
    assert 'model_probability_ap' in failures
