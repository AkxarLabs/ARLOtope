"""Real task lineage, parallel research graph visits and lightweight assistant/room contracts."""
import json
from pathlib import Path

import pytest

from conftest import REPO, kernel, load


def graph(hub):
    k=kernel()
    d=k.define.read(hub.root)
    d['workflows']=[{'id':'parallel','title':'Parallel research','default':True,'path':['seed','analysis','writing','final'],
        'routes':{},'use':{},'checkpoints':[], 'nodes':{
            'seed':{'next':['analysis','writing'],'procedure':None,'instructions':'Plan.'},
            'analysis':{'next':['final'],'procedure':None,'instructions':'Analyze.'},
            'writing':{'next':['final'],'procedure':None,'instructions':'Review.','agent':{'role':'reviewer'}},
            'final':{'next':[],'join':True,'procedure':None,'instructions':'Synthesize.'}}}]
    k.define.write(hub.root,d)
    k.studies.new(hub.root,'study','Parallel study')
    return k


def test_parallel_visits_join_and_no_cross_branch_completion(hub,monkeypatch):
    k=graph(hub)
    k.studies.move(hub.root,'study','done')
    assert set(k.studies.study(hub.root,'study')['runnable'])=={'analysis','writing'}
    with pytest.raises(k.studies.StudyError,match='Several tasks'):
        k.studies.move(hub.root,'study','done')
    monkeypatch.setenv('NEWTS_RUN_SUBJECT','study');monkeypatch.setenv('NEWTS_RUN_NODE','analysis')
    k.studies.move(hub.root,'study','done')
    s=k.studies.study(hub.root,'study')
    assert s['runnable']==['writing'] and s['joins']=={'final':['analysis']}
    monkeypatch.setenv('NEWTS_RUN_NODE','writing')
    k.studies.move(hub.root,'study','done')
    assert k.studies.study(hub.root,'study')['runnable']==['final']
    monkeypatch.setenv('NEWTS_RUN_NODE','final')
    assert k.studies.move(hub.root,'study','done')['finished']


def test_parallel_checkpoint_does_not_reset_the_other_branch(hub,monkeypatch):
    k=graph(hub)
    d=k.define.read(hub.root);d['workflows'][0]['checkpoints']=[{'id':'review','title':'Review','before':'writing','approver':'me'}]
    k.define.write(hub.root,d)
    k.studies.move(hub.root,'study','done')
    assert k.studies.study(hub.root,'study')['runnable']==['analysis']
    k.checkpoints.decide(hub.root,'study','review',by='pi',via='cli')
    assert set(k.studies.study(hub.root,'study')['runnable'])=={'analysis','writing'}


def test_graph_definition_roundtrip_and_ambiguous_continuation(hub):
    k=graph(hub)
    w=k.model.workflow('parallel',hub.root)
    assert w['nodes']['final']['join']
    from workflow_graph import validate
    ns=[{'id':'a','next':['b','c']},{'id':'b','next':[],'context':{'mode':'continue','from':'a'}},
        {'id':'c','next':[],'context':{'mode':'continue','from':'a'}}]
    assert any('only one branch' in p for p in validate(ns))
    ns[2]['context']['mode']='fork'
    assert validate(ns)==[]


def test_mutually_exclusive_outcomes_can_continue_the_same_source():
    from workflow_graph import validate
    ns=[{'id':'source','next':[],'outcomes':{'accept':['write'],'revise':['revise']}},
        {'id':'write','next':[],'context':{'mode':'continue','from':'source'}},
        {'id':'revise','next':[],'context':{'mode':'continue','from':'source'}}]
    assert validate(ns)==[]


def test_malformed_outcome_routes_return_validation_errors():
    from workflow_graph import validate
    ns=[{'id':'source','next':['review'],'outcomes':{'revise':{'invalid':'mapping'}}},
        {'id':'review','next':[],'context':{'mode':'continue','from':'source'}}]
    assert any('existing destinations' in p for p in validate(ns))


def test_context_continuation_resumes_and_prevents_duplicate_ownership(hub):
    import executor
    from executor import contexts, manifest
    lab=executor.Lab(hub.root)
    path=lab.agents_dir(lab.hub)/'source.json';path.parent.mkdir(parents=True,exist_ok=True)
    source={'run_id':'source','schema':2,'target':'hub','level':'hub','cwd':str(lab.hub),'backend':'codex',
            'session_id':'thread-1','status':'completed','label':'Analyze','last_message':'Evidence is in results.json.'}
    manifest.write_manifest(path,source)
    fresh_prompt, fresh = contexts.prepare(lab, {'mode':'fresh'}, 'codex', lab.hub, 'Start independently.')
    assert fresh_prompt == 'Start independently.' and 'session_id' not in fresh and 'resume' not in fresh
    prompt,fields=contexts.prepare(lab,{'mode':'continue','run_id':'source'},'codex',lab.hub,'Review the result.')
    assert fields['session_id']=='thread-1' and fields['resume']['text']==prompt
    manifest.write_manifest(path.with_name('child.json'),{**source,'run_id':'child','status':'queued'})
    with pytest.raises(executor.SpecError,match='active work'):
        contexts.prepare(lab,{'mode':'continue','run_id':'source'},'codex',lab.hub,'Another task')
    text,fork=contexts.prepare(lab,{'mode':'fork','run_id':'source'},'opencode',lab.hub,'Independent work',['results.json'])
    assert 'not an exact conversation clone' in text and 'results.json' in text and 'session_id' not in fork


def test_role_instructions_are_real_and_unknown_roles_fail(hub):
    from executor.contexts import role_text
    from executor import Lab,SpecError
    assert 'Independently assess' in role_text(Lab(hub.root),'reviewer')
    with pytest.raises(SpecError,match='Unknown role'):
        role_text(Lab(hub.root),'imaginary')


def test_assistant_summary_ignores_its_own_run(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/assistant')
    snap={'items':[{'id':'one','title':'Study','state':'active'}], 'runs':[]}
    _,before=api.summary(snap)
    snap['runs']=[{'run_id':'assistant','assistant':True,'status':'working'}]
    _,after=api.summary(snap)
    assert before==after
    snap['items'][0]['state']='analysis'
    assert api.summary(snap)[1]!=before


def test_assistant_routes_roles_and_subagents_to_real_runs(hub, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    api = load('dashboard/assistant')
    old = [{'run_id': 'old-' + str(i), 'status': 'completed'} for i in range(35)]
    review = {'run_id': 'review-run', 'subject': 'replication', 'status': 'waiting_input',
              'role': 'reviewer', 'backend': 'acp', 'workflow_node': 'review',
              'subagents': [{'id': 'lens-1', 'type': 'novelty', 'status': 'working'}]}
    facts, _ = api.summary({'runs': old + [review], 'agents': [
        {'worker_id': 'terminal-1', 'interactive': True, 'role': 'analyst', 'status': 'working'}],
        'artifacts': [{'id': 'report', 'study': 'replication', 'run_id': 'review-run'}]})
    assert facts['runs'][0]['id'] == 'review-run' and len(facts['runs']) == 30
    assert facts['runs'][0]['link'] == '#/run/review-run'
    assert facts['runs'][0]['subagents'][0]['route_to'] == 'review-run'
    assert facts['terminal_agents'][0]['id'] == 'terminal-1'
    assert facts['artifacts'][0]['link'] == '#/artifacts/report'


def test_disabled_assistant_updates_do_no_snapshot_or_agent_work(hub, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    api = load('dashboard/assistant')
    monkeypatch.setattr(api.ctx, 'HUB', hub.root)
    def unwanted():
        raise AssertionError('Disabled automatic updates must not rebuild the workspace or call a model.')
    monkeypatch.setattr(api.sources, 'snapshot', unwanted)
    assert api.update({}) == ({'ok': True, 'automatic': False}, 200)


def test_room_draft_is_private_until_applied(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/room_design');monkeypatch.setattr(api.ctx,'HUB',hub.root);monkeypatch.setattr(api.ctx,'LAB',hub.lab)
    data,code=api.op({'action':'create','room':'study','text':'A reading room'})
    assert code==200 and not (hub.lab/'rooms/study/room.json').exists()
    did=data['id']
    assert api.op({'action':'apply','id':did})[1]==400
    assert api.op({'action':'save','id':did,'definition':{'size':[-1,3]}})[1]==400
    assert api.op({'action':'apply','id':did,'confirm':True})[1]==200
    assert (hub.lab/'rooms/study/room.json').is_file()


def test_native_graph_execution_resumes_one_branch_and_hands_off_the_other(hub, monkeypatch):
    import sys
    import time
    import yaml
    import executor
    import lab_profile
    k = graph(hub)
    definition = k.define.read(hub.root)
    ns = definition['workflows'][0]['nodes']
    ns['analysis']['context'] = {'mode': 'continue', 'from': 'seed'}
    ns['writing']['context'] = {'mode': 'fork', 'from': 'seed'}
    for sid, node in ns.items():
        node['outputs'] = [sid + '.md']
    k.define.write(hub.root, definition)
    (hub.lab / 'config.yaml').write_text(yaml.safe_dump({'agents': {'programmatic': {
        'enabled': True, 'backend': 'claude', 'live': False, 'max_depth': 1,
        'max_parallel': 3, 'backends': {'claude': {'command': [sys.executable, str(REPO / 'tests/fake_workflow_agent.py')]}}
    }}}), encoding='utf-8')
    monkeypatch.setenv('FAKE_MODE', 'complete')
    lab = executor.Lab(hub.root)
    lab_profile.start_graph(lab, 'study', executor.enqueue, executor.RunSpec)
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        executor.tick(lab)
        runs = {m['workflow_node']: m for *_rest, m in executor.all_runs(lab) if m.get('workflow_node')}
        if len(runs) == 4 and all(m['status'] == 'completed' for m in runs.values()):
            break
        time.sleep(.25)
    assert k.studies.study(hub.root, 'study')['finished'], runs
    assert len(runs) == 4 and all(m['status'] == 'completed' for m in runs.values()), runs
    assert runs['seed']['session_id'] == runs['analysis']['session_id']
    assert runs['seed']['session_id'] != runs['writing']['session_id']
    source = runs['analysis']['context']['source_run']
    assert source == runs['seed']['run_id']
    rd = executor.run_dir(lab.agents_dir(lab.hub), runs['analysis']['run_id'])
    call = json.loads((rd / 'fake_calls.jsonl').read_text(encoding='utf-8').splitlines()[0])
    assert call['argv'][call['argv'].index('--resume') + 1] == runs['seed']['session_id']
    pre = (executor.run_dir(lab.agents_dir(lab.hub), runs['writing']['run_id']) / 'preamble.md').read_text(encoding='utf-8')
    assert 'Independently assess' in pre


def test_queued_task_is_rechecked_and_duplicate_report_is_idempotent(hub, monkeypatch):
    from kernel.branches import bind, begin_run
    k = graph(hub)
    bind(hub.root, 'study', 'seed', 'first')
    manifest = {'subject': 'study', 'workflow_node': 'seed', 'workflow_visit': 1, 'run_id': 'first'}
    begin_run(hub.root, manifest)
    monkeypatch.setenv('NEWTS_RUN_SUBJECT', 'study')
    monkeypatch.setenv('NEWTS_RUN_NODE', 'seed')
    monkeypatch.setenv('NEWTS_RUN_ID', 'first')
    k.studies.move(hub.root, 'study', 'done')
    assert k.studies.move(hub.root, 'study', 'done')['moved'] is False
    with pytest.raises(k.studies.StudyError, match='no longer active'):
        begin_run(hub.root, manifest)


def test_assistant_uses_one_native_session_and_refreshes_authoritative_facts(hub, monkeypatch):
    hub.add_registry_row('s',title='Current study',state='active')
    import executor
    from executor import manifest
    import yaml
    import sys
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    api = load('dashboard/assistant')
    monkeypatch.setattr(api.ctx, 'HUB', hub.root)
    monkeypatch.setattr(api.sources, 'snapshot', lambda: {'items': [{'id': 's', 'title': 'Current study', 'state': 'active'}]})
    (hub.lab / 'config.yaml').write_text(yaml.safe_dump({'agents': {'programmatic': {
        'enabled': True, 'backend': 'claude', 'live': False, 'max_depth': 1,
        'backends': {'claude': {'command': [sys.executable, str(REPO / 'tests/fake_claude.py')]}}
    }}}), encoding='utf-8')
    first, code = api.send({'text': 'What is active?'})
    assert code == 200
    lab = executor.Lab(hub.root)
    target, cwd, path, run = executor.find_run(lab, first['run_id'])
    manifest.transition(lab, path, run, 'completed', by='test', session_id='assistant-thread')
    monkeypatch.setattr(api.sources, 'snapshot', lambda: {'items': [{'id': 's', 'title': 'Current study', 'state': 'writing'}]})
    second, code = api.send({'text': 'What changed?'})
    assert code == 200 and second['run_id'] == first['run_id']
    updated = executor.find_run(lab, first['run_id'])[3]
    assert updated['session_id'] == 'assistant-thread' and updated['resume']['mode'] == 'reply'
    contexts = list((hub.lab / '.bus/assistant-context').glob('*.json'))
    facts = next(json.loads(p.read_text(encoding='utf-8')) for p in contexts
                 if json.loads(p.read_text(encoding='utf-8'))['projects'][0]['state']=='writing')
    assert len(contexts)==2
    before={p:p.read_bytes() for p in contexts}
    manifest.write_manifest(path,{**updated,'pending_question':{'id':'q'}})
    assert api.send({'text':'Keep my rejected draft.'})[1]==400
    assert {p:p.read_bytes() for p in contexts}==before
    fresh,code=api.send({'text':'New focus.', 'fresh':True,'study':'s'})
    assert code==200 and fresh['run_id']!=first['run_id']
    assert {p:p.read_bytes() for p in contexts}==before
    assert len(list((hub.lab / '.bus/assistant-context').glob('*.json')))==3
    assert facts['projects'][0]['state'] == 'writing'
    assert facts['tools']['inspect_run'][-1] == '--files'
    assert facts['tools']['message_run'][-4:] == ['reply', '<run-id>', '--text', '<requested-message>']
    assert any('user requested' in instruction for instruction in facts['routing'])
    import os, subprocess
    for name in ('all_runs', 'study_status', 'published_results'):
        result = subprocess.run(facts['tools'][name], cwd=hub.root, capture_output=True, text=True,
                                env={**os.environ, 'NEWTS_HUB': str(hub.root)}, timeout=15)
        assert result.returncode == 0, (name, result.stdout, result.stderr)


def test_queue_lock_retries_windows_delete_pending_collision(hub, monkeypatch):
    from executor import procs
    real_open = procs.os.open
    calls = []
    def pending_once(path, flags, *args):
        if not calls:
            calls.append(path)
            raise PermissionError('Windows delete-pending collision')
        return real_open(path, flags, *args)
    monkeypatch.setattr(procs.os, 'open', pending_once)
    path = hub.lab / '.bus/test-task.lock'
    with procs.excl_lock(path, wait=1):
        assert path.exists()
    assert not path.exists()


def test_loop_context_is_bound_to_the_exact_incoming_visit(hub, monkeypatch):
    from kernel.branches import bind
    k = graph(hub)
    d = k.define.read(hub.root)
    ns = d['workflows'][0]['nodes']
    ns['seed']['next'] = ['analysis']
    ns['analysis']['next'] = ['seed']
    k.define.write(hub.root, d)
    monkeypatch.setenv('NEWTS_RUN_SUBJECT', 'study')
    for sid, rid in [('seed', 'plan-1'), ('analysis', 'analysis-1'), ('seed', 'plan-2')]:
        bind(hub.root, 'study', sid, rid)
        monkeypatch.setenv('NEWTS_RUN_NODE', sid)
        monkeypatch.setenv('NEWTS_RUN_ID', rid)
        k.studies.move(hub.root, 'study', 'done')
    token = k.studies.study(hub.root, 'study')['active_steps'][0]
    assert token['id'] == 'analysis' and token['visit'] == 2
    assert token['incoming_runs'] == {'seed': 'plan-2'}


def test_revoked_checkpoint_refuses_an_already_queued_task(hub):
    from kernel.branches import bind, begin_run
    k = graph(hub)
    d = k.define.read(hub.root)
    d['workflows'][0]['checkpoints'] = [{'id': 'start', 'title': 'Start', 'before': 'seed', 'approver': 'me'}]
    k.define.write(hub.root, d)
    assert k.model.check(hub.root, k.rules.check_names(hub.root)) == []
    k.checkpoints.decide(hub.root, 'study', 'start', by='pi', via='cli')
    bind(hub.root, 'study', 'seed', 'queued')
    k.checkpoints.decide(hub.root, 'study', 'start', decision='revoked', by='pi', via='cli')
    with pytest.raises(k.studies.StudyError, match='checkpoint'):
        begin_run(hub.root, {'subject': 'study', 'workflow_node': 'seed', 'workflow_visit': 1, 'run_id': 'queued'})


def test_graph_rename_preserves_active_branches(hub, tmp_path):
    k = graph(hub)
    k.studies.move(hub.root, 'study', 'done')
    k.studies.rename_step(hub.root, 'analysis', 'evaluate')
    assert set(k.studies.study(hub.root, 'study')['runnable']) == {'evaluate', 'writing'}
    assert 'evaluate' in k.model.workflow('parallel', hub.root)['nodes']['seed']['next']
