"""RoVista lookups that never substitute a future measurement for missing history."""
from __future__ import annotations

from bisect import bisect_right


def ratio_at(series: dict, asn: int, day: str):
    samples = series.get(asn)
    if not samples:
        return None
    i = bisect_right(samples[0], day) - 1
    return samples[1][i] if i >= 0 else None
