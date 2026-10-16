"""Gate public target export on independent final graph/raw-source checks.

This intentionally verifies only the model contract. The combined release gate
separately checks event tables, recovery pairs, frontiers and nongraph outputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    args=parser.parse_args()
    run=args.run
    while not all((run/name).is_file() for name in ("graph-final-models-complete.json", "crossday-source-complete.json")):
        time.sleep(10)
    from verify_corrected_release import verify
    contract=run/"graph-final-build/expected-verification.json"
    expected=json.loads(contract.read_text())
    completion=json.loads((run/"graph-final-models-complete.json").read_text())
    model_root=Path(completion.get("data_root","graph-final-data"))
    assert not model_root.is_absolute() and ".." not in model_root.parts
    result=verify(run/"data",expected,run/model_root)
    omissions=[item for item in result["failures"] if item["kind"]=="empty_required_manifest_category" and item["category"] in {"event_tables","pair_tables"}]
    result["failures"]=[item for item in result["failures"] if item not in omissions]
    result["omitted_categories"]=omissions
    result["scope"]="Declared final model arithmetic, exact cohorts and full targets from original raw membership contracts; not combined release sign-off"
    report=run/"graph-full-target-verification.json"
    report.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"models":len(result["model_tables"]),"failures":len(result["failures"])}),flush=True)
    if result["failures"]:
        raise SystemExit(1)
    marker={"models":len(result["model_tables"]),"report":"graph-full-target-verification.json",
            "report_sha256":hashlib.sha256(report.read_bytes()).hexdigest(),
            "manifest_sha256":hashlib.sha256(contract.read_bytes()).hexdigest()}
    pending=run/"graph-raw-targets-verified.pending.json"
    pending.write_text(json.dumps(marker,indent=2)+"\n")
    pending.replace(run/"graph-raw-targets-verified.json")


if __name__=="__main__":
    main()
