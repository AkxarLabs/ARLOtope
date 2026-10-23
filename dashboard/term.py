"""In-browser terminal sessions for the dashboard — for machines with no desktop (a remote box, a server
you reached over SSH) where "open a terminal window" has nowhere to go.

A session runs ONE fixed command chosen by purpose (tools/terminal.py's table: a CLI's own login, an
installer, or a login shell in the lab folder), never a command line from the page. On POSIX it runs under
a real PTY, so interactive logins and TUIs (opencode's provider picker, `claude auth login`'s paste-the-code
prompt) behave exactly as in a terminal; on Windows it falls back to pipes (the dashboard prefers a real
console window there). Output is kept in a bounded buffer and polled by the page (the server is stdlib;
no websockets):

    POST /api/term/open   {purpose, backend?, cols?, rows?}  → {id}
    GET  /api/term/read?id=&offset=                          → {data (base64), offset, exited, code}
    POST /api/term/write  {id, data}      POST /api/term/resize {id, cols, rows}      POST /api/term/close {id}
"""

from __future__ import annotations

import os
import shlex
import sys
import threading
import time

import ctx  # noqa: E402
import sources  # noqa: E402
import attention  # noqa: E402

MAX_BUF = 1 << 20        # keep the last 1 MB of output per session
MAX_SESSIONS = 8
REAP_AFTER_S = 600       # forget a finished session this long after it ends


def has_pty() -> bool:
    return os.name == "posix"


def desktop() -> bool:
    """Can this machine open a terminal WINDOW the PI will see? (Not over SSH, and with a display.)"""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


from interactive_terminal import Session  # shared with the execution-only worker


SESSIONS: dict[str, Session] = {}
_LOCK = threading.Lock()


def _reap() -> None:
    now = time.time()
    for k, s in list(SESSIONS.items()):
        if s.exited and s.ended and now - s.ended > REAP_AFTER_S:
            SESSIONS.pop(k, None)


def command_for(purpose: str, backend: str | None) -> tuple[list[str] | None, str | None]:
    """The fixed argv for a purpose — (argv, error)."""
    terminal = ctx.tool("terminal")
    if purpose == 'login' and backend == 'github':
        from github_access import login_argv
        argv = login_argv()
        return (argv, None) if argv else (None, 'Install GitHub CLI, then retry. Public repository URLs work without it.')
    if purpose == "shell":
        if os.name == "posix":
            return [os.environ.get("SHELL") or "/bin/bash", "-l"], None
        return [os.environ.get("COMSPEC") or "cmd.exe"], None
    if backend not in (sources.executor.backends.BACKENDS if sources.executor else ("claude", "codex", "opencode")):
        return None, "unknown backend"
    if purpose == "install":
        cmd = terminal.install_command(backend)
        if not cmd:
            return None, f"no install command known for {backend}"
        return (["bash", "-lc", cmd] if os.name == "posix" else ["cmd.exe", "/c", cmd]), None
    if purpose == "login":
        if sources.executor is None:
            return None, "the executor is not available"
        prog = (ctx.config().get("agents") or {}).get("programmatic") or {}
        cli = sources.executor.backends.resolve_cli(backend, (prog.get("backends") or {}).get(backend) or {})
        argv = terminal.login_argv(backend, cli or [])
        return (argv, None) if argv else (None, f"{backend} is not installed yet; install it first")
    return None, "unknown purpose"


def open_session(body: dict) -> tuple[dict, int]:
    purpose, backend = str(body.get("purpose") or ""), body.get("backend")
    argv, err = command_for(purpose, backend)
    if err:
        return {"error": err}, 400
    with _LOCK:
        _reap()
        try:
            cols, rows = int(body.get("cols") or 100), int(body.get("rows") or 28)
        except (TypeError, ValueError):
            cols, rows = 100, 28
        try:
            s, created = Session.open(SESSIONS, argv, str(ctx.HUB), purpose, cols=cols, rows=rows,
                                      request_id=body.get('request_id'), limit=MAX_SESSIONS)
        except ValueError as e:
            return {"error": str(e)}, 400
        except OSError as e:
            return {"error": f"could not start it: {e}"}, 500
    if created:
        ctx.pi_log({"action": f"term.{purpose}", "backend": backend, "argv": argv[:4]})
    attention.recheck_executor(cli=True)
    title = {"login": f"Sign in to {backend}", "install": f"Install {backend}", "shell": "Terminal"}[purpose]
    return {"ok": True, "id": s.id, "title": title, "pty": has_pty(), "command": " ".join(shlex.quote(a) for a in argv)}, 200


def _get(body_or_q: dict) -> Session | None:
    return SESSIONS.get(str(body_or_q.get("id") or ""))


def read(q: dict) -> tuple[dict, int]:
    s = _get(q)
    if not s:
        return {"error": "no such terminal"}, 404
    try:
        off = int(q.get("offset") or 0)
    except ValueError:
        off = 0
    return s.read(off), 200


def write(body: dict) -> tuple[dict, int]:
    s = _get(body)
    if not s:
        return {"error": "no such terminal"}, 404
    data = body.get("data")
    if not isinstance(data, str) or len(data) > 65536:
        return {"error": "data must be text"}, 400
    try:
        s.write(data)
    except OSError as e:
        return {"error": str(e)}, 400
    return {"ok": True}, 200


def resize(body: dict) -> tuple[dict, int]:
    s = _get(body)
    if not s:
        return {"error": "no such terminal"}, 404
    try:
        s.resize(int(body.get("cols")), int(body.get("rows")))
    except (TypeError, ValueError):
        return {"error": "cols/rows"}, 400
    return {"ok": True}, 200


def close(body: dict) -> tuple[dict, int]:
    s = _get(body)
    if not s:
        return {"ok": True}, 200
    s.close()
    return {"ok": True}, 200
