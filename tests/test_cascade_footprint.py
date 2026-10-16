import numpy as np
from bgbench.baselines_eventset import complete_cascade_footprint
from bgbench.diffusion import evaluate_membership


def test_outside_graph_seeds_and_unseen_truth_are_retained():
    sim = {"asn": np.array([1, 2]), "p_affected": np.array([1., 0.]), "expected_curve": np.array([1.])}
    asns, probabilities, size = complete_cascade_footprint(sim, {1, 99}, {1, 99, 100})
    score = evaluate_membership(probabilities, asns, {1, 99, 100}, {1, 2, 99, 100})
    assert size == 2
    assert score["recall"] == round(2 / 3, 4)
    assert score["jaccard"] == round(2 / 3, 4)
    assert score["precision"] == 1


def test_average_precision_ties_are_order_independent():
    a = evaluate_membership(np.array([.5, .5]), np.array([1, 2]), {1})
    b = evaluate_membership(np.array([.5, .5]), np.array([2, 1]), {1})
    assert a["auprc"] == b["auprc"] == .5


def test_true_members_outside_candidates_do_not_gain_oracle_predictions():
    sim = {"asn": np.array([1, 2, 3]), "p_affected": np.array([1., .9, .9]), "expected_curve": np.array([2.8])}
    asns, probabilities, size = complete_cascade_footprint(sim, {1}, {1, 2}, {1})
    assert dict(zip(asns, probabilities)) == {1: 1., 2: 0., 3: 0.}
    assert size == 1
    score = evaluate_membership(probabilities, asns, {1, 2}, {1, 2})
    assert score["jaccard"] == .5
