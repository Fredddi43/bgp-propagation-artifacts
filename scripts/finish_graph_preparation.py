"""Apply causal-history repair as each independent tensor refresh completes."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time

from bgbench import config

root = config.DATA_ROOT / 'tgn'
futures = {}

def repair(folder):
    return subprocess.run([sys.executable, str(Path(__file__).with_name('repair_graph_history.py')), str(folder)], check=True)

with ThreadPoolExecutor(max_workers=8) as pool:
    while True:
        directories = [f.parent for f in root.glob('*/*/correction-impact.json')
                       if (lambda d: d.get('events') or d.get('added_ids') or d.get('rebuilt_from_replay'))(json.loads(f.read_text()))
                       and next(f.parent.glob('*.pt'), None) is not None]
        for directory in directories:
            if directory not in futures and not (directory / 'history-correction.json').exists():
                futures[directory] = pool.submit(repair, directory)
        for directory, future in list(futures.items()):
            if future.done():
                future.result()
        if Path(sys.argv[1]).exists() and all(future.done() for future in futures.values()):
            break
        time.sleep(10)
