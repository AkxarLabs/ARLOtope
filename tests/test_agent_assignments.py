"""Assignment precedence, immutable launch choices and causal conversation ownership."""
import json
import sys
from pathlib import Path

import pytest
import yaml

from conftest import REPO, kernel, load

sys.path.insert(0, str(REPO/'tools'))
from executor import Lab, RunSpec, SpecError, enqueue, manifest, contexts, assignments


def configure(hub):
    fake = [sys.executable, str(REPO/'tests/fake_claude.py')]
    config = {'agents':{'programmatic':{'enabled':True,'backend':'claude','live':False,
        'backends':{b:{'command':fake} for b in ('claude','codex','opencode','acp')},
        'presets':{'lead':{'label':'Lead','backend':'claude','model':'model-a'},
                   'review':{'label':'Review','backend':'codex','model':'model-b'},
                   'external':{'label':'ACP A','backend':'acp','command':fake}},
        'default_preset':'lead','role_presets':{'reviewer':'review'}}}}
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(config),encoding='utf-8')
    return Lab(hub.root), config


def test_specialist_default_and_explicit_override(hub):
    lab,_=configure(hub)
    path=assignments.study_path(lab,'study');path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump({'default_preset':'lead'}))
    review=assignments.resolve(lab,RunSpec('',role='reviewer'), 'study')
    assert review['preset']=='review' and review['source']=='Lab role'
    path.write_text(yaml.safe_dump({'role_presets':{'reviewer':None}}))
    assert assignments.resolve(lab,RunSpec('',role='reviewer'),'study')['preset']=='lead'
    assert assignments.resolve(lab,RunSpec('',preset='review'),'study')['preset']=='review'
    assert assignments.resolve(lab,RunSpec('',backend='opencode'),'study')['model'] is None
    assert assignments.resolve(lab,RunSpec('',role='reviewer',backend='codex'))['model'] is None
    assert assignments.resolve(lab,RunSpec('',preset='review',extra={'agent':{'backend':'claude','model':'wrong'}}))['model']=='model-b'
    assert assignments.resolve(lab,RunSpec('',backend='claude',extra={'agent':{'preset':'missing'}}))['backend']=='claude'
    assert assignments.resolve(lab,RunSpec('',role='reviewer',extra={'agent':{'model':None}}))['model'] is None
    assert assignments.resolve(lab,RunSpec('',role='reviewer',model='inherit'))['model'] is None
    assert assignments.resolve(lab,RunSpec('',target='idea.v2'),'idea.v2')['preset']=='lead'
    with pytest.raises(SpecError,match='missing'):assignments.resolve(lab,RunSpec('',preset='missing'))


def test_launch_captures_configuration_and_changed_defaults_do_not_leak(hub):
    from executor.backends import Attempt
    lab,cfg=configure(hub)
    run=enqueue(lab,RunSpec('',prompt='Read the plan.',role='reviewer'))
    cfg['agents']['programmatic']['backends']['codex']['model']='later-default'
    cfg['agents']['programmatic']['presets']['review']['model']='later-preset'
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(cfg))
    attempt=Attempt(lab,run,lab.hub,lab.hub,lab.prog(),[], '', '',False,False,{},sys.executable)
    assert run['model']=='model-b' and attempt.model=='model-b'
    assert attempt.bcfg['model']=='model-b'
    assert run['assignment']['label']=='Review'


def test_preset_validation_and_effort_capability(hub):
    lab,_=configure(hub)
    with pytest.raises(SpecError,match='effort'):
        assignments.validate({'presets':{'x':{'backend':'acp','effort':'high'}}})
    with pytest.raises(SpecError,match='argument list'):
        assignments.validate({'presets':{'x':{'backend':'acp','command':'unsafe shell string'}}})
    with pytest.raises(SpecError,match='effort'):
        assignments.resolve(lab,RunSpec('',backend='opencode',effort='high'))


def test_legacy_model_and_cancelled_continuation(hub):
    lab,cfg=configure(hub)
    prog=cfg['agents']['programmatic']
    for key in ('presets','default_preset','role_presets'):prog.pop(key)
    prog['model']='legacy-model'
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(cfg))
    assert assignments.resolve(lab,RunSpec('',backend='claude'))['model']=='legacy-model'
    source=enqueue(lab,RunSpec('',prompt='First.'))
    _,_,path,source=manifest.find_run(lab,source['run_id'])
    source.update(status='completed',session_id='session');manifest.write_manifest(path,source)
    child=enqueue(lab,RunSpec('',prompt='Second.',extra={'context':{'mode':'continue','run_id':source['run_id']}}))
    _,_,path,child=manifest.find_run(lab,child['run_id'])
    child['status']='killed';manifest.write_manifest(path,child)
    contexts.assert_current(lab,source)
    child['status']='failed';manifest.write_manifest(path,child)
    contexts.assert_current(lab,source)


def test_continuation_keeps_configuration_and_rejects_wrong_profile(hub):
    lab,cfg=configure(hub)
    run=enqueue(lab,RunSpec('',prompt='Draft.',preset='lead'))
    _,_,path,run=manifest.find_run(lab,run['run_id'])
    run.update(status='completed',session_id='session');manifest.write_manifest(path,run)
    cfg['agents']['programmatic']['presets']['lead']['model']='changed'
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(cfg))
    spec=RunSpec('',prompt='Revise.',extra={'context':{'mode':'continue','run_id':run['run_id']}})
    child=enqueue(lab,spec)
    assert child['model']=='model-a' and child['session_id']=='session'
    assert child['assignment']['source']=='Source conversation'
    with pytest.raises(SpecError,match='another agent'):
        enqueue(lab,RunSpec('',prompt='Wrong.',preset='review',extra=spec.extra))


def test_causal_context_can_resume_writer_after_independent_review(hub):
    lab,_=configure(hub)
    adir=lab.agents_dir(lab.hub)
    writer={'run_id':'writer','target':'hub','schema':2,'level':'hub','workflow_node':'draft',
            'cwd':str(lab.hub),'backend':'claude','session_id':'writer-session','status':'completed','attempt':1}
    reviewer={**writer,'run_id':'review','workflow_node':'review','session_id':'reviewer-session','input_runs':['writer']}
    for run in (writer,reviewer):manifest.write_manifest(adir/(run['run_id']+'.json'),run)
    selected=contexts.workflow_sources(lab,{'review':'review'},{'from':'draft'},'revise')
    assert selected[0]['run_id']=='writer'
    text,lineage=contexts.prepare(lab,{'mode':'continue','run_id':'writer'},'claude',lab.hub,'Revise.')
    assert lineage['session_id']=='writer-session'
    updated={**writer,'run_id':'revise','workflow_node':'revise','context':{'source_run':'writer'}}
    manifest.write_manifest(adir/'revise.json',updated)
    with pytest.raises(SpecError,match='newer work'):
        contexts.prepare(lab,{'mode':'continue','run_id':'writer'},'claude',lab.hub,'Old context.')
    with pytest.raises(SpecError,match='newer work'):contexts.assert_current(lab,writer)


def test_fork_revalidation_and_namespace(hub):
    lab,_=configure(hub);adir=lab.agents_dir(lab.hub)
    for name in ('auth-a','auth-b'):
        early={'run_id':name,'target':'hub','schema':2,'level':'hub','cwd':str(lab.hub),
               'backend':'acp','session_id':None,'status':'waiting_input'}
        manifest.write_manifest(adir/(name+'.json'),early)
    contexts.assert_current(lab,early)  # Separate authentication requests are not a shared conversation.
    source={'run_id':'source','target':'hub','schema':2,'level':'hub','cwd':str(lab.hub),'backend':'claude',
            'session_id':'same-id','status':'completed','attempt':1}
    manifest.write_manifest(adir/'source.json',source)
    other={**source,'run_id':'other','backend':'acp','status':'running'}
    manifest.write_manifest(adir/'other.json',other)
    _,data=contexts.prepare(lab,{'mode':'native-fork','run_id':'source'},'claude',lab.hub,'Fork.')
    fork={**source,**data,'session_id':None,'run_id':'fork','status':'queued'}
    manifest.write_manifest(adir/'fork.json',fork)
    with pytest.raises(SpecError,match='active work'):contexts.assert_current(lab,source)
    fork['session_id']='allocated-but-not-started';manifest.write_manifest(adir/'fork.json',fork)
    with pytest.raises(SpecError,match='active work'):contexts.assert_current(lab,source)
    fork['fork_started']=True;manifest.write_manifest(adir/'fork.json',fork)
    contexts.assert_current(lab,source)
    manifest.write_manifest(adir/'source.json',{**source,'attempt':2})
    with pytest.raises(SpecError,match='changed while queued'):contexts.validate_head(lab,fork)


def test_role_step_roundtrip_and_study_choices(hub):
    import research_start
    lab,_=configure(hub);k=kernel();definition=k.define.read(hub.root)
    definition['steps']['proposal']['agent']={'role':'writer'}
    k.define.write(hub.root,definition)
    assert k.model.step('proposal',hub.root)['agent']['role']=='writer'
    research_start.create(hub.root,title='Choice',question='Investigate.',agents={'default_preset':'review'})
    assert assignments.settings(lab,'choice')[1]['default_preset']=='review'
    definition=k.define.read(hub.root);definition['steps']['seed']['agent']={'role':'writer'}
    k.define.write(hub.root,definition)
    run=enqueue(lab,RunSpec('triage',target='choice'))
    assert run['role']=='writer' and run['assignment']['preset']=='review'


def test_dashboard_settings_save_and_connection_probe(hub,monkeypatch):
    lab,cfg=configure(hub);monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/agent_settings');monkeypatch.setattr(api.ctx,'HUB',hub.root);monkeypatch.setattr(api.ctx,'LAB',hub.lab)
    value={k:lab.prog()[k] for k in ('presets','default_preset','role_presets')}
    assert api.save({'settings':value})[1]==200
    data,code=api.view({});assert code==200 and data['resolved']['reviewer']['preset']=='review'
    from executor.acp_probe import probe
    connection=probe([sys.executable,str(REPO/'tests/fake_acp.py')],hub.root,timeout=5)
    assert connection['protocolVersion']==1


def test_parallel_join_allows_a_separate_stop_outcome():
    from workflow_graph import validate
    nodes=[{'id':'source','next':['a','b'],'outcomes':{'stop':'parked'}},
           {'id':'a','next':['join']},{'id':'b','next':['join']},
           {'id':'join','next':[],'join':True,'agent':{'model':None}}]
    assert validate(nodes)==[]
    nodes[0].update(next=['a'],outcomes={'retry':['b']})
    assert any('mutually exclusive' in p for p in validate(nodes))


def test_graph_join_can_handoff_multiple_completed_sources(hub,monkeypatch):
    import lab_profile
    from kernel.branches import bind
    from test_agent_workspaces import graph
    k=graph(hub);lab,_=configure(hub)
    definition=k.define.read(hub.root)
    ns=definition['workflows'][0]['nodes']
    ns['analysis']['outputs']=['analysis.md'];ns['writing']['outputs']=['review.md']
    ns['final']['context']={'mode':'fresh','handoff':True,'from':['analysis','writing']}
    k.define.write(hub.root,definition)
    k.studies.move(hub.root,'study','done')
    (hub.root/'studies/study').mkdir(parents=True,exist_ok=True)
    for filename in ('analysis.md','review.md'):
        (hub.root/'studies/study'/filename).write_text('Evidence.',encoding='utf-8')
    for task in ('analysis','writing'):
        rid='run-'+task
        bind(hub.root,'study',task,rid)
        manifest.write_manifest(lab.agents_dir(lab.hub)/(rid+'.json'),{
            'run_id':rid,'target':'hub','subject':'study','schema':2,'level':'hub','workflow_node':task,
            'cwd':str(lab.hub),'backend':'claude','status':'completed','last_message':task+' evidence'})
        monkeypatch.setenv('NEWTS_RUN_SUBJECT','study');monkeypatch.setenv('NEWTS_RUN_NODE',task);monkeypatch.setenv('NEWTS_RUN_ID',rid)
        k.studies.move(hub.root,'study','done')
    for key in ('NEWTS_RUN_SUBJECT','NEWTS_RUN_NODE','NEWTS_RUN_ID'):monkeypatch.delenv(key)
    captured=[]
    lab_profile.start_graph(lab,'study',lambda _lab,spec:captured.append(spec) or {'run_id':'final'},RunSpec)
    assert len(captured)==1
    spec=captured[0]
    assert set(spec.extra['context']['run_ids'])=={'run-analysis','run-writing'}
    assert {Path(p).name for p in spec.extra['context_outputs']}=={'analysis.md','review.md'}
    assert all(Path(p).is_absolute() for p in spec.extra['context_outputs'])
    run=enqueue(lab,spec)
    prompt=(manifest.run_dir(lab.agents_dir(lab.hub),run['run_id'])/'prompt.md').read_text(encoding='utf-8')
    assert 'analysis evidence' in prompt and 'writing evidence' in prompt
