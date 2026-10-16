"""Repeat a recorded graph experiment with repaired tensors and full-target scoring.

The original summary supplies splits and hyperparameters. No test-set tuning is
performed; decision thresholds are selected on training events by the shared fit.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import platform
import sys
import hashlib
import datetime
import json
import os
from pathlib import Path


def environment_versions():
    packages = {}
    for package in ('torch', 'torch-geometric', 'numpy', 'polars', 'scipy', 'scikit-learn'):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
            'packages': packages}


def run(path):
    from bgbench import config
    source = Path(__file__).resolve().parents[1] / "src" / "bgbench"
    provenance = {"started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  "slurm_job_id": os.environ.get("SLURM_JOB_ID"), "original_summary": str(path),
                  "environment": environment_versions(),
                  "original_summary_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "source_sha256": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in source.glob("*.py")}}
    old = json.loads(path.read_text())
    directory = path.parents[2]
    year, _, tag = directory.name.partition("_")
    delta = int(path.parents[1].name[1:-1])
    years = old.get("years", str(year))
    input_paths = [config.tgn_dir(int(y), delta, tag) for y in str(years).replace('>', ',').split(',')]
    provenance['data_root'] = str(config.DATA_ROOT)
    provenance['input_manifests_sha256'] = {
        str(folder / name): hashlib.sha256((folder / name).read_bytes()).hexdigest()
        for folder in input_paths for name in ('correction-impact.json', 'history-correction.json', 'index.csv')
        if (folder / name).exists()}
    prefix = path.name.removesuffix("_summary.json")
    years_suffix = "" if str(years).isdigit() else "_" + str(years).replace(",", "+").replace(">", "_to_")
    name = prefix.removesuffix(years_suffix) if years_suffix else prefix
    if name == "hist_avg":
        from bgbench.hist_avg import run as hist
        result = hist(years, delta, tag, old.get("k", 20))
        if tag == 'leak200' and int(year) in (2024, 2025) and delta in (30, 60):
            online = hist(years, delta, tag, old.get('k', 20), online_completed=True)
            if 'error' in online:
                raise RuntimeError(online['error'])
    else:
        family, _, suffix = name.partition("_")
        module = importlib.import_module("bgbench." + ("gnn_train" if family == "sage" else family + "_train"))
        if suffix:
            os.environ["BGBENCH_PREFIX_SUFFIX"] = "_" + suffix
        else:
            os.environ.pop("BGBENCH_PREFIX_SUFFIX", None)
        if suffix.startswith("z"):
            os.environ["BGBENCH_ZERO_FEATURES"] = suffix[1:].replace("-", ",")
        else:
            os.environ.pop("BGBENCH_ZERO_FEATURES", None)
        kwargs = {"year": years, "delta_s": delta, "tag": tag, "seed": old.get("seed", 0),
                  "epochs": old.get("epochs", 20), "hid": old.get("hid", 64),
                  "lr": old.get("lr", 1e-3), "pos_weight_cap": old.get("pos_weight_cap", 20),
                  "focal_gamma": old.get("focal_gamma", 0), "curve_weight": old.get("curve_weight", 1)}
        if family == "sage":
            kwargs.update(rank_weight=old.get("rank_weight", 0), curve_head=old.get("curve_head", "logistic" if suffix == "logistic" else "quantile"), separate_encoders=old.get("separate_encoders", suffix == "sepenc"))
        if family in ("tgn", "dyrep"):
            kwargs["mem"] = old.get("mem", 64)
        result = module.train(**kwargs)
    output_year = int(str(years).replace(">", ",").split(",")[-1])
    output = config.tgn_dir(output_year, delta, tag) / "_results"
    torch_module = sys.modules.get('torch')
    if torch_module is not None:
        provenance['environment']['torch_cuda_runtime'] = torch_module.version.cuda
        provenance['environment']['gpu'] = torch_module.cuda.get_device_name(0) if torch_module.cuda.is_available() else None
    provenance["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for filename, digest in provenance['input_manifests_sha256'].items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'Input manifest changed during training: {filename}')
    (output / (prefix + "_correction_run.json")).write_text(json.dumps(provenance, indent=2))
    if name == 'hist_avg' and tag == 'leak200' and int(year) in (2024, 2025) and delta in (30, 60):
        (output / (prefix.replace('hist_avg', 'hist_avg_online_completed', 1) + '_correction_run.json')).write_text(json.dumps(provenance, indent=2))
    if "error" in result:
        raise RuntimeError(result["error"])
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("original_summary", type=Path)
    args = parser.parse_args()
    run(args.original_summary)
