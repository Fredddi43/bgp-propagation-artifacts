# Review packet: D2 host run, revision 2 (delta vs d2-host d52098ac, addressing reviewer checklist §5)

- Author: claude-opus-5-5, session <SESSION_ID>.
- `../d2-host/` (pins d52098ac) is superseded before any review; its bytes are unchanged. Everything in its REVIEW.md
  still holds except the three items below.
- The full diff is in `d2.py`, `test_d2.py` and `mutation_controls.py` relative to `../d2-host/`.
- Nothing has run. Only synthetic fixtures were used.

## Delta, per `critical-path-assessment.txt` §5

**1. Memory adds the parsed-prediction term from the code.**
- `load_partition` holds a whole horizon's decoded events.
- `rescore_cell` does `json.loads` on one cell's predictions plus its per-event rows at a time.
- So per horizon: `mem` = 2 × (D1-census tensor bytes) + 10 × (largest prediction file of that horizon's cells + K1
  `per_event.max_file_bytes`) + 4 GiB.
- The array takes the maximum. Above 480 GiB it refuses and resources are re-proposed.
- The K1 per-event census must be clean (`non_file_entries == []`).

**2. The cells file is sha-checked in the job.**
- Each task's `CELLS_SHA` (the sha of its embedded list) is in the script.
- After writing the list it runs `sha256sum --strict --check`, before `test ! -e $OUT` and the interpreter.

**3. Wall time is derived from D1.**
- hours = ceil(1.5 × tensor bytes / 66 MB/s / 3600) + 1, with a minimum of 2.
- 66 MB/s is the measured floor: the final eval's verify read 895 GB in 3.75 h.
- With the memory ceiling, this stays ≤ 3 h.

Unchanged:
- 2-task per-horizon array, 1 CPU, partition cpu, no nodelist, `--no-requeue`, no `--export`;
- inputs only from recorded captures;
- fixed 66-cell membership;
- exact approval gate, one submit, read-only queue-check;
- fetch only when both tasks are `COMPLETED|0:0`.
- An output over 16 MiB is refused by f19 and needs a separately reviewed read.

## Tests: 47 passed; ruff clean

New relative to d2-host:
- the exact r2 arithmetic: 19 / 29 GiB; the K1 per-event term counts (38 GiB at 2 GiB per-event); 2 h / 3 h from
  100 / 200 GB stored;
- the ceiling still refuses;
- a job whose embedded `CELLS_SHA` disagrees stops before the interpreter.

## `mutation_controls.py`: 17/17 detected

These are the 14 d2-host controls plus three new ones:

| New mutation | Targeted tests |
|---|---|
| parsed-prediction term dropped | 1 failed |
| time not from the census | 1 failed |
| cells sha check dropped | 1 failed |
