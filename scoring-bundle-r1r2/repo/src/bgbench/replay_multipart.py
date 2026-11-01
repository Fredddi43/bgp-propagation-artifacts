"""Occurrence-preserving, source-aware merge of replay parts (several parts per collector allowed).

`replay_day.merge_event` refuses an event with more than one nonempty part for a collector, because equal retained
rows cannot identify source records (REPLAY-MERGE-PREVENTION.md). This module is the reviewed-semantics replacement for
that case. It follows the 2025/2026 occurrence restore (`scripts/forecast_restore_occurrences.py`):

* every row is a physical occurrence; rows are never value-deduplicated, and repeats inside one source archive are kept;
* each part declares the COMPLETE set of source archives it was extracted from (its ownership);
* an archive owned by exactly one part contributes that part's rows unchanged;
* an archive owned by several parts was ingested more than once. Its event projection is counted exactly once:
  result = sum(parts) - sum over archives u of (owners(u) - 1) * projection(u).

Two modes, both fail closed (raise `UnresolvedOccurrenceOwnership`, never exclude or zero an event):

* tagged: every part carries a `source_archive` column naming the archive of each row. Per-row ownership must lie in the
  part's declared archives; a shared archive's row multiset must be identical in every owning part, and the copy of the
  first owner (sorted by part label) is kept. Distinct archives are distinct physical records even when rows are equal.
* untagged: rows carry no archive identity (legacy parts). The caller supplies, for every shared archive, its complete
  event-filtered projection from an independent parse. Each projection must be contained in every owning part, and an
  equal tuple occurring in two parts beyond their explained shared occurrences is unexplained overlap. For two parts
  this is exactly `restore_pair`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from .replay_day import ROW_COLS, UnresolvedOccurrenceOwnership, measure_event

SOURCE_COL = "source_archive"
POLICY = "source_archive_ownership_preserve_all_record_occurrences"
PANEL = ("rrc25", "rrc00", "rrc12", "rrc01", "route-views3", "rrc03", "route-views2", "rrc20", "rrc15", "route-views.linx")


@dataclass(frozen=True, eq=False)
class OwnedPart:
    """One extracted part. `archives` is the complete ownership: every archive the part was parsed from, empty or not."""

    label: str
    collector: str
    archives: frozenset[str]
    frame: pl.DataFrame
    archive_sha256: dict = field(default_factory=dict, compare=False)


def _projected(frame: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise UnresolvedOccurrenceOwnership(f"Part lacks required columns {missing}")
    return frame.select(columns).with_columns(pl.col("collector").cast(pl.String))


def _check_collector(part: OwnedPart) -> None:
    if not isinstance(part.collector, str) or not part.collector.strip():
        raise UnresolvedOccurrenceOwnership(f"Part {part.label}: declared collector must be a nonblank string")
    if part.frame.height:
        values = part.frame["collector"].cast(pl.String).unique().to_list()
        if values != [part.collector]:
            raise UnresolvedOccurrenceOwnership(
                f"Part {part.label}: row collectors {values} differ from declared collector {part.collector}")


def _owners(parts: list[OwnedPart]) -> dict[str, list[OwnedPart]]:
    owners: dict[str, list[OwnedPart]] = {}
    for part in parts:
        if not part.archives:
            if part.frame.height:
                raise UnresolvedOccurrenceOwnership(f"Part {part.label}: rows without declared source archives")
        for archive in part.archives:
            owners.setdefault(archive, []).append(part)
    return owners


def _check_archive_hashes(archive: str, owning: list[OwnedPart]) -> None:
    hashes = {p.archive_sha256.get(archive) for p in owning if p.archive_sha256.get(archive) is not None}
    if len(hashes) > 1:
        raise UnresolvedOccurrenceOwnership(f"Archive {archive} has different content hashes in its owning parts")


def merge_collector_parts(parts: list[OwnedPart], shared_projections: dict[str, pl.DataFrame] | None = None,
                          columns: list[str] | None = None) -> tuple[pl.DataFrame, dict]:
    """Merge all parts of ONE collector. Returns (rows, proof). Rows have `columns` (default ROW_COLS)."""
    columns = list(columns or ROW_COLS)
    if not parts:
        raise UnresolvedOccurrenceOwnership("No parts to merge")
    parts = sorted(parts, key=lambda p: p.label)
    if len({p.label for p in parts}) != len(parts):
        raise UnresolvedOccurrenceOwnership("Duplicate part labels")
    collectors = {p.collector for p in parts}
    for part in parts:
        _check_collector(part)
    if len(collectors) != 1:
        raise UnresolvedOccurrenceOwnership(f"Parts of different collectors in one group: {sorted(collectors)}")
    collector = collectors.pop()
    owners = _owners(parts)
    shared = {u: o for u, o in owners.items() if len(o) > 1}
    for archive, owning in shared.items():
        _check_archive_hashes(archive, owning)
    tagged = all(SOURCE_COL in p.frame.columns for p in parts)
    if not tagged and any(SOURCE_COL in p.frame.columns and p.frame.height for p in parts):
        raise UnresolvedOccurrenceOwnership("Mixed tagged and untagged parts")
    if tagged:
        result, removed = _merge_tagged(parts, shared, shared_projections, columns)
        mode = "tagged_per_row_source_archive"
    else:
        result, removed = _merge_untagged(parts, shared, shared_projections or {}, columns)
        mode = "untagged_shared_projection_inclusion_exclusion"
    total = sum(p.frame.height for p in parts)
    distinct = result.select(columns).unique().height if result.height else 0
    proof = {
        "collector": collector,
        "mode": mode,
        "parts": [{"label": p.label, "archives": len(p.archives), "occurrences": p.frame.height} for p in parts],
        "archives_owned": len(owners),
        "shared_archives": sorted(shared),
        "part_occurrences": total,
        "repeated_ingestion_occurrences_removed": removed,
        "restored_occurrences": result.height,
        "restored_distinct_projected_tuples": distinct,
        "within_source_tuple_repeats_preserved": result.height - distinct,
        "source_message_identity_is_retained_tuple": False,
        "occurrence_policy": POLICY,
    }
    if result.height != total - removed:
        raise AssertionError("occurrence accounting mismatch")
    return result, proof


def _merge_tagged(parts, shared, shared_projections, columns):
    frames, removed = [], 0
    keep_cols = columns + [SOURCE_COL]
    by_part = {}
    for part in parts:
        frame = _projected(part.frame, keep_cols)
        if frame.height:
            sources = frame[SOURCE_COL]
            if sources.null_count():
                raise UnresolvedOccurrenceOwnership(f"Part {part.label}: rows with null source archive")
            stray = set(sources.unique().to_list()) - set(part.archives)
            if stray:
                raise UnresolvedOccurrenceOwnership(
                    f"Part {part.label}: rows from undeclared archives {sorted(stray)[:3]}")
        by_part[part.label] = frame
    for archive, owning in shared.items():
        projections = [Counter(by_part[p.label].filter(pl.col(SOURCE_COL) == archive).select(columns).iter_rows())
                       for p in owning]
        if any(c != projections[0] for c in projections[1:]):
            raise UnresolvedOccurrenceOwnership(
                f"Shared archive {archive}: event projections differ between owning parts")
        if shared_projections is not None and archive in shared_projections:
            if Counter(_projected(shared_projections[archive], columns).iter_rows()) != projections[0]:
                raise UnresolvedOccurrenceOwnership(f"Shared archive {archive}: independent projection differs")
        removed += (len(owning) - 1) * sum(projections[0].values())
    for part in parts:
        frame = by_part[part.label]
        drop = [u for u, owning in shared.items() if part.label in {o.label for o in owning[1:]}]
        if drop:
            frame = frame.filter(~pl.col(SOURCE_COL).is_in(drop))
        frames.append(frame)
    result = pl.concat(frames, how="vertical_relaxed") if frames else pl.DataFrame()
    return result, removed


def _merge_untagged(parts, shared, shared_projections, columns):
    if set(shared_projections) != set(shared):
        raise UnresolvedOccurrenceOwnership("Shared-source ownership is incomplete or unexpected")
    frames = {p.label: _projected(p.frame, columns) for p in parts}
    counts = {label: Counter(f.iter_rows()) for label, f in frames.items()}
    proj = {u: Counter(_projected(f, columns).iter_rows()) for u, f in shared_projections.items()}
    collector = parts[0].collector
    for u, c in proj.items():
        if any(row[columns.index("collector")] != collector for row in c):
            raise UnresolvedOccurrenceOwnership(f"Shared archive {u}: projection of another collector")
        for p in shared[u]:
            if any(counts[p.label][k] < n for k, n in c.items()):
                raise UnresolvedOccurrenceOwnership(
                    f"Shared archive {u}: projection not contained in part {p.label}")
    # Pairwise: an equal tuple in two parts beyond the occurrences explained by archives both parts own is unexplained.
    for i, a in enumerate(parts):
        for b in parts[i + 1:]:
            both = Counter()
            for u in a.archives & b.archives:
                both.update(proj[u])
            ca, cb = counts[a.label], counts[b.label]
            if any(min(ca[k], cb[k]) > both[k] for k in ca.keys() & cb.keys()):
                raise UnresolvedOccurrenceOwnership("Unexplained overlap requires additional raw-source attribution")
    # Each shared archive's projection is kept in its first owner and removed once from every later owner.
    remove = {p.label: Counter() for p in parts}
    removed = 0
    for u, owning in shared.items():
        for p in owning[1:]:
            remove[p.label].update(proj[u])
            removed += sum(proj[u].values())
    out = []
    for part in parts:
        frame, remaining = frames[part.label], remove[part.label].copy()
        if remaining:
            keep = []
            for row in frame.iter_rows():
                if remaining[row]:
                    remaining[row] -= 1
                    keep.append(False)
                else:
                    keep.append(True)
            if any(remaining.values()):
                raise UnresolvedOccurrenceOwnership(f"Part {part.label}: shared occurrences not removable")
            frame = frame.filter(pl.Series(keep, dtype=pl.Boolean))
        out.append(frame)
    result = pl.concat(out, how="vertical_relaxed")
    expected = Counter()
    for c in counts.values():
        expected.update(c)
    for u, owning in shared.items():
        for _ in owning[1:]:
            expected.subtract(proj[u])
    if Counter(result.iter_rows()) != +expected:
        raise AssertionError("inclusion-exclusion result mismatch")
    return result, removed


def merge_event_parts(parts: list[OwnedPart], shared_projections: dict[str, pl.DataFrame] | None = None,
                      columns: list[str] | None = None) -> tuple[pl.DataFrame, dict]:
    """Merge every collector of one event. Archive identities are scoped per collector: collectors publish archives
    with identical filenames (updates.YYYYMMDD.HHMM.gz), so ownership is only compared within one collector's parts.
    Shared projections (untagged mode) are keyed by full archive URL, which already names the collector."""
    columns = list(columns or ROW_COLS)
    groups: dict[str, list[OwnedPart]] = {}
    for part in parts:
        groups.setdefault(part.collector, []).append(part)
    frames, proofs = [], []
    for collector in sorted(groups):
        own = {a for p in groups[collector] for a in p.archives}
        shared_here = {u for u in own if sum(u in p.archives for p in groups[collector]) > 1}
        sp = None if shared_projections is None else {u: f for u, f in shared_projections.items() if u in shared_here}
        frame, proof = merge_collector_parts(groups[collector], sp, columns)
        frames.append(frame.select(columns))
        proofs.append(proof)
    rows = pl.concat(frames, how="vertical_relaxed") if frames else pl.DataFrame()
    return rows, {"collectors": proofs, "occurrence_policy": POLICY,
                  "restored_occurrences": rows.height, "parts": len(parts)}


# ---- on-disk parts written by the custodian extractor ---------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_owned_parts(parts_dir: Path) -> list[OwnedPart]:
    """Read every `<collector>__<day>.parquet` with its `<same>.ownership.json` receipt from one event directory.

    The receipt lists the complete archive set of the part with archive SHA-256 and the part file's own SHA-256,
    which is rechecked here. A parquet file without a receipt (or the reverse) is refused."""
    parts_dir = Path(parts_dir)
    files = sorted(parts_dir.glob("*.parquet"))
    receipts = sorted(parts_dir.glob("*.ownership.json"))
    if {f.name.removesuffix(".parquet") for f in files} != {r.name.removesuffix(".ownership.json") for r in receipts}:
        raise UnresolvedOccurrenceOwnership(f"{parts_dir}: parts and ownership receipts do not pair up")
    out = []
    for file in files:
        receipt = json.loads((parts_dir / (file.name.removesuffix(".parquet") + ".ownership.json")).read_text())
        if receipt.get("part_sha256") != sha256_file(file):
            raise UnresolvedOccurrenceOwnership(f"{file}: part bytes differ from its ownership receipt")
        frame = pl.read_parquet(file)
        if frame.height != receipt.get("rows"):
            raise UnresolvedOccurrenceOwnership(f"{file}: row count differs from its ownership receipt")
        archives = {a["filename"]: a["sha256"] for a in receipt["archives"]}
        if len(archives) != len(receipt["archives"]):
            raise UnresolvedOccurrenceOwnership(f"{file}: duplicate archive in ownership receipt")
        out.append(OwnedPart(label=file.name, collector=receipt["collector"], archives=frozenset(archives),
                             frame=frame, archive_sha256=archives))
    return out


def merge_event_source_aware(event_id: str, t0: dt.datetime, parts_dir: Path, out_dir: Path, *,
                             leak: tuple | None = None, prefix: str | None = None, new_origin: int | None = None,
                             expected_collectors: int = 10, tag: str = "leak") -> dict:
    """Source-aware replacement for merge_event on parts with ownership receipts. Nothing is written on refusal."""
    parts = load_owned_parts(parts_dir) if Path(parts_dir).exists() else []
    if not parts:
        out_dir.mkdir(parents=True, exist_ok=True)
        s = {"event_id": event_id, "error": "no parts", "collectors_with_parts": 0, "merge_occurrence_policy": POLICY}
        (out_dir / "summary.json").write_text(json.dumps(s))
        return s
    rows, proof = merge_event_parts(parts)
    structure = {
        "collectors_with_parts": len({p.collector for p in parts}),
        "collectors_missing_parts": sorted(set(PANEL) - {p.collector for p in parts}),
        "nonempty_part_collectors": len({p.collector for p in parts if p.frame.height}),
        "parts_files": len(parts), "collector_ownership_basis": "declared_archive_ownership_receipts",
        "merge_occurrence_policy": POLICY,
        "repeated_ingestion_occurrences_removed": sum(c["repeated_ingestion_occurrences_removed"]
                                                      for c in proof["collectors"]),
    }
    summary = measure_event(event_id, prefix, new_origin, t0, rows, out_dir, structure,
                            expected_collectors=expected_collectors, tag=tag, leak=leak)
    (out_dir / "merge_proof.json").write_text(json.dumps(proof, indent=1, default=str))
    return summary


# ---- explicit coverage gaps ----------------------------------------------------------------------------------------

def _ts(value) -> dt.datetime | None:
    if value is None:
        return None
    t = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value))
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def coverage_gaps(archives: list[dict], lo: dt.datetime, hi: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    """Uncovered sub-intervals of [lo, hi] for one collector. An archive covers its nominal interval widened to its
    actual content range when known (rotation shifts). Missing archives are simply absent from `archives`; the
    resulting hole is reported, never imputed as an empty part."""
    spans = []
    for a in archives:
        start, end = _ts(a["nominal_start_utc"]), _ts(a["nominal_end_utc"])
        cmin, cmax = _ts(a.get("content_ts_min")), _ts(a.get("content_ts_max"))
        spans.append((min(start, cmin) if cmin else start, max(end, cmax) if cmax else end))
    gaps, cursor = [], lo
    for start, end in sorted(spans):
        if end <= cursor:
            continue
        if start > cursor:
            gaps.append((cursor, min(start, hi)))
        cursor = max(cursor, end)
        if cursor >= hi:
            break
    if cursor < hi:
        gaps.append((cursor, hi))
    return [(s, e) for s, e in gaps if e > s]


def event_coverage(archives_by_collector: dict[str, list[dict]], collectors: list[str], context_start: dt.datetime,
                   onset: dt.datetime | None, fallback_end: dt.datetime, input_horizon_s: int = 60,
                   target_horizon_s: int = 7200) -> dict:
    """Per-collector gap ledger over [pre-onset context start, onset + 2 h] and the input window [.., onset + 60 s].

    `boundary_censored` is derived from onset + 2 h: a collector whose archive coverage ends before that instant is
    censored, never zero-filled. Without an observed onset, `fallback_end` (planned window end) bounds the ledger."""
    target_end = onset + dt.timedelta(seconds=target_horizon_s) if onset else fallback_end
    input_end = onset + dt.timedelta(seconds=input_horizon_s) if onset else None
    out = {}
    for c in collectors:
        archives = archives_by_collector.get(c, [])
        gaps = coverage_gaps(archives, context_start, target_end)
        last = max((max(_ts(a["nominal_end_utc"]), _ts(a.get("content_ts_max")) or _ts(a["nominal_end_utc"]))
                    for a in archives), default=None)
        input_gaps = coverage_gaps(archives, context_start, input_end) if input_end else None
        out[c] = {
            "gaps": [[s.isoformat(), e.isoformat()] for s, e in gaps],
            "input_window_complete": None if input_gaps is None else not input_gaps,
            "target_window_complete": not gaps,
            "boundary_censored": last is None or last < target_end,
        }
    return out
