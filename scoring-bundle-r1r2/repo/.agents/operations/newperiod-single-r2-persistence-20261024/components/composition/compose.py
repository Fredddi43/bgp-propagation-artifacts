"""Prepare reviewed secondary components, then share one original label opening.

Partial family coverage only; no execution authority or operational launcher.
The owner supplies exact admitted original modules and bounded logged readers.
"""
import hashlib
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPONENTS = {
    'stable': ('components/stable/consumer.py', 'deb124b1931cfa36f0dff0fdc3a2a4d592edbd2147c0d662e44986c09aabb712'),
    'count': ('components/count/evaluate.py', '52ad01ae9b7b1c0e3bf7fda4261672540dee282c91ebd18bae5c7ddf7a20c625'),
    'membership': ('components/membership/consumer.py', '2f40bf28ea95bf69df378c81fc1c57abacf306f9be59a55028397a70be36e006'),
}
FAMILIES = ('h1', 'h3', 'timing', 'history', 'ordinary')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def components():
    """Compile the exact read-once reviewed sources, never their cached bytecode."""
    result = {}
    for name, (relative, expected) in COMPONENTS.items():
        path = HERE / relative
        raw = path.read_bytes()
        need(hashlib.sha256(raw).hexdigest() == expected, 'Reviewed component changed: ' + name)
        module = types.ModuleType('secondary_composition_' + name)
        module.__file__ = str(path)
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        result[name] = module
    return result


def evaluate(original, primary_args, primary_kwargs, *, custody, seal, count_freeze,
             membership_freezes, evidence, stable_freeze, stable_evidence, read_json, read_input, original_score_curves):
    """All preflight first; the original evaluator remains the sole label reader.

    Inputs here are already bound to the actual owner packet. All five fixed
    membership families are required, including retained failure records. The
    unchanged original whole-batch authorization still rechecks the actual seal.
    """
    need(set(membership_freezes) == set(evidence) == set(FAMILIES),
         'Exactly five declared membership family components required')
    anchored_seal = read_json({'path': str(primary_args[0]), 'sha256': primary_args[1]},
                              'composition original sealed batch')
    need(anchored_seal == seal, 'Composition seal differs from original batch')
    anchored_custody = read_json({'path': seal['spec_path'], 'sha256': seal['spec_sha256']},
                                 'composition original custody freeze')
    need(anchored_custody == custody, 'Composition custody differs from original batch')
    modules = components()
    counts, members = modules['count'], modules['membership']
    prepared_counts = counts.prepare_counts(custody, seal, count_freeze, read_json)
    prepared_members = {
        family: members.prepare_sealed(family, custody, seal, membership_freezes[family],
                                       evidence[family], read_json, read_input)
        for family in FAMILIES
    }
    prepared_stable = modules['stable'].prepare_sealed(
        custody, seal, stable_freeze, stable_evidence, read_json, read_input)
    # Reuse the reviewed private-module mechanism. The count wrapper creates
    # its own private copy too; neither copy mutates the original module.
    private = counts.private_primary(original)
    original_reader = private.bound_json
    captured = []

    def capture(path, sha, purpose):
        if purpose == 'Custodian label table':
            need(not captured, 'Second label opening refused')
        value = original_reader(path, sha, purpose)
        if purpose == 'Custodian label table':
            captured.append(value)
        return value

    private.bound_json = capture
    primary, count_report = counts.evaluate_with_counts(
        private, primary_args, primary_kwargs, prepared_counts, original_score_curves)
    need(len(captured) == 1, 'Original single label return missing')
    membership = {family: members.evaluate(prepared_members[family], captured[0])
                  for family in FAMILIES}
    return {'kind': 'newperiod_partial_secondary_composition_v1', 'primary': primary,
            'counts': count_report, 'membership': membership,
            'stable': modules['stable'].evaluate(prepared_stable, captured[0]['stable']),
            'covered_secondary_families': ['counts', *FAMILIES, 'stable'],
            'full_newperiod_coverage': False, 'actual_execution_authorized': False}
