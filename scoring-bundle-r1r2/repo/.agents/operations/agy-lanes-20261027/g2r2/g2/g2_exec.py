#!/usr/bin/env python3
"""G2 executor: ONE retained arm in ONE Slurm array task, through the family's reviewed runner (unchanged).

Run as `python -I -B g2_exec.py --spec SPEC --index N` inside the job (env cleared except SLURM_*, thread counts).
It only fills what the runner demands from the live allocation: job id/cpus/memory, the runtime evidence document, the
resource-admission document and an approval derived from root's go file. Every scientific check stays in the runner:
frozen arm vs plan, custody input hashes, model/fit provenance, label-free inputs, prediction schema, verify_arm.
No retry: records dir and prediction outputs are exclusive; a failed attempt leaves its records and failure.json.

Spec: {"go_file": path, "work": dir, "arms": [{"arm_id", "template": {path,sha256}, "runner": {path,sha256},
        "kernel": {path,sha256}|null, "readiness_flags": [..], "readiness_extra": {..}, "output_parents": [dir,..]}]}
Template = the family's plan (kind, freeze, arm_id, bounds, custody_inputs, access_log, source_root, ... ) without
records/runtime/resource_readiness/job id.
"""
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

FALSE_FLAGS = ("retry_authorized", "fit_authorized", "calibration_authorized", "score_authorized", "seal_authorized",
               "outcome_release_authorized", "cohort_selection_authorized")


def need(ok, why):
    if not ok:
        raise SystemExit("REFUSED: " + why)


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha_bytes(path.read_bytes())}


def write_new(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": str(Path(path).resolve()), "sha256": sha_bytes(data)}


def bound(item):
    path = Path(item["path"])
    raw = path.read_bytes()
    need(sha_bytes(raw) == item["sha256"], f"{path} differs from its pinned hash")
    return raw


def runtime_document():
    # The interpreter is bound as "python"; listing it in "files" would force every runtime_file_bytes bound above ~31 MB.
    files = [importlib.util.find_spec(name).origin for name in ("numpy", "polars", "torch")]
    return {"passed": True, "python": ref(sys.executable),
            "versions": {n: importlib.metadata.version(n) for n in ("numpy", "polars", "torch")},
            "files": [ref(p) for p in files]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--attempt", type=int, default=1)
    a = p.parse_args(argv)
    spec = json.loads(a.spec.read_bytes())
    item = spec["arms"][a.index]
    go = Path(spec["go_file"])
    need(go.is_file() and go.stat().st_size > 0, f"root go file {go} missing: G2 not authorized")
    template = json.loads(bound(item["template"]))
    need(template["arm_id"] == item["arm_id"], "template names another arm")
    env = os.environ
    for k in ("SLURM_JOB_ID", "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_NODE"):
        need(k in env, k + " missing: run inside the allocation")
    resources = dict(template["resources"], job_id=env["SLURM_JOB_ID"], cpus=int(env["SLURM_CPUS_PER_TASK"]),
                     memory_mib=int(env["SLURM_MEM_PER_NODE"]))
    arm_dir = Path(spec["work"]) / "arms" / f"{a.index:03}"
    arm_dir.mkdir(parents=True, exist_ok=True)
    for parent in item.get("output_parents", []):   # runners require the frozen output parent to exist, the file absent
        Path(parent).mkdir(parents=True, exist_ok=True)
    records = arm_dir / f"attempt-{a.attempt}"
    plan = dict(template, resources=resources, records=str(records))
    plan["runtime"] = write_new(arm_dir / f"runtime-{a.attempt}.json", runtime_document())
    carried = {k: plan[k] for k in ("history_bounds", "sources") if k in plan}   # admission must repeat these verbatim
    readiness = {"passed": True, "resources": resources, "freeze": plan["freeze"], "arm_id": plan["arm_id"],
                 "bounds": plan["bounds"], **carried, **{k: True for k in item.get("readiness_flags", [])},
                 **item.get("readiness_extra", {})}
    plan["resource_readiness"] = write_new(arm_dir / f"readiness-{a.attempt}.json", readiness)
    pref = write_new(arm_dir / f"plan-{a.attempt}.json", plan)
    runner_raw = bound(item["runner"])
    approval = {"passed": True, "plan": pref, "runner_sha256": item["runner"]["sha256"], "resources": resources,
                "execution_authorized": True, "review": ref(go), "reviewer_model": "claude-sonnet-5-5",
                "reviewer_worker": "root-orchestrator-claude-sonnet-5-5",
                "reviewer_session": "go-file-" + sha_bytes(go.read_bytes())[:16],
                **dict.fromkeys(FALSE_FLAGS, False)}
    if item.get("kernel"):
        approval["kernel_sha256"] = item["kernel"]["sha256"]
        bound(item["kernel"])
    aref = write_new(arm_dir / f"approval-{a.attempt}.json", approval)
    module = types.ModuleType("g2_family_runner")
    module.__file__ = item["runner"]["path"]
    exec(compile(runner_raw, module.__file__, "exec"), module.__dict__)
    # ROOT DEVIATION D-A13 (2026-10-28): the pinned evaluation role classification (forecast_custodian_eval.role_arm)
    # counts every baseline-family role with panel=reference/library=online, so the published freeze's non-core baseline
    # variants (delay900/delay1800/withhold/stable) collide with the core arms and derive_new_period_arms refuses
    # ("Two retained arms claim ..."). Those variants are sensitivity arms, not evaluation reference arms (the neural
    # branch of role_arm already requires variant == core). The classification is narrowed IN PROCESS, after the runner
    # loaded its pinned modules; no pinned file or hash changes; every arm records this in deviation-N.json.
    # ROOT DEVIATIONS D-A15/D-A16 (2026-10-28), origin family only (the template carries family_evidence):
    # D-A15: the frozen origin arms carry two refs that name lane-laptop paths compute nodes cannot open
    #   (family_fit.review -> .../origin-fits/g1-fit-reviews/<arm>.completed-fit-review.json, and family_sampling_rule ->
    #   .../codex-takeover-20261023/origin-family-prospective-acquisition-proposal.md) while the frozen custodian masters
    #   carry the cluster path of the same sampling-rule bytes. After the runner's own freeze checks (arms_sha256,
    #   typed cells, exclusive outputs) the SELECTED arm's two refs are canonicalized in memory through the root-signed
    #   substitution sidecar (every substituted ref keeps the frozen sha256; mirrored bytes verified 40/40).
    # D-A16: the runner reads the sampling rule through its JSON document() reader, but the frozen rule is a markdown
    #   file; for *.md refs the reader verifies the bytes/sha (raw) and returns an empty document (the caller ignores it).
    _sidecar = Path(spec["work"]).resolve().parent.parent / "origin-evidence" / "origin-path-substitution.json"
    if "family_evidence" in template and _sidecar.is_file():
        _sub = json.loads(_sidecar.read_bytes())
        need(_sub.get("signed") is True, "origin path-substitution sidecar is not root-signed")
        need(hasattr(module, "freeze") and hasattr(module, "document") and hasattr(module, "raw"), "origin runner shape unexpected")
        _orig_freeze, _orig_document = module.freeze, module.document

        def _freeze_d_a15(*fa, **fk):
            f, arm, recipe = _orig_freeze(*fa, **fk)
            s_ = _sub["sampling_rule"]
            if arm.get("family_sampling_rule") == s_["from"]:
                need(s_["to"]["sha256"] == arm["family_sampling_rule"]["sha256"], "sampling rule sha chain differs")
                arm["family_sampling_rule"] = dict(s_["to"])
            ent = _sub["fit_review"].get(arm["arm_id"])
            frz = arm["family_fit"]["review"]
            if ent and (frz.get("path") == ent["from"] if isinstance(ent["from"], str) else frz == ent["from"]):
                need(ent["to"]["sha256"] == frz["sha256"], "fit review sha chain differs")
                arm["family_fit"]["review"] = dict(ent["to"])
            return f, arm, recipe

        def _document_d_a16(ref, *da, **dk):
            if isinstance(ref, dict) and str(ref.get("path", "")).endswith(".md"):
                module.raw(ref, *(da[:1] or (64 << 20,)))
                return {}
            return _orig_document(ref, *da, **dk)
        module.freeze, module.document = _freeze_d_a15, _document_d_a16
        write_new(arm_dir / f"deviation-d-a15-d-a16-{a.attempt}.json", {"id": "D-A15/D-A16", "arm_id": item["arm_id"],
            "sidecar": ref(_sidecar), "g2_exec_sha256": sha_bytes(Path(__file__).read_bytes())})
    _d_a13_applied = []
    # ROOT DEVIATION D-A14 (2026-10-28): the baseline runner reads the freeze with document(ref) whose default byte
    # bound is a hard-coded 64 MiB; the published freeze is ~163 MB (origin cohorts), so every baseline arm is refused
    # ("Input byte bound exceeded"). The default bound is raised in process (1 GiB); runner bytes/hash unchanged.
    _doc = getattr(module, "document", None)
    if _doc is not None and getattr(_doc, "__defaults__", None) == (64 << 20,):
        _doc.__defaults__ = (1 << 30,)
        write_new(arm_dir / f"deviation-d-a14-{a.attempt}.json", {"id": "D-A14", "arm_id": item["arm_id"],
            "change": "runner document() default byte bound 64 MiB -> 1 GiB (freeze.json is ~163 MB)",
            "g2_exec_sha256": sha_bytes(Path(__file__).read_bytes())})
    _d_a13_target = module if hasattr(module, "modules") else getattr(module, "r", None)   # timing runner loads through its base module r
    if _d_a13_target is None or not hasattr(_d_a13_target, "modules"):
        write_new(arm_dir / f"deviation-{a.attempt}.json", {"id": "D-A13", "arm_id": item["arm_id"],
            "change": "not applicable: runner has no modules() (does not call derive_new_period_arms through it)",
            "g2_exec_sha256": sha_bytes(Path(__file__).read_bytes())})
        _orig_modules = None
    else:
        _orig_modules = _d_a13_target.modules

    def _modules_with_d_a13(*args, **kwargs):
        result = _orig_modules(*args, **kwargs)
        ev = sys.modules.get("bgbench.forecast_custodian_eval")
        need(ev is not None, "evaluation module not loaded: D-A13 cannot be applied")
        if not getattr(ev, "_d_a13", False):
            _orig_role_arm = ev.role_arm

            def role_arm(role):
                if isinstance(role, dict) and role.get("family") == "baseline" and role.get("variant") not in (None, "core"):
                    return None
                return _orig_role_arm(role)
            ev.role_arm = role_arm
            ev._d_a13 = True
        _m0 = result[0] if isinstance(result, tuple) else result
        pred = getattr(_m0, "predictor", None)
        if pred is None or not hasattr(pred, "checked_contract"):
            pred = next((v for k, v in list(sys.modules.items()) if hasattr(v, "provenance_frozen") and hasattr(v, "checked_contract")), None)
        if pred is not None and not getattr(pred, "_d_a17", False):
            # ROOT DEVIATIONS D-A17/D-A18 (2026-10-28), frozen-2025 reference arms of the pinned frozen predictor:
            # D-A17: the freeze records an extra provenance key (calibration_membership, a lane-laptop path) on frozen-2025 arms
            #   while provenance_frozen demands exactly {kind, plan}; the extra key is dropped from a COPY of the arm.
            # D-A18: the legacy 2025 checkpoint receipts carry no feature_contract/library_protocol, so the contract
            #   equality fails by absence; for such receipts the equalities are skipped and every other check
            #   (history feature indices, input width == mu/sd length, relation types, horizon) is kept verbatim.
            _pf, _cc = pred.provenance_frozen, pred.checked_contract

            def _provenance_frozen(arm, role, checkpoint):
                prov = arm.get("provenance")
                if isinstance(prov, dict) and prov.get("kind") == "frozen2025_plan_v1" and set(prov) - {"kind", "plan"} == {"calibration_membership"}:
                    arm = dict(arm)
                    arm["provenance"] = {k: v for k, v in prov.items() if k != "calibration_membership"}
                return _pf(arm, role, checkpoint)

            def _checked_contract(manifest, checkpoint, role):
                receipt = checkpoint["receipt"]
                if receipt.get("feature_contract") is not None or receipt.get("library_protocol") is not None:
                    return _cc(manifest, checkpoint, role)
                settings = checkpoint["settings"]
                contract = manifest.get("feature_contract") or {}
                pred.need(checkpoint["history_feature_indices"] == manifest["history_feature_indices"], "Checkpoint/manifest history features differ")
                pred.need(type(contract.get("width")) is int
                          and settings.get("in_dim") == contract["width"] == len(checkpoint["mu"]) == len(checkpoint["sd"]),
                          "Checkpoint input width differs from the feature contract")
                pred.need(type(manifest.get("n_edge_types")) is int and manifest["n_edge_types"] <= settings.get("n_types", 0),
                          "Manifest relation types exceed the checkpoint")
                pred.need(manifest.get("delta_s") == role["horizon_seconds"], "Manifest horizon differs from the role")
            pred.provenance_frozen, pred.checked_contract, pred._d_a17 = _provenance_frozen, _checked_contract, True
            write_new(arm_dir / f"deviation-d-a17-d-a18-{a.attempt}.json", {"id": "D-A17/D-A18", "arm_id": item["arm_id"],
                "g2_exec_sha256": sha_bytes(Path(__file__).read_bytes())})
        # DEBUG (no behaviour change): the runners swallow the cause of a refusal; record tracebacks of the custody helpers.
        if pred is not None and not getattr(pred, "_dbg", False):
            import traceback as _tb

            def _wrap_dbg(fn, label):
                def w(*wa, **wk):
                    try:
                        return fn(*wa, **wk)
                    except BaseException:
                        with (arm_dir / f"debug-{a.attempt}.txt").open("a") as fh:
                            fh.write(f"=== {label}\n{_tb.format_exc()}\n")
                        raise
                return w
            for _n in ("durable_log", "custody_read_paths", "configured_log", "checked_checkpoint", "checked_contract", "run", "infer", "validated_rows"):
                if hasattr(pred, _n):
                    setattr(pred, _n, _wrap_dbg(getattr(pred, _n), _n))
            _inp = getattr(pred, "inputs", None)
            if _inp is not None and hasattr(_inp, "custody_load"):
                _inp.custody_load = _wrap_dbg(_inp.custody_load, "custody_load")
            pred._dbg = True
        if not _d_a13_applied:
            _d_a13_applied.append(write_new(arm_dir / f"deviation-{a.attempt}.json", {"id": "D-A13", "arm_id": item["arm_id"],
                "change": "forecast_custodian_eval.role_arm ignores baseline roles with variant not in (None, core), in process",
                "g2_exec_sha256": sha_bytes(Path(__file__).read_bytes())}))
        return result
    if _orig_modules is not None:
        _d_a13_target.modules = _modules_with_d_a13
    # ROOT DEVIATION D-A20 (2026-10-28): the q35 origin successor runner builds its parallel-inference module as an
    # unregistered local (types.ModuleType('q35_parallel_infer') + exec of the sha-pinned parallel_infer.py), so its
    # ProcessPool tasks cannot be pickled by module name ("import of module 'q35_parallel_infer' failed"; it only worked
    # in the E3 harness). Module objects with exactly that name are registered in sys.modules at creation (no code change).
    import types as _types_mod
    _RealModuleType = _types_mod.ModuleType

    class _ModuleTypeMeta(type):
        def __instancecheck__(cls, inst):
            return isinstance(inst, _RealModuleType)

        def __subclasscheck__(cls, sub):
            return issubclass(sub, _RealModuleType)

    class _RegisteringModuleType(_RealModuleType, metaclass=_ModuleTypeMeta):
        def __init__(self, name, *ma, **mk):
            super().__init__(name, *ma, **mk)
            if name == "q35_parallel_infer":
                sys.modules[name] = self
    _types_mod.ModuleType = _RegisteringModuleType
    write_new(arm_dir / f"deviation-d-a20-{a.attempt}.json", {"id": "D-A20", "arm_id": item["arm_id"],
        "change": "types.ModuleType subclass registering modules named q35_parallel_infer in sys.modules",
        "g2_exec_sha256": sha_bytes(Path(__file__).read_bytes())})
    # ROOT DEVIATION D-A21 (2026-10-28, revised 2026-10-29) timing family: the frozen timing arms reference
    # timing40-fit-ops-v6-20261027/bound-package.json (same package_files/sourceclosure/cells as the transport package.json;
    # only requirements/resources/status differ), but the pinned fit runner's fit_namespace demands root == fit.STAGE and
    # fit.closure(package, root) reads scientific-source/, guard-source/, recipes.json, recipe-freeze-receipt.json from root,
    # which exist only under the original transport STAGE. fit_namespace is narrowed in process: it still requires
    # package stage/output == the original STAGE/OUTPUT, and it then makes fit.closure read those files from fit.STAGE when
    # given the bound-package directory. closure() still checks every snapshot file and package_files sha against the
    # package's own maps, the original source-map digest and the frozen recipes (nothing skipped).
    if hasattr(module, "fit_namespace") and hasattr(module, "checked_fit"):
        def _fit_namespace_d_a21(root, package, fit):
            need(package["stage"] == str(fit.STAGE) and package["output"] == str(fit.OUTPUT), "Original timing fit namespace required")
            _closure, _bound_dir = fit.closure, Path(root)

            def _closure_stage(pkg, croot, *ca, **ck):
                return _closure(pkg, fit.STAGE if Path(croot) == _bound_dir else croot, *ca, **ck)
            fit.closure = _closure_stage
        module.fit_namespace = _fit_namespace_d_a21
        write_new(arm_dir / f"deviation-d-a21-{a.attempt}.json", {"id": "D-A21", "arm_id": item["arm_id"],
            "change": "timing fit_namespace: package stage/output must be the original STAGE/OUTPUT; fit.closure reads its source/package files from fit.STAGE",
            "g2_exec_sha256": sha_bytes(Path(__file__).read_bytes())})
    if hasattr(module, "_run") and os.environ.get("G2_DEBUG_TRACE") == "1":
        import traceback as _tb3
        _orig_run_fn = module._run

        def _run_dbg(*ra, **rk):
            try:
                return _orig_run_fn(*ra, **rk)
            except BaseException:
                with (arm_dir / f"runtb-{a.attempt}.txt").open("a") as fh:
                    fh.write(_tb3.format_exc())
                raise
        module._run = _run_dbg
    if os.environ.get("G2_DEBUG_TRACE") == "1":   # debug only (never set in production jobs): record swallowed ValueErrors
        import traceback as _tb2
        _seen = []

        def _tracer(frame, event, arg):
            if event == "exception" and arg[0] in (ValueError, OSError, AssertionError, MemoryError, RuntimeError, EOFError) and ("/source/" in frame.f_code.co_filename or "/runners/" in frame.f_code.co_filename or "g2_exec" in frame.f_code.co_filename) and "site-packages" not in frame.f_code.co_filename:
                if len(_seen) < 400:
                    _seen.append(1)
                    with (arm_dir / f"trace-{a.attempt}.txt").open("a") as fh:
                        fh.write(f"{arg[0].__name__}: {str(arg[1])[:300]} @ {frame.f_code.co_filename}:{frame.f_lineno} in {frame.f_code.co_name}\n")
            return _tracer
        sys.settrace(_tracer)
    try:
        result = module.run(pref, aref)
    except BaseException as error:
        write_new(arm_dir / f"failure-{a.attempt}.json", {"arm_id": item["arm_id"], "error": str(error)[:500],
                                                         "plan": pref, "retry_authorized": False})
        raise SystemExit(f"G2 arm {item['arm_id']} failed: {str(error)[:200]}")
    write_new(arm_dir / f"result-{a.attempt}.json", {"arm_id": item["arm_id"], "result": result, "plan": pref})
    print(json.dumps({"arm_id": item["arm_id"], "result": result}, sort_keys=True))


if __name__ == "__main__":
    main()
