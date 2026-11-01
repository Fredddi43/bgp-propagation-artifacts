"""Separate new-period adapter around the unchanged reviewed scientific fit loop."""
import importlib.util
import json
from pathlib import Path

from . import forecast_train
from .forecast_manifest import file_sha, validate_development_manifest
from .forecast_release import authorize


def row_year(row):
    return int(row.get('year', str(row['event_id'])[:4]))


def expected_forecast_contract(manifest, year=None):
    """Exact core builder contract; extensions require a separately reviewed arm.

    A split-root manifest (declared ``history_root``) adds the two keys the builder records with a separate history
    root: the root itself and the data-root signature library of the event's construction year, which differs per year.
    """
    from .forecast_history import HISTORY_VERSION
    from .forecast_inputs import panel
    from .forecast_protocol import INPUT_CUTOFF_RULE_ID
    settings = manifest['construction']
    input_panel, reference_panel = (panel(manifest[key]) for key in ('input_collectors', 'reference_collectors'))
    return {'history_mode': 'shared_completed', 'history_version': HISTORY_VERSION,
            'history_source_digest': manifest['history_source_digest'], 'history_frozen_at': None,
            'cohort_mode': 'broad', 'manifest_sha256': manifest['source_manifest_sha256'],
            'delta_s': manifest['delta_s'], 'tag': settings['tag'], 'max_nodes': settings['max_nodes'],
            'topology_lag_months': settings['topology_lag_months'], 'rov_lag_days': settings['rov_lag_days'],
            'input_collectors': None if input_panel == 'pooled' else input_panel,
            'reference_collectors': None if reference_panel == 'pooled' else reference_panel,
            'history_target_scope': 'legacy_input_collectors' if reference_panel == 'pooled' else 'fixed_reference_collectors',
            'early_filter_inputs': False, 'input_cutoff_rule': INPUT_CUTOFF_RULE_ID,
            **_split_root_contract(manifest, year)}


def _split_root_contract(manifest, year):
    if manifest.get('history_root') is None:
        return {}
    digest = (manifest.get('signature_source_digests') or {}).get(str(year))
    if digest is None:
        raise ValueError(f'No signature-library digest declared for year {year}')
    return {'history_root': manifest['history_root'], 'signature_source_digest': digest}


def isolated_core():
    """A private module namespace; never replace the imported trainer's globals."""
    spec = importlib.util.spec_from_file_location('bgbench._development_fit_core', forecast_train.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_manifest = validate_development_manifest
    original_loader = module.load_partition

    def validated_load_partition(manifest_path, manifest, split, graph_dirs, **kwargs):
        # The original loader hashes and deserializes the same bytes and checks
        # supervised labels. Validate those exact objects before normalization;
        # retain the original labels/objects for the unchanged scientific loop.
        from .forecast_inputs import allowed_keys, validate_tensor
        events, receipt = original_loader(manifest_path, manifest, split, graph_dirs, **kwargs)
        rows = {row['event_id']: row for row in manifest['events'] if row['split'] == split}
        for event in events:
            # Development manifests historically have no resource capacity cap.
            # Enforce an explicit cap when present; do not invent one from the
            # builder candidate cap, which may be exceeded by observed seeds.
            contract = dict(manifest, input_profile='core',
                            max_nodes=manifest.get('max_nodes', len(event['asn'])))
            payload = {key: value for key, value in event.items() if key in allowed_keys('core')}
            validate_tensor(payload, rows[event['event_id']], contract)
            year = row_year(rows[event['event_id']]) if manifest.get('history_root') is not None else None
            expected = expected_forecast_contract(manifest, year)
            if event['forecast_contract'] != expected:
                raise ValueError('Tensor construction contract differs from guarded builder')
            provenance = event['history_provenance']
            if provenance.get('source_digest') != manifest['history_source_digest']:
                raise ValueError('Tensor history source differs from audited construction')
            if (provenance.get('history_root') != expected.get('history_root')
                    or provenance.get('signature_source_digest') != expected.get('signature_source_digest')):
                raise ValueError('Tensor history provenance differs from the declared history root')
        return events, receipt

    module.load_partition = validated_load_partition
    return module


def fit(manifest_path, graph_dirs, out, *, input_gate, retrospective_release, expected_gate_sha256, **settings):
    manifest_path, input_gate = Path(manifest_path), Path(input_gate)
    authorization = authorize(manifest_path, operation='core_fit', input_gate=input_gate,
                              expected_gate_sha256=expected_gate_sha256, retrospective_release=retrospective_release)
    manifest = json.loads(manifest_path.read_text())
    validate_development_manifest(manifest)
    gate = json.loads(input_gate.read_text())
    if 'construction_manifest_path' in manifest:
        original = Path(manifest['construction_manifest_path'])
        if file_sha(original) != manifest['source_manifest_sha256']:
            raise ValueError('Original construction manifest changed')
        construction = json.loads(original.read_text())
        if any(construction.get(key) != manifest[key] for key in ('construction', 'history_source_digest')):
            raise ValueError('Development construction binding changed')
    if gate.get('passed') is not True or gate.get('manifest_kind') != 'development':
        raise ValueError('A reviewed development integration gate is required')
    if gate.get('task_protocol_sha256') != manifest['task_protocol_sha256']:
        raise ValueError('Development task protocol differs from integration gate')
    from .forecast_inputs import validate_status_receipt, source_inventory
    inventory = None
    if manifest.get('excluded_inputs'):
        inventory = source_inventory(gate['source_inventory_path'], gate['source_inventory_sha256'],
                                     manifest['reference_population_sha256'], manifest['task_protocol_sha256'], manifest)
    for row in manifest.get('excluded_inputs', []):
        status_path = Path(row['status_receipt_path'])
        if file_sha(status_path) != row['status_receipt_sha256']:
            raise ValueError('Retained input-status evidence changed')
        validate_status_receipt(json.loads(status_path.read_text()), row, inventory)
    release = authorization['release_sha256']
    forbidden = {'model_factory', 'forward', 'extra_receipt', 'model_config'} & set(settings)
    if forbidden:
        raise ValueError('Development core adapter does not accept unreviewed model hooks')
    evidence = {'development_adapter_sha256': file_sha(__file__),
                'development_validator_sha256': file_sha(Path(__file__).with_name('forecast_manifest.py')),
                'retrospective_release_sha256': release, 'release_authorization': authorization,
                'task_protocol_sha256': manifest['task_protocol_sha256'],
                'reference_population_sha256': manifest['reference_population_sha256'],
                'calibration_excludes_flagged_abstentions': True,
                'scientific_loop': 'unchanged reviewed trainer in isolated namespace; manifest and loaded input projection validated before normalization',
                'input_validator_sha256': file_sha(Path(__file__).with_name('forecast_inputs.py'))}
    return isolated_core().fit(manifest_path, graph_dirs, Path(out), input_gate=input_gate,
                               extra_receipt=evidence, **settings)


def main(argv=None):
    """``python -m bgbench.forecast_development fit``: the guarded new-period core fit, one run per call.

    The same scientific options as ``bgbench.forecast_train fit``; the release guard (`authorize`) runs inside
    `fit` before any tensor is opened, so an absent or incomplete release fails before output.
    """
    import argparse
    parser = argparse.ArgumentParser(description=main.__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    sub = commands.add_parser('fit')
    sub.add_argument('--manifest', type=Path, required=True)
    sub.add_argument('--out', type=Path, required=True)
    sub.add_argument('--input-gate', type=Path, required=True)
    sub.add_argument('--expected-gate-sha256', required=True)
    sub.add_argument('--retrospective-release', type=Path, required=True)
    sub.add_argument('--device', dest='device_name')
    sub.add_argument('--message-passing', choices=('sage', 'none'), required=True)
    sub.add_argument('--history', choices=('on', 'off'), required=True)
    for key, default in (('seed', 0), ('epochs', 20), ('hid', 64), ('layers', 2)):
        sub.add_argument('--' + key, type=int, default=default)
    for key, default in (('dropout', .2), ('lr', .001), ('curve-weight', 1.), ('pos-weight-cap', 20.)):
        sub.add_argument('--' + key, type=float, default=default)
    sub.add_argument('--curve-projection', choices=('cummax', 'none'), default='cummax')
    args = vars(parser.parse_args(argv))
    args.pop('command')
    manifest = args.pop('manifest')
    out = args.pop('out')
    result = fit(manifest, [], out, **args)
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('trace', 'train_inputs', 'validation_inputs', 'release_authorization')}), flush=True)
    return result


def build_graphs(manifest_path, out, *, input_gate, expected_gate_sha256, retrospective_release):
    """Guarded production construction adapter, using the existing real builder.

    Writes a development manifest and authorization receipt, never a passed input
    gate. A separate audit must approve the constructed bytes before fitting.
    """
    from .forecast_manifest import seal_manifest
    authorization = authorize(manifest_path, operation='supervised_graph_build', input_gate=input_gate,
                              expected_gate_sha256=expected_gate_sha256, retrospective_release=retrospective_release)
    manifest = json.loads(Path(manifest_path).read_text())
    gate = json.loads(Path(input_gate).read_text())
    from . import tgn_data
    if Path(gate['data_root']).resolve() != tgn_data.config.DATA_ROOT.resolve():
        raise ValueError('Configured source root differs from audited construction gate')
    # A separate original-history root (TARGET-CONSISTENCY-POLICY v6) is declared by the manifest and certified by the
    # gate; it must be a real second root, because one equal to the data root silently builds single-root tensors.
    history_root = manifest.get('history_root')
    if gate.get('history_root') != history_root:
        raise ValueError('Gate and manifest declare different history roots')
    if history_root is not None and (Path(history_root).resolve() != Path(history_root)
                                     or Path(history_root) == tgn_data.config.DATA_ROOT.resolve()):
        raise ValueError('Declared history root must be resolved and differ from the data root')
    settings = manifest['construction']
    if set(settings) != {'tag', 'max_nodes', 'history_years', 'topology_lag_months', 'rov_lag_days'}:
        raise ValueError('Undeclared construction settings')
    if manifest['feature_contract']['width'] != tgn_data.feature_width(settings['tag']):
        raise ValueError('Feature contract width differs from real builder schema')
    from .forecast_inputs import panel
    panels = {key: panel(manifest[key]) for key in ('input_collectors', 'reference_collectors')}
    years = sorted({int(row['year']) for row in manifest['events']})
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    signatures = {}
    (out/'release-authorization.json').write_text(json.dumps(authorization, indent=2)+'\n')
    built = {}
    for year in years:
        directory = out / str(year)
        tgn_data.build_split(year=year, delta_s=manifest['delta_s'], history_mode='shared_completed',
            cohort_mode='broad', manifest_path=Path(manifest_path), output_dir=directory,
            input_collectors=None if panels['input_collectors'] == 'pooled' else tuple(panels['input_collectors']),
            reference_collectors=None if panels['reference_collectors'] == 'pooled' else tuple(panels['reference_collectors']),
            history_root=Path(history_root) if history_root is not None else None, **settings)
        history = json.loads((directory/'history_sources.json').read_text())
        if history['source_digest'] != manifest['history_source_digest']:
            raise ValueError('Built history sources differ from audited construction')
        if history_root is not None:
            built_contract = json.loads((directory/'forecast_contract.json').read_text())
            if built_contract.get('history_root') != history_root:
                raise ValueError('Builder did not use the declared history root')
            signatures[str(year)] = built_contract['signature_source_digest']
        for row in manifest['events']:
            if int(row['year']) != year:
                continue
            graph = directory / (row['event_id']+'.pt')
            if not graph.exists():
                raise ValueError('Construction did not retain a supervised reference ID: '+row['event_id'])
            built[row['event_id']] = dict(row, graph_path=str(graph.resolve()), graph_sha256=file_sha(graph))
    development = dict(manifest, manifest_kind='development', source_manifest_sha256=file_sha(manifest_path),
                       events=[built[row['event_id']] for row in manifest['events']],
                       construction_manifest_path=str(Path(manifest_path).resolve()),
                       **({'signature_source_digests': signatures} if history_root is not None else {}))
    development = seal_manifest(development)
    validate_development_manifest(development)
    path = out/'development_manifest.json'
    path.write_text(json.dumps(development, indent=2)+'\n')
    receipt = {'manifest_path': str(path), 'manifest_sha256': file_sha(path), 'graphs': len(built),
               'release_authorization_sha256': file_sha(out/'release-authorization.json'),
               'builder_source_sha256': file_sha(tgn_data.__file__), 'adapter_source_sha256': file_sha(__file__)}
    (out/'construction-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


if __name__ == "__main__":
    main()
