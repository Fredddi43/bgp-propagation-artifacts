# Protected timing cohort operator r2

Author astra-h3t; independent reviewer sol-h3t. Corrects PT1-R1..R5 in a fresh sibling directory; original runner r1, kernel, source package and final plan bytes unchanged. No remote operations.

R1: shared board mandatory in authority scan dirs; ROOT/REVIEWER/OPUS-REVIEWER/OWNER posts are read at every gate. Existing handled-post mechanism remains; acknowledge routing-only ROOT-STOP-POST-ROUTING before run, not genuine STOP instructions.

R2: stages and release now check both issued joint minima. An additional gate immediately precedes sbatch. Each gate lstat-checks exact canonical <USER>-owned custody log, size strictly below2GiB, and stable dev/inode across the run; contents never read. Metadata result is recorded. Root authority must bind an issued joint document with models_minimum_bytes equal the transport minimum and results_minimum_bytes at least45231374336.

R3: singleton sacct row must contain exactly5 columns, exact submitted job id and numeric exit-code shape. Capture validates supervisor intent plan/approval/operation/job id, worker intent and done plan/approval/operation. Successful receipts require both intents, a plain bounded eligibility-audit output and exact output byte reconciliation; failed records cannot become success. No eligibility-audit contents read.

R4: held MinMemoryNode must exactly equal requested65536MiB, accepting Slurm K/M/G/T or bare MiB spelling.

R5: TimeoutExpired/OSError during read-only polling become recorded transients, preserve original deadline and60-failure cap; no repeated submission/release. Other stage/gate/release exceptions stop.

29 tests pass, including new foreign-job, forged receipt, late results-low/log-ceiling, wrong-memory, REVIEWER-STOP and transient-exception regressions. Tests use simulated cluster only.

Final plan145dd8c4 and resource admission49755fdb remain in newperiod-timing-cohort-astra-final-binding-20261025. The staging byte/throughput basis remains explicitly UNKNOWN. Independent operation approval and root once authority are still required; build transport only from approved final files.
