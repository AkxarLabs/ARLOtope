"""Workflow history links durable records without inferring task completion from a stopped turn."""
import json
from pathlib import Path

import pytest

from conftest import kernel

kernel()
import labfiles
import study_history as H


def test_attached_brief_to_interrupted_task_gate_and_loop_history(hub, tmp_path, monkeypatch):
    from test_workflow_entry import setup, plan
    from research_start import create
    from executor import Lab, attention, manifest
    from task_completion import flag_runs
    k, entry, workflow = setup(hub, loop=True)
    definition = k.define.read(hub.root)
    definition['workflows'][0]['checkpoints'] = [
        {'id': 'inspect-results', 'title': 'Inspect results', 'before': 'combine', 'approver': 'me'}]
    k.define.write(hub.root, definition)
    workflow = k.model.workflow('custom', hub.root)
    project = tmp_path / 'existing-project'
    project.mkdir()
    brief = project / 'brief.md'
    brief.write_text('# Existing question and collected evidence\n', encoding='utf-8')
    original = brief.read_bytes()
    starting = plan(entry, hub, workflow, collect='reuse')
    starting['tasks']['collect'].update(refs=['brief.md'], note='')
    created = create(hub.root, title='Existing project', question='Inspect this evidence.',
                     local=str(project), workflow='custom', entry=starting)
    slug = created['study']
    assert brief.read_bytes() == original
    assert k.studies.study(hub.root, slug)['runnable'] == ['inspect']
    assert not k.journal.events(hub.root, slug, ('task-completed', 'approval'))

    # A lost/limited provider leaves its exact task pending, with recoverable run evidence.
    lab = Lab(hub.root)
    folder = lab.agents_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'inspection.json'
    run = {'schema': 2, 'run_id': 'inspection', 'target': slug, 'subject': slug,
           'workflow_node': 'inspect', 'workflow_visit': 1, 'backend': 'codex',
           'status': 'failed', 'failure_kind': 'usage_limit', 'session_id': 'saved-session',
           'attempt': 1, 'reason': 'Usage limit reached', 'created': labfiles.now()}
    k.branches.bind(hub.root, slug, 'inspect', run['run_id'])
    labfiles.write_json(path, run)
    assert any(a['kind'] == 'crashed' for a in attention.run_items(lab, [(path, run)]))
    assert k.studies.study(hub.root, slug)['runnable'] == ['inspect']
    run.update(status='completed', failure_kind=None, attempt=2)
    labfiles.write_json(path, run)
    assert flag_runs(hub.root, [run])[0]['needs_followup']
    assert next(v for v in H.read(hub.root, slug)['visits'] if v['node'] == 'inspect')['outcome'] is None

    # Only an accepted task outcome reaches the fixture's PI checkpoint.
    with monkeypatch.context() as agent:
        agent.setenv('ARLOTOPE_RUN_ID', 'inspection')
        agent.setenv('ARLOTOPE_RUN_SUBJECT', slug)
        agent.setenv('ARLOTOPE_RUN_NODE', 'inspect')
        k.studies.move(hub.root, slug, 'done')
    study = k.studies.study(hub.root, slug)
    assert not study['runnable'] and study['waiting']['checkpoint'] == 'inspect-results'
    k.checkpoints.decide(hub.root, slug, 'inspect-results', by='pi', via='cli')
    k.studies.move(hub.root, slug, 'done')
    # The initial import does not suppress work when the workflow loops back.
    study = k.studies.study(hub.root, slug)
    assert set(study['runnable']) == {'collect', 'inspect'}
    assert all(t['visit'] == 2 for t in study['active_steps'])
    history = H.read(hub.root, slug)
    assert {v['outcome']['kind'] for v in history['visits'] if v['outcome']} >= {'task-reused', 'task-completed'}
    assert next(r for r in history['runs'] if r['run_id'] == 'inspection')['attempt'] == 2
    assert Path(H.save(hub.root, slug)['path']).is_file()
    assert brief.read_bytes() == original


def test_full_history_preserves_passes_attempts_and_source_isolation(hub):
    from test_workflow_entry import setup,plan
    k,entry,w=setup(hub,loop=True)
    k.studies.new(hub.root,'sample',entry=plan(entry,hub,w,collect='omit'),by='pi')
    entry.apply(hub.root,'sample')
    k.journal.append(hub.root,'sample','task-bind','kernel',node='inspect',visit=1,run_id='one')
    folder=hub.lab/'.bus/agents';folder.mkdir(parents=True)
    manifest={'schema':2,'run_id':'one','subject':'sample','workflow_node':'inspect','workflow_visit':1,
              'backend':'acp','status':'timeout','attempt':2,'attempts':[{'attempt':1,'status':'failed'}],
              'command':['private-argument'],'session_id':'session','stream':'one.stream.jsonl'}
    (folder/'one.json').write_text(json.dumps(manifest))
    (folder/'other.json').write_text(json.dumps({**manifest,'subject':'other','run_id':'other'}))
    (folder/'explainer.json').write_text(json.dumps({'schema':2,'run_id':'explainer','subject':'hub','status':'completed','explains':{'study':'sample','run':'one'}}))
    ledger=hub.lab/'.bus/runs.jsonl';ledger.write_text('\n'.join(json.dumps({'run_id':r,'status':'failed'}) for r in ('one','other')))
    before=k.journal.path(hub.root).read_bytes()
    result=H.read(hub.root,'sample')
    visits={v['node']:v for v in result['visits']}
    assert visits['collect']['outcome']['kind']=='task-omitted'
    assert visits['inspect']['outcome'] is None and visits['inspect']['runs']==['one']
    own=next(r for r in result['runs'] if r['run_id']=='one')
    assert own['attempt']==2 and own['attempts'][0]['status']=='failed'
    assert own['transcript']==str(folder/'one.stream.jsonl')
    assert {r['run_id'] for r in result['runs']}=={'one','explainer'}
    assert 'private-argument' not in json.dumps(result)
    assert result['run_transitions']==[{'run_id':'one','status':'failed'}]
    assert k.journal.path(hub.root).read_bytes()==before
    assert not (hub.root/'studies/sample/history').exists()
    k.studies.move(hub.root,'sample','done');k.studies.move(hub.root,'sample','done')
    result=H.read(hub.root,'sample')
    assert any(v['node']=='collect' and v['visit']==2 and v['outcome'] is None for v in result['visits'])
    saved=H.save(hub.root,'sample')
    assert Path(saved['path']).is_file()
    assert json.loads((Path(saved['path']).parent/'workflow.json').read_text())['schema']==1
    assert 'snapshot' in Path(saved['path']).read_text()
    H.save(hub.root,'sample')  # Refresh is idempotent; canonical evidence stays separate.


def test_history_does_not_truncate_long_journals(hub):
    k=kernel();k.studies.new(hub.root,'sample',by='pi')
    for n in range(315):k.journal.append(hub.root,'sample','title','pi',title=str(n))
    assert len(H.read(hub.root,'sample')['events'])==316
    with pytest.raises(ValueError):H.save(hub.root,'../escape')
    with pytest.raises(ValueError):H.read(hub.root,'missing')


def test_history_keeps_distinct_workflow_epochs(hub):
    from test_workflow_entry import setup
    k,_,_=setup(hub)
    k.studies.new(hub.root,'sample',by='pi')
    k.journal.append(hub.root,'sample','task-bind','kernel',node='collect',visit=1,run_id='old')
    k.journal.append(hub.root,'sample','workflow','pi',workflow='custom')
    k.journal.append(hub.root,'sample','task-bind','kernel',node='collect',visit=1,run_id='new')
    groups=[v for v in H.read(hub.root,'sample')['visits'] if v['node']=='collect']
    assert len(groups)==2 and groups[0]['execution']!=groups[1]['execution']


def test_ordered_cursor_keeps_loops_retries_and_workflow_changes_separate(hub):
    k=kernel();k.studies.new(hub.root,'ordered',at='proposal',by='pi')
    folder=hub.lab/'.bus/agents';folder.mkdir(parents=True)
    def run(rid, step, cursor):
        (folder/(rid+'.json')).write_text(json.dumps({'schema':2,'run_id':rid,'subject':'ordered',
            'assigned_step':step,'assigned_journal_index':cursor,'status':'completed','backend':'codex',
            'attempt':2,'attempts':[{'n':1,'stop_reason':'usage_limit'},{'n':2}],
            'task_label':'Saved task title'}))
    run('first','proposal',1);run('retry','proposal',1)
    k.journal.append(hub.root,'ordered','move','cli',**{'from':'proposal','to':'active','outcome':'done'})
    run('second','active',2)
    k.journal.append(hub.root,'ordered','move','cli',**{'from':'active','to':'proposal','outcome':'revise'})
    run('loop','proposal',3)
    k.journal.append(hub.root,'ordered','workflow','pi',workflow='quick')
    run('changed','proposal',4)
    before=k.journal.path(hub.root).read_bytes()
    history=H.read(hub.root,'ordered')
    groups=history['visits']
    assert groups[0]['runs']==['first','retry']
    assert groups[0]['label']=='Saved task title'
    assert groups[1]['runs']==['second']
    assert groups[2]['runs']==['loop'] and groups[2]['visit']==2
    assert groups[3]['runs']==['changed'] and groups[3]['execution']==2
    assert groups[3]['outcome'] is None
    assert next(r for r in history['runs'] if r['run_id']=='first')['assigned_journal_index']==1
    assert k.journal.path(hub.root).read_bytes()==before


def test_logs_join_history_by_run_without_changing_workflow(hub,monkeypatch):
    import arlo_cli,knowledge
    k=kernel();k.studies.new(hub.root,'sample',by='pi')
    before=k.journal.path(hub.root).read_bytes()
    monkeypatch.setenv('ARLOTOPE_HUB',str(hub.root))
    monkeypatch.setenv('ARLOTOPE_RUN_ID','one')
    monkeypatch.setenv('ARLOTOPE_RUN_SUBJECT','sample')
    monkeypatch.setenv('ARLOTOPE_ATTEMPT','2')
    assert arlo_cli.main(['log','Null result; retained the original method.','--tag','decision',
                          '--ref','runs/one/metrics.json','--agent','child'])==0
    note=H.read(hub.root,'sample')['notes'][0]
    assert note['run']=='one' and note['attempt']==2 and note['about']=={'run':'one','agent':'child'}
    assert note['refs']==['runs/one/metrics.json'] and note['tags']==['decision']
    assert knowledge.dispatch(hub.root,'sample','get',id=note['id'])['text'].startswith('Null result')
    assert k.journal.path(hub.root).read_bytes()==before


def test_ordered_entry_choices_remain_ordered_passes(hub):
    from test_workflow_entry import setup,plan
    k,entry,w=setup(hub,graph=False)
    k.studies.new(hub.root,'sample',entry=plan(entry,hub,w,collect='reuse'),by='pi')
    entry.apply(hub.root,'sample')
    groups=H.read(hub.root,'sample')['visits']
    assert [g['node'] for g in groups]==['collect','inspect']
    assert groups[0]['mode']=='ordered' and groups[0]['outcome']['kind']=='task-reused'
    assert groups[1]['active'] and groups[1]['outcome'] is None


def test_history_index_does_not_embed_full_answer_payloads(hub):
    import knowledge
    k=kernel();k.studies.new(hub.root,'sample',by='pi')
    knowledge.dispatch(hub.root,'sample','add',kind='answer',text='Question summary',title='Saved answer',
                       responses=[{'text':'full answer payload '*10000}])
    note=H.read(hub.root,'sample')['notes'][0]
    assert note['title']=='Saved answer' and 'responses' not in note


def test_renamed_task_keeps_its_pass_run_and_original_evidence(hub):
    from test_workflow_entry import setup
    k,_,_=setup(hub)
    k.studies.new(hub.root,'sample',by='pi')
    k.branches.bind(hub.root,'sample','collect','one')
    folder=hub.lab/'.bus/agents';folder.mkdir(parents=True)
    (folder/'one.json').write_text(json.dumps({'schema':2,'run_id':'one','subject':'sample',
        'workflow_node':'collect','workflow_visit':1,'task_label':'Original task title','status':'running'}))
    k.studies.rename_step(hub.root,'collect','gathering')
    history=H.read(hub.root,'sample')
    groups=[g for g in history['visits'] if g['node']=='gathering']
    assert len(groups)==1 and groups[0]['runs']==['one'] and groups[0]['active']
    assert groups[0]['label']=='Original task title' and groups[0]['recorded_nodes']==['collect']
    assert next(e for e in history['events'] if e['kind']=='task-bind')['node']=='collect'
