"""Evidence APIs distinguish absent records from unreadable records, then recover."""
import http.cookiejar
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

from conftest import REPO, load


def test_preview_head_checks_access_without_downloading(hub, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'tools'))
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    server = load('dashboard/serve')
    monkeypatch.setattr(server.ctx, 'HUB', hub.root)
    monkeypatch.setattr(server.ctx, 'LAB', hub.lab)
    image = hub.lab/'preview.svg'
    image.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"/>')
    route = '/api/libfile?scope=lab&rel=preview.svg'
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with server.LabServer(('127.0.0.1', 0), server.Handler) as listener:
        thread = threading.Thread(target=listener.serve_forever, daemon=True);thread.start()
        base = 'http://127.0.0.1:'+str(listener.server_port)
        head = lambda path, **kw: urllib.request.Request(base+path, method='HEAD', **kw)
        try:
            with pytest.raises(urllib.error.HTTPError) as error:
                client.open(head(route))
            assert error.value.code == 403
            assert error.value.read() == b''
            client.open(base+'/?session=1').read()
            original = Path.open
            class HeaderOnly:
                def __init__(self, source): self.source = source
                def __enter__(self): return self
                def __exit__(self, *args): self.source.close()
                def read(self, count):
                    assert count == 1  # Even a large PDF must not be downloaded for a check.
                    return self.source.read(count)
                def fileno(self): return self.source.fileno()
            def checked(target, *args, **kwargs):
                source = original(target, *args, **kwargs)
                return HeaderOnly(source) if target == image else source
            with monkeypatch.context() as patch:
                patch.setattr(Path, 'open', checked)
                response = client.open(head(route))
                assert response.status == 200 and response.read() == b''
                assert int(response.headers['Content-Length']) == image.stat().st_size
                assert response.headers['Content-Security-Policy'] == 'sandbox allow-scripts'
            def denied(target, *args, **kwargs):
                if target == image: raise PermissionError('denied preview')
                return original(target, *args, **kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(Path, 'open', denied)
                with pytest.raises(urllib.error.HTTPError) as error:
                    client.open(head(route))
                assert error.value.code == 404
                assert error.value.read() == b''
            assert client.open(head(route)).status == 200
            for path, headers, expected in [(route, {'Origin': 'https://elsewhere.example'}, 403),
                                           ('/api/libfile?scope=lab&rel=../preview.svg', {}, 404),
                                           ('/api/events', {}, 405)]:
                with pytest.raises(urllib.error.HTTPError) as error:
                    client.open(head(path, headers=headers))
                assert error.value.code == expected
        finally:
            listener.shutdown();thread.join(5)


@pytest.mark.parametrize('kind', ['log', 'files', 'actions'])
def test_evidence_read_denial_returns_an_error_not_empty_data(hub, monkeypatch, kind):
    monkeypatch.syspath_prepend(str(REPO/'tools'))
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    server = load('dashboard/serve')
    monkeypatch.setattr(server.ctx, 'HUB', hub.root)
    monkeypatch.setattr(server.ctx, 'LAB', hub.lab)
    config = yaml.safe_load((hub.lab/'config.yaml').read_text())
    config['agents'] = {'programmatic': {'enabled': True, 'backends': {'claude': {
        'command': [sys.executable, str(REPO/'tests/fake_claude.py')]}}}}
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(config), encoding='utf-8')
    lab = server.executor.Lab(hub.root)
    run = server.executor.enqueue(lab, server.executor.RunSpec('ask', prompt='Fixture only'))
    path = server.executor.find_run(lab, run['run_id'])[2]
    rd = path.parent/(run['run_id']+'.d');rd.mkdir(exist_ok=True)
    source = {'log': rd/'supervisor.log', 'actions': rd/'actions.jsonl',
              'files': path.parent/run['stream']}[kind]
    route = '/api/run/'+kind+'?run_id='+run['run_id']
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with server.LabServer(('127.0.0.1', 0), server.Handler) as listener:
        thread = threading.Thread(target=listener.serve_forever, daemon=True);thread.start()
        base = 'http://127.0.0.1:'+str(listener.server_port)
        try:
            client.open(base+'/?session=1').read()
            empty = json.load(client.open(base+route))
            assert empty['ok']
            original = Path.open
            def denied(target, *args, **kwargs):
                if target == source:
                    raise PermissionError('denied fixture evidence')
                return original(target, *args, **kwargs)
            with monkeypatch.context() as patch:
                patch.setattr(Path, 'open', denied)
                with pytest.raises(urllib.error.HTTPError) as error:
                    client.open(base+route)
                assert error.value.code == 500
                assert 'denied fixture evidence' in json.load(error.value)['error']
                if kind == 'actions':
                    assert server.executor.actions.read(rd) == []  # Existing best-effort callers stay unchanged.
            recovered = json.load(client.open(base+route))
            assert recovered == empty
        finally:
            listener.shutdown();thread.join(5)


@pytest.mark.parametrize('expired', [False, True])
def test_remote_preview_preserves_headers_and_head_size(hub, monkeypatch, expired):
    from types import SimpleNamespace
    monkeypatch.syspath_prepend(str(REPO/'tools'))
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    server = load('dashboard/serve')
    headers = {'Content-Type': 'text/html', 'Content-Length': '32768',
               'Content-Security-Policy': 'sandbox allow-scripts', 'X-Content-Type-Options': 'nosniff'}
    calls, refreshes = [], []
    class Connection:
        def request(self, method, path, **kw):
            assert method == 'HEAD' and path == '/api/artifact/file?id=example'
            assert kw['headers']['Cookie'] == 'test-session'
            calls.append(method)
        def getresponse(self):
            return SimpleNamespace(status=403 if expired and len(calls) == 1 else 200, getheader=headers.get, read=lambda: b'')
        def close(self): pass
    monkeypatch.setattr(server.http.client, 'HTTPConnection', lambda *a, **kw: Connection())
    monkeypatch.setattr(server.ctx, 'REMOTE', SimpleNamespace(lport=1234, cookie='test-session', refresh_cookie=lambda: refreshes.append(True)))
    handler = object.__new__(server.Handler)
    handler.headers = {}
    handler.path = '/api/artifact/file?id=example'
    handler.command = 'HEAD'
    handler._local_only = lambda: True
    handler._has_session = lambda: True
    sent = []
    handler._send = lambda *args: sent.append(args)
    handler.do_HEAD()
    status, body, ctype, forwarded = sent[0]
    assert status == 200 and body == b'' and ctype == 'text/html'
    assert forwarded == {k: headers[k] for k in ('Content-Length', 'Content-Security-Policy', 'X-Content-Type-Options')}
    assert len(calls) == (2 if expired else 1)
    assert len(refreshes) == int(expired)
