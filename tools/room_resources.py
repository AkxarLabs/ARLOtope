"""Lean room resources: existing builder data plus an optional room-local component module."""
import hashlib
import json
import math
import re
from pathlib import Path

ID = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('A room definition is an object.')
    size = data.get('size', [10, 7])
    if not isinstance(size, list) or len(size) != 2 or any(isinstance(n, bool) or not isinstance(n, (int,float)) or not math.isfinite(n) or n <= 0 for n in size):
        raise ValueError('Room size is two finite positive dimensions.')
    props = data.get('props', [])
    if not isinstance(props, list):
        raise ValueError('Props must be a list of furniture instances.')
    for p in props:
        if (not isinstance(p, dict) or not isinstance(p.get('c'), str) or not p['c']
                or not isinstance(p.get('at'), list) or len(p['at']) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in p['at'])):
            raise ValueError('Each prop needs a component name c and position at: [x,z].')
        if 'rot' in p and (isinstance(p['rot'], bool) or not isinstance(p['rot'], (int, float))):
            raise ValueError('Prop rotation is a number in radians.')
        if 'props' in p and not isinstance(p['props'], dict):
            raise ValueError('Component props are an object.')
    for field in ('stations', 'roleStation'):
        if field not in data:
            continue
        values = data[field]
        if (not isinstance(values, dict) or any(not isinstance(a, list) or len(a) not in (2, 3)
                or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in a) for a in values.values())):
            raise ValueError(f'{field} maps names to [x,z] or [x,z,facing].')
    def finite(v):
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError('Room values must be finite.')
        if isinstance(v, dict):
            for x in v.values(): finite(x)
        elif isinstance(v, list):
            for x in v: finite(x)
    finite(data)
    return data


def read_one(folder):
    folder = Path(folder)
    raw = (folder / 'room.json').read_bytes()
    module = folder / 'extra.js'
    has_module = module.is_file()
    source = module.read_bytes() if has_module else b''
    return {'definition': validate(json.loads(raw)),
            'revision': hashlib.sha256(raw + source).hexdigest()[:16],
            'module': has_module, 'module_src': source.decode('utf-8')}


def read(hub):
    result = {}
    for file in sorted((Path(hub) / 'lab/rooms').glob('*/room.json')):
        if not ID.fullmatch(file.parent.name): continue
        try:
            result[file.parent.name] = read_one(file.parent)
        except (ValueError, OSError):
            continue
    return result
