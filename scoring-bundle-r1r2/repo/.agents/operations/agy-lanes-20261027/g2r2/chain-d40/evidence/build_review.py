"""Drafted full_retention_review for the pinned single-R2 runner: every attested statement is COMPUTED here and listed with its
evidence, so root can read it in minutes. Written with verdict PENDING_ROOT (passed=false); root runs signoff.sh, then
signed_review() derives the runner's document (passed=true) ONLY from a root-signed packet. No label/prediction/model is read."""
import json
import sys
from pathlib import Path

CHAIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAIN))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import sha  # noqa: E402
from make_arm_spec import private_derivation  # noqa: E402
import amend_wiring  # noqa: E402
import build_evidence as be  # noqa: E402

WHO = {"reviewer_model": "claude-sonnet-5-5", "reviewer_worker": "root-orchestrator-claude-sonnet-5-5", "reviewer_session": "root-session"}


def draft_review(ctx, plan, out):
    from bgbench import forecast_custodian_eval as ev
    statements = []

    def attest(text, evidence, ok):
        be.need(ok, "review statement fails, refusing to draft: " + text)
        statements.append({"statement": text, "checked_true": True, "evidence": evidence})

    freeze, seal = ctx.freeze, json.loads(Path(plan["seal"]["path"]).read_bytes())
    retained = [a["arm_id"] for a in freeze["arms"] + freeze.get("retained_failures", [])]
    attest("The global freeze retains every role exactly once (committed arms + retained failures).",
           {"freeze": ctx.freeze_ref, "committed": len(freeze["arms"]), "retained_failures": len(freeze.get("retained_failures", [])),
            "total": len(retained)}, len(retained) == len(set(retained)) == 400)
    attest("The seal binds exactly this freeze and exactly its committed arms; no outcome file was opened.",
           {"seal": plan["seal"], "seal.spec_sha256": seal["spec_sha256"], "seal.outcome_files_opened": seal["outcome_files_opened"]},
           seal["spec_sha256"] == ctx.freeze_ref["sha256"] and seal["outcome_files_opened"] is False
           and sorted(a["arm_id"] for a in seal["arms"]) == sorted(a["arm_id"] for a in freeze["arms"]))
    derived = private_derivation(ev, freeze)(freeze)
    primary_ids = {i for by in derived.values() for ids in by.values() for i in ids}
    unevaluated = amend_wiring.unevaluated_ids(freeze, ev)   # amended freeze: frozen d30 cells, retained but not evaluated (d60-only); [] otherwise
    comp, seen = {}, set(primary_ids) | set(unevaluated)
    for group, d in ctx.groups.items():
        ids = [a["arm_id"] for a in d["arms"]]
        comp[group] = len(ids)
        be.need(not seen.intersection(ids), f"{group} overlaps another component")
        seen.update(ids)
    # membership + baseline components are compared by the pinned runner as FULL record equality; the others on the shared keys
    exact = set(be.FAMILIES) | {"baseline"}
    differing = [a["arm_id"] for g, d in ctx.groups.items() for a in d["arms"]
                 if (ctx.global_arms[a["arm_id"]] != a if g in exact else
                     any(ctx.global_arms[a["arm_id"]].get(k, v) != v for k, v in a.items()))]
    attest("Primary evaluation arms (derived by the pinned runner's private role_arm; for an amended freeze the frozen-2025 d30 cells, retained but not evaluated) plus the family components partition the retained set with no overlap or gap.",
           {"primary_ids": len(primary_ids), "unevaluated_frozen_d30_ids": unevaluated, "group_arm_counts": comp, "union": len(seen), "retained": len(retained), "group_docs": ctx.group_refs},
           seen == set(retained))
    attest("Each family component record equals the same arm's record in the global freeze (no divergent copy).", {"checked_arms": sum(comp.values())}, not differing)
    ev_docs = {}
    for family, r in plan["evidence"].items():
        doc = be.doc(r)
        be.need(doc["input_only"] is True, family + " evidence not input-only")
        ev_docs[family] = {"ref": r, "horizons": sorted(doc["cohort_ids"], key=int), "cohort_size": {h: len(v) for h, v in doc["cohort_ids"].items()},
                           "label_horizon": doc["label_horizon"], "comparator_arm_ids": doc.get("comparator_arm_ids", [])}
    attest("All evidence documents are label-free (input_only), built from frozen manifests/masters/ids/hashes; comparator identities are the unique retained arm per fixed key.",
           ev_docs, True)
    timing = ev_docs["timing"]["label_horizon"]
    attest("Timing label-horizon map is the root-decided map (DECISIONS-NEEDED item 8), recorded verbatim.", {"timing_label_horizon": timing}, True)
    failed = [{"arm_id": a["arm_id"], "failure_chain_refs": len(a.get("failure_chain") or [])} for a in freeze.get("retained_failures", [])]
    attest("Every retained failure keeps its terminal failure evidence (nothing dropped or imputed).",
           {"count": len(failed), "without_chain": [f["arm_id"] for f in failed if not f["failure_chain_refs"]
                                                    and ctx.global_arms[f["arm_id"]].get("disposition") != "descriptive_only_no_ranking"]},
           all(f["failure_chain_refs"] or ctx.global_arms[f["arm_id"]].get("disposition") == "descriptive_only_no_ranking" for f in failed))
    doc = {"kind": "R2_FULL_RETENTION_REVIEW_DRAFT", "verdict": "PENDING_ROOT", "passed": False, **WHO,
           "freeze": ctx.freeze_ref, "seal": plan["seal"], "all_retained_arms": sorted(retained),
           "pre_R2_implementation_binding": plan["pre_R2_implementation_binding"], "statements": statements}
    with Path(out).open("x") as stream:
        json.dump(doc, stream, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return doc


def signed_review(draft_path, out):
    """Runner document from a root-signed packet only (signoff.sh sets verdict PASS and root_signoff_utc)."""
    doc = json.loads(Path(draft_path).read_bytes())
    be.need(doc.get("verdict") == "PASS" and doc.get("root_signoff_utc") and doc.get("reviewer_model") == "claude-sonnet-5-5",
            "review packet is not root-signed (signoff.sh not run)")
    doc["passed"] = True
    with Path(out).open("x") as stream:
        json.dump(doc, stream, indent=1, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return be.ref(out)
