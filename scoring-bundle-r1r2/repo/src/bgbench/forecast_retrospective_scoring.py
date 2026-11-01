"""Pure scoring of verified retrospective forecast payloads and explicitly supplied labels.

No filesystem reads, prediction generation, selection or calibration occur here.
Membership arithmetic follows the frozen forecast_score.py evaluator.
"""
from __future__ import annotations

import numpy as np

from . import forecast_numeric as numeric
from .forecast_history import in_issue_time_slice, issue_time_slice_variables
from .forecast_ranking import event_ranking_metrics
from .forecast_train import CURVE_HORIZONS, membership_metrics


def covered_float32_log_interval(counts, lower, upper):
    lower, upper = np.asarray(lower), np.asarray(upper)
    if (not np.array_equal(lower.astype(np.float32).astype(np.float64), lower.astype(np.float64))
            or not np.array_equal(upper.astype(np.float32).astype(np.float64), upper.astype(np.float64))):
        raise ValueError("Neural interval precision must be exactly float32")
    return numeric.covered_log_interval(counts, lower, upper)


def ranking_scores(row):
    if "ranking_scores" in row:
        if row.get("baseline") not in ("history-knn-mean", "history-knn-median", "topology-seed-adjacency"):
            raise ValueError("Committed ranking scores require a declared baseline arm")
        return row["ranking_scores"]
    return row["probabilities"]


def probability_statistics(forecast, truth):
    """Fixed ten-bin sufficient statistics; no probabilities invented outside the candidate pool."""
    if "probabilities" not in forecast:
        return None
    seeds = set(forecast["seed_asns"])
    pairs = [(a, float(p)) for a, p in zip(forecast["candidate_asns"], forecast["probabilities"], strict=True) if a not in seeds]
    bins = [{"count": 0, "contributing_events": 0, "sum_probability": 0., "positive_count": 0, "squared_error_sum": 0.,
             "event_weight": 0., "weighted_probability_sum": 0., "weighted_positive_sum": 0.,
             "weighted_squared_error_sum": 0.} for _ in range(10)]
    for asn, probability in pairs:
        if not np.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("Invalid probability in reliability statistics")
        bucket = bins[min(int(probability * 10), 9)]
        label = int(asn in truth)
        error = (probability - label) ** 2
        weight = 1 / len(pairs)
        bucket['count'] += 1
        bucket['contributing_events'] = 1
        bucket['sum_probability'] += probability
        bucket['positive_count'] += label
        bucket['squared_error_sum'] += error
        bucket['event_weight'] += weight
        bucket['weighted_probability_sum'] += weight * probability
        bucket['weighted_positive_sum'] += weight * label
        bucket['weighted_squared_error_sum'] += weight * error
    targets = set(truth) - seeds
    return {"bins": bins, "candidate_nonseeds": len(pairs), "zero_candidate_event": not pairs,
            "new_targets": len(targets), "outside_candidate_targets": len(targets - {a for a, _ in pairs})}


def score_membership(prediction_list, events, rules=None):
    """Consume supplied values; the caller owns the global verification and label-access barrier."""
    predictions = {r["event_id"]: r for r in prediction_list}
    if len(predictions) != len(prediction_list) or set(predictions) != {e["event_id"] for e in events}:
        raise ValueError("Prediction/target event IDs differ or duplicate")
    rows, rankings = [], []
    for event in events:
        row = predictions[event["event_id"]]
        baseline = 'ranking_scores' in row
        native = baseline and row.get('candidate_protocol') == 'native_history_union'
        if ((not native and row["candidate_asns"] != event["asn"].tolist())
                or sorted(row["seed_asns"]) != sorted(event["seed_asns"].tolist())):
            raise ValueError(f"Prediction/target candidate or seed mismatch: {event['event_id']}")
        truth = set(map(int, event["target_asns"]))
        seeds = set(row["seed_asns"])
        if baseline:
            # Deterministic baselines commit their decision directly; it is scored as committed.
            predicted = set(map(int, row["predicted_asns"]))
            if not seeds <= predicted:
                raise ValueError("Baseline decision must retain every observed seed")
            union = truth | predicted
            result = {"decision_rule": "committed_baseline_decision", "baseline": row["baseline"],
                      "jaccard": len(truth & predicted) / len(union) if union else float("nan"),
                      "jaccard_persist": len(truth & seeds) / len(truth | seeds) if truth | seeds else float("nan")}
        else:
            if rules is not None and rules['global_threshold'] != row["threshold"]:
                raise ValueError("Decision rules belong to a different global threshold")
            selected = np.asarray(row["probabilities"]) >= row["threshold"]
            result = membership_metrics(event, selected)
            predicted = seeds | set(np.asarray(row["candidate_asns"])[selected].tolist())
            if predicted != set(row["predicted_asns"]):
                raise ValueError("Committed decision differs from probabilities/threshold")
        # Primary metric (PRIMARY-METRIC-REVISION.md §2): candidate-complete new-member ranking.
        ranking = event_ranking_metrics(row["candidate_asns"], ranking_scores(row), truth, seeds,
                                        status=row.get("status", "available"))
        rankings.append(ranking)
        result.update(average_precision=ranking["average_precision"], precision_at=ranking["precision_at"],
                      recall_at=ranking["recall_at"], new_members=ranking["new_members"],
                      eligible=ranking["eligible"], ranked=ranking["ranked"], ranking_status=ranking["status"],
                      new_members_ranked=ranking["new_members_ranked"], coverage_ceiling=ranking["coverage_ceiling"],
                      metric_version=ranking["metric_version"])
        if "history_signature" in event:
            variables = issue_time_slice_variables(event["history_signature"], event["seed_asns"].tolist())
            result.update(issue_time_variables=variables)
            if rules is not None:
                inside = in_issue_time_slice(rules['slice_rule'], variables)
                threshold = rules['slice_threshold'] if inside else rules['remainder_threshold']
                if baseline:
                    two = predicted
                else:
                    two = seeds | {int(a) for a, p in zip(row["candidate_asns"], row["probabilities"]) if p >= threshold}
                union = truth | two
                result.update(in_issue_time_slice=inside, two_threshold_decision_threshold=threshold,
                              two_threshold_jaccard=len(truth & two) / len(union) if union else None)
        elif rules is not None:
            raise ValueError("Slice decisions need the event's issue-time signature")
        result["probability_calibration"] = probability_statistics(row, truth)
        new_true, new_pred = truth - seeds, predicted - seeds
        tp = len(new_true & new_pred)
        result.update(new_tp=tp, new_fp=len(new_pred - truth), new_fn=len(new_true - new_pred),
                      new_precision=tp / len(new_pred) if new_pred else None,
                      new_recall=tp / len(new_true) if new_true else None,
                      new_f1=2 * tp / (len(new_pred) + len(new_true)) if new_pred or new_true else None,
                      no_growth=not new_true, empty_new_prediction=not new_pred)
        if "curve_log_quantiles" in row:
            log_quantiles = np.asarray(row["curve_log_quantiles"])
            quantiles = np.expm1(log_quantiles)
            curve = np.asarray(event["curve"])
            future = np.asarray(CURVE_HORIZONS) > row["observation_cutoff_s"]
            result.update(curve_smape=float(np.mean(2 * np.abs(quantiles[future, 1] - curve[future]) /
                                                    np.maximum(np.abs(quantiles[future, 1]) + curve[future], 1e-9))) if future.any() else None,
                          curve_cover80=float(np.mean(covered_float32_log_interval(curve[future], log_quantiles[future, 0], log_quantiles[future, 2]))) if future.any() else None)
        extent = row.get("extent")
        if extent is None and "curve_log_quantiles" in row:
            extent = float(np.expm1(np.asarray(row["curve_log_quantiles"])[-1, 1]))
        if extent is not None:
            if type(extent) not in (int, float) or not np.isfinite(extent) or extent < 0:
                raise ValueError("Invalid committed extent")
            denominator = extent + len(truth)
            result.update(predicted_count=float(extent), smape_2h=2 * abs(extent - len(truth)) / denominator
                          if denominator else 0.)
        rows.append({"event_id": event["event_id"], **{k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in result.items()}})
    return rows


def score_curves(payload, labels, *, target_seconds, context_seconds, probabilistic):
    """Use the established count metric on each event; point controls have no interval metrics."""
    from .forecast_curve import metrics
    ids = payload['event_ids']
    label_ids = [str(v) for v in labels['event_ids']]
    if len(label_ids) != len(set(label_ids)) or set(label_ids) != set(ids):
        raise ValueError('Curve labels and committed predictions have different IDs')
    order = {eid: i for i, eid in enumerate(label_ids)}
    truth = np.asarray(labels['target'])[[order[eid] for eid in ids]]
    q = payload['log_quantiles']
    if truth.shape != q.shape[:2] or not np.isfinite(truth).all() or (truth < 0).any():
        raise ValueError('Invalid curve target shape or value')
    if not probabilistic and not (np.array_equal(q[:, :, 0], q[:, :, 1])
                                  and np.array_equal(q[:, :, 1], q[:, :, 2])):
        raise ValueError('Point controls must repeat one point across all three slots')
    out = []
    for index, eid in enumerate(ids):
        result = metrics(q[index:index + 1], {'target': truth[index:index + 1],
                         'target_seconds': np.asarray(target_seconds),
                         'context_seconds': np.asarray(context_seconds)}, probabilistic=probabilistic)
        out.append({'event_id': eid, 'curve_smape': result['event_mean_smape'][0],
                    'curve_cover80': result.get('interval80_coverage'),
                    'curve_log_pinball': result.get('log_count_pinball'),
                    'curve_interval80_width': result.get('interval80_mean_width'),
                    'calibration_eligible': probabilistic,
                    'calibration_status': 'probabilistic' if probabilistic else 'not_applicable_point_control'})
    return out


RETROSPECTIVE_14 = (
    ('within-message-passing', 'core-sage-on', 'core-none-on', 'shared_causal_candidates'),
    ('within-history-whole-system', 'core-sage-on', 'online-history-native', 'native_whole_system'),
    ('within-sage-history', 'core-sage-on', 'core-sage-off', 'shared_causal_candidates'),
    ('within-none-history', 'core-none-on', 'core-none-off', 'shared_causal_candidates'),
    ('transfer-sage-history-whole-system', 'transfer-sage-on', 'online-history-native', 'native_whole_system'),
    ('transfer-none-history-whole-system', 'transfer-none-on', 'online-history-native', 'native_whole_system'),
    ('transfer-message-passing', 'transfer-sage-on', 'transfer-none-on', 'shared_causal_candidates'),
)


def retrospective_14(cells, scored, cohorts, *, transfer_variant, repetitions, seed):
    """All fourteen original Jaccard contrasts; ordinary paired intervals, no formal hypotheses.

    This is distinct from the later ranking-v1 C1–C4 report. Failed or absent seeds are
    reported for each affected contrast; they are never removed from paired arrays.
    """
    from .forecast_analysis import incident_day_blocks, paired_interval
    grouped = {}
    for cell in cells:
        if cell.get('secondary'):
            continue
        role = cell['role']
        arm = role['arm_id']
        name = None
        if arm in ('R-core', 'R-transfer') and role.get('model_family') == 'neural':
            if arm == 'R-transfer' and role.get('variant') != transfer_variant:
                continue
            name = ('core' if arm == 'R-core' else 'transfer') + '-' + str(role.get('message_passing')) + '-' + str(role.get('history'))
        elif (arm == 'R-base' and role.get('baseline') == 'history-knn-mean'
              and role.get('candidate_protocol') in ('native', 'native_history_union') and role.get('frozen_at') is None):
            name = 'online-history-native'
        if name:
            grouped.setdefault((name, role['horizon_seconds']), []).append(cell)
    contrasts = []
    for horizon in (30, 60):
        metadata = cohorts.get(str(horizon), [])
        ids = [r['event_id'] for r in metadata]
        for name, left, right, protocol in RETROSPECTIVE_14:
            record = {'name': f'{name}@{horizon}', 'left': left, 'right': right, 'metric': 'jaccard',
                      'candidate_comparison': protocol, 'horizon_seconds': horizon}
            arrays, orders, problems = {}, {}, []
            for arm in (left, right):
                members = sorted(grouped.get((arm, horizon), []), key=lambda c: c['role'].get('seed', 0))
                expected = [0] if arm == 'online-history-native' else list(range(5))
                orders[arm] = [c['role'].get('seed', 0) for c in members]
                if orders[arm] != expected:
                    problems.append({'arm': arm, 'expected_seeds': expected, 'retained_seeds': orders[arm]})
                    continue
                invalid = [c['cell_id'] for c in members if c['status'] != 'committed' or c['cell_id'] not in scored]
                if invalid:
                    problems.append({'arm': arm, 'unavailable_cells': invalid})
                    continue
                if any(set(scored[c['cell_id']]) != set(ids) for c in members):
                    raise ValueError('Original fourteen contrasts require identical full-truth event IDs')
                arrays[arm] = np.asarray([[scored[c['cell_id']][eid]['jaccard'] for eid in ids] for c in members])
            if problems or not ids:
                record.update(status='unavailable', failures=problems, events=len(ids))
            else:
                blocks = {'incident_day': incident_day_blocks(metadata),
                          'incident': [r['incident_id'] for r in metadata]}
                if all('actor' in r for r in metadata):
                    blocks['actor'] = [r['actor'] for r in metadata]
                record.update(status='scored', events=len(ids), training_seeds=orders,
                              uncertainty={label: paired_interval(arrays[left], arrays[right], values,
                                                                  repetitions=repetitions, seed=seed)
                                           for label, values in blocks.items()})
            contrasts.append(record)
    return {'contrasts': contrasts, 'contrast_count': 14, 'metric': 'original_full_target_jaccard',
            'confirmatory': False, 'formal_tests': False,
            'intervals': 'ordinary paired hierarchical intervals; not simultaneous; no equivalence claim',
            'formal_testing_rule': 'If formal tests are added, all fourteen form one Holm family',
            'transfer_variant': transfer_variant}


def score_panel(aligned, original_predictions, events):
    """Fixed-reference H3 score; history extent stays separate from curve calibration."""
    from .forecast_panel import score_panel_predictions
    from .forecast_panel_scoring import HISTORY_NA
    targets = [{'event_id': event['event_id'], 'target_asns': event['target_asns'].tolist(),
                'reference_seed_asns': event['seed_asns'].tolist()} for event in events]
    rows, _ = score_panel_predictions(aligned, targets)
    event_by_id = {e['event_id']: e for e in events}
    original = {r['event_id']: r for r in original_predictions}
    for result, row in zip(rows, aligned, strict=True):
        event = event_by_id[row['event_id']]
        truth = set(map(int, event['target_asns']))
        available = row['forecast_available']
        forecast = original[row['event_id']] if available else {}
        scores = forecast.get('ranking_scores', forecast.get('probabilities', []))
        ranking = event_ranking_metrics(row['candidate_asns'], scores, truth, set(map(int, row['input_seed_asns'])),
                                        status='available' if available else 'no_input')
        result.update(average_precision=ranking['average_precision'], precision_at=ranking['precision_at'],
                      recall_at=ranking['recall_at'], eligible=ranking['eligible'],
                      ranking_status=ranking['status'], new_members=ranking['new_members'],
                      coverage_ceiling=ranking['coverage_ceiling'], predicted_count=row['predicted_count'])
        result.update(forecast_available=available, partial_panel_input=row.get('partial_panel_input', False),
                      complete_input_calibration_eligible=row.get('complete_input_calibration_eligible', False),
                      probability_calibration=probability_statistics(forecast, truth) if available else None)
        if row['family'] == 'history':
            result.update(curve_smape=None, curve_cover80=None, curve_metrics='not_applicable',
                          curve_metrics_reason=HISTORY_NA, estimator_identity=row['estimator_identity'])
        elif available:
            q = np.asarray(row['curve_log_quantiles'])
            curve = np.asarray(event['curve'])
            future = np.asarray(CURVE_HORIZONS) > row['horizon_seconds']
            points = np.expm1(q[:, 1])
            result.update(curve_smape=float(np.mean(2 * abs(points[future] - curve[future]) /
                                                   np.maximum(abs(points[future]) + curve[future], 1e-9))),
                          curve_cover80=float(np.mean(numeric.covered_log_interval(curve[future],
                                                                                 q[future, 0], q[future, 2]))))
        else:
            result.update(curve_smape=None, curve_cover80=None)
    return rows


def score_stable(predictions, events, abstention_targets, *, arm):
    """Stable own-target sensitivity. No ordinary full-panel targets are accepted by the caller."""
    available = [r for r in predictions if r['stable_input_status'] == 'stable_input']
    if arm == 'persistence':
        by_id = {e['event_id']: e for e in events}
        rows = []
        for row in available:
            truth = set(map(int, by_id[row['event_id']]['target_asns']))
            seeds = set(row['seed_asns'])
            if set(row['predicted_asns']) != seeds:
                raise ValueError('Stable persistence changed its committed decision')
            ranking = event_ranking_metrics([], [], truth, seeds)
            rows.append({'event_id': row['event_id'], 'jaccard': len(truth & seeds) / len(truth | seeds) if truth | seeds else 1.,
                         'smape_2h': 2 * abs(len(seeds) - len(truth)) / (len(seeds) + len(truth)) if seeds or truth else 0.,
                         'average_precision': ranking['average_precision'], 'eligible': ranking['eligible'],
                         'curve_cover80': None, 'curve_smape': None, 'calibration_eligible': False,
                         'ranking_definition': 'persistence selects no new ASes'})
    else:
        rows = score_membership(available, events)
    for row in rows:
        row.update(forecast_available=True, target_scope='stable_peer_only', input_status='stable_input')
    for row in predictions:
        if row['stable_input_status'] != 'certified_no_stable_input':
            continue
        truth = set(map(int, abstention_targets[row['event_id']]))
        ranking = event_ranking_metrics([], [], truth, set(), status='no_input')
        rows.append({'event_id': row['event_id'], 'jaccard': 0. if truth else 1., 'smape_2h': 2. if truth else 0.,
                     'predicted_count': 0., 'forecast_available': False, 'calibration_eligible': False,
                     'curve_cover80': None, 'curve_smape': None, 'average_precision': ranking['average_precision'],
                     'eligible': ranking['eligible'], 'target_scope': 'stable_peer_only',
                     'input_status': 'certified_no_stable_input'})
    if {r['event_id'] for r in rows} != {r['event_id'] for r in predictions}:
        raise ValueError('Stable target score population differs')
    return sorted(rows, key=lambda r: r['event_id'])
