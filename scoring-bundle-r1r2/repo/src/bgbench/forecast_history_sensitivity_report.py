"""Input-only impact report for the frozen history-withholding sensitivity.

For every query (issue time, label-free signature, candidate ASNs) this counts which
inference *inputs* change when the specified donors are withheld from the shared
history: native participation counts of the candidate ASNs, the candidate ordering by
participation, the KNN neighbour set and its standardisation. It accepts no targets,
labels or forecast scores, and it never calls the predictor.

Not wired into any production forecast or protected-period path. The caller binds the
reviewed donor list (HISTORY-SENSITIVITY-SPEC.json) and the final canonical library.
"""
from dataclasses import dataclass
import hashlib
import json

import numpy as np

from .forecast_history_sensitivity import input_impact, withhold_snapshot

REPORT_KIND = 'history_withholding_input_impact'
SCOPE = 'input_only_no_forecast_scoring'


@dataclass(frozen=True)
class QueryInput:
    """Label-free description of one forecast issue. There is deliberately no target field."""
    event_id: str
    issue_time: object
    signature: np.ndarray
    candidate_asns: frozenset
    frozen_at: object = None


def _ranked(participation, candidates):
    return tuple(sorted(candidates, key=lambda a: (-participation.get(a, 0), a)))


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def impact_report(library, queries, withheld_ids, *, policy_sha256, delta_s, k=20, spec_sha256=None):
    withheld = tuple(sorted(set(withheld_ids)))
    if not withheld:
        raise ValueError('At least one withheld donor is required')
    unknown = [e for e in withheld if e not in library.by_id]
    if unknown:
        raise ValueError(f'Withheld donors are not in the library: {unknown}')
    rows = []
    for q in queries:
        if q.event_id in withheld:
            raise ValueError(f'Query {q.event_id} is itself a withheld donor')
        primary = library.snapshot(q.issue_time, exclude_event_id=q.event_id, frozen_at=q.frozen_at)
        changed = withhold_snapshot(primary, withheld, policy_sha256=policy_sha256)
        impact = input_impact(primary, changed, np.asarray(q.signature, dtype=np.float64),
                              delta_s=delta_s, k=k)
        candidates = frozenset(int(a) for a in q.candidate_asns)
        part_changed = sorted(a for a in candidates
                              if primary.participation.get(a, 0) != changed.participation.get(a, 0))
        rows.append({
            'query_event_id': q.event_id,
            'issue_time': primary.provenance['issue_time'],
            'availability_cutoff': primary.provenance['availability_cutoff'],
            'candidates': len(candidates),
            'candidates_with_changed_participation': len(part_changed),
            'candidate_order_changed': (_ranked(primary.participation, candidates)
                                        != _ranked(changed.participation, candidates)),
            **{key: impact[key] for key in ('matured_donors_removed', 'participation_entries_changed',
                                            'native_history_asns_removed', 'knn_neighbor_ids_changed',
                                            'knn_neighbors_removed', 'knn_scale_changed')},
        })
    n = len(rows)
    affected = lambda r: (r['matured_donors_removed'] > 0 and (  # noqa: E731
        r['candidates_with_changed_participation'] > 0 or r['candidate_order_changed']
        or r['knn_neighbor_ids_changed'] or r['knn_scale_changed']))
    aggregate = {'queries': n,
                 'queries_with_matured_donor_removed': sum(r['matured_donors_removed'] > 0 for r in rows),
                 'queries_with_changed_input': sum(affected(r) for r in rows),
                 'queries_with_changed_candidate_participation': sum(
                     r['candidates_with_changed_participation'] > 0 for r in rows),
                 'queries_with_candidate_order_changed': sum(r['candidate_order_changed'] for r in rows),
                 'queries_with_knn_neighbors_changed': sum(r['knn_neighbor_ids_changed'] for r in rows),
                 'queries_with_knn_scale_changed': sum(r['knn_scale_changed'] for r in rows)}
    body = {'kind': REPORT_KIND, 'scope': SCOPE, 'policy_sha256': policy_sha256,
            'spec_sha256': spec_sha256, 'withheld_ids': list(withheld),
            'withheld_ids_sha256': hashlib.sha256('\n'.join(withheld).encode()).hexdigest(),
            'library_digest': library.digest, 'delta_s': delta_s, 'k': k,
            'retraining_fits': 0, 'aggregate': aggregate, 'rows': rows}
    return {**body, 'report_sha256': _sha(body)}
