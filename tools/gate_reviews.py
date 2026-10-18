"""Lab-owned gate policy over ordinary executor runs; only the engine applies verdicts."""
import base64
import hashlib
import json
from pathlib import Path

from kernel import checkpoints, journal, model, studies


def evidence_paths(hub, s, refs):
    import remote_projects
    remote = remote_projects.location(s.get('project'))
    return {ref:(ref.replace('{project}', remote['path']).replace('{study}', s['id'])
                 if remote and ref.startswith('{project}/') else str(checkpoints._fill(hub, s['id'], ref))) for ref in refs}


def scope(hub, s, cp, entering=False):
    node = cp.get('before') or cp.get('during')
    if s.get('active_steps') is not None:
        token = next((t for t in s['active_steps'] if t['id'] == node), None)
        return {'node': node, 'visit': token['visit']} if token else None
    entries = sum(e['kind'] in ('move', 'new') and (e.get('to') or e.get('step')) == node
                  for e in journal.events(hub, s['id']))
    pending = (s.get('waiting') or {}).get('checkpoint') == cp['id']
    return {'node': node, 'visit': entries + (1 if cp.get('before') and (entering or pending or s['step'] != node) else 0)}


def revision(hub, s, cp):
    import remote_projects as remote
    loc = remote.location(s.get('project'))
    files = {}
    for rel in cp.get('evidence') or []:
        if loc and str(rel).startswith('{project}/'):
            name = rel.replace('{project}/', '', 1).replace('{study}', s['id'])
            files[rel] = remote.rpc(loc['machine'], 'files', {'path':loc['path'], 'owner':remote.owner(hub),
                                                            'study':s['id'], 'files':[name], 'digest':True}).get(name)
        else:
            p = checkpoints._fill(Path(hub), s['id'], rel)
            if p is None or not p.exists():
                files[rel] = None
            elif p.is_file():
                files[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            else:
                files[rel] = [(str(f.relative_to(p)), f.stat().st_mtime_ns, f.stat().st_size)
                              for f in sorted(p.rglob('*')) if f.is_file()]
    value = {'scope':scope(hub, s, cp), 'terms':model.terms(cp), 'files':files}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(), files


def valid_approval(hub, s, cp, record):
    if not record.get('judge_scope'):
        return True
    here = scope(hub, s, cp)
    if here is None:
        return True
    if s.get('active_steps') is None and cp.get('before') and s['step'] != here['node'] and not s.get('waiting'):
        path = model.workflow(s['workflow'], hub)['path']
        if s['step'] in path and path.index(s['step']) > path.index(here['node']):
            return True  # Historical approval; _go checks a prospective entry separately.
    if s.get('active_steps') is None and s['step'] != here['node'] and not cp.get('before'):
        return True
    return here == record['judge_scope']


def current_evidence(hub, s, cp, record, entering=False):
    """Check at admission, rather than doing filesystem/SSH work during journal folding."""
    if not record.get('evidence_revision'):
        return True
    expected = scope(hub, s, cp, entering=entering)
    if record.get('judge_scope') != expected:
        return False
    return revision(hub, s, cp)[0] == record['evidence_revision']


def decisions(cp):
    return cp.get('decisions') or {'proceed':'continue', 'revise':cp.get('before') or cp['during'], 'stop':'parked'}


def start_waiting(lab, slug, requested=None, source=None, retry=False):
    from executor.procs import excl_lock
    with excl_lock(lab.bus / '.gate-reviews.lock'):
        return _start_waiting(lab, slug, requested, source, retry)


def _start_waiting(lab, slug, requested=None, source=None, retry=False):
    from executor import enqueue, RunSpec, all_runs, ACTIVE, PAUSED
    s = studies.study(lab.hub, slug)
    if not s or s['finished']:
        return []
    waiting = {x['checkpoint'] for x in s.get('task_waits', [])}
    if s.get('waiting'):
        waiting.add(s['waiting'].get('checkpoint'))
    if requested:
        waiting.add(requested)
    runs = [m for *_x,m in all_runs(lab) if m.get('subject') == slug and m.get('judge')]
    queued = []
    for cid in waiting:
        cp = model.checkpoint(cid, s['workflow'], lab.hub)
        if not cp or cp.get('approver') != 'agent':
            continue
        if studies.approved(lab.hub, slug, cid) and current_evidence(lab.hub, s, cp, s['approvals'].get(cid, {})):
            continue
        key, files = revision(lab.hub, s, cp)
        if any(v is None for v in files.values()) or not files:
            continue
        previous = [r for r in runs if r['judge']['checkpoint'] == cid and r['judge']['revision'] == key]
        cfg = cp.get('judge') or {}
        if previous and (not retry or any(r['status'] in ACTIVE | PAUSED | {'queued'} for r in previous)):
            continue
        if len(previous) >= cfg.get('max_attempts', 3):
            continue
        visit = scope(lab.hub, s, cp)
        if cfg.get('max_visits') and visit and visit['visit'] > cfg['max_visits']:
            continue
        choices = decisions(cp)
        output = f'.bus/judgments/{cid}-{key[:16]}-{len(previous)+1}.json'
        skill = cfg.get('skill') or 'gate-review'
        prompt = (f'Read and follow {lab.hub.as_posix()}/.claude/skills/{skill}/SKILL.md.\n'
                  f'Independent gate: {cp["title"]}\nRubric: {cfg.get("rubric") or cp.get("means") or cp.get("tell") or cp["title"]}\n'
                  'Inspect only the supplied evidence and rubric; do not inherit the author conversation.\n'
                  'Evidence paths: ' + '\n'.join(evidence_paths(lab.hub, s, files).values()) + '\n'
                  f'Allowed decisions: {json.dumps(choices)}\nWrite {output} relative to your working directory. '
                  'JSON object: {"decision":"declared decision", "reason":"evidenced reason", "evidence":["inspected paths"]}. '
                  'Do not approve, move studies, edit candidate evidence or start later tasks.')
        cfg_agent = {k:cfg[k] for k in ('preset','backend','model','effort','max_minutes') if cfg.get(k)}
        cfg_agent.setdefault('max_minutes', 15)
        spec = RunSpec(skill='gate-judge', target=slug, prompt_override=prompt, role='reviewer', label='Review: '+cp['title'],
                       chain='off', extra={'judge':{'checkpoint':cid, 'revision':key, 'scope':visit, 'output':output,
                                                   'source':source, 'decisions':choices, 'evidence':list(files)}}, **cfg_agent)
        queued.append(enqueue(lab, spec)['run_id'])
    return queued


def choose(lab, slug, cid, choice, note='', *, judge=None):
    from kernel.branches import locked
    with locked(lab.hub):
        s = studies.study(lab.hub, slug)
        cp = checkpoints.find(lab.hub, slug, cid)
        if judge:
            prior = next((e for e in journal.approvals(lab.hub, slug, cid) if e.get('by')=='judge:'+judge['run_id']), None)
            if prior:
                return prior
        node = cp.get('before') or cp.get('during')
        token = next((t for t in s.get('active_steps', []) if t['id']==node), None)
        if s.get('active_steps') is not None and not token:
            raise ValueError('This gate is no longer active.')
        if s.get('active_steps') is None and s['step'] != node and (s.get('waiting') or {}).get('checkpoint') != cid:
            raise ValueError('This study is not at that gate.')
        choices = decisions(cp)
        if choice not in choices:
            raise ValueError('Choose a declared gate decision.')
        by = 'judge:'+judge['run_id'] if judge else 'pi'
        fields = {'gate_decision':choice}
        if judge:
            key,_ = revision(lab.hub, s, cp)
            if cp.get('approver') != 'agent' or key != judge['judge']['revision']:
                raise ValueError('The gate or evidence changed during review. Request a new review.')
            fields.update(judge_scope=scope(lab.hub, s, cp), evidence_revision=key)
        destination = choices[choice]
        rec = checkpoints.decide(lab.hub, slug, cid, 'approved' if destination=='continue' else 'changes-requested',
                                 by=by, via='kernel' if judge else 'dashboard', note=note, **fields)
        if destination == 'continue':
            studies.resume(lab.hub, slug, by)
        elif s.get('active_steps') is not None:
            if destination in model.SHELF_LABEL:
                studies._go(lab.hub, slug, s, destination, choice, by, note)
            else:
                journal.append(lab.hub, slug, 'task-routed', by, node=node, visit=token['visit'],
                               to=[destination], run_id=judge['run_id'] if judge else None, checkpoint=cid, outcome=choice)
        else:
            studies._go(lab.hub, slug, s, destination, choice, by, note)
        studies.render_registry(lab.hub)
    return rec


def finish(lab, m):
    if m.get('status') != 'completed':
        return
    import remote_projects as remote
    cfg = m['judge']
    if m.get('remote'):
        raw = remote.call(lab.hub, m['subject'], 'read', file=cfg['output'])
        text = base64.b64decode(raw['data']).decode()
    else:
        text = (Path(m['cwd']) / cfg['output']).read_text(encoding='utf-8')
    verdict = json.loads(text)
    if not isinstance(verdict, dict) or not isinstance(verdict.get('reason'), str) or not verdict['reason'].strip() or not isinstance(verdict.get('evidence'), list) or not verdict['evidence']:
        raise ValueError('A gate verdict needs a reason and evidence paths.')
    cp = checkpoints.find(lab.hub, m['subject'], cfg['checkpoint'])
    supplied = cfg.get('evidence') or cp.get('evidence') or []
    s = studies.study(lab.hub, m['subject'])
    allowed = {p.replace('\\','/') for p in [*supplied, *evidence_paths(lab.hub, s, supplied).values()]}
    if any(not isinstance(ref, str) or ref.replace('\\','/') not in allowed for ref in verdict['evidence']):
        raise ValueError('The verdict must reference the supplied evidence paths.')
    choose(lab, m['subject'], cfg['checkpoint'], verdict.get('decision'), verdict['reason'], judge=m)
    m['judge_result'] = verdict
    if cfg.get('source') and verdict['decision'] in cfg['decisions'] and cfg['decisions'][verdict['decision']]=='continue':
        cp = checkpoints.find(lab.hub, m['subject'], cfg['checkpoint'])
        if cp.get('during'):
            from executor import reply
            reply(lab, cfg['source'], 'The configured gate review approved this point. Continue the assigned task.')
