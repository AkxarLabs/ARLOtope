"""Provider discovery and connections for existing agent harnesses. No second agent loop."""
from contextlib import contextmanager
import base64
import http.client
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
from urllib.parse import quote

_cache = None
_lock = threading.RLock()
MAJOR = ('openai', 'anthropic', 'google', 'openrouter', 'xai', 'deepseek', 'mistral', 'groq')


def choices():
    names=('OpenAI','Anthropic','Google','OpenRouter','xAI','DeepSeek','Mistral','Groq')
    return [{'id':pid,'name':name,'backends':[{'openai':'codex','anthropic':'claude'}[pid],'opencode']
             if pid in ('openai','anthropic') else ['opencode']} for pid,name in zip(MAJOR,names)]


def view(provider=None,backend=None,refresh=False):
    if not provider and not backend:return {'ok':True,'choices':choices()}
    backend=backend or {'openai':'codex','anthropic':'claude'}.get(provider,'opencode')
    if backend=='opencode':return {**catalog(refresh),'backend':'opencode'}
    import native_providers
    if provider not in native_providers.NATIVE or native_providers.NATIVE[provider][0]!=backend:
        raise ValueError('Choose a harness that supports this provider.')
    return native_providers.catalog(provider)


def connect(action,provider,value=None,backend=None):
    backend=backend or {'openai':'codex','anthropic':'claude'}.get(provider,'opencode')
    if backend=='opencode':return {**key(action,provider,value),'backend':'opencode'}
    import native_providers
    if provider not in native_providers.NATIVE or native_providers.NATIVE[provider][0]!=backend:
        raise ValueError('Choose a harness that supports this provider.')
    return native_providers.key(action,provider,value)


@contextmanager
def _server():
    from executor.procs import NO_WINDOW, kill_tree, popen
    cli = shutil.which('opencode')
    if not cli:
        raise ValueError('Install OpenCode to use API providers, then retry: https://opencode.ai/docs/')
    password = secrets.token_urlsafe(24)
    env = {**os.environ, 'OPENCODE_SERVER_PASSWORD': password, 'OPENCODE_SERVER_USERNAME': 'opencode',
           'OPENCODE_DISABLE_AUTOUPDATE': '1'}
    process = popen([cli, 'serve', '--hostname', '127.0.0.1', '--port', '0'],
        cwd=Path.home(), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, **NO_WINDOW)
    lines = queue.Queue(maxsize=64)
    def drain():
        for line in process.stdout:
            try: lines.put_nowait(line)
            except queue.Full: pass
    reader=threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 30
        port = None
        while time.monotonic() < deadline:
            try: line = lines.get(timeout=.2)
            except queue.Empty:
                if process.poll() is not None: break
                continue
            match = re.search(r'http://127\.0\.0\.1:(\d+)', line)
            if match:
                port = int(match[1]); break
        if not port:
            raise ValueError('OpenCode did not start. Check its installation and configuration, then retry.')
        auth = 'Basic ' + base64.b64encode(('opencode:'+password).encode()).decode()
        def request(method, path, body=None):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=60)
            try:
                conn.request(method, path, None if body is None else json.dumps(body),
                             {'Authorization': auth, 'Content-Type': 'application/json'})
                response = conn.getresponse()
                raw = response.read()
                if response.status >= 400:
                    raise ValueError('OpenCode refused the provider operation. Check the provider and retry.')
                return json.loads(raw)
            finally: conn.close()
        yield request
    except (OSError, http.client.HTTPException, json.JSONDecodeError):
        raise ValueError('Could not reach OpenCode. Check its installation and retry.') from None
    finally:
        if process.poll() is None:
            kill_tree(process.pid)
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        reader.join(timeout=1)
        process.stdout.close()


def catalog(refresh=False):
    global _cache
    with _lock:
        if not refresh and _cache and time.monotonic()-_cache[0] < 60:
            return _cache[1]
        if refresh:
            from executor.procs import NO_WINDOW, kill_tree, popen
            cli = shutil.which('opencode')
            if not cli:
                raise ValueError('Install OpenCode to use API providers: https://opencode.ai/docs/')
            process = None
            try:
                process = popen([cli, 'models', '--refresh'], cwd=Path.home(),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **NO_WINDOW)
                result = process.wait(timeout=60)
            except (OSError, subprocess.TimeoutExpired):
                raise ValueError('Model refresh did not finish. Retry, or keep using a saved model.') from None
            finally:
                if process is not None and process.poll() is None:
                    kill_tree(process.pid)
                    process.wait(timeout=5)
            if result:
                raise ValueError('Model refresh failed. Retry, or keep using a saved model.')
        with _server() as request:
            data = request('GET', '/provider')
            active = {p['id']:p for p in request('GET','/config/providers').get('providers',[])}
        connected = set(data.get('connected') or [])
        providers = []
        for item in data.get('all') or []:
            source = active.get(item['id'], {'models':{}}) if item['id'] in connected else item
            models = [{'id': key, 'name': value.get('name') or key,
                       'tools': (value.get('capabilities') or {}).get('toolcall')}
                      for key,value in (source.get('models') or {}).items()]
            providers.append({'id': item['id'], 'name': item.get('name') or item['id'],
                              'configured': item['id'] in connected, 'models': models})
        providers.sort(key=lambda p:(MAJOR.index(p['id']) if p['id'] in MAJOR else len(MAJOR),p['name']))
        # Return only public metadata, never the native provider options or credentials.
        value = {'ok': True, 'installed': True, 'source': 'OpenCode / Models.dev',
                 'refreshed_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'providers': providers}
        _cache = time.monotonic(), value
        return value


def key(action, provider, value=None):
    global _cache
    if not isinstance(provider,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}',provider) or '..' in provider:
        raise ValueError('Choose a provider ID from the catalog.')
    if action not in ('connect','disconnect'):
        raise ValueError('Choose connect or disconnect.')
    if action == 'connect' and (not isinstance(value,str) or not value.strip() or len(value)>16384 or any(c in value for c in '\r\n\0')):
        raise ValueError('Enter an API key without line breaks.')
    with _lock, _server() as request:
        request('PUT' if action=='connect' else 'DELETE', '/auth/'+quote(provider,safe=''),
                {'type':'api','key':value.strip()} if action=='connect' else None)
        _cache = None
    return {'ok':True,'provider':provider,'configured':action=='connect'}
