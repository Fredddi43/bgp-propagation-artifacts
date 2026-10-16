"""Persistence floor of the leak event set by final extent (ASes at 2 h) and by leaked prefixes — is the slow tail the large leaks?"""
import polars as pl
from bgbench import config
t = pl.read_parquet(config.DATA_ROOT / "eventset" / "2024_leak" / "events.parquet").filter(pl.col("error").is_null())
t = t.filter(pl.col("observation_lag_s").is_null() | (pl.col("observation_lag_s") >= -60))
def jac(a, b):
    return pl.col(a).list.set_intersection(pl.col(b)).list.len() / pl.col(a).list.set_union(pl.col(b)).list.len().clip(1)
t = t.with_columns(size_b=pl.when(pl.col("asns_final_2h") < 50).then(pl.lit("<50 ASes")).when(pl.col("asns_final_2h") < 200).then(pl.lit("50-199")).otherwise(pl.lit("200+")),
                   pfx_b=pl.when(pl.col("leaked_prefixes") <= 1).then(pl.lit("1 prefix")).when(pl.col("leaked_prefixes") < 10).then(pl.lit("2-9")).when(pl.col("leaked_prefixes") < 100).then(pl.lit("10-99")).otherwise(pl.lit("100+")))
for col in ("size_b", "pfx_b"):
    for dk in ("d30s", "d1m", "d5m", "d15m"):
        r = (t.with_columns(j=jac(f"set_{dk}", "set_final_2h"), grown=(jac(f"set_{dk}", "set_final_2h") >= 0.999))
               .group_by(col).agg(n=pl.len(), J=pl.col("j").mean().round(3), Jp50=pl.col("j").median().round(3), still_growing=(1 - pl.col("grown").mean()).round(2),
                                  asns_p50=pl.col("asns_final_2h").median(), pfx_p50=pl.col("leaked_prefixes").median()).sort(col))
        print(f"== {col} @ {dk} -> 2h"); print(r)
