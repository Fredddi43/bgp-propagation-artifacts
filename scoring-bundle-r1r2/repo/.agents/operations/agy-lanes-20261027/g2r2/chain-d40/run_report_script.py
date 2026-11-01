#!/usr/bin/env python3
"""Run scripts/forecast_full_report_facts.py or scripts/forecast_report_latex.py (row 24) with the d60-only report-facts patches.

usage: run_report_script.py [--d60-only] <script basename> <script args...>
Without --d60-only the script runs exactly as `python scripts/<name> <args>` (nothing patched). With it, d60_only.install_report_facts
is installed on the bgbench modules the script imports (51 instead of 56 primary identities; Holm family size = contrasts + declared
placeholders) and the unmodified repo script then runs in this process. Pinned/published files are not edited."""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402  (puts <repo>/src and <repo>/scripts on sys.path)
import d60_only  # noqa: E402

ALLOWED = ("forecast_full_report_facts.py", "forecast_report_latex.py")


def main(argv):
    d60 = bool(argv) and argv[0] == "--d60-only"
    argv = argv[1:] if d60 else argv
    if not argv or argv[0] not in ALLOWED:
        raise SystemExit(f"usage: run_report_script.py [--d60-only] {{{'|'.join(ALLOWED)}}} <args>")
    if d60:
        from bgbench import forecast_full_report_facts, forecast_release_facts
        d60_only.install_report_facts(forecast_full_report_facts, forecast_release_facts)
    script = common.REPO / "scripts" / argv[0]
    sys.argv = [str(script), *argv[1:]]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main(sys.argv[1:])
