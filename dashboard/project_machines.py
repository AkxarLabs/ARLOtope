"""Machine setup for attached projects. Reuses Lab's SSH tunnel supervision and terminal UI."""
import json
import hashlib
import shlex
import subprocess
import sys
import time
import threading
import secrets

import ctx
import machines
import remote_projects as R

CONNS = {}
CONNS_LOCK = threading.Lock()


class ProjectConn(machines.Conn):
    def __init__(self, machine):
        super().__init__(machine, '@project-runner')
        self.build, self.blob = R.bundle()
        self._setup_lock = threading.Lock()
        if not machine.get('runner_id'):
            machine['runner_id'] = secrets.token_hex(16)
            machines._put(machine)
        # A new immutable runner can serve existing spools without stopping old runs.
        self.rport = 20000 + int(hashlib.sha256((machine['runner_id'] + ':' + self.build).encode()).hexdigest(), 16) % 29000
        self.pidfile = machines._home() / 'workers' / (machine['id'] + '.pid')
        self.sessionfile = self.pidfile.with_suffix('.session.json')
        self.remote_uid = None
        self.remote_pid = None

    def package(self):
        digest, blob = self.build, self.blob
        archive = machines._home() / 'workers' / ('worker-' + digest + '.pyz')
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(blob)
        target = '~/.arlotope/workers/' + digest + '.pyz'
        return archive, target

    def _start_cmd(self):
        _, target = self.package()
        # Cached executable includes PyYAML's pure-Python implementation; no remote pip/uv needed.
        return machines.PATH_PREFIX + '; python3 ' + machines._rpath(target) + ' serve --background --port ' + str(self.rport)

    def bootstrap(self):
        archive, target = self.package()
        digest = target.rsplit('/', 1)[1].removesuffix('.pyz')
        code = ('import sys,pathlib,hashlib,secrets; p=pathlib.Path.home()/".arlotope/workers"/' + repr(digest + '.pyz')
                + '; b=sys.stdin.buffer.read(); '
                + 'assert hashlib.sha256(b).hexdigest().startswith(' + repr(digest) + '); '
                + 'p.parent.mkdir(parents=True,exist_ok=True); t=p.with_name(p.name+"."+secrets.token_hex(6)+".tmp"); t.write_bytes(b); t.replace(p)')
        return archive, 'python3 -c ' + shlex.quote(code) + ' && ' + self._start_cmd()

    def connect(self, interactive=False):
        with self._setup_lock:
            return self._connect(interactive)

    def _connect(self, interactive):
        self.want = True
        if self.state == 'waiting' and self.want:
            return {'ok': True, 'state': 'waiting'}
        if self.alive():
            self.state, self.want = 'connected', True
            return {'ok': True, 'state': self.state}
        if interactive:
            return self._connect_window()
        self.state, self.error = 'starting', None
        archive, script = self.bootstrap()
        for attempt in range(3):
            try:
                result = machines._run(self.machine['host'], script, timeout=60, stdin=archive.read_bytes())
            except (OSError, subprocess.SubprocessError) as error:
                result = subprocess.CompletedProcess([], 255, b'', str(error).encode())
            kind, _ = machines._why(result) if result.returncode else (None, None)
            if kind != 'network' or attempt == 2 or not self.want:
                break
            self.state = 'reconnecting'
            time.sleep(1 + attempt * 2)
        if not self.want:
            return {'error':'Connection cancelled.'}
        if result.returncode:
            kind, self.error = machines._why(result)
            self.state = 'auth' if kind in machines.INTERACTIVE else 'error'
            return {'error': self.error, 'needs_interactive': kind in machines.INTERACTIVE}
        if not self._session(result.stdout):
            self.state, self.error = 'error', 'The runner did not return an account session. Check Python 3.10+ on this machine.'
            return {'error':self.error}
        return super().connect(False)

    def _session(self, content):
        for line in reversed(content.splitlines()):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if (isinstance(value, dict) and value.get('arlotope_worker_session') and value.get('build') == self.build
                    and value.get('port') == self.rport and isinstance(value.get('cookie'), str)
                    and isinstance(value.get('pid'), int) and value['pid'] > 0 and value.get('uid') is not None):
                self.cookie, self.remote_uid, self.remote_pid = value['cookie'], value['uid'], value['pid']
                return True
        return False

    def refresh_cookie(self):
        if self.cookie:
            return
        try:
            if self._session(self.sessionfile.read_bytes()):
                self.sessionfile.unlink(missing_ok=True)
        except OSError:
            pass

    def _restart_remote(self):
        try:
            result = machines._run(self.machine['host'], self._start_cmd(), timeout=180)
        except (OSError, subprocess.SubprocessError) as error:
            self.error = str(error)
            return False
        if result.returncode:
            kind, self.error = machines._why(result)
            if kind in machines.INTERACTIVE:
                self.state = 'auth'
            return False
        return self._session(result.stdout) and self._wait(30)

    def _await_window(self):
        super()._await_window()
        self.save()

    def _stop_window(self):
        super()._stop_window()
        self.sessionfile.unlink(missing_ok=True)

    def _connect_window(self):
        archive, bootstrap = self.bootstrap()
        self.want, self.window, self.state, self.error = True, True, 'waiting', None
        self.login_deadline = time.time() + machines.SIGN_IN_SECONDS
        self.pidfile.unlink(missing_ok=True)
        self.sessionfile.unlink(missing_ok=True)
        argv = [*machines.ssh_cmd(), *machines._opts(False), '-T', '-o', 'ExitOnForwardFailure=yes',
                '-L', f'{self.lport}:127.0.0.1:{self.rport}', self.machine['host'],
                'bash -lc ' + shlex.quote(bootstrap + " && echo 'Connected. Keep this window open.' && while true; do sleep 3600; done")]
        spec = archive.parent / (self.machine['id'] + '.install.json')
        spec.write_text(json.dumps({'archive': str(archive), 'argv': argv, 'pidfile': str(self.pidfile),
                                    'sessionfile':str(self.sessionfile)}), encoding='utf-8')
        result = ctx.tool('terminal').open_terminal([sys.executable, str(ctx.ROOT / 'tools/ssh_worker_install.py'), str(spec)],
                                                   title='Connect ' + self.machine['name'])
        if not result.get('ok'):
            self.state, self.error = 'error', result.get('error')
            return result
        import threading
        threading.Thread(target=self._await_window, daemon=True).start()
        return {'ok': True, 'state': 'waiting', 'note': 'Sign in in the SSH window.'}

    def alive(self, refresh=False):
        import http.client
        try:
            c = http.client.HTTPConnection('127.0.0.1', self.lport, timeout=3)
            c.request('GET', '/api/ping')
            info = json.loads(c.getresponse().read())
            c.close()
            if refresh or not self.cookie:
                self.refresh_cookie()
            if (info.get('app') != 'arlotope-worker' or info.get('protocol') != 1 or info.get('build') != self.build
                    or info.get('uid') != self.remote_uid or info.get('pid') != self.remote_pid):
                return False
            if self.cookie:
                self.error = None
                self.save()
            return bool(self.cookie)
        except (OSError, ValueError, http.client.HTTPException):
            return False

    def save(self):
        if not self.want:
            return
        m = machines._get(self.machine['id'])
        if m:
            m['worker'] = {'port': self.lport, 'cookie': self.cookie, 'state': self.state,
                           'build': self.build, 'updated': time.time()}
            machines._put(m)

    def disconnect(self, stop_remote=False):
        super().disconnect(False)
        if self.pidfile.exists():
            from executor.procs import kill_tree
            try:
                kill_tree(int(self.pidfile.read_text()))
            except (OSError, ValueError):
                pass
            self.pidfile.unlink(missing_ok=True)
        self.sessionfile.unlink(missing_ok=True)
        self.cookie, self.remote_uid, self.remote_pid = None, None, None
        m = machines._get(self.machine['id'])
        if m:
            m.pop('worker', None)
            machines._put(m)


def view(q=None):
    out = []
    for m in machines._load():
        conn = CONNS.get(m['id'])
        out.append({k: m.get(k) for k in ('id', 'name', 'host', 'facts', 'agent_config', 'default_agent', 'labs')}
                   | {'state': conn.state if conn else 'idle', 'error': conn.error if conn else None,
                      'login_deadline': conn.login_deadline if conn else None,
                      'worker_ready': bool(conn and conn.state == 'connected')})
    return {'machines': out}, 200


def _project_rows(rows):
    from project_identity import lab_identity
    ident = lab_identity(ctx.HUB)
    return [{**r, 'ours': r.get('owner') == ident['execution_owner'] or r.get('lab_id') == ident['lab_id']}
            for r in rows]


def projects(body):
    from project_identity import discover
    mid = str(body.get('machine') or '')
    try:
        rows = R.rpc(mid, 'projects', {'root':body.get('root'), 'depth':body.get('depth',2)}) if mid and mid!='local' else discover(body.get('root'), max(0,min(int(body.get('depth',2)),8)))
        return {'ok':True,'projects':_project_rows(rows)}, 200
    except (ValueError, OSError) as error:
        return {'error':str(error)}, 400


def browse(body):
    from project_files import browse as list_folders
    mid = str(body.get('machine') or '')
    try:
        data = {'path':body.get('path'), 'hidden':body.get('hidden') is True}
        result = R.rpc(mid, 'browse', data) if mid and mid != 'local' else list_folders(data['path'], data['hidden'])
        return {'ok':True, **result}, 200
    except (ValueError, OSError) as error:
        return {'error':str(error)}, 400


def connect(body):
    m = machines._get(str(body.get('id') or ''))
    if not m:
        return {'error': 'Choose a machine.'}, 404
    if body.get('confirm') is not True:
        return {'error': 'Confirm setup of the project runner on this machine.'}, 400
    with CONNS_LOCK:
        c = CONNS.get(m['id'])
        if c is not None and c.state in ('auth', 'error'):
            c.disconnect()
            c = None
        if c is None:
            c = CONNS[m['id']] = ProjectConn(m)
    result = c.connect(bool(body.get('interactive')))
    if result.get('state') == 'connected':
        c.save()
    return result, 200


def disconnect(body):
    with CONNS_LOCK:
        c = CONNS.pop(str(body.get('id')), None)
        if c:
            c.disconnect()
    return {'ok': True}, 200


def inspect(body):
    mid = str(body.get('id') or '')
    m = machines._get(mid)
    if not m:
        return {'error': 'Choose a machine.'}, 404
    if body.get('default_agent') is not None and body['default_agent'] not in ('claude', 'codex', 'opencode', 'acp'):
        return {'error': 'Choose a known agent.'}, 400
    if body.get('agent_config') is not None:
        config = body['agent_config']
        if not isinstance(config, dict) or any(k not in ('claude', 'codex', 'opencode', 'acp') for k in config):
            return {'error': 'Choose a known agent.'}, 400
        for value in config.values():
            if not isinstance(value, dict) or not isinstance(value.get('command'), list) or not all(isinstance(v, str) and v for v in value['command']):
                return {'error': 'Commands must be JSON argument arrays.'}, 400
        m['agent_config'] = config
        m['default_agent'] = body.get('default_agent') or m.get('default_agent') or 'claude'
        machines._put(m)
    if body.get('default_agent') is not None:
        m['default_agent'] = body['default_agent']
        machines._put(m)
    try:
        result = R.rpc(mid, 'info', {'backends': m.get('agent_config') or {}})
        result['projects'] = _project_rows(result.get('projects') or [])
        existing = {x['path'] for x in m.get('labs', [])}
        for lab in result.get('labs') or []:
            if isinstance(lab, dict) and lab.get('path') not in existing and machines._clean_path(lab.get('path')):
                m.setdefault('labs', []).append({'path': lab['path'], 'name': lab.get('name')})
                existing.add(lab['path'])
        machines._put(m)
        return {'ok': True, **result, 'agent_config': m.get('agent_config') or {},
                'default_agent': m.get('default_agent') or 'claude'}, 200
    except R.RemoteError as error:
        return {'error': str(error)}, 400


def terminal(body):
    try:
        m = R.machine(body['machine'])
        return R.rpc(m['id'], 'term/' + body['operation'], {**body,
                     'config': (m.get('agent_config') or {}).get(body.get('backend'), {})}), 200
    except (R.RemoteError, KeyError) as error:
        return {'error': str(error)}, 400


import atexit
atexit.register(lambda: [c.disconnect() for c in list(CONNS.values())])
