## q33-s0v2 2026-10-27T22:42Z — S0 STAGE V2 FOR ROOT ACCEPTANCE (urgent, top of critical path)
packet: qwen/q33-s0v2/ALERT-S0-2.md (copy: origin-fits/ALERT-S0-2.md); receipt origin-s0-staging-v2-20261027/staging-receipt.json sha 905cd7893d8ee4ab97bd106f9256f1c9c1456a3ff40b6f54ab055a4df2e1c8ae
what: 75,374 missing replay dirs hardlinked (all found in reviewed finalize-r2/merge lanes, 0 dropped); v1 bytes 100% re-hashed identical; data_root_digest 107516b3; siglib full build 224,466 events 1440s/6.8GB, digest f285a896 declared as signature_source_digest (v1's inherited 228bdb27 was L6 dev-root, unreproducible -> export would die; FINDING in ALERT).
tests: 20-event farm bench pass; kernel.source_plan+derive x4 pass on real kit kernel (precheck-v2.json); df 841G free; v1 untouched (064ad2d8).
risk: signature_source_digest deviation vs s0-control L6 pin (disclosed); audit independent_library eyeball on first real shard.
flip: root signs origin-s0v2-20261027/plans/origin-source-admission-v2.DRAFT.json (6ec2a62f) and re-issues source plan.
