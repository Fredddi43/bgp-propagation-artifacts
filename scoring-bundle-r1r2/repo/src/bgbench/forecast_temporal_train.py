"""Temporal fit adapter using the unchanged core loss, normalization and selection loop.

This entry point fits development train/validation only. Protected prediction
requires its own reviewed temporal input export; the core SAGE predictor cannot
load these checkpoints. No temporal campaign is implicitly dispatched here.
"""
from __future__ import annotations

import argparse
import json
import hashlib
import inspect
from pathlib import Path

import torch
import torch_geometric

from . import forecast_temporal, forecast_train


CONFIGURATIONS = {index: {'hidden': hidden, 'lr': lr}
                  for index, (hidden, lr) in enumerate(
                      ((hidden, lr) for hidden in (32, 64) for lr in (.001, .0003, .0001)), start=1)}


SUPPORTED_PYG_VERSIONS = ('2.8.0.post1', '2.8.1')
PYG_API_SHA256 = {'TGNMemory': 'fc1c5503c4f66b3033bf22bb59cfbcf7162d622cc83d79e7d41370b31a5152e6', 'LastNeighborLoader': '641f7b2b1173f08d1b7c88fd3cea1d29902c8b28645ab3d317c20fb72d6092e8', 'IdentityMessage': '28f5bf62d1710a686691848cc52ab605f819a581677fd1928a4bd84944ac7988', 'LastAggregator': '33d77ab6c899529cf9514aaeee077fbbc2ac5a334fa7fe84d296c43f1e952386', 'TransformerConv': '0f682929439fd962e66ccfe2513cc1b647048faa76e01b0dbb35fa0401625901', 'MeanAggregation': 'caac4f4da1d886783ea51c30030a1b13addd6255bf203206fb98250cff1df29b', 'scatter_module': '14fb794f8d706e0d2294b32d01c251e12c0faa5c43ae30ea3bb2a003e6276f0a', 'softmax_module': '057d3ac17c52abe055b6fba6368c95f064bdaadb16258c0dac50054498efe1c5'}


def check_pyg_version():
    from torch_geometric.nn.models.tgn import TGNMemory, LastNeighborLoader, IdentityMessage, LastAggregator
    from torch_geometric.nn import TransformerConv
    from torch_geometric.nn.aggr import MeanAggregation
    import torch_geometric.utils._scatter as scatter_module
    import torch_geometric.utils._softmax as softmax_module
    if torch_geometric.__version__ not in SUPPORTED_PYG_VERSIONS:
        raise ValueError('Temporal private PyG API requires audited PyG 2.8.0.post1 or 2.8.1')
    objects = dict(TGNMemory=TGNMemory, LastNeighborLoader=LastNeighborLoader, IdentityMessage=IdentityMessage,
                   LastAggregator=LastAggregator, TransformerConv=TransformerConv, MeanAggregation=MeanAggregation,
                   scatter_module=scatter_module, softmax_module=softmax_module)
    hashes = {name: hashlib.sha256(inspect.getsource(obj).encode()).hexdigest() for name, obj in objects.items()}
    if hashes != PYG_API_SHA256:
        raise ValueError('Installed PyG implementation differs from the audited private API')
    return torch_geometric.__version__


def make_model(*, kind, in_dim, hidden=64, dropout=.2, bins=16,
               max_nodes=3000, memory_dim=64, time_dim=16, neighbors=10):
    if kind == 'gru':
        return forecast_temporal.EventGRU(in_dim, hidden=hidden, bins=bins, dropout=dropout)
    if kind == 'tgn':
        return forecast_temporal.EventTGN(in_dim, max_nodes, hidden=hidden, memory_dim=memory_dim,
                                          time_dim=time_dim, neighbors=neighbors, dropout=dropout)
    raise ValueError('Unknown temporal architecture')


def temporal_forward(model, event, device):
    return model(event, device)


def fit(manifest_path, graph_dirs, out, *, kind, input_audit=None, input_gate=None,
        hidden=64, dropout=.2, bins=16, memory_dim=64, time_dim=16, neighbors=10,
        seed=0, epochs=20, lr=.001, curve_weight=1., pos_weight_cap=20., device_name=None,
        configuration_id=None):
    pyg_version = check_pyg_version()
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    forecast_train.validate_manifest(manifest)
    if configuration_id is not None:
        if configuration_id not in CONFIGURATIONS:
            raise ValueError('Unknown temporal configuration')
        hidden, lr = CONFIGURATIONS[configuration_id]['hidden'], CONFIGURATIONS[configuration_id]['lr']
    if manifest.get('schema_version', 0) >= 1:
        if configuration_id is None:
            raise ValueError('Production temporal fits require a prespecified configuration ID')
        if (dropout, bins, memory_dim, time_dim, neighbors, curve_weight, pos_weight_cap, epochs) != (.2, 16, 64, 16, 10, 1., 20., 20):
            raise ValueError('Production temporal settings differ from the frozen grid')
        if seed not in range(5):
            raise ValueError('Production temporal seeds are frozen to 0 through 4')
    capacity = 3000
    audit_sha = None
    if input_audit is not None:
        audit = json.loads(Path(input_audit).read_text())
        if audit.get('passed') is not True or audit['manifest_sha256'] != forecast_train.sha256(manifest_path):
            raise ValueError('Temporal input audit does not bind this manifest')
        capacity = audit['capacity_max_train_validation_nodes']
        audit_sha = forecast_train.sha256(Path(input_audit))
    elif manifest.get('schema_version', 0) >= 1:
        raise ValueError('Production temporal fits require a reviewed input audit')
    torch.use_deterministic_algorithms(True)
    settings = dict(kind=kind, hidden=hidden, dropout=dropout)
    settings.update({'bins': bins} if kind == 'gru' else
                    {'max_nodes': capacity, 'memory_dim': memory_dim, 'time_dim': time_dim, 'neighbors': neighbors})
    evidence = {'temporal_source_sha256': forecast_train.sha256(Path(forecast_temporal.__file__)),
                'temporal_adapter_sha256': forecast_train.sha256(Path(__file__)),
                'temporal_configuration_id': configuration_id,
                'temporal_pyg_version': pyg_version,
                'temporal_pyg_api_sha256': PYG_API_SHA256,
                'temporal_determinism_scope': 'strict algorithms; GPU eval forwards bitwise verified; training repeat equality unproven',
                'temporal_input_audit_sha256': audit_sha,
                'temporal_objective': 'shared supervised membership and extent; not original link prediction',
                'temporal_deterministic_algorithms': True,
                'temporal_ties': 'latest tick; incoming role; greatest canonical counterpart',
                'temporal_memory_scope': 'reset every event; shared matured history enters both readouts'}
    try:
        return forecast_train.fit(manifest_path, graph_dirs, Path(out), seed=seed, epochs=epochs,
            lr=lr, curve_weight=curve_weight, pos_weight_cap=pos_weight_cap, device_name=device_name,
            input_gate=input_gate, history='on', model_factory=make_model, model_config=settings,
            forward=temporal_forward, extra_receipt=evidence)
    except ValueError as error:
        if str(error) not in ('Nonfinite training objective', 'Nonfinite validation objective'):
            raise
        failure = dict(evidence, status='numerical_failure', reason=str(error), seed=seed,
                       model=settings, lr=lr, epochs=epochs, test_inputs_opened=False,
                       source_sha256=forecast_train.sha256(Path(forecast_train.__file__)),
                       manifest_sha256=forecast_train.sha256(manifest_path),
                       input_gate_sha256=forecast_train.sha256(Path(input_gate)) if input_gate else None)
        Path(out).mkdir(parents=True, exist_ok=True)
        with (Path(out) / 'numerical_failure.json').open('x') as handle:
            json.dump(failure, handle, indent=2, allow_nan=False)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', dest='manifest_path', type=Path, required=True)
    parser.add_argument('--graphs', dest='graph_dirs', type=Path, action='append', default=[])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--kind', choices=('gru', 'tgn'), required=True)
    parser.add_argument('--configuration-id', type=int, choices=tuple(CONFIGURATIONS), required=True)
    parser.add_argument('--input-audit', type=Path, required=True)
    parser.add_argument('--input-gate', type=Path, required=True)
    parser.add_argument('--device', dest='device_name')
    for key, value in [('hidden', 64), ('bins', 16), ('memory-dim', 64), ('time-dim', 16),
                       ('neighbors', 10), ('seed', 0), ('epochs', 20)]:
        parser.add_argument('--' + key, type=int, default=value)
    for key, value in [('dropout', .2), ('lr', .001), ('curve-weight', 1.), ('pos-weight-cap', 20.)]:
        parser.add_argument('--' + key, type=float, default=value)
    receipt = fit(**vars(parser.parse_args()))
    print(json.dumps({k: receipt[k] for k in ('model', 'selected_epoch', 'threshold', 'trainable_parameters')}))
