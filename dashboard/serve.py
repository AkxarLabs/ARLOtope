"""ARLOtope dashboard: the HTTP server. Optional, local-only.

    uv run --with pyyaml python dashboard/serve.py [--port 8787] [--hub <another lab's hub root>]
    (or just: uv run --with pyyaml python arlo.py — starts this and opens the browser)

A stdlib HTTP server for the no-build single-page app in static/. This module is the server and its
wiring only: every JSON endpoint is one line in GET_ROUTES / POST_ROUTES (below), pointing at the
module that owns that area —

    sources       reads the lab (the snapshot the page renders; nothing there writes)
    ctx           the lab being shown (or the remote one proxied), the PI's audit log, shared helpers
    runops        headless runs (tools/executor): launch, answer, reply, stop, tail; the scheduler thread
    decisions     the PI's checkpoint decisions, moving a study, its workflow and swaps, flags (the kernel's journal)
    panels        the panel cabinet: instruments, their data, collector approvals
    campaign      campaigns: sign, control, preflight
    settings      lab/config.yaml (one writer), keys, notifications, documents, the System page, setup
    instructions  one study's own instructions, and agents' proposals to change the lab's
    compose       Compose: the lab's definition, edited as a draft and published (with undo)
    bus · library · labs · machines · fleet · term   notes to agents · the library · labs on this
                  computer · remote machines · the across-labs overview · in-browser terminals

  WRITES are PI actions only: explicit (a confirm), validated, and logged to lab/.bus/pi-actions.jsonl.
  A checkpoint is approved only by an explicit press-and-hold (a record in lab/journal.jsonl). Runs start only
  through the executor (the unmodified agent CLI, as the logged-in user, in a detached supervisor that
  outlives this server) and only when the PI has enabled programmatic launching; every checkpoint and hard
  rule binds a launched run exactly as in a session, and every run carries the signature guard.
  PROTECTION: 127.0.0.1 only; Host/Origin checks (DNS rebinding); a per-server SameSite=Strict session
  cookie on every /api call; JSON bodies only (no simple cross-site form POSTs). Delete dashboard/ and
  the lab is unchanged (the executor has its own CLI: tools/executor_cli.py).
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.client
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
# The 3D lab frame runs room code an agent wrote, with the whole lab state posted into it: it keeps its opaque
# sandbox and may load its own scripts, styles, fonts and images, but may not talk to any network or post a form.
LAB_VIEW_CSP = ("sandbox allow-scripts; default-src 'none'; script-src 'self' 'unsafe-inline' blob:; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'none'; form-action 'none'; frame-src 'none'; "
                "object-src 'none'; base-uri 'none'")
sys.path.insert(0, str(HERE))

# The dashboard's modules — each one area of the product; all share ctx (the lab being shown), none
# imports this one.
import ctx  # noqa: E402
import labfiles  # noqa: E402
from loopback_http import LoopbackHTTPServer  # noqa: E402
import starter  # noqa: E402
import sources  # noqa: E402
import term  # noqa: E402
import machines  # noqa: E402
import bus  # noqa: E402
import runops  # noqa: E402
import labs  # noqa: E402
import decisions  # noqa: E402
import panels_api  # noqa: E402
import campaign  # noqa: E402
import settings  # noqa: E402
import instructions  # noqa: E402
import compose  # noqa: E402
import assistant  # noqa: E402
import room_design  # noqa: E402
import fleet  # noqa: E402
import library  # noqa: E402
import artifacts  # noqa: E402
import review  # noqa: E402
import ticker  # noqa: E402
import labtools  # noqa: E402
import keys  # noqa: E402
import system  # noqa: E402
import providers  # noqa: E402
import api_schema  # noqa: E402

executor = sources.executor   # tools/executor, or None (the dashboard then stays observe-and-sign)
TOKEN = secrets.token_urlsafe(24)    # this server process's session secret (the cookie below)
VERSION = "2.0"

# The lab this dashboard shows: a local hub (ctx.HUB), or a lab on another machine reached through an SSH
# tunnel (ctx.REMOTE, a machines.Conn) — then every /api/* call except the local-only ones is proxied.
LOCAL_ONLY_PREFIXES = ("/api/ping", "/api/labs", "/api/machines", "/api/project-machines", "/api/server/stop", "/api/fleet")
LOCAL_ONLY_EXACT = {"/api/terminal"}


def _is_local_route(route: str) -> bool:
    return route in LOCAL_ONLY_EXACT or route.startswith(LOCAL_ONLY_PREFIXES)


# A remote lab's dashboard is another machine's: what it answers is data, never code on this origin.
def _inject_remote(raw: bytes, conn) -> bytes:
    """A remote snapshot, re-encoded here as JSON and tagged with where it came from; anything else is null."""
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return b"null"
    if isinstance(obj, dict):
        obj["remote"] = conn.info()
    return json.dumps(obj).encode("utf-8")


def _remote_headers(ctype: str) -> dict:
    """Whatever the remote claims, the browser must not sniff it, and any page it carries runs in an opaque
    sandbox. PDFs are left unsandboxed: browsers won't render one sandboxed, and it runs no script here."""
    headers = {"X-Content-Type-Options": "nosniff"}
    if ctype.split(";")[0].strip().lower() != "application/pdf":
        headers["Content-Security-Policy"] = "sandbox allow-scripts"
    return headers


# A short shared snapshot cache. ThreadingHTTPServer serves each SSE client on its own thread and each
# re-reads the whole lab; with the TTL under the 1.5 s SSE tick a single client always recomputes fresh
# (never staler than one tick), while N concurrent clients + the index seed share one read instead of N.
_SNAP_LOCK = threading.Lock()
_SNAP_COMPUTE = threading.Lock()


_SNAP_TTL = 1.0


_snap_cache = {"ts": 0.0, "value": None, "sig": None, "version": 0}


def _sig(snap: dict) -> str:
    """A change signature that ignores the wall clock (`now`), so SSE pushes a new snapshot only when
    the lab actually changed — the client stops re-rendering every 1.5 s."""
    import hashlib
    body = {k: v for k, v in snap.items() if k != "now"}
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _snapshot_cached(with_sig: bool = False):
    with _SNAP_COMPUTE:
        while True:
            with _SNAP_LOCK:
                if _snap_cache["value"] is not None and time.time() - _snap_cache["ts"] < _SNAP_TTL:
                    return (_snap_cache["value"], _snap_cache["sig"]) if with_sig else _snap_cache["value"]
                version = _snap_cache['version']
            with labfiles.read_batch():
                snap = sources.snapshot()
                try:
                    snap["lab_info"] = {"name": labs.lab_name(ctx.HUB), "path": str(ctx.HUB), "setup": settings.setup_status(),
                                        "desktop": term.desktop(), "pty": term.has_pty(), "platform": sys.platform}
                except Exception:  # noqa: BLE001
                    snap["lab_info"] = {"name": ctx.HUB.name, "path": str(ctx.HUB)}
            sig = _sig(snap)
            with _SNAP_LOCK:
                if version != _snap_cache['version']:
                    continue  # the Lab switched while this read was in flight
                _snap_cache.update(ts=time.time(), value=snap, sig=sig)
                return (snap, sig) if with_sig else snap


class Handler(BaseHTTPRequestHandler):
    # Demo mode is a debugging/showcase world, NOT a user-facing dashboard feature. It is OFF unless
    # the server is started with `--demo` (or ARLOTOPE_DEMO=1); only then is window.__ARLOTOPE_DEMO__ injected
    # so a `?demo` URL activates the synthetic lab. There is no in-dashboard control to enable it.
    demo = False

    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in {"Content-Length": str(len(body)), "Cache-Control": "no-store", **(headers or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        try:
            if self.command != "HEAD":
                self.wfile.write(body)
        except ConnectionError:
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def _cookie_name(self) -> str:
        return f"arlotope_{self.server.server_address[1]}" if getattr(self, "server", None) else "arlotope"

    def _has_session(self) -> bool:
        """The SameSite=Strict cookie set with the page: a cross-site request never carries it."""
        raw = self.headers.get("Cookie") or ""
        want = self._cookie_name()
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == want and secrets.compare_digest(v, TOKEN):
                return True
        return False

    def _raw_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = 0
        limit = 7 * 1024 * 1024 if self.path.split('?', 1)[0] == '/api/starter/draft' else 1 << 20
        length = max(0, min(length, limit))
        return self.rfile.read(length) if length else b""

    def _body(self) -> dict:
        try:
            return json.loads(self._raw_body() or b"{}")
        except (ValueError, RecursionError) as error:
            raise ValueError("Invalid JSON body: malformed or nested too deeply.") from error

    def _refuse(self, body: dict, code: int):
        """Refuse a POST — after reading its body: closing a socket with unread data resets the
        connection (Windows), and the client may never see the refusal."""
        self._raw_body()
        return self._json(body, code)

    _LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

    def _local_only(self) -> bool:
        """True iff this is a same-origin localhost request. Guards state-changing POSTs (the
        dashboard approves checkpoints) against DNS-rebinding from a malicious page the PI visits:
        a rebound request still carries the attacker's Host header, which is rejected here."""
        host = (self.headers.get("Host") or "").strip()
        if host.startswith("["):            # [::1]:port -> ::1
            host = host.split("]", 1)[0].lstrip("[")
        elif host.count(":") == 1:          # 127.0.0.1:port -> 127.0.0.1
            host = host.rsplit(":", 1)[0]
        if host and host not in self._LOCAL_HOSTS:
            return False
        origin = self.headers.get("Origin")
        if origin == "null":                 # a sandboxed frame / file:// page — never the dashboard
            return False
        if origin:
            from urllib.parse import urlparse
            if (urlparse(origin).hostname or "") not in self._LOCAL_HOSTS:
                return False
        return True

    def do_HEAD(self):
        # Preview checks use the same file authorization/resolution as GET, without a second download.
        if self.path.split("?", 1)[0] not in FILE_ROUTES:
            return self._send(405, b"HEAD is only supported for files", "text/plain")
        return self.do_GET()

    def do_GET(self):
        # The index seed and every /api/* GET carry the full lab snapshot (titles, metrics, directives,
        # the paper). Guard them with the same localhost/same-origin check as the POSTs so a DNS-rebound
        # page the PI visits can't READ the lab (it still carries the attacker's Host header). Static
        # assets (js/css/art) are not sensitive and stay open.
        sensitive = (self.path in ("/",) or self.path.startswith("/index.html")
                     or self.path.startswith("/?") or self.path.startswith("/api/"))
        if sensitive and not self._local_only():
            return self._send(403, b"refused: cross-origin/non-localhost request", "text/plain")
        if self.path == "/" or self.path.startswith("/index.html") or self.path.startswith("/?"):
            return self._serve_index()
        if self.path.startswith("/api/ping"):   # the launcher's "is it up, and which lab?" (no session)
            return self._json({"ok": True, "app": "arlotope", "version": VERSION, "lab": str(ctx.HUB),
                               "name": labs.lab_name(ctx.HUB), "pid": os.getpid()})
        if self.path.split('?',1)[0]=='/api/session':
            return self._send(200,b'{"ok":true}', 'application/json',
                {'Set-Cookie':f'{self._cookie_name()}={TOKEN}; Path=/; HttpOnly; SameSite=Strict'})
        if self.path.startswith("/api/") and not self._has_session():
            return self._json({"error": "no dashboard session; reload the page"}, 403)
        route = self.path.split("?", 1)[0]
        if ctx.REMOTE is not None and self.headers.get('X-Arlotope-Local')!='1' and route.startswith("/api/") and not _is_local_route(route):
            return self._proxy(self.command)

        if route in GET_ROUTES:
            try:
                body, code = GET_ROUTES[route](self._query())
                if route=='/api/schema':
                    body['components']['securitySchemes']['localSession']['name']=self._cookie_name()
            except Exception as e:  # noqa: BLE001
                body, code = {"error": str(e)}, 500
            return self._json(body, code)
        if route == "/api/events":
            return self._serve_sse()
        if route in FILE_ROUTES:
            hit = FILE_ROUTES[route](self._query())
            return self._serve_bytes(*hit) if hit else self._send(404, b"no such file", "text/plain")
        if self.path.startswith("/static/") or self.path.count("/") == 1:
            return self._serve_static(self.path.lstrip("/"))
        self._send(404, b"not found", "text/plain")

    def _query(self) -> dict:
        from urllib.parse import parse_qs, urlparse
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def _serve_bytes(self, f: Path, ctype: str) -> None:
        # a page or a drawing a run wrote is shown, never trusted: HTML and SVG get an opaque origin of their
        # own (a CSP sandbox, even when opened directly), so their scripts can't reach the dashboard's API
        hdrs = {"X-Content-Type-Options": "nosniff"}
        if ctype.split(";")[0].strip() in ("text/html", "image/svg+xml", "application/xhtml+xml", "text/xml"):
            hdrs["Content-Security-Policy"] = "sandbox allow-scripts"
        try:
            if self.command == "HEAD":
                with f.open("rb") as source:
                    source.read(1)  # Check readability as well as existence.
                    size = os.fstat(source.fileno()).st_size
                return self._send(200, b"", ctype, {**hdrs, "Content-Length": str(size)})
            self._send(200, f.read_bytes(), ctype, hdrs)
        except OSError:
            self._send(404, b"unreadable", "text/plain")

    def _proxy(self, method: str):
        """Forward this request to the remote lab's own dashboard through its tunnel."""
        conn = ctx.REMOTE
        route = self.path.split("?", 1)[0]
        raw = None
        if method == "POST":
            raw = self._raw_body()
        streaming = route == "/api/events"
        r = hc = None
        for attempt in (0, 1):
            try:
                hc = http.client.HTTPConnection("127.0.0.1", conn.lport, timeout=None if streaming else 120)
                headers = {"Host": f"127.0.0.1:{conn.lport}", "Cookie": conn.cookie or ""}
                if raw is not None:
                    headers["Content-Type"] = "application/json"
                hc.request(method, self.path, body=raw, headers=headers)
                r = hc.getresponse()
            except (OSError, http.client.HTTPException):
                if conn.state == "connected":
                    conn.state = "reconnecting"
                name = conn.info()["name"]
                return self._json({"error": f"lost the connection to {name}; reconnecting", "remote": conn.info()}, 502)
            if r.status == 403 and attempt == 0:
                body = r.read()
                if method == "HEAD" or b"session" in body:  # HEAD has no error body to inspect.
                    conn.refresh_cookie()
                    continue
                ctype = r.getheader("Content-Type") or "application/json"
                return self._send(403, body, ctype, _remote_headers(ctype))
            break
        ctype = r.getheader("Content-Type") or "application/octet-stream"
        if streaming and r.status == 200:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    line = r.fp.readline()
                    if not line:
                        break
                    if line.startswith(b"data: "):
                        line = b"data: " + _inject_remote(line[6:].strip(), conn) + b"\n"
                    self.wfile.write(line)
                    if line in (b"\n", b"\r\n"):
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass
            finally:
                hc.close()
            return None
        data = r.read()
        hc.close()
        if route == "/api/state" and ctype.startswith("application/json"):
            data = _inject_remote(data, conn)
        headers = _remote_headers(ctype)
        if method == "HEAD" and r.getheader("Content-Length"):
            headers["Content-Length"] = r.getheader("Content-Length")
        return self._send(r.status, data, ctype, headers)

    def _remote_seed(self) -> str:
        conn = ctx.REMOTE
        try:
            hc = http.client.HTTPConnection("127.0.0.1", conn.lport, timeout=30)
            hc.request("GET", "/api/state", headers={"Host": f"127.0.0.1:{conn.lport}", "Cookie": conn.cookie or ""})
            r = hc.getresponse()
            data = r.read()
            if r.status == 403:
                conn.refresh_cookie()
                return "null"
            return _inject_remote(data, conn).decode("utf-8")
        except (OSError, http.client.HTTPException):
            return "null"

    def _serve_index(self) -> None:
        try:
            html = (STATIC / "index.html").read_text(encoding="utf-8")
        except OSError:
            return self._send(500, b"dashboard assets missing (dashboard/static/index.html)", "text/plain")
        try:
            # `</` -> `<\/` so a snapshot string containing "</script>" (an event detail, a registry
            # title, a directive, a worker-trace summary — any of which can carry text an agent copied
            # from an untrusted source) can't break out of this inline <script> and inject live HTML.
            # json.dumps does NOT escape `<` or `/`, so this one replace is the whole XSS defense here.
            seed = ("null" if self._query().get("session") else      # ?session=1: just the session (a tunnel asking)
                    (self._remote_seed() if ctx.REMOTE is not None else json.dumps(_snapshot_cached())).replace("</", "<\\/"))
        except Exception:  # noqa: BLE001
            seed = "null"
        demo = "true" if self.demo else "false"
        html = html.replace(
            "</head>", f"<script>window.__STATE__={seed};window.__ARLOTOPE_DEMO__={demo};</script></head>", 1)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        # the session: HttpOnly (no script reads it), SameSite=Strict (no cross-site request carries it),
        # per port (two dashboards on one machine don't clobber each other)
        self.send_header("Set-Cookie", f"{self._cookie_name()}={TOKEN}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        try:
            self.wfile.write(body)
        except ConnectionError:
            pass

    def _serve_static(self, rel: str) -> None:
        rel = rel.split("?")[0].replace("static/", "", 1)   # only the route prefix, never a nested "static/"
        target = (STATIC / rel).resolve()
        if (STATIC not in target.parents and target != STATIC) or not target.is_file():
            return self._send(404, b"not found", "text/plain")
        ctype = {".html": "text/html", ".css": "text/css", ".js": "application/javascript", ".mjs": "application/javascript",
                 ".svg": "image/svg+xml", ".woff2": "font/woff2", ".woff": "font/woff",
                 ".ttf": "font/ttf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".json": "application/json", ".map": "application/json",
                 ".txt": "text/plain"}.get(target.suffix, "application/octet-stream")
        charset = "; charset=utf-8" if ctype.startswith(("text/", "application/j", "image/svg")) else ""
        body = target.read_bytes()
        headers = {"Access-Control-Allow-Origin": "*"}  # public assets, including modules in opaque frames
        if target.name == "lab-view.html":
            q = self._query()
            if q.get('roomdraft') and q.get('embedded') != '1':
                if not self._local_only():
                    return self._send(403, b"refused: cross-origin/non-localhost request", "text/plain")
                from urllib.parse import urlencode
                return self._send(302, b'', 'text/plain', {'Location': '/?' + urlencode({'roomdraft': q['roomdraft']})})
            body = _with_rooms3d(body.decode("utf-8"), "world3d/rooms/").encode("utf-8")
            headers['Content-Security-Policy'] = LAB_VIEW_CSP
        # Only public assets are cached. Revalidate every load so edits are visible immediately.
        etag = '"' + hashlib.sha256(body).hexdigest() + '"'
        headers.update({'ETag': etag, 'Cache-Control': 'no-cache'})
        previous = getattr(self, 'headers', {}).get('If-None-Match', '')
        if etag in [tag.strip().removeprefix('W/') for tag in previous.split(',')]:
            return self._send(304, b'', f'{ctype}{charset}', {**headers, 'Content-Length': str(len(body))})
        self._send(200, body, f"{ctype}{charset}", headers)

    def _serve_sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = None
        try:
            while True:
                try:
                    snap, sig = _snapshot_cached(with_sig=True)
                    payload = None if sig == last else json.dumps(snap)
                except Exception:  # noqa: BLE001
                    snap, sig, payload = {}, "error", json.dumps({"error": "snapshot failed"})
                if payload is not None:
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    last = sig
                else:   # nothing changed: just move the clock (no re-render on the client)
                    self.wfile.write(f"event: tick\ndata: {json.dumps({'now': snap.get('now')})}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(1.5)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return

    def do_POST(self):
        if not self._local_only():
            return self._refuse({"error": "refused: cross-origin/non-localhost POST"}, 403)
        if not self._has_session():
            return self._refuse({"error": "no dashboard session; reload the page"}, 403)
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            return self._refuse({"error": "requests must be JSON (Content-Type: application/json)"}, 415)
        route = self.path.split("?", 1)[0]
        if ctx.REMOTE is not None and self.headers.get('X-Arlotope-Local')!='1' and not _is_local_route(route):
            return self._proxy("POST")
        try:
            return self._dispatch_post()
        except Exception as e:  # noqa: BLE001 — a handler bug / dirty input must never kill the thread
            return self._json({"error": f"internal error: {e}"}, 500)

    def _dispatch_post(self):
        try:
            body = self._body()
        except ValueError as error:
            return self._json({"error": str(error)}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "body must be a JSON object"}, 400)
        fn = POST_ROUTES.get(self.path.split("?", 1)[0])
        if fn is None:
            return self._send(404, b"not found", "text/plain")
        out, code = fn(body)
        if self.path.split('?', 1)[0] == '/api/starter' and 200 <= code < 300:
            _forget_snapshot()  # Open study must see the study just created, even within the cache TTL.
        return self._json(out, code)


# ── routes: every JSON endpoint, one line each — fn(query) / fn(body) → (body, http code) ───────────
# (/api/events, the paper, figures and library files are streams / files, served in Handler.do_GET;
# the local-only ones are never proxied to a remote lab: LOCAL_ONLY_*)

def _res(out: dict) -> tuple[dict, int]:
    return out, 400 if out.get("error") else 200




GET_ROUTES = {
    '/api/schema': lambda q: (api_schema.describe(GET_ROUTES,POST_ROUTES,FILE_ROUTES,compose.OPS),200),
    '/api/providers': providers.view,
    '/api/knowledge': lambda q: __import__('knowledge_api').list_records(q),
    '/api/agent-settings': lambda q: __import__('agent_settings').view(q),
    '/api/project-machines': lambda q: __import__('project_machines').view(q),
    '/api/room-drafts': room_design.drafts,
    '/api/room-draft': room_design.get,
    '/api/assistant': assistant.view,
    "/api/starter": starter.view,
    '/api/frameworks': starter.frameworks_view,
    "/api/starter/github": starter.github_view,
    '/api/starter/draft': starter.draft_view,
    "/api/state": lambda q: (_snapshot_cached(), 200),
    "/api/run": lambda q: runops.run_detail(q.get("run_id", "")),
    "/api/run/tail": lambda q: runops.run_tail(q.get("run_id", ""), labfiles.pos_int(q.get("offset"), 0, 0)),
    "/api/run/log": lambda q: runops.run_log(q.get("run_id", "")),
    "/api/run/files": runops.run_files,
    "/api/run/actions": runops.run_actions,
    "/api/run/records": runops.run_records,
    "/api/run/file": runops.run_file,
    "/api/executor/health": lambda q: runops.executor_health(fresh=bool(q.get("fresh"))),
    "/api/library": lambda q: (library.lib_tree(), 200),
    "/api/machines": lambda q: machines.list_machines(),
    "/api/labs": lambda q: labs.labs_list(),
    "/api/fleet": lambda q: fleet.fleet(),
    "/api/summary": lambda q: ({"ok": True, **fleet.lab_summary(ctx.HUB)}, 200),
    "/api/checkpoint": decisions.checkpoint_view,
    "/api/study/timeline": decisions.timeline,
    '/api/study/history': decisions.history,
    "/api/panels": panels_api.list_panels,
    "/api/panel": panels_api.get_panel,
    "/api/panel/data": panels_api.panel_data,
    "/api/panel/view": panels_api.panel_view,
    "/api/doc": lambda q: settings.doc_get(q.get("which", "")),
    "/api/workflow/item": instructions.workflow_item,
    "/api/workflow/instructions": instructions.inspect,
    "/api/compose": compose.view,
    '/api/compose/export': compose.export_procedure,
    "/api/compose/file": compose.file_get,
    "/api/artifacts": artifacts.list_artifacts,
    "/api/artifact": artifacts.get,
    "/api/campaign/preflight": campaign.campaign_preflight,
    "/api/workflow/proposal": instructions.workflow_proposal_get,
    "/api/lab/config": lambda q: settings.lab_config_get(),
    "/api/keys": lambda q: keys.keys_status(),
    "/api/notify": lambda q: keys.notify_status(),
    "/api/term/read": term.read,
    "/api/system": system.system_info,
    "/api/figs": lambda q: ({"figures": library.figure_list(q.get("idea", ""))}, 200),
}

# GET routes that answer with a file: fn(query) -> (path, content type) | None (404)
FILE_ROUTES = {
    '/api/knowledge/attachment': lambda q: __import__('knowledge_api').attachment(q),
    "/api/paper": lambda q: _typed(library.paper_pdf(q.get("idea", "")), "application/pdf"),
    "/api/figure": lambda q: _typed(library.figure_file(q.get("idea", ""), q.get("name", ""))),
    "/api/libfile": lambda q: library.lib_file(q.get("scope", ""), q.get("slug"), q.get("rel", "")),
    "/api/artifact/file": artifacts.file_route,
    "/api/run/rawfile": runops.run_file_raw,
}


ROOMS3D_MARK = "<!-- arlotope:rooms3d"


def _with_rooms3d(html: str, prefix: str) -> str:
    """The optional Lab view’s fixed room scripts, loaded only inside its frame."""
    i = html.find(ROOMS3D_MARK)
    if i < 0:
        return html
    j = html.find("<!-- /arlotope:rooms3d -->", i)
    end = j + len("<!-- /arlotope:rooms3d -->") if j >= 0 else html.index("-->", i) + 3
    tags = [f'<script src="{prefix}{f.name}"></script>' for f in sorted((STATIC / "world3d" / "rooms").glob("*.js"))]
    return html[:i] + "\n".join(tags) + html[end:]


def _typed(f, ctype: str | None = None):
    return (f, ctype or library._FIG_CTYPE.get(f.suffix.lower(), "application/octet-stream")) if f else None

POST_ROUTES = {
    '/api/providers': providers.save,
    '/api/knowledge/note': lambda b: __import__('knowledge_api').note(b),
    '/api/agent-settings': lambda b: __import__('agent_settings').save(b),
    '/api/agent-settings/check': lambda b: __import__('agent_settings').check(b),
    '/api/project-machines/connect': lambda b: __import__('project_machines').connect(b),
    '/api/project-machines/disconnect': lambda b: __import__('project_machines').disconnect(b),
    '/api/project-machines/inspect': lambda b: __import__('project_machines').inspect(b),
    '/api/project-machines/projects': lambda b: __import__('project_machines').projects(b),
    '/api/project-machines/browse': lambda b: __import__('project_machines').browse(b),
    '/api/project-machines/terminal': lambda b: __import__('project_machines').terminal(b),
    '/api/room-draft': room_design.op,
    '/api/assistant/message': assistant.send,
    '/api/assistant/update': assistant.update,
    '/api/workflow/run': compose.run_tasks,
    "/api/starter": starter.create,
    '/api/starter/draft': starter.draft_op,
    "/api/study/tags": starter.tags,
    "/api/starter/repository": starter.lookup,
    "/api/study/entry/cancel": starter.cancel_entry,
    '/api/study/history/save': lambda b: decisions.history(b,save=True),
    "/api/starter/plan": starter.preview_entry,
    "/api/run": runops.launch_run,
    **{f"/api/run/{op}": functools.partial(runops._run_op, op) for op in ("answer", "reply", "handoff", "interrupt", "stop", "resume", "cancel")},
    "/api/run/permission": runops.permission_run,
    "/api/run/explain": runops.explain_run,
    "/api/attention/ack": runops.ack_attention,
    "/api/escalation/resolve": bus.resolve_escalation,
    "/api/executor/enable": runops.set_programmatic,
    "/api/lab/pause": runops.lab_pause,
    "/api/executor/config": settings.set_executor_config,
    "/api/labs/open": labs.labs_open,
    "/api/labs/create": labs.labs_create,
    "/api/labs/forget": labs.labs_forget,
    "/api/terminal": labs.terminal_open,
    "/api/checkpoint/decide": decisions.decide,
    '/api/checkpoint/gate': decisions.gate,
    "/api/checkpoint/checks": decisions.run_checks,
    "/api/study/workflow": decisions.set_workflow,
    "/api/study/use": decisions.set_use,
    "/api/study/move": decisions.move,
    "/api/study/hold": decisions.hold_study,
    "/api/flag/ack": decisions.ack_flag,
    "/api/panel/save": panels_api.save_panel,
    "/api/panel/pin": panels_api.pin_panel,
    "/api/panel/archive": panels_api.archive_panel,
    "/api/panel/approve": panels_api.approve_collector,
    "/api/panel/collect": panels_api.collect_now,
    "/api/campaign": campaign.campaign_create,
    "/api/campaign/control": campaign.campaign_control,
    "/api/doc/save": settings.doc_save,
    "/api/workflow/save": instructions.workflow_save,
    "/api/workflow/proposal": instructions.workflow_proposal,
    "/api/compose": compose.op,
    "/api/lab/config": settings.lab_config_set,
    "/api/keys": keys.keys_set,
    "/api/notify": keys.notify_set,
    "/api/notify/test": keys.notify_test,
    "/api/setup/complete": settings.setup_complete,
    "/api/server/stop": labs.server_stop,
    "/api/machines/add": machines.add_machine,
    "/api/machines/remove": machines.remove_machine,
    "/api/machines/probe": machines.probe,
    "/api/machines/add-lab": machines.add_lab,
    "/api/machines/create-lab": machines.create_lab,
    "/api/machines/open": machines.open_lab,
    "/api/machines/use": machines.use_lab,
    "/api/machines/disconnect": machines.disconnect,
    "/api/fleet/keep": fleet.set_keep,
    "/api/machines/local": machines.local,
    "/api/machines/install-uv": machines.install_uv,
    "/api/system/scheduler": system.system_scheduler_set,
    "/api/term/open": term.open_session,
    "/api/term/write": term.write,
    "/api/term/resize": term.resize,
    "/api/term/close": term.close,
    "/api/directive": bus.directive_post,
    "/api/artifact/reply": artifacts.reply,
    "/api/artifact/seen": artifacts.seen,
    "/api/withdraw": bus.withdraw_post,
    "/api/command": runops.command_post,
    "/api/tool": lambda b: _res(labtools.run_tool(b.get("name", ""), b.get("idea"))),
    "/api/read": lambda b: _res(review.read_doc(b.get("what", ""), b.get("idea"), b.get("run"), b.get("checkpoint"))),
    "/api/libdoc": lambda b: _res(library.lib_doc(b.get("scope", ""), b.get("slug"), b.get("rel", ""))),
    "/api/claims": lambda b: _res(review.claims_map(b.get("idea"))),
}


def _use_hub(path: str) -> None:
    """Point the dashboard (and its sources / executor) at another lab's hub root."""
    hub = Path(path).resolve()
    if not (hub / "lab").is_dir():
        raise SystemExit(f"--hub {hub}: no lab/ directory there")
    switch_hub(hub)


switch_hub = ctx.switch_hub   # (the lab picker; caches clear themselves through ctx.on_change)


def _forget_snapshot(_old=None, _new=None) -> None:
    with _SNAP_LOCK:
        _snap_cache.update(ts=0.0, value=None, sig=None, version=_snap_cache['version'] + 1)


ctx.on_change(_forget_snapshot)


class LabServer(LoopbackHTTPServer):
    daemon_threads = True
    request_queue_size = 128  # a cold page and its 3D frame open many asset connections at once

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return   # a client (a tab, a tunnel) went away mid-request — routine, not an error
        super().handle_error(request, client_address)

def main() -> int:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--hub", default=None)
    known, _ = pre.parse_known_args()
    if known.hub:
        _use_hub(known.hub)
    cfg = ctx.config().get("dashboard") or {}
    parser = argparse.ArgumentParser()
    parser.add_argument("--hub", default=None, help="serve another lab (its hub root); default: this repo")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--demo", action="store_true",
                        help="enable the synthetic demo world (debugging/showcase; visit /?demo). "
                             "Off by default; also enabled by ARLOTOPE_DEMO=1.")
    args = parser.parse_args()
    Handler.demo = bool(args.demo) or os.environ.get("ARLOTOPE_DEMO", "").lower() in ("1", "true", "yes")
    try:
        server = LabServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        print(f"port {args.port} is busy ({e}) — start with --port <another>, or use arlo.py (it picks one)")
        return 3
    ctx.SERVER = server
    labs.remember_lab(ctx.HUB)
    ticker._SCHED_HUBS.add(ctx.HUB)
    if not Handler.demo:
        panels_api.start_keeper()
        fleet.start_keeper()          # remote labs stay connected whether or not this dashboard runs agents
    print(f"ARLOtope · http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    if executor is None:
        print("  executor: not available (tools/executor missing) — observe-and-sign only")
    elif cfg.get("executor", True) is False:
        print("  executor: disabled for this dashboard (dashboard.executor: false) — observe-and-sign only")
    else:
        ticker.start_scheduler()
        on = bool((ctx.config().get("agents") or {}).get("programmatic", {}).get("enabled"))
        print("  executor: scheduler running · programmatic launching is "
              + ("ON" if on else "OFF (enable it in the dashboard settings, or /configure)"))
    if Handler.demo:
        print(f"  demo mode ENABLED (debugging) · synthetic world at http://127.0.0.1:{args.port}/?demo")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nARLOtope stopped.")
    ticker.handoff_scheduler()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
