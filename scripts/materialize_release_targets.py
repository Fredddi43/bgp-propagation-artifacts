"""Export small collector-specific target sets for a public verification manifest.

The full cluster contract continues to use raw replay membership. The public
contract explicitly names derived sidecars; the verifier never silently falls
back from missing raw inputs. Source hashes and frozen model event IDs are saved.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import polars as pl

ROOTS = {"origin": "events_replay", "leak": "events_replay_leak", "withdrawal": "events_replay_withdrawal"}


def materialize(source: Path, destination: Path, manifest: dict, model_source: Path | None = None) -> dict:
    public = copy.deepcopy(manifest)
    groups, input_hashes = {}, {}

    def read(relative, root=None):
        path = (root or source) / relative
        input_hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return pl.read_parquet(path) if path.suffix == ".parquet" else pl.read_csv(path)

    event_cache = {}
    for model in manifest["model_tables"]:
        target = manifest["model_targets"][model]
        if not target.get("membership_source"):
            continue
        spec = target["membership_source"]
        family, collector = spec["replay_family"], spec["collector"]
        if family not in ROOTS or not collector.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid replay family or collector name")
        wanted = set(read(model, model_source)["event_id"])
        rows = groups.setdefault((family, collector), {})
        found = set()
        for name in target.get("event_tables") or [target["event_table"]]:
            if name not in event_cache:
                event_cache[name] = read(f"eventset/{name}/events.parquet")
            for event in event_cache[name].filter(pl.col("event_id").is_in(wanted)).iter_rows(named=True):
                if event["error"] is not None:
                    raise ValueError(f"Model references unusable event {event['event_id']}")
                eid = event["event_id"]
                found.add(eid)
                if eid in rows:
                    if rows[eid]["t0_obs"] != event["t0_obs"]:
                        raise ValueError(f"Inconsistent observation clock for {eid}")
                    continue
                relative = f"{ROOTS[family]}/{eid}/membership.parquet"
                membership = read(relative)
                onset = dt.datetime.fromisoformat(event["t0_obs"])
                limits = {"d30s":30, "d1m":60, "T5m":300, "T15m":900, "T60m":3600, "final_2h":7200}
                sets = {name:set() for name in limits}
                for asn, seen, vp in membership.select("asn", "first_seen", "collector").iter_rows():
                    if vp != collector or seen is None:
                        continue
                    elapsed = (seen-onset).total_seconds()
                    for name, limit in limits.items():
                        if elapsed <= limit:
                            sets[name].add(int(asn))
                rows[eid] = {"event_id": eid, "error": None, "t0_obs": event["t0_obs"],
                             "collector": collector, "replay_family": family,
                             "membership_sha256": input_hashes[relative],
                             **{"set_"+key: sorted(value) for key,value in sets.items()}}
        if found != wanted:
            raise ValueError(f"Missing source events for {model}: {sorted(wanted-found)[:5]}")
        public["model_targets"][model] = {
            "target_table": f"verification/collector-targets/{family}-{collector}.parquet",
            "horizon": target["horizon"],
            **{key:target[key] for key in ("count_forecast","membership_predictions","probability_evidence") if key in target}}

    outputs = {}
    for (family, collector), rows in groups.items():
        relative = f"verification/collector-targets/{family}-{collector}.parquet"
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame([rows[key] for key in sorted(rows)]).write_parquet(path, compression="zstd")
        outputs[relative] = {"events": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    provenance = {"method": "collector-specific distinct AS first_seen <= common observation onset + horizon; no candidate pruning",
                  "input_sha256": input_hashes, "target_tables": outputs}
    provenance_path = destination / "verification/collector-targets/provenance.json"
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.write_text(json.dumps(provenance, indent=2)+"\n")
    public.setdefault("required_files", []).append("verification/collector-targets/provenance.json")
    public.setdefault("file_sha256", {}).update({path: record["sha256"] for path, record in outputs.items()})
    public["file_sha256"]["verification/collector-targets/provenance.json"] = hashlib.sha256(provenance_path.read_bytes()).hexdigest()
    return public


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_data",type=Path)
    parser.add_argument("release_data",type=Path)
    parser.add_argument("full_manifest",type=Path)
    parser.add_argument("--output-manifest",required=True,type=Path)
    parser.add_argument("--wait-for-marker",type=Path,help="wait for final model completeness before materializing")
    parser.add_argument("--model-completion",type=Path,help="read model root from final completion marker")
    parser.add_argument("--model-data",type=Path,help="separate final model data root; raw source data remains source_data")
    args=parser.parse_args()
    while args.wait_for_marker is not None and not args.wait_for_marker.exists():
        time.sleep(10)
    if args.model_completion:
        completion=json.loads(args.model_completion.read_text())
        root=Path(completion["data_root"])
        assert not root.is_absolute() and ".." not in root.parts
        args.model_data=args.model_completion.parent/root
    manifest=materialize(args.source_data,args.release_data,json.loads(args.full_manifest.read_text()),args.model_data)
    args.output_manifest.parent.mkdir(parents=True,exist_ok=True)
    pending=args.output_manifest.with_suffix(".pending.json")
    pending.write_text(json.dumps(manifest,indent=2)+"\n")
    pending.replace(args.output_manifest)
    print(json.dumps({"models":len(manifest["model_tables"]),"collector_models":sum("target_table" in x for x in manifest["model_targets"].values())}))

if __name__=="__main__": main()
