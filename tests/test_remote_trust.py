"""What another machine (or an agent) writes is data: it never chooses a local path or runs on the local origin."""
import base64
import json
import sys
from types import SimpleNamespace

import labfiles
import pytest

from conftest import REPO, load
sys.path.insert(0, str(REPO/'tools'))
import remote_projects as R


@pytest.fixture
def remote_run(hub, monkeypatch):
    """A dispatched remote run and a hostile worker: `answer` is what its poll returns."""
    from executor import Lab, manifest
    hub.add_registry_row('s', project=R.uri('box', '/work'))
    lab = Lab(hub.root)
    path = lab.agents_dir(lab.project_workdir('s'))/'remote-run.json'
    manifest.run_dir(path.parent, 'remote-run').mkdir(parents=True)
    local = {'schema': 2, 'run_id': 'remote-run', 'target': 's', 'subject': 's', 'status': 'running',
             'stream': 'remote-run.stream.jsonl', 'remote': {'machine': 'box', 'path': '/work'},
             'remote_dispatched': True}
    labfiles.write_json(path, local)
    answer, sent = {'found': True, 'manifest': dict(local), 'requests': [], 'stream': '', 'offset': 0}, []
    def call(hub_, slug, method, **data):
        sent.append((method, data))
        return answer if method == 'poll' else {}
    monkeypatch.setattr(R, 'call', call)
    return SimpleNamespace(lab=lab, path=path, answer=answer, sent=sent,
                           record=lambda: manifest.read_manifest(path))


def test_remote_manifest_cannot_choose_local_paths_or_identity(remote_run, tmp_path):
    victim = tmp_path/'outside.txt'
    remote_run.answer.update(stream=base64.b64encode(b'bytes from the remote\n').decode(), offset=999_999_999_999,
        manifest={'status': 'completed', 'last_message': 'done', 'stream': str(victim), 'subject': 'other',
                  'target': 'other', 'run_id': 'other', 'cwd': str(tmp_path), 'skill': 'x', 'judge': True,
                  'workflow_node': 'n', 'last_result': {'id': 'r', 'at': 'now', 'file': '../../../secret.json'}})
    R.sync(remote_run.lab)
    m = remote_run.record()
    assert not victim.exists()
    assert remote_run.path.with_suffix('.stream.jsonl').read_bytes() == b'bytes from the remote\n'
    assert m['status'] == 'completed' and m['last_message'] == 'done' and m['remote_status'] == 'connected'
    assert (m['stream'], m['subject'], m['target'], m['run_id']) == ('remote-run.stream.jsonl', 's', 's', 'remote-run')
    assert not {'cwd', 'skill', 'judge', 'workflow_node', 'last_result'} & set(m)
    assert m['remote_offset'] == len(b'bytes from the remote\n')  # this Lab counts its own bytes


def test_remote_manifest_with_an_unknown_status_is_not_merged(remote_run):
    remote_run.answer['manifest'] = {'status': 'pwned', 'last_message': 'nope'}
    R.sync(remote_run.lab)
    m = remote_run.record()
    assert m['status'] == 'running' and 'last_message' not in m and m['remote_status'] == 'disconnected'


@pytest.mark.parametrize('bad', ['../../../../outside_receipt', '/etc/passwd', 'C:/Users/x/.codex/auth', '', None, 7])
def test_remote_request_id_never_becomes_a_local_path(remote_run, tmp_path, bad):
    secret = tmp_path/'secret.json'
    secret.write_text(json.dumps({'OPENAI_API_KEY': 'sk-FAKE'}))
    remote_run.answer['requests'] = [{'id': str(secret.with_suffix('')), 'run_id': 'remote-run', 'verb': 'x'},
                                     {'id': bad, 'run_id': 'remote-run', 'verb': 'x'}, 'not a request',
                                     {'id': 'ok-1', 'run_id': 'remote-run', 'verb': 'nope'}]
    R.sync(remote_run.lab)
    responses = [data for method, data in remote_run.sent if method == 'response']
    assert [r['id'] for r in responses] == ['ok-1'] and 'sk-FAKE' not in json.dumps(responses)
    receipts = remote_run.path.parent/'remote-run.d/controller-receipts'
    assert [p.name for p in receipts.iterdir()] == ['ok-1.json']
    assert not list(tmp_path.rglob('outside_receipt.json'))
