"""Fixed LaTeX views of approved full-N facts. No scientific aggregation."""
import hashlib
import json
import math
from . import forecast_full_report_facts as facts_api


def escape(value):
    """Render untrusted text literally, allowing breaks in long source identifiers."""
    mapping = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
               '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
               '^': r'\textasciicircum{}'}
    out = []
    for i, char in enumerate(str(value)):
        if not 32 <= ord(char) <= 126:
            out.append(r'\texttt{U+' + f'{ord(char):04X}' + '}')
        else:
            out.append(mapping.get(char, char))
        if char in '_/-' or (i + 1) % 6 == 0:
            out.append(r'\allowbreak{}')
    return ''.join(out)


def display(value):
    if value is None:
        return 'not reported'
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('Nonfinite display value')
        text = format(value, '.4f')
        # A nonzero estimate or p value must never look like an observed zero.
        return format(value, '.3e') if value != 0 and float(text) == 0 else text
    if isinstance(value, list) and all(v is None or type(v) in (float, int) for v in value):
        return '[' + ', '.join(display(v) for v in value) + ']'
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return str(value)


def render(facts):
    if facts.get('schema') != 'forecast_full_newperiod_report_facts_v1':
        raise ValueError('Reviewed full-N facts required')
    raw = facts_api.canonical(facts['report'])
    checked = facts_api.collect(raw, hashlib.sha256(raw).hexdigest())
    for key in ('records', 'primary_projection', 'retained_identity_count'):
        if facts[key] != checked[key]:
            raise ValueError('Facts projection differs: ' + key)
    digest = facts['source_report_sha256']
    if not facts_api.primary_facts.SHA256.fullmatch(digest):
        raise ValueError('External report identity required')
    report = facts['report']
    provenance = []

    def value(pointer):
        return facts_api.resolve(report, pointer)

    def row(table, identity, fields):
        values = []
        sources = {}
        for label, pointer in fields:
            v = value(pointer) if pointer is not None else None
            values.append(escape(display(v)))
            sources[label] = {'source_pointer': pointer, 'value': v,
                              'display': display(v), 'missing_field': pointer is None}
        provenance.append({'table': table, 'identity': identity, 'source_report_sha256': digest,
                           'fields': sources})
        return ' & '.join(values) + r' \\' + '\n'

    def field(pointer, name):
        return pointer + facts_api.primary_facts.pointer(name) if name in value(pointer) else None

    def table(name, heading, columns, widths, rows, *, wide=False):
        spec = '@{}' + ''.join(r'>{\raggedright\arraybackslash}p{' + w + r'\linewidth}' for w in widths) + '@{}'
        header = '\\toprule\n' + ' & '.join(escape(c) for c in columns) + r' \\' + '\n\\midrule'
        body = ''.join(rows) + '\\bottomrule\n'
        if wide:
            return ('\\begin{table*}[t]\n\\centering\n\\small\n\\setlength{\\tabcolsep}{2pt}\n'
                    + '\\caption{' + escape(heading) + '}\n\\begin{tabular}{' + spec + '}\n'
                    + header + '\n' + body + '\\end{tabular}\n\\end{table*}\n')
        return ('\\subsection*{' + escape(heading) + '}\n\\begin{longtable}{' + spec + '}\n'
                + header + '\\endhead\n' + body + '\\end{longtable}\n')

    intro = ('% Deterministic projection only; no scientific computation or release authority.\n'
             '\\noindent Source report: \\texttt{' + escape(digest) + '}.\n'
             '\\par Values are already reported estimates. Missing fields and nulls read ``not reported''. '
             'Four decimal places are used for floating estimates and numeric interval endpoints. Nonzero values that would round to zero '
             'use scientific notation. Exact values and field pointers remain in provenance.json and the input facts. '
             'Primary designation identifies the prespecified family, not a significant finding.\n')
    main, appendix = [intro], [intro]
    groups = {}
    for comp in facts['primary_projection']['comparisons']:
        p = '/primary' + comp['source_pointer']
        key = comp['contrast_key']
        # Contrast keys are JSON member names, not fabricated report values.
        fields = [(n, field(p, n)) for n in ('difference', 'ci95', 'holm_p_value', 'events', 'training_seeds', 'status', 'reason')]
        r = row('primary.' + comp['family'], key or comp['family'], fields)
        provenance[-1]['record_source_pointer'] = p
        groups.setdefault(comp['family'], []).append(escape(key or comp['family']) + ' & ' + r)
    for family, rows in sorted(groups.items()):
        p = '/primary/families/' + family
        metadata = row('primary_family_metadata', family, [(n, field(p, n)) for n in ('holm_family_size', 'family_wise_alpha', 'declares_primary_finding')])
        text = table('primary_family_metadata', family + ' multiplicity and designation', ['Holm family size', 'Family alpha', 'Primary designation'], ['.28', '.28', '.28'], [metadata], wide=family == 'primary_ap')
        text += table('primary.' + family, family + ' contrasts',
                     ['Contrast', 'Difference', '95% CI', 'Holm p', 'Events', 'Seeds', 'Status', 'Reason'],
                     ['.14', '.10', '.17', '.08', '.06', '.06', '.12', '.13'], rows, wide=family == 'primary_ap')
        (main if family == 'primary_ap' else appendix).append(text)

    sections = sorted({r['section'] for r in facts['records'] if r['record_type'] == 'section_metadata'})
    scope_rows = []
    for section in sections:
        p = next(r['source_pointer'] for r in facts['records'] if r['section'] == section and r['record_type'] == 'section_metadata')
        scope = field(p, 'target_scope')
        if scope is not None and isinstance(value(scope), dict):
            scope = field(scope, 'kind')
        scope_rows.append(escape(section) + ' & ' + row('secondary_scope', section,
            [('target_scope_kind', scope)] + [(n, field(p, n)) for n in ('declares_primary_finding', 'formal_tests', 'intervals_computed')]))
    main.append(table('secondary_scope', 'All retained secondary sections',
                     ['Section', 'Target scope', 'Primary designation', 'Formal tests', 'Intervals'],
                     ['.28', '.24', '.12', '.12', '.12'], scope_rows, wide=True))
    main.append('\\noindent Complete retained identities, statuses and reported secondary contrasts appear in the supplement. '
                'The formatter does not compute missing per-model means from per-event rows.\n')

    for section in ['primary', *sections]:
        rows = []
        for record in facts['records']:
            if record['section'] != section or record['record_type'] not in ('cell', 'primary_identity'):
                continue
            p = record['source_pointer']
            identity = value(p) if record['record_type'] == 'primary_identity' else p.split('/')[-1].replace('~1', '/').replace('~0', '~')
            if record['record_type'] == 'primary_identity':
                # Primary has no scalar per-model status or overall estimate.
                name, horizon, index = p.split('/')[3:]
                abstention = '/primary/eligibility/' + horizon + '/abstentions/' + name + '/' + index
                census = '/primary/censoring/' + horizon
                fields = [('status', None), ('reference_events', field(census, 'reference_events')),
                          ('scorable_events', field(census, 'scorable_events')), ('mean_smape', None),
                          ('abstentions', abstention)]
            else:
                fields = [(n, field(p, n)) for n in ('status', 'reference_events', 'scorable_events', 'mean_smape')]
                reason = 'reason' if 'reason' in value(p) else 'failure_chain'
                fields.append((reason, field(p, reason)))
            rows.append(escape(identity) + ' & ' + row('identities.' + section, identity, fields))
            provenance[-1]['identity_source_pointer'] = p
        appendix.append(table('identities.' + section, section + ' retained identities',
                              ['Identity', 'Status', 'Reference N', 'Scorable N', 'Mean sMAPE', 'Reason / abstentions'],
                              ['.32', '.13', '.10', '.10', '.10', '.13'], rows))
        contrast_rows = []
        for record in facts['records']:
            if record['section'] != section or record['record_type'] != 'contrast' or section == 'primary':
                continue
            p = record['source_pointer']
            contrast_rows.append(row('contrasts.' + section, p,
                [(n, field(p, n)) for n in ('arm_id', 'comparator', 'cohort', 'metric', 'mean_difference', 'status')]))
        if contrast_rows:
            appendix.append(table('contrasts.' + section, section + ' descriptive contrasts',
                ['Identity', 'Comparator', 'Cohort', 'Metric', 'Difference', 'Status'],
                ['.24', '.22', '.12', '.12', '.08', '.10'], contrast_rows))
    return {'main.tex': ''.join(main), 'supplement.tex': ''.join(appendix),
            'provenance.json': json.dumps({'source_report_sha256': digest, 'rows': provenance,
                'numerical_verification_performed': False, 'release_authority_granted': False},
                indent=2, sort_keys=True, allow_nan=False) + '\n'}
