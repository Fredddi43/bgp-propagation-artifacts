"""Generate manuscript propagation tables and machine-readable supporting facts.

Uses the declared manuscript populations, recomputes set scores, and records
input hashes. Run only against the finalized corrected release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import polars as pl

YEARS = range(2022, 2027)
HORIZONS = ("d30s", "d1m", "d5m", "d15m")


def facts(frame):
    test = frame.filter(pl.col("split") == "test")
    result = {"events": frame.height, "train": frame.filter(pl.col("split") == "train").height,
              "test": test.height, "extent": [frame["extent"].median(), frame["extent"].quantile(.9)],
              "duration_median": frame["duration_min"].median(),
              "labelled_share": frame["labelled"].mean(),
              "growing_share": frame["growing"].mean(),
              "observation_lag_s_p10_p50_p90": [frame["observation_lag_s"].quantile(q) for q in (.1, .5, .9)],
              "t90_s_p10_p50_p90": [frame["t90_s"].quantile(q) for q in (.1, .5, .9)],
              "floors": {h: test["J_" + h].mean() for h in HORIZONS},
              "j30_median": test["J_d30s"].median()}
    if "leaked_prefixes" in frame.columns:
        result["prefixes_median"] = frame["leaked_prefixes"].median()
    for column in ("cone", "n_providers"):
        if column in frame.columns:
            result[column + "_median"] = frame[column].median()
    if "grip_labelled" in frame.columns:
        result["grip_labelled_share"] = frame["grip_labelled"].mean()
    if "validity" in frame.columns:
        result["validity"] = {v: facts(frame.filter(pl.col("validity") == v).drop("validity"))
                              for v in ("invalid", "unknown", "valid")}
        invalid = frame.filter(pl.col("validity") == "invalid")
        result["invalid_displacing_valid"] = invalid.filter(pl.col("prev_validity") == "valid").height
        result["invalid_displacing_valid_share"] = result["invalid_displacing_valid"] / invalid.height if invalid.height else None
    return result


def scores(frame):
    return frame.filter(pl.col("error").is_null()).with_columns(
        pl.col("set_final_2h").list.len().alias("extent"),
        (pl.col("set_d30s").list.len() < pl.col("set_final_2h").list.len()).alias("growing"),
        *[(pl.col("set_" + h).list.set_intersection("set_final_2h").list.len()
           / pl.col("set_" + h).list.set_union("set_final_2h").list.len().clip(1)).alias("J_" + h)
          for h in HORIZONS])


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
        base = args.data / "eventset" / str(year)
        original = read(base / "events.parquet")
        e = scores(original)
        v = read(base / "rpki_validity.parquet").select(
            "event_id", "validity", "prev_validity", "cone", "n_providers", "grip_labelled")
        e = e.join(v, on="event_id", how="left", validate="1:1")
        if e["validity"].null_count():
            raise ValueError(f"Missing validity in {year}")
        annual[year] = {name: facts(e.filter(condition)) for name, condition in (
            ("paper", pl.col("reason") != "rpki_invalid_sample"),
            ("catalogue_labelled", (pl.col("reason") != "rpki_invalid_sample") & pl.col("labelled")),
            ("catalogue_selected", ~pl.col("reason").is_in(["stratified", "rpki_invalid_sample"])),
            ("stratified", pl.col("reason") == "stratified"),
            ("unlabelled_stratified", (pl.col("reason") == "stratified") & ~pl.col("labelled")),
            ("invalid_stratum", pl.col("reason") == "rpki_invalid_sample"))}
        annual[year]["selection"] = {"rows": original.height, "usable": e.height,
                                    "errors": original.filter(pl.col("error").is_not_null()).group_by("error").len().to_dicts(),
                                    "paper_rows": original.filter(pl.col("reason") != "rpki_invalid_sample").height,
                                    "invalid_stratum_rows": original.filter(pl.col("reason") == "rpki_invalid_sample").height}
        annual[year]["paper_controls"] = read(base / "rpki_validity_summary_labelled.json")
        annual[year]["later_validity"] = read(base / "later_validity.json")
        followup = read(base / "later_validity.parquet").select("event_id", "later_valid")
        invalid_followup = e.filter(pl.col("validity") == "invalid").join(
            followup, on="event_id", how="left", validate="1:1")
        if invalid_followup["later_valid"].null_count():
            raise ValueError(f"Missing follow-up flag in {year}")
        annual[year]["invalid_stratum_not_later_valid"] = facts(invalid_followup.filter(
            (pl.col("reason") == "rpki_invalid_sample") & ~pl.col("later_valid")))
        if year in (2024, 2025):
            annual[year]["radar_rpki_agreement"] = read(base / "radar_rpki_agreement.json")
            matches = read(base / "radar_rpki_agreement.parquet")
            if year == 2025:
                retained = matches.filter(~(pl.col("event_id").str.starts_with("20250528T")
                                            & pl.col("event_id").str.ends_with("_53013")))
                annual[year]["radar_rpki_without_20250528_as53013"] = {
                    "matched_events": retained.height,
                    "agreement": (retained["ours"] == retained["radar"]).mean(),
                    "excluded_matches": matches.height - retained.height}
        for tag in ("leak", "withdrawal"):
            selected = read(args.data / "eventset" / f"{year}_{tag}" / "events.parquet")
            f = scores(selected)
            annual[year][tag] = facts(f)
            annual[year][tag]["selected_events"] = selected.height
            annual[year][tag]["excluded_events"] = selected.height - f.height
            if tag == "leak":
                annual[year]["leak_clean"] = facts(f.filter(pl.col("observation_lag_s") >= -60))
                annual[year]["leak_large200"] = facts(f.filter(pl.col("extent") >= 200))
                annual[year]["leak_long_identifier"] = facts(f.filter(pl.col("duration_min") > 10))
                annual[year]["leak_ephemeral_identifier"] = facts(f.filter(pl.col("duration_min") < 1))
        annual[year]["per_collector_combined_population"] = read(base / "per_vp_duration.json")["per_vp_spread"]
        suffix = "" if year == 2022 else "_labelled"
        vp = read(base / f"per_vp_by_validity{suffix}.json")
        rows = [r for r in vp["per_vp_by_validity"] if r["delta"] == "d30s"]
        annual[year]["per_collector"] = {v: {r["collector"]: r["jaccard_mean"] for r in rows if r["validity"] == v}
                                         for v in ("invalid", "unknown", "valid")}

    def row(label, values):
        return label + " & " + " & ".join(values) + r" \\" + "\n"

    def block(title):
        return r"\midrule" + "\n" + r"\multicolumn{6}{l}{\emph{" + title + r"}} \\" + "\n"

    def n(value):
        return f"{value:,.0f}"

    def pct(value):
        return f"{value * 100:.1f}" + r"\,\%"

    tables = {}
    floor = r"\begin{tabular}{lrrrrr}" + "\n" + r"\toprule" + "\n" + row("", map(str, YEARS))
    floor += block("catalogue population (2022: stratified sample only)")
    a = [annual[y]["paper"] for y in YEARS]
    floor += row("usable replayed events", [n(x["events"]) for x in a])
    floor += row("train / test", [f"{n(x['train'])} / {n(x['test'])}" for x in a])
    floor += row(r"$\Jac$ at 30\,s, mean / median", [f"{x['floors']['d30s']:.2f} / {x['j30_median']:.2f}" for x in a])
    floor += row(r"at 1 / 5 / 15\,min", [" / ".join(f"{x['floors'][h]:.2f}" for h in HORIZONS[1:]) for x in a])
    floor += row(r"extent at 2\,h, p50 / p90 ASes", [" / ".join(map(n, x["extent"])) for x in a])
    for pop, title in (("stratified", "stratified sample only"), ("invalid_stratum", "label-free RPKI-invalid stratum")):
        floor += block(title)
        a = [annual[y][pop] for y in YEARS]
        floor += row(r"$\Jac$ at 30\,s, mean (test $n$)", [f"{x['floors']['d30s']:.2f} ({n(x['test'])})" for x in a])
        if pop == "stratified":
            floor += row(r"at 1 / 5 / 15\,min", [" / ".join(f"{x['floors'][h]:.2f}" for h in HORIZONS[1:]) for x in a])
    tables["floors"] = floor + "\\bottomrule\n\\end{tabular}\n"

    valid = "\\begin{tabular}{llrrrrr}\n\\toprule\n" + row(" & new origin", map(str, YEARS)) + "\\midrule\n"
    for label, metric in (("share of events", "share"), ("Radar-labelled", "labelled_share"),
                          (r"extent at 2\,h, p50 ASes", "extent"), ("identifier duration p50", "duration_median"),
                          (r"$\Jac$ at 30\,s (test $n$)", "floor"), (r"growing at 30\,s", "growing_share")):
        for i, cls in enumerate(("invalid", "unknown", "valid")):
            cells = []
            for year in YEARS:
                parent = annual[year]["paper"]
                x = parent["validity"][cls]
                if metric == "share": value = pct(x["events"] / parent["events"])
                elif metric == "extent": value = n(x["extent"][0])
                elif metric == "floor": value = f"{x['floors']['d30s']:.2f} ({n(x['test'])})"
                elif metric == "duration_median": value = n(x[metric]) + r"\,min"
                else: value = "--" if metric == "labelled_share" and year == 2022 else pct(x[metric])
                cells.append(value)
            valid += row((label if i == 0 else "") + " & " + cls, cells)
    tables["validity"] = valid + "\\bottomrule\n\\end{tabular}\n"
    vp = "\\begin{tabular}{lrrrrr}\n\\toprule\n" + row("class", map(str, YEARS)) + "\\midrule\n"
    for cls in ("invalid", "unknown", "valid"):
        vp += row(cls, [f"{min(annual[y]['per_collector'][cls].values()):.2f}--{max(annual[y]['per_collector'][cls].values()):.2f}" for y in YEARS])
    tables["pervp"] = vp + "\\bottomrule\n\\end{tabular}\n"
    for name, table in tables.items():
        (args.out / f"{name}.tex").write_text("% Generated by scripts/paper_propagation_tables.py\n" + table)
    (args.out / "propagation-facts.json").write_text(json.dumps({"inputs_sha256": inputs, "years": annual}, indent=2) + "\n")


if __name__ == "__main__":
    main()
