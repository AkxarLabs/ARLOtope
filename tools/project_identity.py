"""Stable local Lab/project identities and a small discovery index. No account service."""
import hashlib
import os
from pathlib import Path
import uuid

from labfiles import home_path, read_json, write_json


def lab_identity(hub):
    hub = Path(hub).resolve()
    path = hub / 'lab/identity.json'
    from executor.procs import excl_lock
    with excl_lock(hub / 'lab/.bus/.identity.lock'):
        value = read_json(path)
        if value is None and not path.exists():
            value = {'schema':1,'lab_id':uuid.uuid4().hex,
                     'execution_owner':hashlib.sha256(str(hub).encode()).hexdigest()[:24]}
            write_json(path,value)
        if not isinstance(value,dict) or not value.get('lab_id') or not value.get('execution_owner'):
            raise ValueError('The Lab identity is invalid. Restore lab/identity.json before reconnecting projects.')
        return value


def register(root, owner, study, lab_id=None, title=None):
    root = Path(root).resolve()
    if (root/'.arlotope').is_symlink() or (root/'.arlotope/project.json').is_symlink():
        raise ValueError('The project configuration must live inside the project.')
    marker = root / '.arlotope/project.json'
    index = home_path('projects.json')
    from executor.procs import excl_lock
    with excl_lock(index.with_suffix('.lock')):
        old = read_json(marker, {})
        if not isinstance(old, dict) or marker.exists() and not old.get('project_id'):
            raise ValueError(f'The project identity is invalid. Restore {marker} before attaching it.')
        if old and lab_id is not None and old.get('lab_id') not in (None,lab_id):
            raise ValueError(f'Project "{root}" belongs to another Lab (Lab ID: {old["lab_id"]}). Open its owning Lab.')
        if old.get('owner') and (old['owner'] != owner or old.get('study') != study):
            raise ValueError(f'Project "{root}" is attached to another Lab or study (study: {old.get("study")}, '
                             f'execution owner: {old.get("owner")}). Open its owning Lab.')
        rows = read_json(index, [])
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('path'), str) for r in rows):
            raise ValueError('The project discovery index is invalid. Restore projects.json in ARLOTOPE_HOME.')
        previous = next((row for row in rows if row['path'] == str(root)), {})
        if old and previous.get('project_id') and previous['project_id'] != old['project_id']:
            raise ValueError(f'Project identity mismatch in "{root}": projects.json has ID "{previous["project_id"]}", '
                             f'but .arlotope/project.json has ID "{old["project_id"]}". Restore the correct identity before attaching.')
        value = {**old,'schema':1,'owner':owner,'study':study,'project_id':old.get('project_id') or uuid.uuid4().hex,
                 'lab_id':lab_id or old.get('lab_id'), 'name':title or old.get('name') or study,
                 'knowledge_dir':old.get('knowledge_dir','.arlotope/knowledge')}
        write_json(marker,value)
        rows = [r for r in rows if r.get('path') != str(root)]
        rows.append({**value,'title':value['name'],'path':str(root)})
        write_json(index,rows)
        return {**value, 'title':value['name']}


def discover(root=None, depth=2, limit=100):
    rows = read_json(home_path('projects.json'), [])
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('path'), str) for r in rows):
        raise ValueError('The project discovery index is invalid. Restore projects.json in ARLOTOPE_HOME.')
    out = []
    for row in rows:
        marker = read_json(Path(row['path'])/'.arlotope/project.json', {})
        marker = marker if isinstance(marker, dict) else {}
        out.append({**row,'exists':Path(row['path']).is_dir(), 'registered':True,
                    'identity_matches':marker.get('project_id')==row.get('project_id')})
    if root:
        base = Path(root).expanduser()
        if not base.is_absolute() or not base.is_dir():
            raise ValueError('Choose an existing absolute folder to browse.')
        seen = {r['path'] for r in out}
        for folder, dirs, _files in os.walk(base):
            p=Path(folder)
            dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d not in ('node_modules','__pycache__'))
            if len(p.relative_to(base).parts)>=depth:
                dirs[:]=[]
            marker=read_json(p/'.arlotope/project.json', {})
            marker = marker if isinstance(marker, dict) else {}
            if str(p) not in seen and (marker or (p/'.git').exists()):
                out.append({**marker,'path':str(p),'title':marker.get('title') or marker.get('name') or p.name,'exists':True,
                            'registered':bool(marker),'identity_matches':True})
                seen.add(str(p))
            if len(out)>=limit:
                break
    by_id={}
    for row in out:
        if row.get('project_id') and row['exists']:
            by_id.setdefault(row['project_id'],[]).append(row['path'])
    return [{**r,'duplicate':len(by_id.get(r.get('project_id'),[]))>1} for r in out]
