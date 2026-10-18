"""Stable local Lab/project identities and a small discovery index. No account service."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import uuid


def home():
    return Path(os.environ.get('NEWTS_HOME') or Path.home()/'.newts')


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.'+secrets.token_hex(4)+'.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8'); os.replace(temp, path)


def lab_identity(hub):
    hub = Path(hub).resolve()
    path = hub / 'lab/identity.json'
    from executor.procs import excl_lock
    with excl_lock(hub / 'lab/.bus/.identity.lock'):
        value = read(path)
        if value is None and not path.exists():
            value = {'schema':1,'lab_id':uuid.uuid4().hex,
                     'execution_owner':hashlib.sha256(str(hub).encode()).hexdigest()[:24]}
            atomic(path,value)
        if not isinstance(value,dict) or not value.get('lab_id') or not value.get('execution_owner'):
            raise ValueError('The Lab identity is invalid. Restore lab/identity.json before reconnecting projects.')
        return value


def register(root, owner, study, lab_id=None, title=None):
    root = Path(root).resolve()
    if (root/'.newts').is_symlink() or (root/'.newts/project.json').is_symlink():
        raise ValueError('The project configuration must live inside the project.')
    marker = root / '.bus/newts-owner.json'
    index = home() / 'projects.json'
    from executor.procs import excl_lock
    with excl_lock(index.with_suffix('.lock')):
        old = read(marker, {})
        durable = read(root/'.newts/project.json', {})
        if not isinstance(durable,dict) or (root/'.newts/project.json').exists() and not durable.get('project_id'):
            raise ValueError('The durable project identity is invalid.')
        if not isinstance(old, dict) or marker.exists() and not old:
            raise ValueError('The project identity is invalid. Restore .bus/newts-owner.json before attaching it.')
        if durable and (lab_id is not None and durable.get('lab_id') not in (None,lab_id) or old.get('project_id') and old['project_id'] != durable['project_id']):
            raise ValueError('The project identities disagree or belong to another Lab.')
        if old and (old.get('owner') != owner or old.get('study') != study):
            raise ValueError('This project is attached to another Lab or study. Open its owning Lab.')
        value = {**old,'schema':2,'owner':owner,'study':study,'project_id':old.get('project_id') or durable.get('project_id') or uuid.uuid4().hex,
                 'lab_id':lab_id or old.get('lab_id') or durable.get('lab_id'), 'title':title or old.get('title') or durable.get('name') or study}
        rows = read(index, [])
        if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('path'), str) for r in rows):
            raise ValueError('The project discovery index is invalid. Restore projects.json in NEWTS_HOME.')
        atomic(marker,value)
        atomic(root/'.newts/project.json', {**durable,'schema':1,'project_id':value['project_id'],
               'lab_id':value['lab_id'],'name':value['title'],'knowledge_dir':durable.get('knowledge_dir','.newts/knowledge')})
        rows = [r for r in rows if r.get('path') != str(root)]
        rows.append({**value,'path':str(root)})
        atomic(index,rows)
        return value


def discover(root=None, depth=2, limit=100):
    rows = read(home()/'projects.json', [])
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not isinstance(r.get('path'), str) for r in rows):
        raise ValueError('The project discovery index is invalid. Restore projects.json in NEWTS_HOME.')
    out = []
    for row in rows:
        marker = read(Path(row['path'])/'.newts/project.json') or read(Path(row['path'])/'.bus/newts-owner.json', {})
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
            marker=read(p/'.newts/project.json') or read(p/'.bus/newts-owner.json', {})
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
