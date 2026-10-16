import polars as pl
from bgbench.prefix_metrics import set_jaccard


def test_future_prefix_outside_candidates_is_a_miss_even_with_high_prediction():
    group=pl.DataFrame({'prefix':['seen','future'], 'in_candidate':[1,0], 'seen_delta':[1,0], 'y':[1,1], 'p':[0.,1.]})
    assert set_jaccard(group,pl.col('p')>=.5)==.5


def test_unseen_rib_candidate_can_be_predicted_without_target_leak():
    group=pl.DataFrame({'prefix':['seen','rib','future'], 'in_candidate':[1,1,0], 'seen_delta':[1,0,0], 'y':[1,1,1], 'p':[0.,1.,1.]})
    assert set_jaccard(group,pl.col('p')>=.5)==2/3
