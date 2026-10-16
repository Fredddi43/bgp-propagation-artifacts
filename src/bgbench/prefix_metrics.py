"""Prefix-set scoring with full observed truth and a causal candidate universe."""
import polars as pl


def set_jaccard(group: pl.DataFrame, prediction: pl.Expr) -> float:
    predicted = set(group.filter(prediction & (pl.col('in_candidate') == 1))['prefix'].to_list())
    predicted |= set(group.filter(pl.col('seen_delta') == 1)['prefix'].to_list())
    truth = set(group.filter(pl.col('y') == 1)['prefix'].to_list())
    return len(predicted & truth) / len(predicted | truth) if predicted | truth else 1.
