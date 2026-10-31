"""Small project execution endpoint. Bundled with the existing executor, no dashboard or research kernel."""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from loopback_http import LoopbackHTTPServer

PROTOCOL = 1
MAX_BODY = 8 * 1024 * 1024


def user_id():
    import getpass
    return str(os.getuid()) if hasattr(os, 'getuid') else getpass.getuser()


def session_file(port):
    return Path(os.environ.get('ARLOTOPE_HOME') or Path.home() / '.arlotope') / 'workers' / f'session-{port}.json'


def private_json(path, value):
    """Never expose credentials between file creation and rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    with os.fdopen(os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'w', encoding='utf-8') as stream:
        json.dump(value, stream)
    temp.replace(path)


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + secrets.token_hex(4) + '.tmp')
    temp.write_text(json.dumps(value), encoding='utf-8')
    temp.replace(path)


def safe_id(value):
    if not isinstance(value, str) or not value or len(value) > 120 or '..' in value or not all(c.isalnum() or c in '-_.' for c in value):
        raise ValueError('Invalid identifier.')
    return value


class Worker:
    def __init__(self, runtime=None):
        self.runtime = str(runtime or Path(sys.argv[0]).resolve())
        self.lock = threading.RLock()
        self.terminals = {}

    def root(self, data, claim=False):
        root = Path(data['path']).expanduser()
        if not root.is_absolute() or not root.is_dir():
            raise ValueError('Choose an existing absolute project folder.')
        root = root.resolve()
        owner, slug = safe_id(data['owner']), safe_id(data['study'])
        marker = root / '.arlotope' / 'project.json'
        with self.lock:
            if not marker.exists() and claim:
                if (root / 'lab/config.yaml').is_file():
                    raise ValueError('This folder is a Lab. Connect that Lab instead of attaching it as a project.')
                control = root / 'control.yaml'
                if control.is_file():
                    import yaml
                    config = yaml.safe_load(control.read_text(encoding='utf-8')) or {}
                    old_hub = Path(config.get('hub_path') or '')
                    if old_hub.is_absolute() and (old_hub / 'lab/config.yaml').is_file():
                        raise ValueError('This project is attached to an existing Lab. Connect that Lab instead.')
            if claim:
                from project_identity import register
                register(root, owner, slug, data.get('lab_id'), data.get('title'))
            elif marker.exists():
                current = json.loads(marker.read_text(encoding='utf-8'))
                if current.get('owner') != owner or current.get('study') != slug:
                    raise ValueError(f'Project "{root}" belongs to another Lab or study '
                                     f'(study: {current.get("study")}, execution owner: {current.get("owner")}). Open its Lab instead.')
            else:
                raise ValueError('Attach the project to this Lab first.')
        return root, root / '.bus' / 'arlotope' / owner

    def info(self, data):
        from executor import backends
        config = data.get('backends') or {}
        clis = {}
        for name in backends.BACKENDS:
            argv = backends.resolve_cli(name, config.get(name))
            auth = backends.cli_auth(argv, ttl=0, backend=name) if argv else None
            clis[name] = {'found': bool(argv), 'command': argv, 'logged_in': auth.get('logged_in') if auth else None}
        # Registrations only: no recursive filesystem scan.
        labs = []
        registrations = Path.home() / '.arlotope' / 'labs.json'
        if registrations.is_file():
            try:
                labs = json.loads(registrations.read_text(encoding='utf-8')).get('labs', [])
            except (ValueError, OSError):
                pass
        from project_identity import discover
        return {'protocol': PROTOCOL, 'platform': sys.platform, 'python': sys.executable,
                'git': shutil.which('git'), 'npm': shutil.which('npm'), 'clis': clis, 'labs': labs, 'projects':discover(), 'runtime': self.runtime}

    def call(self, method, data):
        if method == 'providers':
            import provider_access
            return (provider_access.view(data.get('provider'),data.get('backend'),data.get('refresh') is True) if data.get('action')=='catalog'
                    else provider_access.connect(data.get('action'),data.get('provider'),data.get('key'),data.get('backend')))
        if method == 'frameworks':
            from frameworks import installed
            return {'frameworks': installed(data['definitions'], data.get('project')), 'machine': 'remote'}
        if method == 'framework-receipt':
            from frameworks import completion
            return completion(data['definition'], data['project'], data['study'], data['phase'])
        if method == 'framework-activity':
            from framework_activity import read
            return read(**data)
        if method == 'browse':
            from project_files import browse
            return browse(data.get('path'), data.get('hidden') is True)
        if method == 'projects':
            from project_identity import discover
            return discover(data.get('root'), max(0,min(int(data.get('depth',2)),8)))
        if method == 'info':
            return self.info(data)
        if method == 'github':
            import github_access as github
            action = data.get('action')
            if action == 'status':
                return github.status()
            if action == 'repositories':
                return github.repositories()
            if action == 'lookup':
                import re
                name = data.get('repository', '')
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', name) or name.split('/')[1] in ('.', '..'):
                    raise ValueError('Use an exact owner/repository.')
                if data.get('authenticated'):
                    value = github.repository(name)
                else:
                    import urllib.request
                    with urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/'+name, headers={'User-Agent':'ARLOtope-Lab'}), timeout=12) as response:
                        value = json.loads(response.read(1_000_001))
                return {'name':value['full_name'],'url':'https://github.com/'+value['full_name'],
                        'description':str(value.get('description') or '')[:500],'language':value.get('language'),
                        'archived':bool(value.get('archived')),'private':bool(value.get('private'))}
            raise ValueError('Choose connection status, repositories or lookup.')
        if method == 'clone':
            # An explicit attach action authorizes a fixed-host download using this machine's sign-in.
            import re
            repo = data['repository']
            if not re.fullmatch(r'[A-Za-z0-9-]+/[A-Za-z0-9_.-]+', repo) or repo.split('/')[1] in ('.', '..'):
                raise ValueError('Use a public owner/repository.')
            dest = Path(data['path']).expanduser()
            if not dest.is_absolute() or dest.exists():
                raise ValueError('Choose a new absolute clone destination.')
            from github_access import clone_argv
            argv = clone_argv(repo, dest) if data.get('github_auth') is True else ['git', 'clone', '--', 'https://github.com/' + repo + '.git', str(dest)]
            result = subprocess.run(argv,
                env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'Never', 'GH_PROMPT_DISABLED': '1'},
                capture_output=True, text=True, timeout=180)
            if result.returncode:
                raise ValueError('Could not clone the repository. Check GitHub access on this machine, or attach an existing checkout.')
            return {'path': str(dest.resolve())}
        if method.startswith('term/'):
            return self.terminal(method, data)
        root, bus = self.root(data, claim=method == 'attach')
        if method == 'attach':
            return {'path': str(root), 'bus': str(bus)}
        if method == 'skills':
            import skill_resources
            sources = {name: {rel: base64.b64decode(value, validate=True) for rel, value in content.items()}
                       for name, content in data['sources'].items()}
            records = skill_resources.install(root, sources)
            skill_resources.record_project(root, data['workflow'], data['study'], records)
            return {'records': records, 'files': {name: {rel: base64.b64encode(value).decode()
                for rel, value in skill_resources.files(root / record['path']).items()} for name, record in records.items()}}
        if method == 'knowledge':
            import knowledge
            folder=knowledge.project_folder(root)
            action=data.get('action','list');args=data.get('record') or {}
            if action=='list':
                result=knowledge.listing(folder,**{k:data[k] for k in ('query','kind','tag','offset','limit') if k in data})
                for row in result['rows']:row['rel']=(folder/row['file']).relative_to(root).as_posix()
                return result
            if action=='get':
                result=knowledge.get(folder,data['id'])
                return {**result,'scope':'project','slug':data['study'],'rel':(folder/result['file']).relative_to(root).as_posix()}
            if action=='attachment':
                file=knowledge.attachment(folder,data['id'])
                offset=max(0,int(data.get('offset',0)))
                with file.open('rb') as stream:
                    stream.seek(offset);content=stream.read(1024*1024)
                return {'name':file.name,'size':file.stat().st_size,'data':base64.b64encode(content).decode()}
            if action=='add':return knowledge.create(folder,studies=[data['study']],**args)
            if action=='update':return knowledge.update(folder,data['id'],**args)
            raise ValueError('Unknown knowledge action.')
        if method == 'files':
            out = {}
            for rel in data.get('files', []):
                path = (root / rel).resolve()
                if not path.is_relative_to(root):
                    raise ValueError('Choose a file inside the project.')
                if data.get('digest') and path.is_file():
                    import hashlib
                    out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
                else:
                    out[rel] = [path.stat().st_mtime_ns, path.stat().st_size] if path.is_file() else None
            return out
        if method == 'documents':
            out = []
            extensions = {'.md','.txt','.yaml','.yml','.json','.csv','.tex','.bib','.markdown'}
            for base, dirs, files in os.walk(root):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in ('node_modules','__pycache__','runs'))[:40]
                if len(Path(base).relative_to(root).parts) >= 3:
                    dirs[:] = []
                for name in sorted(files):
                    path = Path(base) / name
                    if path.suffix.lower() in extensions and not path.is_symlink():
                        out.append({'rel':path.relative_to(root).as_posix(),'title':name,'mtime':int(path.stat().st_mtime)})
                        if len(out) >= 120:
                            return out
            return out
        if method == 'read':
            path = (root / data['file']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError('Choose a project file.')
            if path.stat().st_size > MAX_BODY // 2:
                raise ValueError('This file is too large to preview. Copy it explicitly over SSH.')
            return {'data': base64.b64encode(path.read_bytes()).decode(), 'name': path.name}
        rid = safe_id(data['run_id'])
        adir, rd = bus / 'agents', bus / 'agents' / (rid + '.d')
        manifest = adir / (rid + '.json')
        if method == 'material':
            name = data.get('name')
            if not isinstance(name, str) or name in ('', '.', '..') or '/' in name or '\\' in name or ':' in name:
                raise ValueError('Invalid material filename.')
            encoded = data.get('data')
            if not isinstance(encoded, str) or len(encoded) > 7 * 1024 * 1024:
                raise ValueError('Material is too large.')
            content = base64.b64decode(encoded, validate=True)
            if len(content) > 5 * 1024 * 1024:
                raise ValueError('Material is too large.')
            destination = rd / 'instructions/studies' / data['study'] / 'materials' / name
            if not destination.resolve().is_relative_to(rd.resolve()):
                raise ValueError('Invalid material path.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with self.lock:
                temp = destination.with_name(destination.name + '.tmp')
                temp.write_bytes(content)
                temp.replace(destination)
            return {'stored':True}
        if method == 'dispatch':
            from executor.procs import DETACHED, excl_lock
            with self.lock, excl_lock(rd / 'dispatch.lock'):
                # One accepted dispatch per run/attempt, including a lost HTTP response.
                generation = int(data['manifest'].get('attempt', 0))
                receipt = rd / ('dispatch-' + str(generation) + '.json')
                if receipt.exists():
                    from executor.procs import is_locked, pid_alive
                    old = json.loads(receipt.read_text(encoding='utf-8'))
                    current = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
                    if is_locked(rd / 'lock') or pid_alive(old.get('supervisor_pid')) or current.get('status') not in ('starting', 'resuming'):
                        return old
                rd.mkdir(parents=True, exist_ok=True)
                supplied = data['manifest']
                stop = rd / 'stop'
                if supplied.get('status') == 'resuming' and supplied.get('resume') and stop.is_file():
                    try:
                        requested = json.loads(stop.read_text(encoding='utf-8'))
                    except ValueError:
                        requested = None  # Older workers wrote an unversioned marker.
                    stopped_attempt = requested.get('attempt') if isinstance(requested, dict) else None
                    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {}
                    if (type(stopped_attempt) is int and stopped_attempt <= generation or
                            stopped_attempt is None and previous.get('status') in ('completed', 'failed', 'timeout', 'killed')):
                        stop.unlink()
                m = dict(supplied, cwd=str(root), remote_owner=data['owner'], worker_runtime=self.runtime)
                for name in ('prompt', 'preamble'):
                    (rd / (name + '.md')).write_text(data[name], encoding='utf-8')
                for rel, text in data.get('instructions', {}).items():
                    dest = (rd / 'instructions' / rel).resolve()
                    if not dest.is_relative_to((rd / 'instructions').resolve()):
                        raise ValueError('Invalid instruction path.')
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(text, encoding='utf-8')
                for rel, encoded in data.get('resources', {}).items():
                    dest = (rd / 'skills' / rel).resolve()
                    if not dest.is_relative_to((rd / 'skills').resolve()):
                        raise ValueError('Invalid skill resource path.')
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(base64.b64decode(encoded, validate=True))
                atomic(rd / 'config.json', data['config'])
                atomic(manifest, m)
                result = {'ok': True, 'accepted': True, 'run_id': rid, 'attempt': generation}
                atomic(receipt, result)
                log = (rd / 'supervisor.log').open('ab')
                proc = subprocess.Popen([sys.executable, self.runtime, 'run', '--path', str(root),
                    '--owner', data['owner'], '--run', rid], stdin=subprocess.DEVNULL, stdout=log,
                    stderr=subprocess.STDOUT, close_fds=True, **DETACHED)
                log.close()
                result['supervisor_pid'] = proc.pid
                atomic(receipt, result)
                return result
        if not manifest.is_file():
            return {'found': False}
        if method == 'poll':
            from executor.manifest import now
            from executor.procs import is_locked
            with self.lock:
                queue_late_input(manifest, rd)
                receipts = list(rd.glob('dispatch-*.json'))
                receipt = max(receipts, key=lambda p: p.stat().st_mtime) if receipts else None
                if receipt and time.time() - receipt.stat().st_mtime > 30 and not is_locked(rd / 'lock'):
                    # The supervisor saves its final/parked state before releasing the lock.
                    # Read after the liveness check, so its just-finished result wins.
                    current = json.loads(manifest.read_text(encoding='utf-8'))
                    parked = current.get('status') == 'waiting_input' and current.get('pid') is None
                    if current.get('status') in ('starting', 'resuming', 'running', 'waiting_input') and not parked:
                        current.update(status='failed', reason='Remote supervisor stopped unexpectedly.', finished=now())
                        atomic(manifest, current)
            requests = [json.loads(p.read_text(encoding='utf-8')) for p in (rd / 'controller').glob('*.request.json')
                        if not p.with_name(p.name.replace('.request.json', '.response.json')).exists()]
            offset = max(0, int(data.get('offset', 0)))
            stream = adir / (rid + '.stream.jsonl')
            content = b''
            if stream.is_file():
                with stream.open('rb') as f:
                    f.seek(offset)
                    content = f.read(512 * 1024)
            result = {'found': True, 'manifest': json.loads(manifest.read_text(encoding='utf-8')),
                    'requests': requests[:50], 'stream': base64.b64encode(content).decode(),
                    'offset': offset + len(content)}
            artifacts = {}
            for rel in data.get('study_files', []):
                path = (rd / 'instructions' / rel).resolve()
                allowed = (rd / 'instructions/studies' / data['study']).resolve()
                if path.is_relative_to(allowed) and path.is_file() and path.stat().st_size <= MAX_BODY // 8:
                    artifacts[rel] = base64.b64encode(path.read_bytes()).decode()
            result['study_files'] = artifacts
            caught_up = True
            for name, filename in (('actions','actions.jsonl'), ('records','conversation.jsonl')):
                activity = rd/filename
                position = max(0, int(data.get(name+'_offset', 0)))
                chunk = b''
                if activity.is_file():
                    with activity.open('rb') as source:
                        source.seek(position)
                        chunk = source.read(512*1024)
                result[name] = base64.b64encode(chunk).decode()
                result[name+'_offset'] = position+len(chunk)
                caught_up &= not activity.is_file() or result[name+'_offset'] >= activity.stat().st_size
            from executor.manifest import TERMINAL
            result['settled'] = (result['manifest'].get('status') in TERMINAL and not is_locked(rd/'lock')
                and not requests and not any((rd/'inbox').glob('*.json'))
                and (not stream.is_file() or result['offset'] >= stream.stat().st_size)
                and caught_up)
            if data.get('framework_activity'):
                from framework_activity import read
                try:
                    result['external_activity'] = read(**data['framework_activity'])
                except (OSError, ValueError, TypeError) as error:
                    result['external_activity'] = {'error':str(error)}
            return result
        if method == 'response':
            cid = safe_id(data['id'])
            atomic(rd / 'controller' / (cid + '.response.json'), data['response'])
            return {'ok': True}
        if method == 'command':
            from executor import live
            cid = safe_id(data['id'])
            receipt = rd / 'commands' / (cid + '.json')
            with self.lock:
                if receipt.exists():
                    return json.loads(receipt.read_text(encoding='utf-8'))
                if data['item']['kind'] == 'stop':
                    current = json.loads(manifest.read_text(encoding='utf-8'))
                    active_attempt = int(current.get('attempt', 0)) + (current.get('status') in ('starting', 'resuming'))
                    requested_attempt = data['item'].get('attempt', active_attempt)
                    if type(requested_attempt) is not int or requested_attempt < 0:
                        raise ValueError('Choose a valid run attempt to stop.')
                    if requested_attempt >= active_attempt:
                        from executor.procs import is_locked
                        if (requested_attempt == active_attempt and current.get('status') == 'waiting_input'
                                and current.get('pid') is None and not is_locked(rd / 'lock')):
                            from executor.manifest import now
                            current.update(status='killed', reason='stopped while waiting for the PI', finished=now(),
                                           pending_question=None, pending_questions=[])
                            atomic(manifest, current)
                        else:
                            atomic(rd / 'stop', {'attempt': requested_attempt})
                else:
                    live.post(rd, dict(data['item'], request_id_external=cid))
                result = {'ok': True, 'queued': True, 'id': cid}
                atomic(receipt, result)
                return result
        raise ValueError('Unknown worker operation.')

    def terminal(self, method, data):
        from interactive_terminal import Session
        from terminal import install_command, login_argv
        from executor.backends import resolve_cli
        if method == 'term/open':
            backend, purpose = data['backend'], data['purpose']
            argv = resolve_cli(backend, data.get('config') or {}) if backend != 'github' else None
            if purpose == 'login':
                if backend == 'github':
                    from github_access import login_argv as github_login
                    argv = github_login()
                else:
                    argv = login_argv(backend, argv or [])
            elif purpose == 'install':
                command = install_command(backend)
                argv = ['bash', '-lc', command] if command else None
            else:
                raise ValueError('Choose install or login.')
            if not argv:
                raise ValueError('Configure this agent command and sign in manually.')
            with self.lock:
                session, _ = Session.open(self.terminals, argv, str(Path.home()), purpose,
                                          request_id=data.get('request_id'))
            return {'ok': True, 'id': session.id, 'pty': os.name == 'posix', 'title': purpose.title() + ' · ' + backend}
        session = self.terminals.get(data.get('id'))
        if not session:
            raise ValueError('Unknown terminal.')
        if method == 'term/read':
            return session.read(int(data.get('offset', 0)))
        if method == 'term/write':
            session.write(data['data'])
        elif method == 'term/resize':
            session.resize(int(data['cols']), int(data['rows']))
        elif method == 'term/close':
            session.close()
        else:
            raise ValueError('Unknown terminal operation.')
        return {'ok': True}


def queue_late_input(manifest, rd):
    """Preserve messages arriving after supervisor exit for the controller's next admission."""
    from executor.procs import RunLock
    from executor.supervise import _late_text
    lock = RunLock(rd / 'lock')
    if not lock.try_acquire():
        return
    try:
        current = json.loads(manifest.read_text(encoding='utf-8'))
        if current.get('status') not in ('completed', 'waiting_input', 'queued'):
            return
        items = [(path, json.loads(path.read_text(encoding='utf-8')))
                 for path in sorted((rd / 'inbox').glob('*.json'))]
        items = [(path, item) for path, item in items if item.get('kind') in ('message', 'answer')]
        seen = set(current.get('remote_late_inputs', []))
        fresh = [(path, item) for path, item in items if path.name not in seen]
        if fresh:
            previous = (current.get('resume') or {}).get('text', '') if current.get('status') == 'queued' else ''
            current.update(status='queued', reason='PI message after the session ended',
                resume={'mode': 'reply', 'text': '\n\n'.join(filter(None,
                    [previous, *(_late_text(item) for _, item in fresh)]))},
                pending_question=None, post_processed=False, not_before=None,
                remote_late_inputs=sorted(seen | {path.name for path, _ in fresh}))
            # Commit before acknowledging inbox files; a retry must not duplicate the prompt.
            atomic(manifest, current)
        for path, _ in items:
            path.replace(path.with_suffix('.delivered'))
    finally:
        lock.release()


def run(project, owner, rid):
    from lab_profile import WorkerLab
    from executor.procs import RunLock
    from executor.supervise import _attempt
    root = Path(project)
    bus = root / '.bus' / 'arlotope' / safe_id(owner)
    adir, rd = bus / 'agents', bus / 'agents' / (safe_id(rid) + '.d')
    lock = RunLock(rd / 'lock')
    deadline = time.monotonic() + 10
    while not lock.try_acquire():
        if time.monotonic() >= deadline:
            return 0
        time.sleep(.1)
    try:
        manifest = adir / (rid + '.json')
        m = json.loads(manifest.read_text(encoding='utf-8'))
        if m['status'] not in ('starting', 'resuming'):
            return 0
        cfg = json.loads((rd / 'config.json').read_text(encoding='utf-8'))
        return _attempt(WorkerLab(root, cfg, owner), root, adir, manifest, m, rd)
    finally:
        lock.release()


def serve(port):
    worker, token = Worker(), secrets.token_urlsafe(32)
    identity = {'app':'arlotope-worker','protocol':PROTOCOL,'pid':os.getpid(),
                'build':Path(worker.runtime).stem,'uid':user_id()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def send(self, data, code=200, headers=None):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        def local(self):
            from urllib.parse import urlsplit
            host = self.headers.get('Host', '').split(':')[0]
            origin = self.headers.get('Origin')
            return host in ('127.0.0.1', 'localhost') and (not origin or urlsplit(origin).hostname in ('127.0.0.1', 'localhost'))
        def do_GET(self):
            if not self.local():
                return self.send({'error': 'Local requests only.'}, 403)
            if self.path == '/api/ping':
                return self.send(identity)
            if self.path == '/?session=1':
                return self.send({'error': 'Obtain the worker session over SSH.'}, 403)
            return self.send({'error': 'Not found.'}, 404)
        def do_POST(self):
            if self.path != '/rpc':
                return self.send({'error': 'Not found.'}, 404)
            if not self.local() or self.headers.get('Cookie') != 'worker=' + token:
                return self.send({'error': 'No worker session.'}, 403)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 0 or size > MAX_BODY:
                    return self.send({'error': 'Request too large.'}, 413)
                body = json.loads(self.rfile.read(size))
                return self.send({'ok': True, 'result': worker.call(body['method'], body.get('data') or {})})
            except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
                return self.send({'error': str(error)}, 400)
    server = LoopbackHTTPServer(('127.0.0.1', port), Handler)
    credentials = session_file(server.server_port)
    private_json(credentials, {**identity, 'port':server.server_port,'cookie':'worker='+token,'arlotope_worker_session':True})
    try:
        server.serve_forever()
    finally:
        server.server_close()
        credentials.unlink(missing_ok=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'framework':
        from frameworks import main as framework_main
        return framework_main(sys.argv[2:])
    if len(sys.argv)>1 and sys.argv[1]=='knowledge':
        from knowledge import main as knowledge_main
        return knowledge_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == 'artifact':
        from artifact import main as artifact_main
        return artifact_main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == 'control':
        from project_control import control
        return control(sys.argv[2:])
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('serve', 'run'))
    p.add_argument('--port', type=int, default=0)
    p.add_argument('--background', action='store_true')
    p.add_argument('--path')
    p.add_argument('--owner')
    p.add_argument('--run')
    a = p.parse_args()
    if a.command == 'run':
        return run(a.path, a.owner, a.run)
    if a.background:
        from executor.procs import DETACHED
        import http.client
        try:
            c = http.client.HTTPConnection('127.0.0.1', a.port, timeout=2)
            c.request('GET', '/api/ping')
            result = json.loads(c.getresponse().read())
            if result.get('app') != 'arlotope-worker' or result.get('protocol') != PROTOCOL:
                raise ValueError('The worker port belongs to an incompatible service.')
            if result.get('build') != Path(sys.argv[0]).stem:
                raise ValueError('A different worker build uses this port. Reconnect from the updated Lab.')
            if result.get('uid') != user_id():
                raise ValueError('The worker port belongs to another account. Choose another connection.')
        except OSError:
            log = Path.home() / '.arlotope/worker.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open('ab') as stream:
                child = subprocess.Popen([sys.executable, str(Path(sys.argv[0]).resolve()), 'serve', '--port', str(a.port)],
                    stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, close_fds=True, **DETACHED)
            for _ in range(80):
                try:
                    c = http.client.HTTPConnection('127.0.0.1', a.port, timeout=1)
                    c.request('GET', '/api/ping')
                    result = json.loads(c.getresponse().read())
                    if result.get('app') == 'arlotope-worker':
                        break
                except OSError:
                    if child.poll() is not None:
                        raise ValueError('The worker did not start; inspect ~/.arlotope/worker.log.')
                time.sleep(.1)
            else:
                raise ValueError('The worker did not start.')
        session = json.loads(session_file(a.port).read_text(encoding='utf-8'))
        if any(session.get(k) != result.get(k) for k in ('pid','uid','build')) or session.get('uid') != user_id():
            raise ValueError('The worker session does not match this account/build. Reconnect the machine.')
        print(json.dumps({**session, 'ok':True}))
        return 0
    serve(a.port)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
