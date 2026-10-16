"""Rebuild cited validity-slice/withdrawal inputs removed from the retained cache.

Uses the original invalid-slice sample budget (3000, RNG seed0 in build_split),
reapplied after validity correction. Only dedicated fresh directories are supported.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from bgbench import config

run = Path(sys.argv[1])
while not (run / 'rpki-revalidation-complete.json').exists():
    time.sleep(10)

def task(tag, delta):
    folder = config.tgn_dir(2024, delta, tag)
    if next(folder.glob('*.pt'), None) is not None:
        raise ValueError(f'Refusing to mix rebuilt sample with existing tensors: {folder}')
    log = run / 'logs' / f'rebuild_2024_{tag}_d{delta}s.log'
    code = f'from bgbench.tgn_data import build_split; print(build_split(2024,{delta},max_events={3000 if tag == "rpkiinvalid" else None},tag={tag!r}))'
    with log.open('w') as stream:
        subprocess.run([sys.executable, '-u', '-c', code], check=True, stdout=stream, stderr=subprocess.STDOUT)
        subprocess.run([sys.executable, str(Path(__file__).with_name('repair_graph_history.py')), str(folder)], check=True, stdout=stream, stderr=subprocess.STDOUT)
    (folder / 'correction-impact.json').write_text(json.dumps({'rebuilt_from_replay': True, 'tag': tag, 'delta_s': delta, 'sampling_seed': 0, 'max_events': 3000 if tag == 'rpkiinvalid' else None}, indent=2))
    print('REBUILT', tag, delta, flush=True)

with ThreadPoolExecutor(max_workers=6) as pool:
    futures = [pool.submit(task, tag, delta) for tag in ('rpkivalid','rpkiinvalid','withdrawal') for delta in (30,60)]
    for f in futures:
        f.result()
