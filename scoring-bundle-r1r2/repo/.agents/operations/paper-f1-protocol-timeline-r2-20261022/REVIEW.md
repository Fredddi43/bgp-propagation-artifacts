# F1 protocol timeline, revision r2 (delta for review a6173e46; LOCAL, design only)

Author: claude-opus-5-5, session <SESSION_ID>, 2026-10-22. New directory
`docs/paper/forecasting-improvement-20261017/figures/f1-protocol-timeline-r2/` (`f1_timeline.py`, SVG, PDF, README). The r1
directory and r1 packet (pins ee2f8a14) are preserved byte for byte; their pins still verify. `paper/` is untouched.
Dates, windows and protocol are unchanged from r1. Script delta: `diff-r1-r2-f1_timeline.py.diff`.

## Required findings

**F1, live lane overstated.**
- The lane is now "RIS-only refit (pilot model)".
- The last order box is now "capture window 14 d (+ up to 7 d) + 2 h; oracle-clock replays, no trigger". It rests on
  RECIPE L62, "... called oracle-clock replays, not live forecasts."
- Verbatim notes (5)-(7) quote:
  - methods §3.1, "The frozen rule therefore selected no trigger.";
  - methods §3.10, "The RIS Live capture is availability evidence only.";
  - RECIPE L62, "... the pilot is labelled an availability and timing study."
- The README caption says the same. Nothing implies that prospective or live forecasts happened.

**F2, apparent leakage.**
- Verbatim note (3), RECIPE L8: "So it runs only after every archival prediction has been committed and the single
  archival unblinding has happened."
- Verbatim note (4), RECIPE L42: "Training and calibration rows from September were already scored in the archival
  release. The refit is never evaluated on them."
- The caption explains the overlap in the same terms.

**F3, transfer arm conflated with the 2025 split.**
- The transfer arm has its own row, "Transfer arm (2023/24 to 2025)", with only train [2023-01-01, 2024-11-01) and
  cal. [2024-11-01, 2025-01-01).
- No transfer test window is drawn.
- The 2025 split has its own row.

**F4, the provenance claim.** It is restated exactly in the docstring and README:
- Bar and box texts are short labels, each resting on a stored quote.
- The numbered notes are drawn verbatim from `NOTES`: the drawn text is the stored quote, with only a topic before the
  quote marks and line breaks added.
- `check` verifies every stored quote (12 interval, 6 step and 7 note quotes; all present) and asserts the note
  bookkeeping.
- The r1 hard-coded paraphrase footnote is gone, and r1's undrawn RULES list is removed. Every stored quote is now
  either the basis of a drawn label or itself drawn.

## Optional items taken

- The footnote's maturity wording is now methods L168 verbatim (note 1: "... Events with immature labels at a boundary
  are removed."). The merged "2-hour embargo" paraphrase is gone.
- The two 15-day refit slivers have callouts: "cal. 16 Sep to 1 Oct" and "not used 1 to 16 Oct".
- The font is 6.5 pt (was 5.5) and the figure is 7.0 x 6.0 in.

## Validation

- `check`: all quotes present, rc 0 (`evidence/check.txt`).
- Two renders gave byte-identical files: SVG 8b29b4af, PDF 929b5e0a.
- Several rasterised previews were inspected visually, with these layout fixes: no overlapping callouts, no clipped
  note, legend clear of the bars. The previews are deleted.
- ruff: clean.
