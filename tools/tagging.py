"""Flat labels stored with studies and workflow definitions; no separate taxonomy database."""
from pathlib import Path
import re
import yaml

from labfiles import write_atomic

FRONT = re.compile(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', re.S)


def normalize(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = value.split(',')
    if not isinstance(value, list) or any(not isinstance(tag, str) for tag in value):
        raise ValueError('Tags must be text labels.')
    result = []
    for tag in value:
        tag = '-'.join(tag.strip().casefold().split())
        if not tag:
            continue
        if len(tag) > 64 or ',' in tag or any(ord(c) < 32 for c in tag):
            raise ValueError('Use tags of up to 64 characters, separated by commas.')
        if tag not in result:
            result.append(tag)
    return result


def study_tags(hub, slug):
    try:
        text = (Path(hub) / 'studies' / slug / 'IDEA.md').read_text(encoding='utf-8-sig')
        match = FRONT.match(text)
        return normalize((yaml.safe_load(match[1]) or {}).get('tags')) if match else []
    except (OSError, ValueError, yaml.YAMLError, AttributeError):
        return []


def set_study_tags(hub, slug, value):
    from kernel import studies
    if not studies.study(hub, slug):
        raise ValueError('Choose an existing study.')
    tags = normalize(value)
    path = Path(hub) / 'studies' / slug / 'IDEA.md'
    text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    match = FRONT.match(text)
    try:
        metadata = (yaml.safe_load(match[1]) or {}) if match else {}
    except yaml.YAMLError as exc:
        raise ValueError('Fix the study frontmatter before changing its tags.') from exc
    if not isinstance(metadata, dict):
        raise ValueError('The study frontmatter must be a mapping.')
    metadata['tags'] = tags
    body = text[match.end():] if match else text
    updated = '---\n' + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + '---\n' + body
    write_atomic(path, updated)
    return tags


def catalog(hub, definition=None):
    from kernel import model
    data = definition or model.load(hub)
    steps = data.get('steps') or {}
    values = list(steps.values()) if isinstance(steps, dict) else list(steps)
    values += list((data.get('procedures') or {}).values())
    for workflow in data.get('workflows') or []:
        values += [workflow, *(workflow.get('nodes') or {}).values()]
    found = {tag for item in values for tag in normalize(item.get('tags'))}
    for path in (Path(hub) / 'studies').glob('*/IDEA.md'):
        found.update(study_tags(hub, path.parent.name))
    return sorted(found)
