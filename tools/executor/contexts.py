"""Context lineage for ordinary executor runs; no second agent loop or transcript database."""
from pathlib import Path
from contextlib import contextmanager

from .manifest import ACTIVE, PAUSED, TERMINAL, all_runs, find_run, run_dir
from .spec import SpecError
from workflow_graph import handoff


@contextmanager
def reservation(lab):
    from .procs import excl_lock
    with excl_lock(lab.bus / '.context-queue.lock'):
        yield


def prepare(lab, config, backend, workdir, prompt, outputs=(), machine=None):
    """Return prompt and lineage: fresh with optional handoff, continue, or native fork."""
    config = config or {}
    if not isinstance(config, dict):
        raise SpecError('Context must be a mapping.')
    mode = config.get('mode', 'fresh')
    if mode not in ('fresh', 'continue', 'native-fork'):
        raise SpecError('Context must be fresh, continue or native-fork. Enable handoff on a fresh context to share a summary.')
    lineage = {'mode': mode, 'source_run': config.get('run_id')}
    if mode == 'fresh' and not config.get('handoff'):
        return prompt, {'context': lineage}
    try:
        _target, _where, path, source = find_run(lab, config.get('run_id') or '')
    except (ValueError, TypeError):
        raise SpecError('The context source run is unavailable.') from None
    if source.get('status') not in TERMINAL:
        raise SpecError('Wait for the source task to finish before continuing or copying its context.')
    if mode == 'fresh' and config.get('handoff'):
        lineage['method'] = 'handoff'
        folder = run_dir(path.parent, source['run_id'])
        files = [str(p) for p in (folder / 'prompt.md', folder / 'preamble.md', path.parent / str(source.get('stream') or '')) if p.is_file()]
        if source.get('remote'):
            from remote_projects import owner
            base = source['remote']['path'].rstrip('/') + '/.bus/arlotope/' + owner(lab.hub) + '/agents/'
            files = [base+source['run_id']+'.d/prompt.md', base+source['run_id']+'.d/preamble.md', base+source['stream']]
        summaries = [handoff(source, [*files, *outputs])]
        for other_id in config.get('run_ids', []):
            if other_id == source['run_id']:
                continue
            other = find_run(lab, other_id)
            if not other or other[3].get('status') != 'completed':
                raise SpecError('A selected handoff source has not completed.')
            summaries.append(handoff(other[3]))
        lineage['source_runs'] = [source['run_id'], *[i for i in config.get('run_ids', []) if i != source['run_id']]]
        return '\n\n'.join(summaries) + '\n\nYour independent task:\n' + prompt, {'context': lineage}
    same_folder = (str((source.get('remote') or {}).get('path') or source.get('cwd') or '').rstrip('/') == str(workdir).rstrip('/')
                   if machine else Path(source.get('cwd') or '').resolve() == Path(workdir).resolve())
    if source.get('backend') != backend or source.get('machine') != machine or not same_folder:
        raise SpecError('Continue and native fork require the same backend, machine and folder. Choose a new agent with handoff.')
    sid = source.get('session_id')
    if not sid:
        raise SpecError('The source has no resumable conversation. Choose a new agent with handoff.')
    assert_available(lab, sid, expected=source, forks=mode=='native-fork')
    current = session_head(lab, source)
    if current['run_id'] != source['run_id']:
        raise SpecError('This conversation has newer work in '+current['run_id']+'. Select its latest task, or use a fresh handoff.')
    lineage['source_head'] = {'run': source['run_id'], 'attempt': source.get('attempt', 0)}
    lineage['source_session'] = sid
    if mode == 'native-fork':
        assert_available(lab, sid, expected=source, forks=True)
        if backend not in ('claude', 'codex', 'opencode', 'acp'):
            raise SpecError('Native fork is not supported by this adapter. Choose a new agent with handoff.')
        from .live import enabled
        if backend in ('codex', 'opencode') and not enabled(lab.prog()):
            raise SpecError('Native fork requires a live connection for this backend.')
        lineage['method'] = 'native'
        return prompt, {'context': lineage, 'fork_session': sid}
    assert_available(lab, sid, expected=source)
    return prompt, {'context': lineage, 'session_id': sid, 'resume': {'mode': 'reply', 'text': prompt}}


def same_session(a, b):
    for key in ('backend', 'machine', 'cwd'):
        if a.get(key) != b.get(key):
            return False
    left, right = (a.get('assignment') or {}).get('identity'), (b.get('assignment') or {}).get('identity')
    return not left or not right or left == right


def session_head(lab, source, exclude=None):
    if not source.get('session_id'):
        return source
    candidates = [m for *_, m in all_runs(lab) if m.get('session_id') == source.get('session_id')
                  and m.get('run_id') != exclude and same_session(source, m)
                  and not ((m.get('context') or {}).get('source_run') and m.get('conversation_started') is False
                           and m.get('status') in {'failed','killed','timeout'})]
    ancestors = {(m.get('context') or {}).get('source_run') for m in candidates}
    leaves = [m for m in candidates if m['run_id'] not in ancestors]
    if len(leaves) > 1:
        raise SpecError('This conversation has conflicting owners. Choose a fresh handoff.')
    return leaves[0] if leaves else source


def validate_head(lab, run):
    expected = (run.get('context') or {}).get('source_head')
    if not expected:
        return
    hit = find_run(lab, expected['run'])
    if not hit or hit[3].get('attempt', 0) != expected['attempt']:
        raise SpecError('The source conversation changed while queued. Select its latest task or start new with handoff.')
    head = session_head(lab, hit[3], run['run_id'])
    if head['run_id'] != expected['run']:
        raise SpecError('The source conversation has newer work. Re-select its current task.')
    assert_available(lab, hit[3].get('session_id'), run['run_id'], expected=hit[3], forks=bool(run.get('fork_session')))


def assert_available(lab, session_id, exclude=None, *, expected=None, forks=False):
    if not session_id:
        return
    for _target, _where, _path, run in all_runs(lab):
        owns = run.get('session_id') == session_id
        reserved_fork = not forks and run.get('fork_session') == session_id and not run.get('fork_started')
        if run.get('run_id') != exclude and (owns or reserved_fork) and (not expected or same_session(expected, run)) and run.get('status') in ACTIVE | PAUSED | {'queued'}:
            raise SpecError('This conversation already has active work. Wait, or fork an independent agent.')


def assert_current(lab, run):
    if session_head(lab, run)['run_id'] != run['run_id']:
        raise SpecError('This conversation has newer work. Open its latest task or use a fresh handoff.')
    assert_available(lab, run.get('session_id'), run['run_id'], expected=run)


def workflow_evidence(lab, incoming, imported):
    """Carry accepted source references along the same causal edges as real run IDs."""
    result = {(e['node'], e.get('visit')): e for e in imported}
    seen, queue = set(), [r for r in incoming.values() if r]
    while queue:
        rid = queue.pop()
        if rid in seen:
            continue
        seen.add(rid)
        hit = find_run(lab, rid)
        if hit:
            record = hit[3]
            for e in record.get('input_evidence') or []:
                result[(e['node'], e.get('visit'))] = e
            queue.extend(r for r in record.get('input_runs') or [] if r)
    return list(result.values())


class MissingWorkflowSource(SpecError):
    """No conversation exists for a causal task, e.g. researcher-supplied work."""


def workflow_sources(lab, incoming, context, node):
    """Find exact causal source runs, never the latest unrelated run with the same node name."""
    requested = context.get('from')
    requested = requested if isinstance(requested, list) else [requested]
    result = []
    for task in requested:
        seen, found, queue = set(), set(), list(incoming.values())
        while queue:
            rid = queue.pop()
            if not rid or rid in seen:
                continue
            seen.add(rid)
            hit = find_run(lab, rid)
            if not hit:
                continue
            record = hit[3]
            if record.get('workflow_node') == task:
                found.add(rid)
            else:
                queue.extend(record.get('input_runs') or [])
        if not found and task == node and context.get('initial') == 'fresh':
            continue
        if not found:
            raise MissingWorkflowSource('The context source has no completed run. Start fresh with its evidence instead.')
        if len(found) != 1:
            raise SpecError('Choose an unambiguous completed context source, or start new with evidence handoff.')
        result.append(find_run(lab, next(iter(found)))[3])
    return result


def role_text(lab, name):
    text = _role_text(lab, name)
    if name:
        path = lab.hub / 'lab/workflow/roles' / (name + '.add.md')
        if path.is_file():
            import re
            text += '\n\n' + re.sub(r'\A---\r?\n.*?\r?\n---\r?\n?', '', path.read_text(encoding='utf-8-sig'), count=1, flags=re.S)
    return text


def _role_text(lab, name):
    if not name:
        return ''
    if not isinstance(name, str) or not all(c.isalnum() or c in '-_' for c in name):
        raise SpecError('Choose a valid role ID.')
    folder = lab.hub / 'agent-roles'
    path = folder / (name + '.md')
    if path.is_file():
        return path.read_text(encoding='utf-8-sig')
    # General roles need no backend-specific role files; these are ordinary task instructions.
    builtins = {
        'assistant': 'Help the person navigate and understand the whole workspace. Use current evidence; distinguish facts, proposals and pending decisions.',
        'analyst': 'Investigate carefully, inspect evidence, and explain assumptions and uncertainty.',
        'reviewer': 'Independently assess the named evidence against the rubric. Give an evidenced verdict and specific corrections.',
        'writer': 'Write clearly for the requested audience, grounding factual claims in the supplied evidence.',
        'designer': 'Design and preview the requested room or workflow. Work in the assigned draft; preserve unrelated resources.',
        'general': 'Carry out the task carefully using the available tools and evidence.'}
    if name not in builtins:
        import yaml
        structure = lab.hub / 'lab/structure.yaml'
        roles = (yaml.safe_load(structure.read_text(encoding='utf-8')) or {}).get('roles', {}) if structure.is_file() else {}
        if name in roles:
            return str(roles[name].get('instructions') or '')
        raise SpecError(f'Unknown role {name!r}. Create its instructions before assigning it.')
    return builtins[name]
