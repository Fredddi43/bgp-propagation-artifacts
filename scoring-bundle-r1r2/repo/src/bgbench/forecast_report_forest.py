"""F4: render the twelve existing N AP contrasts, without estimation or selection."""
import hashlib
import io
import json
import math

from . import forecast_full_report_facts as facts_api
from .forecast_report_latex import display

PAIRS = {'C1': ('sage_on', 'none_on'), 'C2': ('sage_on', 'online_history'),
         'C3': ('sage_on', 'sage_off'), 'C4': ('none_on', 'none_off'),
         'C5': ('frozen_sage_on', 'online_history'), 'C6': ('frozen_sage_on', 'sage_on')}
ORDER = tuple(f'{contrast}@{h}' for contrast in PAIRS for h in (30, 60))
NAMES = {'sage_on': 'SAGE + history', 'none_on': 'No-edge + history',
         'sage_off': 'SAGE, no history', 'none_off': 'No-edge, no history',
         'online_history': 'Online history', 'frozen_sage_on': 'Frozen SAGE + history'}


def extract(facts):
    """Exact displayed fields and pointers; the source report remains authoritative."""
    if facts.get('schema') != 'forecast_full_newperiod_report_facts_v1':
        raise ValueError('Reviewed full-N facts required')
    raw = facts_api.canonical(facts['report'])
    checked = facts_api.collect(raw, hashlib.sha256(raw).hexdigest())
    for key in ('records', 'primary_projection', 'retained_identity_count'):
        if facts[key] != checked[key]:
            raise ValueError('Facts projection differs: ' + key)
    digest = facts['source_report_sha256']
    if not facts_api.primary_facts.SHA256.fullmatch(digest):
        raise ValueError('Original report hash required')
    family = facts['report']['primary']['families']['primary_ap']
    prefix = '/primary/families/primary_ap'
    absent = 'contrasts' not in family
    if absent:
        if family.get('status') != 'unavailable' or not family.get('reason'):
            raise ValueError('Explicit unavailable-family reason required')
    elif (set(family['contrasts']) != set(ORDER) or family['holm_family_size'] != 12
          or family['declares_primary_finding'] is not True):
        raise ValueError('Complete fixed twelve-contrast primary AP family required')
    rows = []
    fields = ('difference', 'ci95', 'holm_p_value', 'events', 'eligible_events',
              'training_seeds', 'left', 'right', 'horizon_seconds', 'metric',
              'interval', 'status', 'reason')
    for key in ORDER:
        contrast, horizon = key.split('@')
        row = None if absent else family['contrasts'][key]
        path = prefix if absent else prefix + '/contrasts/' + key
        if row is not None:
            if (row.get('left'), row.get('right')) != PAIRS[contrast] or row.get('horizon_seconds') != int(horizon):
                raise ValueError('Source contrast identity differs')
            if row.get('metric') != 'average_precision':
                raise ValueError('F4 uses candidate-complete AP only')
            delta, ci, holm = row.get('difference'), row.get('ci95'), row.get('holm_p_value')
            if (type(delta) not in (int, float) or not math.isfinite(delta) or not -1 <= delta <= 1
                    or not isinstance(ci, list) or len(ci) != 2
                    or any(type(x) not in (int, float) or not math.isfinite(x) or not -1 <= x <= 1 for x in ci)
                    or ci[0] > ci[1] or type(holm) not in (int, float)
                    or not math.isfinite(holm) or not 0 <= holm <= 1):
                raise ValueError('Finite original AP difference, ordered CI and Holm p required')
            # A percentile CI need not contain its point estimate. Draw these
            # independently, rather than constructing unsigned error lengths.
            if any(type(row.get(k)) is not int or row[k] <= 0 for k in ('events', 'eligible_events', 'training_seeds')):
                raise ValueError('Original eligible-event and seed denominators required')
            if row['events'] != row['eligible_events']:
                raise ValueError('AP event denominator differs from eligible events')
        values = family if absent else row
        rows.append({'contrast_key': key, 'source_report_sha256': digest,
                     'display_status': 'unavailable' if absent else 'reported_estimate',
                     'fields': {field: {'source_pointer': path + '/' + field if field in values else None,
                                        'value': values.get(field)} for field in fields}})
    return {'schema': 'forecast_F4_existing_primary_AP_v1', 'source_report_sha256': digest,
            'family_source_pointer': prefix, 'family_metadata': {k: v for k, v in family.items() if k != 'contrasts'},
            'rows': rows, 'numerical_verification_performed': False, 'release_authority_granted': False,
            'estimation_performed': False,
            'display_policy': 'Fixed C1..C6 then 30/60 seconds; AP difference axis [-1,1]; no significance filtering; '
                              'original ordinary 95% intervals, not simultaneous; Holm p copied, no new tests.'}


def render(facts, *, synthetic=False):
    """Return deterministic PDF/SVG/PNG and exact provenance; never touch files."""
    provenance = extract(facts)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    settings = {'font.family': 'DejaVu Sans', 'font.size': 8, 'text.usetex': False,
                'text.parse_math': False, 'svg.hashsalt': 'bgbench-F4-fixed-v1',
                'pdf.fonttype': 42, 'axes.spines.top': False, 'axes.spines.right': False}
    with matplotlib.rc_context(settings):
        fig = plt.figure(figsize=(8.2, 5.6), facecolor='white')
        grid = fig.add_gridspec(1, 3, width_ratios=(3.15, 2.5, 1.65), wspace=.04,
                               left=.025, right=.985, bottom=.32, top=.82)
        labels, axis, numbers = [fig.add_subplot(grid[0, i]) for i in range(3)]
        for ax in (labels, axis, numbers):
            ax.set_ylim(11.8, -.8)
            for y in (1.5, 3.5, 5.5, 7.5, 9.5):
                ax.axhline(y, color='#e3e6eb', linewidth=.6, zorder=0)
        labels.set_axis_off(); numbers.set_axis_off()
        labels.set_xlim(0, 1); numbers.set_xlim(0, 1)
        axis.set_xlim(-1, 1)
        axis.axvline(0, color='#667085', linewidth=.8, linestyle='--')
        axis.set_yticks([]); axis.spines['left'].set_visible(False)
        axis.set_xticks([-1, -.5, 0, .5, 1])
        axis.xaxis.set_major_formatter(ticker.FormatStrFormatter('%g'))
        axis.set_xlabel('AP difference (left minus right)', fontsize=8)
        labels.text(0, -.95, 'Prespecified contrast', weight='bold', fontsize=8)
        numbers.text(0, -.95, 'Holm p', weight='bold', fontsize=8)
        numbers.text(.54, -.95, 'Events / seeds', weight='bold', fontsize=8)
        for y, row in enumerate(provenance['rows']):
            cid, horizon = row['contrast_key'].split('@'); left, right = PAIRS[cid]
            label = f'{cid}  {NAMES[left]} - {NAMES[right]}' if horizon == '30' else '      Same contrast'
            labels.text(0, y, label + f'  ({horizon}s)', va='center', fontsize=7.1)
            field = {k: v['value'] for k, v in row['fields'].items()}
            if row['display_status'] == 'unavailable':
                axis.text(.5, y, 'Unavailable', transform=axis.get_yaxis_transform(),
                          ha='center', va='center', fontsize=7.5, color='#667085')
                numbers.text(0, y, 'not reported', va='center', fontsize=7)
                continue
            color = '#245E91' if horizon == '30' else '#A34E18'
            low, high = field['ci95']
            axis.hlines(y, low, high, color=color, linewidth=1.6)
            axis.plot([low, high], [y, y], '|', color=color, markersize=5)
            axis.plot(field['difference'], y, 'o' if horizon == '30' else 's',
                      color=color, markersize=4, zorder=3)
            numbers.text(0, y, display(field['holm_p_value']), va='center', fontsize=7.5)
            numbers.text(.54, y, f"{field['eligible_events']} / {field['training_seeds']}", va='center', fontsize=7.5)
        fig.text(.025, .95, 'N: twelve prespecified primary AP contrasts', fontsize=12, weight='bold')
        fig.text(.025, .905, 'SYNTHETIC FIXTURE: NOT EMPIRICAL RESULTS' if synthetic else
                 '30 s: blue circles    60 s: orange squares', fontsize=8.5,
                 color='#9B1C20' if synthetic else '#344054')
        fig.text(.025, .17, 'Dots and ordinary 95% intervals are copied from the source report; intervals are not simultaneous.\n'
                 'Holm-adjusted p values use the existing family of 12. No contrasts are selected or recomputed.\n'
                 'Primary designation describes the prespecified family, not a finding of significance.', fontsize=7.5, linespacing=1.5)
        if provenance['family_metadata'].get('status') == 'unavailable':
            fig.text(.025, .09, 'Family unavailable; exact original reason is retained in provenance.json.', fontsize=7.5)
        fig.text(.025, .04, 'Report SHA-256: ' + provenance['source_report_sha256'], fontsize=6)
        files = {}
        for extension in ('pdf', 'svg', 'png'):
            stream = io.BytesIO()
            metadata = {'CreationDate': None, 'ModDate': None} if extension == 'pdf' else (
                {'Date': None} if extension == 'svg' else {})
            fig.savefig(stream, format=extension, dpi=180, metadata=metadata)
            files['f4-primary-ap.' + extension] = stream.getvalue()
        plt.close(fig)
    provenance.update(synthetic_fixture=synthetic, matplotlib_version=matplotlib.__version__)
    files['provenance.json'] = (json.dumps(provenance, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    return files
