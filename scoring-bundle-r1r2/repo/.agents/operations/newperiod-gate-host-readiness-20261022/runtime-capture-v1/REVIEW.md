# Review packet: read-only capture of the shared venv's virtualenv runtime hook (LOCAL; nothing run remotely)

- Author: claude-opus-5-5, session <SESSION_ID> (`/root/opus_implementation`).
- Trigger: host attempt 2 (approval-v2 247a4121, addendum-1 5b7a6eff) is terminal at S4. `place.py:44` refused
  `['_editable_impl_bgbench.pth', '_virtualenv.pth', 'distutils-precedence.pth']`; result d2e45ef2. Reviewer
  assessment ada45289 requires the bytes and sha of `_virtualenv.pth` and of the module it imports before any
  revision may admit it, and only by exact hash.
- Nothing ran on the host. The live R1 final evaluation (supervisor 317830) is not touched.

## What `capture_runtime.py` (64c1ce39) reads

| Fixed | Value | Grounded in |
|---|---|---|
| directory | `<RESULTS_ROOT>/work/<PROJECT>/venv/lib/python3.12/site-packages` | base host probe: venv python 3.12.8; addendum-1 preflight read `$V/lib/python3.12/site-packages/{pytest,…}` (present) |
| names | `_virtualenv.pth`, `_virtualenv.py` | the S4 refusal names the `.pth`; virtualenv's `.pth` conventionally imports its sibling `_virtualenv` module. The actual import line is read from the captured bytes, not assumed. |
| interpreter | `<RESULTS_ROOT>/work/vllm/miniforge/bin/python3.12 -I -S -B` (sha 62f0c11a) | the venv's own python would run `site`, which processes `_virtualenv.pth` and imports `_virtualenv`, so it would execute the code being captured |

**Not reused:** `r1-prerequisite-evidence-20261021/capture_metadata.py` (f19d1066). It is JSON-only under B, and these
are a `.pth` and a `.py` on the results mount, so it would have to be widened. Instead this file reuses its pattern
(the stdin payload into a REMOTE program, then a local exclusive record) with two fixed names.

## Guards (each refuses with no output)

**Remote side:**
- `<USER>` on <BATCH_HOST>, no Slurm.
- `-I` and `-S` both active, and `site` not imported.
- The names must be exactly the two above.
- The directory is absolute, canonical (`resolve() == itself`), a directory and not a symlink.

**Per file:**
- `lstat` must give a regular file of at most 64 KiB, so a symlink, directory or FIFO refuses.
- It is opened with `O_NOFOLLOW` and read to at most 64 KiB + 1.
- (dev, inode, size, mtime_ns) must be equal across `lstat` before, `fstat` before, `fstat` after and `lstat`
  after, so a file moved or changed during the read refuses.
- The bytes read must equal the size.
- A missing file is recorded `{"absent": true}`. Nothing is searched, listed or walked.

**Local side:**
- It needs an independent exact approval: scope `newperiod-gate-host-runtime-capture-v1`, `tool_sha256`, `site`,
  `names`, the base `python`, `attempt_limit` 1, no retry, and host write, placement and run all false.
- One attempt: `evidence/runtime-capture.json` must not exist, and it is written exclusively. The intent record is
  written before the ssh and the result record after it.
- The bytes are kept as base64 data and never imported.

**No host write.** No N, protected, label or results path.

## Tests

| Suite | Result |
|---|---|
| `test_capture.py` | 23 passed |
| `ruff check` | pass |

The tests:
- **REMOTE program:** runs locally, with only the user and host literals patched, on synthetic site dirs whose
  `.pth` and module write a marker if they are ever processed or imported.
  - It captures exact bytes and sha. No marker appears, and nothing is written beside the files (no
    `__pycache__`).
  - A missing module is recorded absent; a decoy file next to it is ignored.
  - Refusals: a symlinked file, a symlinked parent, an oversize file, a directory, a FIFO, a relative site, a run
    with `site` enabled (`-I` without `-S`), and other names.
- **Approval:** a positive case and 10 refusals: author session or worker, tool sha, site, names, venv python,
  2 attempts, retry, placement, scope.
- **Local side:** no ssh without an independent approval, and none when the output already exists.

**Not tested:** a real race between the reads. The four identity comparisons exist, but no deterministic test can
interleave a rename.

**`mutation_controls.py`:** all 8 guard removals are detected. The symlink and size guards are layered, so both of
those mutations remove every layer.

| Mutation | Targeted tests |
|---|---|
| site processing allowed | 1 failed |
| symlinked file followed (both layers) | 1 failed |
| symlinked parent accepted | 1 failed |
| size cap removed (both layers) | 1 failed |
| other names accepted | 1 failed |
| approval independence removed | 2 failed, 1 passed |
| venv interpreter accepted | 1 failed |
| second capture allowed | 1 failed |

## Requested approval (fields `checked_approval` requires)

The command, once, from this directory:

```
<REPO>/.venv/bin/python -I -B capture_runtime.py capture --approval <A> --approval-sha256 <sha>
```

Approval fields:
- `scope`, `passed` true, `capture_authorized` true
- `tool_sha256` 64c1ce39…, `site`, `names` `["_virtualenv.pth", "_virtualenv.py"]`, `python` (the base interpreter)
- `attempt_limit` 1, `automatic_retry_authorized` false
- `host_write_authorized`, `placement_authorized` and `run_authorized` false
- an independent reviewer identity

The capture reads two small files on the results mount and nothing of R1, so it does not touch the live R1
evaluation.

## After the capture (separate steps, each needing its own review)

1. Inspect the captured bytes locally as text: no import and no execution. Judge their `sys.path` and import-hook
   effect.
2. A host revision-v3 that admits only the exact reviewed sha(s), never a wildcard, with refusal tests and mutation
   controls.
3. A fresh ROOT and tools dir. The current ones keep the attempt-2 state and are preserved.
4. A new exact approval, issued only after the R1 final evaluation has a terminal proof.
