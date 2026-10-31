"""One attention projection, independent opt-in channels, and bounded desktop bursts."""
import json
import os
import shutil
import subprocess
import sys

import labfiles
import pytest

from conftest import REPO, kernel, load

sys.path.insert(0, str(REPO / 'tools'))
from executor import Lab, attention, manifest, notify
from test_executor import _queue, setup


def test_background_notifications_include_authoritative_lab_attention(hub, monkeypatch):
    import artifact
    import lab_attention
    from executor import campaigns
    k = kernel()
    hub.add_registry_row('study', title='Study', state='proposal')
    hub.produce('study')
    k.studies.move(hub.root, 'study', 'done')
    flag = k.watch.flag(hub.root, 'warn', 'Review changed evidence', study='study')
    published = artifact.publish('Choose a source', question='Which source?', choices=['A', 'B'], study='study', h=hub.root)
    labfiles.append_jsonl(hub.lab / '.bus/events.jsonl', {
        'kind': 'escalation', 'source': 'study', 'ts': labfiles.now(), 'detail': 'Need the original data',
        'data': {'id': 'data-request', 'severity': 'high'}})
    monkeypatch.setattr(lab_attention.panels, 'alert_items', lambda _hub: [
        {'panel': 'compute', 'title': 'Compute', 'say': 'Job needs attention', 'study': 'study', 'level': 'warn'}])
    monkeypatch.setattr(campaigns, 'all_states', lambda _lab: [
        {'name': 'night', 'status': 'paused', 'paused_reason': 'Sign in again', 'cycles': [], 'events': []}])
    lab = Lab(hub.root)
    rows = notify.items(lab)
    ids = {row['id'] for row in rows}
    assert {'cp:study:approve-proposal', f"flag:{flag['id']}", f"artifact:{published['id']}",
            'esc:data-request', 'alert:compute:study:Job needs attention', 'campaign:night:paused:0'} <= ids
    dashboard = load('dashboard/sources')
    monkeypatch.setattr(dashboard.ctx, 'HUB', hub.root)
    monkeypatch.setattr(dashboard.ctx, 'LAB', hub.lab)
    ui_ids = {row['id'] for row in dashboard.snapshot()['attention']}
    assert ids <= ui_ids
    attention.ack(lab, f"artifact:{published['id']}", 'seen')
    attention.ack(lab, f"flag:{flag['id']}", 'dismiss')
    assert not {f"artifact:{published['id']}", f"flag:{flag['id']}"} & {row['id'] for row in notify.items(lab)}
    assert notify.link({'link': 'https://lab.example'}, next(r for r in rows if r['kind'] == 'checkpoint')) == \
        'https://lab.example/#/study/study?checkpoint=approve-proposal'


def test_permission_request_id_reuse_in_a_new_attempt_is_new_attention(hub):
    lab = setup(hub)
    rid = _queue(lab, 1)[0]
    _target, _workdir, path, run = manifest.find_run(lab, rid)
    run.update(status='running', attempt=1, pending_permissions=[{'id': 'server-1', 'tool': 'Read'}])
    labfiles.write_json(path, run)
    first = next(row for row in attention.collect(lab) if row['kind'] == 'permission')
    attention.ack(lab, first['id'], 'seen')
    run['attempt'] = 2
    labfiles.write_json(path, run)
    second = next(row for row in attention.collect(lab) if row['kind'] == 'permission')
    assert first['id'] != second['id'] and not second['seen']


def test_revisiting_a_checkpoint_creates_new_notification_attention(hub):
    k = kernel()
    hub.add_registry_row('study', state='proposal')
    hub.produce('study')
    k.studies.move(hub.root, 'study', 'done')
    lab = Lab(hub.root)
    first = next(item for item in notify.items(lab) if item['kind'] == 'checkpoint')
    k.checkpoints.decide(hub.root, 'study', 'approve-proposal', via='cli')
    k.studies.move_to(hub.root, 'study', 'proposal', note='Revisit the proposal')
    k.checkpoints.decide(hub.root, 'study', 'approve-proposal', 'revoked', via='cli', note='Review again')
    k.studies.move(hub.root, 'study', 'done')
    second = next(item for item in notify.items(lab) if item['kind'] == 'checkpoint')
    assert first['id'] == 'cp:study:approve-proposal'
    assert second['id'] != first['id']


def test_stale_supervisor_alert_is_shared_but_parked_questions_are_not_stale():
    from lab_attention import stale_items
    run = {'schema': 2, 'run_id': 'quiet', 'status': 'running', 'heartbeat': '2020-01-01T00:00:00'}
    assert stale_items([run])[0]['id'] == 'stale:quiet'
    assert not stale_items([{**run, 'status': 'waiting_input'}])


def test_failed_channel_retries_without_duplicating_successful_delivery(hub, monkeypatch):
    lab = setup(hub)
    monkeypatch.setattr(notify, 'config', lambda _lab: {'ntfy': 'intercepted', 'webhook': 'intercepted'})
    monkeypatch.setattr(notify, 'items', lambda _lab: [{'id': 'question', 'kind': 'question', 'sev': 'block'}])
    calls = []
    def send(cfg, _item):
        calls.append(set(cfg))
        return ['webhook'] if len(calls) == 1 else []
    monkeypatch.setattr(notify, 'send', send)
    assert len(notify.check(lab, force=True)) == 1
    assert len(notify.check(lab, force=True)) == 1
    assert calls == [{'ntfy', 'webhook'}, {'webhook'}]
    assert notify.check(lab, force=True) == []


def test_large_pending_burst_is_not_evicted_from_delivery_history(hub, monkeypatch):
    lab = setup(hub)
    monkeypatch.setattr(notify, 'config', lambda _lab: {'ntfy': 'intercepted'})
    monkeypatch.setattr(notify, 'items', lambda _lab: [{'id': f'question-{i}'} for i in range(505)])
    monkeypatch.setattr(notify, 'send', lambda *_args: [])
    monkeypatch.setattr(notify, 'MAX_PER_CHECK', 1000)
    assert len(notify.check(lab, force=True)) == 505
    assert notify.check(lab, force=True) == []


def test_partial_channel_failure_does_not_starve_new_items(hub, monkeypatch):
    lab = setup(hub)
    monkeypatch.setattr(notify, 'config', lambda _lab: {'ntfy': 'intercepted', 'webhook': 'intercepted'})
    monkeypatch.setattr(notify, 'items', lambda _lab: [{'id': f'question-{i}'} for i in range(6)])
    calls = []
    def send(cfg, item):
        calls.append((item['id'], set(cfg)))
        return ['webhook']
    monkeypatch.setattr(notify, 'send', send)
    notify.check(lab, force=True)
    notify.check(lab, force=True)
    assert ('question-5', {'ntfy', 'webhook'}) in calls


def test_existing_delivery_ids_survive_the_channel_upgrade(hub, monkeypatch):
    lab = setup(hub)
    monkeypatch.setattr(notify, 'config', lambda _lab: {'ntfy': 'intercepted'})
    monkeypatch.setattr(notify, 'items', lambda _lab: [{'id': 'already-delivered'}])
    notify.state_path(lab).write_text(json.dumps({'ids': ['already-delivered']}))
    monkeypatch.setattr(notify, 'send', lambda *_args: pytest.fail('Repeated an existing delivery'))
    assert notify.check(lab, force=True) == []


def test_one_lab_delivery_does_not_suppress_another_lab(hub, tmp_path, monkeypatch):
    monkeypatch.setattr(notify, 'config', lambda _lab: {'ntfy': 'intercepted'})
    pending = []
    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target
        def start(self):
            pending.append(self.target)
    monkeypatch.setattr(notify.threading, 'Thread', DeferredThread)
    monkeypatch.setattr(notify, 'check', lambda _lab: None)
    notify.check_in_background(Lab(hub.root))
    notify.check_in_background(Lab(tmp_path / 'another-lab'))
    assert len(pending) == 2
    for finish in pending:
        finish()


def test_desktop_burst_groups_all_remaining_updates_and_opens_inbox():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the frontend notification callback check.')
    script = r"""
      const fs=require('fs'),vm=require('vm'),source=fs.readFileSync(FILE,'utf8');
      const snippet=source.slice(source.indexOf('  let seen = null;'),source.indexOf("  window.addEventListener('keydown'"));
      const notices=[],toasts=[],opened=[];
      function Notice(title,options){this.title=title;this.options=options;notices.push(this)}
      Notice.permission='granted';
      const NL={prefs:{notify:true},toast:title=>toasts.push(title),open:()=>opened.push('inbox'),
        InboxSheet:{},attOpen:item=>opened.push(item.id),attSubject:()=> 'Lab'};
      const document={hidden:true},window={Notification:Notice,focus(){}};
      vm.runInNewContext(snippet,{NL,document,window,Notification:Notice});
      const state=n=>({attention:Array.from({length:n},(_,i)=>({id:'q'+i,title:'Question '+i,sev:'block'}))});
      NL.onSnapshot(null,state(0)); NL.onSnapshot(null,state(6));
      if(notices.length!==3||notices[2].title!=='4 more updates in the Inbox')throw Error(JSON.stringify(notices));
      notices[2].onclick();if(opened[0]!=='inbox')throw Error('Summary did not open Inbox');
      NL.onSnapshot(null,state(6));if(notices.length!==3)throw Error('Repeated an unchanged burst');
      NL.prefs.notify=false;NL.onSnapshot(null,state(7));
      if(notices.length!==3||toasts.length!==4)throw Error('Desktop opt-out suppressed Inbox toast or sent a desktop notice');
      console.log('ok');
    """.replace('FILE', json.dumps(str(REPO / 'dashboard/static/ui/app.js')))
    result = subprocess.run([node, '-e', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('status,kind', [('failed', 'crashed'), ('completed', 'needs_pi')])
def test_final_supervisor_flushes_attention_without_a_dashboard_or_more_work(hub, monkeypatch, status, kind):
    from executor import scheduler
    lab = setup(hub)
    rid = _queue(lab, 1)[0]
    _target, _workdir, path, run = manifest.find_run(lab, rid)
    run.update(status=status, finished=labfiles.now(), reason='Provider stopped', pid=None)
    labfiles.write_json(path, run)
    if status == 'completed':
        labfiles.append_jsonl(lab.bus / 'events.jsonl', {
            'kind': 'run_report', 'run_id': rid, 'ts': labfiles.now(), 'data': {'needs_pi': 'other'}})
    monkeypatch.delenv('ARLOTOPE_NO_AUTOTICKER', raising=False)
    monkeypatch.setattr(notify, 'config', lambda _lab: {'ntfy': 'intercepted'})
    sent = []
    monkeypatch.setattr(notify, 'send', lambda _cfg, item: sent.append(item) or [])
    def handoff(_lab, **_kwargs):
        assert not scheduler.has_work(_lab)
        return False
    monkeypatch.setattr(scheduler, 'ensure_ticker', handoff)
    assert not scheduler.has_work(lab)
    scheduler.supervisor_finished(lab)
    assert manifest.read_manifest(path)['post_processed']
    assert any(item.get('run_id') == rid and item['kind'] == kind for item in sent)
    scheduler.supervisor_finished(lab)
    assert len([item for item in sent if item.get('run_id') == rid]) == 1


def test_final_tick_hands_delayed_work_to_a_live_ticker_instead_of_its_own_lease(hub, monkeypatch):
    from executor import scheduler
    from types import SimpleNamespace
    lab = setup(hub)
    rid = _queue(lab, 1)[0]
    _target, _workdir, path, run = manifest.find_run(lab, rid)
    run['not_before'] = '2099-01-01T00:00:00'
    labfiles.write_json(path, run)
    monkeypatch.delenv('ARLOTOPE_NO_AUTOTICKER', raising=False)
    monkeypatch.setattr(notify, 'config', lambda _lab: {})
    monkeypatch.setattr(scheduler, 'pid_alive', lambda pid: pid in (os.getpid(), 8123))
    spawned = []
    monkeypatch.setattr(scheduler.subprocess, 'Popen', lambda argv, **_kw: spawned.append(argv) or SimpleNamespace(pid=8123))
    scheduler.supervisor_finished(lab)
    assert len(spawned) == 1 and spawned[0][-2:] == ['serve', '--until-idle']
    assert scheduler.lease(lab)['pid'] == 8123
    scheduler.supervisor_finished(lab)
    assert len(spawned) == 1


def test_a_dead_dashboard_lease_does_not_hide_remaining_work(hub, monkeypatch):
    from executor import scheduler
    from types import SimpleNamespace
    lab = setup(hub)
    _queue(lab, 1)
    monkeypatch.delenv('ARLOTOPE_NO_AUTOTICKER', raising=False)
    scheduler.write_lease(lab, 'dashboard', pid=9876)
    monkeypatch.setattr(scheduler, 'pid_alive', lambda _pid: False)
    monkeypatch.setattr(scheduler.subprocess, 'Popen', lambda *_a, **_kw: SimpleNamespace(pid=8123))
    assert scheduler.ensure_ticker(lab)
    assert scheduler.lease(lab)['pid'] == 8123


def test_separate_processes_share_notification_delivery_ids(hub):
    lab = setup(hub)
    script = r'''
import sys,time
sys.path.insert(0,sys.argv[1])
from executor import Lab,notify
lab=Lab(sys.argv[2])
notify.config=lambda _lab: {'ntfy':'intercepted'}
notify.items=lambda _lab: [{'id':'shared-question','kind':'question'}]
def send(_cfg,_item):
    time.sleep(.15)
    with (lab.bus/'intercepted-notifications').open('a') as out:out.write('sent\n')
    return []
notify.send=send
notify.check(lab,force=True,wait=10)
'''
    argv = [sys.executable, '-c', script, str(REPO / 'tools'), str(lab.hub)]
    children = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
    for child in children:
        _out, error = child.communicate(timeout=30)
        assert child.returncode == 0, error.decode()
    assert (lab.bus / 'intercepted-notifications').read_text().splitlines() == ['sent']


def test_remote_supervisor_leaves_final_delivery_to_the_owner(hub, monkeypatch):
    from executor import scheduler, supervise
    lab = setup(hub)
    rid = _queue(lab, 1)[0]
    _target, _workdir, path, run = manifest.find_run(lab, rid)
    run.update(status='starting', remote_owner={'hub': 'owner'})
    labfiles.write_json(path, run)
    monkeypatch.setattr(supervise, '_attempt', lambda *_args: 0)
    monkeypatch.setattr(scheduler, 'supervisor_finished', lambda _lab: pytest.fail('Worker imported owner services'))
    assert supervise.supervise(lab, rid, 'hub') == 0
