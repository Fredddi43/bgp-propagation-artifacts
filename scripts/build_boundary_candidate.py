"""Build an isolated complete data-root view of predecessor corrections."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import polars as pl
from bgbench import config
from bgbench.eventset import build_table
from repair_crossday_replays import patch_measurements


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main(run):
    root=run/'boundary-audit';impact=json.loads((root/'impact.json').read_text())
    data=root/'candidate-data';data.mkdir(exist_ok=True)
    affected=[x for x in impact['events'] if x['status']=='candidate' or (x['status']=='coverage_gap' and not x['original_error'])]
    groups=defaultdict(list)
    for x in affected:groups[(x['year'],x['tag'])].append(x)
    for source in (run/'data').iterdir():
        if source.name=='eventset' or source.name in ('events_replay','events_replay_leak','events_replay_withdrawal','tgn'):continue
        dest=data/source.name
        if not dest.exists():dest.symlink_to(source.resolve(),target_is_directory=source.is_dir())
    (data/'tgn').mkdir(exist_ok=True)
    for tag in ('','leak','withdrawal'):
        name='events_replay'+('_'+tag if tag else '');folder=data/name;folder.mkdir(exist_ok=True)
        updates={x['event_id']:x for x in affected if x['tag']==tag}
        def link_event(source):
            x=updates.get(source.name)
            try:
                target=Path(os.readlink(source))
                if not target.is_absolute():target=source.parent/target
            except OSError:target=source
            if x:
                if x['status']=='candidate':target=run/x['candidate_replay']
                else:
                    target=root/'events'/(tag or 'origin')/x['event_id'];target.mkdir(parents=True,exist_ok=True)
                    original=json.loads((source/'summary.json').read_text())
                    original.update(error='incomplete_predecessor_archive_coverage',measurement_predecessor_gap_tasks=x['archive_gap_tasks'])
                    (target/'summary.json').write_text(json.dumps(original,indent=1))
            dest=folder/source.name
            if not dest.is_symlink():dest.symlink_to(target,target_is_directory=True)
            elif dest.readlink()!=target:raise ValueError(f'candidate link already targets a different source: {dest}')
        with ThreadPoolExecutor(max_workers=32) as pool:list(pool.map(link_event,(run/'data'/name).iterdir()))
    (data/'eventset').mkdir(exist_ok=True);bindings={};changes=[]
    for source in (run/'data/eventset').iterdir():
        group=next((g for g in groups if source.name==str(g[0])+('_'+g[1] if g[1] else '')),None)
        dest=data/'eventset'/source.name
        if group is None:
            if not dest.exists():dest.symlink_to(source.resolve(),target_is_directory=True)
            continue
        dest.mkdir(exist_ok=True)
        for file in source.iterdir():
            if file.name=='events.parquet':continue
            link=dest/file.name
            if not link.exists():link.symlink_to(file.resolve(),target_is_directory=file.is_dir())
        year,tag=group;repaired=build_table(year,tag,replay_root=root/'events'/(tag or 'origin'))
        ids=[x['event_id'] for x in groups[group]]
        repaired=repaired.filter(pl.col('event_id').is_in(ids))
        old=pl.read_parquet(source/'events.parquet');new=patch_measurements(old,repaired)
        new.write_parquet(dest/'events.parquet',compression='zstd')
        bindings[str((source/'events.parquet').relative_to(run))]=sha(source/'events.parquet')
        bindings[str((dest/'events.parquet').relative_to(run))]=sha(dest/'events.parquet')
        changes.append({'year':year,'family':tag or 'origin','event_ids':ids,'candidate_event_table':str(dest/'events.parquet')})
    manifest={'status':'ready','candidate_data_root':str(data),'changes':changes,'source_sha256':bindings,'impact_sha256':sha(root/'impact.json'),
              'events':affected,'note':'Isolated view; existing canonical and graph-frozen replay paths are immutable.'}
    (root/'candidate-manifest.json').write_text(json.dumps(manifest,indent=1));print(json.dumps({'groups':len(groups),'affected_events':len(affected),'manifest':str(root/'candidate-manifest.json')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args();main(a.run)
