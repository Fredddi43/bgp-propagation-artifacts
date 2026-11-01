"""Candidate-only history expansion; target labels are not accepted."""
from numbers import Integral
import hashlib
import json


def expand_from_history(original_asns, history_snapshot, k):
    if not isinstance(k, Integral) or isinstance(k, bool) or k < 0:
        raise ValueError('Candidate budget must be a nonnegative integer')
    original = list(map(int, original_asns))
    if len(set(original)) != len(original):
        raise ValueError('Original candidates must be unique')
    counts = history_snapshot.participation
    if any(not isinstance(a, Integral) or a < 0 or not isinstance(n, Integral) or n <= 0
           for a, n in counts.items()):
        raise ValueError('Participation must contain positive completed-event counts')
    ranked = sorted(counts, key=lambda a: (-counts[a], int(a)))[:k]
    existing = set(original)
    added = [int(a) for a in ranked if a not in existing]
    return original + added, {'requested_top_k': int(k), 'selected_history_asns': list(map(int, ranked)),
        'added_asns': added, 'original_candidates': len(original), 'expanded_candidates': len(original) + len(added),
        'history_provenance': dict(history_snapshot.provenance),
        'tie_rule': 'descending completed-event participation, then ascending ASN'}


def expand_graph_candidates(graph, nodes, hops, snapshot, k, *, issue_time, event_id, participation):
    """Extend a causal graph selection; never accept or inspect current targets."""
    import numpy as np
    import scipy.sparse as sp
    from .diffusion import ASGraph
    from .forecast_history import utc

    if snapshot is None or (utc(snapshot.provenance['issue_time']) != utc(issue_time)
                           or utc(snapshot.provenance['availability_cutoff']) > utc(issue_time)
                           or snapshot.provenance.get('excluded_event_id') != event_id
                           or snapshot.participation != participation):
        raise ValueError('Candidate expansion requires the exact causal feature-history snapshot')
    original = graph.asns[nodes].astype(np.int64)
    selected, receipt = expand_from_history(original, snapshot, k)
    missing = sorted(set(selected) - set(graph.index))
    if missing:
        asns = np.concatenate([graph.asns, np.asarray(missing, dtype=np.int64)])
        pad = sp.csr_matrix((len(missing), len(missing)), dtype=graph.c2p.dtype)
        graph = ASGraph(asns, {int(a): i for i, a in enumerate(asns)},
                        *(sp.block_diag((m, pad), format='csr') for m in (graph.c2p, graph.p2c, graph.p2p)), graph.month)
        hops = np.concatenate([hops, np.full(len(missing), -1, dtype=hops.dtype)])
    nodes = np.asarray([graph.index[a] for a in selected], dtype=np.int64)
    receipt['selection_sha256'] = hashlib.sha256(json.dumps(
        {'original': original.tolist(), 'expanded': selected, 'history': snapshot.provenance},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return graph, nodes, hops, receipt
