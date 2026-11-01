#!/usr/bin/env python3
"""Standalone read-only validation of the finished R2 data set (audit lane, 2026-10-30, rev 2).

Answers "is every final scientific artifact present, at its recorded hash, with the durable
completion verdict, and do the huge sealed inputs/predictions still match the receipts that
attest them?" WITHOUT re-hashing terabytes: D-A26-style receipt proof (lstat: regular file,
recorded size, mtime/ctime <= the seal cutoff, symlinks REJECTED like r2_fast_authorize.py)
for the sealed-file set; content hashes only for the small controls, the result-scale
outputs, and the attempt-12 checkpoint bytes the run declared it was prepared from. The
label table is never opened (declared path + lstat + size; its sha is bound by the verified
attempt-12 marker).

Modes:
  (default)          exploratory: everything checkable now; missing final outputs are PENDING.
  --inventory        tier B: receipt-prove the whole read inventory (~3.4 TB, no content reads).
  --deep             also hash every D-A39 result pickle/secondary document, checkpoint bytes,
                     and run the science/identity coverage from the nine family pickles.
  --require-complete FINAL mode: pending counts as failure; full hashes and science checks
                     are mandatory. Only this mode may print PASS over a finished run.
Verdict semantics: FAIL exit 1 (a check failed, or --require-complete with anything pending);
INCOMPLETE exit 2 (pending artifacts, nothing failed); PASS exit 0 (nothing failed or pending).

Never writes. Never follows symlinks for proven reads (O_NOFOLLOW). Never opens label bytes.
--layout FILE: JSON object overriding the path/pin layout (used by the local mock tests).
"""
import argparse, hashlib, json, os, pickle, posixpath, stat, sys
from datetime import datetime, timezone

# --------------------------------------------------------------------------- layout (all overridable)
L = {
    "F": "<FORECAST_ROOT>",
    "R": "<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027",
    "ROOT": "<FORECAST_ROOT>/data-custodian/single-R2-v1",
    "ATTEMPT": "<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/attempt",
    "TARGET": "<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/rescore-secondary-D-A39",
    "CHAIN": "<RESULTS_ROOT>/nobackup/g2-chain-20261029T001120Z/repo/.agents/operations/agy-lanes-20261027/g2r2/chain",
    "CKPT_DIR": "<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-ckpt",
    "EVIDENCE_DIR": "<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-evidence-20261030T0440Z",
    "DRY_ROOT": "<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027",
    # D-A26 seal-verification cutoff
    "cutoff_ns": int(datetime(2026, 10, 29, 1, 36, 0, tzinfo=timezone.utc).timestamp() * 1_000_000_000),
    "pins": {   # name -> [path, sha256 (or prefix), [arms, retained_failures] or null]
        "published_freeze": ["<FORECAST_ROOT>/data-custodian/g1-freeze-20261028T184148Z/freeze.json",
                             "0164b1da3462affe180f900faa7a27f37b31da4d4af40b46f6b895be5b511127", [346, 54]],
        "amended_freeze": ["<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/amend/amended-freeze.json",
                           "921fc9bb06888e39b2399735cd2bc673506116375b5be84ce16dfee59b33beaa", [345, 55]],
        "seal": ["<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/g3-seal-sharded-20261029T013648Z/seal.json",
                 "8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f", None],
        "arm_spec": ["<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/g3-seal-sharded-20261029T013648Z/arm-spec.json",
                     "f8f30b35", None],   # short prefix; tier C proves the full marker-bound digest
        "marker": ["<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/amend/unblinded-8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f.json",
                   "882deb925bf72dc16d0d5abcea066e7e32dc01bdd205e691d7bf2e817d9e1b13", None],
        "primary": ["<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/attempt/primary.json",
                    "849e064518d1aa7e0b1c61c4c5836acd75864de12dce0278dab75918493e9ac1", None],
        "primary_scores": ["<FORECAST_ROOT>/data-custodian/single-R2-v1/arms/000/attempt/primary-scores.json",
                           "af9656ac8e1961eccbda75c590e5c8361a640229127dc122e79611d0365cef59", None],
    },
    "labels": {"path": "<FORECAST_ROOT>/data-custodian/complete-label-preparation-v3-retained/arms/000/attempt/output/labels.json",
               "sha256": "20e3044fa439866512d618d540dcefad1516151bc3f63ac482ee480bb6303447", "size_bytes": 644719739},
    "spec": {"path": "<FORECAST_ROOT>/newperiod-g2-inference-v1-20261027/r2-run-20261030-a17/r2-exec-spec.json",
             "sha256": "6f36f538ccfcce33df2e9396752fdb95503d3d6925babdca2340c384ed20ab13"},
    "attempt_files": ["intent.json", "primary-scores.json", "primary.json"],
    "legacy": {"baseline": {"baseline-ad753ced838eb812dcc44f64.pkl": 275334364},
               "counts": {"counts-959aaa80fd4471fa978b3e43.pkl": 10972},
               "members": {"members-1dc1eba251a8c5065f29ebdd.pkl": 3898663813, "members-125c784dc89ccc5380d85442.pkl": 8758133323,
                           "members-41d7a100dc90759763379813.pkl": 3352991403, "members-84ddd286f969b77b98ef221e.pkl": 5797143995,
                           "members-51e89096eddb87691d10b61f.pkl": 772719845},
               "stable": {"stable-8b2ded7e985a2611c5bbe7e6.pkl": 1479268630}},
    "checkpoint_sha": "97382e4abe67240152e5c01763eb970b0fc5c32eedfb77f0e7453d3dcb580be4",
    "code_files": ["r2_exec.py", "r2_checkpoint.py", "r2_parallel_origin.py", "r2_float32_decision.py", "r2_float32_scoring.py",
                   "r2_stable_persistence.py", "r2_input_cache.py", "r2_fast_authorize.py", "r2_fast_json.py",
                   "amend_wiring.py", "d60_only.py", "r2_rescore_secondary.py"],
    "evidence": ["evidence-baseline", "evidence-h1", "evidence-h3", "evidence-history", "evidence-ordinary",
                 "evidence-origin", "evidence-stable", "evidence-timing", "full-retention-review"],
    "families": ["additional_baselines", "counts", "membership-h1", "membership-h3", "membership-history",
                 "membership-ordinary", "membership-timing", "origin", "stable"],
    "membership_families": ["h1", "h3", "timing", "history", "ordinary"],
    "origin_strata": ["origin_change_invalid", "origin_change_valid"],
    "section_counts": {"counts": 34, "membership-h1": 20, "membership-h3": 80, "membership-timing": 60,
                       "membership-history": 48, "membership-ordinary": 32, "stable": 24,
                       "origin/origin_change_invalid": 20, "origin/origin_change_valid": 20, "additional_baselines": 6},
    "expected_stage_calls": {"origin": 1, "baseline": 1, "counts": 1, "members": 5, "stable": 1},
    "retained_total": 400, "evaluated_total": 395, "excluded_frozen_d30": 5, "primary_ids": 51, "secondary_cells": 344,
    "completion_kind": "newperiod_secondary_rescore_completion_D-A39_v1",
    "document_kind": "newperiod_secondary_rescore_D-A39_v1",
    "ready_kind": "D-A39_secondary_rescore_dry_run_v1",
    "small_cap": 1 << 28, "header_cap": 1 << 26,
}

RESULTS = []
HASHED = {}    # declared path -> sha256, only for files this run hashed from no-follow reads


class Bad(Exception):
    pass


def say(check, ok, **detail):
    entry = {"check": check, "ok": ok if ok is None else bool(ok)}
    entry.update(detail)
    RESULTS.append(entry)
    print(json.dumps(entry, sort_keys=True, default=str), flush=True)


def path(name):
    return L[name]


def st_regular(p):
    st = os.lstat(p)
    if not stat.S_ISREG(st.st_mode):
        raise Bad("not a regular file (symlinks/other rejected): " + str(p))
    return st


def open_nofollow(p):
    return os.fdopen(os.open(str(p), os.O_RDONLY | os.O_NOFOLLOW), "rb")


def sha_nofollow(p, cap=None):
    st = st_regular(p)
    if cap is not None and st.st_size > cap:
        raise Bad("over small cap: " + str(p))
    h = hashlib.sha256()
    with open_nofollow(p) as stream:
        for block in iter(lambda: stream.read(1 << 24), b""):
            h.update(block)
    digest = h.hexdigest()
    HASHED[posixpath.normpath(str(p))] = digest
    return digest, st.st_size


def read_nofollow(p, cap):
    st = st_regular(p)
    if st.st_size > cap:
        raise Bad("over read cap: " + str(p))
    with open_nofollow(p) as stream:
        return stream.read()


def load_json(p, cap=1 << 28):
    return json.loads(read_nofollow(p, cap))


def norm(p):
    return posixpath.normpath(str(p))


# --------------------------------------------------------------------- header-only parse of the big document
def parse_header(chunks):
    """Parse ONLY the header value from a sorted-keys {"header":{...},"secondary":{...}} document stream.

    Scans for the header value start at the document head, then raw_decodes the header object
    as it streams in: a multi-GiB secondary suffix is never parsed, and never even read past
    the point where the header object closes."""
    import codecs
    blocks = iter(chunks)
    buf = bytearray()

    def fill():
        try:
            buf.extend(next(blocks))
            return True
        except StopIteration:
            return False
    while buf.find(b'"header"') == -1:
        if not fill():
            raise Bad("no header key at the document start")
        if len(buf) > L["header_cap"]:
            raise Bad("header key not found within the cap")
    start = buf.find(b'"header"')
    if start > 24:
        raise Bad("the document does not start with the header key")
    while buf.find(b"{", start) == -1:
        if not fill():
            raise Bad("header value does not begin with '{'")
        if len(buf) > L["header_cap"]:
            raise Bad("header value start not found within the cap")
    brace = buf.find(b"{", start)
    decoder, text_decoder, text, pos, next_try = json.JSONDecoder(), codecs.getincrementaldecoder("utf-8")(), "", brace, 1
    while True:
        text += text_decoder.decode(bytes(buf[pos:]))
        pos = len(buf)
        if len(text) >= next_try:
            try:
                return decoder.raw_decode(text)[0]
            except json.JSONDecodeError:
                next_try = max(2 * next_try, 1 << 12)
        if len(buf) > L["header_cap"]:
            raise Bad("header exceeds cap — refusing to parse further")
        if not fill():
            text += text_decoder.decode(b"", True)
            try:
                return decoder.raw_decode(text)[0]
            except json.JSONDecodeError as error:
                raise Bad("unterminated header: " + str(error)[:120])


def doc_chunks(target, secondary_result):
    """Yield the document bytes: single file, or the raw-bytes split parts (never pickle-decoded)."""
    if "path" in (secondary_result or {}):
        p = secondary_result["path"]
        st_regular(p)

        def one():
            with open_nofollow(p) as stream:
                while True:
                    block = stream.read(1 << 24)
                    if not block:
                        return
                    yield block
        return one()
    split = (secondary_result or {}).get("split")
    if not isinstance(split, dict):
        raise Bad("secondary_result names neither a path nor a split manifest")
    base = posixpath.join(str(target), split["name"])
    manifest_path = base + ".manifest.json"
    manifest = load_json(manifest_path, 1 << 20)
    if manifest != split:
        raise Bad("split manifest on disk differs from the completion receipt")
    if manifest.get("format") != "raw-bytes":
        raise Bad("split manifest format is not raw-bytes")

    def many():
        for i in range(manifest["parts"]):
            with open_nofollow(f"{base}.pkl.part{i:04d}") as stream:
                while True:
                    block = stream.read(1 << 24)
                    if not block:
                        break
                    yield block
    return many()


def hash_chunks(chunks, want_bytes, want_sha, what):
    h, total = hashlib.sha256(), 0
    for chunk in chunks:
        h.update(chunk)
        total += len(chunk)
    if total != want_bytes or h.hexdigest() != want_sha:
        raise Bad(f"{what} bytes differ from the declared receipt (bytes {total} vs {want_bytes})")
    return {"bytes": total, "sha256": h.hexdigest()}


# --------------------------------------------------------------------------- parts (persist_object)
def parts_intact(directory, name, manifest):
    base = posixpath.join(str(directory), name)
    if load_json(base + ".manifest.json", 1 << 20) != manifest:
        return False, "manifest on disk differs from the reported receipt"
    total, h = 0, hashlib.sha256()
    try:
        for i in range(manifest["parts"]):
            with open_nofollow(f"{base}.pkl.part{i:04d}") as stream:
                for block in iter(lambda: stream.read(1 << 24), b""):
                    h.update(block)
                    total += len(block)
    except (OSError, Bad) as error:
        return False, repr(error)[:200]
    if total != manifest["bytes"] or h.hexdigest() != manifest["sha256_of_concatenated_parts"]:
        return False, "part bytes differ from the manifest digest"
    return True, ""


def parts_present(directory, name, manifest):
    base = posixpath.join(str(directory), name)
    try:
        if load_json(base + ".manifest.json", 1 << 20) != manifest:
            return False, "manifest on disk differs from the reported receipt"
        total = sum(st_regular(f"{base}.pkl.part{i:04d}").st_size for i in range(manifest["parts"]))
    except (OSError, Bad) as error:
        return False, repr(error)[:200]
    return total == manifest["bytes"], "size" if total != manifest["bytes"] else ""


# --------------------------------------------------------------------------------------------- tier A
def tier_a(code=True):
    pins, amended_ids, published_ids = L["pins"], None, None
    for name, (p, want, counts) in pins.items():
        try:
            got, size = sha_nofollow(p, L["small_cap"])
        except (OSError, Bad) as error:
            say("tierA:" + name, False, path=p, why=repr(error)[:160]); continue
        ok = got == want if len(want) == 64 else got.startswith(want)
        detail = {"path": p, "sha256": got[:20] + "..", "bytes": size}
        if ok and counts and name.endswith("freeze"):
            doc = load_json(p, 1 << 28)
            arms, failures = doc.get("arms", []), doc.get("retained_failures", [])
            ids = [a["arm_id"] for a in arms] + [a["arm_id"] for a in failures]
            frozen = [a["arm_id"] for a in arms + failures
                      if isinstance(a.get("role"), dict) and a["role"].get("family") == "neural" and a["role"].get("variant") == "core"
                      and a["role"].get("panel") == "reference" and a["role"].get("training") == "frozen_2025"
                      and a["role"].get("message_passing") == "sage" and a["role"].get("history") == "on"
                      and a["role"].get("horizon_seconds") == 30]
            detail.update(arms=len(arms), retained_failures=len(failures), unique_ids=len(set(ids)), frozen_d30=len(frozen))
            ok = ok and (len(arms), len(failures)) == tuple(counts) and len(set(ids)) == L["retained_total"]
            if name == "amended_freeze":
                amended_ids = (set(ids), set(frozen))
                ok = ok and len(frozen) == L["excluded_frozen_d30"]
            else:
                published_ids = set(ids)
        say("tierA:" + name, ok, **detail)
    if amended_ids and published_ids is not None:
        ids, frozen = amended_ids
        evaluated = len(ids) - len(frozen)
        say("tierA:identity-arithmetic", evaluated == L["evaluated_total"] and ids == published_ids and len(ids) == L["retained_total"],
            retained=len(ids), evaluated=evaluated, excluded_frozen_d30=len(frozen), published=len(published_ids),
            note=f"{evaluated} evaluated + {len(frozen)} retained/excluded frozen d30 = {len(ids)} original ids")
    seal = load_json(pins["seal"][0], 1 << 20)
    say("tierA:seal-content", len(seal.get("arms", [])) == 345 and seal.get("outcome_files_opened") is False
        and seal.get("spec_sha256") == pins["amended_freeze"][1]
        and all({"arm_id", "commitment_sha256", "predictions_sha256", "events"} <= set(a) for a in seal["arms"]),
        arms=len(seal.get("arms", [])), outcome_files_opened=seal.get("outcome_files_opened"))
    files = sorted(os.listdir(path("ATTEMPT")))
    say("tierA:attempt-dir", files == L["attempt_files"], files=files)
    marker = load_json(pins["marker"][0], 1 << 20)
    say("tierA:marker-binding", marker.get("seal_sha256") == pins["seal"][1] and marker.get("labels_sha256") == L["labels"]["sha256"]
        and marker.get("custody_spec_sha256") == pins["amended_freeze"][1] and marker.get("out") == pins["primary"][0],
        unblinded_utc=marker.get("unblinded_utc"), arm_spec_sha256=marker.get("arm_spec_sha256", "")[:16] + "..")
    lbl = L["labels"]
    try:
        st = st_regular(lbl["path"])          # lstat: a symlink here is a violation, contents are never opened
        ok = st.st_size == lbl["size_bytes"] and marker.get("labels_sha256") == lbl["sha256"]
        say("tierA:labels-metadata-only", ok, path=lbl["path"], bytes=st.st_size,
            mtime=datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            receipt="size + regular-file identity + attempt-12 marker labels_sha256 binding", note="label contents not read")
    except (OSError, Bad) as error:
        say("tierA:labels-metadata-only", False, path=lbl["path"], why=repr(error)[:160])
    try:
        spec = load_json(L["spec"]["path"], 1 << 30)
        got, _ = sha_nofollow(L["spec"]["path"])
        say("tierA:spec", got == L["spec"]["sha256"], entries=len(spec.get("inventory", [])))
        tmpl_p = spec["template"]["path"]
        try:
            tsha, tsize = sha_nofollow(tmpl_p, 1 << 26)      # the actual template bytes, never the claimed digest
        except (OSError, Bad) as error:
            tsha, tsize = None, None
            say("tierA:template", False, path=tmpl_p, why=repr(error)[:160])
        if tsha is not None:
            say("tierA:template", tsha == spec["template"]["sha256"], path=tmpl_p, sha256=tsha[:20] + "..", bytes=tsize)
        tmpl = load_json(tmpl_p, 1 << 26) if tsha == spec["template"]["sha256"] else {}
        log = tmpl.get("access_log") or tmpl.get("paths", {}).get("access_log")
        if log:
            size = st_regular(log).st_size if os.path.lexists(log) else None
            bounds = tmpl.get("bounds", {})
            say("tierA:access-log", None, informational=True, log_bytes=size, access_log_budget=bounds.get("access_log_bytes"),
                note="launch admission only: final validity never depends on this; the completed run proved its own growth")
        else:
            say("tierA:access-log", None, informational=True, note="template names no access log: nothing to report")
    except (OSError, Bad) as error:
        say("tierA:spec", False, why=repr(error)[:160])
        spec = None
    for name in L["evidence"]:
        p = L["EVIDENCE_DIR"] + "/" + name + ".json"
        try:
            sha_nofollow(p, L["small_cap"])
            ok = True
            if name == "full-retention-review":
                doc = load_json(p, L["small_cap"])
                ok = doc.get("passed") is True and doc.get("seal", {}).get("sha256") == pins["seal"][1]
        except (OSError, Bad) as error:
            ok = repr(error)[:160]
            say("tierA:" + name, False, path=p, why=ok)
            continue
        say("tierA:" + name, ok, path=p)
    for stage, files in L["legacy"].items():
        for fname, want in sorted(files.items()):
            p = L["CKPT_DIR"] + "/" + fname
            ok, why = True, ""
            try:
                st = st_regular(p)
                if st.st_size != want:
                    ok, why = False, "size differs from the pinned attempt-12 size"
                else:
                    with open_nofollow(p) as stream:
                        header = pickle.load(stream)
                    if header.get("stage") != stage or not fname.startswith(f"{stage}-{str(header.get('fingerprint', ''))[:24]}"):
                        ok, why = False, "checkpoint header stage/fingerprint differs"
            except (OSError, Bad, pickle.UnpicklingError, EOFError) as error:
                ok, why = False, repr(error)[:160]
            say("tierA:ckpt:" + fname, ok, **({"why": why} if why else {}))
    if L.get("checkpoint_sha"):
        try:
            say("tierA:r2_checkpoint-sha", sha_nofollow(L["CHAIN"] + "/r2_checkpoint.py", 1 << 22)[0] == L["checkpoint_sha"])
        except (OSError, Bad) as error:
            say("tierA:r2_checkpoint-sha", False, why=repr(error)[:160])
    if code:
        missing = [n for n in L["code_files"] if not os.path.lexists(L["CHAIN"] + "/" + n)]
        say("tierA:chain-code-present", not missing, missing=missing)
    readys = [p for p in os.listdir(L["DRY_ROOT"]) if p.startswith("r2-rescore-D-A39-dry-run-")]
    ready_files = [posixpath.join(L["DRY_ROOT"], d, "records-dry-run", "ready.json") for d in sorted(readys)
                   if os.path.lexists(posixpath.join(L["DRY_ROOT"], d, "records-dry-run", "ready.json"))]
    say("tierA:dry-run-ready", True if ready_files else None,
        found=[f.replace(L["DRY_ROOT"], "") for f in ready_files] or "no ready.json yet (dry run in progress or not started)",
        note="presence only; the approval->ready->code binding is proven by tierC:approval-chain")
    return spec


# --------------------------------------------------------------------------------------------- tier B
def tier_b(spec):
    bad, stats = [], {"checked": 0, "label_entries": 0, "sha_verified": 0}
    for item in spec["inventory"]:
        p = item["path"]
        if item["kind"] == "label":
            stats["label_entries"] += 1
            try:
                if st_regular(p).st_size != item["size_bytes"]:
                    bad.append({"path": p, "why": "label size differs (stat only)"})
            except (OSError, Bad) as error:
                bad.append({"path": p, "why": repr(error)[:120]})
            continue
        key = norm(p)
        if key in HASHED:
            stats["sha_verified"] += 1
            if HASHED[key] != item["sha256"]:
                bad.append({"path": p, "why": "tier-A hash differs from the inventory digest"})
            continue
        try:
            st = os.lstat(p)
        except OSError as error:
            bad.append({"path": p, "why": repr(error)[:120]}); continue
        if not stat.S_ISREG(st.st_mode):
            bad.append({"path": p, "why": "not a regular file (symlink or other)"})
        elif st.st_size != item["size_bytes"]:
            bad.append({"path": p, "why": "size differs from the inventory"})
        elif max(st.st_mtime_ns, st.st_ctime_ns) > L["cutoff_ns"]:
            bad.append({"path": p, "why": "mtime/ctime newer than the seal cutoff and not hashed as a small control"})
        else:
            stats["checked"] += 1
    say("tierB:inventory-receipts", not bad, **stats, bad=bad[:20], bad_count=len(bad),
        proof="tier-A-hashed-and-compared, or lstat regular + recorded size + mtime/ctime <= cutoff (D-A26, no symlinks); label stat-only")


# --------------------------------------------------------------------------------------------- tier C
def tier_c(full, science):
    target = path("TARGET")
    if not os.path.isdir(target):
        say("tierC:rescore-records", None, path=target, why="D-A39 records absent: the approved open run has not produced results")
        return
    want = ["intent.json", "primary-recomputed-D-A39.json", "primary-scores.json", "second-label-read-D-A39.json", "completion.json"]
    listing = sorted(os.listdir(target))
    missing = [w for w in want if w not in listing]
    other = [f for f in listing if f not in want and not f.startswith(("families", "secondary-result"))]
    say("tierC:fixed-artifacts", None if missing else True if not other else False, missing=missing, other=other,
        **({"why": "final outputs not produced yet (pending); unexpected extra files are a failure"} if missing else {}))
    intent = None
    try:
        intent = load_json(posixpath.join(target, "intent.json"), 1 << 20)
    except (OSError, Bad, ValueError) as error:
        say("tierC:intent", None if isinstance(error, OSError) else False, why=repr(error)[:160])
    if intent is not None:
        if intent.get("mode") != "open" or intent.get("deviation") != "D-A39" or intent.get("automatic_retry_authorized") is not False:
            say("tierC:intent", False, mode=intent.get("mode"), deviation=intent.get("deviation"))
        else:
            say("tierC:intent", True, approval_ref=bool(intent.get("approval")))
    try:
        completion = load_json(posixpath.join(target, "completion.json"), 1 << 20)
    except (OSError, Bad, ValueError) as error:
        say("tierC:completion", None if isinstance(error, OSError) else False, why=repr(error)[:160]); return
    blocking = completion.get("blocking") or {}
    say("tierC:completion", completion.get("kind") == L["completion_kind"] and completion.get("deviation") == "D-A39"
        and completion.get("passed") is True and not blocking and completion.get("errors") == []
        and completion.get("label_reads") == 1 and completion.get("outcome_release_authorized") is False
        and completion.get("records") == target and isinstance(completion.get("secondary_result"), dict)
        and isinstance(completion.get("raw_result"), dict),
        kind=completion.get("kind"), passed=completion.get("passed"), blocking_keys=sorted(blocking), errors=len(completion.get("errors") or []),
        label_reads=completion.get("label_reads"), utc=completion.get("utc"))
    if completion.get("passed") is False:
        say("tierC:completion-blocking", False, blocking=blocking, note="the driver's own durable verdict refused completion")
    # marker + secondary document
    d39_marker = posixpath.join(target, "second-label-read-D-A39.json")
    try:
        msha, _ = sha_nofollow(d39_marker, 1 << 20)
        say("tierC:d39-marker", True, sha256=msha[:20] + "..")
    except FileNotFoundError as error:
        say("tierC:d39-marker", None, why=repr(error)[:160])
    except (OSError, Bad) as error:
        say("tierC:d39-marker", False, why=repr(error)[:160])
    sr = completion.get("secondary_result") or {}
    header = None
    try:
        header = parse_header(doc_chunks(target, sr))
        say("tierC:header-parsed", header.get("kind") == L["document_kind"], kind=header.get("kind"),
            representation="split raw-bytes parts" if "split" in sr else "single file",
            note="only the header object was parsed; the secondary suffix was not decoded")
    except FileNotFoundError as error:
        say("tierC:header-parsed", None, why="secondary document not written yet: " + repr(error)[:120])
    except (Bad, OSError, UnicodeDecodeError, ValueError) as error:
        say("tierC:header-parsed", False, why=repr(error)[:200])
    if header:
        pc = header.get("primary_comparison") or {}
        scores = pc.get("scores") or {}
        say("tierC:primary-equality", pc.get("canonical_identical_except_unblinded_marker") is True
            and scores.get("canonical_identical_except_primary_report_path") is True
            and pc.get("attempt12", {}).get("sha256") == L["pins"]["primary"][1]
            and scores.get("attempt12", {}).get("sha256") == L["pins"]["primary_scores"][1]
            and pc.get("recomputed", {}).get("sha256") == sha_nofollow(posixpath.join(target, "primary-recomputed-D-A39.json"), L["small_cap"])[0]
            and scores.get("recomputed", {}).get("sha256") == sha_nofollow(posixpath.join(target, "primary-scores.json"), L["small_cap"])[0]
            and all(str(x).startswith("/unblinded_marker") for x in (pc.get("diff") or {}).get("paths", []))
            and all(str(x).startswith("/primary_report_path") for x in (scores.get("diff") or {}).get("paths", [])),
            primary_identical_except_marker=pc.get("canonical_identical_except_unblinded_marker"),
            scores_identical_except_report_path=scores.get("canonical_identical_except_primary_report_path"),
            expected_exclusions=[pc.get("expected_difference"), "/primary_report_path"])
        dc = header.get("decision_check") or {}
        say("tierC:decision-check", (dc.get("members") or {}).get("float32_mismatch_rows") == 0
            and (dc.get("origin") or {}).get("float64_mismatch_rows") == 0 and (dc.get("stable") or {}).get("float64_mismatch_rows") == 0
            and (dc.get("members") or {}).get("arms_checked", 0) > 0,
            members=(dc.get("members") or {}).get("arms_checked"), float32_mismatch=(dc.get("members") or {}).get("float32_mismatch_rows"))
        say("tierC:release-flag", header.get("outcome_release_authorized") is False
            and header.get("label_reads_this_run") == 1 and header.get("primary_of_record", {}).get("sha256") == L["pins"]["primary"][1],
            label_reads_this_run=header.get("label_reads_this_run"))
    # families: exactly nine unique receipts, header entry == disk manifest, parts intact
    fam_dir = posixpath.join(target, "families")
    entries = (header or {}).get("families") or []
    names = [e.get("family") for e in entries]
    problems = {k: [] for k in ("missing", "duplicate", "unexpected", "failed", "persist_error", "not_persisted")}
    for name in L["families"]:
        if names.count(name) == 0:
            problems["missing"].append(name)
        elif names.count(name) > 1:
            problems["duplicate"].append(name)
    problems["unexpected"] = sorted({n for n in names if n not in L["families"]})
    for entry in entries:
        name = entry.get("family")
        if entry.get("status") != "scored":
            problems["failed"].append(name)
        if "persist_error" in entry:
            problems["persist_error"].append(name)
            continue
        persisted = entry.get("persisted") or {}
        ok = isinstance(persisted, dict) and persisted.get("name") == name and persisted.get("parts", 0) >= 1 and persisted.get("bytes", 0) > 0
        if ok:
            ok, _ = (parts_intact if full else parts_present)(fam_dir, name, persisted)
        if not ok:
            problems["not_persisted"].append(name)
    say("tierC:families", None if not header else not any(problems.values()),
        **{"problems": problems, "entries": len(entries), "why": "header not available yet" if not header else ""})
    # aggregate + raw receipts
    if full and header:
        try:
            say("tierC:secondary-document-bytes", True, **(hash_chunks(doc_chunks(target, sr), sr.get("bytes"), sr.get("sha256"), "secondary-result")))
        except (Bad, OSError) as error:
            say("tierC:secondary-document-bytes", False, why=repr(error)[:200])
    raw = completion.get("raw_result") or {}
    if raw:
        ok, why = (parts_intact if full else parts_present)(target, "secondary-result-raw", raw)
        say("tierC:raw-result", ok, **({"why": why} if why else {}), bytes=raw.get("bytes"), parts=raw.get("parts"))
    else:
        say("tierC:raw-result", False, why="completion names no raw result receipt")
    # stage bindings: nine stages, five distinct membership fingerprints, declared bytes hashed in full mode
    stages = (header or {}).get("stages") or []
    calls = {}
    for s in stages:
        calls[s.get("stage")] = calls.get(s.get("stage"), 0) + 1
    member_fps = {s.get("fingerprint") for s in stages if s.get("stage") == "members"}
    stage_problems, recomputed_stages = [], []
    for s in stages:
        name = s.get("stage")
        if s.get("source") == "computed":
            recomputed_stages.append(name)
        ck = s.get("checkpoint") if isinstance(s.get("checkpoint"), dict) else {}
        artifacts = ck.get("artifacts") or ([{"path": s.get("path"), "bytes": s.get("bytes"), "sha256": s.get("sha256")}]
                                            if s.get("sha256") else [])
        if artifacts:
            for a in artifacts:
                try:
                    if st_regular(a["path"]).st_size != a["bytes"]:
                        stage_problems.append(f"{name}:{posixpath.basename(a['path'])}: size")
                    elif full and sha_nofollow(a["path"], None)[0] != a["sha256"]:
                        stage_problems.append(f"{name}:{posixpath.basename(a['path'])}: digest")
                except (OSError, Bad, KeyError) as error:
                    stage_problems.append(f"{name}: {repr(error)[:80]}")
        elif s.get("source") == "computed":   # older driver shape: the origin save receipt is the only cross-check
            save = s.get("save") or {}
            if save.get("status") == "saved":
                base = save.get("manifest", "").replace(".manifest.json", "")
                try:
                    manifest = load_json(save["manifest"], 1 << 20)
                    total = sum(st_regular(f"{base}.part{i:04d}").st_size for i in range(manifest.get("parts", -1)))
                    if total != manifest.get("bytes"):
                        stage_problems.append("origin rolling parts size")
                    for a in save.get("artifacts", []):
                        if st_regular(a["path"]).st_size != a.get("bytes"):
                            stage_problems.append(f"origin artifact {posixpath.basename(a['path'])}: size")
                        elif full and sha_nofollow(a["path"], None)[0] != a.get("sha256"):
                            stage_problems.append(f"origin artifact {posixpath.basename(a['path'])}: digest")
                except (OSError, Bad, KeyError) as error:
                    stage_problems.append("origin save: " + repr(error)[:120])
        else:
            stage_problems.append(f"{name}: no byte binding")
    say("tierC:stage-bindings", None if not header else calls == L["expected_stage_calls"] and len(member_fps) == 5 and not stage_problems,
        calls=calls, membership_fingerprints=len(member_fps), problems=stage_problems[:10], recomputed=recomputed_stages,
        **({"why": "header not available yet"} if not header else {}),
        note="recomputed stages: the integrated successor driver refuses the label until every stage is byte-bound to the "
             "approved dry run, so a passed completion naming a recomputed stage needs review")
    # approval -> ready -> code binding
    if intent is None:
        say("tierC:approval-chain", None, why="intent.json not available")
    else:
        try:
            approval_ref = intent["approval"]
            asha, _ = sha_nofollow(approval_ref["path"], 1 << 20)
            approval = load_json(approval_ref["path"], 1 << 20)
            ready_ref = approval["dry_run_ready"]
            rsha, _ = sha_nofollow(ready_ref["path"], 1 << 20)
            ready = load_json(ready_ref["path"], 1 << 20)
            code_ok = all(sha_nofollow(L["CHAIN"] + "/" + n, 1 << 22)[0] == ref["sha256"] for n, ref in ready.get("code", {}).items())
            hdr_binding = None if header is None else header.get("approval") == approval_ref
            ok = (asha == approval_ref["sha256"] and rsha == ready_ref["sha256"]
                  and ready.get("kind") == L["ready_kind"] and ready.get("labels_opened") is False
                  and ready.get("reader", {}).get("label_reads") == 0 and ready.get("target_records") == path("TARGET")
                  and ready.get("driver", {}).get("sha256") == sha_nofollow(L["CHAIN"] + "/r2_rescore_secondary.py", 1 << 22)[0]
                  and ready.get("float32_scoring", {}).get("module", {}).get("sha256") == sha_nofollow(L["CHAIN"] + "/r2_float32_scoring.py", 1 << 22)[0]
                  and code_ok and hdr_binding is not False
                  and approval.get("deviation") == "D-A39" and approval.get("scope") == "secondary lanes only"
                  and approval.get("labels_sha256") == L["labels"]["sha256"] and approval.get("seal_sha256") == L["pins"]["seal"][1]
                  and approval.get("primary_json_sha256") == L["pins"]["primary"][1])
            say("tierC:approval-chain", ok, approval=approval_ref["path"], ready=ready_ref["path"],
                code_files_checked=len(ready.get("code", {})), header_binding=hdr_binding)
        except (OSError, Bad, KeyError, ValueError) as error:
            say("tierC:approval-chain", False, why=repr(error)[:200])
    # science/identity coverage from the nine family pickles
    if science and not header:
        say("tierC:identity-coverage", None, why="header/family receipts not available yet")
    elif science:
        try:
            cells = {}
            for name in L["families"]:
                persisted = next(e["persisted"] for e in entries if e.get("family") == name and e.get("persisted"))
                base = posixpath.join(fam_dir, name)
                data = b"".join(open_nofollow(f"{base}.pkl.part{i:04d}").read() for i in range(persisted["parts"]))
                obj = pickle.loads(data)
                sections = {f"origin/{s}": obj["families"][s] for s in L["origin_strata"]} if name == "origin" else {name: obj}
                for section_name, section in sections.items():
                    need = L["section_counts"][section_name]
                    cs = section.get("cells")
                    if not isinstance(cs, dict) or len(cs) != need or section.get("declares_primary_finding") is not False:
                        raise Bad(f"{section_name}: cells {len(cs) if isinstance(cs, dict) else '?'} != {need} or declares_primary_finding")
                    for identity, cell in cs.items():
                        if not (isinstance(cell, dict) and isinstance(cell.get("status"), str) and isinstance(cell.get("role"), dict)):
                            raise Bad(f"{section_name}/{identity}: cell without explicit status/role")
                        if identity in cells:
                            raise Bad(f"identity in two sections: {identity}")
                        cells[identity] = section_name
            primary = load_json(L["pins"]["primary"][0], 1 << 26)
            primary_ids = {i for h in primary.get("arms", {}).values() for ids in h.values() for i in ids}
            amended = load_json(L["pins"]["amended_freeze"][0], 1 << 28)
            all_ids = {a["arm_id"] for a in amended.get("arms", [])} | {a["arm_id"] for a in amended.get("retained_failures", [])}
            frozen = {a["arm_id"] for a in amended.get("arms", []) + amended.get("retained_failures", [])
                      if isinstance(a.get("role"), dict) and a["role"].get("training") == "frozen_2025" and a["role"].get("horizon_seconds") == 30}
            union = primary_ids | set(cells) | frozen
            ok = (len(cells) == L["secondary_cells"] and len(primary_ids) == L["primary_ids"] and len(frozen) == L["excluded_frozen_d30"]
                  and len(union) == L["retained_total"] and union == all_ids and len(primary_ids) + len(cells) == L["evaluated_total"]
                  and not (primary_ids & set(cells)) and not (frozen & set(cells)))
            say("tierC:identity-coverage", ok, secondary_cells=len(cells), primary_ids=len(primary_ids),
                excluded_frozen_d30=len(frozen), union=len(union), evaluated=len(primary_ids) + len(cells),
                note="51 primary + 344 secondary = 395 evaluated; + 5 retained/excluded frozen d30 = 400 retained identities")
        except (Bad, OSError, KeyError, StopIteration, pickle.UnpicklingError) as error:
            say("tierC:identity-coverage", False, why=repr(error)[:240])


# ------------------------------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--require-complete", action="store_true", help="final mode: nothing may be pending; full hashes and science checks")
    ap.add_argument("--no-code", action="store_true")
    ap.add_argument("--layout", type=argparse.FileType("r"), help="JSON layout overrides (mock tests)")
    a = ap.parse_args(argv)
    if a.layout:
        overrides = json.load(a.layout)
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(L.get(key), dict) and key not in ("pins",):
                L[key].update(value)
            else:
                L[key] = value
    full = a.deep or a.require_complete
    if not os.path.isdir(L["ROOT"]):
        print(json.dumps({"fatal": "root not present; run where <CLUSTER_STORAGE> is mounted (read-only) or use --layout"})); return 2
    spec = tier_a(code=not a.no_code)
    if a.inventory and spec:
        tier_b(spec)
    tier_c(full=full, science=full)
    done = [r for r in RESULTS if r["ok"] is not None]
    failed = [r["check"] for r in done if not r["ok"]]
    pending = [r["check"] for r in RESULTS if r["ok"] is None and not r.get("informational")]
    if a.require_complete:
        failed += pending
        pending = []
    verdict = "FAIL" if failed else ("INCOMPLETE" if pending else "PASS")
    print(json.dumps({"summary": verdict, "checks": len(RESULTS), "failed": failed, "pending": pending,
                      "mode": "require-complete" if a.require_complete else ("deep" if a.deep else "explore")}, sort_keys=True))
    return 0 if verdict == "PASS" else (1 if verdict == "FAIL" else 2)


if __name__ == "__main__":
    sys.exit(main())
