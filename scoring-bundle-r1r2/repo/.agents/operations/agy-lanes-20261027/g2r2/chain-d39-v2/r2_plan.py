#!/usr/bin/env python3
"""Assemble the exact read inventory (and optionally the plan) for the PINNED single-R2 persistence runner.

The runner refuses any read outside `read_inventory` (a late refusal after the label marker would burn the one opening),
so the inventory is computed by walking every {path, sha256} reference reachable from the plan documents, the frozen arms
and their manifests. `kind`: label (plan['labels'] only), checkpoint (arm model_path), input (manifest event inputs),
metadata (everything else). Sizes come from stat, hashes from the references (verified again by the runner at read time).
No label/prediction payload is opened here except to follow JSON references in metadata documents.
"""
import json
from pathlib import Path

from common import sha

# A reachable non-binary document LARGER than this is a loud failure (q22 §5: a silent skip drops every
# reference nested inside it, and the runner then refuses "Read outside exact source inventory" late —
# after the one-opening marker). Inventory inclusion itself is never size-gated.
FOLLOW_CAP = 64 << 30
# D-A30: paths whose reference sha is already known (sealed predictions digests) and which are never followed (opaque predictions payloads)
KNOWN_SHA = {}
OPAQUE = set()
BINARY = {".pt", ".pkl", ".parquet", ".npy", ".pth", ".bin", ".log", ".jsonl"}


def is_ref(v):
    return isinstance(v, dict) and {"path", "sha256"} <= set(v) and isinstance(v["path"], str) and v["path"].startswith("/") and isinstance(v["sha256"], str) \
        and len(v["sha256"]) == 64


def walk(value):
    if is_ref(value):
        yield {"path": value["path"], "sha256": value["sha256"]}
    if isinstance(value, dict):
        for key, v in value.items():   # flat pairs such as scientific_protocol_path / scientific_protocol_sha256
            if key.endswith("_path") and isinstance(v, str) and v.startswith("/") and isinstance(value.get(key[:-5] + "_sha256"), str) \
                    and len(value[key[:-5] + "_sha256"]) == 64:
                yield {"path": v, "sha256": value[key[:-5] + "_sha256"]}
        for v in value.values():
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)


def arm_files(arm):
    for key in ("model", "manifest", "input_gate"):
        if arm.get(key + "_path"):
            yield key, {"path": arm[key + "_path"], "sha256": arm[key + "_sha256"]}
    for key, value in arm.items():   # predictions, commitment, count sidecars, ... (hash computed here; the runner re-verifies)
        if key.endswith("_path") and key not in ("model_path", "manifest_path", "input_gate_path") \
                and isinstance(value, str) and value.startswith("/") and Path(value).is_file():
            yield "metadata", {"path": value, "sha256": KNOWN_SHA.get(value) or sha(value)}


def build_inventory(plan, extra_paths=(), follow_depth=3):
    """Return the sorted `files` list for plan['read_inventory']."""
    found, kinds = {}, {}

    def add(ref, kind):
        p = Path(ref["path"])
        if not p.is_file():
            return False
        prior = found.get(ref["path"])
        if prior and prior["sha256"] != ref["sha256"]:
            raise ValueError(f"conflicting hashes for {ref['path']}")
        found[ref["path"]] = ref
        if kinds.get(ref["path"]) in (None, "metadata") or kind == "label":
            kinds[ref["path"]] = kind
        return True

    skip = {"read_inventory", "resource_readiness", "runtime", "records", "primary_output", "result_output", "primary_scores_output"}
    frontier = [(ref, 0) for key, value in plan.items() if key not in skip for ref in walk(value)]
    seen = set()
    while frontier:
        ref, depth = frontier.pop()
        if ref["path"] in seen:
            continue
        seen.add(ref["path"])
        kind = "label" if ref == plan["labels"] else "metadata"
        if not add(ref, kind):
            continue
        p = Path(ref["path"])
        if p.suffix not in BINARY and ref != plan["labels"] and ref["path"] not in OPAQUE:
            size = p.stat().st_size
            if size > FOLLOW_CAP:   # never silently stop following a reachable document: fail the build instead
                raise ValueError(f"reachable metadata document too large to follow: {p} ({size} bytes > FOLLOW_CAP {FOLLOW_CAP})")
            try:
                doc = json.loads(p.read_bytes())
            except ValueError:
                continue   # not a JSON metadata document (opaque payload): inventoried, not followed
            lists = [doc.get(k) for k in ("arms", "retained_failures")] if isinstance(doc, dict) else []
            for arm in [x for lst in lists if isinstance(lst, list) for x in lst]:
                if isinstance(arm, dict) and "arm_id" in arm:
                    for kind2, r in arm_files(arm):
                        kk = "checkpoint" if kind2 == "model" else "metadata"
                        add(r, kk)
                        frontier.append((r, depth + 1))
                    for item in (arm.get("failure_chain") or []):
                        if is_ref(item):
                            frontier.append((item, depth + 1))
                    ci = arm.get("custody_inputs")
                    if isinstance(ci, dict):
                        for r in walk(ci):
                            frontier.append((r, depth + 1))
            if isinstance(doc, dict) and isinstance(doc.get("events"), list):
                for row in (x for x in doc["events"] if isinstance(x, dict)):
                    if row.get("input_path") and row.get("input_sha256"):
                        add({"path": row["input_path"], "sha256": row["input_sha256"]}, "input")
            if depth < follow_depth:
                for r in walk(doc):
                    frontier.append((r, depth + 1))
    # refuse_second_opening reads every unblinded-*.json beside the freeze: any that exist must be admitted (none should in production)
    for marker in sorted(Path(plan["freeze"]["path"]).parent.glob("unblinded-*.json")):
        add({"path": str(marker), "sha256": sha(marker)}, "metadata")
    for extra in extra_paths:
        add({"path": str(extra), "sha256": sha(extra)}, "metadata")
    return [dict(path=p, sha256=found[p]["sha256"], size_bytes=Path(p).stat().st_size, kind=kinds[p]) for p in sorted(found)]


R2_ROOT = "<FORECAST_ROOT>/data-custodian/single-R2-v1"
MIB = 1 << 20
GIB = 1 << 30


def derive_bounds(inventory, *, output_file_bytes=16 * GIB, access_log_bytes=4 * GIB, runtime_file_bytes=4 * GIB, view_cache=64 * GIB):
    """Finite generous bounds for the PINNED persistence runner from the sized inventory (NO SELF-IMPOSED LIMITS).

    Every derived bound is >= 16x the measured need with a 16 GiB floor (RESOURCE-POLICY.md): the R2 outputs
    aggregate 10,000 repetitions x all arms and nothing local measures them (q22 §5). The pinned runner
    (newperiod-single-r2-persistence-20261024/runner.py) checks its own ceilings we must not exceed here:
    cpus<=128, memory_mib<=2_097_152 (runner.py:45), wall_seconds<=86400 (runner.py:45,:318); it also sets
    RLIMIT_FSIZE := bounds['output_file_bytes'] and RLIMIT_AS := (memory_mib-512) MiB (runner.py:332-333),
    and requires current_log_size + access_log_bytes <= output_file_bytes before the run (runner.py:325).
    """
    biggest = {k: max([x["size_bytes"] for x in inventory if x["kind"] == k] or [1]) for k in ("metadata", "input", "checkpoint", "label")}
    total = sum(x["size_bytes"] for x in inventory)
    pad = lambda n: ((max(16 * n, 16 * GIB) + MIB - 1) // MIB) * MIB   # >= 16x measured need, 16 GiB floor
    return {"metadata_bytes": pad(biggest["metadata"]), "input_bytes": pad(biggest["input"]), "checkpoint_bytes": pad(biggest["checkpoint"]),
            "label_bytes": pad(biggest["label"]), "runtime_file_bytes": runtime_file_bytes, "total_unique_bytes": pad(total),
            "total_read_bytes": pad(total), "output_file_bytes": output_file_bytes, "access_log_bytes": access_log_bytes,
            "output_total_bytes": 6 * output_file_bytes + access_log_bytes, "input_view_cache_bytes": view_cache}


def build_template(controls, *, source_root, access_log, extra_paths=()):
    """controls: refs {freeze, seal, arm_spec, labels, count_freeze, membership_freezes{h1,h3,timing,history,ordinary}, evidence{same},
    stable_freeze, stable_evidence, origin_freeze, origin_evidence, baseline_freeze, baseline_evidence, extension_decision, slice_rules,
    issue_time_tables{30,60}, full_retention_review, pre_R2_implementation_binding, source_closure}. Returns (template_without_job_fields, inventory)."""
    plan = dict(controls)
    plan.update(kind="newperiod_single_R2_execution_v1", arm_id="R2", repetitions=10000, bootstrap_seed=1701, alpha=0.05,
                source_root=str(source_root), access_log=str(access_log), records=R2_ROOT + "/arms/000/attempt",
                primary_output=R2_ROOT + "/arms/000/attempt/primary.json", result_output=R2_ROOT + "/arms/000/attempt/complete-result.json",
                primary_scores_output=R2_ROOT + "/arms/000/attempt/primary-scores.json")
    inventory = build_inventory(plan, extra_paths=extra_paths)
    plan["bounds"] = derive_bounds(inventory)
    return plan, inventory
