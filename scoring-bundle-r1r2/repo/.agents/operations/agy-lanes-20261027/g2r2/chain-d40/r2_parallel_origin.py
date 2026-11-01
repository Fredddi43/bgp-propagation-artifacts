"""D-A35: run the R2 origin component's label-free `prepare_sealed` per arm in forked workers (no pinned file is edited).

The pinned evaluation calls origin.prepare_sealed once; it loops over the 40 origin arms (reads each arm's commitment, fit documents,
sealed predictions and every test input, then `check_cell`). The arms are independent, the loop is serial, and at ~135k events per
origin valid arm the serial loop is ~20 min per arm (~7 h total). Nothing in this phase opens a label (the one-opening marker is
created later, in the primary evaluation).

Mechanism: the component's own source (already sha-verified by the runner, same file bytes) is re-parsed and compiled with ONE change:
immediately after `arms=freeze['arms']` the statement `_shard_arms=[a for a in arms if a['arm_id'] in _SHARD_IDS]` is inserted and the loop
`for a in arms:` iterates `_shard_arms` instead. Every pre-loop check still runs on all 40 arms in each worker. A worker handles exactly one
arm and returns its `cells` entry; the parent merges the entries in the freeze's arm order and returns the same dict the original returns.
Any worker exception aborts the phase (before any label access).
"""
import ast
import copy
import multiprocessing
from pathlib import Path


def _shard_function(module):
    tree = ast.parse(Path(module.__file__).read_bytes())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "prepare_sealed")
    function.name = "prepare_sealed_shard"
    body = function.body
    arms_index = next(i for i, n in enumerate(body) if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "arms")
    insert = ast.parse("_shard_arms=[a for a in arms if a['arm_id'] in _SHARD_IDS]").body[0]
    body.insert(arms_index + 1, insert)
    loops = [n for n in body if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "a"
             and isinstance(n.iter, ast.Name) and n.iter.id == "arms"]
    if len(loops) != 1:
        raise ValueError("origin prepare_sealed loop shape changed")
    loops[0].iter = ast.Name(id="_shard_arms", ctx=ast.Load())
    ast.fix_missing_locations(tree)
    namespace = module.__dict__
    exec(compile(ast.Module(body=[function], type_ignores=[]), module.__file__, "exec"), namespace)
    return namespace["prepare_sealed_shard"]


_JOB = {}
PRELOAD_THREADS = 64


def _run_one(arm_id):
    module = _JOB["module"]
    module._SHARD_IDS = {arm_id}
    partial = _JOB["shard"](*_JOB["args"])
    return arm_id, partial["cells"]


def install(module, workers=8):
    original = module.prepare_sealed
    shard = _shard_function(module)

    def prepare_sealed(custody, seal, freeze, evidence, read_json, read_input):
        arms = freeze["arms"]
        # check once, serially and cheaply, that the pre-loop checks pass (also yields scopes/projection/decision)
        executable = [a for a in arms if a.get("status") == "committed_for_prediction"]
        module._SHARD_IDS = {a["arm_id"] for a in arms if a.get("status") != "committed_for_prediction"}   # cheap arms in the serial pass
        base = shard(custody, seal, freeze, evidence, read_json, read_input)
        order = [a["arm_id"] for a in arms]
        executable.sort(key=lambda a: 0 if a["role"]["variant"] == "origin_change_valid" else 1)   # big (valid) arms first
        # Preload the Reader's verified input views ONCE in the parent (threaded: NFS reads are latency-bound per stream), through the same
        # read_input the consumer uses, so every forked worker finds them in its inherited cache and only logs the verified-reuse rows.
        from concurrent.futures import ThreadPoolExecutor
        seen_manifests, refs = set(), []
        for a in executable:
            if a["manifest_path"] in seen_manifests:
                continue
            seen_manifests.add(a["manifest_path"])
            manifest = read_json({"path": a["manifest_path"], "sha256": a["manifest_sha256"]}, "own origin issue input")
            refs.extend({"path": r["input_path"], "sha256": r["input_sha256"]} for r in manifest["events"] if r["input_status"] == "available")
        with ThreadPoolExecutor(max_workers=PRELOAD_THREADS) as pool:
            list(pool.map(lambda ref: read_input(ref, "own origin issue-time tensor"), refs))
        _JOB.update(module=module, shard=shard, args=(custody, seal, freeze, evidence, read_json, read_input))
        cells = dict(base["cells"])   # arms not committed (descriptive/not_estimable) were produced by the cheap serial pass
        context = multiprocessing.get_context("fork")
        with context.Pool(processes=workers, maxtasksperchild=1) as pool:
            for arm_id, arm_cells in pool.imap_unordered(_run_one, [a["arm_id"] for a in executable]):
                cells.update(arm_cells)
        missing = [name for name in order if name not in cells]
        if missing:
            raise ValueError(f"parallel origin preparation lacks arms: {missing[:3]}")
        merged = dict(base)
        merged["cells"] = {name: cells[name] for name in order}
        return merged   # fresh object assembled from the workers' own copies (nothing aliased); a deepcopy of ~0.9 TB of cells would not fit

    prepare_sealed._d_a35 = True
    prepare_sealed._original = original
    module.prepare_sealed = prepare_sealed
    return prepare_sealed
