"""Managed-session admission across studies, chat parking and workflow branches."""
import yaml
import pytest

from test_executor import Spawns, _queue, setup
import executor
from executor import manifest, scheduler


def _health(lab, monkeypatch):
    # Capacity checks do not need installed-provider version or authentication probes.
    with monkeypatch.context() as patch:
        patch.setattr(executor.backends, 'BACKENDS', ())
        return executor.health(lab)


def test_seven_studies_start_and_an_explicit_capacity_change_releases_the_eighth(hub):
    lab = setup(hub)
    queued = _queue(lab, 8)
    first = executor.tick(lab, spawn=Spawns())
    assert first['started'] == queued[:7]
    assert executor.find_run(lab, queued[-1])[3]['status'] == 'queued'
    # Native children belong to their harness; they do not become executor sessions.
    _, _, path, parent = executor.find_run(lab, queued[0])
    parent['subagents'] = {str(i): {'status': 'working'} for i in range(12)}
    manifest.write_manifest(path, parent)
    config = lab.config()
    config['agents']['programmatic']['max_concurrent_total'] = 8
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    assert executor.tick(lab, spawn=Spawns())['started'] == queued[7:]


def test_open_chat_reserves_a_slot_until_parked(hub, monkeypatch):
    lab = setup(hub)
    queued = _queue(lab, 8)
    executor.tick(lab, spawn=Spawns())
    _, _, path, chat = executor.find_run(lab, queued[0])
    chat.update(status='waiting_input', pid=424242)
    manifest.write_manifest(path, chat)
    monkeypatch.setattr(scheduler, 'is_locked', lambda _path: True)
    assert executor.tick(lab, spawn=Spawns())['started'] == []
    assert _health(lab, monkeypatch)['active'] == 7
    chat['pid'] = None
    manifest.write_manifest(path, chat)
    assert executor.tick(lab, spawn=Spawns())['started'] == queued[7:]


def test_hub_and_project_work_share_the_study_capacity(hub):
    lab = setup(hub, extra='    max_concurrent: 1\n')
    project = hub.make_project('shared')
    hub.add_registry_row('shared', state='active', project=str(project))
    hub_task = executor.enqueue(lab, executor.RunSpec('advance', target='shared'))['run_id']
    project_task = executor.enqueue(lab, executor.RunSpec('experiment', target='shared'))['run_id']
    other = executor.enqueue(lab, executor.RunSpec('advance', target='other-study'))['run_id']
    started = executor.tick(lab, spawn=Spawns())['started']
    assert len(set(started) & {hub_task, project_task}) == 1
    assert other in started


def test_lost_open_chat_supervisor_releases_capacity_but_parked_question_survives(hub):
    lab = setup(hub)
    rid = _queue(lab, 1)[0]
    _, workdir, path, run = executor.find_run(lab, rid)
    run.update(status='waiting_input', pid=None, session_id='saved-session')
    manifest.write_manifest(path, run)
    assert not scheduler.reconcile_manifest(lab, workdir, path, run)
    run['pid'] = 99999999
    manifest.write_manifest(path, run)
    assert scheduler.reconcile_manifest(lab, workdir, path, run)
    result = manifest.read_manifest(path)
    assert result['status'] == 'failed' and result['pid'] is None
    assert result['session_id'] == 'saved-session'


@pytest.mark.parametrize('support', [
    {'role': 'reviewer', 'workflow_node': 'independent-review'},
    {'role': 'fresh-context-reviewer'}, {'role': 'overseer'},
    {'assistant': True}, {'role': 'assistant'},
    {'explains': {'run': 'source'}, 'role': 'analyst'},
    {'judge': {'checkpoint': 'review'}}, {'role': 'explainer'},
])
def test_support_starts_when_all_task_slots_are_full(hub, monkeypatch, support):
    lab = setup(hub)
    queued = _queue(lab, 9)
    _, _, path, helper = executor.find_run(lab, queued[-1])
    helper.update(support)
    manifest.write_manifest(path, helper)
    started = executor.tick(lab, spawn=Spawns())['started']
    assert started == queued[:7] + queued[8:]
    assert executor.find_run(lab, queued[7])[3]['status'] == 'queued'
    health = _health(lab, monkeypatch)
    assert health['active'] == 8 and health['slots_used'] == 7


@pytest.mark.parametrize('subject', [None, 'idea-a'])
def test_support_does_not_consume_per_study_or_unscoped_capacity(hub, subject):
    lab = setup(hub, extra='    max_concurrent_total: 1\n    max_concurrent: 1\n    hub_max_concurrent: 1\n')
    queued = _queue(lab, 3)
    for rid in queued[:2]:
        _, _, path, helper = executor.find_run(lab, rid)
        helper.update(assistant=True, subject=subject)
        manifest.write_manifest(path, helper)
    assert executor.tick(lab, spawn=Spawns())['started'] == queued


def test_support_remains_live_for_recovery_accounting_and_ticker(hub, monkeypatch):
    lab = setup(hub)
    rid = _queue(lab, 1)[0]
    _, workdir, path, helper = executor.find_run(lab, rid)
    helper.update(assistant=True, status='waiting_input', pid=99999999, session_id='support-session',
                  attempts=[{'started': manifest.now()}])
    manifest.write_manifest(path, helper)
    monkeypatch.setattr(scheduler, 'is_locked', lambda _path: True)
    assert manifest.is_live(helper) and not manifest.uses_slot(helper)
    assert scheduler.has_work(lab)
    health = _health(lab, monkeypatch)
    assert health['active'] == 1 and health['slots_used'] == 0
    assert scheduler.daily_usage([helper])['attempts'] == 1
    monkeypatch.setattr(scheduler, 'is_locked', lambda _path: False)
    assert scheduler.reconcile_manifest(lab, workdir, path, helper)
    assert manifest.read_manifest(path)['status'] == 'failed'


def test_custom_task_roles_still_use_task_capacity():
    for role in ('analyst', 'writer', 'designer', 'general', 'custom-role'):
        assert manifest.uses_slot({'status': 'running', 'role': role})
    assert not manifest.uses_slot({'status': 'waiting_input', 'pid': None})
