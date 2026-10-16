"""Event-level candidate volume for identifier v2 outputs (distinct (prefix,new_origin) pairs and edges)."""

import sys

import polars as pl

D = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "data/identifier2/2024-06-10_2024-06-16"
)
for m in (1, 2, 3, 5):
    oc = pl.read_parquet(f"{D}/m{m}_b5/origin_change_candidates.parquet")
    ne = pl.read_parquet(f"{D}/m{m}_b5/new_edge_candidates.parquet")
    pairs = oc.group_by("prefix", "new_origin").agg(
        bins=pl.len(), maxc=pl.col("n_collectors").max()
    )
    edges = ne.group_by("a", "b").agg(bins=pl.len(), maxc=pl.col("n_collectors").max())
    print(
        f"m={m}: distinct (prefix,new_origin)={pairs.height:,}; <=2 bins/week={pairs.filter(pl.col('bins') <= 2).height:,}; "
        f">=20 bins (flappers)={pairs.filter(pl.col('bins') >= 20).height:,}; distinct new edges={edges.height:,}; "
        f"edges <=2 bins={edges.filter(pl.col('bins') <= 2).height:,}"
    )
