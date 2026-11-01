# Origin construction v6 (author Sonnet; delta over v5 for sol-g1a; NOT authority)
Closes OCEP-V4-2 (locale differs by host) and the symlinked-interpreter finding. v4/v5 untouched; the v5 job.py PASS does not transfer (job.py sha, manifests and all 85 templates changed).

## Which step runs where, and which locale pin it checks
| Step | Runs on | Code | Pin (`manifest.locale_pins`) |
|---|---|---|---|
| meta_review, stage, preflight, science (prepare, gate, precision), install, capture, review_install | <BATCH_HOST> (coordinator), `/usr/bin/python3 -I -B` remote.py, science via the venv python | remote.py `preflight` (OR_12/OR_13) | `coordinator` = 353,616 B sha256 e4b5576b...2120 |
| Slurm array `build` and dependent `assemble` | cpu20-* compute nodes | job.py `verify_runtime` (OJ_13-18) before any write | `compute` = 367,708 B sha256 12575972...64b3 (all 4 nodes probed 2026-10-26 17:44Z agree; any other node that differs REFUSES OJ_13/14 before writing) |
Single-namespace manifests (meta, precision) run only on the coordinator and carry only `coordinator`. `common.LOCALE_PIN` is gone (two named pins); nothing else reads a locale pin.

## Why the host difference is harmless for the science (checked, not assumed)
LC_CTYPE only drives the C library's character classification/conversion (isalpha/toupper, multibyte tables) and the default text encoding. Grep of the full source closure (35 files: the 30 `src/bgbench` modules, family/reviewed_build/adapter, both budget helpers) plus science.py/remote.py/job.py finds NO use of `locale`, `strxfrm`, `strcoll`, `re.LOCALE`, `setlocale` or `getpreferredencoding` except the pin/setlocale checks themselves; Python 3 `str` methods, `re` and `json` use the Unicode database, not the locale file; event ids are ASCII hashed via explicit `.encode()` (UTF-8); numpy/torch/polars numeric code does not read LC_CTYPE. The pin exists to make the environment identity explicit and fail-closed, not because results depend on it; a different glibc table could in principle classify different non-ASCII code points, which no path here consumes. Residual: native libraries are not source-audited.

## Source delta (diff v5/v6)
common.py: two pins + comment. chain.py: manifests carry `locale_pins` (`coordinator`+`compute` for groups, `coordinator` for single manifests). remote.py: preflight uses `locale_pins['coordinator']`. job.py: calls `verify_runtime(m['locale_pins']['compute'])`; the interpreter check now dereferences the venv symlink: `real = realpath(python)`, lstat must be a regular file of 31,511,608 B (OJ_15) with sha256 62f0c11a... (OJ_16) (venv bin/python is a 63-byte 0777 symlink). test_packet.py follows the key. test_v6.py (9): v5's checks plus symlinked interpreter dereference, distinct pins in manifests, compute pin used by job main (wrong pin writes nothing).
Tests: 24+9+9+6 stdlib, 4 pytest, 9 v6: all green. Residuals of v4/v5 unchanged (<=65,536 B growth premise, no retry).
