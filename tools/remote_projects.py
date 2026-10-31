"""Remote project locations and controller-side execution. Research state remains in this Lab."""
from __future__ import annotations

import base64
import hashlib
import http.client
import io
import json
import shlex
import zipfile
from pathlib import Path, PureWindowsPath
from urllib.parse import quote, unquote, urlsplit

import labfiles

ROOT = Path(__file__).resolve().parents[1]
SCHEME = 'arlotope+ssh'


class RemoteError(ValueError):
    pass


def location(value):
    if not isinstance(value, str) or not value.startswith(SCHEME + '://'):
        return None
    u = urlsplit(value)
    if not u.netloc or not u.path.startswith('/') or u.query or u.fragment or any(c in u.netloc for c in '/\\@:'):
        raise RemoteError('Invalid remote project location.')
    path = unquote(u.path)
    if len(path) > 3 and path[0] == '/' and path[2] == ':' and path[3] == '/':
        path = path[1:]
    return {'machine': u.netloc, 'path': path}


def uri(machine, path):
    from project_worker import safe_id
    safe_id(machine)
    if not isinstance(path, str) or '\0' in path or not (path.startswith('/') or PureWindowsPath(path).is_absolute()):
        raise RemoteError('Use an absolute remote project path.')
    if PureWindowsPath(path).drive:
        path = '/' + PureWindowsPath(path).as_posix()
    return SCHEME + '://' + machine + quote(path, safe='/')


def project(hub, slug):
    row = labfiles.row(hub, slug)
    return location((row or {}).get('project'))


def owner(hub):
    from project_identity import lab_identity
    return lab_identity(hub)['execution_owner']


def spool(hub, slug):
    from project_worker import safe_id
    return Path(hub) / 'lab/.bus/remote-projects' / safe_id(slug)


def machines():
    return labfiles.home_rows('machines')


def machine(mid):
    m = next((m for m in machines() if m.get('id') == mid), None)
    if not m:
        raise RemoteError('Connect this machine from Machines first.')
    return m


def rpc(mid, method, data=None):
    info = machine(mid).get('worker') or {}
    if not info.get('port'):
        raise RemoteError('Connect the project runner on this machine first.')
    try:
        c = http.client.HTTPConnection('127.0.0.1', int(info['port']), timeout=190 if method in ('clone','providers') else 35)
        c.request('POST', '/rpc', json.dumps({'method': method, 'data': data or {}}),
                  {'Content-Type': 'application/json', 'Cookie': info.get('cookie') or ''})
        response = c.getresponse()
        result = json.loads(response.read())
        c.close()
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise RemoteError('The project runner is unreachable. Reconnect the machine; remote work may still be running.') from error
    if response.status != 200 or not result.get('ok'):
        raise RemoteError(result.get('error') or 'The worker refused the request.')
    return result.get('result')


def call(hub, slug, method, **data):
    loc = project(hub, slug)
    if not loc:
        raise RemoteError('This study has no remote project.')
    return rpc(loc['machine'], method, {'path': loc['path'], 'owner': owner(hub), 'study': slug, **data})


def bundle():
    """Immutable, self-contained Python zipapp. No dashboard, assets, registry or workflow catalog."""
    import yaml
    from importlib.metadata import distribution
    files = {}
    for name in ('LICENSE', 'LICENSES/MIT-original.txt', 'LICENSES/README.md'):
        files[name] = (ROOT / name).read_bytes()
    dependency = distribution('PyYAML')
    notices = [p for p in dependency.files or [] if p.name.upper() == 'LICENSE']
    if not notices:
        raise RemoteError('PyYAML license notice is missing. Reinstall PyYAML before bundling the worker.')
    for index, notice in enumerate(notices):
        files['LICENSES/PyYAML' + (str(index) if index else '') + '.txt'] = dependency.locate_file(notice).read_bytes()
    for name in ('project_worker', 'loopback_http', 'project_identity', 'project_files', 'project_control', 'interactive_terminal', 'terminal', 'labfiles', 'artifact', 'knowledge', 'tagging', 'github_access', 'frameworks', 'framework_activity', 'skill_resources', 'provider_access', 'native_providers'):
        files[name + '.py'] = (ROOT / 'tools' / (name + '.py')).read_bytes()
    files['lab_profile.py'] = (ROOT / 'tools/project_profile.py').read_bytes()
    files['executor/__init__.py'] = b'"""Execution-only package; no central scheduler or research kernel."""\n'
    for name in ('lab', 'live', 'manifest', 'actions', 'records', 'procs', 'supervise'):
        files['executor/' + name + '.py'] = (ROOT / 'tools/executor' / (name + '.py')).read_bytes()
    for path in (ROOT / 'tools/executor/backends').glob('*.py'):
        files['executor/backends/' + path.name] = path.read_bytes()
    # PyYAML is already a hub dependency; bundle its pure Python fallback instead of installing on hosts.
    for path in Path(yaml.__file__).parent.glob('*.py'):
        files['yaml/' + path.name] = path.read_bytes()
    files['__main__.py'] = b'from project_worker import main\nraise SystemExit(main())\n'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, content)
    blob = output.getvalue()
    return hashlib.sha256(blob).hexdigest()[:20], blob


def capture(lab, validated, rd):
    """Copy instruction text, not the Lab filesystem or credentials, into this run's snapshot."""
    from kernel import model
    paths = []
    files = {}
    for base in dict.fromkeys((model.CODE, lab.hub)):
        inherited = [base / p for p in ('AGENTS.md', 'AGENT-GUIDE.md')]
        inherited.append(base / 'docs/external-frameworks.md')
        for path in (base / '.claude/skills').glob('*/SKILL.md'):
            inherited.extend(p for p in path.parent.rglob('*') if p.is_file() and not p.is_symlink()
                             and (p.suffix in ('.md', '.py', '.js', '.json', '.yaml', '.yml')
                                  or p.name in ('LICENSE', 'NOTICE')) and p.stat().st_size < 100_000)
        inherited.extend((base / 'agent-roles').glob('*.md'))
        inherited.extend((base / 'workflow/frameworks').glob('*.yaml'))
        inherited.extend(p for p in (base / 'templates').rglob('*.md') if p.stat().st_size < 100_000)
        for p in inherited:
            if p.is_file():
                files[p.relative_to(base).as_posix()] = p.read_text(encoding='utf-8-sig')
    paths.extend(lab.hub / p for p in ('lab/RESEARCH.md', 'lab/SYSTEM.md'))
    paths.extend((lab.hub / 'studies' / validated['subject']).glob('*.md'))
    paths.extend(p for p in (lab.hub / 'lab/templates').rglob('*.md') if p.stat().st_size < 100_000)
    for p in paths:
        if p.is_file():
            files[p.relative_to(lab.hub).as_posix()] = p.read_text(encoding='utf-8-sig')
    (rd / 'instructions.json').write_text(json.dumps(files), encoding='utf-8')
    # Preserve binary originals as well as text. Each file is transferred separately below.
    import shutil
    materials = lab.hub / 'studies' / validated['subject'] / 'materials'
    if materials.is_dir():
        for p in materials.iterdir():
            if p.is_file() and not p.is_symlink():
                if p.stat().st_size > 5 * 1024 * 1024:
                    raise RemoteError('A study material exceeds the 5 MB remote transfer limit: ' + p.name)
                target = rd / 'materials' / p.name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(p, target)


def rewrite(lab, m, text):
    """Translate the specific run paths before their containing controller directory."""
    from executor.manifest import run_dir
    loc = m['remote']
    local = lab.project_workdir(m['target'])
    local_rd = run_dir(lab.agents_dir(local), m['run_id'])
    remote_rd = loc['path'].rstrip('/') + '/.bus/arlotope/' + owner(lab.hub) + '/agents/' + m['run_id'] + '.d'
    for source, destination in ((local_rd, remote_rd), (local, loc['path']), (lab.hub, remote_rd + '/instructions')):
        for spelling in sorted({str(source), source.as_posix()}, key=len, reverse=True):
            text = text.replace(spelling, destination)
    # Inherited resources can live in the installed runtime, outside this Lab's directory.
    from kernel import model
    if model.CODE.resolve() != lab.hub.resolve():
        for relative in ('tools', 'arlo.py', '.claude/skills', 'agent-roles', 'templates', 'workflow/frameworks', 'docs/external-frameworks.md', 'AGENTS.md', 'AGENT-GUIDE.md'):
            source = model.CODE / relative
            for spelling in sorted({str(source), source.as_posix()}, key=len, reverse=True):
                text = text.replace(spelling, remote_rd + '/instructions/' + relative)
    return text


def dispatch(lab, path, m):
    from executor.manifest import run_dir
    loc, rid = m['remote'], m['run_id']
    from executor.contexts import validate_head
    validate_head(lab, m)
    if project(lab.hub, m['subject']) != loc:
        raise RemoteError('This study moved. Reassign this run before dispatch.')
    if m.get('session_id') and m.get('status') == 'resuming':
        from executor.contexts import assert_available
        assert_available(lab, m['session_id'], rid, expected=m)
    facts = rpc(loc['machine'], 'info', {'backends': (machine(loc['machine']).get('agent_config') or {})})
    rd = run_dir(path.parent, rid)
    remote_rd = loc['path'].rstrip('/') + '/.bus/arlotope/' + owner(lab.hub) + '/agents/' + rid + '.d'
    snapshot = remote_rd + '/instructions'
    runtime = facts['runtime']
    instructions = json.loads((rd / 'instructions.json').read_text(encoding='utf-8'))
    instructions['arlo.py'] = ('import os,sys\nos.execv(sys.executable, [sys.executable, ' + repr(runtime) + ', "control", *sys.argv[1:]])\n')
    instructions['tools/arlo_cli.py'] = instructions['arlo.py']
    instructions['tools/lab_bus.py'] = instructions['arlo.py']
    instructions['tools/artifact.py'] = ('import os,sys\nos.execv(sys.executable, [sys.executable, ' + repr(runtime) + ', "artifact", *sys.argv[1:]])\n')
    instructions['tools/knowledge.py'] = ('import os,sys\nos.execv(sys.executable, [sys.executable, ' + repr(runtime) + ', "knowledge", *sys.argv[1:]])\n')
    instructions['tools/frameworks.py'] = ('import os,sys\nos.execv(sys.executable, [sys.executable, ' + repr(runtime) + ', "framework", *sys.argv[1:]])\n')
    prompt = rewrite(lab, m, (rd / 'prompt.md').read_text(encoding='utf-8'))
    pre = rewrite(lab, m, (rd / 'preamble.md').read_text(encoding='utf-8'))
    local_knowledge=f'python "{(lab.hub / "tools/knowledge.py").as_posix()}" --hub "{lab.hub.as_posix()}" --study {m["subject"]}'
    remote_knowledge='python3 '+shlex.quote(runtime)+' knowledge --project '+shlex.quote(loc['path'])
    pre=pre.replace(rewrite(lab,m,local_knowledge),remote_knowledge)
    pre += ('\n\nREMOTE PROJECT\nThe owning Lab is on another machine. Its instruction files are in ' + snapshot
        + '. Read them there. Project files stay in ' + loc['path'] + '.\n'
        + 'For status, next, approved or move, use: python3 ' + runtime + ' control <verb> <arguments>. '
        + 'These requests wait for the main Lab. No new approval is available while it is unreachable. '
        + 'For your run report use the same command with emit run_report --data next=... --data needs_pi=... .\n')
    config = dict(lab.prog())
    config['backends'] = machine(loc['machine']).get('agent_config') or {}
    # Backend options are portable; executable paths and credentials are not.
    for backend, settings in (lab.prog().get('backends') or {}).items():
        config['backends'].setdefault(backend, {}).update({k: v for k, v in settings.items() if k != 'command'})
    if m.get('assignment'):
        config['backends'][m['backend']] = {**config['backends'].get(m['backend'], {}), **m['assignment']['options']}
    supplied = dict(m)
    if (m.get('resume') or {}).get('text'):
        supplied['resume'] = {**m['resume'], 'text': rewrite(lab, m, m['resume']['text'])}
    for material in (rd / 'materials').glob('*'):
        if material.is_file():
            receipt = call(lab.hub, m['target'], 'material', run_id=rid, name=material.name,
                           data=base64.b64encode(material.read_bytes()).decode())
            if not receipt or receipt.get('stored') is not True:
                raise RemoteError('Reconnect this machine to update its runner before using study materials.')
    result = call(lab.hub, m['target'], 'dispatch', run_id=rid, manifest=supplied, prompt=prompt, preamble=pre,
                  instructions={k: rewrite(lab, m, v) for k, v in instructions.items()}, config=config,
                  resources={p.relative_to(rd / 'skills').as_posix(): base64.b64encode(p.read_bytes()).decode()
                             for p in (rd / 'skills').rglob('*') if p.is_file()})
    m['remote_dispatched'] = True
    m.pop('remote_dispatch_pending', None)
    m['remote_status'] = 'connected'
    labfiles.write_json(path, m)
    return result


def _request(lab, m, request):
    from kernel import studies, branches
    verb, args = request.get('verb'), request.get('values') or []
    slug, rid = m['subject'], m['run_id']
    if request.get('run_id') != rid:
        raise RemoteError('This request belongs to another run.')
    if m.get('judge') and verb == 'move':
        raise RemoteError('Return the gate verdict. Only the engine applies its decision.')
    if verb == 'artifact':
        import artifact
        if request.get('action') == 'list':
            payload = request.get('payload') or {}
            return {'result': artifact.all_artifacts(lab.hub, study=slug, limit=max(1,min(int(payload.get('limit') or 300),1000)),
                         run=payload.get('run'), about=payload.get('about'), before=payload.get('before'),
                         search=str(payload.get('search') or '')[:500], state=payload.get('state') or 'all')}
        if request.get('action') != 'publish':
            raise RemoteError('Unknown artifact operation.')
        for saved in artifact.all_artifacts(lab.hub, limit=None, run=rid):
            if saved.get('request_id') == request['id'] and saved.get('run_id') == rid:
                return {'result': saved}
        payload = dict(request.get('payload') or {})
        if payload.get('study') not in (None, slug):
            raise RemoteError('Publish artifacts for the assigned study only.')
        about = payload.get('about')
        if about and about.split(':', 1)[0] != rid:
            raise RemoteError('An explanation must describe its own run.')
        import tempfile
        with tempfile.TemporaryDirectory(prefix='artifact-', dir=spool(lab.hub, slug)) as folder:
            content, name = payload.pop('content', None), payload.pop('name', None)
            context = {'run_id': rid, 'skill': m.get('skill'), 'source_machine': m['remote']['machine'],
                       'source_path': payload.pop('source_path', None), 'request_id': request['id']}
            file = None
            if content is not None:
                data = base64.b64decode(content, validate=True)
                if len(data) > artifact.MAX_BYTES:
                    raise RemoteError('Publish a smaller artifact.')
                file = Path(folder) / ('content' + Path(name or '').suffix.lower())
                file.write_bytes(data)
            payload['study'] = slug
            if set(payload) - {'title', 'kind', 'study', 'note', 'question', 'choices', 'about'} or not payload.get('title'):
                raise RemoteError('Invalid artifact request.')
            return {'result': artifact.publish(file=str(file) if file else None, h=lab.hub, context=context, **payload)}
    if verb == 'status':
        return {'result': studies.study(lab.hub, slug)}
    if verb == 'next':
        return {'result': studies.next_for(lab.hub, slug)}
    if verb in ('approved', 'move'):
        # Permit both `move done` and the normal `move study done` spelling.
        if len(args) > 1:
            if args[0] != slug:
                raise RemoteError('A project run can only address its assigned study.')
            args = args[1:]
        if not args:
            raise RemoteError('Supply a checkpoint or outcome.')
        if verb == 'approved':
            ok = studies.approved(lab.hub, slug, args[0])
            return {'code': 0 if ok else 1, 'text': 'Approved' if ok else 'Waiting for approval'}
        marker = '[request:' + request['id'] + ']'
        from kernel import journal
        if any(marker in str(e.get('note', '')) for e in journal.events(lab.hub)):
            return {'result': studies.study(lab.hub, slug), 'text': 'Outcome already recorded.'}
        state = studies.study(lab.hub, slug)
        note = request.get('note', '') + ' ' + marker
        if m.get('workflow_node'):
            result = branches.move(lab.hub, state, args[0], note, 'run:' + rid, m['workflow_node'], run_id=rid)
        else:
            result = studies.move(lab.hub, slug, args[0], note=note, by='run:' + rid)
        return {'result': result}
    if verb == 'emit':
        kind = (args or ['note'])[0]
        if kind not in ('run_report', 'note', 'escalation', 'writeback'):
            raise RemoteError('This event is not available to a project run.')
        data = dict(x.split('=', 1) for x in request.get('data', []) if '=' in x)
        labfiles.append_jsonl(lab.project_workdir(slug) / '.bus/events.jsonl', {'ts': labfiles.now(), 'kind': kind,
            'source': slug, 'idea': slug, 'run_id': rid, 'detail': request.get('detail', ''), 'data': data})
        return {'result': {'ok': True}}
    raise RemoteError('Unsupported controller request.')


# What a remote machine may tell this Lab about a run: its progress, as data. Everything that names a
# place or an identity (run_id, subject, target, stream, cwd, skill, judge, workflow_node, backend, pid,
# last_result's file, …) stays the controller's own.
REMOTE_FIELDS = frozenset({
    'status', 'status_ts', 'reason', 'heartbeat', 'attempt', 'attempts', 'transport', 'started', 'finished',
    'exit_code', 'wall_seconds', 'failure_kind', 'limit_reset', 'not_before', 'no_live', 'resume',
    'session_id', 'model_used', 'cli', 'cli_version', 'conversation_started', 'fork_started',
    'pending_question', 'pending_questions', 'pending_permissions', 'external_interactions', 'qa', 'assumed',
    'delivery_uncertain', 'undelivered_input', 'knowledge_question', 'knowledge_error', 'watch_error',
    'last_message', 'last_text', 'last_action', 'n_actions', 'in_tool', 'denials', 'usage', 'limits', 'subagents',
})


def remote_progress(remote):
    """The allowlisted fields of a manifest a remote machine returned, with a status this Lab knows."""
    from executor.manifest import STATUSES
    if not isinstance(remote, dict) or remote.get('status') not in STATUSES:
        raise RemoteError('The remote run reported an unreadable state.')
    return {k: v for k, v in remote.items() if k in REMOTE_FIELDS}


def sync(lab):
    """Refresh remote mirrors, deliver queued input and settle task-scoped controller requests.
    Every local path comes from this Lab's own record of the run; the remote supplies only data."""
    from executor.manifest import TERMINAL, all_runs, read_manifest, run_dir
    for _, _, path, m in all_runs(lab):
        if not m.get('remote'):
            continue
        rd = run_dir(path.parent, m['run_id'])
        try:
            if (m.get('status') in TERMINAL and m.get('post_processed') and m.get('remote_settled')
                    and m.get('remote_status') == 'connected'
                    and not m.get('remote_dispatch_pending') and not (rd/'stop').exists()
                    and not any((rd/'inbox').glob('*.json'))):
                continue  # Settled history is local; replies and disconnected/final syncs still poll.
            if m.get('remote_dispatch_pending'):
                dispatch(lab, path, m)
            if not m.get('remote_dispatched'):
                continue
            from kernel import studies
            state = studies.study(lab.hub, m['subject'])
            outputs = studies.study_outputs(lab.hub, dict(state, step=m.get('workflow_node') or state['step']))
            from framework_activity import request as activity_request
            try:
                activity = activity_request(lab.hub, m)
            except (OSError, ValueError, KeyError, TypeError) as error:
                activity = None
                m['external_activity'] = {'error':str(error)}
            if activity:
                activity.pop('machine')
            poll = call(lab.hub, m['target'], 'poll', run_id=m['run_id'], offset=m.get('remote_offset', 0),
                        actions_offset=m.get('remote_actions_offset', 0), records_offset=m.get('remote_records_offset',0),
                        study_files=outputs, framework_activity=activity)
            if not poll.get('found'):
                raise RemoteError('The remote run is unavailable; no replacement was started.')
            current = read_manifest(path) or m
            m = current
            remote = remote_progress(poll['manifest'])
            if remote['status'] == 'queued' and remote.get('resume'):
                current['post_processed'] = False  # A late message creates another turn to process.
            # A completed old attempt must never overwrite a locally queued resume.
            if current.get('status') != 'queued':
                m.update(remote)
            m['remote_status'], m['remote_error'] = 'connected', None
            m['remote_settled'] = poll.get('settled') is True
            if 'external_activity' in poll:
                m['external_activity'] = poll['external_activity']
            # Mirror appended bytes at this Lab's own offsets, which are committed with the manifest;
            # truncating drops a replayed tail after an interrupted sync.
            for key, mirror, chunk in (('remote_offset', path.with_suffix('.stream.jsonl'), poll['stream']),
                                       ('remote_actions_offset', rd/'actions.jsonl', poll.get('actions')),
                                       ('remote_records_offset', rd/'conversation.jsonl', poll.get('records'))):
                if chunk is None:
                    continue
                content = base64.b64decode(chunk)
                with mirror.open('r+b' if mirror.exists() else 'w+b') as f:
                    f.seek(int(m.get(key, 0)))
                    f.write(content)
                    f.truncate()
                m[key] = int(m.get(key, 0)) + len(content)
            for rel, content in poll.get('study_files', {}).items():
                if rel not in outputs:
                    continue
                dest = (lab.hub / rel).resolve()
                if not dest.is_relative_to((lab.hub / 'studies' / m['subject']).resolve()):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(base64.b64decode(content))
            for req in poll['requests']:
                cid = labfiles.safe_id(req.get('id')) if isinstance(req, dict) else None
                if not cid:
                    continue  # No id this Lab can name a receipt by; an honest worker never sends one.
                receipt = rd / 'controller-receipts' / (cid + '.json')
                if receipt.exists():
                    response = json.loads(receipt.read_text(encoding='utf-8'))
                else:
                    try:
                        response = _request(lab, m, req)
                    except ValueError as error:
                        response = {'code': 1, 'text': str(error)}
                    labfiles.write_json(receipt, response)
                call(lab.hub, m['target'], 'response', run_id=m['run_id'], id=cid, response=response)
            for item in (rd / 'inbox').glob('*.json'):
                message = json.loads(item.read_text(encoding='utf-8'))
                if isinstance(message.get('text'), str):
                    message['text'] = rewrite(lab, m, message['text'])
                call(lab.hub, m['target'], 'command', run_id=m['run_id'], id=item.stem,
                     item=message)
                m['remote_settled'] = False
                item.unlink()  # Worker durably accepted it; remote live delivery has its own receipt.
            if (rd / 'stop').exists():
                attempt = int(m.get('attempt', 0)) + (m.get('status') in ('starting', 'resuming'))
                call(lab.hub, m['target'], 'command', run_id=m['run_id'], id='stop-' + str(attempt),
                     item={'kind': 'stop', 'attempt': attempt})
                m['remote_settled'] = False
            labfiles.write_json(path, m)
        except (RemoteError, OSError) as error:
            m['remote_status'], m['remote_error'] = 'disconnected', str(error)
            labfiles.write_json(path, m)


def file_states(hub, slug, files):
    return call(hub, slug, 'files', files=list(files))
