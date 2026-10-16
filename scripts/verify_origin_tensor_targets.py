"""Compare all train/test origin graph tensor target sets with canonical event tables."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import numpy as np
import polars as pl
import torch


def one(item):
    path,expected=item
    tensor=torch.load(path,weights_only=False,map_location='cpu',mmap=True)
    actual={'seed':set(tensor['seed_asns'].tolist()),'final':set(tensor['target_asns'].tolist())}
    differences={key:{'only_tensor':sorted(actual[key]-set(expected[key])),'only_source':sorted(set(expected[key])-actual[key])}
                 for key in actual if actual[key]!=set(expected[key])}
    curve=np.asarray(tensor['curve']).reshape(-1).tolist()
    if curve!=expected['curve']:differences['curve']={'tensor':curve,'source':expected['curve']}
    return {'event_id':tensor['event_id'],'split':tensor['split'],'file':str(path),'differences':differences}


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source={r['event_id']:r for r in pl.read_parquet(a.run/'data/eventset/2024/events.parquet').select('event_id','set_d30s','set_d1m','set_T5m','set_T15m','set_T60m','set_final_2h').to_dicts()}
    records=[];counts={}
    for tag in ['rpkivalid','rpkiinvalid']:
        for delta,col in [(30,'set_d30s'),(60,'set_d1m')]:
            folder=a.run/f'graph-final-data/tgn/2024_{tag}/d{delta}s';index=pl.read_csv(folder/'index.csv')
            items=[]
            for eid in index['event_id']:
                row=source[eid];items.append((folder/f'{eid}.pt',{'seed':row[col],'final':row['set_final_2h'],
                    'curve':[len(row[c]) for c in ['set_T5m','set_T15m','set_T60m','set_final_2h']]}))
            with ProcessPoolExecutor(max_workers=8) as pool:results=list(pool.map(one,items,chunksize=16))
            key=f'{tag}/d{delta}';counts[key]={split:sum(r['split']==split for r in results) for split in ['train','test']}
            changes=[{**r,'cohort':key} for r in results if r['differences']];records.extend(changes)
            print(key,len(results),len(changes),flush=True)
    a.output.write_text(json.dumps({'cohorts':counts,'changed_tensors':records},indent=2)+'\n')


if __name__=='__main__':main()
