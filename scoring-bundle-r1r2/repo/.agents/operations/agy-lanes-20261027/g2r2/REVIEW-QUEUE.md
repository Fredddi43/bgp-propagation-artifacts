# g2r2 review queue (claude-sonnet-5-5 subagent; nothing here is a signed review)
1. chain/{g3_seal,make_arm_spec,r2_run,g4_labels}.py + g2/{stage_source,g2_exec,g2_submit}.py: authored, tested on synthetic fixtures (pytest 7 passed). Root should skim chain/r2_run.py (single attempt marker, go-file gate) and g2/g2_exec.py (approval derived from ROOT-GO-G2.txt; reviewer_model claude-sonnet-5-5, worker 'root-orchestrator-claude-sonnet-5-5'). No consumer needs a signed review for these; they bypass the transport/approval ceremony and keep every scientific check in the unchanged runners/evaluator.
2. Decisions for root: see DECISIONS-NEEDED.md.

3. h1-successor + REVIEW-h1-runner-successor.json (PENDING_ROOT): namespace-only successor so the 20 H1 arms can run; evidence in H1-RUNNER-SUCCESSOR.md. Flip: signoff.sh g2r2/REVIEW-h1-runner-successor.json.

4. chain/evidence/ (build_evidence, build_review, build_r2_evidence + test_evidence, 4 passed): label-free R2 evidence + drafted full_retention_review (PENDING_ROOT, session root-session). Root: decide DECISIONS item 8 (timing label map). Qwen cross-check not run (I have no subagent tool in this session); suggested audit: read-only diff of build_evidence.py against consumer.py prepare/prepare_sealed requirements.
