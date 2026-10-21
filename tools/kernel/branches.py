"""Optional task graphs over the existing study journal. Linear workflows are unchanged."""
from __future__ import annotations

import os
from pathlib import Path

from . import journal, model
from workflow_graph import predecessors, targets


def locked(hub):
    from executor.procs import excl_lock
    return excl_lock(Path(hub) / 'lab/.bus/.task-state.lock')


def output_state(hub, s, node):
    from . import studies
    import remote_projects
    if remote_projects.location(s.get('project')):
        local = {str(Path(hub) / p): [(Path(hub) / p).stat().st_mtime_ns, (Path(hub) / p).stat().st_size]
                 if (Path(hub) / p).is_file() else None for p in studies.study_outputs(hub, dict(s, step=node['id']))}
        return {**local, **remote_projects.file_states(hub, s['id'], node.get('outputs', []))}
    root = Path(s.get('project') or Path('studies') / s['id'])
    if not root.is_absolute():
        root = Path(hub) / root
    files = [Path(hub) / p for p in studies.study_outputs(hub, dict(s, step=node['id']))]
    files += [root / p for p in node.get('outputs', [])]
    return {str(p): (p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else None for p in files}


def nodes(w, steps):
    path = w['path']
    return [dict({'id': sid, 'label': steps.get(sid, {}).get('label', sid),
                  'agent': steps.get(sid, {}).get('agent') or {}, 'next': path[i + 1:i + 2], 'room': steps.get(sid, {}).get('room'), 'tags': steps.get(sid, {}).get('tags', []),
                  'procedure': w.get('use', {}).get(steps.get(sid, {}).get('do'), steps.get(sid, {}).get('do'))},
                 **w.get('nodes', {}).get(sid, {})) for i, sid in enumerate(path)]


def fold(hub, s, events):
    w = model.workflow(s['workflow'], hub)
    ns = nodes(w, model.steps(hub))
    active, visits, arrivals, completed, bindings, incoming = {}, {}, {}, [], {}, {}
    resolved = []
    by_id = {n['id']: n for n in ns}
    remaps = {}
    for e in events:
        if e['kind'] == 'remap':
            mapping = e.get('map') or {}
            remaps = {k: mapping.get(v, v) for k, v in remaps.items()} | mapping
    def name(sid):
        return remaps.get(sid, sid)
    def enter(sid, source=None, source_run=None):
        sid, source = name(sid), name(source)
        if sid not in by_id:
            return
        if source:
            incoming.setdefault(sid, {})[source] = source_run
        if by_id[sid].get('join') and source:
            arrived = arrivals.setdefault(sid, set())
            arrived.add(source)
            if not predecessors(ns, sid).issubset(arrived):
                return
            arrivals.pop(sid, None)
        if sid not in active:
            visits[sid] = visits.get(sid, 0) + 1
            active[sid] = {'id': sid, 'visit': visits[sid], 'incoming_runs': incoming.pop(sid, {})}
    for e in events:
        if e['study'] != s['id']:
            continue
        kind = e['kind']
        if kind == 'new':
            start = e.get('step') if name(e.get('step')) != w['path'][0] else w.get('start') or e.get('step')
            for sid in targets(start):
                enter(sid)
        elif kind == 'task-bind':
            e = dict(e, node=name(e['node']))
            bindings[e['run_id']] = e
            if e['node'] in active and active[e['node']]['visit'] == e['visit']:
                active[e['node']]['run_id'] = e['run_id']
        elif kind in ('task-completed', 'task-routed', 'task-reused', 'task-omitted'):
            e = dict(e, node=name(e['node']))
            if e['node'] not in active or active[e['node']]['visit'] != e['visit']:
                continue
            active.pop(e['node'], None)
            resolved.append(e['node'])
            if kind == 'task-completed':
                completed.append(e['node'])
            for sid in targets(e.get('to')):
                enter(sid, e['node'], e.get('run_id'))
        elif kind == 'move':
            active.clear(); arrivals.clear(); incoming.clear()
            enter(e.get('to'))
        elif kind == 'finish':
            active.clear()
    runnable, waits = [], []
    from .entry import pending
    for token in active.values():
        for cp in w['checkpoints']:
            rec = s['approvals'].get(cp['id'], {})
            approved = (rec.get('decision') == 'approved' and model.may_approve(cp, str(rec.get('by') or 'pi'))
                        and (not rec.get('terms') or rec['terms'] == model.terms(cp)))
            if approved and rec.get('judge_scope'):
                from gate_reviews import valid_approval
                approved = valid_approval(hub, dict(s, active_steps=list(active.values())), cp, rec)
            if (cp.get('before') == token['id'] or pending(s, token) and cp.get('during') == token['id']) and not approved:
                waits.append({'at': token['id'], 'to': token['id'], 'checkpoint': cp['id'], 'title': cp['title']})
        limit = by_id[token['id']].get('max_visits')
        if not any(x['at'] == token['id'] for x in waits) and not (limit and token['visit'] > limit):
            runnable.append(token['id'])
    focus = runnable[0] if runnable else next(iter(active), resolved[-1] if resolved and s['step'] not in model.SHELF_LABEL else s['step'])
    if os.environ.get('NEWTS_RUN_SUBJECT') == s['id'] and os.environ.get('NEWTS_RUN_NODE') in active:
        focus = os.environ['NEWTS_RUN_NODE']
    return dict(s, step=focus, active_steps=list(active.values()), runnable=runnable, task_bindings=bindings,
                completed_steps=completed, joins={k: sorted(v) for k, v in arrivals.items()},
                waiting=next((x for x in waits if x['at'] == focus), None), task_waits=waits,
                finished=s['finished'] or not active and not arrivals and s['step'] not in model.SHELF_LABEL,
                blocked_reason='A task reached its repetition limit.' if any(by_id[t['id']].get('max_visits') and t['visit'] > by_id[t['id']]['max_visits'] for t in active.values()) else 'A join is waiting for a branch that did not arrive.' if arrivals and not active else '')


def selected(hub, s, node=None):
    from .studies import StudyError
    sid = node or (os.environ.get('NEWTS_RUN_NODE') if os.environ.get('NEWTS_RUN_SUBJECT') == s['id'] else None)
    if not sid:
        if len(s['active_steps']) != 1:
            raise StudyError('Several tasks are active. Select a task rather than completing the whole study.')
        sid = s['active_steps'][0]['id']
    token = next((t for t in s['active_steps'] if t['id'] == sid), None)
    if not token:
        raise StudyError('This task is no longer active.')
    return token


def bind(hub, slug, node, run_id):
    with locked(hub):
        return _bind(hub, slug, node, run_id)


def _bind(hub, slug, node, run_id):
    from . import studies
    s = studies.study(hub, slug)
    token = selected(hub, s, node)
    from .entry import pending
    if pending(s, token):
        raise studies.StudyError('Resolve the starting plan before assigning an agent to this task.')
    if node not in s['runnable']:
        raise studies.StudyError('The task waits at a checkpoint.')
    old = token.get('run_id')
    if old:
        from executor import Lab, find_run, ACTIVE, PAUSED
        try:
            m = find_run(Lab(hub), old)[3]
        except ValueError:
            m = {}
        if m.get('status') in ACTIVE | PAUSED | {'queued'}:
            raise studies.StudyError('An agent already owns this task.')
    journal.append(hub, slug, 'task-bind', 'kernel', node=node, visit=token['visit'], run_id=run_id)
    return {'node': node, 'visit': token['visit']}


def move(hub, s, outcome, note, by, node_id=None, run_id=None):
    with locked(hub):
        from . import studies
        return _move(hub, studies.study(hub, s['id']), outcome, note, by, node_id, run_id)


def _move(hub, s, outcome, note, by, node_id=None, run_id=None):
    from . import studies
    rid = run_id or os.environ.get('NEWTS_RUN_ID')
    if rid and any(e.get('run_id') == rid for e in journal.events(hub, s['id'], ('task-completed',))):
        return {'moved': False, 'step': s['step'], 'runnable': s['runnable'], 'finished': s['finished']}
    token = selected(hub, s, node_id)
    sid = token['id']
    if rid and token.get('run_id') != rid:
        raise studies.StudyError('Only the agent assigned to this task visit can report its result.')
    w = model.workflow(s['workflow'], hub)
    node = next(n for n in nodes(w, model.steps(hub)) if n['id'] == sid)
    if outcome in model.SHELVES:
        return studies._go(hub, s['id'], s, model.SHELVES[outcome], outcome, by, note)
    if sid not in s['runnable']:
        raise studies.StudyError('Resolve this task’s checkpoint before doing its work.')
    if outcome == model.DONE:
        for cp in w['checkpoints']:
            if cp.get('during') == sid:
                from gate_reviews import current_evidence
                if not studies.approved(hub, s['id'], cp['id']) or not current_evidence(hub, s, cp, s['approvals'].get(cp['id'], {})):
                    raise studies.StudyError('This task still needs checkpoint ' + cp['id'])
        if node.get('external'):
            import frameworks
            frameworks.check_task(hub, s, node['external'])
        missing = studies.missing_outputs(hub, dict(s, step=sid))
        project = s.get('project')
        root = Path(project) if project else Path(hub) / 'studies' / s['id']
        if not root.is_absolute():
            root = Path(hub) / root
        import remote_projects
        if remote_projects.location(project):
            missing += [f for f, stat in remote_projects.file_states(hub, s['id'], node.get('outputs', [])).items() if stat is None]
        else:
            missing += [f for f in node.get('outputs', []) if not (root / f).is_file()]
        if missing:
            raise studies.StudyError('Required outputs are missing: ' + ', '.join(missing))
        binding = s['task_bindings'].get(rid) if rid else None
        if binding and binding.get('started'):
            current = output_state(hub, s, node)
            if any(value is None or list(value) == binding.get('outputs', {}).get(path) for path, value in current.items()):
                raise studies.StudyError('Expected outputs are missing or unchanged from before this task run.')
        to = targets(node.get('next'))
    else:
        to = targets((node.get('outcomes') or {}).get(outcome, (w.get('routes', {}).get(sid) or {}).get(outcome, model.ASK)))
        if model.ASK in to:
            raise studies.StudyError('This outcome requires the researcher to choose the next task.')
        if any(t in model.SHELF_LABEL for t in to):
            if len(to) != 1:
                raise studies.StudyError('A shelf route must have one destination.')
            return studies._go(hub, s['id'], s, to[0], outcome, by, note)
    collision = set(to) & {t['id'] for t in s['active_steps'] if t['id'] != sid}
    if collision:
        raise studies.StudyError('This route re-enters an active task. Join the branches explicitly.')
    journal.append(hub, s['id'], 'task-completed', by, node=sid, visit=token['visit'], to=to,
                   outcome=outcome, run_id=rid or token.get('run_id'), note=note)
    studies.render_registry(hub)
    after = studies.study(hub, s['id'])
    studies._bus(hub, 'state_change', s['id'], f'{sid} completed; next: {", ".join(after["runnable"]) or "waiting/finished"}')
    return {'moved': bool(to), 'step': after['step'], 'runnable': after['runnable'],
            'finished': after['finished'], 'waiting': (after.get('waiting') or {}).get('checkpoint')}


def begin_run(hub, manifest):
    """Recheck live task admission; return True only for feedback on a completed task."""
    from . import studies
    with locked(hub):
        s = studies.study(hub, manifest['subject'])
        # An explicit follow-up may revise a completed task's output, without a new assignment.
        # Its original run binding remains: move() cannot advance another task from this session.
        if (s and s['step'] not in model.SHELF_LABEL and manifest.get('session_id')
                and (manifest.get('resume') or {}).get('mode') == 'reply'
                and any(e.get('run_id') == manifest['run_id'] and e.get('node') == manifest['workflow_node']
                        and e.get('visit') == manifest['workflow_visit']
                        for e in journal.events(hub, s['id'], ('task-completed',)))):
            return True
        if not s or s['finished'] or s['step'] in model.SHELF_LABEL:
            raise studies.StudyError('This study is finished or shelved.')
        token = selected(hub, s, manifest['workflow_node'])
        if (token.get('run_id') != manifest['run_id'] or token['visit'] != manifest['workflow_visit']):
            raise studies.StudyError('This run belongs to an old task visit.')
        if token['id'] not in s['runnable']:
            raise studies.StudyError('This task now waits at a checkpoint.')
        for cp in model.workflow(s['workflow'], hub)['checkpoints']:
            rec = s['approvals'].get(cp['id'], {})
            if cp.get('before') == token['id'] and rec.get('evidence_revision'):
                from gate_reviews import current_evidence
                if not current_evidence(hub, s, cp, rec):
                    raise studies.StudyError('The gate evidence changed. Request a new independent review.')
        binding = s['task_bindings'][manifest['run_id']]
        if not binding.get('started'):
            w = model.workflow(s['workflow'], hub)
            node = next(n for n in nodes(w, model.steps(hub)) if n['id'] == token['id'])
            if node.get('external'):
                import frameworks
                frameworks.check_launch(hub, s, node['external'])
            journal.append(hub, s['id'], 'task-bind', 'kernel', node=token['id'], visit=token['visit'],
                           run_id=manifest['run_id'], started=True, outputs=output_state(hub, s, node))
