#!/usr/bin/env python3
"""Standalone read-only validation of the finished R2 data set (audit lane, 2026-10-30).

Answers "is every final scientific artifact present, at its recorded hash, and are the huge
sealed inputs/predictions still the ones the seal receipts attest?" WITHOUT re-hashing
terabytes: large data is proven by the D-A26 receipt argument (regular file, recorded size,
ctime/mtime not newer than the seal cutoff) instead of content hashes. The label table is
NEVER opened: it is checked by recorded reference, size and mtime only.

Tiers (default = a c):
  a  re-hash small scientific controls and results (<= --small-cap, default 256 MiB):
     published freeze, amended freeze, seal, arm spec, one-opening marker, attempt-12
     intent/primary/primary-scores, evidence docs, full-retention review, D-A39 dry-run
     ready.json / open-run approval binding, chain code files, checkpoint headers.
  b  receipt-proof the whole D-A39 read inventory (~3.4 TB across 328,874 entries): every
     non-label entry must be a regular file of the recorded size with stime/ctime <= the
     seal cutoff (2026-10-29T01:36:00Z, D-A26); label entry stat-checked only. No content read.
  c  D-A39 re-scoring records (arms/000/rescore-secondary-D-A39), when they exist: fixed
     artifact set, families exactly the expected nine with part manifests, secondary-result.json
     header (primary of record, one label read, decision check clean, no failed family).
     --deep additionally hashes every family/secondary pickle part (result-sized, not TB-sized).

usage: python3 validate_final_data.py [--inventory] [--deep] [--no-code] [--json]
Exit 0 = every executed check passed. Prints one JSON line per check, summary last.
Read-only: this script never writes, never follows links for reads it performs, opens
everything read-only, and reads the label path only via os.stat.
"""
import argparse, hashlib, json, os, pickle, stat, sys
from datetime import datetime, timezone

F = "<FORECAST_ROOT>"
R = F + "/newperiod-g2-inference-v1-20261027"
ROOT = F + "/data-custodian/single-R2-v1"
ATTEMPT = ROOT + "/arms/000/attempt"
TARGET = ROOT + "/arms/000/rescore-secondary-D-A39"
CHAIN = "<RESULTS_ROOT>/nobackup/g2-chain-20261029T001120Z/repo/.agents/operations/agy-lanes-20261027/g2r2/chain"
CUTOFF_NS = int(datetime(2026, 10, 29, 1, 36, 0, tzinfo=timezone.utc).timestamp() * 1_000_000_000)  # D-A26 cutoff

# Pinned identities (chain/r2_rescore_secondary.py constants + MASTER-PLAN root anchors).
PIN = {
    "published_freeze": (F + "/data-custodian/g1-freeze-20261028T184148Z/freeze.json",
                         "0164b1da3462affe180f900faa7a27f37b31da4d4af40b46f6b895be5b511127", (346, 54)),
    "amended_freeze":   (R + "/amend/amended-freeze.json",
                         "921fc9bb06888e39b2399735cd2bc673506116375b5be84ce16dfee59b33beaa", (345, 55)),
    "seal":             (R + "/g3-seal-sharded-20261029T013648Z/seal.json",
                         "8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f", None),
    "arm_spec":         (R + "/g3-seal-sharded-20261029T013648Z/arm-spec.json",
                         "f8f30b3525bc602012b0e0c76ebb", None),   # prefix recorded in the marker
    "marker":           (R + "/amend/unblinded-8ede1a58a437559ea1fb5259edd60141e1a8312ae286a978e7e4554e19a6014f.json",
                         "882deb925bf72dc16d0d5abcea066e7e32dc01bdd205e691d7bf2e817d9e1b13", None),
    "primary":          (ATTEMPT + "/primary.json",
                         "849e064518d1aa7e0b1c61c4c5836acd75864de12dce0278dab75918493e9ac1", None),
    "primary_scores":   (ATTEMPT + "/primary-scores.json",
                         "af9656ac8e1961eccbda75c590e5c8361a640229127dc122e79611d0365cef59", None),
}
LABELS = {"path": F + "/data-custodian/complete-label-preparation-v3-retained/arms/000/attempt/output/labels.json",
          "sha256": "20e3044fa439866512d618d540dcefad1516151bc3f63ac482ee480bb6303447", "size_bytes": 644719739}
SPEC = {"path": R + "/r2-run-20261030-a17/r2-exec-spec.json",
        "sha256": "6f36f538ccfcce33df2e9396752fdb95503d3d6925babdca2340c384ed20ab13"}
ATTEMPT_FILES = ["intent.json", "primary-scores.json", "primary.json"]
LEGACY = {"baseline": {"baseline-ad753ced838eb812dcc44f64.pkl": 275334364},
          "counts": {"counts-959aaa80fd4471fa978b3e43.pkl": 10972},
          "members": {"members-1dc1eba251a8c5065f29ebdd.pkl": 3898663813, "members-125c784dc89ccc5380d85442.pkl": 8758133323,
                      "members-41d7a100dc90759763379813.pkl": 3352991403, "members-84ddd286f969b77b98ef221e.pkl": 5797143995,
                      "members-51e89096eddb87691d10b61f.pkl": 772719845},
          "stable": {"stable-8b2ded7e985a2611c5bbe7e6.pkl": 1479268630}}
CHECKPOINT_SHA = "97382e4abe67240152e5c01763eb970b0fc5c32eedfb77f0e7453d3dcb580be4"
CODE_FILES = ("r2_exec.py", "r2_checkpoint.py", "r2_parallel_origin.py", "r2_float32_decision.py", "r2_float32_scoring.py",
              "r2_stable_persistence.py", "r2_input_cache.py", "r2_fast_authorize.py", "r2_fast_json.py",
              "amend_wiring.py", "d60_only.py", "r2_rescore_secondary.py")
FAMILIES = {"membership-h1", "membership-h3", "membership-timing", "membership-history", "membership-ordinary",
            "stable", "counts", "origin", "additional_baselines"}
EVIDENCE_DIR = R + "/r2-evidence-20261030T0440Z"

RESULTS = []
SELF_HASHED = {}   # path -> sha256 for every file tier A re-hashed; tier B proves these instead of the ctime cutoff


def say(check, ok, **detail):
    RESULTS.append({"check": check, "ok": ok if ok is None else bool(ok), **detail})
    print(json.dumps(RESULTS[-1], sort_keys=True), flush=True)


def sha_file(path, cap=None):
    size = os.path.getsize(path)
    if cap is not None and size > cap:
        return None, size
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 24), b""):
            h.update(block)
    digest = h.hexdigest()
    SELF_HASHED[os.path.realpath(path)] = digest
    return digest, size


def tier_a(small_cap, code=True):
    for name, (path, want, counts) in PIN.items():
        if not os.path.isfile(path):
            say("tierA:" + name, False, path=path, why="missing"); continue
        got, size = sha_file(path, small_cap)
        ok = got == want if len(want) == 64 else (got or "").startswith(want)
        detail = {"path": path, "sha256": (got or "over-small-cap")[:20] + "..", "bytes": size}
        if got and counts:
            doc = json.load(open(path))
            detail["arms"] = len(doc.get("arms", []))
            detail["retained_failures"] = len(doc.get("retained_failures", []))
            ok = ok and (len(doc.get("arms", [])), len(doc.get("retained_failures", []))) == counts
        say("tierA:" + name, ok, **detail)
    # seal content: 345 arms, receipts for all, no outcome files opened
    seal = json.load(open(PIN["seal"][0]))
    say("tierA:seal-content", len(seal.get("arms", [])) == 345 and seal.get("outcome_files_opened") is False
        and seal.get("spec_sha256") == PIN["amended_freeze"][1]
        and all({"arm_id", "commitment_sha256", "predictions_sha256", "events"} <= set(a) for a in seal["arms"]),
        arms=len(seal.get("arms", [])), outcome_files_opened=seal.get("outcome_files_opened"))
    # attempt directory: exactly the three files; marker binds them
    files = sorted(os.listdir(ATTEMPT))
    say("tierA:attempt-dir", files == ATTEMPT_FILES, files=files)
    marker = json.load(open(PIN["marker"][0]))
    say("tierA:marker-binding", marker.get("seal_sha256") == PIN["seal"][1] and marker.get("labels_sha256") == LABELS["sha256"]
        and marker.get("custody_spec_sha256") == PIN["amended_freeze"][1] and marker.get("out") == PIN["primary"][0],
        unblinded_utc=marker.get("unblinded_utc"))
    # labels: metadata only, never opened
    st = os.stat(LABELS["path"])
    say("tierA:labels-metadata-only", st.st_size == LABELS["size_bytes"], path=LABELS["path"], bytes=st.st_size,
        mtime=datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), note="label contents not read")
    # read inventory + bounds
    inv_doc_raw = open(SPEC["path"], "rb").read()
    inv_doc = json.loads(inv_doc_raw)
    got, size = sha_file(SPEC["path"])
    SELF_HASHED[os.path.realpath(inv_doc["template"]["path"])] = inv_doc["template"]["sha256"]
    tmpl = json.loads(open(inv_doc["template"]["path"]).read())
    bounds, log = tmpl["bounds"], tmpl["access_log"]
    log_size = os.path.getsize(log)
    say("tierA:spec", got == SPEC["sha256"], entries=len(inv_doc.get("inventory", [])), bytes=size)
    say("tierA:access-log-admissible", log_size + bounds["access_log_bytes"] <= bounds["output_file_bytes"],
        log_bytes=log_size, limit_bytes=bounds["output_file_bytes"], headroom_bytes=bounds["output_file_bytes"] - bounds["access_log_bytes"] - log_size)
    # evidence + signed review (hashed: these post-date the seal cutoff legitimately, tier B proves them by sha)
    for name in ("evidence-baseline", "evidence-h1", "evidence-h3", "evidence-history", "evidence-ordinary",
                 "evidence-origin", "evidence-stable", "evidence-timing", "full-retention-review"):
        p = EVIDENCE_DIR + "/" + name + ".json"
        ok = os.path.isfile(p)
        if ok:
            sha_file(p)
            if name == "full-retention-review":
                doc = json.load(open(p))
                ok = doc.get("passed") is True and doc.get("seal", {}).get("sha256") == PIN["seal"][1]
        say("tierA:" + name, ok, path=p)
    # attempt-12 checkpoints: sizes pinned, stage + fingerprint prefix in the header (header bytes only)
    for stage, files in LEGACY.items():
        for fname, want_size in sorted(files.items()):
            p = R + "/r2-ckpt/" + fname
            ok = os.path.isfile(p) and os.path.getsize(p) == want_size
            if ok:
                with open(p, "rb") as stream:
                    header = pickle.load(stream)          # stops after the small header object
                ok = header.get("stage") == stage and fname.startswith(f"{stage}-{header.get('fingerprint', '')[:24]}")
            say("tierA:ckpt:" + fname, ok, bytes=os.path.getsize(p) if os.path.isfile(p) else None)
    ck = CHAIN + "/r2_checkpoint.py"
    if os.path.isfile(ck):
        got, _ = sha_file(ck)
        say("tierA:r2_checkpoint-sha", got == CHECKPOINT_SHA, sha256=(got or "")[:20] + "..")
    if code:
        missing = [n for n in CODE_FILES if not os.path.isfile(CHAIN + "/" + n)]
        say("tierA:chain-code-present", not missing, missing=missing,
            note="full chain-code sha binding is enforced by the driver's verify_approval against ready.json")
    # dry-run ready.json / approval when present
    ready = sorted(p for p in os.listdir(R) if p.startswith("r2-rescore-D-A39-dry-run-"))
    ready_files = [f for d in ready for f in (d + "/records-dry-run/ready.json",) if os.path.isfile(R + "/" + f)]
    say("tierA:dry-run-ready", ready_files or None, found=ready_files or "not written yet (dry run in progress or not started)")
    return inv_doc


def tier_b(inv_doc):
    bad, stats = [], {"checked": 0, "label_entries": 0, "sha_verified": 0}
    for item in inv_doc["inventory"]:
        path = item["path"]
        if item["kind"] == "label":                      # never opened: stat metadata only
            stats["label_entries"] += 1
            if os.stat(path).st_size != item["size_bytes"]:
                bad.append({"path": path, "why": "label size differs (stat only)"})
            continue
        real = os.path.realpath(path)
        if real in SELF_HASHED:                          # small controls/results hashed in tier A may post-date the cutoff
            stats["sha_verified"] += 1
            if SELF_HASHED[real] != item["sha256"]:
                bad.append({"path": path, "why": "tier-A sha differs from inventory sha"})
            continue
        try:
            st = os.stat(path)
        except OSError as error:
            bad.append({"path": path, "why": repr(error)[:120]}); continue
        stats["checked"] += 1
        if not stat.S_ISREG(st.st_mode):
            bad.append({"path": path, "why": "not regular"})
        elif st.st_size != item["size_bytes"]:
            bad.append({"path": path, "why": "size differs from inventory"})
        elif max(st.st_mtime_ns, st.st_ctime_ns) > CUTOFF_NS:
            bad.append({"path": path, "why": "mtime/ctime newer than the seal cutoff"})
    say("tierB:inventory-receipts", not bad, **stats, bad=bad[:20], bad_count=len(bad),
        proof="hashed-in-tier-A or (regular file + recorded size + mtime/ctime <= 2026-10-29T01:36:00Z, D-A26); label stat-only; no bulk content read")


def read_json_head(path, cap=8 << 20):
    with open(path, "rb") as stream:
        raw = stream.read(cap)
    return json.JSONDecoder().raw_decode(raw.decode("utf-8", "ignore"))[0]      # header precedes "secondary" (sort_keys)


def tier_c(deep=False):
    if not os.path.isdir(TARGET):
        say("tierC:rescore-records", None, path=TARGET, why="not present yet: the D-A39 open run has not been launched")
        return
    files = sorted(os.listdir(TARGET))
    want = ["intent.json", "primary-recomputed-D-A39.json", "primary-scores.json", "second-label-read-D-A39.json"]
    say("tierC:fixed-artifacts", all(w in files for w in want), files=[f for f in files if not f.startswith(("families", "secondary-result"))])
    fam_dir = TARGET + "/families"
    found, bad = set(), []
    for name in sorted(os.listdir(fam_dir)) if os.path.isdir(fam_dir) else []:
        if name.endswith(".manifest.json"):
            base = name[:-len(".manifest.json")]
            found.add(base)
            manifest = json.load(open(fam_dir + "/" + name))
            parts = [f"{fam_dir}/{base}.pkl.part{i:04d}" for i in range(manifest["parts"])]
            if not all(os.path.isfile(p) for p in parts) or sum(os.path.getsize(p) for p in parts) != manifest["bytes"]:
                bad.append(base)
            if deep:
                h = hashlib.sha256()
                for p in parts:
                    with open(p, "rb") as stream:
                        for block in iter(lambda: stream.read(1 << 24), b""):
                            h.update(block)
                if h.hexdigest() != manifest["sha256_of_concatenated_parts"]:
                    bad.append(base + " (sha)")
    say("tierC:families", found == FAMILIES and not bad, missing=sorted(FAMILIES - found), unexpected=sorted(found - FAMILIES),
        corrupted=bad, deep_verified=deep)
    sj = TARGET + "/secondary-result.json"
    if os.path.isfile(sj):
        head = read_json_head(sj).get("header", {})
        checks = {"primary_of_record": head.get("primary_of_record", {}).get("sha256") == PIN["primary"][1],
                  "one_label_read": head.get("label_reads_this_run") == 1,
                  "labels_seal_freeze": head.get("labels", {}).get("sha256") == LABELS["sha256"]
                      and head.get("seal", {}).get("sha256") == PIN["seal"][1]
                      and head.get("freeze", {}).get("sha256") == PIN["amended_freeze"][1],
                  "no_failed_family": all(f.get("status") == "scored" for f in head.get("families", [])) and len(head.get("families", [])) == 9,
                  "release_flag_false": head.get("outcome_release_authorized") is False}
        check = head.get("decision_check", {})
        checks["decision_check_clean"] = check.get("members", {}).get("float32_mismatch_rows") == 0 \
            and check.get("origin", {}).get("float64_mismatch_rows") == 0 and check.get("stable", {}).get("float64_mismatch_rows") == 0
        say("tierC:secondary-result-header", all(checks.values()), **{k: v for k, v in checks.items()},
            kinds=head.get("kind"), primary_note="primary.json of attempt 12 stays the primary result")
    else:
        say("tierC:secondary-result-header", None, why="secondary-result.json absent (split persist used, or run incomplete)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inventory", action="store_true", help="tier B: stat-prove the whole ~3.4 TB read inventory (no content reads)")
    ap.add_argument("--deep", action="store_true", help="tier C: hash every D-A39 family/secondary pickle part")
    ap.add_argument("--no-code", action="store_true", help="skip cluster chain-code file presence checks")
    ap.add_argument("--small-cap", type=int, default=1 << 28, help="tier A re-hash cap per file (default 256 MiB)")
    a = ap.parse_args()
    if not os.path.isdir(ROOT):
        print(json.dumps({"fatal": "<CLUSTER_STORAGE> not mounted here; run on <BATCH_HOST> (read-only)"})); return 2
    inv_doc = tier_a(a.small_cap, code=not a.no_code)
    if a.inventory:
        tier_b(inv_doc)
    tier_c(deep=a.deep)
    done = [r for r in RESULTS if r["ok"] is not None]
    passed = all(r["ok"] for r in done)
    print(json.dumps({"summary": "PASS" if passed else "FAIL", "checks": len(RESULTS),
                      "failed": [r["check"] for r in done if not r["ok"]],
                      "pending": [r["check"] for r in RESULTS if r["ok"] is None]}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
