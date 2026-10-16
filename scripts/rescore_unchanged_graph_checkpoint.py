"""Evaluate corrected test tensors only after exact training-input equivalence.

Normalization, weights, feature masks and the training-selected threshold are
retained. This does not tune a threshold or fit parameters on corrected test data.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil

import torch

from bgbench import config
from bgbench.gnn_train import TypedSAGE, load_splits, prospective_training_events, sage_forward, evaluate, bootstrap_diff
from rerun_graph_result import environment_versions
from audit_graph_boundary_inputs import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('original_summary', type=Path)
    parser.add_argument('training_proof', type=Path)
    args = parser.parse_args()
    old = json.loads(args.original_summary.read_text())
    proof = json.loads(args.training_proof.read_text())
    assert proof['training_equal'], 'Training tensors changed: checkpoint reuse is forbidden'
    prefix = args.original_summary.name.removesuffix('_summary.json')
    family, _, suffix = prefix.partition('_')
    year, tag, delta = old['years'], old['tag'], int(old['delta_s'])
    assert str(year).isdigit(), 'This bounded correction supports within-year origin cohorts only'
    folder = config.tgn_dir(int(year), delta, tag)
    assert Path(proof['after']).resolve() == folder.resolve()
    assert Path(proof['before']).resolve() == args.original_summary.parents[1].resolve()
    assert digest(folder / 'index.csv') == proof['index_after_sha256']
    assert digest(args.original_summary.parents[1] / 'index.csv') == proof['index_before_sha256']
    source = Path(__file__).resolve().parents[1] / 'src/bgbench'
    provenance = {'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'mode': 'inference_only_unchanged_training',
        'slurm_job_id': os.environ.get('SLURM_JOB_ID'), 'original_summary': str(args.original_summary),
        'original_summary_sha256': digest(args.original_summary), 'environment': environment_versions(),
        'training_equivalence_proof': str(args.training_proof), 'training_equivalence_sha256': digest(args.training_proof),
        'source_sha256': {p.name: digest(p) for p in source.glob('*.py')}, 'data_root': str(config.DATA_ROOT),
        'input_manifests_sha256': {str(folder / n): digest(folder / n) for n in ('index.csv', 'correction-impact.json', 'history-correction.json')}}
    checkpoint = args.original_summary.with_name(prefix + '_model.pt')
    ck = torch.load(checkpoint, weights_only=False, map_location='cpu')
    splits = load_splits(folder)
    training, protocol = prospective_training_events(splits['train'], splits['test'], year, tag)
    assert len(training) == old['train_events'] and protocol == old['split_protocol']
    for event in training:
        entry = proof['events'][event['event_id']]
        assert not entry['fields'] and digest(folder / (event['event_id'] + '.pt')) == entry['after_sha256']
    testing = splits['test']
    zero = [int(v) for v in suffix[1:].split('-')] if suffix.startswith('z') else []
    mu, sd = ck['mu'].cpu(), ck['sd'].cpu()
    for event in testing:
        if zero: event['x'][:, zero] = 0
        event['x'] = (event['x'] - mu) / sd
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    if family == 'sage':
        model = TypedSAGE(len(mu), old.get('hid', 64), n_types=ck['n_types'],
                          curve_head=old.get('curve_head', 'quantile'), separate_encoders=old.get('separate_encoders', False))
        forward = sage_forward
    elif family == 'gat':
        from bgbench.gat_train import GATMember
        model = GATMember(len(mu), old.get('hid', 64)); forward = sage_forward
    else:
        from bgbench.tgn_train import TGNMember, prepare
        from bgbench.dyrep_train import DyRepMember
        for event in testing: prepare(delta)(event)
        if family == 'tgn':
            model = TGNMember(len(mu), ck['state_dict']['memory.memory'].shape[0], old.get('mem', 64), old.get('hid', 64), n_types=ck['n_types'])
        elif family == 'dyrep':
            model = DyRepMember(len(mu), old.get('mem', 64), old.get('hid', 64), n_types=ck['n_types'])
        else: raise ValueError(family)
        forward = lambda m, event, target: m(event, target)
    model.load_state_dict(ck['state_dict']); model.to(device); model.eval()
    final = evaluate(model, testing, device, forward, threshold=ck['threshold'], save_probabilities=True)
    rows, probabilities = final.pop('_rows'), final.pop('_probabilities')
    clean = rows.filter(~rows['legacy_window_crosses_midnight'])
    final['same_day_replay_sensitivity'] = {'events': clean.height, 'excluded': rows.height - clean.height,
        'jaccard_model_tuned_mean': clean['jaccard_model_tuned'].mean(), 'jaccard_persist_mean': clean['jaccard_persist'].mean(),
        'diff_tuned_minus_persistence': bootstrap_diff(clean, 'jaccard_model_tuned', 'jaccard_persist')}
    for key, a, b in [('diff_tuned_minus_persistence', 'jaccard_model_tuned', 'jaccard_persist'),
                      ('diff_at05_minus_persistence', 'jaccard_model', 'jaccard_persist'),
                      ('diff_curve_smape_model_minus_persist', 'curve_smape_model', 'curve_smape_persist')]:
        final[key] = bootstrap_diff(rows, a, b)
    out = folder / '_results'; out.mkdir(exist_ok=True)
    for suffix_out in ('_model.pt', '_test_per_event.csv', '_summary.json', '_correction_run.json'):
        if (out / (prefix + suffix_out)).exists(): raise FileExistsError(out / (prefix + suffix_out))
    rows.write_csv(out / (prefix + '_test_per_event.csv'))
    torch.save(probabilities, out / (prefix + '_test_probs.pt'))
    shutil.copy2(checkpoint, out / (prefix + '_model.pt'))
    result = dict(old, final_test=final, test_events=len(testing), device=str(device),
                  correction='canonical_origin_membership_test_inference_only')
    result['history'] = [{k: v for k, v in row.items() if not k.startswith('test_')} for row in old.get('history', [])]
    result['original_per_epoch_test_metrics_omitted'] = True
    (out / (prefix + '_summary.json')).write_text(json.dumps(result, indent=2))
    provenance['checkpoint_sha256'] = digest(checkpoint)
    provenance['checkpoint_reused_without_modification'] = digest(out / (prefix + '_model.pt')) == digest(checkpoint)
    provenance['completed_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    provenance['environment']['torch_cuda_runtime'] = torch.version.cuda
    provenance['environment']['gpu'] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    for path, value in provenance['input_manifests_sha256'].items():
        assert digest(path) == value, f'Input manifest changed: {path}'
    assert provenance['source_sha256'] == {p.name: digest(p) for p in source.glob('*.py')}, 'Producer changed during inference'
    (out / (prefix + '_correction_run.json')).write_text(json.dumps(provenance, indent=2))
    print(json.dumps({'model': prefix, 'test_events': len(testing), 'checkpoint_reused': True}), flush=True)


if __name__ == '__main__':
    main()
