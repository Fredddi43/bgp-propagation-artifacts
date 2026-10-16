"""Assemble only finalized measurement and model outputs into a fresh data tree.

Historical exploratory outputs, raw archives, graph tensors and correction
backups are deliberately outside this release. This is an internal assembly
step; export_review_artifacts.py performs the subsequent anonymization.
"""
from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil


def auxiliary_index_sources(graph, audit, require_hash):
    """Retain every cohort index actually consumed by the auxiliary audit."""
    if audit.get("status") != "passed":
        raise ValueError("Auxiliary index inputs require a passed source audit")
    sources = {}
    for relative, digest in audit["source_sha256"].items():
        if not relative.endswith("/index.csv"):
            continue
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 4 or path.parts[0] != "tgn":
            raise ValueError(f"Invalid auxiliary cohort index: {relative}")
        source = graph / path
        require_hash(source, digest)
        sources[relative] = source
    return sources


def frozen_table_equivalence(left, right):
    """Permit only exact equality or a proved fill of redundant early counts.

    Training never consumed these four added scalar columns. Their original
    bytes remain frozen; all other decoded inputs must still match exactly.
    """
    import polars as pl
    columns = sorted(left.columns)
    if set(right.columns) != set(columns):
        raise ValueError("Frozen/released columns differ")
    left, right = left.select(columns).sort("event_id"), right.select(columns).sort("event_id")
    if left.equals(right):
        return {"decoded_tables_equal": True}
    allowed = {"asns_" + h: "set_" + h for h in ("d30s", "d1m", "d5m", "d15m")}
    remaining = [column for column in columns if column not in allowed]
    if not left.select(remaining).equals(right.select(remaining)):
        raise ValueError("Non-redundant frozen/released values differ")
    changes = {}
    for column, members in allowed.items():
        if column not in columns:
            continue
        if members not in columns:
            raise ValueError(f"Missing set for derived count: {column}")
        if left.filter(pl.col(column).is_not_null() & pl.col(column).ne_missing(pl.col(members).list.len())).height:
            raise ValueError(f"Non-null frozen count is incorrect: {column}")
        if right.filter(pl.col(column).ne_missing(pl.col(members).list.len())).height:
            raise ValueError(f"Released derived count is incorrect: {column}")
        count = int(left[column].ne_missing(right[column]).sum())
        if count:
            changes[column] = count
    if not changes:
        raise ValueError("Table difference is not a derived-count fill")
    return {"decoded_tables_equal": False, "all_other_columns_equal": True,
            "derived_count_materialization": changes}


def graph_boundary_evidence(run, model_manifest, auxiliary_manifest, input_plan, require_hash):
    """Require the complete consumed-input proof before accepting changed tables."""
    proof_path = run / "boundary-audit/graph-input-proof/report.json"
    proof = json.loads(proof_path.read_text())
    if proof.get("status") != "passed" or proof.get("failures"):
        raise ValueError("Graph boundary input equivalence failed")
    expected_outputs = set(model_manifest["model_tables"]) | set(auxiliary_manifest["auxiliary_files"])
    expected_cohorts = {tuple(cohort) for cohort in input_plan["cohorts"]}
    if (set(proof["model_tables"]) != set(model_manifest["model_tables"])
            or set(proof["auxiliary_files"]) != set(auxiliary_manifest["auxiliary_files"])
            or set(proof["dependency_closure"]) != expected_outputs
            or {tuple(row["cohort"]) for row in proof["cohorts"]} != expected_cohorts
            or len(proof["cohorts"]) != len(expected_cohorts)):
        raise ValueError("Graph boundary proof covers a different release population")
    covered = {f"tgn/{year}_{tag}/d{delta}s" for year, tag, delta in expected_cohorts}
    if any(not deps or not set(deps) <= covered for deps in proof["dependency_closure"].values()):
        raise ValueError("Graph boundary proof has incomplete dependencies")
    import polars as pl
    expected_indexes = {}
    for row in proof["cohorts"]:
        year, tag, delta = row["cohort"]
        index = (Path(proof["frozen_root"]) / f"tgn/{year}_{tag}/d{delta}s/index.csv").resolve()
        index_hash = proof.get("index_sha256", {}).get(str(index))
        if not index_hash:
            raise ValueError("Graph boundary proof omits its frozen index hash")
        require_hash(index, index_hash)
        ids = pl.read_csv(index)["event_id"]
        if ids.n_unique() != len(ids) or set(row["tensors"]) != set(ids):
            raise ValueError("Graph boundary tensor evidence is incomplete")
        if (tag.startswith("leak") or tag == "withdrawal") and set(row.get("collector_membership", {})) != set(ids):
            raise ValueError("Graph boundary collector evidence is incomplete")
        expected_indexes[str(index)] = index_hash
        if (row["status"] != "equivalent" or row["differences"]
                or row["selected_ids_before"] != row["selected_ids_after"]
                or row["evaluation_before_sha256"] != row["evaluation_after_sha256"]
                or any(not tensor["equal"] or tensor["fields"] for tensor in row["tensors"].values())
                or any(not member["equal"] or member["before_sha256"] != member["after_sha256"]
                       for member in row.get("collector_membership", {}).values())):
            raise ValueError("Graph boundary proof contains changed consumed inputs")
    if proof["index_sha256"] != expected_indexes:
        raise ValueError("Graph boundary index proof covers a different population")
    paths = [(Path(path), digest) for field in ("contract_sha256", "source_sha256")
             for path, digest in proof[field].items()]
    producer_root = Path(proof.get("producer_root", run / "code")).resolve()
    if not producer_root.is_relative_to(run.resolve()):
        raise ValueError("Graph boundary producer snapshot lies outside the correction run")
    paths.extend((producer_root / path, digest) for path, digest in proof["producer_sha256"].items())
    if any(not Path(path).resolve().is_relative_to(run.resolve()) for path in proof["contract_sha256"]):
        raise ValueError("Graph boundary contracts lie outside the correction run")
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda item: require_hash(*item), paths))
    bindings = proof["event_table_bindings"]
    for relative, sides in bindings.items():
        if not relative.startswith("eventset/") or not relative.endswith("/events.parquet"):
            raise ValueError("Unexpected graph boundary table binding")
        for side in ("before", "after"):
            path, digest = Path(sides[side]["path"]), sides[side]["sha256"]
            if proof["source_sha256"].get(str(path.resolve())) != digest:
                raise ValueError("Graph boundary table is absent from audited sources")
            require_hash(path, digest)
    require_hash(proof_path, hashlib.sha256(proof_path.read_bytes()).hexdigest())
    return proof_path, bindings


def assemble(run: Path, out: Path):
    verified_hashes = {}

    def require_hash(path: Path, expected: str):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Evidence changed after verification: {path}")
        if path in verified_hashes and verified_hashes[path] != expected:
            raise ValueError(f"Conflicting evidence hashes: {path}")
        verified_hashes[path] = expected

    for name in ("crossday-source-complete.json", "post-crossday-analyses-complete.json",
                 "primary-pairs-complete.json", "pch-correction-complete.json", "graph-final-models-complete.json",
                 "graph-final-auxiliary-complete.json", "graph-raw-targets-verified.json",
                 "nongraph-final-complete.json", "nongraph-release-complete.json", "nongraph-verification.json", "pch-final-source-verification.json",
                 "frontier-source-verification.json", "derived-count-fill-bridge.json",
                 "derived-count-fill-verification.json", "propagation-controls-verification.json",
                 "radar-agreement-verification.json", "full-publication-verification.json",
                 "boundary-source-verification.json", "boundary-input-bridge.json",
                 "boundary-input-verification.json", "boundary-audit/nongraph-input-equivalence.json", "withdrawal-baseline-revision.json",
                 "withdrawal-baseline-availability-audit.json", "withdrawal-baseline-verification.json"):
        if not (run / name).is_file():
            raise FileNotFoundError(f"Final source gate missing: {name}")
    model_manifest = json.loads((run / "graph-final-build/expected-verification.json").read_text())
    model_completion = json.loads((run / "graph-final-models-complete.json").read_text())
    graph = (run / model_completion.get("data_root", "graph-final-data")).resolve()
    if not graph.is_relative_to(run.resolve()):
        raise ValueError("Model completion names a data tree outside this run")
    expected_model_files = set(model_manifest["model_checkpoints"])
    probability_files = {target["probability_evidence"] for target in model_manifest.get("model_targets", {}).values()
                         if target.get("probability_evidence")}
    expected_model_files.update(probability_files)
    for relative in model_manifest["model_tables"]:
        prefix = relative.removesuffix("_test_per_event.csv")
        expected_model_files.update((relative, prefix + "_summary.json", prefix + "_correction_run.json"))
    if set(model_completion["sha256"]) != expected_model_files:
        raise ValueError("Model completion hashes cover a different result population")
    for relative, expected_hash in model_completion["sha256"].items():
        require_hash(graph / relative, expected_hash)
    source_publication = json.loads((run / "crossday-source-complete.json").read_text())
    repair_root = (run / source_publication["repair_root"]).resolve()
    if not repair_root.is_relative_to(run.resolve()):
        raise ValueError("Source publication names a repair tree outside this run")
    expected_source_tables = {f"eventset/{year}{suffix}/events.parquet"
                              for year in range(2022, 2027) for suffix in ("", "_leak", "_withdrawal")}
    if set(source_publication["event_tables_sha256"]) != expected_source_tables:
        raise ValueError("Source publication covers a different measurement population")
    for relative, expected_hash in source_publication["event_tables_sha256"].items():
        require_hash(run / "data" / relative, expected_hash)
    boundary_path = run / "boundary-source-verification.json"
    require_hash(boundary_path, source_publication["boundary_verification_sha256"])
    boundary_proof = json.loads(boundary_path.read_text())
    if (boundary_proof.get("status") != "passed"
            or boundary_proof.get("published_event_tables_sha256") != source_publication["event_tables_sha256"]):
        raise ValueError("Source publication lacks matching archive boundary evidence")
    publication_proof = json.loads((run / "full-publication-verification.json").read_text())
    if (publication_proof["status"] != "passed" or publication_proof["failures"]
            or publication_proof["repaired_rows"] != source_publication["events"]
            or publication_proof["published_event_tables_sha256"] != source_publication["event_tables_sha256"]):
        raise ValueError("Published source tables do not match the independently audited replay")
    for filename, field in (("crossday-source-complete.json", "source_gate_sha256"),
                            ("full-replay-invariants.json", "audit_sha256"),
                            (str(repair_root.relative_to(run.resolve()) / "input-changes.json"), "changes_sha256"),
                            ("followup-exclusions-all.json", "followup_exclusions_sha256")):
        require_hash(run / filename, publication_proof[field])
    expected_probability_files = {
        f"tgn/{year}_leak200/d{delta}s/_results/{model}_test_probs.pt"
        for year in (2024, 2025) for delta in (30, 60)
        for model in ("sage", "gat", "tgn", "dyrep")}
    if probability_files != expected_probability_files:
        raise ValueError("Main-ladder probability evidence covers a different population")
    raw_proof = json.loads((run / "graph-raw-targets-verified.json").read_text())
    for path, field in ((run / "graph-final-build/expected-verification.json", "manifest_sha256"),
                        (run / "graph-full-target-verification.json", "report_sha256")):
        require_hash(path, raw_proof[field])
    raw_report = json.loads((run / "graph-full-target-verification.json").read_text())
    if raw_report["failures"] or raw_proof["models"] != len(model_manifest["model_tables"]):
        raise ValueError("Raw target verification failed or has incomplete model coverage")
    if {record["file"] for record in raw_report["model_tables"]} != set(model_manifest["model_tables"]):
        raise ValueError("Raw target report does not cover the final model population")
    if {record["table"] for record in raw_report["event_tables"]} != set(model_manifest["event_tables"]):
        raise ValueError("Raw target report does not cover the final event population")
    for record in raw_report["event_tables"]:
        require_hash(run / "data/eventset" / record["table"] / "events.parquet", record["sha256"])
    # Early model waves use immutable copies. Final publication may reencode
    # those same tables or fill four redundant presentation counts; consumed
    # training/test inputs must remain exactly equal.
    import polars as pl
    input_equivalence = {}
    publications = sorted((graph / "_publications").glob("*.json"))
    input_plan = json.loads((run / "graph-final-build/manifest.json").read_text())
    frozen_tables = set()
    for year, tag, _delta in input_plan["cohorts"]:
        base = tag.partition("@")[0]
        family = "leak" if base.startswith("leak") else "" if base in ("rpkivalid", "rpkiinvalid", "") else base
        frozen_tables.add(str(year) + ("_" + family if family else ""))
    if {path.stem for path in publications} != frozen_tables:
        raise ValueError("Frozen model publications cover a different input cohort population")
    auxiliary_manifest = json.loads((run / "graph-final-build/expected-auxiliary.json").read_text())
    graph_boundary_path, graph_boundary_bindings = graph_boundary_evidence(
        run, model_manifest, auxiliary_manifest, input_plan, require_hash)
    for publication in publications:
        frozen = json.loads(publication.read_text())
        for filename, expected_hash in frozen["table_files"].items():
            relative = Path("eventset") / frozen["table"] / filename
            source, released = graph / relative, run / "data" / relative
            require_hash(source, expected_hash)
            left, right = pl.read_parquet(source), pl.read_parquet(released)
            try:
                equivalence = frozen_table_equivalence(left, right)
            except ValueError as error:
                binding = graph_boundary_bindings.get(str(relative))
                if not binding or binding["before"]["sha256"] != expected_hash:
                    raise ValueError(f"Final publication differs from frozen model input: {relative}: {error}") from error
                candidate = pl.read_parquet(binding["after"]["path"])
                final_equivalence = frozen_table_equivalence(candidate, right)
                equivalence = {"decoded_tables_equal": False,
                    "consumed_inputs_equal": True,
                    "boundary_proof_sha256": verified_hashes[graph_boundary_path],
                    "candidate_sha256": binding["after"]["sha256"],
                    "candidate_to_final": final_equivalence}
            require_hash(released, hashlib.sha256(released.read_bytes()).hexdigest())
            if verified_hashes[released] != expected_hash:
                input_equivalence[str(relative)] = {"frozen_sha256": expected_hash,
                    "released_sha256": verified_hashes[released], **equivalence}
    for record in raw_report["model_tables"]:
        source = graph / record["file"]
        require_hash(source, record["sha256"])
        probability = model_manifest["model_targets"][record["file"]].get("probability_evidence")
        if record.get("probability_evidence") != probability:
            raise ValueError(f"Raw model proof names different probability evidence: {record['file']}")
        if probability:
            require_hash(graph / probability, record["probability_sha256"])
    pch_proof = json.loads((run / "pch-final-source-verification.json").read_text())
    if pch_proof["passed"] is not True:
        raise ValueError("Final PCH source verification failed")
    require_hash(run / "crossday-source-complete.json", pch_proof["source_gate_sha256"])
    pch_inputs = dict(pch_proof["public_table_content_sha256"])
    pch_inputs.update({f"eventset/2024_{tag}/events.parquet": digest for tag, digest in pch_proof["pch_table_content_sha256"].items()})
    if set(pch_inputs) != {f"eventset/{name}/events.parquet" for name in ("2024", "2024_leak", "2024_leakpch", "2024_pchorigin")}:
        raise ValueError("Final PCH verification covers a different population")
    for relative, expected_hash in pch_inputs.items():
        source = run / "data" / relative
        table = pl.read_parquet(source)
        actual = hashlib.sha256(table.sort("event_id").select(sorted(table.columns)).write_json().encode()).hexdigest()
        if actual != expected_hash:
            raise ValueError(f"PCH comparison source changed after verification: {relative}")
        require_hash(source, hashlib.sha256(source.read_bytes()).hexdigest())
    auxiliary_manifest = json.loads((run / "graph-final-build/expected-auxiliary.json").read_text())
    nongraph_manifest = json.loads((run / "expected-nongraph.json").read_text())
    nongraph_release = json.loads((run / "nongraph-release-complete.json").read_text())
    nongraph_root = (run / nongraph_release["data_root"]).resolve()
    if nongraph_release["status"] != "complete" or not nongraph_root.is_relative_to(run.resolve()):
        raise ValueError("Invalid final non-graph release view")
    require_hash(run / "nongraph-final-complete.json", nongraph_release["original_completion_sha256"])
    require_hash(run / "expected-nongraph.json", nongraph_release["expected_manifest_sha256"])
    for relative, digest in nongraph_release["selected_artifact_sha256"].items():
        require_hash(nongraph_root / relative, digest)
    nongraph_proof = json.loads((run / "nongraph-verification.json").read_text())
    if nongraph_proof["failures"] or len(nongraph_proof["tables"]) != len(nongraph_manifest["nongraph_tables"]):
        raise ValueError("Non-graph verification failed or has incomplete coverage")
    require_hash(run / "expected-nongraph.json", nongraph_proof["manifest_sha256"])
    if {record["summary"] for record in nongraph_proof["tables"]} != {record["summary"] for record in nongraph_manifest["nongraph_tables"]}:
        raise ValueError("Non-graph verification covers a different result population")
    bridge_paths = {"manifest": "analysis/derived-count-fill-bridge.json",
                    "verification": "analysis/derived-count-fill-verification.json"}
    if nongraph_proof.get("derived_count_bridge") != bridge_paths:
        raise ValueError("Non-graph proof predates derived-count input verification")
    boundary_paths = {"manifest": "analysis/boundary-input-bridge.json",
                      "verification": "analysis/boundary-input-verification.json",
                      "equivalence": "analysis/nongraph-boundary-input-equivalence.json"}
    boundary_sources = {
        boundary_paths["manifest"]: run / "boundary-input-bridge.json",
        boundary_paths["verification"]: run / "boundary-input-verification.json",
        boundary_paths["equivalence"]: run / "boundary-audit/nongraph-input-equivalence.json"}
    if nongraph_proof.get("boundary_input_bridge") != boundary_paths:
        raise ValueError("Non-graph proof lacks the archive boundary input bridge")
    floor_spec = next(spec for spec in nongraph_manifest["nongraph_tables"]
                      if spec["kind"] == "prefix_floor" and spec["event_table"] == "2025_leak")
    release_floor = nongraph_root / floor_spec["rows"].removeprefix("analysis/nongraph/")
    release_floor_relative = "eventset/2025_leak/prefix_floor.parquet"
    from verify_boundary_inputs import verify as verify_boundary_inputs
    boundary_inputs = verify_boundary_inputs(run / "data", boundary_sources[boundary_paths["manifest"]],
        boundary_sources[boundary_paths["equivalence"]], boundary_sources[boundary_paths["verification"]],
        floor_path=release_floor)
    cascade_bootstrap = nongraph_manifest.get("cascade_bootstrap")
    if (cascade_bootstrap != "analysis/nongraph-cascade-bootstrap.json"
            or nongraph_proof.get("cascade_bootstrap") != cascade_bootstrap):
        raise ValueError("Non-graph proof lacks the paired cascade comparison")
    for relative, expected_hash in nongraph_proof["file_sha256"].items():
        if relative in boundary_sources:
            source = boundary_sources[relative]
        elif relative == release_floor_relative:
            source = release_floor
        elif relative in {*bridge_paths.values(), cascade_bootstrap, "analysis/nongraph-release-complete.json"}:
            source = run / Path(relative).name
        elif relative.startswith("analysis/nongraph/"):
            source = nongraph_root / relative.removeprefix("analysis/nongraph/")
        else:
            source = run / "data" / relative
        require_hash(source, expected_hash)
    auxiliary_proof = json.loads((run / "graph-final-auxiliary-complete.json").read_text())
    if set(auxiliary_proof["sha256"]) != set(auxiliary_manifest["auxiliary_files"]):
        raise ValueError("Auxiliary completion proof covers a different release population")
    for relative, expected_hash in auxiliary_proof["sha256"].items():
        require_hash(graph / relative, expected_hash)
    nongraph = json.loads((run / "nongraph-plan.json").read_text())
    for task in nongraph:
        folder = nongraph_root / str(task["year"]) / f"{task['index']:03d}_{task['kind']}"
        if not (folder / "complete.json").is_file():
            raise FileNotFoundError(f"Non-graph task incomplete: {folder.name}")
    data = run / "data"
    withdrawal_paths = {"revision": "analysis/withdrawal-baseline-revision.json",
                        "availability": "analysis/withdrawal-baseline-availability-audit.json",
                        "verification": "analysis/withdrawal-baseline-verification.json"}
    withdrawal_revision = json.loads((run / "withdrawal-baseline-revision.json").read_text())
    withdrawal_root = (run / withdrawal_revision["data_root"]).resolve()
    if withdrawal_revision["status"] != "complete" or not withdrawal_root.is_relative_to(run.resolve()):
        raise ValueError("Invalid withdrawal baseline revision")
    require_hash(run / "crossday-source-complete.json", withdrawal_revision["source_gate_sha256"])
    require_hash(run / "withdrawal-baseline-availability-audit.json", withdrawal_revision["availability_audit_sha256"])
    expected_withdrawal_tables = {f"eventset/{year}_withdrawal/events.parquet" for year in range(2022, 2027)}
    if {record["path"] for record in withdrawal_revision["tables"]} != expected_withdrawal_tables:
        raise ValueError("Withdrawal revision covers a different event population")
    for record in withdrawal_revision["tables"]:
        require_hash(data / record["path"], record["before_sha256"])
        require_hash(withdrawal_root / record["path"], record["after_sha256"])
        # 2024 is consumed by graph transfer evaluation and the count bridge.
        if record["year"] == 2024 and (not record["unchanged_bytes"] or record["changes"]
                                       or record["before_sha256"] != record["after_sha256"]):
            raise ValueError("Withdrawal baseline revision changes frozen graph evaluation")
    withdrawal_files = withdrawal_revision["selected_artifact_sha256"]
    for relative, digest in withdrawal_files.items():
        if Path(relative).parent.as_posix() not in {str(Path(path).parent) for path in expected_withdrawal_tables}:
            raise ValueError("Withdrawal revision includes an unexpected destination")
        require_hash(withdrawal_root / relative, digest)
    from verify_withdrawal_baselines import verify as verify_withdrawal_baselines
    withdrawal_proof = verify_withdrawal_baselines(withdrawal_root, *(run / Path(withdrawal_paths[key]).name
                                                 for key in ("revision", "availability", "verification")))
    if withdrawal_proof["status"] != "passed" or withdrawal_proof["failures"]:
        raise ValueError("Withdrawal baseline source verification failed")
    copies = {}
    manifest = {**model_manifest, "event_tables": [], "pair_tables": [], "frontier_tables": [], "event_selections": {},
                "nongraph_tables": nongraph_manifest["nongraph_tables"],
                "cascade_bootstrap": cascade_bootstrap,
                "required_files": list(model_manifest.get("required_files", [])) + nongraph_manifest["required_files"]}

    def add(source: Path, relative: str | Path):
        relative = str(relative)
        if relative in withdrawal_files and source == data / relative:
            source = withdrawal_root / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        if relative in copies and copies[relative] != source:
            raise ValueError(f"Conflicting release destinations: {relative}")
        if source not in verified_hashes:
            verified_hashes[source] = hashlib.sha256(source.read_bytes()).hexdigest()
        copies[relative] = source

    for relative in withdrawal_paths.values():
        add(run / Path(relative).name, relative)
        manifest["required_files"].append(relative)
    for relative in withdrawal_files:
        add(withdrawal_root / relative, relative)
        manifest["required_files"].append(relative)
    manifest["withdrawal_baseline"] = withdrawal_paths
    for relative, source in boundary_sources.items():
        add(source, relative)
        manifest["required_files"].append(relative)
    for relative, digest in boundary_inputs["proof"]["source_sha256"].items():
        source = release_floor if relative == release_floor_relative else data / relative
        require_hash(source, digest)
        add(source, relative)
        manifest["required_files"].append(relative)
    manifest["boundary_input_bridge"] = boundary_paths

    from verify_derived_counts import verify_bridge
    bridge_path = run / "derived-count-fill-bridge.json"
    bridge_proof_path = run / "derived-count-fill-verification.json"
    checked_bridge = verify_bridge(data, bridge_path, bridge_proof_path,
                                   boundary_tables=boundary_inputs["restored_tables"])
    expected_bridge_tables = {f"eventset/{name}/events.parquet" for name in
                             ("2023_leak", "2024_leak", "2025_leak", "2024", "2024_withdrawal")}
    if {record["path"] for record in checked_bridge["tables"]} != expected_bridge_tables:
        raise ValueError("Derived-count bridge covers a different input population")
    bridge_proof = json.loads(bridge_proof_path.read_text())
    for relative, expected_hash in bridge_proof["original_source_sha256"].items():
        require_hash(run / relative, expected_hash)
    for relative, expected_hash in bridge_proof["source_sha256"].items():
        require_hash(data / relative, expected_hash)
        add(data / relative, relative)
        manifest["required_files"].append(relative)
    require_hash(bridge_path, bridge_proof["evidence_sha256"][bridge_paths["manifest"]])
    for relative in bridge_paths.values():
        add(run / Path(relative).name, relative)
        manifest["required_files"].append(relative)
    manifest["derived_count_bridge"] = bridge_paths
    add(run / Path(cascade_bootstrap).name, cascade_bootstrap)

    def event_files(folder: str, names):
        for name in names:
            add(data / "eventset" / folder / name, Path("eventset") / folder / name)

    basic = ("events.parquet", "summary.json", "persistence_train.csv", "persistence_test.csv")
    durations = ("durations.parquet", "per_vp_duration.json", "persistence_per_vp_test.csv",
                 "persistence_by_duration_test.csv")
    for year in range(2022, 2027):
        for tag in ("", "_leak", "_withdrawal", "_hijack_first_transition", "_recovery_first_transition"):
            folder = str(year) + tag
            manifest["event_tables"].append(folder)
            if "first_transition" in tag:
                manifest["event_selections"][folder] = {
                    "file": f"inventory/{year}/recovery_replay_selection.parquet",
                    "key": "hijack_id" if tag.startswith("_hijack") else "event_id"}
            else:
                relative = f"verification/frozen-event-ids/{folder}.parquet"
                add(run / relative, relative)
                manifest["event_selections"][folder] = {"file": relative, "key": "event_id"}
            event_files(folder, basic)
            if "first_transition" in tag:
                event_files(folder, ("transition_coverage.json", "transition_source_manifest.json"))
            else:
                event_files(folder, durations)
            if tag == "_recovery_first_transition":
                for pattern in ("pairs*.parquet", "pairs_summary*.json", "overlap_summary*.json", "rov_summary*.json"):
                    for source in sorted((data / "eventset" / folder).glob(pattern)):
                        relative = source.relative_to(data)
                        add(source, relative)
                        if source.name.startswith("pairs") and source.suffix == ".parquet":
                            manifest["pair_tables"].append(str(relative))
        folder = str(year)
        event_files(folder, ("rpki_validity.parquet", "rpki_validity_summary.json",
                            "rpki_validity_summary_labelled.json", "later_validity.json", "later_validity.parquet"))
        suffix = "" if year == 2022 else "_labelled"
        event_files(folder, (f"per_vp_by_validity{suffix}.json", f"persistence_per_vp_by_validity_test{suffix}.csv"))
        for source in sorted((data / "eventset" / folder).glob("rov_frontier*.json")):
            for member in (source, source.with_suffix(".parquet")):
                add(member, member.relative_to(data))
            manifest["frontier_tables"].append(str(source.relative_to(data)))
        if year in (2024, 2025):
            event_files(folder, ("radar_rpki_agreement.json", "radar_rpki_agreement.parquet"))
        inventory = data / "inventory" / str(year)
        for prefix in ("", "leak_", "withdrawal_", "recovery_"):
            for ending in ("replay_manifest.tsv", "replay_selection.parquet"):
                source = inventory / (prefix + ending)
                add(source, source.relative_to(data))

    for folder in ("2024_leakpch", "2024_pchorigin"):
        manifest["event_tables"].append(folder)
        relative = f"verification/frozen-event-ids/{folder}.parquet"
        add(run / relative, relative)
        manifest["event_selections"][folder] = {"file": relative, "key": "event_id"}
        event_files(folder, (*basic, "pch_vs_public.json", "pch_vs_public.parquet", "pch_correction_scope.json"))
    add(run / "verification/frozen-event-ids/provenance.json", "verification/frozen-event-ids/provenance.json")
    for relative in model_manifest["model_tables"]:
        add(graph / relative, relative)
        prefix = relative.removesuffix("_test_per_event.csv")
        for ending in ("_summary.json", "_correction_run.json"):
            add(graph / (prefix + ending), prefix + ending)
    for relative in model_manifest["model_checkpoints"]:
        add(graph / relative, relative)
        manifest["required_files"].append(relative)
    for relative in sorted(probability_files):
        add(graph / relative, relative)
        manifest["required_files"].append(relative)
    for contract in model_manifest["model_cohorts"].values():
        for relative in contract["index_tables"]:
            add(graph / relative, relative)
    auxiliary_audit = json.loads((graph / "analysis/graph_auxiliary_verification.json").read_text())
    for relative, source in auxiliary_index_sources(graph, auxiliary_audit, require_hash).items():
        auxiliary_only = relative not in copies
        add(source, relative)
        if auxiliary_only:
            manifest["required_files"].append(relative)
    for relative in auxiliary_manifest["auxiliary_files"]:
        add(graph / relative, relative)
        manifest["required_files"].append(relative)
    auxiliary_contract = "analysis/expected-graph-auxiliary.json"
    add(run / "graph-final-build/expected-auxiliary.json", auxiliary_contract)
    manifest["required_files"].append(auxiliary_contract)
    manifest["auxiliary_verification"] = auxiliary_contract
    # Namespace these results because alpha sensitivities intentionally have
    # separate task directories even when their legacy filenames are identical.
    add(run / "nongraph-plan.json", "analysis/nongraph-plan.json")
    manifest["required_files"].append("analysis/nongraph-plan.json")
    for relative in sorted(nongraph_release["selected_artifact_sha256"]):
        add(nongraph_root / relative, Path("analysis/nongraph") / relative)
    # Independent verification sidecars are produced after the immutable model
    # completion and are bound by the audit report, not by producer hashes.
    for relative, digest in nongraph_proof["file_sha256"].items():
        if relative.startswith("analysis/nongraph/"):
            source = nongraph_root / relative.removeprefix("analysis/nongraph/")
            require_hash(source, digest)
            add(source, relative)
            manifest["required_files"].append(relative)
    release_relative = "analysis/nongraph-release-complete.json"
    add(run / "nongraph-release-complete.json", release_relative)
    manifest["required_files"].append(release_relative)
    manifest["nongraph_release"] = release_relative
    for source in (data / "rpki").glob("beacon_*.parquet"):
        add(source, source.relative_to(data))
    for source in (data / "rpki/beacon_reach_scan").glob("*.parquet"):
        add(source, source.relative_to(data))
    beacon_delay = "2024-06-10_2024-06-16"
    for name in ("cycles.parquet", "per_vp_summary.parquet", "summary.json", "provenance.json"):
        relative = f"rpki/beacon-delay/{beacon_delay}/{name}"
        add(run / "beacon-delay-final" / beacon_delay / name, relative)
        manifest["required_files"].append(relative)
    manifest["beacon_delay_tables"] = [f"rpki/beacon-delay/{beacon_delay}/summary.json"]

    paired_frontier = json.loads((run / "expected-paired-frontier.json").read_text())
    frontier_proof = json.loads((run / "frontier-source-verification.json").read_text())
    if frontier_proof["status"] != "passed" or frontier_proof["mode"] != "private_source_audit":
        raise ValueError("Frontier source verification failed")
    if {record["file"] for record in frontier_proof["variants"]} != set(paired_frontier["frontier_tables"]):
        raise ValueError("Frontier source verification covers a different population")
    for field in ("source_sha256", "evidence_sha256"):
        for relative, expected_hash in frontier_proof[field].items():
            require_hash(data / relative, expected_hash)
    frontier_audit = "analysis/frontier-source-verification.json"
    add(run / "frontier-source-verification.json", frontier_audit)
    manifest["required_files"].append(frontier_audit)
    manifest["frontier_source_verification"] = frontier_audit
    controls_proof = json.loads((run / "propagation-controls-verification.json").read_text())
    if (controls_proof["status"] != "passed" or controls_proof["mode"] != "private_source_audit"
            or controls_proof["years"] != list(range(2022, 2027))):
        raise ValueError("Propagation control verification failed or has incomplete coverage")
    for field in ("source_sha256", "evidence_sha256"):
        for relative, expected_hash in controls_proof[field].items():
            require_hash(data / relative, expected_hash)
    controls_audit = "analysis/propagation-controls-verification.json"
    add(run / "propagation-controls-verification.json", controls_audit)
    manifest["required_files"].append(controls_audit)
    manifest["propagation_controls_verification"] = controls_audit
    radar_proof = json.loads((run / "radar-agreement-verification.json").read_text())
    expected_radar_outputs = {
        "analysis/nongraph/2024/097_radar_prefix_agreement/cloudflare_leaks_prefixes_reconstructed",
        "eventset/2024/radar_rpki_agreement", "eventset/2025/radar_rpki_agreement"}
    if (radar_proof["status"] != "passed" or radar_proof["mode"] != "private_source_audit"
            or set(radar_proof["outputs"]) != expected_radar_outputs):
        raise ValueError("Radar agreement verification failed or has incomplete coverage")
    for field in ("source_sha256", "evidence_sha256"):
        for relative, expected_hash in radar_proof[field].items():
            source = (nongraph_root / relative.removeprefix("analysis/nongraph/")
                      if relative.startswith("analysis/nongraph/") else data / relative)
            require_hash(source, expected_hash)
    radar_audit = "analysis/radar-agreement-verification.json"
    add(run / "radar-agreement-verification.json", radar_audit)
    manifest["required_files"].append(radar_audit)
    manifest["radar_agreement_verification"] = radar_audit
    for category in ("pair_tables", "frontier_tables"):
        if set(manifest[category]) != set(paired_frontier[category]):
            raise ValueError(f"Missing or unexpected finalized variants: {category}")

    manifest["required_files"] = sorted(set(manifest["required_files"]))
    missing = set(manifest["required_files"]) - copies.keys()
    if missing:
        raise ValueError(f"Required files absent from assembly: {sorted(missing)}")

    public_root = run / "public-verification-targets"
    targets = json.loads((public_root / "expected-verification.json").read_text())
    for key, value in model_manifest.items():
        if key not in {"model_targets", "file_sha256", "required_files"} and targets.get(key) != value:
            raise ValueError(f"Public target contract is stale: {key}")
    if set(targets["model_tables"]) != set(manifest["model_tables"]):
        raise ValueError("Public targets and final models name different populations")
    public = copy.deepcopy(manifest)
    for model, contract in manifest["model_targets"].items():
        replacement = targets["model_targets"][model]
        if contract.get("membership_source"):
            if not replacement.get("target_table") or replacement.get("membership_source"):
                raise ValueError(f"Missing public collector target: {model}")
            invariant = {key: value for key, value in contract.items()
                         if key not in {"membership_source", "event_table", "event_tables"}}
            replaced = {key: value for key, value in replacement.items() if key != "target_table"}
            if invariant != replaced:
                raise ValueError(f"Public target changed model scoring requirements: {model}")
            public["model_targets"][model] = replacement
        elif replacement != contract:
            raise ValueError(f"Unexpected public target change: {model}")
    public["file_sha256"] = targets["file_sha256"]
    target_provenance = json.loads((public_root / "verification/collector-targets/provenance.json").read_text())
    for relative, expected_hash in target_provenance["input_sha256"].items():
        source = (graph if relative.startswith("tgn/") else data) / relative
        require_hash(source, expected_hash)
    for relative, expected_hash in public["file_sha256"].items():
        source = public_root / relative
        require_hash(source, expected_hash)
        add(source, relative)
    public["required_files"] = sorted(set(public["required_files"]) | public["file_sha256"].keys())

    out.mkdir(parents=True, exist_ok=False)
    files = {}
    for relative, source in sorted(copies.items()):
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
        if copied_hash != verified_hashes[source]:
            raise ValueError(f"Source changed during assembly: {relative}")
        files[relative] = {"bytes": destination.stat().st_size, "sha256": copied_hash}
    auxiliary_relative = "analysis/graph_auxiliary_verification.json"
    auxiliary_path = out / auxiliary_relative
    audit = json.loads(auxiliary_path.read_text())
    original_sources = dict(audit["source_sha256"])
    for relative, expected_hash in original_sources.items():
        if relative not in files or files[relative]["sha256"] == expected_hash:
            continue
        equivalence = input_equivalence.get(relative)
        if not equivalence or equivalence["frozen_sha256"] != expected_hash:
            raise ValueError(f"Auxiliary source differs without decoded equivalence proof: {relative}")
        audit["source_sha256"][relative] = files[relative]["sha256"]
    if audit["source_sha256"] != original_sources:
        audit["pre_assembly_source_sha256"] = original_sources
        audit["assembly_input_equivalence"] = input_equivalence
        auxiliary_path.write_text(json.dumps(audit, indent=2) + "\n")
        files[auxiliary_relative] = {"bytes": auxiliary_path.stat().st_size,
                                    "sha256": hashlib.sha256(auxiliary_path.read_bytes()).hexdigest()}
    (out / "expected-verification-full.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "expected-verification.json").write_text(json.dumps(public, indent=2) + "\n")
    (out / "assembly-manifest.json").write_text(json.dumps(files, indent=2) + "\n")
    print(json.dumps({"files": len(files), "bytes": sum(x["bytes"] for x in files.values()),
                      "event_tables": len(manifest["event_tables"]), "models": len(manifest["model_tables"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    assemble(args.run, args.out)
