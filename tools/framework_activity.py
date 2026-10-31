"""Read-only, declarative JSONL activity for external tools. Never executes commands.

A project on another machine reads its own activity there (`read`); what comes back is data (`remote`)."""
from __future__ import annotations

import json
from pathlib import Path

from labfiles import inside, pos_int

RUNS = '.arlotope/framework-runs'


def field(record, path):
    if not isinstance(path, str) or not path:
        raise ValueError('Activity fields must be dotted field names.')
    for key in path.split('.'):
        record = record.get(key) if isinstance(record, dict) else None
    return record


def read(definition, project, study, phase):
    from frameworks import ID
    if not all(isinstance(v, str) and ID.fullmatch(v) for v in (definition['id'], study, phase)):
        raise ValueError('Invalid framework activity scope.')
    project = Path(project).resolve()
    root = project / RUNS / study / definition['id'] / 'run'
    if not root.resolve().is_relative_to(project):
        raise ValueError('Activity must remain inside its project.')
    recipe = definition.get('activity') or {}
    if (not isinstance(recipe, dict) or not isinstance(recipe.get('files', []), list)
            or not all(isinstance(p,str) and p for p in recipe.get('files', []))
            or not all(isinstance(recipe.get(key, {}), dict) for key in ('events','fields','kinds'))):
        raise ValueError('Activity needs file paths and an event mapping.')
    fields = {'time':'timestamp', 'event':'event', 'label':'fields.label', 'state':'fields.status',
              'worker':'worker_index', 'cycle':'fields.cycle', **recipe.get('fields', {})}
    events, clipped, malformed = [], False, 0
    for pattern in recipe.get('files', []):
        relative = pattern.replace('{phase}', phase)
        path = root / relative
        if not inside(root, path):
            raise ValueError('Activity file escapes its run directory.')
        try:
            with path.open('rb') as stream:
                offset = max(0, stream.seek(0, 2) - 256 * 1024)
                stream.seek(offset)
                if offset:
                    stream.readline(); clipped = True
                lines = stream.read(256 * 1024).splitlines()
        except FileNotFoundError:
            continue
        for line in lines:
            try:
                raw = json.loads(line)
            except (ValueError, UnicodeError):
                malformed += 1; continue
            name = field(raw, fields['event'])
            if not isinstance(name, str) or (recipe.get('phase_field') and field(raw, recipe['phase_field']) not in (None, phase)):
                continue
            mapping = recipe.get('events', {}).get(name)
            if not isinstance(mapping, dict):
                continue  # Configuration/authentication records are not activity rows.
            label = mapping.get('label') or field(raw, mapping.get('label_from', fields['label'])) or name
            state = mapping.get('state') or field(raw, mapping.get('state_from', fields['state'])) or 'recorded'
            state = {'started':'running','complete':'completed','fail':'failed','pass':'completed'}.get(str(state), str(state))
            events.append({'time':str(field(raw, fields['time']) or '')[:64], 'event':name,
                'label':str(label).replace('_',' ')[:200], 'state':str(state)[:40],
                'kind':mapping.get('kind') or recipe.get('kinds',{}).get(str(field(raw,fields.get('phase','phase'))),'run'), 'worker':field(raw, fields['worker']),
                'cycle':field(raw, fields['cycle']), 'source':relative})
    events.sort(key=lambda row:row['time'])
    clipped |= len(events)>160
    return _activity(definition, phase, root, events[-160:], clipped, malformed)


def _activity(definition, phase, root, events, clipped, malformed):
    return {'framework':definition['id'], 'phase':phase, 'title':definition.get('title',definition['id']),
            'root':str(root), 'events':events, 'current':events[-1] if events else None,
            'clipped':clipped, 'malformed':malformed, 'supported':bool(definition.get('activity'))}


def remote(result, query):
    """What a machine reported for `query` (request's), as data: read's shape rebuilt from it — text and numbers,
    each event's source one of the definition's own files — with the root and the machine this Lab decides, so a
    link built from them opens that machine's run folder, never a place the machine named (a local file, a share)."""
    definition, phase, machine = query['definition'], query['phase'], query['machine']
    if not isinstance(result, dict) or result.get('error'):
        error = result.get('error') if isinstance(result, dict) else 'The machine reported unreadable activity.'
        return {'error': str(error)[:300], 'machine': machine}
    sources = {p.replace('{phase}', phase) for p in (definition.get('activity') or {}).get('files', []) if isinstance(p, str)}
    rows = result.get('events') if isinstance(result.get('events'), list) else []
    events = [_event(e, sources) for e in rows[-160:] if isinstance(e, dict)]
    root = f"{query['project']}/{RUNS}/{query['study']}/{definition['id']}/run"
    return {**_activity(definition, phase, root, events, bool(result.get('clipped')),
                        pos_int(result.get('malformed'), 0, 0)), 'machine': machine}


def _event(e, sources):
    def scalar(v):
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)[:40] if isinstance(v, str) else None
    return {**{k: str(e.get(k) or '')[:n] for k, n in (('time', 64), ('event', 100), ('label', 200), ('state', 40), ('kind', 40))},
            'worker': scalar(e.get('worker')), 'cycle': scalar(e.get('cycle')),
            'source': e['source'] if e.get('source') in sources else ''}


def request(hub, run):
    from kernel import studies, model, checkpoints
    import frameworks
    import remote_projects
    if not run.get('subject') or not run.get('workflow_node'):
        return None
    study = studies.study(hub, run['subject'])
    if not study:
        return None
    external = model.workflow(study['workflow'], hub).get('nodes', {}).get(run['workflow_node'], {}).get('external')
    if not external:
        return None
    remote = remote_projects.location(study.get('project'))
    return {'definition':frameworks.definitions(hub)[external['framework']], 'study':study['id'],
            'project':remote['path'] if remote else str(checkpoints.project_dir(hub,study['id'])),
            'phase':external['phase'], 'machine':remote['machine'] if remote else ''}


def view(hub, run, *, refresh=False):
    try:
        query = request(hub, run)
        if not query:
            return None
        ask = {k: v for k, v in query.items() if k != 'machine'}
        if not query['machine']:
            return {**read(**ask), 'machine': ''}
        if not refresh:
            return run.get('external_activity')   # remote_projects.sync keeps it, already taken as data
        import remote_projects
        return remote(remote_projects.rpc(query['machine'], 'framework-activity', ask), query)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {'error':str(error)}
