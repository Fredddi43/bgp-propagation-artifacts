"""Lossless full-N paper projection and exact-value tables; never rescore."""
import csv
import hashlib
import io
import json

from . import forecast_release_facts as primary_facts

MEMBERSHIP = {'h1': 20, 'h3': 80, 'timing': 60, 'history': 48, 'ordinary': 32}
ORIGINS = ('origin_change_invalid', 'origin_change_valid')
COVERED = {'counts', *MEMBERSHIP, 'stable', 'additional_baselines', *ORIGINS}


def need(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def resolve(value, pointer):
    for part in pointer.removeprefix('/').split('/'):
        key = part.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def collect(raw, expected_sha256):
    """Project only the existing 400-identity result envelope, including failures.

    The caller must separately establish release/read authority and numerical
    verification. This pure operation does not provide either.
    """
    digest = hashlib.sha256(raw).hexdigest()
    need(isinstance(expected_sha256, str) and primary_facts.SHA256.fullmatch(expected_sha256)
         and digest == expected_sha256, 'Full report differs from external hash')
    report = json.loads(raw, object_pairs_hook=primary_facts._object,
                        parse_constant=primary_facts._nonfinite)
    canonical(report)
    need(report.get('kind') == 'newperiod_all_retained_R2_evaluation_v1'
         and report.get('full_newperiod_coverage') is True
         and report.get('actual_execution_authorized') is False, 'Complete original N envelope required')
    covered = report.get('covered_secondary_families')
    need(isinstance(covered, list) and len(covered) == len(set(covered))
         and set(covered) == COVERED, 'Complete secondary-family declarations required')
    need(set(report['membership']) == set(MEMBERSHIP)
         and set(report['origin']['families']) == set(ORIGINS), 'Exact retained families required')
    primary_raw = canonical(report['primary'])
    projected = primary_facts.collect(primary_raw, hashlib.sha256(primary_raw).hexdigest())
    need(projected['population'] == 'new_period', 'N primary population required')
    primary_ids = {arm for horizons in report['primary']['arms'].values()
                   for arms in horizons.values() for arm in arms}
    need(len(primary_ids) == 56 and sum(len(ids) for h in report['primary']['arms'].values() for ids in h.values()) == 56, 'Complete fixed primary identity population required')
    seen = set(primary_ids)
    records = []
    primary = report['primary']
    for name, horizons in primary['arms'].items():
        for horizon, identities in horizons.items():
            abstentions = primary['eligibility'][horizon]['abstentions'][name]
            strata = primary['stratification_by_new_members'][name][horizon]
            need(len(abstentions) == len(strata) == len(identities),
                 'Primary seed metadata differs from retained identities')
            for index, identity in enumerate(identities):
                for record_type, path in (
                    ('primary_identity', ('primary', 'arms', name, horizon, index)),
                    ('primary_abstentions', ('primary', 'eligibility', horizon, 'abstentions', name, index)),
                    ('primary_stratification', ('primary', 'stratification_by_new_members', name, horizon, index))):
                    records.append({'section': 'primary', 'record_type': record_type,
                                    'source_pointer': primary_facts.pointer(*path)})
    for horizon in primary['censoring']:
        records.append({'section': 'primary', 'record_type': 'censoring',
                        'source_pointer': primary_facts.pointer('primary', 'censoring', horizon)})
    for family in primary['families']:
        records.append({'section': 'primary', 'record_type': 'family_metadata',
                        'source_pointer': primary_facts.pointer('primary', 'families', family)})
    for row in projected['comparisons']:
        records.append({'section': 'primary', 'record_type': 'contrast',
                        'source_pointer': '/primary' + row['source_pointer']})
    sections = [(('counts',), 34), *((('membership', f), n) for f, n in MEMBERSHIP.items()),
                (('stable',), 24), *((('origin', 'families', f), 20) for f in ORIGINS),
                (('additional_baselines',), 6)]
    for parts, count in sections:
        prefix = primary_facts.pointer(*parts)
        section = resolve(report, prefix)
        need(section.get('declares_primary_finding') is False, 'Secondary designation changed')
        records.append({'section': '.'.join(parts), 'record_type': 'section_metadata',
                        'source_pointer': prefix})
        cells = section['cells']
        need(isinstance(cells, dict) and len(cells) == count and not seen.intersection(cells),
             'Retained cells missing, duplicated or reassigned')
        seen.update(cells)
        for name, cell in cells.items():
            need(isinstance(cell, dict) and isinstance(cell.get('status'), str)
                 and isinstance(cell.get('role'), dict), 'Explicit original cell status and role required')
            records.append({'section': '.'.join(parts), 'record_type': 'cell',
                            'source_pointer': primary_facts.pointer(*parts, 'cells', name)})
        contrasts = section.get('contrasts', [])
        need(isinstance(contrasts, list), 'Original secondary contrast list required')
        for index, contrast in enumerate(contrasts):
            need(isinstance(contrast, dict) and isinstance(contrast.get('status'), str),
                 'Original secondary contrast status required')
            records.append({'section': '.'.join(parts), 'record_type': 'contrast',
                            'source_pointer': primary_facts.pointer(*parts, 'contrasts', index)})
    need(len(seen) == 400, 'Complete original retained identity union required')
    # One full source object is retained. Record pointers avoid duplicating the
    # potentially large per-event lists in a second cell-facts collection.
    return {'schema': 'forecast_full_newperiod_report_facts_v1',
            'source_report_sha256': digest, 'population': 'new_period',
            'primary_projection': projected, 'primary_source_pointer': '/primary',
            'primary_canonical_sha256': hashlib.sha256(primary_raw).hexdigest(),
            'retained_identity_count': len(seen), 'records': sorted(records, key=lambda r: r['source_pointer']),
            'report': report, 'numerical_verification_performed': False,
            'release_authority_granted': False,
            'status': 'source_projection_only_pending_independent_numerical_verification'}


# Event-wise values remain lossless in facts.report; they are deliberately not
# represented as aggregate findings. Existing aggregate results/statuses only.
PER_EVENT_FIELDS = {'rows', 'per_event', 'input_available_rows'}
COLLECTION_FIELDS = {'cells', 'contrasts', 'cohort_ids', 'h3_cohorts', 'input_available_cohort'}


def table_rows(facts):
    need(facts.get('schema') == 'forecast_full_newperiod_report_facts_v1', 'Exact full-N facts required')
    for record in facts['records']:
        value = resolve(facts['report'], record['source_pointer'])
        if record['record_type'] == 'primary_identity':
            yield {'source_report_sha256': facts['source_report_sha256'],
                   'section': 'primary', 'record_type': 'primary_identity',
                   'source_pointer': record['source_pointer'],
                   'field': 'arm_id', 'value_json': canonical(value).decode()}
            continue
        for field in sorted(value):
            if field in PER_EVENT_FIELDS | COLLECTION_FIELDS:
                continue
            yield {'source_report_sha256': facts['source_report_sha256'],
                   'section': record['section'], 'record_type': record['record_type'],
                   'source_pointer': record['source_pointer'] + primary_facts.pointer(field),
                   'field': field, 'value_json': canonical(value[field]).decode()}


def tables(facts):
    """Deterministic exact-value CSV tables keyed by existing report section.

    No averaging, interval calculation, status filtering or numeric rounding.
    Compound existing metadata remains JSON in a single cell; null stays null.
    """
    grouped = {}
    for row in table_rows(facts):
        grouped.setdefault(row['section'], []).append(row)
    output = {}
    fields = ['source_report_sha256', 'section', 'record_type', 'source_pointer', 'field', 'value_json']
    for section, rows in sorted(grouped.items()):
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        output[section + '.csv'] = stream.getvalue()
    return output
