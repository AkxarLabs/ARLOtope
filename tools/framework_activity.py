"""Read-only, declarative JSONL activity for external tools. Never executes commands."""
from __future__ import annotations

import json
from pathlib import Path

from labfiles import inside


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
    root = project / '.arlotope/framework-runs' / study / definition['id'] / 'run'
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
    events = events[-160:]
    return {'framework':definition['id'], 'phase':phase, 'title':definition.get('title',definition['id']),
            'root':str(root), 'events':events, 'current':events[-1] if events else None,
            'clipped':clipped, 'malformed':malformed, 'supported':bool(recipe)}


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
        machine = query.pop('machine')
        if machine:
            if not refresh:
                return run.get('external_activity')
            import remote_projects
            result = remote_projects.rpc(machine, 'framework-activity', query)
        else:
            result = read(**query)
        return {**result, 'machine':machine}
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {'error':str(error)}
