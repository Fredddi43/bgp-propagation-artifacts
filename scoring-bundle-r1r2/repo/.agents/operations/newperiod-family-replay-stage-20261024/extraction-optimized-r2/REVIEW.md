Local source-only optimization candidate. No actual replay or authority.

Original origin adapter and full archive scope unchanged. Prefix partition preserves physical row order; actual inclusive timestamp envelope only skips provably empty NONnominal parts. Every nominal empty part remains. Complete day archive provenance is stored once, SHA-bound and expanded before the original ownership loader. Original load_owned_parts numerical/ownership logic unchanged. Cache limited to470 days and128MiB encoded metadata; allow4GiB decoded object/allocator headroom in the outer resource plan (hard process/cgroup bounds still apply). Before/after identity and bytes checked on first read; cached identity changes refuse.

Complete produced-part index records original event order and exact manifest. Merge validates original done/hash, distinct full population subset, original order, every indexed pair, complete source grid and exact deterministic lane-to-day mapping. No absent index/day/part means empty input. Existing source qualifications remain unchanged.

24 tests: actual original extractor with synthetic native decoding only; exact ordered part rows, duplicate physical occurrences, inclusive boundaries, four-day late rows, nominal empties, exact expanded provenance and day ledger bytes. Original merger outputs match; anomalous physical rows compared unsorted, membership group aggregate compared as a multiset because original group_by has nondeterministic order. Failed/missing days/index/parts, duplicate/foreign/reversed index, count mismatch, lane swap, first-read/cached mutation and total metadata cache bound refuse. No scientific data reads.

Run POLARS_MAX_THREADS=8 PYTHONPATH=src /tmp/np-hostver-venv/bin/python -B -m pytest -q <this directory>. Outer scratch/runtime/resource successor remains separate, not launch-ready from this kernel.

R2: cache-cap exhaustion raises operational ReplayResourceError, never UnresolvedOccurrenceOwnership. Genuine merge phase regression proves whole operation fails without statuses.json or fabricated unresolved summary. Predecessor v1 preserved.
