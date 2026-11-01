"""Local assembly from externally supplied exact metadata; never freeze or approve."""
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('baseline_transport',HERE/'client.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
RUNNER=HERE


def assemble(batch,templates,source_files,freeze_raw):
    """Callers supply the complete actual batch. Pending job IDs remain in templates only."""
    files=dict(source_files)
    c.need(batch['source_files']=={n:c.sha(v) for n,v in source_files.items()},'Explicit source manifest differs')
    files.update({n:(HERE/n).read_bytes() for n in ('client.py','bootstrap.py','reviewed_transport.py')})
    files.update({n:(RUNNER/n).read_bytes() for n in ('runner.py','pins.json')})
    files['freeze-capture.json']=freeze_raw
    c.need(set(templates)=={j['template'] for j in batch['jobs']},'Exact complete template set required')
    files.update({n:c.encode(v) for n,v in templates.items()})
    files['batch.json']=c.encode(batch)
    files.update({f'job-{i:03}.sbatch':c.job_script(batch,i,c.sha(files['batch.json'])) for i in range(len(batch['jobs']))})
    c.check_batch(batch,files)
    return files


def write_package(destination,files):
    """Exclusive local output only; no approvals are minted."""
    destination=Path(destination);destination.mkdir()
    for n,raw in files.items():
        rel=Path(n);c.need(not rel.is_absolute() and '..' not in rel.parts,'Unsafe relative package member')
        path=destination/rel;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as out:out.write(raw)
    return c.binding(files)
