"""Independent explanations consume records, never the source agent's input channel."""
import json
import sys
from pathlib import Path

import labfiles
import pytest
import yaml

from conftest import REPO, load

sys.path.insert(0, str(REPO/'tools'))
from executor import Lab, RunSpec, enqueue, manifest, evidence, actions


def configured(hub, backend='claude'):
    (hub.lab/'config.yaml').write_text(yaml.safe_dump({'agents':{'programmatic':{
        'enabled':True, 'backend':backend, 'backends':{backend:{'command':[sys.executable,str(REPO/'tests/fake_claude.py')]}}}}}))
    return Lab(hub.root)


@pytest.mark.parametrize('backend',['claude','codex','opencode','acp'])
@pytest.mark.parametrize('status',['queued','running','waiting_input','completed','failed'])
def test_explainer_is_fresh_and_does_not_touch_source(hub,monkeypatch,backend,status):
    monkeypatch.setattr(evidence, 'python_exe', lambda: 'C:/durable helper/python.exe')
    lab=configured(hub,backend)
    source=enqueue(lab,RunSpec('',prompt='Inspect evidence.'))
    _,_,path,source=manifest.find_run(lab,source['run_id'])
    source.update(status=status, session_id='working-session',pending_question={'id':'unanswered'},
                  subagents={'child':{'type':'reviewer','description':'Read the paper','session':'child-session','result':'Reported evidence.'}})
    labfiles.write_json(path,source)
    rd=manifest.run_dir(path.parent,source['run_id'])
    (path.parent/source['stream']).write_text('{"type":"turn.completed"}\n')
    actions.record(rd,None,'spawn',child='child',type='reviewer',summary='Read the paper')
    actions.record(rd,'child','action',tool='Read',summary='paper.md')
    original=path.read_bytes()
    child=evidence.describe(lab,source['run_id'],'child-session')
    assert child['agent']=='child' and child['agents']['child']['result']=='Reported evidence.'
    explained=evidence.start(lab,source['run_id'],'child')
    assert explained['run_id']!=source['run_id'] and explained['context']['mode']=='fresh'
    assert explained['level']=='hub' and explained['subject'] is None and explained['chain']=='off'
    assert explained['backend']==backend and explained['explains']['agent']=='child'
    assert path.read_bytes()==original and not (rd/'inbox').exists()
    own=manifest.run_dir(lab.agents_dir(lab.hub),explained['run_id'])
    pre=(own/'preamble.md').read_text()
    assert 'separate terminal explainer' in pre and 'Do not edit research files' in pre
    index=json.loads(Path(explained['explains']['evidence']).read_text())
    frozen=Path(index['captures']['transcript']['path'])
    (path.parent/source['stream']).write_text('later changes\n')
    assert json.loads(frozen.read_text())['type']=='turn.completed'
    assert (own/'prompt.md').read_text().find('--about')>=0
    assert (own/'prompt.md').read_text().count('C:/durable helper/python.exe') == 2
    import gate_reviews
    monkeypatch.setattr(gate_reviews,'start_waiting',lambda *a,**k:pytest.fail('Explanation triggered a gate reviewer'))
    import lab_profile
    assert lab_profile.next_command(lab,{**explained,'subject':'some-study'})==(True,None)


def test_publication_keeps_producer_source_and_study(hub,tmp_path,monkeypatch):
    lab=configured(hub);source=enqueue(lab,RunSpec('',prompt='Inspect evidence.'))
    result=evidence.start(lab,source['run_id'])
    page=tmp_path/'summary.html';page.write_text('<h1>Evidence</h1>')
    monkeypatch.setenv('ARLOTOPE_RUN_ID',result['run_id'])
    art=load('artifact').publish('Explanation',str(page),h=hub.root,study='study-a',about=source['run_id'])
    assert art['run_id']==result['run_id'] and art['about']['run']==source['run_id'] and art['study']=='study-a'


def test_missing_and_partial_evidence_is_explicit(hub,tmp_path):
    lab=configured(hub);source=enqueue(lab,RunSpec('',prompt='Inspect evidence.'))
    info=evidence.describe(lab,source['run_id'])
    assert 'transcript' in info['coverage']['missing']
    assert 'conversation' in info['coverage']['missing']
    with pytest.raises(ValueError,match='subagent'):evidence.describe(lab,source['run_id'],'invented')
    stream=Path(info['files']['transcript'])
    stream.write_text('{"type":"x"}\n'*100+'{"_truncated":"limit"}\n')
    content,bounds=evidence._excerpt(stream,100)
    assert bounds['excerpt'] and bounds['start_byte']>0
    assert all(isinstance(json.loads(line),dict) for line in content.splitlines())
    assert evidence.describe(lab,source['run_id'])['coverage']['transcript_capped']
    with stream.open('a') as more:more.write('{"type":"resumed"}\n'*1000)
    assert evidence.describe(lab,source['run_id'])['coverage']['transcript_capped']
    outside=tmp_path/'private.txt';outside.write_text('outside hub')
    with pytest.raises(ValueError,match='inside'):evidence.project_file(lab,source['run_id'],str(outside))


def test_evidence_descriptor_keeps_metadata_without_copying_child_actions(hub):
    lab = configured(hub)
    source = enqueue(lab, RunSpec('', prompt='Inspect evidence.'))
    rd = manifest.run_dir(lab.agents_dir(lab.hub), source['run_id'])
    actions.record(rd, None, 'spawn', child='review', type='reviewer', summary='Check evidence')
    for i in range(300):
        actions.record(rd, 'review', 'action', kind='read', tool='Read', summary=str(i))
    actions.record(rd, 'review', 'stop', status='done', result='Supported by the supplied evidence')
    info = evidence.describe(lab, source['run_id'], 'review')
    assert info['agents']['review']['result'] == 'Supported by the supplied evidence'
    assert 'actions' not in info['agents']['review']
    assert len(json.dumps(info)) < 10000
    assert len(actions.tree(rd)['agents']['review']['actions']) == 300
    assert len(actions.read(rd)) == 302
    actions.record(rd, None, 'spawn', child='later', type='analyst')
    assert 'later' in evidence.describe(lab, source['run_id'])['agents']


def test_hook_logs_use_embedded_run_identity(hub):
    lab=configured(hub);source=enqueue(lab,RunSpec('',prompt='Inspect evidence.'))
    rd=manifest.run_dir(lab.agents_dir(lab.hub),source['run_id'])
    actions.record(rd,None,'spawn',child='child',type='reviewer',summary='Check evidence')
    logs=lab.bus/'workers';logs.mkdir(parents=True,exist_ok=True)
    for worker,role in [('native-session','orchestrator'),('agent-7','reviewer')]:
        (logs/(worker+'.jsonl')).write_text(json.dumps({'worker_id':worker,'role':role,
            'run_id':source['run_id'],'event':'stop','result':'Evidence returned.'})+'\n')
    (logs/(source['run_id']+'.jsonl')).write_text(json.dumps({'worker_id':source['run_id'],
        'run_id':source['run_id'],'role':'analyst','session_id':'native-session'})+'\n')
    (logs/(source['run_id']+'.child.jsonl')).write_text(json.dumps({'worker_id':source['run_id']+'.child',
        'run_id':source['run_id'],'role':'reviewer'})+'\n')
    info=evidence.describe(lab,source['run_id'],'agent-7')
    assert info['agent']=='agent-7'
    assert source['run_id'] not in info['agents']
    assert set(info['agents'])=={'child','agent-7'}
    assert 'worker-native-session' in info['files'] and 'worker-agent-7' in info['files']
    _,frozen=evidence.snapshot(lab,source['run_id'],'agent-7')
    assert 'Evidence returned.' in Path(frozen['captures']['worker-agent-7']['path']).read_text()


def test_remote_file_does_not_follow_a_reattached_study(hub,monkeypatch):
    import remote_projects
    lab=configured(hub);source=enqueue(lab,RunSpec('',prompt='Inspect evidence.'))
    _,_,path,run=manifest.find_run(lab,source['run_id'])
    labfiles.write_json(path,{**run,'subject':'study','remote':{'machine':'box','path':'/old'}})
    monkeypatch.setattr(remote_projects,'project',lambda *a:{'machine':'box','path':'/new'})
    monkeypatch.setattr(remote_projects,'call',lambda *a,**k:pytest.fail('Read an unrelated project'))
    with pytest.raises(ValueError,match='moved'):evidence.project_file(lab,source['run_id'],'REPORT.md')


def test_remote_evidence_uses_worker_and_discloses_stale_mirror(hub, monkeypatch):
    import base64
    import remote_projects
    lab = configured(hub)
    source = enqueue(lab, RunSpec('', prompt='Inspect evidence.'))
    _, _, path, run = manifest.find_run(lab, source['run_id'])
    remote = {'machine': 'test-machine', 'path': '/project'}
    labfiles.write_json(path, {**run, 'subject': 'study', 'remote': remote})
    monkeypatch.setattr(remote_projects, 'project', lambda *a: remote)
    calls = []
    def read(*args, **kwargs):
        calls.append((args[1:], kwargs))
        return {'data': base64.b64encode(b'Remote evidence').decode()}
    monkeypatch.setattr(remote_projects, 'call', read)
    assert evidence.project_file(lab, source['run_id'], 'REPORT.md')['text'] == 'Remote evidence'
    assert calls == [(('study', 'read'), {'file': 'REPORT.md'})]
    assert 'remote work may be newer' in evidence.describe(lab, source['run_id'])['coverage']['remote']
