"""Entry decisions use arbitrary task graphs, checkpoints and the existing journal."""
import pytest

from conftest import kernel


def setup(hub, *, graph=True, checkpoints=(), loop=False):
    k = kernel()
    d = k.define.read(hub.root)
    # Deliberately unrelated to research phases; the labels and IDs belong to this workflow.
    for sid in ('collect', 'inspect', 'combine'):
        d['steps'][sid] = {'id': sid, 'label': sid.title(), 'also': [], 'room': 'study', 'do': None}
    w = {'id': 'custom', 'title': 'Custom process', 'default': True,
         'path': ['collect', 'inspect', 'combine'], 'routes': {}, 'use': {}, 'checkpoints': list(checkpoints)}
    if graph:
        w.update(start=['collect', 'inspect'], nodes={
            'collect': {'procedure': None, 'instructions': 'Collect evidence', 'next': ['combine']},
            'inspect': {'procedure': None, 'instructions': 'Inspect evidence', 'next': ['combine']},
            'combine': {'procedure': None, 'instructions': 'Combine evidence', 'join': True,
                        'next': ['collect', 'inspect'] if loop else []}})
    d['workflows'] = [w]
    k.define.write(hub.root, d)
    from kernel import entry
    w = k.model.workflow('custom', hub.root)
    return k, entry, w


def plan(entry, hub, w, **tasks):
    return {'revision': entry.revision(hub.root, w), 'tasks': {
        sid: {'action': action, 'note': 'Researcher selected existing work',
              'refs': ['existing/brief.md'] if action == 'reuse' else []}
        for sid, action in tasks.items()}}


def test_reuse_arrives_at_join_without_fabricating_a_run_or_completed_task(hub):
    k, entry, w = setup(hub)
    k.studies.new(hub.root, 'sample', entry=plan(entry, hub, w, collect='reuse'), by='pi')
    entry.apply(hub.root, 'sample')
    s = k.studies.study(hub.root, 'sample')
    assert s['runnable'] == ['inspect'] and s['joins'] == {'combine': ['collect']}
    assert s['completed_steps'] == []
    assert not k.journal.events(hub.root, 'sample', ('approval', 'task-bind', 'task-completed'))
    event = k.journal.events(hub.root, 'sample', ('task-reused',))[0]
    assert event['refs'] == ['existing/brief.md'] and event['selected_by'] == 'pi'
    k.studies.move(hub.root, 'sample', 'done')
    assert k.studies.study(hub.root, 'sample')['runnable'] == ['combine']


def test_plain_ordered_workflow_can_reuse_work_and_later_execute_normally(hub):
    k, entry, w = setup(hub, graph=False)
    k.studies.new(hub.root, 'sample', entry=plan(entry, hub, w, collect='reuse'), by='pi')
    entry.apply(hub.root, 'sample')
    assert k.studies.study(hub.root, 'sample')['runnable'] == ['inspect']
    k.studies.move(hub.root, 'sample', 'done')
    k.studies.move(hub.root, 'sample', 'done')
    assert k.studies.study(hub.root, 'sample')['finished']


@pytest.mark.parametrize('placement', ['before', 'during'])
def test_entry_never_approves_or_crosses_checkpoints(hub, placement):
    cp = {'id': 'check', 'title': 'Accept evidence', placement: 'collect', 'approver': 'me'}
    if placement == 'during': cp['at'] = 'accepting existing evidence'
    k, entry, w = setup(hub, checkpoints=[cp])
    k.studies.new(hub.root, 'sample', entry=plan(entry, hub, w, collect='reuse'), by='pi')
    entry.apply(hub.root, 'sample')
    s = k.studies.study(hub.root, 'sample')
    assert 'collect' not in s['runnable'] and s['task_waits'][0]['checkpoint'] == 'check'
    assert not k.journal.events(hub.root, 'sample', ('task-reused', 'approval'))
    k.checkpoints.decide(hub.root, 'sample', 'check', by='pi')
    entry.apply(hub.root, 'sample')
    assert k.journal.events(hub.root, 'sample', ('task-reused',))


def test_omission_is_distinct_and_first_visit_only(hub):
    k, entry, w = setup(hub, loop=True)
    k.studies.new(hub.root, 'sample', entry=plan(entry, hub, w, collect='omit', inspect='reuse'), by='pi')
    entry.apply(hub.root, 'sample')
    assert k.studies.study(hub.root, 'sample')['runnable'] == ['combine']
    k.studies.move(hub.root, 'sample', 'done')
    entry.apply(hub.root, 'sample')
    s = k.studies.study(hub.root, 'sample')
    assert set(s['runnable']) == {'collect', 'inspect'}
    assert all(t['visit'] == 2 for t in s['active_steps'])
    assert len(k.journal.events(hub.root, 'sample', ('task-omitted',))) == 1


def test_changed_workflow_requires_review_and_cancel_preserves_history(hub):
    k, entry, w = setup(hub)
    k.studies.new(hub.root, 'sample', entry=plan(entry, hub, w, collect='reuse', inspect='omit'), by='pi')
    d = k.define.read(hub.root)
    d['workflows'][0]['nodes']['collect']['instructions'] = 'Changed requirements'
    k.define.write(hub.root, d)
    with pytest.raises(ValueError, match='workflow changed'):
        entry.apply(hub.root, 'sample')
    entry.cancel(hub.root, 'sample')
    entry.apply(hub.root, 'sample')
    assert set(k.studies.study(hub.root, 'sample')['runnable']) == {'collect', 'inspect'}
    assert k.journal.events(hub.root, 'sample', ('entry-cancelled',))


def test_an_agent_cannot_select_reuse_or_cancel_the_researchers_plan(hub, monkeypatch):
    k, entry, w = setup(hub)
    value = plan(entry, hub, w, collect='reuse')
    monkeypatch.setenv('ARLOTOPE_RUN_ID', 'working-agent')
    with pytest.raises(k.studies.StudyError): k.studies.new(hub.root, 'sample', entry=value, by='pi')
    with pytest.raises(k.studies.StudyError): entry.cancel(hub.root, 'sample')


@pytest.mark.parametrize('patch', [
    {'action': 'approve'}, {'note': 12}, {'refs': []}, {'outcome': 'invented'}, {'refs': 'not-a-list'}])
def test_invalid_entry_is_rejected_before_filing_a_study(hub, patch):
    k, entry, w = setup(hub)
    value = plan(entry, hub, w, collect='reuse');value['tasks']['collect'].update(patch)
    with pytest.raises(ValueError): k.studies.new(hub.root, 'sample', entry=value, by='pi')
    assert k.studies.study(hub.root, 'sample') is None


def test_preview_matches_creation_without_writing_or_approving(hub):
    k, entry, w = setup(hub)
    value = plan(entry, hub, w, collect='reuse')
    before = k.journal.events(hub.root)
    preview = entry.preview(hub.root, w, value)
    assert preview['ready'] == ['inspect'] and preview['joins'] == {'combine': ['collect']}
    assert k.journal.events(hub.root) == before
    k.studies.new(hub.root, 'sample', entry=value, by='pi');entry.apply(hub.root, 'sample')
    assert k.studies.study(hub.root, 'sample')['runnable'] == preview['ready']


@pytest.mark.parametrize('action', ['omit','reuse'])
def test_starting_choices_need_no_explanation(hub, action):
    k, entry, w = setup(hub)
    value=plan(entry,hub,w,collect=action)
    value['tasks']['collect'].pop('note')
    k.studies.new(hub.root,'sample',entry=value,by='pi');entry.apply(hub.root,'sample')
    event=k.journal.events(hub.root,'sample',('task-omitted' if action=='omit' else 'task-reused',))[0]
    assert event['visit']==1 and not event.get('note')
    assert k.studies.study(hub.root,'sample')['runnable']==['inspect']


def test_reuse_follows_declared_outcome_and_all_reused_work_finishes(hub):
    k, entry, w = setup(hub, graph=False)
    d = k.define.read(hub.root)
    d['workflows'][0]['routes'] = {'collect': {'already-checked': 'combine'}}
    k.define.write(hub.root, d)
    w = k.model.workflow('custom', hub.root)
    value = plan(entry, hub, w, collect='reuse', combine='reuse')
    value['tasks']['collect']['outcome'] = 'already-checked'
    preview = entry.preview(hub.root, w, value)
    assert preview['finished'] and [e['node'] for e in preview['resolved']] == ['collect', 'combine']
    k.studies.new(hub.root, 'sample', entry=value, by='pi')
    entry.apply(hub.root, 'sample')
    s = k.studies.study(hub.root, 'sample')
    assert s['finished'] and s['step'] == 'combine' and s['completed_steps'] == []


def test_presentation_changes_do_not_invalidate_reuse(hub):
    k, entry, w = setup(hub)
    value = plan(entry, hub, w, collect='reuse')
    d = k.define.read(hub.root)
    d['workflows'][0]['nodes']['collect'].update(label='Collect specimens', room='bench', tags=['field'])
    k.define.write(hub.root, d)
    assert entry.prepare(hub.root, k.model.workflow('custom', hub.root), value)


@pytest.mark.parametrize('mode', ['continue', 'native-fork'])
@pytest.mark.parametrize('note', ['', 'Existing evidence supplied.'])
def test_reused_context_is_fresh_with_evidence_not_a_fabricated_session(hub, mode, note):
    import executor, lab_profile
    from test_agent_assignments import configure
    k, entry, w = setup(hub, graph=False)
    d = k.define.read(hub.root)
    d['workflows'][0]['nodes'] = {'inspect': {'context': {'mode': mode, 'from': 'collect'}, 'instructions': 'Inspect the existing work'}}
    k.define.write(hub.root, d);w = k.model.workflow('custom', hub.root)
    starting = plan(entry, hub, w, collect='reuse')
    starting['tasks']['collect']['note'] = note
    k.studies.new(hub.root, 'sample', entry=starting, by='pi')
    lab, _ = configure(hub)
    specs = []
    def enqueue(_lab, spec):
        specs.append(spec)
        return {'run_id': 'fixture-only'}
    assert lab_profile.start_graph(lab, 'sample', enqueue, executor.RunSpec) == ['fixture-only']
    assert specs[0].extra['context'] == {'mode': 'fresh'}
    assert 'existing/brief.md' in specs[0].prompt_override
    assert specs[0].extra['input_evidence'][0]['node'] == 'collect'
    assert not k.journal.events(hub.root, 'sample', ('task-bind',))  # Fixture only, no real agent was queued.


def test_join_handoff_keeps_real_context_and_imported_references(hub, monkeypatch):
    import executor, lab_profile
    from test_agent_assignments import configure
    k, entry, w = setup(hub)
    d = k.define.read(hub.root)
    ns = d['workflows'][0]['nodes']
    ns['collect']['outputs'] = ['not-imported.md']
    ns['inspect']['outputs'] = ['inspection.md']
    ns['combine']['context'] = {'mode': 'fresh', 'handoff': True, 'from': ['collect', 'inspect']}
    k.define.write(hub.root, d)
    w = k.model.workflow('custom', hub.root)
    k.studies.new(hub.root, 'sample', entry=plan(entry, hub, w, collect='reuse'), by='pi')
    entry.apply(hub.root, 'sample')
    lab, _ = configure(hub)
    root = hub.root / 'studies/sample'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'inspection.md').write_text('Inspection evidence', encoding='utf-8')
    k.branches.bind(hub.root, 'sample', 'inspect', 'inspection-run')
    executor.manifest.write_manifest(lab.agents_dir(lab.hub) / 'inspection-run.json', {
        'run_id': 'inspection-run', 'target': 'hub', 'subject': 'sample', 'schema': 2,
        'level': 'hub', 'workflow_node': 'inspect', 'cwd': str(root), 'backend': 'claude',
        'status': 'completed', 'last_message': 'Inspected the evidence.'})
    monkeypatch.setenv('ARLOTOPE_RUN_SUBJECT', 'sample')
    monkeypatch.setenv('ARLOTOPE_RUN_NODE', 'inspect')
    monkeypatch.setenv('ARLOTOPE_RUN_ID', 'inspection-run')
    k.studies.move(hub.root, 'sample', 'done')
    for key in ('ARLOTOPE_RUN_SUBJECT', 'ARLOTOPE_RUN_NODE', 'ARLOTOPE_RUN_ID'):
        monkeypatch.delenv(key)
    specs = []
    lab_profile.start_graph(lab, 'sample', lambda _, s: specs.append(s) or {'run_id': 'joined'}, executor.RunSpec)
    spec = specs[0]
    assert spec.extra['context']['run_ids'] == ['inspection-run']
    assert spec.extra['context']['handoff'] is True
    assert 'inspection.md' in spec.prompt_override and 'not-imported.md' not in spec.prompt_override
    assert 'existing/brief.md' in spec.prompt_override
