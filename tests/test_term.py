"""dashboard/term.py — in-browser terminal sessions (fixed commands; a PTY on POSIX, pipes on Windows)."""

from __future__ import annotations

import base64
import json
import os
import sys
import time

import pytest

from conftest import REPO, load

FAKE = REPO / "tests" / "fake_claude.py"


@pytest.fixture
def m(hub, monkeypatch):
    (hub.lab / "config.yaml").write_text(
        "agents:\n  programmatic:\n    enabled: true\n    backends:\n      claude:\n"
        f"        command: {json.dumps([sys.executable, str(FAKE)])}\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    mod = load("dashboard/serve")
    for tgt in (mod.ctx,):
        monkeypatch.setattr(tgt, "HUB", hub.root)
        monkeypatch.setattr(tgt, "LAB", hub.lab)
    return mod


def _drain(term, sid, want, timeout=20):
    out, off, t0 = b"", 0, time.time()
    while time.time() - t0 < timeout:
        r, _ = term.read({"id": sid, "offset": off})
        out += base64.b64decode(r["data"])
        off = r["offset"]
        if want in out or r["exited"]:
            return out, r
        time.sleep(0.05)
    return out, r


def test_session_round_trip(m):
    s = m.term.Session([sys.executable, "-u", "-c", "import sys; print('ready'); l=sys.stdin.readline(); print('got', l.strip())"],
                       str(REPO), "test")
    m.term.SESSIONS[s.id] = s
    out, _ = _drain(m.term, s.id, b"ready")
    assert b"ready" in out
    m.term.write({"id": s.id, "data": "hello\r"})
    out, r = _drain(m.term, s.id, b"got hello")
    assert b"got hello" in out
    out, r = _drain(m.term, s.id, b"[finished")
    assert r["exited"]


@pytest.mark.skipif(os.name != "posix", reason="a real PTY is POSIX-only")
def test_pty_is_a_tty_and_resizes(m):
    s = m.term.Session([sys.executable, "-u", "-c", "import os,sys,time; print('tty', os.isatty(0)); time.sleep(0.5); print(os.get_terminal_size())"],
                       str(REPO), "test", cols=91, rows=17)
    m.term.SESSIONS[s.id] = s
    out, _ = _drain(m.term, s.id, b"columns")
    assert b"tty True" in out and b"columns=91" in out


def test_only_fixed_purposes(m, hub):
    assert m.term.open_session({"purpose": "exec", "backend": "claude"})[1] == 400
    assert m.term.open_session({"purpose": "login", "backend": "rm -rf"})[1] == 400
    out, code = m.term.open_session({"purpose": "login", "backend": "claude"})
    assert code == 200, out
    assert "fake_claude.py" in out["command"] and "auth login" in out["command"]
    m.term.close({"id": out["id"]})
    pi = [json.loads(x) for x in (hub.lab / ".bus" / "pi-actions.jsonl").read_text(encoding="utf-8").splitlines()]
    assert pi[-1]["action"] == "term.login"
    assert m.term.read({"id": "nope"})[1] == 404


def test_read_retry_replays_absolute_bytes_and_reports_clipped_output(monkeypatch):
    import threading
    monkeypatch.syspath_prepend(str(REPO / 'tools'))
    import interactive_terminal as terminal
    monkeypatch.setattr(terminal, 'MAX_BUF', 8)
    s = object.__new__(terminal.Session)
    s.lock, s.buf, s.base = threading.Lock(), bytearray(), 0
    s.exited, s.code = False, None
    s._append(b'abcdefgh')
    first = s.read(3)
    assert s.read(3) == first and base64.b64decode(first['data']) == b'defgh'
    s._append(b'ijkl')
    clipped = s.read(0)
    assert clipped['skipped'] == 4 and clipped['offset'] == 12
    assert base64.b64decode(clipped['data']) == b'efghijkl'
    assert s.read(clipped['offset'])['data'] == ''


def test_creation_retry_reuses_process_on_dashboard_and_worker(m, monkeypatch):
    from project_worker import Worker
    created = []
    def init(self, argv, cwd, purpose, cols=100, rows=28):
        created.append(argv)
        self.id, self.argv, self.cwd, self.purpose = 'request-session', argv, cwd, purpose
        self.exited = False
    monkeypatch.setattr(m.term.Session, '__init__', init)
    monkeypatch.setattr(m.term, 'SESSIONS', {})
    monkeypatch.setattr(m.term, 'command_for', lambda *_: (['fake-agent', 'login'], None))
    body = {'purpose': 'login', 'backend': 'claude', 'request_id': 'a' * 32}
    first, code = m.term.open_session(body)
    assert code == 200
    assert m.term.open_session(body)[0]['id'] == first['id'] and len(created) == 1
    assert m.term.open_session({**body, 'request_id': 'bad'})[1] == 400
    import terminal
    import executor.backends
    monkeypatch.setattr(executor.backends, 'resolve_cli', lambda *_: ['fake-agent'])
    monkeypatch.setattr(terminal, 'login_argv', lambda *_: ['fake-agent', 'login'])
    worker = Worker()
    original = worker.terminal('term/open', body)
    assert worker.terminal('term/open', body)['id'] == original['id'] and len(created) == 2
    with pytest.raises(ValueError, match='another command'):
        worker.terminal('term/open', {**body, 'purpose': 'install'})
