"""Task outcomes, independent verdicts and portable procedures without external agents."""
import base64
import io
import json
import shutil
import zipfile

import pytest

from conftest import REPO, kernel
kernel()


def setup(hub, ordered=False):
    k = kernel()
    definition = k.define.read(hub.root)
    definition['workflows'] = [{'id':'decision-test','title':'Review flow','default':True,
        'path':['seed','analysis','writing'], 'routes':{}, 'use':{},
        'checkpoints':[{'id':'judge-test','title':'Review evidence','before':'analysis','approver':'agent',
            'evidence':['studies/{study}/candidate.md'], 'judge':{'skill':'gate-review','max_visits':3},
            'decisions':{'proceed':'continue','revise':'seed','stop':'parked'}}],
        **({} if ordered else {'nodes':{'seed':{'instructions':'Investigate','procedure':None,'next':['analysis']},
            'analysis':{'instructions':'Analyze','procedure':None,'next':['writing']},
            'writing':{'instructions':'Write','procedure':None,'next':[]}}})}]
    k.define.write(hub.root, definition)
    k.studies.new(hub.root, 'sample', 'A study')
    candidate = hub.root/'studies/sample/candidate.md'
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text('Candidate evidence', encoding='utf-8')
    (candidate.parent/'IDEA.md').write_text('Study brief', encoding='utf-8')
    return k, candidate


def verdict(hub, choice='proceed'):
    import executor
    import gate_reviews as judges
    k = kernel()
    s = k.studies.study(hub.root,'sample')
    cp = k.checkpoints.find(hub.root,'sample','judge-test')
    revision, _ = judges.revision(hub.root,s,cp)
    output = hub.root/'verdict.json'
    output.write_text(json.dumps({'decision':choice,'reason':'Candidate meets the rubric.',
        'evidence':cp['evidence']}), encoding='utf-8')
    return executor.Lab(hub.root), {'run_id':'judge-run','status':'completed','subject':'sample',
        'cwd':str(hub.root), 'judge':{'checkpoint':cp['id'],'revision':revision,'scope':judges.scope(hub.root,s,cp),
            'output':'verdict.json','decisions':cp['decisions'],'evidence':cp['evidence']}}


@pytest.mark.parametrize('ordered',[False, True])
def test_accepted_verdict_advances_and_is_idempotent(hub, ordered):
    import gate_reviews as judges
    k, _ = setup(hub, ordered)
    k.studies.move(hub.root,'sample','done')
    lab, run = verdict(hub)
    judges.finish(lab,run)
    assert k.studies.approved(hub.root,'sample','judge-test')
    assert k.studies.study(hub.root,'sample')['step']=='analysis'
    before=len(k.journal.events(hub.root,'sample'))
    judges.finish(lab,run)
    assert len(k.journal.events(hub.root,'sample'))==before


def test_evidence_changed_during_review_is_rejected(hub):
    import gate_reviews as judges
    k, candidate = setup(hub)
    k.studies.move(hub.root,'sample','done')
    lab, run = verdict(hub)
    candidate.write_text('A different candidate', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence changed'):
        judges.finish(lab,run)
    assert not k.studies.approved(hub.root,'sample','judge-test')


def test_judge_cannot_bypass_a_required_check(hub,monkeypatch):
    import gate_reviews as judges
    k,_=setup(hub)
    d=k.define.read(hub.root);d['workflows'][0]['checkpoints'][0]['checks']=['append-only']
    k.define.write(hub.root,d);k.studies.move(hub.root,'sample','done')
    lab,run=verdict(hub)
    monkeypatch.setattr(k.checkpoints,'run_checks',lambda *args,**kw: {'append-only':{'code':1,'out':'Evidence changed'}})
    with pytest.raises(k.checkpoints.CheckpointError,match='did not pass'):
        judges.finish(lab,run)
    assert not k.studies.approved(hub.root,'sample','judge-test')


def test_researcher_only_gate_cannot_use_a_judge_verdict(hub):
    import gate_reviews as judges
    k,_=setup(hub)
    d=k.define.read(hub.root);d['workflows'][0]['checkpoints'][0]['approver']='me'
    k.define.write(hub.root,d);k.studies.move(hub.root,'sample','done')
    lab,run=verdict(hub)
    with pytest.raises(ValueError,match='gate or evidence changed'):
        judges.finish(lab,run)
    assert not k.studies.approved(hub.root,'sample','judge-test')


@pytest.mark.parametrize('mode',['continue','native-fork'])
def test_remote_context_uses_execution_path_instead_of_controller_mirror(hub,monkeypatch,mode):
    import executor
    from executor import contexts
    source={'run_id':'source','status':'completed','backend':'codex','session_id':'source-thread','machine':'box',
            'cwd':str(hub.root/'controller-mirror'), 'remote':{'machine':'box','path':'/research/Project'}}
    monkeypatch.setattr(contexts,'find_run',lambda *args: ('sample',hub.root,hub.root/'source.json',source))
    _, fields=contexts.prepare(executor.Lab(hub.root),{'mode':mode,'run_id':'source'},'codex','/research/Project','Next task',machine='box')
    assert fields['fork_session' if mode=='native-fork' else 'session_id']=='source-thread'
    with pytest.raises(executor.SpecError,match='same backend, machine and folder'):
        contexts.prepare(executor.Lab(hub.root),{'mode':mode,'run_id':'source'},'codex','/research/project','Next task',machine='box')


def test_revise_reenters_task_without_completing_gated_task(hub):
    import gate_reviews as judges
    k, _ = setup(hub)
    k.studies.move(hub.root,'sample','done')
    lab, run = verdict(hub,'revise')
    judges.finish(lab,run)
    s=k.studies.study(hub.root,'sample')
    assert s['runnable']==['seed'] and s['active_steps'][0]['visit']==2
    assert 'analysis' not in s['completed_steps']


def test_unknown_decision_or_evidence_is_rejected(hub):
    import gate_reviews as judges
    k, _=setup(hub)
    k.studies.move(hub.root,'sample','done')
    lab,run=verdict(hub,'invented')
    with pytest.raises(ValueError,match='declared gate decision'):
        judges.finish(lab,run)
    (hub.root/'verdict.json').write_text(json.dumps({'decision':'proceed','reason':'Trust me',
        'evidence':['unrelated-file']}),encoding='utf-8')
    with pytest.raises(ValueError,match='supplied evidence'):
        judges.finish(lab,run)


def test_new_visit_needs_a_new_review_and_changed_evidence_blocks_admission(hub):
    import gate_reviews as judges
    k,candidate=setup(hub)
    k.studies.move(hub.root,'sample','done')
    lab,run=verdict(hub)
    judges.finish(lab,run)
    from kernel.branches import bind, begin_run
    bind(hub.root,'sample','analysis','analysis-run')
    candidate.write_text('Changed after the verdict',encoding='utf-8')
    with pytest.raises(k.studies.StudyError,match='evidence changed'):
        begin_run(hub.root, {'subject':'sample','workflow_node':'analysis','workflow_visit':1,'run_id':'analysis-run'})
    k.studies.move_to(hub.root,'sample','seed')
    k.studies.move(hub.root,'sample','done')
    assert not k.studies.approved(hub.root,'sample','judge-test')


def test_ordered_back_route_reenters_the_gate(hub):
    import gate_reviews as judges
    k,_=setup(hub,ordered=True)
    d=k.define.read(hub.root);d['workflows'][0]['routes']={'writing':{'revisit':'analysis'}}
    k.define.write(hub.root,d);k.studies.move(hub.root,'sample','done')
    lab,run=verdict(hub);judges.finish(lab,run)
    k.studies.move_to(hub.root,'sample','writing')
    assert k.studies.approved(hub.root,'sample','judge-test')  # Historical review remains in the record.
    result=k.studies.move(hub.root,'sample','revisit')
    assert result['waiting']=='judge-test'
    assert not k.studies.approved(hub.root,'sample','judge-test')


def test_judge_is_fresh_and_uses_only_declared_evidence(hub,monkeypatch):
    import executor
    import gate_reviews as judges
    k,_=setup(hub)
    k.studies.move(hub.root,'sample','done')
    specs=[]
    monkeypatch.setattr(executor,'enqueue',lambda lab,spec: specs.append(spec) or {'run_id':'review'})
    monkeypatch.setattr(executor,'all_runs',lambda lab: [])
    assert judges.start_waiting(executor.Lab(hub.root),'sample')==['review']
    spec=specs[0]
    assert spec.role=='reviewer' and spec.max_minutes==15
    assert 'Independent gate' in spec.prompt_override and 'candidate.md' in spec.prompt_override
    assert 'context' not in spec.extra and 'last_message' not in spec.prompt_override
    import lab_profile
    (hub.lab/'RESEARCH.md').write_text('An opinion that should not bias the reviewer.',encoding='utf-8')
    pre=lab_profile.preamble(executor.Lab(hub.root),'review',
        {'skill':'gate-judge','subject':'sample','target':'sample','level':'hub','cfg':{},'workdir':hub.root},None)
    assert 'An opinion that should not bias' not in pre and 'Shared study records:' not in pre


def test_alternative_routes_merge_without_waiting_for_unselected_branch(hub,monkeypatch):
    k,_=setup(hub)
    d=k.define.read(hub.root); w=d['workflows'][0]
    w['checkpoints']=[]
    w['nodes']['seed'].update(next=[],outcomes={'analyze':'analysis','write':'writing'})
    w['nodes']['analysis']['next']=['writing']
    w['nodes']['writing']['join']=False
    k.define.write(hub.root,d)
    k.studies.move(hub.root,'sample','write')
    assert k.studies.study(hub.root,'sample')['runnable']==['writing']
    k.studies.move(hub.root,'sample','done')
    assert k.studies.study(hub.root,'sample')['finished']


def test_repetition_limit_stops_dispatch(hub):
    k,_=setup(hub)
    d=k.define.read(hub.root);w=d['workflows'][0]
    w['checkpoints']=[];w['nodes']['seed'].update(next=['seed'],max_visits=2)
    k.define.write(hub.root,d)
    k.studies.move(hub.root,'sample','done');k.studies.move(hub.root,'sample','done')
    s=k.studies.study(hub.root,'sample')
    assert not s['runnable'] and 'repetition limit' in s['blocked_reason']


def test_finished_turn_is_not_an_accepted_outcome(hub):
    from task_completion import flag_runs
    from kernel.branches import bind
    k,_=setup(hub);bind(hub.root,'sample','seed','owner')
    run={'run_id':'owner','status':'completed','subject':'sample','workflow_node':'seed','workflow_visit':1}
    assert flag_runs(hub.root,[run])[0]['needs_followup']
    k.studies.move(hub.root,'sample','done')
    assert not flag_runs(hub.root,[run])[0]['needs_followup']


def test_ordered_followup_uses_a_journal_cursor_not_second_precision_timestamps(hub):
    from task_completion import flag_runs
    k,_=setup(hub,ordered=True)
    k.studies.move_to(hub.root,'sample','analysis')
    run={'run_id':'ordered-owner','status':'completed','subject':'sample','assigned_step':'analysis',
         'assigned_journal_index':len(k.journal.events(hub.root,'sample')), 'started':k.journal.now()}
    assert flag_runs(hub.root,[run])[0]['needs_followup']


def test_export_includes_skills_and_hashes_resolved_content(hub):
    from workflow_export import export
    k,_=setup(hub)
    d=k.define.read(hub.root);w=d['workflows'][0]
    w['nodes']['seed']['skills']=['gate-review']
    k.define.write(hub.root,d)
    a=export(hub.root,'decision-test');b=export(hub.root,'decision-test')
    assert a['data']==b['data']
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(a['data']))) as archive:
        assert 'resources/skills/gate-review/SKILL.md' in archive.namelist()
        assert 'require the corresponding runner/tools' in archive.read('SKILL.md').decode()
    d['workflows'][0]['nodes']['seed']['instructions']='Changed objective'
    k.define.write(hub.root,d)
    assert export(hub.root,'decision-test')['revision'] != a['revision']


def test_identity_survives_lab_move(hub,tmp_path):
    from project_identity import lab_identity, register, discover
    first=lab_identity(hub.root)
    moved=tmp_path/'moved';shutil.copytree(hub.root,moved)
    assert lab_identity(moved)==first
    project=tmp_path/'project';project.mkdir()
    identity=register(project,first['execution_owner'],'sample',first['lab_id'])
    assert identity['project_id'] and discover()[0]['identity_matches']
    assert register(project,first['execution_owner'],'sample')['project_id']==identity['project_id']
    with pytest.raises(ValueError,match='another Lab'):
        register(project,'other','sample')


def test_project_discovery_is_bounded_and_does_not_attach(tmp_path):
    from project_identity import discover, register
    project=tmp_path/'git-project';(project/'.git').mkdir(parents=True)
    rows=discover(str(tmp_path),depth=1)
    assert rows[0]['path']==str(project) and not rows[0]['registered']
    assert not (project/'.bus').exists()
    (project/'.arlotope').mkdir();(project/'.arlotope/project.json').write_text('{broken')
    with pytest.raises(ValueError,match='identity is invalid'):
        register(project,'owner','sample')


def test_executor_runs_independent_review_and_continues_graph(hub,monkeypatch):
    import sys
    import time
    import yaml
    import executor
    import lab_profile
    k,_=setup(hub)
    (hub.lab/'config.yaml').write_text(yaml.safe_dump({'agents':{'programmatic':{
        'enabled':True,'backend':'claude','live':False,'max_parallel':2,
        'backends':{'claude':{'command':[sys.executable,str(REPO/'tests/fake_workflow_agent.py')]}}}}}),encoding='utf-8')
    monkeypatch.setenv('FAKE_MODE','complete')
    lab=executor.Lab(hub.root)
    lab_profile.start_graph(lab,'sample',executor.enqueue,executor.RunSpec)
    until=time.monotonic()+90
    while time.monotonic()<until:
        executor.tick(lab)
        runs=[m for *_x,m in executor.all_runs(lab)]
        if k.studies.study(hub.root,'sample')['finished'] and all(r['status']=='completed' for r in runs):
            break
        time.sleep(.25)
    assert k.studies.study(hub.root,'sample')['finished'], runs
    reviews=[r for r in runs if r.get('judge')]
    assert len(reviews)==1 and reviews[0].get('judge_result'), reviews
    assert reviews[0]['role']=='reviewer' and reviews[0]['context']['mode']=='fresh'
    assert len(runs)==4 and all(r['status']=='completed' for r in runs)
