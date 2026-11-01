"""Shared, prespecified interval-coverage arithmetic for every forecast family."""
import numpy as np

MAX_VERIFIED_COUNT = 131072
COVERAGE_CONVENTION = (
    'Closed log-count interval at common float32 precision for all forecast families; '
    'log1p(integer truth) and forecast log bounds rounded to float32; exactly one '
    'outward nextafter ULP per bound; fail closed outside integer counts0..131072. '
    'Count-space error and membership metrics unchanged.'
)


def covered_log_interval(counts, lower, upper):
    counts, lower, upper = map(np.asarray, (counts, lower, upper))
    if (counts.shape != lower.shape or counts.shape != upper.shape
            or not all(np.isfinite(v).all() for v in (counts, lower, upper))
            or (counts < 0).any() or (counts > MAX_VERIFIED_COUNT).any()
            or (counts != np.floor(counts)).any() or (lower > upper).any()):
        raise ValueError('Coverage requires ordered intervals and integer counts in verified range0..131072')
    lo, hi = lower.astype(np.float32), upper.astype(np.float32)
    truth = np.log1p(counts.astype(np.float64)).astype(np.float32)
    return ((truth >= np.nextafter(lo, np.float32(-np.inf)))
            & (truth <= np.nextafter(hi, np.float32(np.inf))))
