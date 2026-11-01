"""Manifest-driven matched-information forecasts, with separate fit/predict/score gates.

Unlike the legacy experiment runner, fitting never loads a test tensor. The no-edge
control retains candidates, topology-derived input features, every root transform,
and both readouts; it removes only neighbor messages. It is not topology-free.

Usage: python -m bgbench.forecast_train {fit,predict,score} --help
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .gnn_train import CURVE_HORIZONS, TypedSAGE, curve_forecast_mask, pinball, sage_forward
from .graph_metrics import membership_metrics

LABEL_KEYS = frozenset(("y", "curve", "target_asns", "first_s", "n_pos"))
INPUT_KEYS = frozenset(("event_id", "x", "edge_index", "edge_type", "asn", "seed_asns",
                        "persistence_pred", "n_seed_all", "delta_s", "observation_cutoff_s"))
# Above any probability: selecting with p >= this adds no candidate (seeds only = persistence).
NO_ADDITIONS_THRESHOLD = 1.01


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def timestamp(value):
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Manifest timestamp has no timezone: {value}")
    return parsed.astimezone(dt.timezone.utc)


def validate_manifest(manifest: dict):
    """Fail closed on overlapping incidents, dates or immature supervised labels."""
    if "manifest_sha256" in manifest:
        payload = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if digest != manifest["manifest_sha256"]:
            raise ValueError("Manifest self-digest mismatch")
    rows = manifest["events"]
    if not rows:
        raise ValueError("Empty manifest")
    ids, incidents = set(), {}
    parts = {name: [] for name in ("train", "validation", "test")}
    for row in rows:
        eid, split = row["event_id"], row["split"]
        if eid in ids:
            raise ValueError(f"Duplicate manifest event: {eid}")
        ids.add(eid)
        if split not in parts:
            raise ValueError(f"Unknown split {split}")
        incident = row["incident_id"]
        if not incident:
            raise ValueError(f"Missing incident_id: {eid}")
        if incident in incidents and incidents[incident] != split:
            raise ValueError(f"Incident crosses split boundary: {incident}")
        incidents[incident] = split
        onset = timestamp(row["onset"])
        # Test maturity is not used for any fit decision. In particular, avoid
        # inspecting protected outcome-availability metadata during fitting.
        maturity = (onset + dt.timedelta(seconds=7200) if split == "test" else
                    timestamp(row.get("label_available_at", onset + dt.timedelta(seconds=7200))))
        if maturity < onset + dt.timedelta(seconds=7200):
            raise ValueError(f"Label matures before target horizon: {eid}")
        parts[split].append((onset, maturity, eid))
    if any(not parts[s] for s in parts):
        raise ValueError("Manifest requires nonempty train, validation and test splits")
    for earlier, later in (("train", "validation"), ("validation", "test")):
        boundary = min(r[0] for r in parts[later])
        if max(r[0] for r in parts[earlier]) >= boundary:
            raise ValueError(f"Nonchronological {earlier}/{later} split")
        bad = [eid for _, available, eid in parts[earlier] if available > boundary]
        if bad:
            raise ValueError(f"Immature {earlier} labels at {later} boundary: {bad[:5]}")
    features = manifest.get("history_feature_indices")
    if not isinstance(features, list) or not features or any(not isinstance(i, int) or i < 0 for i in features):
        raise ValueError("Manifest must declare history_feature_indices")
    return parts


def graph_path(row: dict, graph_dirs: list[Path], manifest_path: Path, prediction=False):
    explicit = row.get("input_path") if prediction else None
    explicit = explicit or row.get("graph_path")
    if explicit:
        path = Path(explicit)
        return path if path.is_absolute() else manifest_path.parent / path
    found = [directory / f"{row['event_id']}.pt" for directory in graph_dirs
             if (directory / f"{row['event_id']}.pt").is_file()]
    if len(found) != 1:
        raise ValueError(f"Expected exactly one tensor for {row['event_id']}, found {len(found)}")
    return found[0]


def load_partition(manifest_path: Path, manifest: dict, split: str, graph_dirs: list[Path], *,
                   prediction=False, allow_label_containers=False, expected_hashes=None):
    """Only open the selected partition; return input checksums for reproducibility."""
    events, receipt = [], []
    for row in sorted((r for r in manifest["events"] if r["split"] == split), key=lambda r: (r["onset"], r["event_id"])):
        path = graph_path(row, graph_dirs, manifest_path, prediction=prediction)
        # Hash and deserialize exactly the same bytes, including through shard symlinks.
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        if expected_hashes is not None and expected_hashes.get(row["event_id"]) != digest:
            raise ValueError(f"Tensor differs from integration gate: {row['event_id']}")
        expected = row.get("input_sha256" if prediction and row.get("input_path") else "graph_sha256")
        if expected and expected != digest:
            raise ValueError(f"Tensor checksum mismatch: {row['event_id']}")
        event = torch.load(io.BytesIO(content), map_location="cpu", weights_only=False)
        if event["event_id"] != row["event_id"]:
            raise ValueError(f"Tensor event ID mismatch: {path}")
        provenance = event.get("history_provenance")
        contract = event.get("forecast_contract")
        if not provenance or not contract or contract.get("history_mode") != "shared_completed":
            raise ValueError(f"Matched training requires shared completed-history tensors: {path}")
        source_manifest_hash = manifest.get("source_manifest_sha256", sha256(manifest_path))
        if contract.get("manifest_sha256") != source_manifest_hash:
            raise ValueError(f"Tensor/manifest digest mismatch: {path}")
        require_input_cutoff_rule(contract, path)
        issue_time = timestamp(row.get("issue_time", timestamp(row["onset"]) + dt.timedelta(
            seconds=float(event.get("observation_cutoff_s", event.get("delta_s", 30))))))
        if timestamp(provenance["issue_time"]) != issue_time or timestamp(provenance["availability_cutoff"]) > issue_time:
            raise ValueError(f"History availability/issue-time mismatch: {path}")
        if provenance.get("excluded_event_id") != row["event_id"]:
            raise ValueError(f"Current event was not excluded from history: {path}")
        expected_contract = manifest.get("feature_contract")
        if expected_contract and event.get("feature_contract") != expected_contract:
            raise ValueError(f"Feature contract mismatch: {path}")
        expected_library = manifest.get("library_protocol")
        if expected_library and event.get("library_protocol") != expected_library:
            raise ValueError(f"Library protocol mismatch: {path}")
        if prediction:
            if LABEL_KEYS.intersection(event) and not allow_label_containers:
                raise ValueError("Prediction requires custodian-exported label-free inputs; "
                                 f"found label fields in {path}")
            event = {key: value for key, value in event.items() if key in INPUT_KEYS}
        else:
            if not {"y", "target_asns", "curve"} <= event.keys():
                raise ValueError(f"Training/calibration labels incomplete: {path}")
        for key in ("x", "edge_index", "edge_type", "asn", "seed_asns", "persistence_pred", "y", "curve"):
            if key in event:
                event[key] = torch.as_tensor(event[key]).clone()
        event["edge_index"] = event["edge_index"].long()
        event["edge_type"] = event["edge_type"].long()
        event["x"] = event["x"].float()
        if not torch.isfinite(event["x"]).all() or not len(event["x"]):
            raise ValueError(f"Invalid/empty input features: {path}")
        if len(set(event["asn"].tolist())) != len(event["asn"]):
            raise ValueError(f"Duplicate candidate ASNs: {path}")
        if not torch.equal(event["persistence_pred"].bool(), torch.isin(event["asn"], event["seed_asns"])):
            raise ValueError(f"Seed mask/ASN mismatch: {path}")
        if not prediction:
            target = torch.as_tensor(event["target_asns"])
            if not torch.equal(event["y"].bool(), torch.isin(event["asn"], target)):
                raise ValueError(f"Candidate/full-target label mismatch: {path}")
            if event["curve"][-1].item() != len(set(target.tolist())):
                raise ValueError(f"Curve/full-target size mismatch: {path}")
        events.append(event)
        receipt.append({"event_id": row["event_id"], "path": str(path.resolve()), "sha256": digest,
                        "forecast_contract": contract,
                        **({"history_provenance": provenance} if not prediction else {})})
    return events, receipt


def require_input_cutoff_rule(contract, where):
    """Every model input must be built under the whole-second availability rule (forecast_protocol).

    Tensors built before the rule (raw first_seen cutoffs) carry no tag and are refused on every
    training, prediction and evaluation load path, not only when a build directory is resumed.
    """
    from .forecast_protocol import INPUT_CUTOFF_RULE_ID
    if not isinstance(contract, dict) or contract.get("input_cutoff_rule") != INPUT_CUTOFF_RULE_ID:
        raise ValueError(f"Input was not built under cutoff rule {INPUT_CUTOFF_RULE_ID}: {where}")


def input_gate_hashes(gate_path, manifest_path, manifest):
    if gate_path is None:
        if manifest.get("schema_version", 0) >= 1:
            raise ValueError("Versioned production manifests require --input-gate")
        return None, None
    gate = json.loads(Path(gate_path).read_text())
    if gate.get("passed") is not True:
        raise ValueError("Input integration gate has not passed")
    expected = sha256(Path(manifest_path))
    matches = [entry for entry in gate["manifests"] if entry["sha256"] == expected]
    if len(matches) != 1:
        raise ValueError("Manifest is absent from input integration gate")
    hashes = {row["event_id"]: row["sha256"] for row in matches[0]["inputs"]}
    if len(hashes) != len(matches[0]["inputs"]) or set(hashes) != {r["event_id"] for r in manifest["events"]}:
        raise ValueError("Input gate event IDs differ or duplicate")
    return hashes, sha256(Path(gate_path))


class MatchedSAGE(TypedSAGE):
    """Identical branches/readouts; no-edge suppresses only neighbor aggregation."""

    def __init__(self, in_dim, hid=64, n_types=3, layers=2, dropout=0.2,
                 message_passing="sage", curve_projection="cummax"):
        super().__init__(in_dim, hid=hid, n_types=n_types, layers=layers, dropout=dropout)
        if message_passing not in ("sage", "none") or curve_projection not in ("none", "cummax"):
            raise ValueError("Invalid model control")
        self.message_passing = message_passing
        self.curve_projection = curve_projection

    def _encode(self, convs, x, edge_index, edge_type):
        h = x
        for layer in convs:
            # All relation root transforms run in BOTH arms, even for empty types.
            # This avoids changing root multiplicity when neighbor messages vanish.
            outputs = []
            for relation, conv in enumerate(layer):
                edges = edge_index[:, edge_type == relation] if self.message_passing == "sage" else edge_index[:, :0]
                outputs.append(conv(h, edges))
            h = F.dropout(F.relu(torch.stack(outputs).sum(0)), self.dropout, self.training)
        return h

    def forward(self, *args, **kwargs):
        logits, quantiles = super().forward(*args, **kwargs)
        if self.curve_projection == "cummax":
            quantiles = torch.cummax(quantiles, dim=0).values
        return logits, quantiles


def transform_events(events, history_indices, history, mu=None, sd=None):
    for event in events:
        event["x"] = event["x"].clone()
        if any(i >= event["x"].shape[1] for i in history_indices):
            raise ValueError("History feature index outside tensor")
        if history == "off":
            event["x"][:, history_indices] = 0
    if mu is None:
        # Streaming sufficient statistics avoid concatenating the entire cohort.
        count = sum(len(e["x"]) for e in events)
        total = sum(e["x"].double().sum(0) for e in events)
        squares = sum(e["x"].double().square().sum(0) for e in events)
        mu = (total / count).float()
        variance = ((squares - total.square() / count) / max(count - 1, 1)).clamp_min(0)
        sd = variance.sqrt().float() + 1e-6
    for event in events:
        event["x"] = (event["x"] - mu) / sd
    return mu, sd


def objective(model, event, device, curve_weight, pos_weight_cap, weighted=True, *, forward=sage_forward):
    logits, quantiles = forward(model, event, device)
    mask = ~event["persistence_pred"].bool().to(device)
    loss = logits.sum() * 0
    if mask.any():
        y = event["y"].float().to(device)[mask]
        weight = ((len(y) - y.sum()) / y.sum().clamp_min(1)).clamp(max=pos_weight_cap) if weighted else None
        if weighted and bool((y > .5).all()):
            weight = torch.ones((), device=device)  # A positive-only event still teaches membership.
        loss = F.binary_cross_entropy_with_logits(logits[mask], y, pos_weight=weight)
    future = torch.as_tensor(curve_forecast_mask(event), device=device)
    if curve_weight and future.any():
        loss = loss + curve_weight * pinball(quantiles[future], torch.log1p(event["curve"].float().to(device)[future]))
    return loss


def prediction_rows(model, events, device, threshold, *, forward=sage_forward):
    rows = []
    model.eval()
    with torch.no_grad():
        for event in events:
            started = time.perf_counter()
            logits, q = forward(model, event, device)
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            probability = torch.sigmoid(logits).cpu().numpy()
            candidates = event["asn"].tolist()
            seeds = sorted(map(int, event["seed_asns"].tolist()))
            chosen = sorted(set(seeds) | {int(a) for a, p in zip(candidates, probability) if p >= threshold})
            rows.append({"event_id": event["event_id"], "candidate_asns": candidates,
                         "probabilities": probability.tolist(), "seed_asns": seeds, "predicted_asns": chosen,
                         "curve_log_quantiles": q.cpu().tolist(), "threshold": threshold,
                         "observation_cutoff_s": float(event.get("observation_cutoff_s", event.get("delta_s", 30))),
                         "forward_seconds": time.perf_counter() - started})
    return rows


def calibrate_threshold(rows, events):
    """Validation-only full-target macro-Jaccard; ties prefer fewer false selections.

    The last grid point exceeds every probability, so seeds-only (persistence) is always an
    option, even when float32 sigmoids saturate to exactly 1.0 (logits above about 17).
    """
    thresholds = np.array([i / 100 for i in range(1, 101)] + [NO_ADDITIONS_THRESHOLD])
    total, count = np.zeros(len(thresholds)), np.zeros(len(thresholds))
    targets = {d["event_id"]: d for d in events}
    for row in rows:
        event = targets[row["event_id"]]
        candidates = np.asarray(event["asn"])
        seeds = set(map(int, np.asarray(event["seed_asns"])))
        truth = set(map(int, np.asarray(event["target_asns"])))
        nonseed = ~np.isin(candidates, list(seeds))
        positive = np.isin(candidates[nonseed], list(truth))
        selected = np.asarray(row["probabilities"])[nonseed, None] >= thresholds[None, :]
        hits = selected[positive].sum(axis=0)
        intersection = len(seeds & truth) + hits
        union = len(truth | seeds) + selected.sum(axis=0) - hits
        defined = union > 0
        total[defined] += intersection[defined] / union[defined]
        count[defined] += 1
    if not count.any():
        raise ValueError("Validation Jaccard is undefined for every threshold")
    values = np.divide(total, count, out=np.full_like(total, -np.inf), where=count > 0)
    best = np.flatnonzero(values == values.max())[-1]
    return float(thresholds[best]), float(values[best])


def reserve_output(path: Path):
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {path}")
    path.mkdir(parents=True, exist_ok=True)


def fit(manifest_path: Path, graph_dirs: list[Path], out: Path, *, message_passing="sage", history="on",
        seed=0, epochs=20, hid=64, layers=2, dropout=0.2, lr=1e-3, curve_weight=1.0,
        pos_weight_cap=20.0, curve_projection="cummax", device_name=None, input_gate=None,
        model_factory=MatchedSAGE, model_config=None, forward=sage_forward, extra_receipt=None):
    started = time.perf_counter()
    manifest = json.loads(manifest_path.read_text())
    validate_manifest(manifest)
    expected_hashes, gate_digest = input_gate_hashes(input_gate, manifest_path, manifest)
    training, tr_receipt = load_partition(manifest_path, manifest, "train", graph_dirs, expected_hashes=expected_hashes)
    validation, va_receipt = load_partition(manifest_path, manifest, "validation", graph_dirs, expected_hashes=expected_hashes)
    reserve_output(out)
    if epochs < 1:
        raise ValueError("epochs must be positive")
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    indices = manifest["history_feature_indices"]
    mu, sd = transform_events(training, indices, history)
    transform_events(validation, indices, history, mu, sd)
    n_types = int(manifest.get("n_edge_types", 3))
    for event in training + validation:
        if event["edge_type"].numel() and int(event["edge_type"].max()) >= n_types:
            raise ValueError("Manifest n_edge_types does not cover tensor relation types")
    settings = dict(in_dim=len(mu), hid=hid, n_types=n_types, layers=layers, dropout=dropout,
                    message_passing=message_passing, curve_projection=curve_projection)
    if model_config is not None:
        if 'in_dim' in model_config:
            raise ValueError('Model input dimension must come from training normalization')
        settings = dict(in_dim=len(mu), **model_config)
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    model = model_factory(**settings).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    best_loss, best_epoch, best_state, trace = float("inf"), None, None, []
    for epoch in range(1, epochs + 1):
        model.train()
        losses = []
        for index in np.random.permutation(len(training)):
            optimizer.zero_grad()
            loss = objective(model, training[index], device, curve_weight, pos_weight_cap, forward=forward)
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training objective")
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            validation_loss = float(np.mean([float(objective(model, e, device, curve_weight, pos_weight_cap, weighted=False, forward=forward))
                                             for e in validation]))
        if not np.isfinite(validation_loss):
            raise ValueError("Nonfinite validation objective")
        if validation_loss < best_loss:
            best_loss, best_epoch = validation_loss, epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        item = {"epoch": epoch, "training_loss": float(np.mean(losses)),
                "validation_loss": validation_loss, "elapsed_seconds": time.perf_counter() - started}
        trace.append(item)
        print(json.dumps(item), flush=True)
    model.load_state_dict(best_state)
    val_predictions = prediction_rows(model, validation, device, 0.5, forward=forward)
    threshold, validation_jaccard = calibrate_threshold(val_predictions, validation)
    for row in val_predictions:
        row["threshold"] = threshold
        row["predicted_asns"] = sorted(set(row["seed_asns"]) | {a for a, p in zip(row["candidate_asns"], row["probabilities"]) if p >= threshold})
    receipt = {"manifest_sha256": sha256(manifest_path), "input_gate_sha256": gate_digest, "source_sha256": sha256(Path(__file__)),
               "gnn_source_sha256": sha256(Path(__file__).with_name("gnn_train.py")),
               "graph_metrics_sha256": sha256(Path(__file__).with_name("graph_metrics.py")),
               "train_inputs": tr_receipt, "validation_inputs": va_receipt,
               "test_inputs_opened": False, "history_feature_indices": indices,
               "protocol": manifest.get("protocol"), "feature_contract": manifest.get("feature_contract"),
               "library_protocol": manifest.get("library_protocol"), "seed": seed,
               "history": history, "model": settings, "epochs": epochs, "selected_epoch": best_epoch,
               "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
               "selection_objective": "validation_event_mean_unweighted_bce_plus_curve_pinball",
               "lr": lr, "curve_weight": curve_weight, "pos_weight_cap": pos_weight_cap,
               "positive_only_event_weight": 1.0,
               "threshold": threshold, "threshold_grid": "0.01,...,1.00 plus 1.01 (no additions); highest threshold breaks ties",
               "threshold_calibration_split": "validation", "validation_jaccard": validation_jaccard,
               "torch_version": str(torch.__version__), "device": str(device),
               "hardware": torch.cuda.get_device_name(device) if device.type == "cuda" else "CPU",
               "elapsed_seconds": time.perf_counter() - started,
               "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated(device) if device.type == "cuda" else None,
               "gpu_peak_reserved_bytes": torch.cuda.max_memory_reserved(device) if device.type == "cuda" else None,
               "determinism": "fixed RNG seeds and deterministic cuDNN; CUDA scatter may remain nondeterministic",
               "trace": trace}
    if extra_receipt:
        if set(extra_receipt) & set(receipt):
            raise ValueError('Extension receipt must not override shared training evidence')
        receipt.update(extra_receipt)
    torch.save({"state_dict": best_state, "mu": mu, "sd": sd, "threshold": threshold,
                "settings": settings, "history": history, "history_feature_indices": indices,
                "receipt": receipt}, out / "checkpoint.pt")
    write_json(out / "validation_predictions.json", val_predictions)
    receipt["checkpoint_sha256"] = sha256(out / "checkpoint.pt")
    write_json(out / "fit_receipt.json", receipt)
    return receipt


def export_inputs(manifest_path: Path, graph_dirs: list[Path], out: Path):
    """Custodian-only export: copy permitted input fields, leaving labels at source.

    This operation reads test labels as serialized container bytes, so it belongs
    to the evidence custodian, never the protected model-development process.
    No target statistics are emitted. Existing graph/source files are untouched.
    """
    manifest = json.loads(manifest_path.read_text())
    validate_manifest(manifest)
    reserve_output(out)
    source_digest = sha256(manifest_path)
    allowed = INPUT_KEYS | {"history_provenance", "forecast_contract", "feature_contract", "library_protocol"}
    for row in manifest["events"]:
        if row["split"] != "test":
            continue
        path = graph_path(row, graph_dirs, manifest_path)
        expected = row.get("graph_sha256")
        if expected and expected != sha256(path):
            raise ValueError(f"Source checksum mismatch: {row['event_id']}")
        event = torch.load(path, map_location="cpu", weights_only=False)
        if event["event_id"] != row["event_id"]:
            raise ValueError("Source event ID mismatch")
        payload = {k: v for k, v in event.items() if k in allowed}
        target = out / f"{row['event_id']}.pt"
        torch.save(payload, target)
        row["input_path"] = str(target.resolve())
        row["input_sha256"] = sha256(target)
    # Source graph contracts refer to the original manifest bytes. This link is
    # explicit because adding label-free input paths necessarily changes bytes.
    manifest["source_manifest_sha256"] = manifest.get("source_manifest_sha256", source_digest)
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    write_json(out / "input_manifest.json", manifest)
    return {"input_manifest": str((out / "input_manifest.json").resolve()),
            "sha256": sha256(out / "input_manifest.json"), "source_manifest_sha256": source_digest}


def predict(checkpoint_path: Path, manifest_path: Path, graph_dirs: list[Path], out: Path, *,
            allow_label_containers=False, device_name=None, input_gate=None):
    manifest = json.loads(manifest_path.read_text())
    validate_manifest(manifest)
    if allow_label_containers and (manifest.get("protected_test", False) or manifest.get("locked_test", False)):
        raise ValueError("Protected tests require label-free inputs")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint["history_feature_indices"] != manifest["history_feature_indices"]:
        raise ValueError("Checkpoint/manifest history features differ")
    if checkpoint["receipt"].get("feature_contract") != manifest.get("feature_contract"):
        raise ValueError("Checkpoint/manifest feature contracts differ")
    expected_hashes, gate_digest = input_gate_hashes(input_gate, manifest_path, manifest)
    events, inputs = load_partition(manifest_path, manifest, "test", graph_dirs, prediction=True,
                                   allow_label_containers=allow_label_containers, expected_hashes=expected_hashes)
    reserve_output(out)
    transform_events(events, checkpoint["history_feature_indices"], checkpoint["history"], checkpoint["mu"], checkpoint["sd"])
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = MatchedSAGE(**checkpoint["settings"]).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    rows = prediction_rows(model, events, device, checkpoint["threshold"])
    write_json(out / "predictions.json", rows)
    commitment = {"created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "manifest_sha256": sha256(manifest_path), "input_gate_sha256": gate_digest,
                  "checkpoint_sha256": sha256(checkpoint_path),
                  "predictions_sha256": sha256(out / "predictions.json"), "inputs": inputs,
                  "event_ids": [r["event_id"] for r in rows], "test_labels_used": False,
                  "label_free_input_files": not allow_label_containers,
                  "prediction_source_sha256": sha256(Path(__file__))}
    write_json(out / "commitment.json", commitment)
    return commitment


def score(predictions_path: Path, commitment_path: Path, manifest_path: Path, graph_dirs: list[Path], out: Path, input_gate=None):
    """Explicit evaluator operation after batch unblinding; never called by fit/predict."""
    commitment = json.loads(commitment_path.read_text())
    if sha256(predictions_path) != commitment["predictions_sha256"]:
        raise ValueError("Prediction commitment mismatch")
    if sha256(manifest_path) != commitment["manifest_sha256"]:
        raise ValueError("Manifest changed after prediction commitment")
    manifest = json.loads(manifest_path.read_text())
    validate_manifest(manifest)
    if (manifest.get("protected_test", False) or manifest.get("locked_test", False)):
        raise ValueError("Protected test requires campaign-level one-batch evaluator; standalone score is disabled")
    expected_hashes, gate_digest = input_gate_hashes(input_gate, manifest_path, manifest)
    if gate_digest != commitment.get("input_gate_sha256"):
        raise ValueError("Prediction/scoring input gates differ")
    events, receipt = load_partition(manifest_path, manifest, "test", graph_dirs, expected_hashes=expected_hashes)
    prediction_list = json.loads(predictions_path.read_text())
    predictions = {r["event_id"]: r for r in prediction_list}
    if len(predictions) != len(prediction_list) or set(predictions) != {e["event_id"] for e in events}:
        raise ValueError("Prediction/target event IDs differ or duplicate")
    reserve_output(out)
    rows = []
    for event in events:
        row = predictions[event["event_id"]]
        if row["candidate_asns"] != event["asn"].tolist() or sorted(row["seed_asns"]) != sorted(event["seed_asns"].tolist()):
            raise ValueError(f"Prediction/target candidate or seed mismatch: {event['event_id']}")
        selected = np.asarray(row["probabilities"]) >= row["threshold"]
        result = membership_metrics(event, selected)
        truth = set(map(int, event["target_asns"]))
        seeds = set(row["seed_asns"])
        predicted = seeds | set(np.asarray(row["candidate_asns"])[selected].tolist())
        if predicted != set(row["predicted_asns"]):
            raise ValueError("Committed decision differs from probabilities/threshold")
        new_true, new_pred = truth - seeds, predicted - seeds
        tp = len(new_true & new_pred)
        result.update(new_tp=tp, new_fp=len(new_pred - truth), new_fn=len(new_true - new_pred),
                      new_precision=tp / len(new_pred) if new_pred else None,
                      new_recall=tp / len(new_true) if new_true else None,
                      new_f1=2 * tp / (len(new_pred) + len(new_true)) if new_pred or new_true else None,
                      no_growth=not new_true, empty_new_prediction=not new_pred)
        if "curve_log_quantiles" in row:
            quantiles = np.expm1(np.asarray(row["curve_log_quantiles"]))
            curve = np.asarray(event["curve"])
            future = np.asarray(CURVE_HORIZONS) > row["observation_cutoff_s"]
            result.update(curve_smape=float(np.mean(2 * np.abs(quantiles[future, 1] - curve[future]) /
                                                    np.maximum(np.abs(quantiles[future, 1]) + curve[future], 1e-9))) if future.any() else None,
                          curve_cover80=float(np.mean((curve[future] >= quantiles[future, 0]) & (curve[future] <= quantiles[future, 2]))) if future.any() else None)
        rows.append({"event_id": event["event_id"], **{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in result.items()}})
    write_json(out / "per_event.json", rows)
    summary = {"events": len(rows), "membership_target": "full_observed_2h",
               "jaccard_mean": float(np.mean([r["jaccard"] for r in rows])),
               "prediction_commitment_sha256": sha256(commitment_path), "label_inputs": receipt,
               "new_metric_empty_convention": "undefined precision/recall/F1 are null; no-growth counts reported separately"}
    write_json(out / "score_receipt.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("fit", "predict", "score", "export-inputs"):
        sub = commands.add_parser(name)
        sub.add_argument("--manifest", type=Path, required=True)
        sub.add_argument("--graphs", type=Path, action="append", default=[])
        sub.add_argument("--out", type=Path, required=True)
        if name != "export-inputs":
            sub.add_argument("--input-gate", type=Path)
        if name in ("fit", "predict"):
            sub.add_argument("--device", dest="device_name")
        if name == "fit":
            sub.add_argument("--message-passing", choices=("sage", "none"), default="sage")
            sub.add_argument("--history", choices=("on", "off"), default="on")
            for key, default in (("seed", 0), ("epochs", 20), ("hid", 64), ("layers", 2)):
                sub.add_argument("--" + key, type=int, default=default)
            for key, default in (("dropout", .2), ("lr", .001), ("curve-weight", 1.), ("pos-weight-cap", 20.)):
                sub.add_argument("--" + key, type=float, default=default)
            sub.add_argument("--curve-projection", choices=("cummax", "none"), default="cummax")
        elif name == "predict":
            sub.add_argument("--checkpoint", type=Path, required=True)
            sub.add_argument("--allow-label-containers", action="store_true",
                             help="Only for retrospective tests; protected tests always reject label-bearing input files")
        elif name == "score":
            sub.add_argument("--predictions", type=Path, required=True)
            sub.add_argument("--commitment", type=Path, required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    args["manifest_path"] = args.pop("manifest")
    args["graph_dirs"] = args.pop("graphs")
    for name in ("checkpoint", "predictions", "commitment"):
        if name in args:
            args[name + "_path"] = args.pop(name)
    result = {"fit": fit, "predict": predict, "score": score, "export-inputs": export_inputs}[command](**args)
    print(json.dumps({k: v for k, v in result.items() if k not in ("trace", "train_inputs", "validation_inputs", "inputs", "label_inputs")}), flush=True)


if __name__ == "__main__":
    main()
