"""Generate the paper's ROV frontier table from finalized historical-only results."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", type=Path)
    ap.add_argument("out", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    inputs, annual = {}, {}
    def load(year, suffix):
        path = args.data / "eventset" / str(year) / f"rov_frontier{suffix}.json"
        inputs[str(path.relative_to(args.data))] = hashlib.sha256(path.read_bytes()).hexdigest()
        result = json.loads(path.read_text())
        if result.get("lookup_policy") != "latest measurement at or before event date; missing history is unknown":
            raise ValueError(f"Historical-only lookup missing: {path}")
        return result
    def row(values): return " & ".join(values) + r" \\" + "\n"
    def fraction(x): return "--" if x is None else f"{x:.2f}"
    table = "\\begin{tabular}{llrrrr}\n\\toprule\n"
    table += row(["year", "new origin", "events: measured / total", "ROV share: C / F", "coverage: C / F", r"log-odds [95\,\% CI]"])
    table += "\\midrule\n"
    def cells(year, label, d):
        interval = d["log_odds_mean_ci95_bootstrap"]
        value = d["log_odds_frontier_vs_carriers_mean"]
        odds = "--" if value is None else f"${value:+.2f}$"
        if interval is not None: odds += f" [${interval[0]:+.2f}$, ${interval[1]:+.2f}$]"
        return [str(year), label, f"{d['events_with_both_measured']:,} / {d['events']:,}",
                fraction(d["enforcing_share_carriers"])+" / "+fraction(d["enforcing_share_frontier"]),
                fraction(d["carriers_measured_share"])+" / "+fraction(d["frontier_measured_share"]), odds]
    for year in range(2022,2027):
        suffix = "" if year == 2022 else "_labelled" + ("_frozen2505" if year>=2025 else "")
        data = load(year, suffix)
        annual[year] = {"paper": data}
        for validity in ("invalid", "unknown", "valid"):
            table += row(cells(year, validity, data["by_validity"][validity]))
    table += "\\midrule\n"
    table += r"\multicolumn{6}{l}{\emph{Separate RPKI-invalid sampling stratum}} \\" + "\n"
    for year in range(2023,2027):
        data = load(year, "_stratum" + ("_frozen2505" if year>=2025 else ""))
        annual[year]["invalid_stratum"] = data
        table += row(cells(year, "invalid", data["by_validity"]["invalid"]))
    table += "\\bottomrule\n\\end{tabular}\n"
    (args.out / "frontier.tex").write_text(table)
    (args.out / "frontier_facts.json").write_text(json.dumps({"inputs_sha256": inputs, "years": annual}, indent=2)+"\n")

if __name__ == "__main__": main()
