"""ACP v1 client-side files and terminals, executed beside the agent, never on the controller by proxy."""
import json
import shlex
import subprocess
import threading
import uuid
from pathlib import Path

from ..procs import NEW_GROUP, kill_tree


class ClientTools:
    def __init__(self, workdir, env, guard=None, python=None):
        self.workdir, self.env = Path(workdir), env
        self.guard, self.python = guard, python
        self.terminals = {}
        self.lock = threading.RLock()

    def check(self, tool, value):
        if not self.guard:
            return
        result = subprocess.run([self.python, str(self.guard)], input=json.dumps({
            'tool_name': tool, 'tool_input': value, 'cwd': str(self.workdir)}),
            text=True, capture_output=True, env=self.env, timeout=20)
        if result.returncode == 2:
            raise PermissionError(result.stderr.strip() or 'The lab guard refused this operation.')

    def path(self, value):
        p = Path(value)
        if not p.is_absolute():
            raise ValueError('ACP file paths must be absolute.')
        return p

    def call(self, method, p):
        if method == 'fs/read_text_file':
            text = self.path(p['path']).read_text(encoding='utf-8')
            start, limit = p.get('line', 1), p.get('limit')
            if type(start) is not int or start < 1 or (limit is not None and (type(limit) is not int or limit < 0)):
                raise ValueError('line starts at 1; limit must be nonnegative.')
            return {'content': ''.join(text.splitlines(keepends=True)[start - 1:None if limit is None else start - 1 + limit])}
        if method == 'fs/write_text_file':
            path = self.path(p['path'])
            self.check('Write', {'file_path': str(path), 'content': p['content']})
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(p['content'], encoding='utf-8')
            return {}
        if method == 'terminal/create':
            argv = [p['command'], *p.get('args', [])]
            if not all(isinstance(v, str) and '\0' not in v for v in argv):
                raise ValueError('A command and text arguments are required.')
            self.check('Bash', {'command': shlex.join(argv)})
            env = dict(self.env)
            env.update({v['name']: v['value'] for v in p.get('env', [])})
            limit = p.get('outputByteLimit', 1024 * 1024)
            if not isinstance(limit, int) or limit < 0:
                raise ValueError('outputByteLimit must be nonnegative.')
            proc = subprocess.Popen(argv, cwd=self.path(p['cwd']) if p.get('cwd') else self.workdir, env=env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **NEW_GROUP)
            tid = uuid.uuid4().hex
            record = {'proc': proc, 'output': bytearray(), 'truncated': False, 'done': threading.Event()}
            with self.lock:
                self.terminals[tid] = record
            def drain():
                try:
                    while data := proc.stdout.read1(4096):
                        with self.lock:
                            record['output'].extend(data)
                            if len(record['output']) > limit:
                                record['truncated'] = True
                                record['output'][:] = record['output'][-limit:] if limit else b''
                    proc.wait()
                finally:
                    record['done'].set()
            threading.Thread(target=drain, daemon=True).start()
            return {'terminalId': tid}
        if method.startswith('terminal/'):
            with self.lock:
                t = self.terminals.get(p.get('terminalId'))
            if not t:
                raise ValueError('Unknown terminal.')
            proc = t['proc']
            if method in ('terminal/kill', 'terminal/release'):
                if proc.poll() is None:
                    kill_tree(proc.pid)
                if method == 'terminal/release':
                    t['done'].wait(10)
                    with self.lock:
                        self.terminals.pop(p['terminalId'], None)
                return {}
            if method == 'terminal/wait_for_exit':
                t['done'].wait()
            # A process can exit before its last pipe bytes have been drained. Do not
            # report completion until terminal/output can return the complete output.
            code = proc.poll() if t['done'].is_set() else None
            status = {'exitCode': code if code is None or code >= 0 else None,
                      'signal': str(-code) if code is not None and code < 0 else None}
            if method == 'terminal/wait_for_exit':
                return status
            if method == 'terminal/output':
                with self.lock:
                    output = bytes(t['output']).decode('utf-8', 'ignore' if t['truncated'] else 'replace')
                return {'output': output, 'truncated': t['truncated'], **({'exitStatus': status} if code is not None else {})}
        raise NotImplementedError(method)

    def close(self):
        with self.lock:
            ids = list(self.terminals)
        for tid in ids:
            self.call('terminal/release', {'terminalId': tid})
