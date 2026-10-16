"""Correct first-announcement timing from retained observations, preserving inputs."""
import argparse
import hashlib
import json
from pathlib import Path

import polars as pl

from bgbench.beacon_analysis import first_observation_per_cycle, per_vp_summary, timing_eligible_cycles


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observations",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    obs=pl.read_parquet(args.observations)
    cycles=first_observation_per_cycle(obs)
    eligible=timing_eligible_cycles(cycles)
    args.output.mkdir(parents=True,exist_ok=False)
    cycles.write_parquet(args.output/"cycles.parquet",compression="zstd")
    per_vp_summary(cycles).write_parquet(args.output/"per_vp_summary.parquet",compression="zstd")
    summary={"measurement_definition":"first_received_announcement_grouped_by_decoded_origin_cycle_v3",
        "row_grain":"prefix, decoded-origin cycle (arrival cycle if unknown), collector, peer address, peer ASN, origin-known stratum",
        "eligibility":"unambiguous first-arrival origin and announcement delay in [0,3600] seconds; withdrawal summaries use the same cycles",
        "cycles":cycles.height,"eligible_cycles":eligible.height,"excluded_cycles":cycles.height-eligible.height,
        "exclusion_counts_overlap":True,
        "excluded_late_announcement":cycles.filter(pl.col("a_delay_s")>3600).height,
        "excluded_negative_delay":cycles.filter(pl.col("a_delay_s")<0).height,
        "excluded_missing_origin":cycles["a_delay_s"].null_count(),
        "ambiguous_first_origin_cycles":cycles.filter(pl.col("first_a_origin_ambiguous")).height,
        "first_arrival_in_different_cycle":cycles.filter(pl.col("first_a_arrival_slot_ts")!=pl.col("slot_ts")).height,
        "statistics":{}}
    for name,column in (("announcement","a_delay_s"),("withdrawal","w_delay_s")):
        values=eligible[column].drop_nulls()
        summary["statistics"][name]={"n":len(values),**{f"p{int(q*100)}_s":values.quantile(q) for q in (.5,.9,.99)}}
    (args.output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    provenance={"source":"beacons/2024-06-10_2024-06-16/observations.parquet",
        "source_sha256":hashlib.sha256(args.observations.read_bytes()).hexdigest(),"source_rows":obs.height,
        "aggregation_source_sha256":hashlib.sha256((Path(__file__).parents[1]/"src/bgbench/beacon_analysis.py").read_bytes()).hexdigest()}
    (args.output/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    print(json.dumps(summary),flush=True)


if __name__=="__main__":
    main()
