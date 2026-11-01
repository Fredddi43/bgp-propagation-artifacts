"""Primary-only facts projection of the R2 primary report (deviation D-A39).

Job 52700052 (attempt 12) opened the labels once, wrote the confirmatory primary report (arms/000/attempt/primary.json),
and then failed while scoring the secondary lanes, so no complete report exists. This projects ONLY the primary report
with the reviewed projection (bgbench.forecast_release_facts.collect, with the d60-only patches of D-A22), exactly as
forecast_full_report_facts.collect projects report['primary']. It computes nothing new.

usage: r2_primary_facts.py <primary.json> <out_dir> --expected-report-sha256 <sha>"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402,F401  (puts <repo>/src on sys.path)
import d60_only  # noqa: E402
from bgbench import forecast_full_report_facts, forecast_release_facts  # noqa: E402

SCHEMA = 'forecast_newperiod_primary_facts_v1'


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    parser.add_argument('out_dir', type=Path)
    parser.add_argument('--expected-report-sha256', required=True)
    args = parser.parse_args(argv)
    d60_only.install_report_facts(forecast_full_report_facts, forecast_release_facts)
    raw = args.report.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != args.expected_report_sha256:
        raise SystemExit('primary report differs from the expected hash')
    report = json.loads(raw)
    canonical = forecast_full_report_facts.canonical(report)
    projected = forecast_release_facts.collect(canonical, hashlib.sha256(canonical).hexdigest())
    if projected.get('population') != 'new_period' or projected.get('confirmatory') is not True:
        raise SystemExit('confirmatory new-period primary report required')
    facts = {'schema': SCHEMA, 'source_report_sha256': digest, 'population': 'new_period',
             'primary_projection': projected, 'primary_canonical_sha256': hashlib.sha256(canonical).hexdigest(),
             'report': {}, 'secondary_status': 'not in this report: secondary lanes failed after the label opening (D-A39)',
             'numerical_verification_performed': False,
             'status': 'source_projection_only_pending_independent_numerical_verification'}
    args.out_dir.mkdir(parents=True, exist_ok=False)
    out = args.out_dir / 'facts.json'
    out.write_text(json.dumps(facts, sort_keys=True, indent=1, allow_nan=False) + '\n')
    print(out, hashlib.sha256(out.read_bytes()).hexdigest())


if __name__ == '__main__':
    main(sys.argv[1:])
