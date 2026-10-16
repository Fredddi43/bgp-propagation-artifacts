"""Emit matched-transition recovery tables and auditable manuscript facts."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import polars as pl

from bgbench.paired_analysis import clustered_mean_ci, link_components

YEARS = range(2022, 2027)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    inputs, annual = {}, {}

    def read(path):
        inputs[str(path.relative_to(args.data))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return pl.read_parquet(path) if path.suffix == ".parquet" else json.loads(path.read_text())

    for year in YEARS:
        base = args.data / "eventset" / f"{year}_recovery_first_transition"
        suffix = "" if year == 2022 else "_labelled"
        summary = read(base / f"pairs_summary{suffix}.json")
        pairs = read(base / f"pairs{suffix}.parquet")
        overlap = read(base / f"overlap_summary{suffix}.json")
        rov = read(base / f"rov_summary{suffix}{'_frozen2505' if year >= 2025 else ''}.json")
        assert pairs.height == summary["pairs"] == overlap["selected_pairs"] == rov["pairs"]
        assert summary["pair_population"]["require_matched_definition"]
        assert summary["chronologically_unmatched_count"] == overlap["chronologically_unmatched_count"] == rov["chronologically_unmatched_count"]
        origin = read(args.data / "eventset" / str(year) / "events.parquet")
        validity = read(args.data / "eventset" / str(year) / "rpki_validity.parquet")
        eligible = origin.join(validity.select("event_id", "validity", "prev_validity"), on="event_id", validate="1:1").filter(
            (pl.col("validity") == "invalid") & (pl.col("prev_validity") == "valid"))
        if year > 2022:
            eligible = eligible.filter(pl.col("reason") != "rpki_invalid_sample")
        selection = read(args.data / "inventory" / str(year) / "recovery_replay_selection.parquet").select("event_id", "hijack_id").unique()
        full_selection_links = selection.height
        selection = selection.join(eligible.select(pl.col("event_id").alias("hijack_id")), on="hijack_id", how="semi")
        htable = read(args.data / "eventset" / f"{year}_hijack_first_transition" / "events.parquet")
        rtable = read(base / "events.parquet")
        hrows = {x["event_id"]: x for x in htable.iter_rows(named=True)}
        rrows = {x["event_id"]: x for x in rtable.iter_rows(named=True)}
        excluded = Counter()
        for rid, hid in selection.iter_rows():
            causes = []
            for label, source, event_id in (("H", hrows, hid), ("R", rrows, rid)):
                if event_id not in source:
                    causes.append(label + ": missing measurement")
                elif source[event_id]["error"]:
                    causes.append(label + ": " + source[event_id]["error"])
            if causes: excluded["; ".join(causes)] += 1
        same_day = pairs.filter(pl.Series([not hrows[hid]["recovery_source_window_crosses_midnight"] and
                                          not rrows[rid]["recovery_source_window_crosses_midnight"]
                                          for rid, hid in pairs.select("event_id", "hijack_id").iter_rows()]))
        groups = link_components(same_day)
        difference = same_day["r_j30"] - same_day["h_j30"]
        sensitivity = {"pairs": same_day.height, "excluded_crossday_links": pairs.height-same_day.height,
                       "components": len(set(groups)), "paired_j30_diff": {"mean": difference.mean(), "ci95": clustered_mean_ci(difference, groups)},
                       "h_t90_s_p50": same_day["h_t90_s"].median(), "r_t90_s_p50": same_day["r_t90_s"].median(),
                       "recovery_slower_t90_frac": (same_day["r_t90_s"] > same_day["h_t90_s"]).mean(),
                       "reach_ratio_p50": (same_day["r_reach"] / same_day["h_reach"]).median()}
        assert sum(excluded.values()) == selection.height - pairs.height - summary["chronologically_unmatched_count"]
        annual[year] = {"same_day_sensitivity": sensitivity, "unusable_link_reasons": dict(excluded), "full_selection_links_all_populations": full_selection_links,"pairs": summary, "overlap": overlap, "rov": rov,
                        "eligible_selected_hijacks": eligible.height, "identified_links": selection.height,
                        "unusable_measurement_links": selection.height - pairs.height - summary["chronologically_unmatched_count"]}

    def row(label, values):
        return label + " & " + " & ".join(values) + r" \\" + "\n"

    def n(x): return f"{x:,.0f}"
    def pct(x): return "--" if x is None else f"{100*x:.1f}" + r"\,\%"
    def start(): return "\\begin{tabular}{lrrrrr}\n\\toprule\n" + row("", map(str, YEARS)) + "\\midrule\n"
    def finish(): return "\\bottomrule\n\\end{tabular}\n"
    values = list(annual.values())
    table = start()
    table += row("selected invalid-displacing-valid hijacks", [n(x["eligible_selected_hijacks"]) for x in values])
    table += row("identified hijack--return links", [n(x["identified_links"]) for x in values])
    table += row("excluded: unusable transition measurements", [n(x["unusable_measurement_links"]) for x in values])
    table += row("excluded: unmatched observed chronology", [n(x["pairs"]["chronologically_unmatched_count"]) for x in values])
    table += row("retained links", [n(x["pairs"]["pairs"]) for x in values])
    table += row("unique hijacks / returns", [f"{n(x['pairs']['unique_hijacks'])} / {n(x['pairs']['unique_recoveries'])}" for x in values])
    table += row("connected event components", [n(x["pairs"]["bootstrap_components"]) for x in values])
    table += row("identifier gap, p50 (s)", [n(x["pairs"]["gap_s_p50"]) for x in values])
    table += finish()
    (args.out / "recovery_population.tex").write_text(table)
    table = start()
    for label, role, key, formatter in (
        (r"hijack $\Jac_{30}$, mean", "hijack", "j30_mean", lambda x:f"{x:.2f}"),
        (r"return $\Jac_{30}$, mean", "recovery", "j30_mean", lambda x:f"{x:.2f}"),
        (r"hijack $t_{90}$, p50 (s)", "hijack", "t90_s_p50", lambda x:f"{x:.1f}"),
        (r"return $t_{90}$, p50 (s)", "recovery", "t90_s_p50", lambda x:f"{x:.1f}"),
        (r"return $t_{90}>5$\,min", "recovery", "t90_gt_5min_frac", pct)):
        table += row(label, [formatter(x["pairs"][role][key]) for x in values])
    differences, intervals=[], []
    for x in values:
        d=x["pairs"]["paired_j30_diff_recovery_minus_hijack"]
        interval=d["ci95"]
        differences.append(f"${d['mean']:+.3f}$")
        intervals.append(f"[${interval[0]:+.2f}$, ${interval[1]:+.2f}$]" if interval else "--")
    table += row(r"paired $\Delta\Jac$", differences)
    table += row(r"95\,\% component-bootstrap CI", intervals)
    table += row("return slower", [pct(x["pairs"]["recovery_slower_t90_frac"]) for x in values])
    table += row("return / hijack extent, p50", [f"{x['pairs']['recovery_reach_over_hijack_reach_p50']:.2f}" + r"$\times$" for x in values])
    table += row("extent p50, return / hijack", [f"{n(x['pairs']['recovery']['reach_p50'])} / {n(x['pairs']['hijack']['reach_p50'])}" for x in values])
    table += row(r"$|R\setminus H|/|R|$, mean", [pct(x["overlap"]["recoverers_never_carried_hijack_mean"]) for x in values])
    table += row(r"ROV share: $R\setminus H$ / $R\cap H$ / $H\setminus R$", [" / ".join("--" if x["rov"]["enforcing_share"][key]["share"] is None else f"{x['rov']['enforcing_share'][key]['share']:.2f}" for key in ("R-H","R&H","H-R")) for x in values])
    table += row(r"RoVista coverage: $R\setminus H$ / $R\cap H$ / $H\setminus R$", [" / ".join("--" if x["rov"]["enforcing_share"][key]["coverage"] is None else f"{x['rov']['enforcing_share'][key]['coverage']:.2f}" for key in ("R-H","R&H","H-R")) for x in values])
    table += finish()
    (args.out / "recovery_pairs.tex").write_text(table)
    (args.out / "recovery_facts.json").write_text(json.dumps({"inputs_sha256": inputs, "years": annual}, indent=2)+"\n")


if __name__ == "__main__":
    main()
