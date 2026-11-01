"""Reporting gate for the mandatory history-withholding sensitivity.

``require_sensitivity_for_reporting`` refuses to release evaluation numbers unless the
receipts exist and bind to the frozen spec: one input-only impact report per primary
horizon (``forecast_history_sensitivity_report.impact_report``, 30 s and 60 s, k=20) and a
frozen-model sensitivity receipt that names both reports. The gate reads receipts and the
spec only. It never reads, accepts or inspects scores, targets or labels.

The reports' ``report_sha256`` is a self-hash, so it proves only internal consistency.
What ties a report to the evaluation being released are values the *caller* supplies
from its own inputs: the history-library digest the evaluated tensors were built from,
and the exact cohort of event IDs being reported. Every report must cover exactly that
cohort with that library, and the frozen-model receipt must name the same cohort hash,
library digest and both report hashes.

Spec revisions: the original ``HISTORY-SENSITIVITY-SPEC.json`` is accepted as is. A spec
that declares ``spec_version`` other than 1, or carries ``revision``/``supersedes``, is
accepted only if its revision binding verifies (``verify_revision``): the superseded
spec file and the revision note match their pinned SHA256, the policy fields are
identical, and only the evidence pins listed as re-pinned differ.

Wired into ``scripts/forecast_comparisons.py`` (the retrospective contrast report). The
gate does not verify that the frozen-model sensitivity was computed correctly, only that
its receipt is complete, bound to this spec, library and cohort, and consistent with the
impact reports.
"""
import hashlib
import json
from pathlib import Path

from .forecast_history_sensitivity_report import REPORT_KIND, SCOPE, _sha

FROZEN_MODEL_KIND = 'history_withholding_frozen_model_sensitivity'
HEX64 = frozenset('0123456789abcdef')
REQUIRED_K = 20
REQUIRED_HORIZONS = (30, 60)
# Fields that define the policy; a revision may not change any of them.
POLICY_FIELDS = ('kind', 'withheld_event_ids', 'rule', 'not_withheld', 'primary',
                 'recovered_2024_proof', 'consumers_to_apply_identically', 'retraining_fits',
                 'transfer_training_membership', 'scope', 'policy_sha256', 'executor')


class SensitivityGateError(ValueError):
    pass


def _hex64(value, name):
    if not isinstance(value, str) or len(value) != 64 or set(value) - HEX64:
        raise SensitivityGateError(f'{name} must be a SHA256 hex digest')
    return value


def _file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cohort_ids_sha256(event_ids):
    ids = sorted(event_ids)
    if len(set(ids)) != len(ids) or not ids:
        raise SensitivityGateError('Cohort event IDs must be non-empty and unique')
    return hashlib.sha256('\n'.join(ids).encode()).hexdigest()


def _basic_spec(spec):
    for key in ('policy_sha256', 'withheld_event_ids', 'retraining_fits'):
        if key not in spec:
            raise SensitivityGateError(f'Spec lacks {key}')
    _hex64(spec['policy_sha256'], 'spec policy_sha256')
    if spec['retraining_fits'] != 0 or not spec['withheld_event_ids']:
        raise SensitivityGateError('Spec must withhold donors with zero retraining fits')


def _is_revision(spec):
    return spec.get('spec_version', 1) != 1 or 'revision' in spec or 'supersedes' in spec


def verify_revision(spec, spec_path):
    """Check a revised spec against the superseded spec it names. Returns the binding."""
    revision = spec.get('revision')
    if not isinstance(revision, dict):
        raise SensitivityGateError('Revised spec lacks its revision binding')
    base = Path(spec_path).resolve().parent
    previous = revision.get('supersedes') or {}
    note = revision.get('note') or {}
    for name, ref in (('superseded spec', previous), ('revision note', note)):
        if not ref.get('path') or Path(ref['path']).is_absolute() or '..' in Path(ref['path']).parts:
            raise SensitivityGateError(f'Revision binding needs a relative {name} path')
        path = base / ref['path']
        if not path.is_file() or _file_sha(path) != _hex64(ref.get('sha256'), f'{name} sha256'):
            raise SensitivityGateError(f'{name} does not match its pinned SHA256')
    old = json.loads((base / previous['path']).read_text())
    if _is_revision(old):
        raise SensitivityGateError('A revision must supersede the original frozen spec')
    _basic_spec(old)
    for field in POLICY_FIELDS:
        if old.get(field) != spec.get(field):
            raise SensitivityGateError(f'Revision changes policy field {field}')
    repinned = revision.get('repinned') or {}
    if not repinned:
        raise SensitivityGateError('Revision names no re-pinned evidence')
    old_files, new_files = old.get('evidence_files', {}), spec.get('evidence_files', {})
    if set(old_files) != set(new_files):
        raise SensitivityGateError('Revision adds or drops evidence files')
    changed = {k for k in old_files if old_files[k] != new_files[k]}
    if changed != set(repinned):
        raise SensitivityGateError('Evidence pins changed beyond the declared re-pins')
    for name, pins in repinned.items():
        if (pins.get('original_sha256') != old_files[name] or pins.get('new_sha256') != new_files[name]
                or pins.get('original_bytes_recovered') is not False):
            raise SensitivityGateError(f'Re-pin record for {name} is inconsistent')
    if revision.get('originals_lost') is not True:
        raise SensitivityGateError('Revision must record that the original evidence bytes were lost')
    return {'superseded_spec_sha256': previous['sha256'], 'revision_note_sha256': note['sha256']}


def load_spec(spec_path):
    raw = Path(spec_path).read_bytes()
    spec = json.loads(raw)
    _basic_spec(spec)
    if _is_revision(spec):
        verify_revision(spec, spec_path)
    return spec, hashlib.sha256(raw).hexdigest()


def _load(receipt):
    return receipt if isinstance(receipt, dict) else json.loads(Path(receipt).read_text())


def verify_input_impact_report(report, spec_path, *, delta_s=None, library_digest=None, cohort_event_ids=None):
    spec, spec_sha = load_spec(spec_path)
    report = _load(report)
    if report.get('kind') != REPORT_KIND or report.get('scope') != SCOPE:
        raise SensitivityGateError('Not an input-only impact report')
    claimed = report.get('report_sha256')
    body = {k: v for k, v in report.items() if k != 'report_sha256'}
    if _sha(body) != _hex64(claimed, 'report_sha256'):
        raise SensitivityGateError('Impact report hash does not match its content')
    if report.get('policy_sha256') != spec['policy_sha256']:
        raise SensitivityGateError('Impact report is bound to a different policy')
    if report.get('spec_sha256') != spec_sha:
        raise SensitivityGateError('Impact report is bound to a different spec file')
    ids = sorted(spec['withheld_event_ids'])
    if report.get('withheld_ids') != ids or report.get('withheld_ids_sha256') != hashlib.sha256(
            '\n'.join(ids).encode()).hexdigest():
        raise SensitivityGateError('Impact report withheld a different donor set')
    if report.get('retraining_fits') != 0:
        raise SensitivityGateError('Impact report claims retraining')
    if not report.get('rows') or report['aggregate'].get('queries') != len(report['rows']):
        raise SensitivityGateError('Impact report has no queries or inconsistent aggregate')
    if report.get('k') != REQUIRED_K:
        raise SensitivityGateError(f'Impact report must use k={REQUIRED_K}')
    if delta_s is not None and report.get('delta_s') != delta_s:
        raise SensitivityGateError(f'Impact report is not for the {delta_s}s horizon')
    if library_digest is not None and report.get('library_digest') != library_digest:
        raise SensitivityGateError('Impact report used a different history library')
    if cohort_event_ids is not None:
        queried = [r.get('query_event_id') for r in report['rows']]
        if len(set(queried)) != len(queried) or sorted(queried) != sorted(cohort_event_ids):
            raise SensitivityGateError('Impact report does not cover exactly the reported cohort')
    return claimed


def verify_frozen_model_receipt(receipt, spec_path, reports, *, library_digest, cohort_sha256):
    spec, spec_sha = load_spec(spec_path)
    receipt = _load(receipt)
    if receipt.get('kind') != FROZEN_MODEL_KIND:
        raise SensitivityGateError('Not a frozen-model sensitivity receipt')
    if receipt.get('policy_sha256') != spec['policy_sha256'] or receipt.get('spec_sha256') != spec_sha:
        raise SensitivityGateError('Frozen-model receipt is bound to a different policy or spec')
    ids = sorted(spec['withheld_event_ids'])
    if receipt.get('withheld_ids') != ids:
        raise SensitivityGateError('Frozen-model receipt withheld a different donor set')
    if receipt.get('retraining_fits') != 0:
        raise SensitivityGateError('Frozen-model sensitivity must use zero retraining fits')
    expected = {str(h): _load(r).get('report_sha256') for h, r in reports.items()}
    if receipt.get('input_impact_report_sha256') != expected:
        raise SensitivityGateError('Frozen-model receipt does not name these impact reports')
    if receipt.get('library_digest') != library_digest:
        raise SensitivityGateError('Frozen-model receipt used a different history library')
    if receipt.get('cohort_ids_sha256') != cohort_sha256:
        raise SensitivityGateError('Frozen-model receipt covers a different cohort')
    _hex64(receipt.get('frozen_model_ledger_sha256'), 'frozen_model_ledger_sha256')
    _hex64(receipt.get('results_sha256'), 'results_sha256')
    return receipt['results_sha256']


def require_sensitivity_for_reporting(spec_path, impact_reports, frozen_model_receipt, *,
                                      library_digest, cohort_event_ids):
    """Return the bound hashes, or raise. Missing receipts are refusals, not warnings.

    ``impact_reports`` maps each primary horizon (30, 60 seconds) to its report (dict or
    path). ``library_digest`` and ``cohort_event_ids`` come from the caller's own inputs.
    """
    if not impact_reports or frozen_model_receipt is None:
        raise SensitivityGateError('Evaluation reporting requires both sensitivity receipts')
    if not isinstance(impact_reports, dict) or any(r is None for r in impact_reports.values()):
        raise SensitivityGateError('Evaluation reporting requires both sensitivity receipts')
    try:
        horizons = {int(h) for h in impact_reports}
    except (TypeError, ValueError):
        raise SensitivityGateError('Impact reports must be keyed by horizon seconds') from None
    if len(horizons) != len(impact_reports) or horizons != set(REQUIRED_HORIZONS):
        raise SensitivityGateError(f'One impact report per horizon {REQUIRED_HORIZONS} is required')
    _hex64(library_digest, 'library_digest')
    cohort_sha = cohort_ids_sha256(cohort_event_ids)
    reports = {int(h): _load(r) for h, r in impact_reports.items()}
    report_shas = {str(h): verify_input_impact_report(r, spec_path, delta_s=h, library_digest=library_digest,
                                                      cohort_event_ids=cohort_event_ids)
                   for h, r in sorted(reports.items())}
    results_sha = verify_frozen_model_receipt(frozen_model_receipt, spec_path, reports,
                                              library_digest=library_digest, cohort_sha256=cohort_sha)
    _, spec_sha = load_spec(spec_path)
    return {'spec_sha256': spec_sha, 'impact_report_sha256': report_shas,
            'frozen_model_results_sha256': results_sha, 'library_digest': library_digest,
            'cohort_ids_sha256': cohort_sha}
