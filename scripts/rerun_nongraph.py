"""Manifest and source-gated reruns for cascade, count curves and prefix models."""
from __future__ import annotations
import argparse
import hashlib
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys


def prepare(run: Path):
    tasks = []
    for year in (2024, 2025):
        for source in sorted((run / 'data' / 'eventset' / str(year)).glob('cascade_vs_persistence_*.json')):
            old = json.loads(source.read_text())
            args = {key: old[key] for key in ('delta', 'target', 'coaffection', 'alpha', 'rec', 'valley_free', 'set_tag', 'min_asns') if key in old}
            tasks.append(dict(kind='cascade', year=year, name=source.stem, args=args, params=old['params']))
            if old.get('coaffection') and old.get('set_tag') == 'leak' and old.get('delta') == 'd30s':
                for alpha in (5., 20.):
                    if alpha != old.get('alpha'):
                        tasks.append(dict(kind='cascade', year=year, name=source.stem + f'_alpha{alpha:g}', args={**args, 'alpha': alpha}, params=old['params']))
        tasks += [dict(kind='curve_naive', year=year), dict(kind='tsfm', year=year), dict(kind='prefix_floor', year=year), dict(kind='prefix_model', year=year)]
        tasks += [dict(kind='prefix_features', year=year, shard=index, shards=32) for index in range(32)]
    tasks.append(dict(kind='chronos_lora', year=2025))
    tasks.append(dict(kind='radar_prefix_agreement', year=2024))
    for index, task in enumerate(tasks):
        task['index'] = index
    destination = run / 'nongraph-plan.json'
    destination.write_text(json.dumps(tasks, indent=1))
    print(json.dumps({'tasks': len(tasks), 'counts': {kind: sum(t['kind']==kind for t in tasks) for kind in sorted({t['kind'] for t in tasks})}}))


def fingerprint(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def table_content_fingerprint(path: Path):
    import polars as pl
    table = pl.read_parquet(path)
    if "event_id" in table.columns:
        table = table.sort("event_id")
    text = table.select(sorted(table.columns)).write_json()
    return hashlib.sha256(text.encode()).hexdigest()


def input_contract(run: Path, task):
    year, kind = task["year"], task["kind"]
    tag = task.get("args", {}).get("set_tag", "") if kind == "cascade" else "leak"
    event_dir = f"{year}_{tag}" if tag else str(year)
    inputs = [f"eventset/{event_dir}/events.parquet"]
    if kind in ("prefix_features", "prefix_model"):
        inputs.append(f"eventset/{year}_leak/prefix_floor.parquet")
    sources = {
        "cascade": ["src/bgbench/baselines_eventset.py", "src/bgbench/diffusion.py"],
        "curve_naive": ["src/bgbench/curve_eventset.py"],
        "tsfm": ["scripts/tsfm_curves.py", "src/bgbench/curve_eventset.py"],
        "chronos_lora": ["scripts/tsfm_finetune.py", "src/bgbench/curve_eventset.py"],
        "prefix_floor": ["scripts/prefix_floor.py"],
        "prefix_features": ["scripts/prefix_model.py", "src/bgbench/prefix_metrics.py"],
        "prefix_model": ["scripts/prefix_model.py", "src/bgbench/prefix_metrics.py"],
        "radar_prefix_agreement": ["scripts/label_leak_prefixes.py"],
    }[kind]
    sources += ["scripts/rerun_nongraph.py", "jobs/nongraph_corrections.sh", "src/bgbench/config.py", "src/bgbench/graph_metrics.py"]
    return {"inputs": {path: fingerprint(run/"data"/path) for path in inputs},
            "input_content_sha256": {path: table_content_fingerprint(run/"data"/path) for path in inputs},
            "code": {path: fingerprint(run/"code"/path) for path in sources},
            "plan_sha256": fingerprint(run/"nongraph-plan.json")}


def execute(run: Path, index: int):
    task = json.loads((run / 'nongraph-plan.json').read_text())[index]
    is_leak = task["kind"] != "cascade" or task["args"].get("set_tag", "").startswith("leak")
    forecast_origin = not is_leak and task["year"] == 2024 and (run/"forecast-origin-withdrawal-complete.json").exists()
    ready = (run / "crossday-source-complete.json").exists() or (is_leak and (run / "crossday-leak-2023-2025-complete.json").exists()) or forecast_origin
    if not ready:
        raise RuntimeError("final replay source is not published; refusing stale inputs")
    kind, year = task['kind'], task['year']
    output = run / 'nongraph-final' / str(year) / f'{index:03d}_{kind}'
    output.mkdir(parents=True, exist_ok=True)
    marker = output / 'complete.json'
    if marker.exists():
        print(marker.read_text()); return
    started = dt.datetime.now(dt.UTC).isoformat()
    before = input_contract(run, task)
    gate = "crossday-leak-2023-2025-complete.json" if is_leak and (run/"crossday-leak-2023-2025-complete.json").exists() else "crossday-source-complete.json"
    if forecast_origin:
        gate = "forecast-origin-withdrawal-complete.json"
    gate_sha256 = fingerprint(run/gate)
    python = sys.executable
    def script(name, *args, env=None):
        subprocess.run([python, str(run / 'code' / 'scripts' / name), *map(str, args)], check=True, env=env)
    if kind == 'cascade':
        from bgbench.baselines_eventset import run as cascade
        from bgbench.diffusion import ICParams
        sample = 100000 if task['args'].get('set_tag', '').startswith('leak') else 300
        result = cascade(year=year, sample=sample, p=ICParams(**task['params']), output_dir=output, **task['args'])
    elif kind == 'curve_naive':
        from bgbench.curve_eventset import run as curves
        result = curves(year=year, sample=400, use_chronos=False, set_tag='leak', min_asns=200)
        import shutil
        for file in (run/'data/eventset'/f'{year}_leak').glob('curve_baselines*'):
            shutil.copy2(file, output/file.name)
    elif kind == 'tsfm':
        script('tsfm_curves.py', year, 'leak', 200, 150, output / 'summary.json'); result = {}
    elif kind == 'chronos_lora':
        script('tsfm_finetune.py', year, 'leak', 200, output / 'summary.json', 600); result = {}
    elif kind == 'radar_prefix_agreement':
        script('label_leak_prefixes.py', year, '--output-dir', output); result = {}
    elif kind == 'prefix_floor':
        script('prefix_floor.py', year)
        import shutil
        for name in ('prefix_floor.parquet', 'prefix_floor_summary.json'):
            shutil.copy2(run/'data/eventset'/f'{year}_leak'/name, output/name)
        result = {}
    elif kind == 'prefix_features':
        env = dict(os.environ, PREFIX_SHARDS=str(task['shards']), PREFIX_SHARD=str(task['shard']), PREFIX_FEATURES_ONLY='1')
        script('prefix_model.py', year, 30, env=env); result = {}
    elif kind == 'prefix_model':
        # Features must be completed by all shards before the serial fit.
        plan = json.loads((run / 'nongraph-plan.json').read_text())
        required = [run / 'nongraph-final' / str(year) / f"{t['index']:03d}_prefix_features" / 'complete.json' for t in plan if t['kind']=='prefix_features' and t['year']==year]
        if not all(file.exists() for file in required):
            raise RuntimeError('prefix feature shards have not all completed')
        script('prefix_model.py', year, 30, env=dict(os.environ, PREFIX_OUTPUT_DIR=str(output))); result = {}
    else:
        raise ValueError(kind)
    after = input_contract(run, task)
    if any(before[key] != after[key] for key in ("input_content_sha256", "code", "plan_sha256")) or gate_sha256 != fingerprint(run/gate):
        raise RuntimeError("Non-graph source inputs or implementation changed during execution; refusing completion")
    provenance = {**before, "inputs_after": after["inputs"], "input_files_byte_identical": before["inputs"] == after["inputs"], "source_gate": gate, "source_gate_sha256": gate_sha256,
                  "started_utc": started, "finished_utc": dt.datetime.now(dt.UTC).isoformat(),
                  "inputs_unchanged": True, "code_unchanged": True}
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps({'task': task, 'result': result, 'correction_run': provenance}, indent=1, default=str))
    temporary.replace(marker)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('run_root', type=Path)
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    prepare(args.run_root) if args.action == 'prepare' else execute(args.run_root, args.index)
