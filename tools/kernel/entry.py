"""Researcher-selected reuse/omission for a task's first visit, through the ordinary journal."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import journal, model


def revision(hub, workflow):
    from .branches import nodes
    tasks = [{k: v for k, v in n.items() if k not in ('label', 'room', 'tags')} for n in nodes(workflow, model.steps(hub))]
    skills = {}
    for name in {p for n in tasks for p in [n.get('procedure'), *n.get('skills', [])] if p}:
        path = Path(hub) / model.SKILLS / name / 'SKILL.md'
        if not path.is_file():
            path = model.CODE / model.SKILLS / name / 'SKILL.md'
        skills[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    value = [tasks, workflow.get('routes'), workflow['checkpoints'], workflow.get('start'), skills]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:20]


def prepare(hub, workflow, value):
    if not value:
        return None
    from .branches import nodes
    if not isinstance(value, dict) or value.get('revision') != revision(hub, workflow):
        raise ValueError('The workflow changed. Review the starting plan again.')
    choices = value.get('tasks')
    known = {n['id']: n for n in nodes(workflow, model.steps(hub))}
    if not isinstance(choices, dict) or not choices or len(choices) > len(known):
        raise ValueError('Choose tasks from this workflow.')
    clean = {}
    for sid, item in choices.items():
        if sid not in known or not isinstance(item, dict) or item.get('action') not in ('reuse', 'omit'):
            raise ValueError('Choose Run task, Use existing work, or Skip at start.')
        note, refs, outcome = item.get('note', ''), item.get('refs', []), item.get('outcome', 'done')
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError('Keep the optional task note under 2000 characters.')
        if not isinstance(refs, list) or len(refs) > 20 or any(not isinstance(r, str) or not r.strip() or len(r) > 2000 for r in refs):
            raise ValueError('Use a short list of file paths, record IDs or source URLs.')
        if item['action'] == 'reuse' and not refs:
            raise ValueError('Reference the existing work you want to use.')
        routes = {**workflow.get('routes', {}).get(sid, {}), **known[sid].get('outcomes', {})}
        if outcome != 'done' and outcome not in routes:
            raise ValueError('Choose an outcome defined by this task.')
        from workflow_graph import targets
        dest = known[sid].get('next') if outcome == 'done' else routes[outcome]
        if any(t not in known for t in targets(dest)):
            raise ValueError('Run decision tasks normally when their outcome needs the researcher or shelves the study.')
        clean[sid] = {'action': item['action'], 'note': note.strip(), 'refs': [r.strip() for r in refs], 'outcome': outcome}
    return {'revision': value['revision'], 'tasks': clean}


def pending(s, token):
    return (s.get('entry') or {}).get('tasks', {}).get(token['id']) if token['visit'] == 1 and not s.get('entry_cancelled') else None


def _next(hub, s):
    from . import branches, studies
    from workflow_graph import targets
    if not s:
        return None
    token = next((t for t in s.get('active_steps', []) if t['id'] in s['runnable'] and pending(s, t)), None)
    if token is None:
        return None
    w = model.workflow(s['workflow'], hub)
    if (s.get('entry') or {}).get('revision') != revision(hub, w):
        raise ValueError('The workflow changed. Review the starting plan, or run its remaining tasks normally.')
    for cp in w['checkpoints']:
        if (cp.get('before') == token['id'] or cp.get('during') == token['id']) and not studies.approved(hub, s['id'], cp['id']):
            raise ValueError('Review checkpoint ' + cp['title'] + ' before reusing or omitting this task.')
    choice = pending(s, token)
    node = next(n for n in branches.nodes(w, model.steps(hub)) if n['id'] == token['id'])
    outcome = choice['outcome']
    dest = node.get('next') if outcome == 'done' else {**w.get('routes', {}).get(node['id'], {}), **node.get('outcomes', {})}[outcome]
    to = targets(dest)
    if set(to) & {t['id'] for t in s['active_steps'] if t['id'] != token['id']}:
        raise ValueError('This starting plan re-enters an active task. Join its branches explicitly.')
    return {'kind': 'task-reused' if choice['action'] == 'reuse' else 'task-omitted', 'node': token['id'],
            'visit': token['visit'], 'to': to, 'outcome': outcome, 'refs': choice['refs'],
            'note': choice['note'], 'workflow_revision': s['entry']['revision'], 'selected_by': 'pi'}


def preview(hub, workflow, value):
    """Fold hypothetical entry decisions with the same graph engine, without writing or launching."""
    from . import branches
    value = prepare(hub, workflow, value)
    events = [{'kind': 'new', 'study': 'entry-preview', 'by': 'pi', 'workflow': workflow['id'],
               'step': workflow['path'][0], 'entry': value}]
    while True:
        s = branches.fold(hub, journal.fold(events)['entry-preview'], events)
        event = _next(hub, s)
        if event is None:
            return {'ok': True, 'ready': s['runnable'], 'waiting': s['task_waits'], 'joins': s['joins'],
                    'resolved': events[1:], 'finished': s['finished']}
        events.append(dict(event, study='entry-preview', by='kernel'))


def apply(hub, slug):
    """Resolve only researcher-selected, ungated first visits. Never approve or launch anything."""
    from . import branches, studies
    with branches.locked(hub):
        while True:
            event = _next(hub, studies.study(hub, slug))
            if event is None:
                return
            journal.append(hub, slug, event.pop('kind'), 'kernel', **event)
            studies.render_registry(hub)


def cancel(hub, slug):
    from . import studies, branches
    studies._pi('pi')
    with branches.locked(hub):
        if not studies.study(hub, slug):
            raise ValueError('Choose an existing study.')
        journal.append(hub, slug, 'entry-cancelled', 'pi', note='Run remaining tasks normally. Previous reuse decisions remain recorded.')
        studies.render_registry(hub)
    return {'ok': True}
