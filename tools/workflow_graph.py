"""Small, product-neutral task graph helpers. Rooms and context never change dependencies."""
from __future__ import annotations

MODES = ('fresh', 'continue', 'native-fork')


def targets(value):
    if value is None or value == 'end':
        return []
    return list(value) if isinstance(value, list) else [value]


def edges(nodes):
    out = []
    for node in nodes:
        outcomes = node.get('outcomes') or {}
        routes = outcomes.values() if isinstance(outcomes, dict) else []
        out.extend((node['id'], target) for value in [node.get('next'), *routes]
                   for target in targets(value) if isinstance(target, str))
    return list(dict.fromkeys(out))


def predecessors(nodes, node):
    return {source for source, target in edges(nodes) if target == node}


def ancestors(nodes, task):
    found, pending = set(), list(predecessors(nodes, task))
    while pending:
        source = pending.pop()
        if source not in found:
            found.add(source)
            pending.extend(predecessors(nodes, source)-found)
    return found


def validate(nodes):
    if not isinstance(nodes, list) or not nodes:
        return ['Keep at least one task.']
    ids = [n.get('id') for n in nodes if isinstance(n, dict)]
    if len(ids) != len(nodes) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        return ['Tasks need unique text IDs.']
    problems, known = [], set(ids)
    contexts = {n['id']: n.get('context') if isinstance(n.get('context'), dict) else {} for n in nodes}
    for node in nodes:
        sid = node['id']
        if any(not isinstance(t, str) or t not in known for t in targets(node.get('next'))):
            problems.append(f'{sid}: choose existing destinations.')
        outcomes = node.get('outcomes') or {}
        if not isinstance(outcomes, dict):
            problems.append(f'{sid}: outcomes must map names to destinations.')
        else:
            import re
            for outcome, to in outcomes.items():
                if not isinstance(outcome, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', outcome) or outcome in ('done','park','kill'):
                    problems.append(f'{sid}: choose a distinct outcome name.')
                if any(not isinstance(t,str) or t not in known and t not in ('parked','killed','ask') for t in targets(to)):
                    problems.append(f'{sid}: outcome {outcome} needs existing destinations.')
        context = node.get('context') if node.get('context') is not None else {}
        if not isinstance(context, dict) or context.get('mode', 'fresh') not in MODES:
            problems.append(f'{sid}: context is fresh, continue or fork.')
            continue
        mode, source = context.get('mode', 'fresh'), context.get('from')
        if mode != 'fresh' or context.get('handoff'):
            sources = source if isinstance(source, list) else [source]
            allowed = ancestors(nodes, sid) | ({sid} if context.get('initial') == 'fresh' else set())
            if not sources or any(not isinstance(s, str) or s not in allowed for s in sources) or mode != 'fresh' and len(sources) != 1:
                problems.append(f'{sid}: choose an earlier task as the context source.')
            elif mode == 'continue':
                source = sources[0]
                siblings = [n['id'] for n in nodes if n['id'] != sid and
                            contexts[n['id']].get('mode') == 'continue' and
                            contexts[n['id']].get('from') == source]
                source_node = next(n for n in nodes if n['id'] == source)
                source_outcomes = source_node.get('outcomes') or {}
                routes = source_outcomes.values() if isinstance(source_outcomes, dict) else []
                concurrent = [targets(source_node.get('next')), *[targets(v) for v in routes]]
                if any(sid in group and any(other in group for other in siblings) for group in concurrent):
                    problems.append(f'{sid}: only one branch can continue {source}; fork the other branch.')
        if node.get('join'):
            incoming = predecessors(nodes, sid)
            for origin in nodes:
                groups = [targets(origin.get('next')), *[targets(v) for v in (origin.get('outcomes') or {}).values()]] if isinstance(origin.get('outcomes') or {}, dict) else []
                arms = [{p for p in incoming if any(p == t or t in ancestors(nodes, p) for t in g)} for g in groups]
                if any(a and b and a.isdisjoint(b) for i,a in enumerate(arms) for b in arms[i+1:]):
                    problems.append(f'{sid}: an all-input join cannot wait for mutually exclusive outcome branches; use a normal merge.')
                    break
        agent = node.get('agent') or {}
        if not isinstance(agent, dict) or any(k in agent and not isinstance(agent[k], str) and not (k in ('model','effort') and agent[k] is None)
                for k in ('role', 'preset', 'backend', 'model', 'effort', 'instructions')):
            problems.append(f'{sid}: agent settings must be text fields in a mapping.')
        outputs = node.get('outputs', [])
        if not isinstance(outputs, list) or any(not isinstance(p, str) or not p or p.startswith(('/', '\\')) or ':' in p or '..' in p.replace('\\','/').split('/') for p in outputs):
            problems.append(f'{sid}: outputs must be relative file paths.')
        if node.get('instructions') is not None and not isinstance(node['instructions'], str):
            problems.append(f'{sid}: task instructions must be text.')
        if node.get('external') is not None:
            from frameworks import validate as validate_external
            try:
                validate_external(node['external'])
            except ValueError as error:
                problems.append(f'{sid}: {error}')
        if not isinstance(node.get('skills', []), list) or any(not isinstance(p,str) for p in node.get('skills', [])):
            problems.append(f'{sid}: skills must be a list of procedure names.')
        if node.get('join') is not None and not isinstance(node['join'], bool):
            problems.append(f'{sid}: join must be true or false.')
        if node.get('max_visits') is not None and (not isinstance(node['max_visits'], int) or isinstance(node['max_visits'], bool) or node['max_visits'] < 1):
            problems.append(f'{sid}: repetition limit must be a positive integer.')
        if 'tags' in node:
            from tagging import normalize
            try:
                normalize(node['tags'])
            except ValueError as error:
                problems.append(f'{sid}: {error}')
        for field in ('room', 'procedure', 'label'):
            if node.get(field) is not None and not isinstance(node[field], str):
                problems.append(f'{sid}: {field} must be text.')
    return list(dict.fromkeys(problems))


def handoff(source, files=()):
    """Portable context inheritance. Never pretend this is a cloned native conversation."""
    return ('Context handoff (independent conversation; not an exact conversation clone).\n'
            f"Source task/run: {source.get('label') or source.get('skill') or 'task'} / {source['run_id']}\n"
            f"Latest result:\n{source.get('last_message') or source.get('last_text') or 'Read the source artifacts.'}\n"
            + ('Evidence and outputs:\n' + '\n'.join('- ' + str(f) for f in files) if files else ''))
