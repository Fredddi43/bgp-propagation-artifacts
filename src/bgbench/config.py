"""Paths and constants. Cluster layout per ADR-0011; overridable via env vars."""

from __future__ import annotations

import os
from pathlib import Path

DATA_ROOT = Path(
    os.environ.get("BGBENCH_DATA_ROOT", "data")
)
WORK_ROOT = Path(
    os.environ.get("BGBENCH_WORK_ROOT", "work")
)
SECRETS_DIR = Path(
    os.environ.get("BGBENCH_SECRETS", "secrets")
)

PARQUET_DIR = DATA_ROOT / "parquet"  # updates: <collector>/<YYYY-MM-DD>/part-HH.parquet
AGG_DIR = DATA_ROOT / "aggregates"  # per-collector per-minute signals
RIB_DIR = DATA_ROOT / "ribs"
BEACON_DIR = DATA_ROOT / "beacons"
EVENT_DIR = DATA_ROOT / "events"
MANIFEST_DIR = DATA_ROOT / "manifests"  # one JSON per collector-day

BROKER_URL = "https://api.bgpkit.com/v3/broker/search"


# RIS collectors publish 5-min update files (288/day), RouteViews 15-min (96/day).
def expected_update_files(collector: str) -> int:
    if collector.startswith("pch."):
        return 1440                    # PCH IXP route collectors: one MRT update file per minute
    return 288 if collector.startswith("rrc") else 96


def shm_dir() -> Path:
    """RAM-backed scratch (ADR-0011). Falls back to WORK_ROOT/tmp off-cluster."""
    base = Path(os.environ.get("BGBENCH_SHM", "/dev/shm"))
    if not base.exists():
        base = WORK_ROOT / "tmp"
    job = os.environ.get("SLURM_JOB_ID", str(os.getpid()))
    return base / f"bgbench-{job}"


def release_shm(path: Path) -> None:
    """Delete a scratch dir under shm_dir() and every parent it leaves empty, up to and including bgbench-<id>.
    Removing only the leaf left one empty bgbench-<id>/<kind>/<collector>/ tree per run (11,790 in the original runs,
    2026-09-26). Parents that still hold another task's scratch in the same job are kept."""
    import shutil

    shutil.rmtree(path, ignore_errors=True)
    root = shm_dir()
    if root not in path.parents:
        return
    p = path.parent
    while True:
        try:
            p.rmdir()
        except OSError:
            return
        if p == root:
            return
        p = p.parent


def tgn_dir(year: int, delta_s: int, tag: str = "") -> Path:
    """Per-event graph tensors (tgn_data.build_split writes, gnn_train / tgn_train read); tag = replay set ('' | 'leak')."""
    return DATA_ROOT / "tgn" / (f"{year}_{tag}" if tag else str(year)) / f"d{delta_s}s"

# temporal split: months <= SPLIT_MONTH train, later months test (8 = Jan–Aug / Sep–Dec). Partial years set BGB_SPLIT_MONTH
# (2026 Jan–Aug uses 5: Jan–May train, Jun–Aug test).
SPLIT_MONTH = int(os.environ.get("BGB_SPLIT_MONTH", "8"))
