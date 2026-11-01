"""Provenance of the origin-change allowlist ("persistent-flapper whitelist") threshold per year, for the paper.

Question: which threshold did identifier2.dedupe_origin_events actually apply in each monthly run (2022-2026)?
run_events scales F per week since commit 86b9b4b2 (f_eff = round(F * days / 7)), the output directory keeps the
unscaled f{F}, and summary.json records only the unscaled flapper_bins. So the effective threshold is recovered
from the outputs themselves:

  * min(bins) over flapper_whitelist.parquet   -> threshold <= min_wl
  * max over kept pairs of sum(n_bins) in origin_change_events.parquet (every kept bin of a pair belongs to exactly
    one event, so this sum is the pair's bin count)  -> threshold > max_kept
  => the threshold lies in (max_kept, min_wl]; we report which of flat F and round(F * days / 7) falls inside.

Plus file mtimes vs the commit dates, the code version recorded in the run logs, and the downstream chain
(identifier2 -> inventory/<y>/events_ranked -> replay_selection -> eventset/<y>/events) checked by joins.

Cluster access is read-only (ssh: stat, tar to stdout, grep, and a python -B -I read from stdin in /tmp).
usage: python -B scripts/paper_allowlist_by_year.py --cache <dir> [--host <BATCH_HOST>] [--out <json>] [--refresh]
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[1]
D = "<MODELS_ROOT>/nobackup/<PROJECT>"
L = "<RESULTS_ROOT>/nobackup/<PROJECT>/logs"
VENV_PY = "<RESULTS_ROOT>/work/<PROJECT>/venv/bin/python"
RELEASE = REPO / "data" / "corrected-release-20261016"
YEARS = [2022, 2023, 2024, 2025, 2026]
F = 50
SCALING_COMMIT = "86b9b4b2"
LABEL_FIX_COMMIT = "ac4ad7a8"

# Which job wrote the files now on disk (matched by file mtime against the log windows; see the "runs" notes).
RUN_LOGS = {
    2022: {"writer": "inv_2022_m1_50616672.log", "driver": "extend_2022_50604932.log"},
    2023: {"writer": "inv_2023_leak_m1_50435357.log", "driver": "inventory_2023_50430718.log",
           "earlier": ["inv_2023_m1_50426372.log", "inv_2023_m1_50434683.log"], "earlier_driver": "inventory_2023_50425278.log"},
    2024: {"writer": "ident2024d_50183224.log", "eval": "identeval_50183617.log"},
    2025: {"writer": "inv_2025_m1_50430821.log", "driver": "inventory_2025_50425883.log",
           "later_skip_ident": "inv_2025_m1_50435574.log"},
    2026: {"writer": "inv_2026_m1_50648648.log", "driver": "extend_2026_50618948.log"},
}

REMOTE_PY = r'''
import glob, json, os, datetime as dt, hashlib
import polars as pl
D = "<MODELS_ROOT>/nobackup/<PROJECT>"
F = 50
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
out = {}
for y in (2022, 2023, 2024, 2025, 2026):
    frames, months = [], []
    for d in sorted(glob.glob(f"{D}/identifier2/{y}-*_{y}-*")):
        f = f"{d}/m2_b5_events_f50/origin_change_events.parquet"
        if not os.path.exists(f):
            continue
        win = os.path.basename(d)
        s, e = win.split("_")
        days = (dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days + 1
        scaled = max(1, round(F * days / 7))
        ev = pl.read_parquet(f, columns=["prefix", "new_origin", "first_ts", "n_bins"])
        pairs = ev.group_by("prefix", "new_origin").agg(bins=pl.col("n_bins").sum(), n_ev=pl.len())
        band = pairs.filter((pl.col("bins") >= F) & (pl.col("bins") < scaled))
        months.append({"window": win, "days": days, "events": ev.height, "kept_pairs": pairs.height,
                       "max_kept_pair_bins": int(pairs["bins"].max()),
                       "kept_pairs_bins_ge_F_lt_scaled": band.height,
                       "kept_events_in_pairs_bins_ge_F_lt_scaled": int(band["n_ev"].sum() or 0)})
        frames.append(ev.with_columns(win=pl.lit(win), days=pl.lit(days),
                                      pair_bins=pl.col("n_bins").sum().over("prefix", "new_origin")))
    allev = pl.concat(frames, how="diagonal_relaxed")
    r = {"months": months, "identifier2_events_total": allev.height}
    rk = f"{D}/inventory/{y}/events_ranked.parquet"
    ranked = pl.read_parquet(rk, columns=["prefix", "new_origin", "first_ts", "month"])
    r["events_ranked_rows"] = ranked.height
    r["events_ranked_semi_join_identifier2"] = ranked.join(allev.select("prefix", "new_origin", "first_ts").unique(),
                                                          on=["prefix", "new_origin", "first_ts"], how="semi").height
    r["events_ranked_unique_keys"] = ranked.unique(["prefix", "new_origin", "first_ts"]).height
    r["identifier2_unique_keys"] = allev.unique(["prefix", "new_origin", "first_ts"]).height
    sp = f"{D}/inventory/{y}/replay_selection.parquet"
    sel = pl.read_parquet(sp, columns=["prefix", "new_origin", "first_ts", "event_id"])
    r["replay_selection_sha256"] = sha(sp)
    r["replay_selection_rows"] = sel.height
    j = sel.join(allev.select("prefix", "new_origin", "first_ts", "win", "days", "pair_bins"),
                 on=["prefix", "new_origin", "first_ts"], how="left")
    jj = j.group_by("event_id").agg(wins=pl.col("win").drop_nulls().unique().sort(),
                                     pair_bins=pl.col("pair_bins").max(), days=pl.col("days").max())
    r["replay_selection_matched_in_identifier2"] = int(jj.filter(pl.col("wins").list.len() > 0).height)
    r["replay_selection_by_window"] = {str(k): v for k, v in
        jj.with_columns(w=pl.col("wins").list.join("+")).group_by("w").len().sort("w").iter_rows()}
    scaled_expr = (pl.lit(F) * pl.col("days") / 7).round(0)
    r["replay_selected_in_pairs_bins_ge_F_lt_scaled"] = int(jj.filter((pl.col("pair_bins") >= F) & (pl.col("pair_bins") < scaled_expr)).height)
    ep = f"{D}/eventset/{y}/events.parquet"
    es = pl.read_parquet(ep, columns=["event_id"])
    r["eventset_rows"] = es.height
    r["eventset_ids_in_replay_selection"] = es.join(sel.select("event_id"), on="event_id", how="semi").height
    r["eventset_sha256"] = sha(ep)
    out[str(y)] = r
print(json.dumps(out))
'''


def ssh(host: str, cmd: str, stdin: bytes | None = None) -> bytes:
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", host, cmd], input=stdin,
                       capture_output=True, timeout=1800, check=False)
    if p.returncode != 0:
        sys.exit(f"ssh failed ({cmd[:80]}...): {p.stderr.decode()[-2000:]}")
    return p.stdout


def fetch(host: str, cache: Path, refresh_parts: set[str]) -> None:
    """refresh_parts: subset of {files, stat, logs, remote} (or {all}) to re-fetch even when cached."""
    cache.mkdir(parents=True, exist_ok=True)
    wl = cache / "identifier2"

    def want(part: str, path: Path) -> bool:
        return "all" in refresh_parts or part in refresh_parts or not path.exists()

    if want("files", wl):
        wl.mkdir(exist_ok=True)
        tar = ssh(host, f"cd {D}/identifier2 && tar cf - 20*/m*_events_f*/flapper_whitelist.parquet "
                        "20*/m*_events_f*/summary.json 20*/m*_events_f*/evaluation_windowed.json 2>/dev/null")
        subprocess.run(["tar", "xf", "-", "-C", str(wl)], input=tar, check=True)
    if want("stat", cache / "stat.txt"):
        st = ssh(host, f'cd {D} && stat -c "%n|%s|%y" identifier2/20*/m*_events_f*/* inventory/20*/events_ranked.parquet '
                       f'inventory/20*/replay_selection.parquet inventory/20*/replay_manifest.tsv eventset/20??/events.parquet')
        (cache / "stat.txt").write_bytes(st)
    if want("logs", cache / "logs.json"):
        names = sorted({n for v in RUN_LOGS.values() for k, n in v.items() if k != "earlier"}
                       | {n for v in RUN_LOGS.values() for n in v.get("earlier", [])})
        logs = {}
        for n in names:
            txt = ssh(host, f'cd {L} && stat -c "%y" {n} && grep -n "^repo at " {n} | cut -c1-200; '
                            f'grep -m4 -n "whitelisted_pairs\\|identify2-events\\|Error" {n} | cut -c1-240')
            logs[n] = txt.decode().splitlines()
        (cache / "logs.json").write_text(json.dumps(logs, indent=1))
    if want("remote", cache / "remote_checks.json"):
        res = ssh(host, f"cd /tmp && {VENV_PY} -B -I -", stdin=REMOTE_PY.encode())
        (cache / "remote_checks.json").write_bytes(res)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout.strip()


def contains_scaling(commit: str) -> bool:
    return subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", SCALING_COMMIT, commit],
                          check=False).returncode == 0


def sha256(p: Path) -> str | None:
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(cache: Path) -> dict:
    stats = {}
    for line in (cache / "stat.txt").read_text().splitlines():
        n, size, mtime = line.split("|")
        assert mtime.endswith("+0000"), mtime
        stats[n] = {"bytes": int(size), "mtime_utc": mtime[:19]}
    logs = json.loads((cache / "logs.json").read_text())
    remote = json.loads((cache / "remote_checks.json").read_text())

    def repo_at(name: str) -> str | None:
        """Last 'repo at' line: the git_sync immediately before the driver submitted the month jobs (the shared
        checkout is only ever reset forward to origin/main, so the month jobs ran this commit or a later one)."""
        hits = [ln.split("repo at ")[1].split()[0] for ln in logs.get(name, []) if "repo at " in ln]
        return hits[-1] if hits else None

    commit_dates = {c: git("show", "-s", "--format=%cI", c) for c in (SCALING_COMMIT, LABEL_FIX_COMMIT)}
    scaling_utc = dt.datetime.fromisoformat(commit_dates[SCALING_COMMIT]).astimezone(dt.UTC)

    months_out: dict[str, list] = {str(y): [] for y in YEARS}
    remote_month = {m["window"]: m for y in YEARS for m in remote[str(y)]["months"]}
    for f in sorted(glob.glob(str(cache / "identifier2" / "20*" / "m*_events_f*" / "flapper_whitelist.parquet"))):
        p = Path(f)
        win, sub = p.parent.parent.name, p.parent.name
        s, e = win.split("_")
        y = int(s[:4])
        if sub != "m2_b5_events_f50" or int(e[:4]) != y or y not in YEARS:
            continue
        days = (dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days + 1
        scaled = max(1, round(F * days / 7))
        wl = pl.read_parquet(p)
        min_wl = int(wl["bins"].min())
        rm = remote_month.get(win, {})
        max_kept = rm.get("max_kept_pair_bins")
        lo, hi = (max_kept + 1 if max_kept is not None else None), min_wl
        flat_ok = lo is not None and lo <= F <= hi
        scaled_ok = lo is not None and lo <= scaled <= hi
        summ = p.parent / "summary.json"
        sj = json.loads(summ.read_text()) if summ.exists() else None
        rel = f"identifier2/{win}/{sub}/flapper_whitelist.parquet"
        mtime = stats.get(rel, {}).get("mtime_utc")
        before = (dt.datetime.fromisoformat(mtime + "+00:00") < scaling_utc) if mtime else None
        if flat_ok and scaled_ok and F == scaled:
            # 7-day window (the 2024 beacon week): flat F and the per-week rule give the same threshold
            applied, kind = F, "seven_day_window_flat_equals_scaled"
        elif flat_ok and not scaled_ok:
            applied, kind = F, "flat"
        elif scaled_ok and not flat_ok:
            applied, kind = scaled, "per_week_scaled"
        else:
            applied, kind = None, "ambiguous"
        entry = {
            "window": win, "days": days, "subdir": sub, "F_param": F,
            "threshold_bins_applied": applied, "rule": kind,
            "threshold_interval_from_outputs": [lo, hi],
            "flat_F_consistent": flat_ok, "scaled_value": scaled, "scaled_consistent": scaled_ok,
            "whitelist_min_bins": min_wl, "whitelist_pairs_at_min": int((wl["bins"] == min_wl).sum()),
            "whitelisted_pairs_parquet": wl.height,
            "whitelisted_pairs_summary": sj.get("whitelisted_pairs") if sj else None,
            "summary_json": "present" if sj else "absent (run crashed in the label evaluation after writing the parquet files)",
            "max_kept_pair_bins": max_kept,
            "events": rm.get("events"),
            "kept_pairs_bins_ge_F_lt_scaled": rm.get("kept_pairs_bins_ge_F_lt_scaled"),
            "kept_events_in_pairs_bins_ge_F_lt_scaled": rm.get("kept_events_in_pairs_bins_ge_F_lt_scaled"),
            "whitelist_pairs_bins_lt_scaled": int((wl["bins"] < scaled).sum()),
            "whitelist_mtime_utc": mtime, "written_before_86b9b4b2": before,
            "confidence": "established" if applied is not None else "unknown",
        }
        ev = p.parent / "evaluation_windowed.json"
        if sj and "hijacks" in sj and sj["hijacks"].get("by_size"):
            entry["hijack_recall_same_run"] = {b["bucket"]: [round(b["recall"], 3), b["n"]] for b in sj["hijacks"]["by_size"]}
            if ev.exists():
                entry["hijack_recall_same_run_note"] = ("superseded: this run scored one month of events against the whole "
                                                         "year's labels (fixed in a8cabbee); see evaluation_windowed_recall")
        if ev.exists():
            ej = json.loads(ev.read_text())
            entry["evaluation_windowed_recall"] = {b["bucket"]: [round(b["recall"], 3), b["n"]] for b in ej["hijacks"]["by_size"]}
            entry["evaluation_windowed_sha256"] = sha256(ev)
        months_out[str(y)].append(entry)

    years = {}
    for y in YEARS:
        ms = months_out[str(y)]
        rules = sorted({m["rule"] for m in ms if m["days"] >= 28})
        rr = remote[str(y)]
        rl = RUN_LOGS[y]
        run_commits = {k: repo_at(v) for k, v in rl.items() if isinstance(v, str) and repo_at(v)}
        local_sel = RELEASE / "inventory" / str(y) / "replay_selection.parquet"
        local_es = RELEASE / "eventset" / str(y) / "events.parquet"
        years[str(y)] = {
            "rule": rules[0] if len(rules) == 1 else rules,
            "F_param": F,
            "threshold_bins_by_window_length": sorted({(m["days"], m["threshold_bins_applied"]) for m in ms}),
            "months": len(ms),
            "confidence": "established" if all(m["confidence"] == "established" for m in ms) else "partly unknown",
            "whitelist_mtime_range_utc": [min(m["whitelist_mtime_utc"] for m in ms), max(m["whitelist_mtime_utc"] for m in ms)],
            "all_written_before_86b9b4b2": all(m["written_before_86b9b4b2"] for m in ms),
            "run_logs": {k: (f"{L}/{v}" if isinstance(v, str) else [f"{L}/{x}" for x in v]) for k, v in rl.items()},
            "run_log_repo_at": run_commits,
            "run_commits_contain_86b9b4b2": {c: contains_scaling(c) for c in run_commits.values()},
            "downstream": {
                "chain": "ranking.load_year_events(year, tag='m2_b5_events_f50') globs identifier2/<y>-*_<y>-*/m2_b5_events_f50/"
                         "origin_change_events.parquet -> inventory/<y>/events_ranked.parquet -> select-replay -> "
                         "replay_selection.parquet -> replay_manifest.tsv -> eventset/<y>/events.parquet",
                "identifier2_event_rows": rr["identifier2_events_total"],
                "events_ranked_rows": rr["events_ranked_rows"],
                "events_ranked_rows_found_in_identifier2": rr["events_ranked_semi_join_identifier2"],
                "identifier2_unique_event_keys": rr.get("identifier2_unique_keys"),
                "events_ranked_unique_event_keys": rr.get("events_ranked_unique_keys"),
                "replay_selection_rows": rr["replay_selection_rows"],
                "replay_selection_matched_in_identifier2": rr["replay_selection_matched_in_identifier2"],
                "replay_selection_by_identifier2_window": rr["replay_selection_by_window"],
                "replay_selected_in_pairs_bins_ge_F_lt_scaled": rr["replay_selected_in_pairs_bins_ge_F_lt_scaled"],
                "eventset_rows": rr["eventset_rows"],
                "eventset_ids_in_replay_selection": rr["eventset_ids_in_replay_selection"],
                "release_replay_selection_sha256_equals_cluster": sha256(local_sel) == rr["replay_selection_sha256"],
                "release_eventset_sha256_equals_cluster": sha256(local_es) == rr["eventset_sha256"],
                **release_eventset_check(local_es, local_sel),
                "cluster_mtimes_utc": {k: stats.get(f"inventory/{y}/{k}", {}).get("mtime_utc")
                                       for k in ("events_ranked.parquet", "replay_selection.parquet", "replay_manifest.tsv")},
            },
            "run_notes": RUN_NOTES[y],
            "monthly": ms,
        }
    # the paper's printed 2024 recall (0.66-0.73 at 10-49 peers) comes from identifier-summary-verification.json, whose
    # input hashes must equal the evaluation_windowed.json files of the flat-F=50 directories
    ver = json.loads((REPO / "docs/paper/corrections-2026-10-16/identifier-summary-verification.json").read_text())["input_sha256"]
    want_eval = {k: h for k, h in ver.items() if k.endswith("evaluation_windowed.json")}
    got = {f"identifier2/{m['window']}/{m['subdir']}/evaluation_windowed.json": m.get("evaluation_windowed_sha256")
           for m in years["2024"]["monthly"]}
    paper_recall = {
        "source": "docs/paper/corrections-2026-10-16/identifier-summary-verification.json (input_sha256)",
        "evaluation_files_pinned": len(want_eval),
        "pinned_hashes_equal_flat_F50_outputs": sum(got.get(k) == h for k, h in want_eval.items()),
        "recall_10_49_range_2024": [min(m["evaluation_windowed_recall"]["10-49"][0] for m in years["2024"]["monthly"] if "evaluation_windowed_recall" in m),
                                    max(m["evaluation_windowed_recall"]["10-49"][0] for m in years["2024"]["monthly"] if "evaluation_windowed_recall" in m)],
    }
    return {"commit_dates": commit_dates, "paper_2024_recall_provenance": paper_recall, "years": years}


def release_eventset_check(es_path: Path, sel_path: Path) -> dict:
    if not es_path.exists() or not sel_path.exists():
        return {"release_eventset_rows": None}
    es = pl.read_parquet(es_path, columns=["event_id"])
    sel = pl.read_parquet(sel_path, columns=["event_id"])
    return {"release_eventset_rows": es.height,
            "release_eventset_ids_in_release_replay_selection": es.join(sel, on="event_id", how="semi").height}


RUN_NOTES = {
    2022: "extend_year.sh -> inventory_year.sh driver synced to 536b67d (contains 86b9b4b2) and submitted array 50616672; the "
          "month jobs wrote events and whitelist on 2026-09-14 19:06-19:07 UTC, then crashed in the hijack evaluation (no 2022 "
          "Cloudflare hijack labels: ColumnNotFoundError min_hijack_ts), hence no summary.json. The traceback cites cli.py:683 and "
          "identifier2.py:373, the line numbers of the post-86b9b4b2 file.",
    2023: "Three identify2-events runs, all after 86b9b4b2: array 50426372 (driver at 1f28986, 2026-09-08 ~19:22 UTC), array "
          "50434683 (driver at 5c360e3; crashed with KeyError 'recall' after writing the parquet files), and the run logged as "
          "inv_2023_leak_m*_50435357 (2026-09-09 00:38 UTC, right after ac4ad7a8 fixed that KeyError), which wrote the files now "
          "on disk; its log has no 'repo at' line, but the shared checkout is only reset forward from 5c360e3. January "
          "whitelisted_pairs is 841 in the first and the last run.",
    2024: "jobs/ident2024.sh run 50183224 (git pull at a0919ae, 2026-09-04 18:53 +0900, which does not contain 86b9b4b2; its "
          "run_events calls dedupe_origin_events(oc_c, flapper_bins)) wrote all twelve months on 2026-09-04 11:41-11:49 UTC, "
          "i.e. 16-24 minutes before 86b9b4b2 was committed (12:05 UTC). identify2-eval (run 50183617 at 1c61676, also before "
          "86b9b4b2) re-scored the saved events with windowed labels into evaluation_windowed.json without recomputing the "
          "whitelist. The 7-day RIS beacon-week window 2024-06-10_2024-06-16 (23 RRCs, run 2026-09-03) also has an "
          "m2_b5_events_f50 table; ranking.load_year_events' glob includes it, so it feeds the 2024 ranking and selection "
          "(threshold 50 bins in 7 days, where the flat and per-week rules coincide). No 2024 month was re-run after 86b9b4b2.",
    2025: "inventory_year.sh driver at c8a768c (contains 86b9b4b2) submitted array 50430821, which wrote the files on "
          "2026-09-08 20:40-20:41 UTC; summary.json has no hijack evaluation because no Cloudflare hijack label file existed "
          "at that time. The later array 50435574 (driver at 3c32cf2) ran with SKIP_IDENT and reused these files.",
    2026: "extend_year.sh -> inventory_year.sh driver synced to c8703f6 (contains 86b9b4b2) and submitted array 50648648, which "
          "wrote the files on 2026-09-15 12:32-12:33 UTC.",
}


def code_and_docs() -> dict:
    """Static code/doc citations; each is checked against the working tree so a moved line fails loudly."""
    cites = {
        "dedupe_origin_events_threshold": ("src/bgbench/identifier2.py", 'whitelist = pairs.filter(pl.col("bins") >= flapper_bins)'),
        "run_events_scaling": ("src/bgbench/identifier2.py", "f_eff = max(1, round(flapper_bins * days / 7)) if flapper_per_week else flapper_bins"),
        "run_events_default_per_week": ("src/bgbench/identifier2.py", "flapper_per_week: bool = True,"),
        "out_dir_unscaled_name": ("src/bgbench/identifier2.py", 'f"m{min_collectors}_b{bin_min}_events_f{flapper_bins}"'),
        "summary_records_unscaled_only": ("src/bgbench/identifier2.py", '"flapper_bins": flapper_bins,'),
        "cli_no_per_week_option": ("src/bgbench/cli.py", "flapper_bins: int = typer.Option(20),"),
        "job_2024": ("jobs/ident2024.sh", "--flapper-bins 50"),
        "job_other_years": ("jobs/inventory_year.sh", "--flapper-bins 50"),
        "ranking_reads_f50_tables": ("src/bgbench/ranking.py", 'tag: str = "m2_b5_events_f50"'),
        "trailing_whitelist_defined_never_called": ("src/bgbench/identifier2.py", "def trailing_whitelist("),
        "doc_2024_flat_F50": ("docs/results/2026-09-04-inventory-2024.md", "same-window flapper whitelist"),
        "doc_2024_fix_planned": ("docs/results/2026-09-04-inventory-2024.md", "threshold per unit time (≈ 50 bins/week ⇒ ~200/month)"),
        "leak_identifier_no_allowlist_candidates": ("src/bgbench/leakcheck.py", "def triple_candidates("),
        "leak_identifier_no_allowlist_events": ("src/bgbench/leak_events.py", "def build_events("),
        "paper_text": ("paper/sections/03-data.tex", "a threshold of 50 bins in 2024"),
    }
    out = {}
    for k, (f, needle) in cites.items():
        lines = (REPO / f).read_text().splitlines()
        hits = [i + 1 for i, ln in enumerate(lines) if needle in ln]
        if not hits:
            sys.exit(f"citation {k}: {needle!r} not found in {f}")
        out[k] = f"{f}:{hits[0]}"
    calls = subprocess.run(["git", "-C", str(REPO), "grep", "-n", "trailing_whitelist(", "--", "src", "scripts", "jobs", "workflow"],
                           capture_output=True, text=True, check=False).stdout.splitlines()
    # exclude this script: its own git grep line contains the needle
    out["trailing_whitelist_call_sites"] = [c for c in calls if "def trailing_whitelist" not in c
                                            and not c.startswith("scripts/paper_allowlist_by_year.py:")]
    out["cli_exposes_flapper_per_week"] = "flapper_per_week" in (REPO / "src/bgbench/cli.py").read_text()
    leak_src = (REPO / "src/bgbench/leakcheck.py").read_text() + (REPO / "src/bgbench/leak_events.py").read_text()
    out["leak_code_mentions_whitelist_or_flapper"] = any(w in leak_src.lower() for w in ("whitelist", "allowlist", "flapper"))
    out["scaling_commit"] = git("show", "-s", "--format=%h %cI %s", SCALING_COMMIT)
    out["label_fix_commit"] = git("show", "-s", "--format=%h %cI %s", LABEL_FIX_COMMIT)
    out["identifier2_history"] = git("log", "--format=%h %cI %s", "--", "src/bgbench/identifier2.py").splitlines()
    return out


def summarise(res: dict) -> dict:
    ys = res["years"]
    by = {}
    for y, v in ys.items():
        th = sorted({m["threshold_bins_applied"] for m in v["monthly"] if m["days"] >= 28})
        by[y] = {"rule": v["rule"], "thresholds_bins": th, "confidence": v["confidence"]}
    scaled_years = [y for y, v in by.items() if v["rule"] == "per_week_scaled"]
    flat_years = [y for y, v in by.items() if v["rule"] == "flat"]
    assert flat_years == ["2024"] and scaled_years == ["2022", "2023", "2025", "2026"], by
    scaled_vals = sorted({t for y in scaled_years for t in by[y]["thresholds_bins"]})
    sentence = (
        "A retrospective allowlist removes (prefix, new origin) pairs that change in at least T five-minute bins of their "
        "calendar month: T = 50 in 2024, the year of the recall validation, and T = round(50 x days / 7), i.e. 50 bins per "
        f"week or {scaled_vals[0]}-{scaled_vals[-1]} bins per month, in 2022, 2023, 2025 and 2026, so the 2024 allowlist is "
        "about four times stricter."
    )
    ys = res["years"]
    rec = {y: [m["hijack_recall_same_run"]["10-49"][0] for m in ys[y]["monthly"]
               if "hijack_recall_same_run" in m and "hijack_recall_same_run_note" not in m and m["days"] >= 28]
           for y in scaled_years}
    note = {
        "same_threshold_as_other_years": False,
        "text": "The 2024 recall validation (10-49 peers: "
                f"{res['paper_2024_recall_provenance']['recall_10_49_range_2024'][0]}-"
                f"{res['paper_2024_recall_provenance']['recall_10_49_range_2024'][1]}) scored the flat T = 50 event tables. "
                "The other years' event tables used T = 200-221. Their own same-run windowed evaluations at 10-49 peers "
                + "; ".join(f"{y}: {min(v):.2f}-{max(v):.2f} over {len(v)} months" for y, v in rec.items() if v)
                + " (none for 2022 and 2025, which had no Cloudflare hijack labels when they ran). These figures are not "
                "a controlled comparison: label coverage and year differ.",
        "scaled_year_recall_10_49": {y: [min(v), max(v), len(v)] if v else None for y, v in rec.items()},
    }
    return {"by_year": by, "summary": sentence, "validation_threshold_note": note}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--host", default="<BATCH_HOST>")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--refresh", default="", help="comma list of cached parts to re-fetch: files,stat,logs,remote or all")
    a = ap.parse_args()
    fetch(a.host, a.cache, {p for p in a.refresh.split(",") if p})
    res = build(a.cache)
    res["code_and_docs"] = code_and_docs()
    s = summarise(res)
    res = {"question": "Effective origin-change allowlist threshold (bins per monthly analysis window) per year",
           "summary": s["summary"], "by_year": s["by_year"], "validation_threshold_note": s["validation_threshold_note"],
           "leak_events": "The leak identifier (first-seen path triples: leakcheck.triple_candidates/classify_triples, "
                          "leak_events.build_events) applies no allowlist; see code_and_docs.leak_* citations.",
           "method": "Effective threshold T bounded from the outputs: max over kept pairs of sum(n_bins) < T <= min(bins) of "
                     "flapper_whitelist.parquet; summary.json records only the unscaled flapper_bins.",
           **res,
           "generated_by": "scripts/paper_allowlist_by_year.py", "generated_at_utc": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    txt = json.dumps(res, indent=1, default=str)
    if a.out:
        a.out.write_text(txt + "\n")
    else:
        print(txt)


if __name__ == "__main__":
    main()
