# D300 operator v2 — source successor for sol-storage2

Addresses `D300-V1-BINDING-SIZE` and `D300-V1-SSH-WRITER-CLOSURE`. Immutable v1 and scientific v5 source are retained. No production attempt occurred.

Binder and exclusive remote installer now both allow **256KiB** release binding. Actual issued v43 is80360bytes; the regression rebuilds the real canonical binding with synthetic independent records and verifies it exceeds64KiB but fits256KiB, remote1MiB file bound,4MiB wire bound and unchanged scientific reader128MiB bound. Future phase/control growth beyond256KiB refuses before staging through the required binding review; no unbounded increase.

Both batch and Slurm transport use root's exact `root-ssh-standard-20261026` policy: pinned read-only known_hosts `b60433ea`, `/usr/bin/ssh -F /dev/null`, strict existing host checking, no host-key updates, explicit ProxyCommand with the same policy for contact, no ambient config or ProxyJump. `operate.validate` checks trust before the authority is consumed. Local operator+targetSSH+proxySSH require explicit3process/1GiB aggregate admission; each inherits256MiB AS/2000CPU seconds, with256MiB aggregate host margin. Existing16MiB local-record allocation and4MiB local FSIZE remain; neither SSH hop writes trust files.

New once kind `ROOT_D300_V5_OPERATOR_ONCE_V2`; exact pins include `ssh_contract.py`. `--check-only` uses the actual consumer. Distinct stage_hold and install_release namespaces remain unconsumed. Exact phase-bound `timing_science` and `allocation_premise` concurrences, accepted root all-writer/runtime adoption, current controls and each independent execution verdict remain required. The scientific v5 plan/worker, original failed attempt,63old+1corrective routing,32..63 continuation and full64 assembly/audit/finalizer order are unchanged. d900 still follows accepted complete d300.

FSIZE/source scope is unchanged: zero shared-log appends, stat-only custody identity/no-shrink/whole EOF+ALL remaining positive growth below2GiB-64MiB; scientific file cap2GiB, shell inherited4GiB. Do not reinterpret this as custody append authority.

17 targeted synthetic tests pass, including real-v43 binding regression; no scientific payload/remote/cluster/once action. Final designated reviewer is sol-storage2. FALSE templates are not execution authority.
