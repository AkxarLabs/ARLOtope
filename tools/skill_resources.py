"""Ordinary skill folders: resolve, import, and retain the methods a project actually uses."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

SKILLS = Path('.agents/skills')
IGNORE = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache'}


def folders(hub, project=None):
    from kernel import model
    hub = Path(hub)
    roots = [model.CODE, hub]
    out = {}
    for root in dict.fromkeys(roots):
        for folder in sorted((root / model.SKILLS).glob('*/SKILL.md')):
            out[folder.parent.name] = folder.parent
        excluded = root / model.SKILLS / '.excluded.json'
        for name in json.loads(excluded.read_text(encoding='utf-8')) if excluded.is_file() else []:
            out.pop(name, None)
    if project:
        for directory in ('.opencode/skills', '.claude/skills', '.agents/skills'):
            for file in sorted((Path(project) / directory).glob('*/SKILL.md')):
                out[file.parent.name] = file.parent
    return out


def exclude(hub, name, hidden=True):
    path = Path(hub) / '.claude/skills/.excluded.json'
    names = set(json.loads(path.read_text(encoding='utf-8'))) if path.is_file() else set()
    names.add(name) if hidden else names.discard(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if names:
        path.write_text(json.dumps(sorted(names)) + '\n', encoding='utf-8')
    else:
        path.unlink(missing_ok=True)


def files(folder):
    """Keep resources byte-for-byte; do not follow a link outside the selected skill."""
    folder = Path(folder).resolve()
    result = {}
    for directory, dirs, names in os.walk(folder, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE)
        for name in sorted(names + [d for d in dirs if (Path(directory) / d).is_symlink()]):
            path = Path(directory) / name
            rel = path.relative_to(folder)
            if not path.resolve().is_relative_to(folder):
                raise ValueError(f'Skill resource points outside its folder: {rel}')
            if path.is_symlink() and path.is_dir():
                raise ValueError(f'Use ordinary folders for skill resources: {rel}')
            if path.is_file() and path.suffix != '.pyc':
                result[rel.as_posix()] = path.read_bytes()
    return result


def digest(content):
    value = hashlib.sha256()
    for name, data in sorted(content.items()):
        value.update(name.encode() + b'\0' + data + b'\0')
    return value.hexdigest()


def inspect(folder):
    from kernel import model
    if not folder or not (Path(folder).expanduser() / 'SKILL.md').is_file():
        raise ValueError('Choose a skill folder containing SKILL.md.')
    folder = Path(folder).expanduser().resolve()
    content = files(folder)
    if 'SKILL.md' not in content:
        raise ValueError('Choose a skill folder containing SKILL.md.')
    meta = model.skill_meta(content['SKILL.md'].decode('utf-8-sig'))
    name = meta.get('name') or folder.name
    if not model.SLUG.fullmatch(name) or not meta.get('description'):
        raise ValueError('SKILL.md needs a valid name and a description.')
    if name != folder.name:
        raise ValueError('The skill name must match its folder name.')
    return {'name': name, 'description': meta['description'], 'files': list(content),
            'sha256': digest(content), 'bytes': sum(map(len, content.values()))}


def copy(folder, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('A skill with this name already exists. Import a separately named variant or use the existing skill.')
    content = files(folder)
    try:
        for relative, data in content.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    except Exception:
        if destination.is_dir():
            shutil.rmtree(destination)
        raise
    return content


def install(project, sources):
    """One collection per project. Native project skills win over reusable Lab originals."""
    project = Path(project)
    records = {}
    for name, content in sources.items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,79}', name) or 'SKILL.md' not in content:
            raise ValueError('A skill needs a valid folder name and SKILL.md.')
        base = (project / SKILLS / name).resolve()
        if not base.is_relative_to(project.resolve()) or any(not (base / relative).resolve().is_relative_to(base) for relative in content):
            raise ValueError('Invalid skill resource path.')
    for name, content in sources.items():
        folder = next((project / root / name for root in ('.agents/skills', '.claude/skills', '.opencode/skills')
                       if (project / root / name / 'SKILL.md').is_file()), None)
        source = 'project' if folder else 'lab'
        folder = folder or project / SKILLS / name
        if not (folder / 'SKILL.md').exists():
            if folder.exists():
                raise ValueError(f'The skill folder {name} already exists without SKILL.md. Choose another skill name.')
            for relative, data in content.items():
                target = folder / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        actual = files(folder)
        records[name] = {'path': folder.relative_to(project).as_posix(), 'sha256': digest(actual), 'source': source}
    return records


def selected(hub, workflow, use=None):
    from kernel import model
    from kernel.branches import nodes
    pending = []
    for node in nodes(workflow, model.steps(hub)):
        name = node.get('procedure')
        name = (use or {}).get(name, name)
        pending += ([name] if name else []) + node.get('skills', [])
    pending += [c.get('judge', {}).get('skill', 'gate-review') for c in workflow['checkpoints'] if c.get('approver') == 'agent']
    found = []
    while pending:
        name = pending.pop(0)
        if name in found:
            continue
        found.append(name)
        definition = model.procedure(name, hub) or {}
        pending += definition.get('uses', [])
        if definition.get('like'):
            pending.append(definition['like'])
    return found


def package(hub, project, workflow, study, *, extra=()):
    """Materialize selected methods once; existing project methods remain the user's own."""
    project = Path(project)
    inventory = folders(hub, project)
    from kernel import studies
    use = (studies.study(hub, study) or {}).get('use')
    workflow = {**workflow, 'use': {**workflow.get('use', {}), **(use or {})}}
    names = list(dict.fromkeys(selected(hub, workflow, use) + list(extra)))
    sources = {}
    for name in names:
        folder = inventory.get(name)
        if folder is None:
            raise ValueError(f'Missing skill /{name}. Import it before running this workflow.')
        sources[name] = files(folder)
    chosen = install(project, sources)
    record_project(project, workflow, study, chosen)
    return chosen


def record_project(project, workflow, study, chosen):
    if not study or '/' in study or '\\' in study or study in ('.', '..'):
        raise ValueError('Invalid study name.')
    project = Path(project)
    record = project / '.newts'
    record.mkdir(parents=True, exist_ok=True)
    manifest = record / 'skills.json'
    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {}
    manifest.write_text(json.dumps({**previous, **chosen}, indent=2) + '\n', encoding='utf-8')
    workflows = record / 'workflows'
    workflows.mkdir(exist_ok=True)
    (workflows / f'{study}.json').write_text(json.dumps(workflow, indent=2) + '\n', encoding='utf-8')


def snapshot(hub, project, workflow, study, destination, *, extra=()):
    """An immutable run copy, including binary assets and supporting files."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    from kernel import studies
    workflow = {**workflow, 'use': {**workflow.get('use', {}), **(studies.study(hub, study) or {}).get('use', {})}}
    chosen = package(hub, project, workflow, study, extra=extra)
    for name, record in chosen.items():
        copy(Path(project) / record['path'], destination / name)
    (destination / '_workflow.json').write_text(json.dumps(workflow, indent=2) + '\n', encoding='utf-8')
    (destination / '_manifest.json').write_text(json.dumps(chosen, indent=2) + '\n', encoding='utf-8')
    return chosen


def prepare(lab, validated, spec, directory, remote=None):
    """Package on first use and pin the exact method bytes to this run, on either machine."""
    from kernel import checkpoints, model, studies
    state = studies.study(lab.hub, validated['subject']) if validated.get('subject') else None
    if not state or spec.extra.get('explains') or validated['skill'] == 'ask' and not spec.extra.get('workflow_node'):
        return {}
    project = checkpoints.project_dir(lab.hub, state['id'])
    if not remote and (not project or not project.is_dir()):
        return {}
    workflow = model.workflow(state['workflow'], lab.hub)
    workflow = {**workflow, 'use': {**workflow.get('use', {}), **state.get('use', {})}}
    extra = [validated['skill']] if model.procedure(validated['skill'], lab.hub) else []
    destination = Path(directory) / 'skills'
    if not remote:
        return snapshot(lab.hub, project, workflow, state['id'], destination, extra=extra)
    import base64
    import remote_projects
    inventory = folders(lab.hub)
    names = list(dict.fromkeys(selected(lab.hub, workflow, state.get('use')) + extra))
    sources = {name: {rel: base64.b64encode(data).decode() for rel, data in files(inventory[name]).items()}
               for name in names if name in inventory}
    if len(sources) != len(names):
        raise ValueError('A selected skill is missing. Import it before running the workflow.')
    receipt = remote_projects.call(lab.hub, state['id'], 'skills', sources=sources, workflow=workflow)
    if not receipt.get('records') and names:
        raise ValueError('Reconnect this machine to update its runner before using project skills.')
    chosen = receipt['records']
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in receipt['files'].items():
        for rel, encoded in content.items():
            target = destination / name / rel
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError('Invalid skill resource path from worker.')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(encoded, validate=True))
    (destination / '_workflow.json').write_text(json.dumps(workflow, indent=2), encoding='utf-8')
    (destination / '_manifest.json').write_text(json.dumps(chosen, indent=2), encoding='utf-8')
    return chosen


def rewrite(text, hub, project, snapshot_dir, names):
    """Managed runs select exact files instead of harness-specific same-name precedence."""
    sources = folders(hub, project)
    from kernel import model
    for name in names:
        source = sources.get(name)
        if source:
            target = (Path(snapshot_dir) / name).as_posix()
            for path in {source, Path(hub) / '.claude/skills' / name, model.CODE / '.claude/skills' / name}:
                for spelling in {str(path), path.as_posix()}:
                    text = text.replace(spelling + '/', target + '/').replace(spelling + '\\', target + '/')
    return text
