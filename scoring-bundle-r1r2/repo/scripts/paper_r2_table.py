#!/usr/bin/env python3
"""Write the paper's R2 tables from the reviewed facts projection of the accepted R2 report.

Input: the facts.json written by scripts/forecast_full_report_facts.py (for the amended, d60-only report: through
.agents/operations/agy-lanes-20261027/g2r2/chain/run_report_script.py --d60-only). Default input: the single file matching
docs/paper/newperiod-final-*/facts/facts.json.

Output (default directory paper/generated):
  newperiod-table.tex  one table* (label tab:r2): the twelve prespecified primary AP contrasts C1-C6 at 30 and 60 s
                       and, below a rule, the native-candidate whole-system family, with the outcome class of the
                       outcome-to-wording rule of paper/sections/04-forecast-protocol.tex (sec:newperiod-stats).
  newperiod-lanes.tex  one table (label tab:r2-lanes): retained roles and reported statuses of the five secondary lanes.
                       Written only when the facts hold at least one lane section; a stale copy is removed otherwise.

The script copies reported values. It computes only the half-width, (upper - lower) / 2, which the wording rule
defines, and it counts reported role statuses. It does not recompute estimates, intervals or p values. A Holm p value
whose raw p value equals the smallest value the bootstrap can give, 2 / (repetitions + 1), prints as "<= value".
The tables never print a hash, a path or an internal key. Any missing or inconsistent field stops the script with a
nonzero exit status and writes nothing.
"""
import argparse
import glob
import hashlib
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEMA = 'forecast_full_newperiod_report_facts_v1'
SCHEMAS = (SCHEMA, 'forecast_newperiod_primary_facts_v1')  # primary-only facts: r2_primary_facts.py (D-A39)
HORIZONS = (30, 60)
RESOLVED_HALF_WIDTH = 0.01  # sec:newperiod-stats, "Wording of each outcome"
HEADLINE = ('C2', 30)       # sec:forecast-newperiod, "Primary contrasts"

# Arm pairs mirror src/bgbench/forecast_custodian_eval.py PRIMARY_CONTRASTS and WHOLE_SYSTEM_CONTRASTS.
# The script refuses a report whose arms differ, so a changed evaluator cannot be printed under the old names.
PRIMARY = {
    'C1': (('sage_on', 'none_on'), 'SAGE vs.\\ no message passing, both with history'),
    'C2': (('sage_on', 'online_history'), 'SAGE with history vs.\\ online history'),
    'C3': (('sage_on', 'sage_off'), 'SAGE with vs.\\ without history'),
    'C4': (('none_on', 'none_off'), 'No message passing, with vs.\\ without history'),
    'C5': (('frozen_sage_on', 'online_history'), 'Frozen 2025 SAGE vs.\\ online history'),
    'C6': (('frozen_sage_on', 'sage_on'), 'Frozen 2025 SAGE vs.\\ refitted SAGE with history'),
}
NATIVE = {
    'C2-native': (('sage_on', 'online_history_native'), 'SAGE with history vs.\\ online history, native candidates'),
    'C5-native': (('frozen_sage_on', 'online_history_native'), 'Frozen 2025 SAGE vs.\\ online history, native candidates'),
}
REQUIRED_RESULT = ('contrast', 'left', 'right', 'horizon_seconds', 'difference', 'ci95', 'p_value', 'holm_p_value',
                   'holm_rejects', 'repetitions', 'training_seeds', 'events')
# The five secondary lanes of sec:newperiod-arms, in the order of app:np-arms, keyed by report section.
LANES = (('membership', 'h1', 'Candidate expansion'),
         ('membership', 'h3', 'Reduced collectors'),
         ('stable', None, 'Stable peers'),
         ('membership', 'timing', 'Timing'),
         ('origin', 'origin_change_invalid', 'Origin changes, invalid'),
         ('origin', 'origin_change_valid', 'Origin changes, valid'))
HEX_RUN = re.compile(r'[0-9a-fA-F]{16,}')


class Refusal(Exception):
    pass


def need(condition, message):
    if not condition:
        raise Refusal(message)


def number(value, name):
    need(type(value) in (int, float) and math.isfinite(value), f'{name}: finite number required, got {value!r}')
    return float(value)


def signed(value):
    text = f'{value:+.4f}'
    if float(text) == 0.0:
        text = f'{value:+.1e}' if value != 0 else '0.0000'
    return text.replace('-', '$-$')


def plain(value):
    return f'{value:.4f}'


def count(value):
    need(type(value) is int and value >= 0, f'count required, got {value!r}')
    return f'{value:,}'.replace(',', '{,}')


def outcome(rejects, difference, half_width):
    """Outcome class of the wording rule of sec:newperiod-stats."""
    resolved = half_width <= RESOLVED_HALF_WIDTH
    if rejects:
        text = 'first arm better' if difference > 0 else 'second arm better'
        return text if resolved else text + ', not resolved'
    return 'bounded, no rejection' if resolved else 'not resolved'


def load_facts(path, expected_sha256):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        need(digest == expected_sha256, 'facts file differs from --expected-facts-sha256')
    facts = json.loads(raw)
    need(isinstance(facts, dict) and facts.get('schema') in SCHEMAS, f'facts schema one of {SCHEMAS} required')
    need(facts.get('population') == 'new_period', 'new-period facts required')
    for key in ('primary_projection', 'report', 'source_report_sha256'):
        need(key in facts, f'facts lack {key}')
    return facts, digest


def family_rows(projection, family, spec):
    """Rows of one family in a fixed order, with not-available contrasts of the d60-only deviation."""
    comps = [c for c in projection['comparisons'] if c.get('family') == family]
    need(comps, f'family {family} missing')
    metadata = comps[0].get('family_metadata')
    need(isinstance(metadata, dict), f'{family}: family metadata missing')
    if comps[0].get('contrast_key') is None:
        need(metadata.get('status') == 'unavailable' and metadata.get('reason'), f'{family}: unavailable family needs a reason')
        return None, metadata
    for key in ('holm_family_size', 'family_wise_alpha', 'declares_primary_finding'):
        need(key in metadata, f'{family}: family metadata lacks {key}')
    analysis = projection.get('analysis_metadata', {})
    deviation = analysis.get('d60_only_deviation')
    missing = {}
    padded = False
    if deviation is not None:
        need(isinstance(deviation, dict) and isinstance(deviation.get('not_available'), dict)
             and type(deviation.get('holm_padded')) is bool, 'd60_only_deviation: not_available and holm_padded required')
        group = deviation['not_available'].get('whole_system' if family == 'whole_system_ap' else 'contrasts')
        need(isinstance(group, dict), f'd60_only_deviation lacks the group of {family}')
        missing = group
        padded = deviation['holm_padded']
    found = {c['contrast_key']: c['result'] for c in comps}
    need(not set(found) & set(missing), f'{family}: a contrast is both reported and not available')
    need(metadata['holm_family_size'] == len(found) + (len(missing) if padded else 0),
         f'{family}: Holm family size differs from reported plus placeholder contrasts')
    rows = []
    for cid, ((left, right), name) in spec.items():
        for horizon in HORIZONS:
            key = f'{cid}@{horizon}'
            need((key in found) != (key in missing), f'{family}: {key} must be reported or declared not available')
            if key in missing:
                entry = missing[key]
                need(isinstance(entry, dict) and entry.get('status') == 'not_available'
                     and (entry.get('left'), entry.get('right')) == (left, right)
                     and entry.get('horizon_seconds') == horizon, f'{family}: {key} not-available record differs')
                rows.append({'cid': cid, 'name': name, 'horizon': horizon, 'available': False, 'padded': padded})
                continue
            result = found[key]
            need(isinstance(result, dict), f'{family}: {key} result missing')
            for field in REQUIRED_RESULT:
                need(field in result, f'{family}: {key} lacks {field}')
            need(result['contrast'] == cid and result['horizon_seconds'] == horizon
                 and (result['left'], result['right']) == (left, right), f'{family}: {key} arms or horizon differ')
            ci = result['ci95']
            need(isinstance(ci, list) and len(ci) == 2, f'{family}: {key} ci95 must hold two ends')
            lo, hi = number(ci[0], key + ' lower'), number(ci[1], key + ' upper')
            need(lo <= hi, f'{family}: {key} interval ends out of order')
            difference = number(result['difference'], key + ' difference')
            p, holm = number(result['p_value'], key + ' p'), number(result['holm_p_value'], key + ' Holm p')
            need(0 < p <= 1 and 0 < holm <= 1 and holm >= p - 1e-12, f'{family}: {key} p values out of range')
            need(type(result['holm_rejects']) is bool, f'{family}: {key} holm_rejects must be boolean')
            alpha = number(metadata['family_wise_alpha'], family + ' alpha')
            need(result['holm_rejects'] == (holm <= alpha), f'{family}: {key} rejection differs from Holm p and alpha')
            reps = result['repetitions']
            need(type(reps) is int and reps > 0, f'{family}: {key} repetitions required')
            eligible = result.get('eligible_events', result['events'])
            rows.append({'cid': cid, 'name': name, 'horizon': horizon, 'available': True, 'difference': difference,
                         'lo': lo, 'hi': hi, 'half_width': (hi - lo) / 2, 'holm': holm,
                         'at_floor': math.isclose(p, 2 / (reps + 1), rel_tol=1e-9), 'rejects': result['holm_rejects'],
                         'eligible': eligible, 'seeds': result['training_seeds'], 'reps': reps})
    return rows, metadata


def primary_table(facts):
    projection = facts['primary_projection']
    need(projection.get('population') == 'new_period' and projection.get('confirmatory') is True,
         'confirmatory new-period primary projection required')
    primary, primary_meta = family_rows(projection, 'primary_ap', PRIMARY)
    need(primary is not None, 'primary_ap family unavailable')
    need(primary_meta['declares_primary_finding'] is True, 'primary_ap must be the declared primary family')
    native, native_meta = family_rows(projection, 'whole_system_ap', NATIVE)
    if native is not None:
        need(native_meta['declares_primary_finding'] is False, 'native-candidate family must not be primary')
    reps = {r['reps'] for r in (primary + (native or [])) if r['available']}
    need(len(reps) == 1, 'all contrasts must report the same number of bootstrap repetitions')
    (repetitions,) = reps
    alpha = number(primary_meta['family_wise_alpha'], 'alpha')
    seeds = {r['seeds'] for r in (primary + (native or [])) if r['available']}
    shared_seeds = next(iter(seeds)) if len(seeds) == 1 else None  # one value: state it in the caption, no column
    by_horizon = {}
    for r in primary + (native or []):
        if r['available']:
            by_horizon.setdefault(r['horizon'], set()).add(r['eligible'])
    # one eligible count per horizon: state it in the caption, no column
    shared_eligible = ({h: next(iter(v)) for h, v in sorted(by_horizon.items())}
                       if all(len(v) == 1 for v in by_horizon.values()) else None)
    columns = 7 + (shared_eligible is None) + (shared_seeds is None)
    spans = {}
    for r in primary + (native or []):
        spans[r['cid']] = spans.get(r['cid'], 0) + 1

    def line(row, first):
        label = f'\\textbf{{{row["cid"]}}}' if row['cid'] == HEADLINE[0] else row['cid']
        # the contrast name spans the rows of its horizons, so a two-line name adds no line
        name = f'{label}: {row["name"]}'
        head = ((f'\\multirow[t]{{{spans[row["cid"]]}}}{{=}}{{{name}}}' if spans[row['cid']] > 1 else name) if first else '')
        head += f' & {row["horizon"]}'
        if not row['available']:
            note = 'no estimate, $p=1$ in Holm' if row['padded'] else 'no estimate'
            return head + f' & \\multicolumn{{{columns - 3}}}{{c}}{{--}} & ' + note + ' \\\\\n'
        holm = plain(row['holm'])
        holm = ('$\\leq$\\,' + holm) if row['at_floor'] else holm
        return (head + f' & {signed(row["difference"])} & [{signed(row["lo"])}, {signed(row["hi"])}]'
                f' & {plain(row["half_width"])} & {holm}' + ('' if shared_eligible is not None else f' & {count(row["eligible"])}')
                + ('' if shared_seeds is not None else f' & {count(row["seeds"])}') +
                f' & {outcome(row["rejects"], row["difference"], row["half_width"])} \\\\\n')

    body = []
    for rows in (primary, native):
        if rows is None:
            continue
        if body:
            size = native_meta['holm_family_size']
            body.append(f'\\midrule\n\\multicolumn{{{columns}}}{{@{{}}l}}{{Native-candidate whole-system family, '
                        f'separate Holm family of {size}}} \\\\\n')
        previous = None
        for row in rows:
            body.append(line(row, row['cid'] != previous))
            previous = row['cid']
    if native is None:
        body.append(f'\\midrule\n\\multicolumn{{{columns}}}{{@{{}}l}}{{Native-candidate whole-system family: not reported by the evaluation}} \\\\\n')
    size = primary_meta['holm_family_size']
    caption = (
        'R2 average-precision contrasts. Upper rows: the prespecified primary family, C1 to C6 at 30 and 60\\,s, '
        f'one Holm family of {size} at family-wise level {alpha:g}. '
        'Each difference is the first arm minus the second. '
        f'Intervals are paired 95\\,\\% percentile intervals over training seeds and UTC-day blocks ({count(repetitions)} repetitions). '
        + (f'All contrasts use {count(shared_seeds)} training seeds. ' if shared_seeds is not None else '')
        + ('Eligible events: ' + ' and '.join(f'{count(n)} at {h}\\,s' for h, n in shared_eligible.items()) + '. '
           if shared_eligible is not None else '') +
        'The intervals are ordinary, not simultaneous and not adjusted for the twelve tests, and the Holm $p$ decides each rejection. '
        'For the bounded C2 cells, \\Cref{tab:actor-bootstrap} also resamples leakers. '
        'The half-width is half the interval length, and a contrast is resolved if it is at most 0.01\\,AP. '
        'The outcome follows the wording rule of \\Cref{sec:forecast-newperiod}. '
        '$\\leq$ marks a Holm $p$ at the smallest value the bootstrap can give. '
        'C2 at 30\\,s is the headline contrast.')
    table = ('% Generated by scripts/paper_r2_table.py from the facts projection of the accepted R2 report; do not edit by hand.\n'
             '\\begin{table*}[t]\n\\centering\\small\n'
             '\\caption{' + caption + '}\n\\label{tab:r2}\n'
             '\\setlength{\\tabcolsep}{2.5pt}\n'
             '\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{' + ('0.36' if shared_eligible is not None else '0.26') + '\\textwidth}'
             + 'r' * (columns - 2) + '>{\\raggedright\\arraybackslash}p{' + ('0.21' if shared_eligible is not None else '0.16')
             + '\\textwidth}@{}}\n'
             '\\toprule\n'
             'Contrast: first arm vs.\\ second arm & \\hd{Horizon\\\\(s)} & \\hd{AP\\\\difference} & 95\\,\\% interval'
             ' & \\hd{Half-\\\\width} & Holm $p$' + ('' if shared_eligible is not None else ' & \\hd{Eligible\\\\events}')
             + ('' if shared_seeds is not None else ' & Seeds')
             + ' & Outcome \\\\\n'
             '\\midrule\n' + ''.join(body) + '\\bottomrule\n\\end{tabular}\n\\end{table*}\n')
    return table


def lanes_table(facts):
    report = facts['report']
    rows = []
    for section, key, name in LANES:
        part = report.get(section)
        if part is None:
            continue
        if section == 'origin':
            part = part.get('families', {}).get(key)
        elif key is not None:
            part = part.get(key)
        if part is None:
            continue
        cells = part.get('cells')
        need(isinstance(cells, dict) and cells, f'lane {name}: cells required')
        statuses = [c.get('status') for c in cells.values()]
        need(all(isinstance(s, str) for s in statuses), f'lane {name}: every role needs a status')
        need(type(part.get('declares_primary_finding')) is bool and part['declares_primary_finding'] is False,
             f'lane {name}: lane must not declare a primary finding')
        contrasts = part.get('contrasts', [])
        need(isinstance(contrasts, list), f'lane {name}: contrasts must be a list')
        tests = part.get('formal_tests')
        need(tests is None or type(tests) is bool, f'lane {name}: formal_tests must be boolean when present')
        scored = sum(s == 'scored' for s in statuses)
        rows.append(f'{name} & {count(len(cells))} & {count(scored)} & {count(len(cells) - scored)}'
                    f' & {count(len(contrasts))} & {"yes" if tests else "no"} \\\\\n')
    if not rows:
        return None
    caption = ('Secondary lanes of R2: retained roles, roles with a score, roles without one (failed or not estimable) and '
               'the descriptive paired contrasts that each lane reports. The lanes carry no formal tests and cannot '
               'change the primary result (\\Cref{sec:forecast-newperiod}).')
    return ('% Generated by scripts/paper_r2_table.py from the facts projection of the accepted R2 report; do not edit by hand.\n'
            '\\begin{table}[t]\n\\centering\\small\n\\caption{' + caption + '}\n\\label{tab:r2-lanes}\n'
            '\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{@{}lrrrrl@{}}\n\\toprule\n'
            'Lane & Roles & Scored & \\hd{Not\\\\scored} & Contrasts & Tests \\\\\n\\midrule\n'
            + ''.join(rows) + '\\bottomrule\n\\end{tabular}\n\\end{table}\n')


def default_facts():
    hits = sorted(glob.glob(str(REPO / 'docs/paper/newperiod-final-*/facts/facts.json')))
    need(len(hits) == 1, f'exactly one docs/paper/newperiod-final-*/facts/facts.json required, found {len(hits)}; pass the path')
    return Path(hits[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('facts', nargs='?', type=Path, help='facts.json of the accepted R2 report')
    parser.add_argument('--out-dir', type=Path, default=REPO / 'paper/generated')
    parser.add_argument('--expected-facts-sha256', default=None)
    args = parser.parse_args(argv)
    try:
        path = args.facts if args.facts is not None else default_facts()
        need(path.is_file(), f'facts file not found: {path}')
        facts, digest = load_facts(path, args.expected_facts_sha256)
        outputs = {'newperiod-table.tex': primary_table(facts), 'newperiod-lanes.tex': lanes_table(facts)}
        for name, text in outputs.items():
            printed = '' if text is None else '\n'.join(l for l in text.splitlines() if not l.startswith('%'))
            need(not HEX_RUN.search(printed), f'{name}: refusing to print a hash-like string')
            need('_' not in printed, f'{name}: refusing to print an internal key')
    except (Refusal, KeyError, TypeError, ValueError) as error:
        print(f'paper_r2_table.py: refused: {error}', file=sys.stderr)
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in outputs.items():
        target = args.out_dir / name
        if text is None:
            target.unlink(missing_ok=True)
            continue
        target.write_text(text)
    print(json.dumps({'facts_sha256': digest, 'written': sorted(n for n, t in outputs.items() if t is not None)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
