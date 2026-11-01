# Own scratch descriptor cleanup compatibility

Author `/root/deadline_audit`; independent review required. No production reads, jobs, cleanup or scientific execution performed.

The frozen 52-test shared development package remains unchanged. This candidate replaces only `output_budget.py`; its original linear budget is copied byte-identically. The caller must update its exact source pin after independent review.

H3's per-event `TemporaryDirectory` uses Python's `shutil.rmtree`, which calls `unlink(name, dir_fd=opened_directory)`. The previous extension rejected every descriptor-relative unlink, preventing cleanup of its own correctly accounted scratch files.

The new path resolution accepts only a single literal relative filename and a live directory descriptor. `/proc/self/fd` must identify a canonical directory under the exact own output/scratch root, with device/inode matching fstat. The resolved target must still be canonical, within scratch, accounted by this budget, and a regular file. Absolute paths with dir_fd, traversal, aliases, outside directories, regular-file descriptors and unaccounted files are refused. The same canonical-target check also prevents an absolute symlink deletion from crediting bytes belonging to its untouched target.

No reservation, peak/cumulative size, completed-output rewrite or source mutation policy changes. The original budget handles active-file reconciliation; only successfully admitted own-file deletion decrements retained accounting. This pre-operation audit hook retains the existing fail-terminal assumption if the actual unlink fails. The shared worker still reconciles retained bytes and refuses incomplete work.

Twelve synthetic tests pass, including actual H3 original scientific replay and TemporaryDirectory cleanup with the production budget hook installed, on both success and a corrupt-signature failure. Two events reuse the scratch reservation without accumulation. Deletion refusal tests retain accounting and source bytes. No protected inputs or actual cluster files are touched.
