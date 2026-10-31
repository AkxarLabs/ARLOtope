"""Remote stop/resume generations and parked-question recovery; no SSH or model calls."""
import json
import os
import sys
import time
from types import SimpleNamespace

import labfiles
import pytest

from conftest import REPO
from test_remote_projects import configure, wait, worker  # noqa: F401 — reuse the isolated worker fixture

sys.path.insert(0, str(REPO / 'tools'))
import project_worker as W


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv('ARLOTOPE_HOME', str(tmp_path / 'home'))
    root = tmp_path / 'project'
    root.mkdir()
    worker = W.Worker()
    args = {'path': str(root), 'owner': 'owner', 'study': 'study', 'run_id': 'run'}
    worker.call('attach', args)
    agents = root / '.bus/arlotope/owner/agents'
    rd = agents / 'run.d'
    rd.mkdir(parents=True)
    manifest = agents / 'run.json'
    labfiles.write_json(manifest, {'run_id': 'run', 'status': 'killed', 'attempt': 1})
    monkeypatch.setattr(W.subprocess, 'Popen', lambda *a, **kw: SimpleNamespace(pid=54321))
    return worker, args, rd, manifest


def dispatch(state):
    worker, args, _rd, _manifest = state
    return worker.call('dispatch', {**args, 'manifest': {
        'run_id': 'run', 'status': 'resuming', 'attempt': 1, 'resume': {'mode': 'continue'}},
        'prompt': 'Continue', 'preamble': '', 'config': {}})


@pytest.mark.parametrize('legacy', [False, True])
def test_resume_clears_only_the_previous_attempt_stop(state, legacy):
    worker, args, rd, _manifest = state
    if legacy:
        (rd / 'stop').write_text('requested', encoding='utf-8')
    else:
        worker.call('command', {**args, 'id': 'stop-1', 'item': {'kind': 'stop', 'attempt': 1}})
    dispatch(state)
    assert not (rd / 'stop').exists()


def test_new_cancellation_before_resume_dispatch_is_preserved(state):
    worker, args, rd, _manifest = state
    worker.call('command', {**args, 'id': 'stop-2', 'item': {'kind': 'stop', 'attempt': 2}})
    dispatch(state)
    assert json.loads((rd / 'stop').read_text()) == {'attempt': 2}


def test_replayed_dispatch_cannot_erase_a_later_cancellation(state, monkeypatch):
    worker, args, rd, _manifest = state
    dispatch(state)
    worker.call('command', {**args, 'id': 'stop-2', 'item': {'kind': 'stop', 'attempt': 2}})
    from executor import procs
    monkeypatch.setattr(procs, 'pid_alive', lambda _pid: True)
    dispatch(state)
    assert json.loads((rd / 'stop').read_text()) == {'attempt': 2}


def test_delayed_stop_for_an_old_attempt_cannot_stop_the_new_one(state):
    worker, args, rd, _manifest = state
    dispatch(state)
    worker.call('command', {**args, 'id': 'delayed-stop-1', 'item': {'kind': 'stop', 'attempt': 1}})
    assert not (rd / 'stop').exists()


@pytest.mark.parametrize(('status', 'pid', 'expected'), [
    ('waiting_input', None, 'waiting_input'),
    ('waiting_input', 54321, 'failed'),
    ('running', 54321, 'failed'),
])
def test_poll_preserves_parked_questions_but_reconciles_lost_supervisors(state, status, pid, expected):
    worker, args, rd, manifest = state
    question = {'tool_use_id': 'question', 'input': {'questions': [{'question': 'Which method?'}]}}
    labfiles.write_json(manifest, {'run_id': 'run', 'status': status, 'attempt': 1, 'pid': pid,
                        'pending_question': question})
    receipt = rd / 'dispatch-0.json'
    labfiles.write_json(receipt, {'run_id': 'run'})
    os.utime(receipt, (time.time() - 60, time.time() - 60))
    result = worker.call('poll', args)['manifest']
    assert result['status'] == expected
    assert result['pending_question'] == question


def test_finished_status_written_before_lock_release_wins_over_reconciliation(state, monkeypatch):
    worker, args, rd, manifest = state
    labfiles.write_json(manifest, {'run_id': 'run', 'status': 'running', 'attempt': 1, 'pid': 54321})
    receipt = rd / 'dispatch-0.json'
    labfiles.write_json(receipt, {'run_id': 'run'})
    os.utime(receipt, (time.time() - 60, time.time() - 60))
    from executor import procs
    def finished(_path):
        labfiles.write_json(manifest, {'run_id': 'run', 'status': 'completed', 'attempt': 1, 'pid': None})
        return False
    monkeypatch.setattr(procs, 'is_locked', finished)
    assert worker.call('poll', args)['manifest']['status'] == 'completed'


def test_stop_a_parked_remote_question_without_a_supervisor(state):
    worker, args, rd, manifest = state
    labfiles.write_json(manifest, {'run_id': 'run', 'status': 'waiting_input', 'attempt': 1, 'pid': None,
                        'pending_question': {'tool_use_id': 'question'}})
    worker.call('command', {**args, 'id': 'stop-1', 'item': {'kind': 'stop', 'attempt': 1}})
    result = worker.call('poll', args)['manifest']
    assert result['status'] == 'killed'
    assert result['pending_question'] is None and not result['pending_questions']
    assert not (rd / 'stop').exists()


def test_stopped_remote_agent_resumes_on_the_first_try(hub, worker):
    import executor
    import remote_projects as remote
    import research_start
    root = worker['root'] / 'project'
    root.mkdir()
    research_start.create(hub.root, title='Remote study', question='Test recovery', local=str(root), machine='box')
    configure(hub)
    lab = executor.Lab(hub.root)
    run = executor.enqueue(lab, executor.RunSpec('ask', target='remote-study', prompt='ASK_PERMISSION'))
    executor.tick(lab)
    pending = wait(lab, run['run_id'], lambda m: bool(m.get('pending_permissions')))
    executor.stop(lab, run['run_id'])
    stopped = wait(lab, run['run_id'], lambda m: m['status'] == 'killed')
    assert stopped['session_id'] == pending['session_id']
    rd = root / '.bus/arlotope' / remote.owner(hub.root) / 'agents' / (run['run_id'] + '.d')
    assert (rd / 'stop').exists()
    executor.reply(lab, run['run_id'], 'Continue this conversation.')
    executor.tick(lab)
    finished = wait(lab, run['run_id'], lambda m: m['status'] in ('completed', 'failed', 'killed') and m.get('attempt') == 2)
    assert finished['status'] == 'completed', finished
    assert finished['session_id'] == stopped['session_id']
    assert not (rd / 'stop').exists()
