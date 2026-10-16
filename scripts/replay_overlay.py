"""Writable replay overlays without changing the frozen original replay trees.

prepare populates event-directory links and atomically redirects the correction
checkout's root links. publish atomically replaces only repaired event links.
No event tables are published here; coordinate those with downstream readers.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

FAMILIES = {"origin": "events_replay", "leak": "events_replay_leak", "withdrawal": "events_replay_withdrawal"}


def atomic_link(destination: Path, target: Path):
    temporary = destination.with_name(f".{destination.name}.link-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(destination)


def prepare(original: Path, corrected: Path, overlay: Path, workers: int):
    if original.resolve() == corrected.resolve():
        raise ValueError("original and correction data roots must differ")
    overlay.mkdir(parents=True, exist_ok=True)
    report = []
    for family, name in FAMILIES.items():
        source = original / name
        target = overlay / name
        target.mkdir(parents=True, exist_ok=True)
        names = [entry.name for entry in os.scandir(source)]
        def one(entry_name):
            link = target / entry_name
            if not link.exists() and not link.is_symlink():
                link.symlink_to(source / entry_name)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, names))
        link = corrected / name
        if link.exists() and not link.is_symlink():
            raise ValueError(f"refusing to replace an existing real directory: {link}")
        atomic_link(link, target)
        report.append({"family": family, "entries": len(names), "original": str(source), "overlay": str(target)})
        print(json.dumps(report[-1]), flush=True)
    (overlay / "prepared.json").write_text(json.dumps(report, indent=1))


def publish(overlay: Path, repair: Path, report_file: Path):
    if not (overlay / "prepared.json").exists():
        raise ValueError("prepare the overlay before publishing repaired event links")
    report = json.loads(report_file.read_text())
    published = []
    for row in report:
        if row["status"] not in ("merged", "excluded"):
            continue
        family = row["tag"] or "origin"
        target = repair / "events" / family / row["event_id"]
        summary = json.loads((target / "summary.json").read_text())
        if bool(summary.get("error")) != (row["status"] == "excluded"):
            raise ValueError(f"repair status disagrees with summary: {row['event_id']}")
        atomic_link(overlay / FAMILIES[family] / row["event_id"], target)
        published.append({"family": family, "event_id": row["event_id"], "target": str(target)})
    (overlay / "published.json").write_text(json.dumps(published, indent=1))
    print(json.dumps({"published": len(published)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "publish"])
    parser.add_argument("--original", type=Path)
    parser.add_argument("--corrected", type=Path)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--repair", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.original, args.corrected, args.overlay, args.workers)
    else:
        publish(args.overlay, args.repair, args.report)
