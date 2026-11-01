import hashlib, json, os, time
from pathlib import Path
import pytest
from bgbench import forecast_custody as custody
import r2_fast_authorize


def sh(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(tmp):
    tmp = Path(tmp)
    (tmp / 'proto.txt').write_text('p'); (tmp / 'ledger.txt').write_text('l')
    arms, inputs = [], []
    for name in ('a1', 'a2'):
        d = tmp / name; d.mkdir()
        (d / 'model.bin').write_bytes(b'model' + name.encode())
        ins = []
        for i in range(2):
            ip = d / f'in{i}.json'; ip.write_text(json.dumps({'x': i, 'n': name}))
            ins.append(ip)
        manifest = {'protected_test': True, 'events': [
            {'event_id': f'{name}-{i}', 'split': 'test', 'input_path': str(ip), 'input_sha256': sh(ip)} for i, ip in enumerate(ins)]}
        (d / 'manifest.json').write_text(json.dumps(manifest))
        gate = {'passed': True, 'manifests': [{'sha256': sh(d / 'manifest.json')}]}
        (d / 'gate.json').write_text(json.dumps(gate))
        arms.append(dict(arm_id=name, event_ids=[f'{name}-0', f'{name}-1'], model_path=d / 'model.bin', manifest_path=d / 'manifest.json',
                         input_gate_path=d / 'gate.json', predictions_path=d / 'pred.json', commitment_path=d / 'commit.json'))
        inputs += ins
    fz = tmp / 'freeze.json'
    rec = custody.freeze(fz, protocol='t', arms=arms, scientific_protocol=tmp / 'proto.txt', exposure_ledger=tmp / 'ledger.txt')
    for a in json.loads(fz.read_text())['arms']:
        preds = [{'event_id': e, 'predicted_asns': [1.0, 2.0], 'candidate_asns': [1, 2], 'probabilities': [0.5, 0.5]} for e in a['event_ids']]
        Path(a['predictions_path']).write_text(json.dumps(preds))
        Path(a['commitment_path']).write_text(json.dumps(dict(
            predictions_sha256=sh(a['predictions_path']), manifest_sha256=a['manifest_sha256'], input_gate_sha256=a['input_gate_sha256'],
            checkpoint_sha256=a['model_sha256'], label_free_input_files=True)))
    seal = tmp / 'seal.json'
    custody.seal(fz, seal, expected_spec_sha256=sh(fz))
    return seal, json.loads(fz.read_text())['arms'], inputs


@pytest.fixture
def world(tmp_path):
    seal, arms, inputs = build(tmp_path)
    return seal, arms, inputs, time.time() + 1  # cutoff after all files


def patched(cutoff):
    class M:  # isolate: patch a stand-in so original stays callable
        hashed_json = staticmethod(custody.hashed_json); sha = staticmethod(custody.sha)
    r2_fast_authorize.install(M, cutoff)
    return M.authorize_outcome_join


def test_equal_and_pass(world):
    seal, arms, inputs, cutoff = world
    assert patched(cutoff)(seal) == custody.authorize_outcome_join(seal)


def touch_later(p, how):
    if how == 'append':
        with open(p, 'ab') as f: f.write(b' ')
    elif how == 'mtime_preserved':  # content change with restored mtime: ctime still moves
        st = os.stat(p); Path(p).write_bytes(Path(p).read_bytes()[:-1] + b'Z'); os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))


@pytest.mark.parametrize('which', ['input', 'predictions', 'commitment'])
@pytest.mark.parametrize('how', ['append', 'mtime_preserved'])
def test_modification_detected(world, which, how):
    seal, arms, inputs, _ = world
    target = {'input': inputs[0], 'predictions': arms[0]['predictions_path'], 'commitment': arms[0]['commitment_path']}[which]
    cutoff = time.time() + 0.5
    time.sleep(1.2)
    touch_later(target, how)
    with pytest.raises(ValueError):
        patched(cutoff)(seal)
    with pytest.raises(ValueError):
        custody.authorize_outcome_join(seal)  # the original also rejects (control)
