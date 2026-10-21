"""Project-only worker with real HTTP/processes; SSH/auth itself is covered separately."""
import json
import os
import socket
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from conftest import REPO, kernel
sys.path.insert(0, str(REPO/'tools'))
import remote_projects as R


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.setenv('NEWTS_HOME', str(tmp_path/'home'))
    monkeypatch.setenv('NEWTS_KEEP_PYTHON', '1')
    digest, blob = R.bundle()
    package = tmp_path/(digest + '.pyz'); package.write_bytes(blob)
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
    log = (tmp_path/'worker.log').open('w')
    proc = subprocess.Popen([sys.executable, str(package), 'serve', '--port', str(port)], stdout=log, stderr=log)
    import http.client
    for _ in range(100):
        try:
            c = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
            c.request('GET', '/api/ping'); res=c.getresponse(); res.read();c.close()
            session=json.loads((tmp_path/'home/workers'/f'session-{port}.json').read_text())
            cookie=session['cookie']; break
        except (OSError, ValueError):
            time.sleep(.1)
    else:
        proc.kill(); log.close(); pytest.fail((tmp_path/'worker.log').read_text())
    home = tmp_path/'home';home.mkdir(exist_ok=True)
    fake = [sys.executable, str(REPO/'tests/fake_acp.py')]
    (home/'machines.json').write_text(json.dumps({'machines':[{'id':'box','host':'unused-fixture',
        'name':'Compute box','default_agent':'acp','agent_config':{'acp':{'command':fake}},
        'worker':{'port':port,'cookie':cookie}}]}), encoding='utf-8')
    yield {'package':package,'port':port,'cookie':cookie,'root':tmp_path}
    proc.terminate();proc.wait(10);log.close()


def configure(hub):
    cfg=yaml.safe_load((hub.root/'lab/config.yaml').read_text()) or {}
    cfg.setdefault('agents',{}).setdefault('programmatic',{}).update(enabled=True,backend='acp',
        live={'linger_minutes':0},backends={'acp':{'command':['does-not-exist-on-controller']}})
    (hub.root/'lab/config.yaml').write_text(yaml.safe_dump(cfg),encoding='utf-8')


def wait(lab, run_id, predicate, seconds=25):
    from executor.manifest import find_run
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        R.sync(lab)
        m=find_run(lab,run_id)[3]
        if predicate(m):return m
        time.sleep(.25)
    pytest.fail(json.dumps(m,indent=2))


def test_worker_bundle_is_execution_only(worker):
    import zipfile
    with zipfile.ZipFile(worker['package']) as z:
        assert not any(n.startswith(('dashboard/','kernel/','workflow/')) for n in z.namelist())
        assert z.read('LICENSE') == (REPO/'LICENSE').read_bytes()
        assert z.read('LICENSES/MIT-original.txt') == (REPO/'LICENSES/MIT-original.txt').read_bytes()
        assert b'Copyright' in z.read('LICENSES/PyYAML.txt')
    info=R.rpc('box','info')
    assert info['protocol']==1 and 'clis' in info


def test_worker_reads_framework_activity_without_launching(worker):
    root=worker['root']/'observed-project'
    path=root/'.newts/framework-runs/demo/tool/run/events.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'event':'work','timestamp':'now','fields':{'label':'Reading evidence'}}))
    definition={'id':'tool','activity':{'files':['events.jsonl'],'events':{'work':{'state':'running','kind':'read'}}}}
    result=R.rpc('box','framework-activity',{'definition':definition,'project':str(root),'study':'demo','phase':'work'})
    assert result['current']['label']=='Reading evidence' and result['current']['kind']=='read'


def test_worker_knowledge_records_and_project_cli(hub,worker):
    import research_start,knowledge
    root=worker['root']/'knowledge-project';root.mkdir()
    research_start.create(hub.root,title='Remote knowledge',question='Keep records.',local=str(root),machine='box')
    record=knowledge.dispatch(hub.root,'remote-knowledge','add',kind='note',text='Read this note.',acknowledge=True)
    assert knowledge.dispatch(hub.root,'remote-knowledge','get',id=record['id'])['scope']=='project'
    rows=knowledge.dispatch(hub.root,'remote-knowledge','list')['rows']
    assert rows[0]['rel'].startswith('.newts/knowledge/')
    done=subprocess.run([sys.executable,str(worker['package']),'knowledge','--project',str(root),'ack',record['id']],
                        capture_output=True,text=True,timeout=15)
    assert done.returncode==0,done.stderr
    assert json.loads(done.stdout)['acknowledgements']
    assert (root/'.newts/project.json').is_file()


def test_checkpoint_evidence_reads_remote_files_together_and_stays_fresh(hub, worker, monkeypatch):
    import research_start
    root = worker['root'] / 'review-project'
    root.mkdir()
    research_start.create(hub.root, title='Remote review', question='Check evidence.', local=str(root), machine='box')
    (root / 'notes.md').write_text('Notes', encoding='utf-8')
    cp = {'evidence': ['{project}/notes.md', '{project}/report.md']}
    calls = []
    rpc = R.rpc
    def measured(machine, action, *args, **kwargs):
        if action == 'files':
            calls.append(1)
        return rpc(machine, action, *args, **kwargs)
    monkeypatch.setattr(R, 'rpc', measured)
    first = kernel().checkpoints.evidence(hub.root, 'remote-review', cp)
    assert [e['exists'] for e in first] == [True, False] and len(calls) == 1
    (root / 'report.md').write_text('New report', encoding='utf-8')
    second = kernel().checkpoints.evidence(hub.root, 'remote-review', cp)
    assert all(e['exists'] for e in second) and len(calls) == 2


def test_remote_retained_attachment_downloads_without_bundling_controller(hub,worker,monkeypatch):
    import research_start,knowledge
    from conftest import load
    root=worker['root']/'attachment-project';root.mkdir()
    research_start.create(hub.root,title='Remote attachments',question='Keep sources.',local=str(root),machine='box')
    # Larger than one worker response chunk, and not a preview-only format.
    content=b'archive fixture\n'*100000
    source=root/'data.zip';source.write_bytes(content)
    done=subprocess.run([sys.executable,str(worker['package']),'knowledge','--project',str(root),'add',
        '--kind','source','--text','A retained source.','--attachment',str(source)],capture_output=True,text=True,timeout=15)
    assert done.returncode==0,done.stderr
    record=json.loads(done.stdout)
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/knowledge_api');monkeypatch.setattr(api.ctx,'HUB',hub.root)
    file,ctype=api.attachment({'study':'remote-attachments','id':record['id']})
    assert file.read_bytes()==content and ctype=='application/octet-stream'


def test_worker_browses_unattached_folders_without_registering_them(worker):
    root=worker['root']/'unattached';root.mkdir()
    (root/'nested').mkdir();(root/'file.txt').write_text('not a folder')
    result=R.rpc('box','browse',{'path':str(root)})
    assert result['path']==str(root.resolve())
    assert [f['name'] for f in result['folders']]==['nested']
    assert not (root/'.bus').exists()
    with pytest.raises(R.RemoteError):R.rpc('box','browse',{'path':str(root/'missing')})


def test_uploaded_binary_materials_reach_remote_agent_snapshot(hub,worker):
    import base64
    import research_start,executor,study_materials as materials
    root=worker['root']/'project';root.mkdir()
    meta=materials.new(hub.root);path,_=materials.load(hub.root,meta['id'])
    content=b'%PDF-1.7\n\x00\xfforiginal'
    materials.upload(path,meta,'project brief.pdf',base64.b64encode(content).decode())
    research_start.create(hub.root,title='Remote brief',question='Read materials.',local=str(root),machine='box',draft=meta['id'])
    configure(hub);lab=executor.Lab(hub.root)
    m=executor.enqueue(lab,executor.RunSpec('ask',target='remote-brief',prompt='Read the study materials.'))
    # Source changes after enqueue cannot alter the frozen run snapshot.
    source=hub.root/'studies/remote-brief/materials'/meta['files'][0]['stored']
    source.write_bytes(b'changed later')
    executor.tick(lab)
    done=wait(lab,m['run_id'],lambda m:m['status'] in ('completed','failed'))
    assert done['status']=='completed',done
    copies=list((root/'.bus/newts').glob('*/agents/*.d/instructions/studies/remote-brief/materials/*'))
    assert len(copies)==1 and copies[0].read_bytes()==content
    index=copies[0].parent.parent/'MATERIALS.md'
    assert 'project brief.pdf' in index.read_text()
    with pytest.raises(R.RemoteError):
        R.call(hub.root,'remote-brief','material',run_id=m['run_id'],name='../escape',data='eA==')


def test_worker_session_is_private_and_never_issued_to_http_clients(worker):
    import http.client
    from project_worker import session_file
    c = http.client.HTTPConnection('127.0.0.1', worker['port'], timeout=2)
    c.request('GET', '/?session=1')
    response=c.getresponse(); response.read()
    assert response.status == 403 and response.getheader('Set-Cookie') is None
    c.close()
    path = session_file(worker['port'])
    assert json.loads(path.read_text())['cookie'] == worker['cookie']
    if os.name == 'posix':
        assert path.stat().st_mode & 0o777 == 0o600


def test_attach_and_run_without_a_remote_lab(hub,worker):
    import research_start
    import executor
    from executor.manifest import transition,run_dir,find_run
    root=worker['root']/'project';root.mkdir()
    (root/'keep.txt').write_text('existing')
    result=research_start.create(hub.root,title='Remote study',question='Test evidence',local=str(root),machine='box')
    assert R.location(result['project'])['machine']=='box'
    assert not (root/'lab').exists() and (root/'keep.txt').read_text()=='existing'
    configure(hub)
    lab=executor.Lab(hub.root)
    m=executor.enqueue(lab,executor.RunSpec('ask',target='remote-study',prompt='WRITE_RESULT'))
    hit=find_run(lab,m['run_id']);path=hit[2]
    transition(lab,path,m,'starting',by='test')
    R.dispatch(lab,path,m)
    # Repeat after simulated lost response: same run/attempt is accepted once.
    R.dispatch(lab,path,m)
    done=wait(lab,m['run_id'],lambda m:m['status']=='completed')
    assert done['session_id']=='fixture-session' and (root/'result.txt').read_text()=='evidence'
    assert Path(done['remote']['path'])==root.resolve()
    assert (run_dir(path.parent,m['run_id'])/'instructions.json').exists()
    assert 'Task complete' in (path.parent/m['stream']).read_text()
    activity=run_dir(path.parent,m['run_id'])/'actions.jsonl'
    assert activity.exists() and 'attempt' in activity.read_text()
    before=activity.read_bytes()
    R.sync(lab)
    assert activity.read_bytes()==before  # Replayed polls do not duplicate actions.
    assert not (root/'lab').exists()


def test_permissions_roundtrip(hub,worker):
    import research_start,executor
    from executor.manifest import transition,find_run
    root=worker['root']/'project';root.mkdir()
    research_start.create(hub.root,title='Remote study',question='Test',local=str(root),machine='box')
    configure(hub);lab=executor.Lab(hub.root)
    m=executor.enqueue(lab,executor.RunSpec('ask',target='remote-study',prompt='ASK_PERMISSION'))
    path=find_run(lab,m['run_id'])[2];transition(lab,path,m,'starting',by='test');R.dispatch(lab,path,m)
    pending=wait(lab,m['run_id'],lambda m:bool(m.get('pending_permissions')))
    executor.permission_decision(lab,m['run_id'],pending['pending_permissions'][0]['id'],True)
    done=wait(lab,m['run_id'],lambda m:m['status']=='completed')
    assert done['last_message']=='Decision received'


def test_remote_visual_summary_is_published_once_to_the_owning_lab(hub, worker):
    import research_start, executor, artifact
    root = worker['root'] / 'project'
    root.mkdir()
    research_start.create(hub.root, title='Remote study', question='Test', local=str(root), machine='box')
    configure(hub)
    lab = executor.Lab(hub.root)
    m = executor.enqueue(lab, executor.RunSpec('ask', target='remote-study', prompt='PUBLISH_SUMMARY'))
    executor.tick(lab)
    done = wait(lab, m['run_id'], lambda m: m['status'] in ('completed', 'failed'))
    assert done['status'] == 'completed', done
    rows = artifact.all_artifacts(hub.root)
    assert len(rows) == 1 and rows[0]['kind'] == 'html' and rows[0]['run_id'] == m['run_id']
    assert rows[0]['study'] == 'remote-study' and rows[0]['source_machine'] == 'box'
    assert not (root / 'lab').exists()
    request = next(json.loads(path.read_text(encoding='utf-8')) for path in
        (root / '.bus/newts' / R.owner(hub.root) / 'agents' / (m['run_id'] + '.d') / 'controller').glob('*.request.json')
        if json.loads(path.read_text(encoding='utf-8')).get('verb') == 'artifact')
    assert R._request(lab, done, request)['result']['id'] == rows[0]['id']
    assert len(artifact.all_artifacts(hub.root)) == 1


def test_message_after_remote_exit_is_admitted_as_a_resume(hub, worker):
    import executor, research_start
    from executor.manifest import find_run, write_manifest
    root = worker['root'] / 'project'
    root.mkdir()
    research_start.create(hub.root, title='Remote study', question='Test', local=str(root), machine='box')
    configure(hub)
    lab = executor.Lab(hub.root)
    m = executor.enqueue(lab, executor.RunSpec('ask', target='remote-study', prompt='Inspect'))
    executor.tick(lab)
    wait(lab, m['run_id'], lambda m: m['status'] == 'completed')
    # The controller's last poll still says running when the PI sends a follow-up.
    hit = find_run(lab, m['run_id'])
    stale = dict(hit[3], status='running')
    write_manifest(hit[2], stale)
    executor.reply(lab, m['run_id'], 'WRITE_RESULT')
    R.sync(lab)  # Delivers into the already-finished worker's inbox.
    queued = wait(lab, m['run_id'], lambda m: m['status'] == 'queued')
    assert queued['resume']['text'] == 'WRITE_RESULT'
    R.sync(lab)
    assert find_run(lab, m['run_id'])[3]['resume']['text'] == 'WRITE_RESULT'
    executor.tick(lab)
    done = wait(lab, m['run_id'], lambda m: m['status'] == 'completed')
    assert done['session_id'] == 'fixture-session' and done['attempt'] == 2
    assert (root / 'result.txt').read_text() == 'evidence'


def test_ownership_and_remote_files(worker):
    root=worker['root']/'project';root.mkdir()
    data={'path':str(root),'owner':'lab-a','study':'study'}
    R.rpc('box','attach',data)
    with pytest.raises(R.RemoteError,match='another Lab'):
        R.rpc('box','attach',dict(data,owner='lab-b'))
    with pytest.raises(R.RemoteError,match='inside'):
        R.rpc('box','files',{**data,'files':['../secret']})
    (root/'result.txt').write_text('result')
    assert R.rpc('box','files',{**data,'files':['result.txt','missing']})['missing'] is None
    lab = worker['root'] / 'other-lab'
    (lab / 'lab').mkdir(parents=True)
    (lab / 'lab/config.yaml').write_text('lab: {}', encoding='utf-8')
    with pytest.raises(R.RemoteError, match='Connect that Lab'):
        R.rpc('box', 'attach', dict(data, path=str(lab)))


def test_remote_attach_checks_durable_identity_before_writing_local_owner(worker):
    root = worker['root']/'portable project'; (root/'.newts').mkdir(parents=True)
    identity = root/'.newts/project.json'
    original = json.dumps({'schema': 1, 'project_id': 'portable-id', 'lab_id': 'owning-lab',
                           'name': 'Portable project', 'knowledge_dir': '.newts/knowledge'})
    identity.write_text(original, encoding='utf-8')
    data = {'path': str(root), 'owner': 'execution-owner', 'study': 'portable-study', 'lab_id': 'wrong-lab'}
    with pytest.raises(R.RemoteError) as error:
        R.rpc('box', 'attach', data)
    assert 'owning-lab' in str(error.value) and str(root) in str(error.value)
    assert identity.read_text(encoding='utf-8') == original
    assert not (root/'.bus/newts-owner.json').exists()
    assert not (worker['root']/'home/projects.json').exists()
    # A failed claim must not poison a later legitimate attachment.
    result = R.rpc('box', 'attach', {**data, 'lab_id': 'owning-lab'})
    assert Path(result['path']) == root.resolve()
    assert json.loads(identity.read_text(encoding='utf-8'))['project_id'] == 'portable-id'
    assert json.loads((root/'.bus/newts-owner.json').read_text(encoding='utf-8'))['owner'] == data['owner']


def test_worker_refuses_cross_origin(worker):
    import http.client
    c=http.client.HTTPConnection('127.0.0.1',worker['port'])
    c.request('POST','/rpc','{}',{'Cookie':worker['cookie'],'Origin':'https://example.com'})
    r=c.getresponse();assert r.status==403;r.read();c.close()


def test_inbox_external_command_is_idempotent(tmp_path):
    from executor import live
    item={'kind':'message','text':'one','request_id_external':'request-1'}
    live.post(tmp_path,item);live.post(tmp_path,item)
    files=list((tmp_path/'inbox').glob('*.json'));assert len(files)==1
    files[0].replace(files[0].with_suffix('.claimed'))
    live.post(tmp_path,item)
    assert not list((tmp_path/'inbox').glob('*.json'))


def test_remote_brief_includes_procedure_catalog_and_helpers(hub, tmp_path):
    skill = hub.root / '.claude/skills/custom-review'
    skill.mkdir(parents=True)
    (skill / 'SKILL.md').write_text('Read helper.py before reviewing.', encoding='utf-8')
    (skill / 'helper.py').write_text('print("review")', encoding='utf-8')
    R.capture(type('Lab', (), {'hub': hub.root})(), {'subject': 'study', 'skill': 'ask'}, tmp_path)
    files = json.loads((tmp_path / 'instructions.json').read_text(encoding='utf-8'))
    assert files['.claude/skills/custom-review/SKILL.md']
    assert files['.claude/skills/custom-review/helper.py'] == 'print("review")'


def test_worker_detects_crash_from_its_own_supervisor_lock(tmp_path):
    from project_worker import Worker, atomic
    from executor.procs import RunLock
    root = tmp_path / 'project'
    root.mkdir()
    worker = Worker('fixture.pyz')
    data = {'path': str(root), 'owner': 'lab-a', 'study': 'study', 'run_id': 'run-a'}
    worker.call('attach', data)
    agents = root / '.bus/newts/lab-a/agents'
    rd = agents / 'run-a.d'
    atomic(agents / 'run-a.json', {'status': 'running', 'attempt': 1})
    atomic(rd / 'dispatch-0.json', {'accepted': True})
    old = time.time() - 60
    os.utime(rd / 'dispatch-0.json', (old, old))
    lock = RunLock(rd / 'lock')
    assert lock.try_acquire()
    try:
        assert worker.call('poll', data)['manifest']['status'] == 'running'
    finally:
        lock.release()
    assert worker.call('poll', data)['manifest']['status'] == 'failed'


def test_remote_task_reports_to_central_graph_and_stops_at_gate(hub,worker):
    import research_start,executor
    k=kernel();d=k.define.read(hub.root)
    d['workflows']=[{'id':'remote-test','title':'Remote test','default':True,'path':['seed','writing'],
        'routes':{},'use':{},'checkpoints':[{'id':'review','title':'Review result','before':'writing','approver':'me'}],
        'nodes':{'seed':{'procedure':None,'instructions':'WRITE_RESULT REPORT_DONE','outputs':['result.txt'],'next':['writing']},
                 'writing':{'procedure':None,'instructions':'Review evidence.','next':[]}}}]
    k.define.write(hub.root,d)
    root=worker['root']/'project';root.mkdir()
    research_start.create(hub.root,title='Remote study',question='Test',local=str(root),machine='box')
    configure(hub);lab=executor.Lab(hub.root)
    ids=executor.profile.start_graph(lab,'remote-study',executor.enqueue,executor.RunSpec)
    assert len(ids)==1
    report=executor.tick(lab)
    assert ids[0] in report['started']
    done=wait(lab,ids[0],lambda m:m['status']=='completed')
    state=k.studies.study(hub.root,'remote-study')
    assert not state['runnable'] and state['task_waits']
    assert not (root/'lab/journal.jsonl').exists()
    k.checkpoints.decide(hub.root,'remote-study','review',by='pi',via='cli')
    assert k.studies.study(hub.root,'remote-study')['runnable']==['writing']


def test_remote_session_can_resume_after_completion(hub,worker):
    import research_start,executor
    root=worker['root']/'project';root.mkdir()
    research_start.create(hub.root,title='Remote study',question='Test',local=str(root),machine='box')
    configure(hub);lab=executor.Lab(hub.root)
    m=executor.enqueue(lab,executor.RunSpec('ask',target='remote-study',prompt='First turn'))
    executor.tick(lab)
    done=wait(lab,m['run_id'],lambda m:m['status']=='completed')
    executor.reply(lab,m['run_id'],'Second turn')
    executor.tick(lab)
    done=wait(lab,m['run_id'],lambda m:m['status']=='completed' and m['attempt']==2)
    assert done['session_id']=='fixture-session'


@pytest.mark.parametrize('backend', ['claude', 'codex', 'opencode'])
def test_remote_worker_keeps_native_adapters(hub, worker, backend):
    import research_start, executor
    if backend == 'opencode' and not shutil.which('node'):
        pytest.skip('opencode fixture needs Node.js')
    root = worker['root'] / 'project'
    root.mkdir()
    registry = worker['root'] / 'home/machines.json'
    data = json.loads(registry.read_text(encoding='utf-8'))
    command = ([shutil.which('node'), str(REPO / 'tests/fake_opencode.mjs')] if backend == 'opencode'
               else [sys.executable, str(REPO / ('tests/fake_' + backend + '.py'))])
    data['machines'][0]['default_agent'] = backend
    data['machines'][0]['agent_config'] = {backend: {'command': command}}
    registry.write_text(json.dumps(data), encoding='utf-8')
    research_start.create(hub.root, title='Remote study', question='Test', local=str(root), machine='box')
    configure(hub)
    lab = executor.Lab(hub.root)
    m = executor.enqueue(lab, executor.RunSpec('ask', target='remote-study', prompt='Inspect the project'))
    executor.tick(lab)
    done = wait(lab, m['run_id'], lambda m: m['status'] in ('completed', 'failed'), seconds=35)
    assert done['status'] == 'completed', done
    assert done['backend'] == backend and done['session_id']
