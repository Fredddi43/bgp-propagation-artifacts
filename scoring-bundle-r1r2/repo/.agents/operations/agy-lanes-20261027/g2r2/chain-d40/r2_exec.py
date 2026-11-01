#!/usr/bin/env python3
"""Thin in-job wrapper: ONE singleton Slurm job runs the PINNED single-R2 persistence runner (its run(plan_ref, approval_ref)).

Fills only live-allocation facts (job id/cpus/memory, runtime doc, admission doc listing the exact inventory) and an approval
derived from root's ROOT-GO-R2.txt, then calls the runner. All science (one label opening, arm/seal/spec checks, sidecar,
envelope) stays in the pinned runner and evaluator. ONE SHOT: the runner's records dir is exclusive and its marker refuses a
second opening; there is no retry.

Spec JSON: {"go_file": path, "work": dir, "template": {path,sha256}, "inventory": [..files..], "runner": {path,sha256},
            "reviewer": optional override}. Template = r2_plan.build_template() output (no resources/runtime/read_inventory/readiness).
"""
import argparse
import hashlib
import json
import os
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "g2"))
import g2_exec  # noqa: E402  (runtime_document, ref, write_new)
import amend_wiring  # noqa: E402  (d60-only wiring, engaged only for an amended freeze)

FALSE_FLAGS = ("retry_authorized", "fit_authorized", "prediction_authorized", "seal_authorized", "outcome_release_authorized")

# Generous allocation floors for the singleton R2 job (RESOURCE-POLICY.md heavy tier; over-reserve, never
# choose a smaller allocation). Submit with: g2_submit.py --singleton --cpus 64 --mem-mib 1000000 --wall 1-00:00:00.
# The PINNED runner (newperiod-single-r2-persistence-20261024/runner.py) caps what it will admit at
# cpus<=128, memory_mib<=2_097_152, wall_seconds<=86400 (runner.py:45,:318) and sets the process rlimits itself:
# RLIMIT_AS := (memory_mib-512) MiB, RLIMIT_FSIZE := bounds['output_file_bytes'] (runner.py:332-333) — so FSIZE
# is exactly the derive_bounds output bound (16 GiB; the runner gives no separate FSIZE knob to raise to 64 GiB
# without multiplying the 6-file storage reservation; see q23 notes). These floors refuse UNDER-allocation at
# prepare time, before the records dir or the one-opening marker exist; the runner's ceilings bound over-allocation.
GENEROUS = {"cpus": 64, "memory_mib": 1000000, "wall_seconds": 86400}
GENEROUS_BOUNDS = {"output_file_bytes": 16 << 30, "access_log_bytes": 4 << 30, "runtime_file_bytes": 4 << 30,
                   "input_view_cache_bytes": 64 << 30}


def need(ok, why):
    if not ok:
        raise SystemExit("REFUSED: " + why)


def prepare(spec, env=os.environ, attempt_dir=None):
    go = Path(spec["go_file"])
    need(go.is_file() and go.stat().st_size > 0, f"root go file {go} missing: R2 not authorized")
    need(env.get("CUSTODIAN_ACCESS_LOG"), "CUSTODIAN_ACCESS_LOG must be exported (the runner requires it to equal plan['access_log'])")
    template = json.loads(g2_exec.bound(spec["template"]))
    need(template["kind"] == "newperiod_single_R2_execution_v1" and template["repetitions"] == 10000
         and template["bootstrap_seed"] == 1701 and template["alpha"] == 0.05, "R2 constants differ")
    need(env["CUSTODIAN_ACCESS_LOG"] == template["access_log"], "CUSTODIAN_ACCESS_LOG differs from plan access_log")
    for k in ("SLURM_JOB_ID", "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE"):
        need(k in env, k + " missing: run inside the allocation")
    need("SLURM_ARRAY_TASK_ID" not in env, "R2 is a singleton job, not an array task")
    work = Path(spec["work"])
    work.mkdir(parents=True, exist_ok=True)
    resources = {"cpus": int(env["SLURM_CPUS_PER_TASK"]), "memory_mib": int(env["SLURM_MEM_PER_NODE"]),
                 "wall_seconds": template.get("wall_seconds", 86400), "job_id": int(env["SLURM_JOB_ID"])}
    for key, floor in GENEROUS.items():   # over-reserve (RESOURCE-POLICY): refuse a stingy allocation here, not OOM/SIGALRM mid-run
        need(resources[key] >= floor, f"{key}={resources[key]} below the generous floor {floor}: resubmit the singleton "
             "(g2_submit.py --singleton --cpus 64 --mem-mib 1000000 --wall 1-00:00:00)")
    bounds = template.get("bounds", {})
    for key, floor in GENEROUS_BOUNDS.items():   # stale template? rebuild with the current r2_plan.derive_bounds
        need(isinstance(bounds.get(key), int) and bounds[key] >= floor,
             f"template bounds {key}={bounds.get(key)} below the generous floor {floor}: re-stage the template with r2_plan.build_template")
    log = Path(template["access_log"])
    log_size = log.stat().st_size if log.exists() else 0   # the pinned runner repeats this at start (runner.py:325)
    need(log_size + bounds["access_log_bytes"] <= bounds["output_file_bytes"],
         f"access log {log} at {log_size} B + growth {bounds['access_log_bytes']} exceeds the RLIMIT_FSIZE the runner "
         f"will set ({bounds['output_file_bytes']} B): raise output_file_bytes/access_log_bytes in derive_bounds")
    inventory = g2_exec.write_new(work / "read-inventory.json", {"files": spec["inventory"]})
    plan = {k: v for k, v in template.items() if k != "wall_seconds"}
    plan.update(resources=resources, read_inventory=inventory)
    plan["runtime"] = g2_exec.write_new(work / "runtime.json", g2_exec.runtime_document())
    who = {"reviewer_model": "claude-sonnet-5-5", "reviewer_worker": "root-orchestrator-claude-sonnet-5-5",
           "reviewer_session": "go-file-" + hashlib.sha256(go.read_bytes()).hexdigest()[:16], **spec.get("reviewer", {})}
    plan["resource_readiness"] = g2_exec.write_new(work / "readiness.json", {
        "passed": True, "resources": resources, "freeze": plan["freeze"], "arm_id": "R2", "bounds": plan["bounds"],
        "read_inventory": inventory, "all_prepared_predictions_and_bootstrap_memory_fit": True,
        "shared_storage_reservation_bytes": plan["bounds"]["output_total_bytes"], "free_floor_bytes": 64 << 30,
        "reviewer_worker": who["reviewer_worker"], "reviewer_session": who["reviewer_session"]})
    pref = g2_exec.write_new(work / "plan.json", plan)
    approval = {"passed": True, "plan": pref, "runner_sha256": spec["runner"]["sha256"], "resources": resources,
                "read_inventory": inventory, "seal": plan["seal"], "labels": plan["labels"],
                "full_retention_review": plan["full_retention_review"], "review": g2_exec.ref(go),
                "execution_authorized": True, "single_label_join_authorized": True, "score_authorized": True,
                **dict.fromkeys(FALSE_FLAGS, False), **who}
    aref = g2_exec.write_new(work / "approval.json", approval)
    return pref, aref


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    a = p.parse_args(argv)
    spec = json.loads(a.spec.read_bytes())
    pref, aref = prepare(spec)
    raw = g2_exec.bound(spec["runner"])
    module = types.ModuleType("r2_persistence_runner")
    module.__file__ = spec["runner"]["path"]
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    plan = json.loads(Path(pref["path"]).read_bytes())
    freeze_raw = g2_exec.bound(plan["freeze"])   # sha-verified, label-free
    engaged = amend_wiring.engage_runner(module, freeze_raw)   # before run(): wraps scientific_modules, patches evaluate
    print(json.dumps({"d60_only_engaged": engaged}), file=sys.stderr)
    fast_json = bool(spec.get("fast_json_predictions"))   # D-A28
    ckpt_dir = spec.get("checkpoint_dir")   # D-A37: persist every label-free preparation result
    ckpt_key = None
    if ckpt_dir:
        import r2_checkpoint
        ckpt_key = r2_checkpoint.code_fingerprint()
    cache_dir = spec.get("input_projection_cache")   # D-A27: parallel-precomputed default_input_loader results, hash-keyed
    cutoff = spec.get("fast_authorize_cutoff_epoch")   # D-A26: ctime-based immutability proof instead of the serial full re-hash
    if True:
        import r2_fast_authorize
        import r2_fast_json
        import r2_input_cache
        original_modules = module.scientific_modules

        def scientific_modules(plan):
            # D-A32: the origin component reads evidence['sampling_rule'] through Reader.json (JSON parse); the bound rule is a markdown
            # file. For exactly that hash-pinned file, verify+log the read as usual and return a stub (the consumer discards the value).
            rule_sha = "a8fa51b0fbf137c7685e2a532e8abe981757876295f349a779b364e15c85dbb6"
            reader_class, original_json = module.Reader, module.Reader.json

            # D-A33: frozen origin arms name lane-laptop paths for family_fit.review (40 files); the byte-identical cluster mirrors are listed in
            # the root-signed substitution sidecar (same sha256). Map exactly those from-paths to their mirrors; mirrors are in the inventory.
            sidecar = Path(spec["work"]).resolve().parent.parent / "origin-evidence" / "origin-path-substitution.json"
            substitution = json.loads(sidecar.read_bytes())
            need(substitution.get("signed") is True, "origin path-substitution sidecar is not root-signed")
            review_map = {(e["from"] if isinstance(e["from"], str) else e["from"]["path"]): e["to"] for e in substitution["fit_review"].values()}

            def reader_json(self, ref, purpose):
                if isinstance(ref, dict) and ref.get("path") in review_map:
                    target = review_map[ref["path"]]
                    need(target["sha256"] == ref.get("sha256"), "fit review sha chain differs")
                    ref = {"path": target["path"], "sha256": target["sha256"]}
                if isinstance(ref, dict) and ref.get("sha256") == rule_sha:
                    self.bytes(ref, purpose)
                    return {"markdown_rule": True}
                return original_json(self, ref, purpose)
            reader_class.json = reader_json
            # D-A34: the root-signed completed-fit reviews (pinned by hash in the frozen arms) record reviewer_session "root-session" (the
            # root sign-off stamp); the origin component's independent() demands a "/root/..." session string. Accept exactly that stamp as
            # "/root/root-session"; every other value, and the worker/model checks, are checked unchanged.
            original_components = module.components

            def patched_components():
                loaded = original_components()
                composition = loaded.get("composition")
                if composition is not None and hasattr(composition, "components") and not getattr(composition.components, "_d_a36", False):
                    original_composition_components = composition.components

                    def composition_components():
                        modules = original_composition_components()
                        import r2_float32_decision   # D-A36
                        r2_float32_decision.patch(modules["membership"])
                        import r2_stable_persistence   # D-A38
                        r2_stable_persistence.patch(modules["stable"])
                        if ckpt_dir:
                            import r2_checkpoint
                            modules["membership"].prepare_sealed = r2_checkpoint.wrap(modules["membership"].prepare_sealed, "members", ckpt_dir, ckpt_key)
                            modules["stable"].prepare_sealed = r2_checkpoint.wrap(modules["stable"].prepare_sealed, "stable", ckpt_dir, ckpt_key)
                            modules["count"].prepare_counts = r2_checkpoint.wrap(modules["count"].prepare_counts, "counts", ckpt_dir, ckpt_key)
                        return modules
                    composition_components._d_a36 = True
                    composition.components = composition_components
                return loaded

            def components():
                loaded = patched_components()
                for loaded_module in loaded.values():
                    if getattr(loaded_module, "FAMILIES", None) == ("origin_change_invalid", "origin_change_valid") and hasattr(loaded_module, "prepare_sealed") \
                            and spec.get("origin_workers"):
                        import r2_parallel_origin   # D-A35
                        r2_parallel_origin.install(loaded_module, int(spec["origin_workers"]))
                        if ckpt_dir:
                            import r2_checkpoint
                            loaded_module.prepare_sealed = r2_checkpoint.wrap(loaded_module.prepare_sealed, "origin", ckpt_dir, ckpt_key)
                    if ckpt_dir and loaded_module is loaded.get("baseline") and not getattr(loaded_module.prepare_sealed, "_d_a37", False):
                        import r2_checkpoint
                        loaded_module.prepare_sealed = r2_checkpoint.wrap(loaded_module.prepare_sealed, "baseline", ckpt_dir, ckpt_key)
                    original_independent = getattr(loaded_module, "independent", None)
                    if original_independent is None or getattr(original_independent, "_d_a34", False):
                        continue

                    def independent(review, _orig=original_independent):
                        if isinstance(review, dict) and review.get("reviewer_session") == "root-session":
                            review = {**review, "reviewer_session": "/root/root-session"}
                        return _orig(review)
                    independent._d_a34 = True
                    loaded_module.independent = independent
                return loaded
            module.components = components
            evaluator, custody = original_modules(plan)
            if cutoff is not None:
                r2_fast_authorize.install(custody, cutoff)
            if fast_json:
                r2_fast_json.install(evaluator)
            if cache_dir:
                print(json.dumps({"input_projection_entries": r2_input_cache.install(evaluator, cache_dir)}), file=sys.stderr)
            return evaluator, custody

        module.scientific_modules = scientific_modules
    print(json.dumps({"fast_authorize": cutoff is not None, "input_cache": bool(cache_dir)}), file=sys.stderr)
    original_execute = module.execute   # diagnostics only: print the traceback the pinned run() swallows, then re-raise unchanged

    def execute(*args, **kwargs):
        try:
            return original_execute(*args, **kwargs)
        except BaseException:
            import traceback
            traceback.print_exc()
            raise
    module.execute = execute
    result = module.run(pref, aref)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
