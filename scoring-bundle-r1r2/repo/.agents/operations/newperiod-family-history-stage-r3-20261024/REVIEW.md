# History stage r3: the original onset fallback missing from r2 (job 52473649 FAILED 1:0, 00:21:19)

Evidence: root failure capture under approval 74a83aa3, execution-v1 stdout c60c6817 (sanitized frames, no values).
- A ValueError was raised in original_stage.utc (line 51), called from history_stage.plan_links line 65: the
  query-summary onset equality check.
- That check runs after table parsing and role hashing, which matches the 21 min runtime.
- Line 65 parsed `summary['first_observation']` unconditionally.
- The original eventset (src/bgbench/eventset.py:72, ADR-0018) defines
  `t0_obs = first_observation if s.get('first_observation') else s['t0']`.
- A falsy first_observation (null or "") therefore makes eventset use the identifier t0. r2 then fed null/"" to
  fromisoformat, which raises ValueError: the actual symptom.
- An absent key would raise a KeyError instead; a truthy non-ISO string would already have broken eventset. Both are
  ruled out by the actual capture and the existing tables.

Fix (`build_r3.py` from the r2 CODEPASS bytes 13298dcf):
- `summary_onset(s)` mirrors eventset.py:72 exactly.
- The check compares `utc(summary_onset(summary))` to the table onset, so equality is still required.
- No other kernel line changes.
- The execution files are r2's with the namespace newperiod-origin-history-v2 -> v3. v2 keeps the failed r2 state
  untouched.
- package-v1 is rebuilt by the reviewed execution/build.py: 102 files, manifest 0d09f2e1. Against r2 it differs only
  in run.py (the v3 ROOT) and history_stage.py.

Tests: 22 pass with /tmp/np-hostver-venv (Polars 1.44.1), PYTHONPATH=src. Inherited: test_history and
execution/test_execution. New, in test_onset_fallback:
- null and "" first_observation reproduce r2's ValueError, and r3 passes;
- an absent key also uses the fallback;
- a fallback t0 that differs from the table onset still refuses ("onset differs");
- a summary with neither onset refuses;
- the exact kernel delta from r2.

test_clock_compat.py was not carried over: its third test pins the r1 -> r2 delta. The string/datetime parser is
unchanged from r2.

Not authorized: anything on the host. A launch needs the same L1-L6 chain as r2 for v3: plan, resource admission on
a fresh df, stage/held approval, release approval, run once.
