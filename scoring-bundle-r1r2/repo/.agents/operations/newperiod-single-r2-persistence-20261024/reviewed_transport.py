"""Explicit N-GBDT stage / submit-held / admit / independently authorized release.

Local code candidate. There are no default approvals, automatic release or retries.
Scientific logic, job and all six prerequisite bindings are preserved; reviewer policy accepts independent Codex.
"""
import argparse
import base64
import copy
import hashlib
import json
import os
import posixpath
import pwd
import re
import shlex
import stat
import subprocess
import types
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent / 'policy-candidate'
STAGE = Path('<FORECAST_ROOT>/'
             'newperiod-gbdt-transport-v1-20261020')
OUTPUT = STAGE.parent / 'newperiod-development-v1/campaigns/gbdt-v1'
BOOTSTRAP = '<RESULTS_ROOT>/work/vllm/miniforge/bin/python3.12'
TEMPLATE_SHA = '1dd39cf18e4ad518945d1a3c563946f0f2212a6effa96eb9ed84d8910fa07c13'
RUNNER_SHA = 'b0ac3ede4a028d4e5a2f1275591ecb7544600a5e482034d681724d81d448f9a2'
AUTHORS = ('/root', 'root', '/root/remaining_work_audit', 'remaining_work_audit',
           '/root/temporal_guard_recovery', 'temporal_guard_recovery', '/root/history_recovery', 'history_recovery')
EXTRA = ('package.json', 'adapter-spec.json', 'execution-approval.json', 'operation-approval.json',
         'execution-review.txt', 'operation-review.txt', 'resource-readiness.json')
RECORDS = ('stage-complete', 'submission-intent', 'submitted', 'admission-intent', 'admitted',
           'release-intent', 'release-complete')
LIMIT = 128 << 20


def need(ok, message):
    if not ok:
        raise ValueError(message)


def raw_json(doc):
    return (json.dumps(doc, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_file(path):
    path = Path(path)
    need(path.absolute() == path.resolve(), 'Canonical nonsymlink path required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        need(stat.S_ISREG(info.st_mode) and info.st_size <= LIMIT, 'Bounded regular file required')
        data = stream.read(LIMIT + 1)
    need(len(data) <= LIMIT, 'File grew beyond bound')
    return data


def write_new(path, doc):
    path = Path(path)
    need(path.parent.resolve() == path.parent.absolute(), 'Record parent must be canonical')
    with path.open('xb') as stream:
        stream.write(raw_json(doc))
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def independent(value):
    if not isinstance(value, str) or value != value.strip() or not value.strip():
        return False
    canonical = lambda s: posixpath.normpath('/' + s.casefold().lstrip('/')).rstrip('/')
    return canonical(value) not in {canonical(v) for v in (*AUTHORS, '/')}


def load_runner(raw):
    need(sha(raw) == RUNNER_SHA, 'Reviewed runner bytes changed')
    module = types.ModuleType('original_ngbdt_runner')
    exec(compile(raw, '<unchanged-ngbdt-runner>', 'exec'), module.__dict__)
    return module


def validate_files(files, directory):
    """Reuse original source/approval validation; no actual prerequisite reads here."""
    template = json.loads(files['template.json'])
    need(sha(files['template.json']) == TEMPLATE_SHA, 'Reviewed template changed')
    p = json.loads(files['package.json'])
    r = load_runner(files['run_package.py'])
    need(p.get('status') == 'actual_inputs_bound_pending_execution_review' and not r.blockers(p),
         'Actual release/seal/resource references remain pending')
    expected = copy.deepcopy(template)
    expected['status'] = p['status']
    for key, value in p['requirements'].items():
        old = template['requirements'][key]['path']
        need(old is None or value['path'] == old, 'Previously declared prerequisite path changed')
    expected['requirements'] = p['requirements']
    need(p == expected, 'Only original binder prerequisite/status changes are allowed')
    names = set(template['package_files']) | set(EXTRA) | {'template.json'}
    for sub, key in (('scientific-source', 'scientific'), ('guard-source', 'guard')):
        names |= {sub + '/' + n for n in template['sourceclosure'][key]} | {sub + '/snapshot.json'}
    need(set(files) == names, 'Missing or excess bundle members')
    need(sum(map(len, files.values())) <= 16 << 20, 'Code/metadata bundle exceeds 16 MiB')
    r.check_source_closure(p, directory)
    spec = r.resolved_spec(p)
    need(json.loads(files['adapter-spec.json']) == spec, 'Bound adapter spec differs')
    refs = {n: {'path': str(STAGE / n), 'sha256': sha(files[n])} for n in EXTRA}
    a, o = (json.loads(files[n]) for n in ('execution-approval.json', 'operation-approval.json'))
    need(a.get('operation_review') == refs['operation-approval.json'], 'Execution must bind operation approval')
    for doc, name in ((a, 'execution-review.txt'), (o, 'operation-review.txt')):
        need(doc.get('review') == refs[name], 'Review must name exact staged bytes')
        # Original checker reads only these two review paths. Local copies keep all authority fields and
        # hashes unchanged; substitute local paths solely for that byte check before transport.
        doc['review'] = {'path': str(directory / name), 'sha256': refs[name]['sha256']}
    r.check_approval(p, refs['package.json'], a, o, refs['adapter-spec.json'])
    need(independent(a.get('reviewer_agent')) and independent(o.get('review_session')),
         'Client authors cannot approve inherited execution/operation either')
    readiness = json.loads(files['resource-readiness.json'])
    need(p['requirements']['resource_readiness']['sha256'] == sha(files['resource-readiness.json'])
         and readiness.get('passed') is True and readiness.get('resources') == p['resources']
         and readiness.get('input_manifests') == spec['manifests']
         and readiness.get('retrospective_release') == spec['retrospective_release'],
         'Actual exact resource readiness required')
    return p


def bundle(directory):
    """Read only the known code/control closure; never glob a data directory."""
    directory = Path(directory).absolute()
    template_raw = read_file(BASE / 'package.json')
    template = json.loads(template_raw)
    # Pending refusal precedes other candidate reads and any transport.
    p = json.loads(read_file(directory / 'package.json'))
    r = load_runner(read_file(BASE / 'run_package.py'))
    need(not r.blockers(p), 'Actual release/seal/resource references remain pending')
    names = set(template['package_files']) | set(EXTRA)
    for sub, key in (('scientific-source', 'scientific'), ('guard-source', 'guard')):
        names |= {sub + '/' + n for n in template['sourceclosure'][key]} | {sub + '/snapshot.json'}
    files = {n: read_file(directory / n) for n in sorted(names)}
    files['template.json'] = template_raw
    validate_files(files, directory)
    return files


def anchor(files, source):
    return {'client_sha256': sha(source), 'files': {n: sha(v) for n, v in sorted(files.items())},
            'stage': str(STAGE)}


def check_transport(approval, review_raw, binding):
    need(approval.get('kind') == 'newperiod_gbdt_transport_approval_v1'
         and approval.get('passed') is True and approval.get('binding') == binding
         and approval.get('review_sha256') == sha(review_raw)
         and independent(approval.get('reviewer_agent'))
         and isinstance(approval.get('reviewer_model'), str) and bool(approval['reviewer_model'].strip())
         and approval.get('stage_authorized') is True and approval.get('submit_held_authorized') is True
         and approval.get('release_authorized') is False and approval.get('retry_authorized') is False,
         'Exact independent transport approval required; no automatic release')


def check_release(approval, review_raw, binding, admitted):
    need(approval.get('kind') == 'newperiod_gbdt_held_release_approval_v1'
         and approval.get('passed') is True and approval.get('binding') == binding
         and approval.get('admitted_sha256') == sha(raw_json(admitted))
         and approval.get('job_id') == admitted['job_id']
         and approval.get('review_sha256') == sha(review_raw)
         and independent(approval.get('reviewer_agent'))
         and isinstance(approval.get('reviewer_model'), str) and bool(approval['reviewer_model'].strip())
         and approval.get('release_authorized') is True and approval.get('retry_authorized') is False,
         'Separate exact actual-admission release approval required')


def prerequisites(p):
    """Only five reviewed metadata refs; no tensor, prediction or score artifact walk.

    Complete scientific release evidence is independently verified by the unchanged fit adapter before fitting.
    Here enforce actual metadata existence/hashes and release-complete state before stage/submission/release.
    """
    docs = {}
    for name, ref in p['requirements'].items():
        if name == 'resource_readiness':
            continue  # Included in the exact bundle, not yet on the host during stage.
        raw = read_file(ref['path'])
        need(sha(raw) == ref['sha256'], 'Actual prerequisite changed: ' + name)
        docs[name] = json.loads(raw)
    receipt = docs['retrospective_release']
    need(all(receipt.get(k) is True for k in ('passed', 'development_frozen', 'evaluation_release_complete')),
         'Actual R1 release is not complete')
    need(receipt.get('released_window') == {'start': '2025-09-01T00:00:00+00:00',
                                          'end': '2026-01-01T00:00:00+00:00'}, 'R1 release window differs')
    completed = datetime.fromisoformat(receipt['completed_utc'].replace('Z', '+00:00'))
    need(completed.tzinfo is not None and completed <= datetime.now(timezone.utc), 'Invalid R1 completion clock')
    for horizon in (30, 60):
        need(docs['core_gate' + str(horizon)].get('retrospective_release_sha256')
             == p['requirements']['retrospective_release']['sha256'], 'Development gate R1 binding differs')
    need(not OUTPUT.exists() and not OUTPUT.is_symlink(), 'Prior scientific attempt exists')


def remote_action(payload):
    """Stdlib-only batch-host control. Invoked from reviewed source supplied on stdin."""
    need(pwd.getpwuid(os.getuid()).pw_name == '<USER>', 'Wrong cluster owner')
    need(STAGE.parent.resolve() == STAGE.parent, 'Stage parent must be canonical')
    files = {n: base64.b64decode(v, validate=True) for n, v in payload['files'].items()}
    binding = anchor(files, payload['source'].encode())
    approval = json.loads(payload['approval'])
    check_transport(approval, payload['review'].encode(), binding)
    action = payload['action']
    need(action in ('stage', 'preflight', 'record', 'get'), 'Unknown host operation')
    if action == 'stage':
        # The local check validated full closure and both scientific approvals. Before the first host write,
        # validate fixed member names/digests and actual prerequisite refs; repeat original validators after copy.
        template = json.loads(files['template.json'])
        need(sha(files['template.json']) == TEMPLATE_SHA, 'Template differs')
        p = json.loads(files['package.json'])
        need(not load_runner(files['run_package.py']).blockers(p), 'Pending prerequisites')
        prerequisites(p)
        need(not STAGE.exists() and not STAGE.is_symlink(), 'Stage exists; do not retry')
        STAGE.mkdir()
        for name, raw in files.items():
            rel = Path(name)
            need(not rel.is_absolute() and '..' not in rel.parts and str(rel) == name,
                 'Noncanonical bundle member')
            target = STAGE / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            target.chmod(0o444)
        validate_files(files, STAGE)
        write_new(STAGE / 'stage-complete.json', {'binding': binding})
        return {'binding': binding, 'stage_complete': True}
    need(STAGE.resolve() == STAGE, 'Staged root is not canonical')
    for name, raw in files.items():
        need(read_file(STAGE / name) == raw, 'Staged bytes changed: ' + name)
    validate_files(files, STAGE)
    need(json.loads(read_file(STAGE / 'stage-complete.json')) == {'binding': binding}, 'Stage receipt differs')
    if action == 'preflight':
        prerequisites(json.loads(files['package.json']))
        return {'binding': binding, 'preflight_passed': True}
    name = payload['name']
    need(name in RECORDS[1:], 'Unexpected operational record')
    if action == 'get':
        doc = json.loads(read_file(STAGE / (name + '.json')))
        need(doc.get('binding') == binding, 'Record binding differs')
        return doc
    doc = payload['document']
    need(doc.get('binding') == binding, 'New record binding differs')
    index = RECORDS.index(name)
    previous = json.loads(read_file(STAGE / (RECORDS[index - 1] + '.json')))
    need(previous.get('binding') == binding, 'Predecessor binding differs')
    if name not in ('submission-intent',):
        need(isinstance(doc.get('job_id'), str) and re.fullmatch(r'[1-9][0-9]*', doc['job_id']), 'Job identity required')
        if 'job_id' in previous:
            need(doc['job_id'] == previous['job_id'], 'Job identity changed')
    if name == 'release-intent':
        check_release(payload['release_approval'], payload['release_review'].encode(), binding, previous)
    write_new(STAGE / (name + '.json'), doc)
    return doc


def held_job(text, job_id, p):
    """Conservative scontrol -o parser: unexpected/missing admission fields refuse."""
    need('\n' not in text.strip(), 'Expected exactly one job record')
    fields = {}
    for part in shlex.split(text):
        if '=' in part:
            key, value = part.split('=', 1)
            need(key not in fields, 'Duplicate scheduler field')
            fields[key] = value
    expected = {'JobId': job_id, 'JobName': 'bg-n-gbdt2', 'JobState': 'PENDING', 'Reason': 'JobHeldUser',
                'Priority': '0', 'Partition': 'cpu', 'NumCPUs': str(p['resources']['cpu_threads']),
                'NumTasks': '1', 'CPUs/Task': str(p['resources']['cpu_threads']),
                'Requeue': '0', 'Restarts': '0', 'TimeLimit': '1-00:00:00',
                'WorkDir': str(STAGE), 'Command': str(STAGE / 'job.sbatch'), 'Dependency': '(null)',
                'ReqNodeList': '(null)', 'ExcNodeList': '(null)',
                'StdOut': str(STAGE / ('job-' + job_id + '.stdout')),
                'StdErr': str(STAGE / ('job-' + job_id + '.stderr'))}
    need(all(fields.get(k) == v for k, v in expected.items())
         and fields.get('NumNodes') in ('1', '1-1'), 'Held job identity/resources differ')
    need(re.fullmatch(r'<USER>\([0-9]+\)', fields.get('UserId', '')), 'Held job owner differs')
    need(not any(k.startswith('Array') for k in fields), 'Unexpected job array')
    tres = dict(x.split('=', 1) for x in fields.get('ReqTRES', '').split(',') if '=' in x)
    need(set(tres) <= {'cpu', 'mem', 'node', 'billing'} and tres.get('cpu') == '4'
         and tres.get('node') == '1' and tres.get('mem') in ('256G', '262144M'), 'Requested TRES differs')
    need(fields.get('MinMemoryNode') in ('256G', '262144M'), 'Requested memory differs')
    return fields


def command(argv, *, host, data=None):
    # Remove local overrides; explicitly clear remote SBATCH_* via env -i for scheduler calls.
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SBATCH_', 'SLURM_'))}
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=30', host, shlex.join(argv)],
                            input=data, text=True, capture_output=True, check=False, timeout=300, env=env)
    need(len(result.stdout) + len(result.stderr) <= 8 << 20, 'Operational response exceeds bound')
    return {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}


class Client:
    def __init__(self, directory, records, approval_path, approval_sha, review_path, transport=command):
        self.files = bundle(directory)
        self.p = json.loads(self.files['package.json'])
        self.source = read_file(Path(__file__).resolve())
        self.binding = anchor(self.files, self.source)
        self.approval = read_file(approval_path)
        need(sha(self.approval) == approval_sha, 'External transport approval hash differs')
        self.review = read_file(review_path)
        check_transport(json.loads(self.approval), self.review, self.binding)
        self.records, self.transport = Path(records).absolute(), transport
        self.records.mkdir(parents=True, exist_ok=True)
        need(self.records.resolve() == self.records, 'Local records must be canonical')

    def record(self, name, doc):
        write_new(self.records / (name + '.json'), doc)

    def remote(self, action, **extra):
        payload = {'source': self.source.decode(), 'files': {n: base64.b64encode(v).decode() for n, v in self.files.items()},
                   'approval': self.approval.decode(), 'review': self.review.decode(), 'action': action, **extra}
        boot = "import json,sys; x=json.load(sys.stdin); ns={'__name__':'ngbdt_remote','__file__':'<stdin>'}; " \
               "exec(compile(x['source'],'<reviewed-client>','exec'),ns); print(json.dumps(ns['remote_action'](x)))"
        response = self.transport([BOOTSTRAP, '-I', '-S', '-B', '-c', boot], host='<BATCH_HOST>', data=json.dumps(payload))
        index = 0
        while (self.records / ('host-response-%04d.json' % index)).exists():
            index += 1
        self.record('host-response-%04d' % index, {'action': action, **response})
        need(response['returncode'] == 0, 'Host action failed or uncertain; preserve state, never retry')
        return json.loads(response['stdout'])

    def mutation_record(self, name, doc, **extra):
        self.record(name, doc)
        return self.remote('record', name=name, document=doc, **extra)

    def scheduler(self, name, argv):
        # Only Slurm control commands run on the dispatcher. Bare ALL overrides inherited export behavior;
        # env -i also prevents other inherited SBATCH_* options from changing the held request.
        response = self.transport(['env', '-i', 'PATH=/usr/local/bin:/usr/bin:/bin', *argv], host='<SUBMIT_HOST>')
        self.record(name, response)
        need(response['returncode'] == 0, 'Scheduler failed or uncertain; preserve intent, never retry')
        return response['stdout']

    def stage(self):
        self.record('stage-intent', {'binding': self.binding})
        self.record('stage-result', self.remote('stage'))

    def submit_held(self):
        self.remote('preflight')
        self.mutation_record('submission-intent', {'binding': self.binding})
        args = [sha(self.files[n]) for n in ('package.json', 'execution-approval.json', 'operation-approval.json')]
        argv = load_runner(self.files['run_package.py']).submission_argv(str(STAGE), *args)
        # Explicit allocation CLI pins supplement the unchanged job; no nodes or extra tasks allowed.
        argv[1:1] = ['--nodes=1', '--ntasks=1', '--partition=cpu', '--cpus-per-task=4', '--mem=262144M',
                     '--time=24:00:00', '--no-requeue', '--job-name=bg-n-gbdt2']
        stdout = self.scheduler('submission-response', argv)
        need(re.fullmatch(r'[1-9][0-9]*\n?', stdout), 'Ambiguous job identity; never resubmit')
        doc = {'binding': self.binding, 'job_id': stdout.strip(), 'argv': argv}
        self.mutation_record('submitted', doc)
        return doc  # Deliberately no admission or release here.

    def admit(self):
        submitted = self.remote('get', name='submitted')
        doc = {'binding': self.binding, 'job_id': submitted['job_id']}
        self.mutation_record('admission-intent', doc)
        text = self.scheduler('admission-response', ['scontrol', '-o', 'show', 'job', doc['job_id']])
        fields = held_job(text, doc['job_id'], self.p)
        self.remote('preflight')
        return self.mutation_record('admitted', {**doc, 'scheduler': fields, 'scheduler_text_sha256': sha(text.encode())})

    def release(self, approval_path, approval_sha, review_path):
        admitted = self.remote('get', name='admitted')
        raw, review = read_file(approval_path), read_file(review_path)
        need(sha(raw) == approval_sha, 'External release approval hash differs')
        a = json.loads(raw)
        check_release(a, review, self.binding, admitted)
        doc = {'binding': self.binding, 'job_id': admitted['job_id'], 'release_approval_sha256': sha(raw)}
        # Durable intents precede even the fresh readback; any subsequent error leaves the job held.
        self.mutation_record('release-intent', doc, release_approval=a, release_review=review.decode())
        text = self.scheduler('release-readback', ['scontrol', '-o', 'show', 'job', admitted['job_id']])
        held_job(text, admitted['job_id'], self.p)
        self.remote('preflight')
        self.scheduler('release-response', ['scontrol', 'release', admitted['job_id']])
        return self.mutation_record('release-complete', doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'submit-held', 'admit', 'release'))
    for name in ('candidate', 'records', 'approval', 'approval-sha256', 'review'):
        parser.add_argument('--' + name, required=True)
    for name in ('release-approval', 'release-approval-sha256', 'release-review'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    if args.action == 'release':
        need(all((args.release_approval, args.release_approval_sha256, args.release_review)), 'Separate release review required')
    client = Client(args.candidate, args.records, args.approval, args.approval_sha256, args.review)
    if args.action == 'release':
        result = client.release(args.release_approval, args.release_approval_sha256, args.release_review)
    else:
        result = getattr(client, args.action.replace('-', '_'))()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
