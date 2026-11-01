#!/usr/bin/env python3
"""Build every R2 evidence document, the timing equivalence report and the DRAFT full_retention_review (PENDING_ROOT).

controls.json: {"freeze": path, "groups": {count,h1,h3,history,ordinary,stable,origin,baseline,timing: <group>.json path},
 "g4_plan": path, "h3_availability": {"30": {reference,ris7,mixed7: ref}, "60": {...}},
 "timing_label_map": {"5":"30",...} (root decision, DECISIONS item 8), "seal": ref, "pre_R2_implementation_binding": ref,
 "plan_refs": optional extra refs, "out": fresh dir}
Prints the refs for r2_plan.build_template (evidence, stable_evidence, origin_evidence, baseline_evidence, review draft path)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_evidence as be  # noqa: E402
import build_review as br  # noqa: E402


def main(path):
    c = json.loads(Path(path).read_bytes())
    ctx = be.Context(Path(c["freeze"]), {g: Path(p) for g, p in c["groups"].items()}, g4_plan=c["g4_plan"],
                     h3_availability=c["h3_availability"], timing_label_map=c.get("timing_label_map"))
    out = Path(c["out"])
    refs = be.build_all(ctx, out)
    report = be.timing_label_equivalence(ctx)
    (out / "timing-label-equivalence.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    plan = dict(refs, seal=c["seal"], pre_R2_implementation_binding=c["pre_R2_implementation_binding"])
    br.draft_review(ctx, plan, out / "full-retention-review.DRAFT.json")
    print(json.dumps(dict(refs, review_draft=str(out / "full-retention-review.DRAFT.json"), timing_equivalence=report), indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
