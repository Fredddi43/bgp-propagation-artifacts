# Cold-prefix backup 52477689: terminal metadata capture (author Opus f4d75bb1)

The waiter reported task 0 COMPLETED 0:0 and tasks 1-9 FAILED 1:0. No receipt or log has been read yet. The cause is
not assumed. The 500 GiB models / 52 GiB results asserts run before `dest.mkdir()` (archive.py L81 and L83, before L85 mkdir), so a task
refused there would leave no dest and only its `.out` traceback (job.sh sends 2>&1 to the `.out` log). A later failure
would leave started.json, exit.json and possibly a temporary archive. The capture distinguishes these cases.

`capture.py` runs once: one read-only ssh to <BATCH_HOST> and one `sacct` on <SUBMIT_HOST>.
- Paths: only exact emitter paths (transport.py ROOT/logs, archive.py dest/TEMP/hf-cache names). No listing beyond
  per-dir entry counts.
- Reads:
  * four small receipts (<=16 KiB);
  * sha+size of manifest.json and source-manifest-private.json;
  * lstat of any temporary archive;
  * a bounded byte total for hf-cache-N;
  * each log's full sha+size, with only its first and last 32 KiB returned, `hf_...` token patterns redacted
    (count recorded);
  * the four staged-file shas against the transport pins;
  * statvfs free bytes (informational; root owns admission).
- Not read: no source parquet, no archive, no HF content.
- Output: exclusive local OUTPUT_DIR; failure evidence (rc/stdout/stderr) is kept.

Tests: `python3 -m pytest -q -p no:cacheprovider test_capture.py` -> 5 passed.
