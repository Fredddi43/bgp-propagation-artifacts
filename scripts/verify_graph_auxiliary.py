"""Independently verify auxiliary forecasts against source sets and saved evidence.

Private mode reads replay membership for collector/shifted observations. Public
mode requires the private audit's hashes before using those embedded source sets.
Neither mode loads a checkpoint or trusts producer-computed metric values.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import polars as pl

REPORT = 'analysis/graph_auxiliary_verification.json'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def as_set(value):
    values = json.loads(value)
    assert isinstance(values, list) and all(type(v) is int for v in values), 'invalid AS list'
    assert len(values) == len(set(values)), 'duplicate AS in evidence'
    return set(values)

def equal(got, want, tolerance=1e-9):
    if got is None or not np.isfinite(float(got)):
        assert want is None or not np.isfinite(float(want)), (got, want)
    else:
        assert want is not None and np.isfinite(float(want)) and abs(float(got)-float(want)) <= tolerance, (got, want)

def jac(a, b):
    assert a | b, 'unexpected empty target and prediction'
    return len(a & b) / len(a | b)

def mean(values):
    values = [v for v in values if v is not None and np.isfinite(v)]
    return float(np.mean(values)) if values else None

def ap_score(truth, candidates, probabilities, seeds):
    pairs = [(p, a in truth) for a,p in zip(candidates, probabilities) if a not in seeds]
    labels = np.array([y for _,y in pairs], dtype=bool)
    if not labels.any() or labels.all():
        return float('nan')
    order = np.argsort(-np.array([p for p,_ in pairs]), kind='stable')
    scores = np.array([p for p,_ in pairs])[order]
    labels = labels[order]
    ends = np.r_[np.flatnonzero(np.diff(scores)), len(scores)-1]
    tp = np.cumsum(labels)[ends]
    return float(np.sum(np.diff(np.r_[0,tp]) * tp / (ends+1)) / labels.sum())

class Audit:
    def __init__(self, data, public=False):
        self.data, self.public = data, public
        self.source_hashes, self.evidence_hashes = {}, {}
        self.tables, self.memberships, self.injection_candidates = {}, {}, {}
        self.checks = 0
        self.previous = json.loads((data/REPORT).read_text()) if public else None
        if public:
            assert self.previous['status'] == 'passed' and self.previous['mode'] == 'private_source_audit'

    def hashed(self, relative, source=False):
        path = self.data / relative
        value = digest(path)
        (self.source_hashes if source else self.evidence_hashes)[relative] = value
        if self.public:
            expected = self.previous['source_sha256' if source else 'evidence_sha256'][relative]
            assert value == expected, f'changed audited evidence: {relative}'
        return path

    def source(self, setting, eid):
        year, tag = setting.split('_', 1)
        family = 'withdrawal' if tag == 'withdrawal' else 'leak'
        relative = f'eventset/{year}_{family}/events.parquet'
        if relative not in self.tables:
            self.tables[relative] = pl.read_parquet(self.hashed(relative, True))
        rows = self.tables[relative].filter(pl.col('event_id') == eid).to_dicts()
        assert len(rows) == 1, f'missing/duplicate source event {eid}'
        return rows[0], family

    def membership(self, family, eid):
        relative = f'events_replay_{family}/{eid}/membership.parquet'
        if relative not in self.memberships:
            self.memberships[relative] = pl.read_parquet(self.hashed(relative, True))
        return self.memberships[relative]

    def check_row(self, row, setting, delta, kind):
        truth, seeds = as_set(row['target_asns']), as_set(row['seed_asns'])
        assert truth, 'unexpected empty full target'
        source, family = self.source(setting, row['event_id'])
        shift_match = re.search(r'@t0=(-?\d+)', setting)
        shift = int(shift_match[1]) if shift_match else 0
        canonical_seed = set(source['set_d30s' if delta == 30 else 'set_d1m'])
        if kind == 'per_vp' or shift:
            if not self.public:
                mem = self.membership(family, row['event_id'])
                if kind == 'per_vp':
                    mem = mem.filter(pl.col('collector') == row['collector'])
                onset = source['t0_obs']
                if isinstance(onset, str): onset = datetime.fromisoformat(onset)
                canonical_seed = set(mem.filter(pl.col('first_seen') <= onset+timedelta(seconds=delta+shift))['asn'])
                expected_truth = set(mem.filter(pl.col('first_seen') <= onset+timedelta(hours=2))['asn'])
                assert truth == expected_truth, 'raw membership target mismatch'
                assert seeds == canonical_seed, 'raw membership seed mismatch'
            elif kind != 'per_vp':
                assert truth == set(source['set_final_2h'])
        else:
            assert truth == set(source['set_final_2h']), 'source target mismatch'
            if kind == 'robustness' and row['kind'] == 'inject':
                assert canonical_seed <= seeds, 'injection removed real seed'
                candidates = set(json.loads(row['candidate_asns']))
                eligible = as_set(row['eligible_injection_asns'])
                assert seeds-canonical_seed <= eligible <= candidates-canonical_seed, 'invalid injected candidates'
                k = round(row['level']*max(1,len(candidates & canonical_seed)))
                assert len(seeds-canonical_seed) == min(k,len(eligible)), 'incorrect injection size'
                if not self.public:
                    import torch
                    relative = f'tgn/{setting}/d{delta}s/{row["event_id"]}.pt'
                    if relative not in self.injection_candidates:
                        tensor = torch.load(self.hashed(relative, True), weights_only=False, map_location='cpu', mmap=True)
                        self.injection_candidates[relative] = set(tensor['asn'][~tensor['persistence_pred'].bool() & (tensor['x'][:,5] == 1)].tolist())
                    assert eligible == self.injection_candidates[relative], 'injection candidates differ from frozen uncorrupted input'
            else:
                assert seeds == canonical_seed, 'source seed mismatch'
        predictions = {'jaccard_thr':'predicted_asns_tuned', 'jaccard_05':'predicted_asns_at05'} if kind == 'cross' else {
            'j_model' if kind == 'per_vp' else 'jaccard_model':'predicted_asns'}
        for metric, column in predictions.items():
            pred = as_set(row[column])
            assert seeds <= pred, 'prediction omitted observed seed'
            if kind != 'prf1': equal(row[metric], jac(pred, truth))
        if kind != 'prf1':
            equal(row['j_persist' if kind == 'per_vp' else 'jaccard_persist'], jac(seeds, truth))
        if kind in ('cross','robustness'):
            candidates = json.loads(row['candidate_asns'])
            assert len(candidates) == len(set(candidates))
            probabilities = json.loads(row['candidate_probabilities'])
            assert len(candidates) == len(probabilities) and all(np.isfinite(p) and 0 <= p <= 1 for p in probabilities)
            equal(row['auprc_new'], ap_score(truth, candidates, probabilities, seeds))
        if kind == 'cross':
            equal(row['pos'], len(truth)); equal(row['seeds'], len(seeds))
            equal(row['curve_true_2h'], len(truth))
            assert row['curve_pred_2h']+1e-6*max(1,len(seeds)) >= len(seeds), 'count forecast below seed floor'
        if kind == 'prf1':
            new, actual = pred-seeds, truth-seeds
            tp,fp,fn = len(new&actual),len(new-actual),len(actual-new)
            for key,value in {'tp':tp,'fp':fp,'fn':fn,'new_pos':len(actual),'pred_new':len(new),
                'prec':tp/(tp+fp) if tp+fp else float('nan'), 'rec':tp/(tp+fn) if tp+fn else float('nan'),
                'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else float('nan'),
                'prec_full':len(pred&truth)/max(len(pred),1),'rec_full':len(pred&truth)/len(truth)}.items(): equal(row[key],value)
        self.checks += 1

    def verify_file(self, relative):
        path = self.hashed(relative)
        frame = pl.read_csv(path)
        rows = frame.to_dicts()
        setting, delta = path.parents[2].name, int(path.parents[1].name[1:-1])
        kind = 'robustness' if 'robustness' in path.name else 'per_vp' if '_per_vp_' in path.name else 'prf1' if '_prf1_' in path.name else 'cross'
        index_relative = str(path.parents[1].relative_to(self.data)/'index.csv')
        index = pl.read_csv(self.hashed(index_relative, True)).filter(pl.col('split') == 'test')
        ids = set(index['event_id'])
        assert set(frame['event_id']) == ids, f'incomplete auxiliary cohort: {relative}'
        keys = ['event_id'] + (['kind','level'] if kind == 'robustness' else ['collector'] if kind == 'per_vp' else [])
        assert frame.unique(keys).height == frame.height, 'duplicate auxiliary row'
        primary = None
        if kind in ('prf1','per_vp'):
            model = path.name.split('_',1)[0]
            primary_relative = str(path.with_name(model+'_test_per_event.csv').relative_to(self.data))
            primary = {r['event_id']:as_set(r['predicted_asns_tuned']) for r in pl.read_csv(self.hashed(primary_relative)).to_dicts()}
            assert set(primary) == ids, 'primary versus auxiliary cohort mismatch'
        for row in rows:
            self.check_row(row,setting,delta,kind)
            if primary is not None:
                expected_prediction = primary[row['event_id']] | as_set(row['seed_asns'])
                assert as_set(row['predicted_asns']) == expected_prediction, 'auxiliary changed primary prediction'
        groups = defaultdict(list)
        for row in rows:
            groups[(row['kind'],row['level']) if kind == 'robustness' else row['collector'] if kind == 'per_vp' else None].append(row)
        if kind == 'robustness':
            assert set(groups) == {('clean',0.),('drop',.3),('drop',.6),('drop',.9),('inject',.25),('inject',.5),('inject',1.),('hide',1.)}
            summary_relative = relative.replace('_per_event.csv','.json')
            summary = json.loads(self.hashed(summary_relative).read_text())
            table = pl.read_csv(self.hashed(relative.replace('_per_event.csv','.csv'))).to_dicts()
            assert table == summary['table']
            for row in table:
                group = groups[(row['kind'],row['level'])]
                assert {r['event_id'] for r in group} == ids
                equal(row['n'],len(group))
                for metric in ('jaccard_model','jaccard_persist','auprc_new'): equal(row[metric],mean([r[metric] for r in group]),5.01e-5)
                for r in group:
                    wanted = as_set(r['seed_asns']) | {a for a,p in zip(json.loads(r['candidate_asns']),json.loads(r['candidate_probabilities'])) if p >= summary['threshold']}
                    assert as_set(r['predicted_asns']) == wanted, 'threshold prediction mismatch'
        elif kind == 'per_vp':
            table = pl.read_csv(self.hashed(relative.replace('_per_event.csv','.csv'))).to_dicts()
            assert {r['collector'] for r in table} == set(groups)
            if not self.public:
                expected_pairs = set()
                for eid in ids:
                    source,family = self.source(setting,eid)
                    onset = source['t0_obs']; onset = datetime.fromisoformat(onset) if isinstance(onset,str) else onset
                    mem = self.membership(family,eid).filter(pl.col('first_seen') <= onset+timedelta(hours=2))
                    expected_pairs.update((eid,c) for c in mem['collector'].unique())
                assert {(r['event_id'],r['collector']) for r in rows} == expected_pairs, 'missing collector rows'
            for row in table:
                group = groups[row['collector']]; equal(row['n'],len(group))
                for metric in ('j_model','j_persist'): equal(row[metric],mean([r[metric] for r in group]))
                equal(row['diff'],mean([r['j_model']-r['j_persist'] for r in group]))
        else:
            summary = json.loads(self.hashed(relative.replace('_per_event.csv','.json')).read_text())
            equal(summary['events'],len(rows))
            if kind == 'cross':
                for metric in ('jaccard_thr','jaccard_05','jaccard_persist','auprc_new'): equal(summary[metric],mean([r[metric] for r in rows]),5.01e-5)
                equal(summary['curve_smape_2h'],mean([2*abs(r['curve_pred_2h']-r['curve_true_2h'])/max(abs(r['curve_pred_2h'])+abs(r['curve_true_2h']),1e-9) for r in rows]),5.01e-5)
                for r in rows:
                    for col,thr in [('predicted_asns_tuned',summary['threshold']),('predicted_asns_at05',.5)]:
                        wanted = as_set(r['seed_asns']) | {a for a,p in zip(json.loads(r['candidate_asns']),json.loads(r['candidate_probabilities'])) if p >= thr}
                        assert as_set(r[col]) == wanted
            else:
                s = summary['new_members_only']
                for key,col in [('precision','prec'),('recall','rec'),('f1','f1')]:
                    equal(s[key+'_mean'],mean([r[col] for r in rows]),5.01e-5)
                    equal(s[key+'_defined_events'],sum(np.isfinite(r[col]) for r in rows))
                totals = {k:sum(r[k] for r in rows) for k in ('tp','fp','fn')}
                for key,den in [('precision','fp'),('recall','fn')]: equal(s['micro_'+key],totals['tp']/max(totals['tp']+totals[den],1),5.01e-5)
                equal(s['zero_prediction_events'],sum(r['pred_new']==0 for r in rows))
                for key,col in [('predicted_new_per_event_p50','pred_new'),('true_new_per_event_p50','new_pos')]: equal(s[key],np.median([r[col] for r in rows]))
                for key,col in [('precision_mean','prec_full'),('recall_mean','rec_full')]: equal(summary['full_set_seeds_plus_predicted'][key],mean([r[col] for r in rows]),5.01e-5)

def verify_auxiliary(data, manifest, public=False):
    data, manifest = Path(data), Path(manifest)
    audit = Audit(data,public)
    expected = json.loads(manifest.read_text())['auxiliary_files']
    for relative in expected:
        if relative.endswith('_per_event.csv'): audit.verify_file(relative)
    # The common trigger cohort is derived from all five eligible populations.
    relative = 'tgn/2025_leak200/d30s/_results/trigger_error_common_cohort.json'
    common = json.loads(audit.hashed(relative).read_text())
    frames = {}
    for shift in (0,-30,60,300,900):
        tag = 'leak200'+(f'@t0={shift}' if shift else '')
        rel = f'tgn/2025_{tag}/d30s/_results/cross_sage_leak2002025_per_event.csv'
        frames[shift] = pl.read_csv(data/rel)
    ids = set.intersection(*(set(f['event_id']) for f in frames.values()))
    assert set(common['common_event_ids']) == ids
    for shift,frame in frames.items():
        frame = frame.filter(pl.col('event_id').is_in(sorted(ids)))
        summary_relative = rel = f'tgn/2025_leak200'+(f'@t0={shift}' if shift else '')+'/d30s/_results/cross_sage_leak2002025.json'
        assert common['all_eligible_by_shift'][str(shift)] == json.loads((data/summary_relative).read_text())
        row = common['paired_common_cohort'][str(shift)]
        equal(row['events'],len(ids)); equal(row['jaccard_model'],frame['jaccard_thr'].mean()); equal(row['jaccard_persist'],frame['jaccard_persist'].mean())
    paired = json.loads(audit.hashed('analysis/graph_paired_comparisons.json').read_text())
    for comparison in paired['comparisons']:
        frames = []
        for name in ('model_a','model_b'):
            relative = comparison[name]
            table = pl.read_csv(audit.hashed(relative)).sort('event_id')
            metric = 'jaccard_hist' if Path(relative).name.startswith('hist_avg') else 'jaccard_model_tuned'
            frames.append((list(table['event_id']),table[metric].to_numpy(),table['jaccard_persist'].to_numpy()))
        a,b = frames
        assert a[0] == b[0] and np.allclose(a[2],b[2],rtol=0,atol=1e-10)
        difference = a[1]-b[1]
        equal(comparison['events'],len(difference)); equal(comparison['mean_a'],a[1].mean()); equal(comparison['mean_b'],b[1].mean())
        equal(comparison['difference_a_minus_b'],difference.mean())
        rng = np.random.default_rng(0)
        bootstrap = [difference[rng.integers(0,len(difference),len(difference))].mean() for _ in range(2000)]
        for actual,wanted in zip(comparison['ci95'],np.quantile(bootstrap,[.025,.975])): equal(actual,wanted)

    result = {'status':'passed','mode':'private_source_audit','checked_event_rows':audit.checks,
              'source_sha256':audit.source_hashes,'evidence_sha256':audit.evidence_hashes,
              'public_policy':'Recompute arithmetic; require byte-identical evidence to private raw-membership source audit.'}
    if not public:
        (data/REPORT).write_text(json.dumps(result,indent=2))
    return {'status':'passed','checked_event_rows':audit.checks,'mode':'public' if public else 'private'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('data',type=Path); parser.add_argument('manifest',type=Path)
    parser.add_argument('--public',action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify_auxiliary(args.data,args.manifest,args.public)))

if __name__ == '__main__': main()
