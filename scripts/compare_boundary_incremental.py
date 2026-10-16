"""Replace only independently assessed boundary rows in the full replay comparison."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import polars as pl


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(run):
    root=run/'crossday-final';old_path=run/'crossday-repair/input-changes.json';manifest_path=run/'boundary-audit/candidate-manifest.json'
    manifest=json.loads(manifest_path.read_text());old=json.loads(old_path.read_text())
    affected={(e['tag'],e['event_id']) for e in manifest['events']};old_keys={(x['tag'],x['event_id']) for x in old}
    assert len(old)==len(old_keys)==16700 and affected<=old_keys
    def unchanged(row):
        if (row['tag'],row['event_id']) in affected:return
        family=row['tag'] or 'origin';path=root/'events'/family/row['event_id'];expected=run/'crossday-repair/events'/family/row['event_id']
        if not path.is_symlink() or path.readlink()!=expected:raise ValueError(f'unchanged event does not reference identical old replay: {path}')
    with ThreadPoolExecutor(max_workers=32) as pool:list(pool.map(unchanged,old))
    patches={};bindings={str(old_path.relative_to(run)):sha(old_path),str(manifest_path.relative_to(run)):sha(manifest_path)}
    for group in manifest['changes']:
        year=group['year'];tag='' if group['family']=='origin' else group['family'];ids=group['event_ids']
        candidate=Path(group['candidate_event_table']);folder=str(year)+('_'+tag if tag else '')
        original=run/'data/eventset'/folder/'events.before-crossday-repair.parquet'
        if not original.exists():original=run/'data/eventset'/folder/'events.parquet'
        before={r['event_id']:r for r in pl.read_parquet(original).filter(pl.col('event_id').is_in(ids)).to_dicts()}
        new=pl.read_parquet(candidate).filter(pl.col('event_id').is_in(ids))
        assert new.height==len(ids)
        for after in new.to_dicts():
            prior=before[after['event_id']];sets={}
            for key in sorted(k for k in set(prior)|set(after) if k.startswith('set_')):
                a,b=set(prior.get(key) or []),set(after.get(key) or [])
                sets[key]={'old_n':len(a),'new_n':len(b),'added':sorted(b-a),'removed':sorted(a-b)}
            patches[(tag,after['event_id'])]={'new_t0_obs':after.get('t0_obs'),'new_error':after.get('error'),'new_t90_s':after.get('t90_s'),'new_anomalous_msgs':after.get('anomalous_msgs'),'sets':sets}
        for path in (original,candidate):bindings[str(path.relative_to(run))]=sha(path)
    result=[{**row,**patches.get((row['tag'],row['event_id']),{})} for row in old]
    assert set(patches)==affected
    dest=root/'input-changes.json';temp=dest.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=1,default=str));temp.replace(dest)
    proof={'status':'passed','rows':len(result),'recomputed_rows':len(patches),'unchanged_replay_paths':len(result)-len(patches),'source_sha256':bindings,'comparison_sha256':sha(dest),'script_sha256':sha(Path(__file__))}
    (root/'incremental-comparison-verification.json').write_text(json.dumps(proof,indent=1))
    print(json.dumps({k:v for k,v in proof.items() if k!='source_sha256'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args();main(a.run)
