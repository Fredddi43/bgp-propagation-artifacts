# Recovery r3a: predicate-only amendment of reviewed r3 (CODE PASS 3e7c77d2) to root phase v3 456 GiB

Root coordination 08:08Z (root-resource456-coordination.json): the joint phase is now v3 6716fbf8. Its models minimum is
489,626,271,744 B (450 GiB base + 6 GiB master-pair controls; archive_metadata 1 GiB still reserved). r3 must not run.

Exact delta vs recovery-r3 (pinned by test_r3a_delta_is_predicate_only):
- archive.py L81: 483,183,820,800 -> 489,626,271,744 (message names phase v3 6716fbf8).
- transport.py STAGE: the same models predicate.
- job.sh: unchanged. The namespaces stay r3 (storage-prefix25-archive-r3 / temp-r3). r3 was never staged; the stage
  code still requires both roots absent, so it fails closed if anything was touched.
- request.json: new file pins, minimum_start_free_bytes, root_phase ref, and the unexecuted r3 request recorded as
  superseded.
Everything else is byte-identical to r3: tasks 1-9 only, task 0 refused, results 52 GiB, member hashing, no overwrite,
full remote download verification, sources preserved, public BGP derivatives only to the existing HF repo.

Fresh root observation 08:08Z: models 534,028,222,464 B (>= 489,626,271,744), results 56,270,782,464 B
(>= 55,834,574,848; about 0.4 GB margin).
Tests: 23 passed (r3 22 plus the delta pin).
