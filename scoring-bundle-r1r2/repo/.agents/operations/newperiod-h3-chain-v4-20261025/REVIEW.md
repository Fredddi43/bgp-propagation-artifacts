# H3 chain v4 (review2 CHANGES_REQUIRED F1/F2 on v3 7697d793), immutable new directory

Author 4ba6111c. Reviewer review2 7f4c18c0. Local only; nothing executed. v1-v3 stay byte-frozen in
newperiod-h3-chain-20261025/ (review-ready, -v2, -v3). This directory starts from v3 chain_h3.py 9c5db616.

- F1:
  (a) await_terminal treats a failed or timed-out READ-ONLY poll (TimeoutExpired/OSError/rc != 0) as transient. It
      appends to <step>-wait/transient.jsonl and keeps polling until the existing deadline. The K5 squeue evidence
      poll is guarded the same way.
  (b) execute() catches BaseException and writes STOPPED.json {reason, exception_type, step, utc, jobs_left_as_is,
      assembled_released}, then the STOPPED event/notify (itself guarded), and returns None, so the CLI exits 3.
      self.step is tracked at every gate and wait.
- F2: one refusal test per mechanical stop that review2 found mutation-surviving:
  * earlier shard changed;
  * shard > 6 GiB;
  * file > 512 MiB;
  * census symlinks;
  * results-minimum df;
  * assembly singleton not COMPLETED 0:0;
  * authority chain_sha256 != running file.
  Plus timeout probes for a transient wait and a gate exception. 23 tests pass. Mutations M6-M14 are all caught
  (mutation-proof.txt).
- Template: models_minimum_bytes 710,817,087,488 and joint admission v26 bd1286d9 (ROOT-V26-ISSUED);
  notify.session = <AGENT_TOOL>-reported <SESSION_ID>; allowed_concurrent_jobs = ALL current d60 job ids (root fills).
- The wave-0 binding (review2 PASS): newperiod-h3-release-v26-20261025/initial-wave-binding-v1 (admission d9d32c17)
  with review2's release-review text 8b8c462b.
