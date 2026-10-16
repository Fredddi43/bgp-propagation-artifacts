"""Version repaired replay inputs without changing paths used by frozen models."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path


def main(run):
    root=run/'boundary-audit';manifest=json.loads((root/'candidate-manifest.json').read_text())
    assert manifest['status']=='ready'
    old=run/'crossday-repair';new=run/'crossday-final';new.mkdir(exist_ok=True)
    events={(e['tag'] or 'origin',e['event_id']):e for e in manifest['events']}
    for kind in ('events','parts'):
        for family in ('origin','leak','withdrawal'):
            destination=new/kind/family;destination.mkdir(parents=True,exist_ok=True)
            def link_source(source):
                e=events.get((family,source.name));target=source.resolve()
                if e:
                    if kind=='events':target=root/'events'/family/source.name
                    elif e['status']=='candidate':target=root/'combined-parts'/family/source.name
                link=destination/source.name
                if not link.exists():link.symlink_to(target,target_is_directory=True)
                elif link.resolve()!=target.resolve():raise ValueError(f'conflicting existing target: {link}')
            with ThreadPoolExecutor(max_workers=32) as pool:list(pool.map(link_source,(old/kind/family).iterdir()))
    (new/'tasks').symlink_to(old/'tasks',target_is_directory=True) if not (new/'tasks').exists() else None
    merged=json.loads((old/'merge.json').read_text())
    gaps={eid for (family,eid),e in events.items() if e['status']=='coverage_gap'}
    for row in merged:
        if row['event_id'] in gaps:
            row['status']='excluded';row['error']='incomplete_predecessor_archive_coverage'
    (new/'merge.json').write_text(json.dumps(merged,indent=1))
    (new/'boundary-inputs.json').write_text(json.dumps({'candidate_manifest':str(root/'candidate-manifest.json'),'original_repair_root':str(old),'repair_root':str(new),'changed_replay_paths':len(events),'additional_exclusions':sorted(gaps)},indent=1))
    print(json.dumps({'repair_root':str(new),'events':len(merged),'additional_exclusions':sorted(gaps)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args();main(a.run)
