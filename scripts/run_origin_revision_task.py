"""Execute one immutable origin-membership correction task."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('manifest', type=Path)
parser.add_argument('index', type=int)
args = parser.parse_args()
task = json.loads(args.manifest.read_text())[args.index]
scripts = Path(__file__).parent
if task['mode'] == 'inference':
    command = [sys.executable, '-u', str(scripts / 'rescore_unchanged_graph_checkpoint.py'), task['summary'], task['proof']]
else:
    command = [sys.executable, '-u', str(scripts / 'rerun_graph_result.py'), task['summary']]
subprocess.run(command, check=True)
