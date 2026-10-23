"""Snapshot reads stay bounded and fresh without sharing request-local data across threads."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest

from conftest import REPO, kernel, load


@pytest.mark.parametrize('route,code,fresh', [('/api/starter', 201, True),
                                          ('/api/starter', 400, False),
                                          ('/api/libdoc', 200, False)])
def test_created_study_is_visible_before_snapshot_ttl_expires(hub, monkeypatch, route, code, fresh):
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    server = load('dashboard/serve')
    monkeypatch.setattr(server.ctx, 'HUB', hub.root)
    monkeypatch.setattr(server.ctx, 'LAB', hub.lab)
    monkeypatch.setattr(server.settings, 'setup_status', lambda: {})
    monkeypatch.setattr(server.term, 'desktop', lambda: False)
    monkeypatch.setattr(server.term, 'has_pty', lambda: False)
    # Freeze the clock: this tests invalidation, not a lucky cache expiry.
    monkeypatch.setattr(server.time, 'time', lambda: 100)
    rows = []
    monkeypatch.setattr(server.sources, 'snapshot', lambda: {'items': list(rows)})
    server._forget_snapshot()
    assert server._snapshot_cached()['items'] == []
    def create(_body):
        rows.append({'id': 'new-study'})
        return {'ok': code == 201}, code
    monkeypatch.setitem(server.POST_ROUTES, route, create)
    handler = object.__new__(server.Handler)
    handler.path = route
    handler._body = lambda: {}
    handler._json = lambda body, code: (body, code)
    handler._dispatch_post()
    assert server._snapshot_cached()['items'] == (rows if fresh else [])
    server._forget_snapshot()


@pytest.mark.parametrize('count', [1, 6])
def test_snapshot_reads_registry_and_model_once(hub, monkeypatch, count):
    for i in range(count):
        hub.add_registry_row(f'idea-{i}')
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    server = load('dashboard/serve')
    monkeypatch.setattr(server.ctx, 'HUB', hub.root)
    monkeypatch.setattr(server.ctx, 'LAB', hub.lab)
    monkeypatch.setattr(server.sources.attention, 'executor_status', lambda: {})
    monkeypatch.setattr(server.term, 'desktop', lambda: False)
    monkeypatch.setattr(server.term, 'has_pty', lambda: False)
    server._forget_snapshot()
    k = kernel()
    calls = {'rows': 0, 'signature': 0}
    rows, signature = k.studies.rows, k.model._sig
    def read_rows(*args, **kwargs):
        calls['rows'] += 1
        return rows(*args, **kwargs)
    def read_signature(*args, **kwargs):
        calls['signature'] += 1
        return signature(*args, **kwargs)
    monkeypatch.setattr(k.studies, 'rows', read_rows)
    monkeypatch.setattr(k.model, '_sig', read_signature)
    assert len(server._snapshot_cached()['items']) == count
    assert calls == {'rows': 1, 'signature': 1}
    calls.update(rows=0, signature=0)
    idea = hub.root / 'studies/idea-0/IDEA.md'
    idea.write_text('---\ntitle: Changed title\n---\n', encoding='utf-8')
    server._forget_snapshot()
    assert server._snapshot_cached()['items'][0]['title'] == 'Changed title'
    assert calls == {'rows': 1, 'signature': 1}, 'each snapshot must reread changed files'


def test_read_batches_do_not_hide_later_config_or_workflow_edits(hub):
    import shutil
    import labfiles
    import yaml
    k = kernel()
    shutil.copytree(REPO / 'workflow', hub.root / 'workflow')
    steps = hub.root / 'workflow/steps.yaml'
    original = yaml.safe_load(steps.read_text(encoding='utf-8'))
    with labfiles.read_batch():
        first = k.model.load(hub.root)
        config = labfiles.config(hub.root)
        changed = dict(original)
        changed['seed'] = {**original['seed'], 'label': 'Changed seed'}
        steps.write_text(yaml.safe_dump(changed), encoding='utf-8')
        (hub.lab / 'config.yaml').write_text('lab:\n  name: Changed lab\n', encoding='utf-8')
        assert k.model.load(hub.root) is first
        assert labfiles.config(hub.root) is config
    assert k.model.load(hub.root)['steps']['seed']['label'] == 'Changed seed'
    assert labfiles.config(hub.root)['lab']['name'] == 'Changed lab'


def test_project_enumeration_resolves_rows_without_registry_relookup(hub, monkeypatch):
    import executor
    import labfiles
    lab = executor.Lab(hub.root)
    local = hub.make_project('local')
    monkeypatch.setattr(lab, 'registry_rows', lambda: [
        {'id': 'local', 'project': str(local)},
        {'id': 'duplicate', 'project': str(local)},
        {'id': 'remote', 'project': 'arlotope+ssh://machine/home/project'},
    ])
    def relookup(*args):
        raise AssertionError('already have the registry row')
    monkeypatch.setattr(labfiles, 'row', relookup)
    assert lab.project_dirs() == [('local', local), ('remote', hub.lab / '.bus/remote-projects/remote')]


def test_checkpoint_request_reuses_reads_but_sees_later_changes(hub, monkeypatch):
    import shutil
    import yaml
    shutil.copytree(REPO / 'workflow', hub.root / 'workflow')
    hub.add_registry_row('review', state='internal-review')
    k = kernel()
    k.studies.move(hub.root, 'review', 'done')
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    server = load('dashboard/serve')
    monkeypatch.setattr(server.ctx, 'HUB', hub.root)
    monkeypatch.setattr(server.ctx, 'LAB', hub.lab)
    calls = {'rows': 0, 'signature': 0}
    rows, signature = k.studies.rows, k.model._sig
    def read_rows(*args, **kwargs):
        calls['rows'] += 1
        return rows(*args, **kwargs)
    def read_signature(*args, **kwargs):
        calls['signature'] += 1
        return signature(*args, **kwargs)
    monkeypatch.setattr(k.studies, 'rows', read_rows)
    monkeypatch.setattr(k.model, '_sig', read_signature)
    query = {'study': 'review', 'id': 'finalize-paper'}
    first, code = server.decisions.checkpoint_view(query)
    assert code == 200 and first['waiting'] and not first['approved']
    assert calls == {'rows': 1, 'signature': 1}
    main = hub.root / 'studies/review/paper/main.pdf'
    assert not next(e for e in first['evidence'] if e['name'] == 'main.pdf')['exists']
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_bytes(b'%PDF-fixture')
    workflow = hub.root / 'workflow/workflows/research.yaml'
    definition = yaml.safe_load(workflow.read_text(encoding='utf-8'))
    next(cp for cp in definition['checkpoints'] if cp['id'] == 'finalize-paper')['title'] = 'Updated review'
    workflow.write_text(yaml.safe_dump(definition), encoding='utf-8')
    k.checkpoints.decide(hub.root, 'review', 'finalize-paper', via='cli')
    calls.update(rows=0, signature=0)
    second, code = server.decisions.checkpoint_view(query)
    assert code == 200 and second['approved'] and not second['waiting']
    assert second['checkpoint']['title'] == 'Updated review'
    assert next(e for e in second['evidence'] if e['name'] == 'main.pdf')['exists']
    assert calls == {'rows': 1, 'signature': 1}, 'a new request must see edits and decisions'


@pytest.mark.parametrize('attached', [False, True])
def test_checkpoint_evidence_resolves_local_project_once(hub, monkeypatch, attached):
    k = kernel()
    project = hub.make_project('evidence', in_root=not attached)
    hub.add_registry_row('evidence', project=str(project) if attached else '-')
    (project / 'notes.md').write_text('Notes', encoding='utf-8')
    (project / 'reviews').mkdir()
    original = k.checkpoints.project_dir
    calls = []
    def resolve(*args):
        calls.append(args)
        return original(*args)
    monkeypatch.setattr(k.checkpoints, 'project_dir', resolve)
    refs = ['{project}/notes.md', '{project}/missing.md', '{project}/reviews', 'studies/{study}/IDEA.md']
    evidence = k.checkpoints.evidence(hub.root, 'evidence', {'evidence': refs})
    assert len(calls) == 1
    assert [e['exists'] for e in evidence] == [True, False, True, True]
    assert evidence[2]['dir']
    assert evidence[0]['path'] == (project / 'notes.md').as_posix()
    assert evidence[3]['path'] == 'studies/evidence/IDEA.md'


@pytest.mark.parametrize('disconnected', [False, True])
def test_checkpoint_remote_evidence_is_one_read_with_local_fallback(hub, monkeypatch, disconnected):
    import remote_projects as remote
    k = kernel()
    hub.add_registry_row('remote', project=remote.uri('box', '/research/my project'))
    local = hub.root / 'studies/remote/IDEA.md'
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text('Hub notes', encoding='utf-8')
    requests = []
    def states(hub, slug, files):
        requests.append((slug, files))
        if disconnected:
            raise remote.RemoteError('Connection lost')
        return {'notes.md': {}, 'missing.md': None}
    monkeypatch.setattr(remote, 'file_states', states)
    evidence = k.checkpoints.evidence(hub.root, 'remote', {'evidence': [
        '{project}/notes.md', 'studies/{study}/IDEA.md', '{project}/missing.md']})
    assert requests == [('remote', ['notes.md', 'missing.md'])]
    assert [e['exists'] for e in evidence] == [not disconnected, True, False]
    assert evidence[0]['path'] == remote.uri('box', '/research/my project/notes.md')
    assert evidence[0]['remote'] and not evidence[0]['dir']
    assert evidence[1]['path'] == 'studies/remote/IDEA.md'


def test_concurrent_snapshot_requests_share_one_read(hub, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    server = load('dashboard/serve')
    monkeypatch.setattr(server.ctx, 'HUB', hub.root)
    monkeypatch.setattr(server.ctx, 'LAB', hub.lab)
    monkeypatch.setattr(server.settings, 'setup_status', lambda: {})
    monkeypatch.setattr(server.term, 'desktop', lambda: False)
    monkeypatch.setattr(server.term, 'has_pty', lambda: False)
    server._forget_snapshot()
    calls = []
    def snapshot():
        calls.append(1)
        time.sleep(.05)  # competing requests arrive while the first read is in flight
        return {'now': 'test'}
    monkeypatch.setattr(server.sources, 'snapshot', snapshot)
    start = threading.Barrier(6)
    def get(_):
        start.wait(timeout=5)
        return server._snapshot_cached()
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(get, range(6)))
    assert len(calls) == 1
    assert all(value is values[0] for value in values)
    server._forget_snapshot()
    server._snapshot_cached()
    assert len(calls) == 2


def test_switch_invalidates_an_inflight_snapshot(hub, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    server = load('dashboard/serve')
    monkeypatch.setattr(server.ctx, 'HUB', hub.root)
    monkeypatch.setattr(server.ctx, 'LAB', hub.lab)
    monkeypatch.setattr(server.settings, 'setup_status', lambda: {})
    monkeypatch.setattr(server.term, 'desktop', lambda: False)
    monkeypatch.setattr(server.term, 'has_pty', lambda: False)
    server._forget_snapshot()
    started, release = threading.Event(), threading.Event()
    calls = []
    def snapshot():
        calls.append(1)
        if len(calls) == 1:
            started.set()
            assert release.wait(timeout=5)
        return {'now': 'test', 'read': len(calls)}
    monkeypatch.setattr(server.sources, 'snapshot', snapshot)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(server._snapshot_cached)
        assert started.wait(timeout=5)
        server._forget_snapshot()
        release.set()
        assert result.result(timeout=5)['read'] == 2
    assert server._snapshot_cached()['read'] == 2
