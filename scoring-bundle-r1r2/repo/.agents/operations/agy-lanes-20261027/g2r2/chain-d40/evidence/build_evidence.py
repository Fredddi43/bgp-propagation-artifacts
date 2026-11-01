"""Label-free evidence documents for the PINNED single-R2 persistence runner (membership x5, stable, origin, baseline).

Every value is derived from frozen/accepted metadata (freeze arms, manifests' event ids, masters, the G4 plan's source refs,
the frozen slice-rule and issue-time tables, H3 availability ledgers). Nothing here reads a label, a prediction or a model.
Two things are NOT derivable from the protocol and are required inputs (see DECISIONS-NEEDED item 8): the timing
label-horizon map for 5/10/300/900 s. Comparators are never chosen: the roles grid fixes the comparator KEYS
(membership consumer `comparator_key`, `roles`) and each key must match exactly one retained global arm (else this refuses).
"""
import copy
import json
import sys
import types
from pathlib import Path

CHAIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CHAIN))
from common import REPO, sha  # noqa: E402

PERSIST = REPO / ".agents/operations/newperiod-single-r2-persistence-20261024/runner.py"
HORIZONS = ("30", "60")
TIMING_HORIZONS = ("5", "10", "30", "60", "300", "900")
FAMILIES = ("h1", "h3", "timing", "history", "ordinary")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def ref(path):
    return {"path": str(path), "sha256": sha(path)}


def strip(r):
    return {"path": r["path"], "sha256": r["sha256"]}


def doc(r):
    p = Path(r["path"])
    need(sha(p) == r["sha256"], f"{p} differs from its reference")
    return json.loads(p.read_bytes())


def membership_module():
    """The hash-pinned membership consumer of the persistence package (roles grid, REFERENCE, comparator_key)."""
    m = types.ModuleType("r2_persistence_runner_for_evidence")
    m.__file__ = str(PERSIST)
    exec(compile(PERSIST.read_bytes(), str(PERSIST), "exec"), m.__dict__)
    return m.components()["composition"].components()["membership"]


class Context:
    """freeze: global freeze.json path; groups: {group: <group>.json path}; plan: G4 plan json (source refs)."""

    def __init__(self, freeze, groups, g4_plan=None, h3_availability=None, timing_label_map=None, h1_slice_decisions=None):
        self.freeze_ref = ref(freeze)
        self.freeze = json.loads(Path(freeze).read_bytes())
        self.groups = {g: json.loads(Path(p).read_bytes()) for g, p in groups.items()}
        self.group_refs = {g: ref(p) for g, p in groups.items()}
        self.plan = json.loads(Path(g4_plan).read_bytes()) if g4_plan else None
        self.h3_availability = h3_availability
        self.timing_label_map = timing_label_map
        self.h1_slice_decisions = h1_slice_decisions   # only for G1 arms that lack slice_decisions (never in production)
        self.M = membership_module()
        self.global_arms = {a["arm_id"]: a for a in self.freeze["arms"] + self.freeze.get("retained_failures", [])}
        need(len(self.global_arms) == len(self.freeze["arms"]) + len(self.freeze.get("retained_failures", [])), "duplicate global arm ids")

    def lineage(self, optional=False):
        """pooled_target_lineage from the G4 plan's ordinary subplan (masters, source inventories, collector inventory, recipe)."""
        if self.plan is None:
            need(optional, "pooled_target_lineage needs the G4 plan (manifests use the pooled selector)")
            return None
        sub = self.plan["base"]["ordinary"]
        return {"masters": {h: strip(v) for h, v in sub["masters"].items()},
                "source_inventories": {h: strip(v) for h, v in sub["source_inventories"].items()},
                "collector_inventory": strip(sub["collector_inventory"]), "recipe": strip(sub["recipe"])}

    def pooled(self, arms):
        sel = {json.dumps(doc({"path": a["manifest_path"], "sha256": a["manifest_sha256"]}).get("reference_collectors")) for a in arms
               if a.get("status") == "committed_for_prediction"}
        return any(s == json.dumps("pooled") for s in sel), sel


def cohort_ids(arms, horizons, *, one_cohort=False):
    ids = {}
    for h in horizons:
        group = [a for a in arms if str(a["role"]["horizon_seconds"]) == h and a.get("status") == "committed_for_prediction"]
        need(group, f"no committed arm at horizon {h} to take the cohort from")
        sets = {tuple(a["event_ids"]) for a in group}
        need(len(sets) == 1, f"arms at horizon {h} disagree on their event ids")
        ids[h] = sorted(set(group[0]["event_ids"]))
        need(len(ids[h]) == len(group[0]["event_ids"]), f"duplicate event ids at horizon {h}")
    if one_cohort:
        need(len({tuple(v) for v in ids.values()}) == 1, "timing needs one cohort across all horizons")
    return ids


def comparator_ids(ctx, family):
    """Names of the fixed primary comparator arms: one retained global arm per required comparator key, predicates as in the consumer."""
    M = ctx.M
    out = []
    for key in sorted({M.comparator_key(r) for r in M.roles(family)}, key=repr):
        found = []
        for a in ctx.global_arms.values():
            role = a["role"]
            try:
                same = M.comparator_key(role) == key
            except KeyError:        # role has no message_passing/seed: not a comparator candidate
                continue
            if not same or role.get("variant") not in (None, "core") or role.get("panel") != "reference":
                continue
            if role.get("family") == "baseline":
                ok = role.get("baseline") == "history-knn-mean" and role.get("library") == "online"
            else:
                ok = role.get("family") == "neural" and role.get("training") == "updated" and role.get("history") == "on"
            if ok:
                found.append(a["arm_id"])
        need(len(found) == 1, f"comparator key {key} matches {len(found)} retained arms {found}: AMBIGUOUS, not chosen")
        out.append(found[0])
    return out


def membership_evidence(ctx, family):
    M = ctx.M
    freeze = ctx.groups[family]
    arms = freeze["arms"]
    roles = {M.key(r) for r in M.roles(family)}
    need(len(arms) == len(roles) and {M.key(a["role"]) for a in arms} == roles, f"{family}: frozen family grid differs from the pinned roles grid")
    horizons = sorted({str(r["horizon_seconds"]) for r in M.roles(family)}, key=int)
    ev = {"input_only": True, "target_scope": {"panel": "reference", "kind": "full_reference_membership", "collectors": list(M.REFERENCE)},
          "cohort_ids": cohort_ids(arms, horizons, one_cohort=family == "timing")}
    if family == "timing":
        mapping = ctx.timing_label_map
        need(mapping is not None and set(mapping) == set(horizons) and all(v in HORIZONS for v in mapping.values()),
             "timing label-horizon map is REQUIRED (protocol leaves it open: DECISIONS-NEEDED item 8)")
        ev["label_horizon"] = {h: mapping[h] for h in horizons}
    else:
        ev["label_horizon"] = {h: h for h in horizons}      # label table is keyed by the cell's own horizon (baseline consumer pins {'30':'30','60':'60'})
    ev["comparator_arm_ids"] = [] if family in ("timing", "ordinary") else comparator_ids(ctx, family)
    pooled, selectors = ctx.pooled(arms)
    # The membership consumer also runs check_target_selector on every primary COMPARATOR arm; the comparators come from the pooled-selector
    # primary family, so the evidence must carry the pooled lineage when any comparator manifest is pooled, even if the family's own arms
    # use the explicit reference panel (found in R2 attempt 9: "Exact bound pooled target lineage required" at the h1 comparators).
    comparators = [ctx.global_arms[name] for name in ev["comparator_arm_ids"] if name in ctx.global_arms]
    comparator_pooled, _ = ctx.pooled(comparators)
    if pooled or comparator_pooled:
        ev["pooled_target_lineage"] = ctx.lineage()
        selectors = {s for s in selectors if s != json.dumps("pooled")} if comparator_pooled and not pooled else selectors
    else:
        need(all(s == json.dumps(list(M.REFERENCE)) for s in selectors) or not selectors, f"{family}: unexpected reference_collectors selector {selectors}")
    if family == "h1":
        sd = lambda a: a.get("slice_decisions") or ctx.h1_slice_decisions
        probe = sd(next(a for a in arms if a.get("status") == "committed_for_prediction"))
        need(probe is not None, "h1 arms carry no slice_decisions")
        for a in arms:
            if a.get("status") == "committed_for_prediction":
                need(sd(a)["slice_rules"] == probe["slice_rules"] and sd(a)["issue_time_tables"] == probe["issue_time_tables"],
                     "h1 arms carry different slice/issue-time refs")
        rules = doc(probe["slice_rules"])["horizons"]
        ev["slice_rules"] = {h: rules[h] for h in HORIZONS}
        ev["issue_time"] = {}
        for h in HORIZONS:
            table = doc(probe["issue_time_tables"][h])
            need(table.get("input_only") is True, "issue-time table must be input-only")
            ev["issue_time"][h] = table["events"]
    if family == "h3":
        need(ctx.h3_availability is not None, "h3 availability ledgers (per horizon and view) are required")
        ev["availability"], ev["reference_seeds"] = {}, {}
        for h in HORIZONS:
            views = {}
            for view in ("reference", "ris7", "mixed7"):
                rows = doc(ctx.h3_availability[h][view])["rows"]
                need(sorted(r["event_id"] for r in rows) == ev["cohort_ids"][h], f"h3 {view}@{h} availability does not cover the cohort exactly")
                views[view] = {r["event_id"]: {"status": r["status"], "partial_panel_input": bool(r["partial_panel_input"])} for r in rows}
                if view == "reference":
                    ev["reference_seeds"][h] = {r["event_id"]: sorted(r["input_seed_asns"]) for r in rows}
            ev["availability"][h] = views
    return ev


def stable_evidence(ctx):
    base = ctx.plan["base"]
    return {"input_only": True, "masters": {h: strip(v) for h, v in base["stable"]["masters"].items()},
            "primary_masters": {h: strip(v) for h, v in base["ordinary"]["masters"].items()}, "stable_source": strip(base["stable_source"])}


def origin_evidence(ctx):
    e = ctx.plan["origin_evidence"]
    need(e.get("input_only") is True, "origin evidence must be input-only")
    return {"input_only": True, "masters": {f: {h: strip(v) for h, v in hs.items()} for f, hs in e["masters"].items()},
            "metadata_projection": strip(e["metadata_projection"]), "sampling_rule": strip(e["sampling_rule"]),
            "source_review": strip(e["source_review"])}


def baseline_evidence(ctx):
    M = ctx.M
    arms = ctx.groups["baseline"]["arms"]
    return {"input_only": True, "target_scope": {"panel": "reference", "kind": "full_reference_membership", "collectors": list(M.REFERENCE)},
            "cohort_ids": cohort_ids(arms, HORIZONS), "label_horizon": {"30": "30", "60": "60"}, "pooled_target_lineage": ctx.lineage()}


def build_all(ctx, out):
    """Write every evidence document exclusively into `out`; return the refs for r2_plan.build_template controls."""
    out = Path(out)
    out.mkdir(parents=True)
    refs = {"evidence": {}}

    def write(name, value):
        path = out / name
        with path.open("x") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        return ref(path)

    for family in FAMILIES:
        refs["evidence"][family] = write(f"evidence-{family}.json", membership_evidence(ctx, family))
    refs["stable_evidence"] = write("evidence-stable.json", stable_evidence(ctx))
    refs["origin_evidence"] = write("evidence-origin.json", origin_evidence(ctx))
    refs["baseline_evidence"] = write("evidence-baseline.json", baseline_evidence(ctx))
    return refs


def timing_label_equivalence(ctx):
    """Label-free check that the open timing label-horizon choice cannot change the truth: do the d30 and d60 target masters name the
    same onset, incident and per-event custodian label files for every timing-cohort event? (Reads master metadata only.)"""
    ids = cohort_ids(ctx.groups["timing"]["arms"], ("30",))["30"]
    masters = {h: doc(v) for h, v in ctx.lineage()["masters"].items()}
    rows = {h: {r["event_id"]: r for r in m["events"]} for h, m in masters.items()}
    missing = [e for e in ids if e not in rows["30"] or e not in rows["60"]]
    differing = [e for e in ids if e not in missing and any(rows["30"][e].get(k) != rows["60"][e].get(k)
                                                            for k in ("onset", "incident_id", "custodian_label_files"))]
    return {"timing_cohort_events": len(ids), "missing_in_a_master": missing, "differing": differing,
            "equivalent": not missing and not differing}
