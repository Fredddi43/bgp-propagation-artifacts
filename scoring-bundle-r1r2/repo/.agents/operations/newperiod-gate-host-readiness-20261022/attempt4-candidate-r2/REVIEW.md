# Gate host attempt-4 candidate, revision r2 (LOCAL; nothing staged, placed or run)

## r2 delta: review F1 only (`diff-r1-r2.diff`; review `attempt4-and-gate-v5-review.txt` 4eb60ef3, section C)

**The defect.** In r1, `test_host.py` (the host-version rehearsal test, lines 792-795) wrote
`evidence-local/rehearsal-hostver.json` into the frozen packet. The reviewer's independent run overwrote the pinned
file, 74f584f0 -> 504b05b6, so r1's pins 5df00674 now fail on exactly that one file.
- **r1 is preserved as it is now:** overwritten file included, not restored, not re-pinned.
- **The original 74f584f0 bytes are not recoverable.** The packet was untracked, and the rehearsal's temporary
  directories have rotated away.
- **What survives:** the reviewer kept the overwriting bytes
  (`review/v8-actual-captures-b8-u2-review/attempt4-rehearsal-hostver-OVERWRITTEN-BY-REVIEWER-RUN.json`). Their
  content facts match what r1 reported.
- **What this packet does not claim:** that r1's pins verify.

**The change, in `test_host.py` only, plus one mutation case:**
1. The rehearsal record goes to `tmp_path`. Evidence for a new freeze is written only on an explicit opt-in:
   - `A4_REHEARSAL_OUT=<absolute path>`;
   - the path must lie outside the packet and must not exist yet (opened `'x'`).

   The author copies that file in before pinning.
2. **The guard.** A session-scoped autouse fixture `packet_bytes_unchanged` takes the sha256 of every packet file
   (bytecode caches excluded) before the run and again after it. It fails the run if any file was added, removed or
   changed.
3. **The proof.** `mutation_controls.py` gains `A4r2 rehearsal record written into the packet again (the F1 defect)`,
   which re-introduces a packet write in the rehearsal test. It must be detected.

**Other changes:**
- `mutation_controls.py` uses its own temporary directory name (`gate-host-attempt4-r2-mutation-tmp`).
- stage.py, place.py, host_run.py and preflight_probe_v4.sh are byte-identical to r1.

**Evidence:**
- `evidence-local/pytest.txt` and `evidence-local/rehearsal-hostver.json` are new for r2.
  - **83 passed** (11 min).
  - It was run with `A4_REHEARSAL_OUT` pointing at `/tmp`, and the file was copied in afterwards.
  - `packet-before.sha` and `packet-after.sha` hash the packet before and after that run, taken outside pytest, and
    are identical. The tool and test files they list are the frozen ones. Only REVIEW.md and evidence-local/ were
    filled in after the run.
  - The rehearsal again gives `168 passed, 1 deselected`, with the same diagnostics facts as r1:
    - 81 traces, 1 parse failure and 11 verify refusals;
    - outside names `/etc` and `/x`;
    - absent_readers `[polars.scan_external_reader, polars.scan_reader_not_in_this_version]`.
  - `pytest-first-run-guard-tripped.txt` is kept for transparency. In an earlier r2 run all 83 tests passed, and then
    the guard failed the session. The cause was me: I added REVIEW.md, the diffs and the carried evidence to the
    packet while that run was going. So that failure is a true positive, and that run is not used as evidence.
- Carried byte-identical from r1, with the code they describe unchanged: `mutations.txt` (the 46 r1 cases),
  `preflight-sanity.txt`, `stage-manifest-now.json`, `rehearsal-diagnostics-breakdown.json`.
- `evidence-local/mutation-f1.txt`: the new F1 mutation, run on a sibling copy that was deleted afterwards. It is **detected**:
  `1 passed, 82 deselected, 1 error`, with exactly `tests changed the frozen packet: ['rehearsal-hostver.json']`.

**Reviewer conditions C1-C4 for any future approval** (shared-venv quiescence, the pinned readers/absent_readers/
summary pass criteria, the S1 manifest sha, R1 first) are recorded in that review and not changed here.

**Non-blocking items not taken up here:**
- a read-only `/dev/shm/gate-v2-*` listing in the preflight;
- a host-legal second-device variant of the deselected test.

Both are left for a later revision, to keep this delta to F1.

---

# Revision r1 text (unchanged below, except that test and evidence lines describe r1)

Author: claude-opus-5-5, session <SESSION_ID>. This is a code candidate only. It claims no approval, and it may not be
staged, placed or run while the R1 v8 custody is live. The tools enforce that too.

**Preserved untouched:**
- the attempt-3 flow `revision-v3-round2/` (tools 5e7f0263/dd356c70/4b74d853), its evidence and its host root
  `newperiod-gate-host-v3`;
- the v1 probe scratch leftover;
- the shared venv;
- gate revision-v3, revision-v4 (CODEPASS 0c5f9c60, committed c31dcc9) and revision-v5.

## Base and deltas (`diff-v3r2-a4.diff`)

The tools are copies of `revision-v3-round2` (the reviewed attempt-3 flow, approval 9af22ba6 plus addendum e436f428),
with these changes only:

**1. The gate: revision-v5** (`stage.PACKAGE`, `GATE_PINS_SHA256`).
- v5 is v4 (absent listed readers recorded, `/etc/locale.alias`) with v4's two environment-dependent tests corrected.
- Under the host's library versions, v4 fails exactly those 2 tests (`../../newperiod-input-gate-20261021/revision-v5/REVIEW.md`).
- `TEST` is derived from `PACKAGE`.

**2. The R1 v8 custody** (`stage.V8_EXIT`, `stage.V8_EVAL_EXIT`, `v8_terminal`, `v8_eval_terminal`).
- These are the v8 `control-v1` and `evaluation-control-v1` `execution-exit.json`.
- They use the same strict `terminal_record` as v7: a regular file of at most 4 KiB, not a symlink, with an integer
  returncode.
- `place.py` and `host_run.py` require both records, next to the two v7 records, before anything else. So no hard
  link is made and no run happens before the whole v8 chain (preparation, then evaluation) is terminal. The v8 launch
  receipt says the same: "host placement/shared-venv change until the v8 chain is terminal".

**3. Diagnostics kept before cleanup** (`host_run.diagnostics`, the attempt-3 lesson).
- **The attempt-3 problem:** attempt 3 removed `run/basetemp` after the run. The witness traces that named the
  failure were deleted, and two diagnosis rounds and four probe revisions followed.
- **What is written now:** after pytest, after `run_bytes` is measured and before the worlds are removed,
  `run/diagnostics.json` is written. It holds:
  - **per witness trace** under basetemp (at most 512):
    - size and sha256;
    - the gate's own `parse` result, as its fixed message;
    - the opens outside the reference roots (repo src/scripts/package, `sys.prefix`, `sys.base_prefix`), the
      gate's own `system_path` and `run/`. These are names only: at most 16 per trace and 300 characters each;
    - the gate's own `verify` result against that witness's recorded scope, when its untraced witness exists;
  - **the union** of outside names (at most 256), each with its count and the first trace's test directory, plus
    the union of `absent_readers` from the witnesses. The test directory separates the gate's deliberate negative
    tests (forged traces, `os.listdir('/etc')`, `/x`) from an unexpected host-only path;
  - **READERS:** one child from the placement venv, under the run's limits and environment, with cwd `run/tmp`.
    It is the reader part of the reviewed probe r4 child A and computes the same things: library versions, listed
    names missing from the installed libraries, aliases outside the reader libraries, and `install_readers`'
    result.
- **Kept traces:** up to 2 traces the gate cannot parse (each at most 64 MiB) are moved to `run/kept-traces/`.
  Their shas are recorded. A trace is kept only when a witness wrote its `witness-untraced.json` beside it. Traces the
  gate's tests forge on purpose have none, so they cannot use up the two slots. The first rehearsal showed this
  happening: a 929 KB forged trace filled a slot.
- **Failure handling:** an exception inside diagnostics is recorded, and the cleanup and `result.json` still happen.
  Diagnostics never change `passed`.
- **`result.json`** binds the diagnostics: path, sha256, bytes, counts, the kept-trace shas, any error, and the
  witnesses' `absent_readers`. That last item answers the gate-v4 review's non-blocking note that the host-attempt
  record should surface them. It also records `retained_bytes`, measured after cleanup.
- **What it names, and what not:** the tests run no N data, so a trace holds only synthetic-world paths, reference
  and system paths, and whatever host-only path caused a refusal. The diagnostics name paths, never contents. They do
  not loosen the witness, the allowlist or the verdict: they re-run the gate's own parse and verify, read only.

**4. One gate test is deselected on the host** (`HOST_DESELECTED`, recorded in `result.json` as `deselected`).
- **The finding (new, not known before):** `test_fsid_zero_with_data_on_another_device_refuses` builds its synthetic
  world with `tempfile.mkdtemp(dir='/dev/shm')`, because it needs a second local filesystem. Its `finally` removes it.
  - **Attempt 3 ran it on <BATCH_HOST>.** The attempt-3 host log has it FAILED, with tmp_path under the v3 root.
    So that run made a transient, synthetic write to `/dev/shm` on the login host. That is outside the placement root
    `host_run`'s docstring promises, and outside the Slurm skill's `<CLUSTER_STORAGE>` write rule for that host. No review, mine
    included, caught it.
  - Whether its `finally` ran on the host is not observed. The test failed inside the `try`, so the `finally` should
    have run.
- **What I checked:** I grepped the gate package for other write locations (`tempfile`, `mkdtemp`, absolute paths).
  This is the only one. The other `/tmp/...` strings are JSON fields that the tests expect to be refused, not writes.
- **The decision, which is the reviewer's and root's to make:**
  - **(a) Deselect it on the host (my pick, implemented).** G3 stays tested locally, the gate bytes stay unchanged,
    and the host pass criterion becomes `168 passed, 1 deselected`.
  - **(b) Keep it, under an explicit approval** of a transient `/dev/shm/gate-v2-*` write on the login host.

**5. `preflight_probe_v4.sh`.** The attempt-3 probe, changed as follows:
- the fresh v4 paths;
- all three terminal records (v7 evaluation, v8 preparation, v8 evaluation), with their content recorded;
- the v8 preparation pids 469425/469426 gone;
- no process with an exact v8 `control-v1`/`evaluation-control-v1` `execute.py`/`supervise.py`/`run.sh` argv
  element. The scan was checked locally (`evidence-local/preflight-sanity.txt`): it finds a planted exact-path
  process and ignores a `.bak` lookalike.

Nothing else changed: the hook admission (69ac3d8f/cfb3db86), O_NOFOLLOW, the limits, the data-like listing, the
strace binding, the editable `.pth` check, one attempt per placement, and the smoke selector.

## Compatibility with the host (existing evidence, no host read)

- **Modules:** probe r4 (4ef29caf) recorded the sha256 of every repo module the host loaded. All 11 non-gate modules
  are byte-identical to today's repo:
  - `scripts`: custodian_access_log, custodian_newperiod_inputs;
  - `src/bgbench`: `__init__`, config, forecast_history, forecast_inputs, forecast_manifest, forecast_protocol,
    forecast_train (ebf066a2), gnn_train, graph_metrics.

  `boundary.py` is identical too. Only `audit_witness.py` and `syscall_trace.py` differ, as v4/v5 intend.
- **Library versions:** a local venv holding the host's versions (python 3.12.8, polars 1.44.1, pyarrow 25.0.1,
  numpy 2.5.2, pandas 3.0.5, torch 2.14.0, CPU build where the host has cu130):
  - **gate v3:** 96 failing. All of them failed on the host as well. The 14 host-only failures are exactly the
    no-denylist tests that stop at `trace` on the host (F2, a host-only open).
  - **gate v4:** 166 passed, 2 failed (the v5 finding).
  - **gate v5:** 169 passed.
  - **This whole candidate run end to end** (stage, place from that venv, `host_run --full`): **passed: `168 passed, 1 deselected`**, run_bytes 80.7 MB, retained 43.9 KB
    (`evidence-local/rehearsal-hostver.json`). The diagnostics found:
    - 81 traces, and READERS reported `missing ['polars.scan_external_reader']` with `install_readers` ok;
    - one parse failure: the gate's deliberately forged trace, not kept;
    - 11 verify refusals, all from the gate's negative tests: 9 `test_round2_probe_readers_without_any_denylist_*`
      ("Unrecorded data open") and 2 `test_data_copied_or_linked_outside_the_roots_*` ("Open outside").
      Per test directory: `evidence-local/rehearsal-diagnostics-breakdown.json`;
    - two outside names, both from negative tests: `/etc` (`test_native_bypasses_fd_opens_*`) and `/x`
      (`test_gate_refuses_a_witness_wh*`).

    This is the baseline: on the host, any other outside name is host-only.
    - One rehearsal-only patch was needed. uv's standalone CPython 3.12.8 holds an fd on
      `/sys/kernel/mm/transparent_hugepage/enabled` open from start-up, so the inherited-fd check would refuse it.
      The test relaxes exactly that fd target in its tool copy. The host's miniforge 3.12.8 passed the unpatched check
      in attempt 3 (S5 ran).
- **Not covered by any local run:**
  - **strace:** the host's strace is 6.1 (aebaf212), the development host's 6.19. Probe r4 parsed a host 6.1 trace of
    start-up without error; audit-stage traces are untested.
  - **System files:** the host's system files and kernel differ. Locally `/etc/locale.alias` does not exist.
  - **Audit-time opens:** host-only opens during the audit stages are unknown. If there are any, attempt 4 fails at
    `trace`, and diagnostics.json names them.

## Tests and controls

- **`test_host.py`: 83 passed** (`evidence-local/pytest.txt`, 11 min). That is the 62 of revision-v3-round2,
  adapted, plus 21 new tests:
  - **v8 records:** strict-record matrix ×2 (8 tests), control-root paths, placement refuses while either is live
    (×2), `host_run` refuses before writing for `v8-live` and `v8-eval-live`;
  - **diagnostics, unit level** (on fixed strace lines):
    - outside opens named, with the first test directory;
    - system paths not reported;
    - the gate's own verify message reproduced;
    - an unparsable witness trace moved and kept, a forged trace not kept;
    - every cap and the clipping exercised;
    - the size bound holds by construction;
  - **diagnostics, end to end:**
    - a failing smoke run where `TZ=/etc/hostname` makes every witness child open a host file at start-up. The
      witness stops at `trace`, `diagnostics.json` names exactly `/etc/hostname`, and the cleanup and result still
      happen;
    - an exception inside diagnostics is recorded, while the cleanup, the result and `passed` are unaffected;
    - the passing smoke run has an empty outside union and `absent_readers` `[]`;
  - **host versions:** the READERS child names attempt 3's reader failure on gate v3 and `install_readers` ok on v5;
    the full rehearsal described above.
- **`mutation_controls.py`: 46/46 detected** (`evidence-local/mutations.txt`). That is the 28 attempt-3 cases (one
  anchor re-pointed for the v8 lines) plus 18 new ones: 4 for v8, 13 for diagnostics, 1 for the deselection.
  - The mutations ran before one later line was added: the `absent_readers` entry in `result.json`'s diagnostics
    summary, now covered by two assertions in the full suite above. No mutation anchor touches that line, and the
    mutations were not re-run.
- `preflight_probe_v4.sh`: `bash -n` clean, and the local argv-scan sanity check (`evidence-local/preflight-sanity.txt`).
- ruff: clean.

## Unresolved conditional values (filled only at execution, each bound by the exact approval)

| Value | Status |
|---|---|
| gate pins | revision-v5 pins ff4a9535 (frozen locally). v4 is CODEPASS (0c5f9c60); the v5 test-only delta is not yet reviewed. A requested change means a new revision and a new candidate. |
| tool shas | the frozen candidate bytes (`pins.json`) |
| stage-manifest sha | computed from the repo at S1; `evidence-local/stage-manifest-now.json` gives today's value, **d3e3c20a** (110 files). Compared with attempt 3's 3e01aed8 (105 files), only gate-package entries differ; `src/`, `scripts/` and the extras are identical. It must equal the approved value (P2): any repo source change before S1 needs a new approval. |
| placement sha | known only after S4. It depends on the shared venv's file count, the python link target and the hook's presence. |
| shared venv / hook | assumed unchanged since attempt 3 (hook 69ac3d8f/cfb3db86, `.pth` set). Not read now; PF and `place.py` check it at execution. |
| strace | aebaf212 (probe r4 tracer identity) |
| v8 terminal records | preparation terminal, returncode 0 (exit record written 2026-10-22T15:52:58Z; captures A/B/F1 done, d440641). The evaluation is not launched and its record does not exist, so the tools refuse. |
| v8 evaluation supervisor pid | unknown. PF uses the exact-argv marker scan for the evaluation, and the pids only for the preparation. |
| host-only audit-time opens | unknown (see above) |

## Proposed next-phase ordering (each step needs its own exact approval and root routing; none is requested here)

1. **Local review only.** The probe-r4 outcome and gate v4 are reviewed (0c5f9c60). Still to review: the v5 test
   delta, the `/dev/shm` finding with its deselection decision, then this candidate. No host action.
2. **R1 first.** Done: the v8 preparation is terminal (rc 0) and captures A/B/F1 ran under 079ab5aa. Still to come,
   on the R1 critical path: the reviews of the captured evidence (B8, the resolved diff, U2/U3), the remaining
   post-preparation steps, the v8 evaluation launch and the evaluation. Nothing here may delay them.
3. **Attempt 4 only after the v8 evaluation is terminal,** with any integer returncode. Both v8 records must exist,
   the markers must be gone, and the R1 post-evaluation steps keep priority. It needs a new exact approval binding:
   - tools, gate pins, the S1 stage-manifest sha, strace, paths, limits, the preflight sha;
   - the capture scope below.

   Then: E0 → PF → S0-S6, once, no retry, no cleanup.
4. **Outcome to independent review.** A pass proves host readiness only. The real N gate needs its own approval,
   including the reference data-like listing judgement.

**Proposed S6 capture scope (read-only, O_NOFOLLOW regular files, sha-bound):**
- placement.json, stage-manifest.json;
- run/result.json, run/limits-observed.json, run/reference-data-like.json;
- **run/diagnostics.json** in full (at most 16 MiB by construction);
- **run/pytest.log in full**, at most 64 MiB, and its sha must equal `result.log_sha256`. Attempt 3's capture kept
  only the last 200 lines, which lost the witness's stderr.
- run/kept-traces/*: at most 2 files, each at most 64 MiB, sha equal to diagnostics `kept`.
- S4/S5 stdout, stderr and exit codes.

**Proposed pass criteria (attempt 3's, adapted):**
- `result.json`:
  - `passed` true, `returncode` 0, `full_suite` true;
  - summary `168 passed, 1 deselected`, and `deselected` equal to `HOST_DESELECTED`;
  - `limits_observed.ok` true, `run_bytes_within_bound` true;
  - the strace and placement shas as approved;
  - `diagnostics.error` null.
- `placement.json`: `runtime_hook` equal to the reviewed hook.

A pass proves host readiness only. On a failure, `diagnostics.json`, the full log and any kept traces are the
evidence. A fix still goes through a new revision and a new approval; there is no retry.
