"""Fixed-reference collector comparisons with explicit input abstentions.

Availability is established by a separate input-coverage audit, never inferred
from an absent graph or prediction. These adapters do not open any raw labels.
"""
import math


def _index(rows, name):
    result = {}
    for row in rows:
        eid = row['event_id']
        if eid in result:
            raise ValueError(f'Duplicate {name} event: {eid}')
        result[eid] = row
    return result


def align_panel_predictions(reference_event_ids, availability, predictions):
    """Keep every reference event; synthesize only audited no-input abstentions.

    The ledger requires status available/no_input, complete input-window coverage,
    successful parsing, canonical input seeds, and its coverage-audit SHA256.
    Missing archives, parse/inference failures and unclassified IDs fail closed.
    Prediction rows use predicted_asns, candidate_asns and predicted_count.
    """
    ids = list(reference_event_ids)
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate reference IDs')
    ledger, forecasts = _index(availability, 'availability'), _index(predictions, 'prediction')
    if set(ledger) != set(ids):
        raise ValueError('Availability ledger must cover exact reference IDs')
    eligible = set()
    for eid, row in ledger.items():
        receipt = row.get('coverage_audit_sha256', '')
        if (row.get('input_window_complete') is not True or row.get('parse_status') != 'ok'
                or len(receipt) != 64 or any(c not in '0123456789abcdef' for c in receipt)):
            raise ValueError(f'Unverified input coverage or parsing: {eid}')
        seeds = row.get('input_seed_asns')
        if seeds is None:
            raise ValueError(f'Missing canonical input seeds: {eid}')
        status = row.get('status')
        if status == 'available' and seeds:
            eligible.add(eid)
        elif status != 'no_input' or seeds:
            raise ValueError(f'Unsupported or inconsistent input status: {eid}: {status}')
    if set(forecasts) != eligible:
        raise ValueError('Predictions must cover all and only input-eligible IDs; inference failures cannot become abstentions')
    aligned = []
    for eid in ids:
        source = ledger[eid]
        available = eid in eligible
        row = dict(forecasts[eid]) if available else {
            'event_id': eid, 'predicted_asns': [], 'candidate_asns': [], 'predicted_count': 0.0}
        count = float(row['predicted_count'])
        if not math.isfinite(count) or count < 0:
            raise ValueError(f'Invalid predicted count: {eid}')
        if not set(row['predicted_asns']) <= set(row['candidate_asns']) | set(source['input_seed_asns']):
            raise ValueError(f'Prediction outside declared candidates/seeds: {eid}')
        row.update(input_status=source['status'], forecast_available=available,
                   calibration_eligible=available, input_seed_asns=list(source['input_seed_asns']),
                   coverage_audit_sha256=source['coverage_audit_sha256'],
                   abstention_policy='empty_set_zero_count' if not available else None)
        aligned.append(row)
    return aligned


def common_input_eligible(panel_rows):
    """Secondary paired cohort: intersection of available IDs, same reference pool."""
    indexed = [_index(rows, 'panel') for rows in panel_rows]
    if not indexed:
        raise ValueError('At least one panel is required')
    ids = set(indexed[0])
    if any(set(panel) != ids for panel in indexed):
        raise ValueError('Panels must retain the same complete reference population')
    return sorted(eid for eid in ids if all(panel[eid]['forecast_available'] for panel in indexed))


def score_panel_predictions(aligned, reference_targets):
    """Evaluator-only full-reference scores, including the declared abstention cost.

    Targets contain target_asns and reference_seed_asns at the common issue time.
    ``new_*`` metrics subtract reference seeds; ``input_new_*`` subtract input-panel
    seeds. Both use the same full reference target and are reported separately.
    Abstention zeros are penalties, excluded from probabilistic calibration.
    """
    targets = _index(reference_targets, 'target')
    rows = _index(aligned, 'aligned prediction')
    if set(targets) != set(rows):
        raise ValueError('Reference targets and aligned predictions differ')
    scored = []
    for eid, row in rows.items():
        truth = set(targets[eid]['target_asns'])
        reference_seeds = set(targets[eid]['reference_seed_asns'])
        if not reference_seeds <= truth:
            raise ValueError(f'Reference seeds outside full reference target: {eid}')
        prediction = set(row['predicted_asns'])
        new_truth, new_prediction = truth - reference_seeds, prediction - reference_seeds
        input_new_truth = truth - set(row['input_seed_asns'])
        input_new_prediction = prediction - set(row['input_seed_asns'])
        tp = len(new_truth & new_prediction)
        count = float(row['predicted_count'])
        denominator = count + len(truth)
        scored.append({'event_id': eid, 'forecast_available': row['forecast_available'],
                       'calibration_eligible': row['calibration_eligible'],
                       'input_status': row['input_status'],
                       'jaccard': len(prediction & truth) / len(prediction | truth) if prediction | truth else 1.0,
                       'smape_2h': 2 * abs(count - len(truth)) / denominator if denominator else 0.0,
                       'new_tp': tp, 'new_fp': len(new_prediction - truth), 'new_fn': len(new_truth - new_prediction),
                       'input_new_tp': len(input_new_truth & input_new_prediction),
                       'input_new_fp': len(input_new_prediction - truth),
                       'input_new_fn': len(input_new_truth - input_new_prediction),
                       'candidate_coverage': (len((set(row['candidate_asns']) | set(row['input_seed_asns'])) & truth) / len(truth) if truth else None)
                       if row['forecast_available'] else 0.0})
    n = len(scored)
    available = sum(row['forecast_available'] for row in scored)
    return scored, {'reference_events': n, 'available_forecasts': available,
                    'unavailable_fraction': (n - available) / n if n else None,
                    'calibration_coverage': available / n if n else None,
                    'abstention_policy': 'empty_set_zero_count', 'new_target_scope': 'fixed_reference_seeds',
                    'input_new_target_scope': 'panel_input_seeds', 'candidate_coverage_scope': 'candidates_union_input_seeds'}
