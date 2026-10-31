"""Start ARLOtope: the dashboard server for this lab, then your browser.

    uv run --with pyyaml python arlo.py                 # this lab, http://127.0.0.1:8787 (or the next free port)
    uv run --with pyyaml python arlo.py --hub ../my-lab # another lab
    uv run --with pyyaml python arlo.py --no-browser
    uv run --with pyyaml python arlo.py --background    # detach: keeps running after you log out (remote boxes)
    uv run --with pyyaml python arlo.py --status | --stop

Or double-click `Start ARLOtope.cmd` (Windows) / `start-arlotope.command` (macOS) / run `./start-arlotope.sh`.
If the dashboard is already running for this lab, it just opens the browser. Everything else — creating
or switching labs, connecting other machines, signing in to an agent CLI, setup, launching work — happens
in the dashboard. Ctrl-C (or Settings → About → Stop server) stops the server; agent runs keep going.

On a machine you reached over SSH (no desktop), it prints the one line to run on your own computer to
reach it:  ssh -N -L 8787:127.0.0.1:<port> you@this-machine  → then open http://127.0.0.1:8787.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tools"))
import labfiles  # noqa: E402 — stdlib-only, so this launcher runs on any Python

PORTS = range(8787, 8800)


def lab_key(hub: Path) -> str:
    return hashlib.sha1(str(hub.resolve()).lower().encode("utf-8")).hexdigest()[:12]


def state_file(hub: Path) -> Path:
    return labfiles.home_path("servers", f"{lab_key(hub)}.json")


def _procs():
    """tools/executor/procs.py (detached spawning, tree kill, the stable Python), loaded by path: it is
    stdlib-only, and the executor package it lives in needs pyyaml, which this launcher may not have yet."""
    import importlib.util  # noqa: PLC0415
    spec = importlib.util.spec_from_file_location("arlotope_procs", HERE / "tools" / "executor" / "procs.py")
    procs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(procs)
    return procs


def stable_python() -> str:
    """A Python that outlives this launcher (see procs.python_exe): this one, unless it is uv's throwaway
    environment — then the one in the ARLOtope home. The dashboard, its detached supervisors and hooks all
    run on it."""
    return _procs().python_exe()


def _local(port: int, method: str, path: str, timeout: float, **request):
    """One request to a dashboard on this machine → (status, Set-Cookie, body). Loopback only: no OS proxy
    settings, no redirects."""
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    try:
        conn.request(method, path, **request)
        response = conn.getresponse()
        return response.status, response.getheader('Set-Cookie') or '', response.read()
    finally:
        conn.close()


def ping(port: int, timeout: float = 0.6) -> dict | None:
    try:
        status, _cookie, body = _local(port, 'GET', '/api/ping', timeout)
        data = json.loads(body.decode('utf-8')) if status == 200 else None
        return data if isinstance(data, dict) and data.get('app') == 'arlotope' else None
    except (OSError, ValueError, http.client.HTTPException):
        return None


def ask_to_stop(port: int) -> bool:
    """Stop the dashboard on `port` the way Settings → Stop server does (POST /api/server/stop, with the session
    the dashboard gives this machine's own processes)."""
    try:
        _status, cookie, _body = _local(port, 'GET', '/api/session', 5)
        status, _cookie, _body = _local(port, 'POST', '/api/server/stop', 10, body=b'{"confirm": true}',
                                        headers={'Content-Type': 'application/json', 'Cookie': cookie.split(';', 1)[0]})
        return status == 200
    except (OSError, http.client.HTTPException):
        return False


def port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        elif os.name == "posix":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # match HTTPServer after TIME_WAIT
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def headless() -> bool:
    """No local browser to open: an SSH session, or Linux without a display."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return True
    return sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def tunnel_hint(port: int) -> str:
    user = getpass.getuser()
    host = socket.gethostname()
    return (f"This machine has no browser of its own. On YOUR computer run:\n\n"
            f"    ssh -N -L 8787:127.0.0.1:{port} {user}@{host}\n\n"
            f"then open http://127.0.0.1:8787 (any free local port works in place of 8787).\n"
            f"Or add this machine in your local dashboard (Labs → Add a machine) and it does this for you.")


def running_for(hub: Path, port: int | None = None) -> tuple[int, dict] | None:
    """(port, ping) of a dashboard already serving this lab, if any."""
    cands = [port] if port else []
    try:
        st = json.loads(state_file(hub).read_text(encoding="utf-8"))
        cands.append(int(st.get("port")))
    except (OSError, ValueError, TypeError):
        pass
    cands += list(PORTS)
    seen = set()
    for p in cands:
        if not p or p in seen:
            continue
        seen.add(p)
        info = ping(p)
        if info and Path(info.get("lab") or "").resolve() == hub.resolve():
            return p, info
    return None


def stop(hub: Path) -> dict:
    """Stop this lab's dashboard and nothing else. It is asked to shut down (it hands queued work to a background
    scheduler first); only one that does not answer, or does not exit, is killed — that process alone. Never a
    tree kill: on Windows that also ends the detached supervisors it started, and with them every agent run."""
    hit = running_for(hub)
    try:
        st = json.loads(state_file(hub).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        st = {}
    pid = (hit[1].get("pid") if hit else None) or st.get("pid")
    if not pid:
        return {"ok": True, "note": "not running"}
    procs = _procs()
    asked = bool(hit) and ask_to_stop(hit[0])
    deadline = time.time() + (30 if asked else 0)
    while procs.pid_alive(pid) and time.time() < deadline:
        time.sleep(0.1)
    if procs.pid_alive(pid):
        try:
            os.kill(int(pid), signal.SIGTERM)   # Windows: TerminateProcess on this one process
        except (OSError, ValueError) as e:
            return {"error": f"could not stop pid {pid}: {e}"}
        for _ in range(50):
            if not procs.pid_alive(pid):
                break
            time.sleep(0.1)
    try:
        state_file(hub).unlink()
    except OSError:
        pass
    return {"ok": True, "note": f"stopped the dashboard (pid {pid}); agent runs keep going"}


def background(hub: Path, port: int | None, demo: bool) -> dict:
    """Start (or find) a detached dashboard for this lab; return {ok, port, pid, lab, already}."""
    hit = running_for(hub, port)
    if hit and (not port or hit[0] == port):
        return {"ok": True, "port": hit[0], "pid": hit[1].get("pid"), "lab": str(hub), "name": hit[1].get("name"),
                "already": True}
    if hit and port and hit[0] != port:
        stop(hub)                                   # the caller needs exactly `port` (a tunnel points there)
    if port and not port_free(port):
        return {"error": f"port {port} is in use by something else"}
    port = port or next((p for p in PORTS if port_free(p)), None)
    if port is None:
        return {"error": "no free port in 8787–8799 — pass --port"}
    logs = labfiles.home_path("logs")
    logs.mkdir(parents=True, exist_ok=True)
    log = (logs / f"{lab_key(hub)}.log").open("ab")
    argv = [sys.executable, str(Path(__file__).resolve()), "--hub", str(hub), "--port", str(port), "--no-browser",
            "--foreground", *(["--demo"] if demo else [])]
    procs = _procs()
    child = subprocess.Popen(argv, cwd=str(hub), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             env={**os.environ, "ARLOTOPE_BACKGROUND": "1"}, close_fds=True, **procs.DETACHED)
    for _ in range(150):
        info = ping(port, 0.3)
        if info:
            return {"ok": True, "port": port, "pid": info.get("pid") or child.pid, "lab": str(hub), "name": info.get("name"), "already": False}
        if child.poll() is not None:
            break
        time.sleep(0.1)
    return {"error": f"the dashboard did not start — see {logs / (lab_key(hub) + '.log')}"}


def main() -> int:
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):   # `arlo <verb> …` — the lab from a terminal
        import arlo_cli  # noqa: PLC0415
        if sys.argv[1] in arlo_cli.VERBS:
            return arlo_cli.main(sys.argv[1:])
    ap = argparse.ArgumentParser(description="Start ARLOtope (the dashboard) and open it in your browser. "
                                             "`arlo.py <verb>` controls the lab from a terminal: arlo.py status, "
                                             "approve, start, runs, panels … (`arlo.py status --help`).")
    ap.add_argument("--hub", default=str(HERE), help="the lab to open (default: this folder)")
    ap.add_argument("--port", type=int, default=None, help="default: 8787, or the next free port")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--background", action="store_true", help="detach and return (prints where it runs)")
    ap.add_argument("--foreground", action="store_true",
                    help="run the server in this window (closing it stops the dashboard's scheduling; by default "
                         "the server runs detached so the lab keeps working after you close the window)")
    ap.add_argument("--status", action="store_true", help="is a dashboard running for this lab?")
    ap.add_argument("--stop", action="store_true", help="stop this lab's dashboard (agent runs keep going)")
    ap.add_argument("--json", action="store_true", help="machine-readable output (used by remote connections)")
    ap.add_argument("--demo", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    py = stable_python()
    if py != sys.executable and not os.environ.get("ARLOTOPE_REEXEC"):
        # move onto the stable interpreter first (see stable_python), same arguments
        return subprocess.run([py, str(Path(__file__).resolve()), *sys.argv[1:]],
                              env={**os.environ, "ARLOTOPE_REEXEC": "1"}).returncode
    hub = Path(a.hub).expanduser().resolve()
    say = (lambda d: print(json.dumps(d))) if a.json else None
    if not labfiles.ensure_config(hub).exists():
        msg = (f"{hub} is not an ARLOtope lab (no lab/config.yaml). Open the dashboard from a lab folder, "
               "or create one from the dashboard's Labs page.")
        (say or print)({"error": msg} if say else msg)
        return 2

    if a.stop:
        res = stop(hub)
        (say or (lambda d: print(d.get("note") or d.get("error"))))(res)
        return 0 if res.get("ok") else 1
    if a.status:
        hit = running_for(hub)
        res = {"ok": True, "running": bool(hit), "port": hit[0] if hit else None,
               "pid": hit[1].get("pid") if hit else None, "lab": str(hub)}
        (say or (lambda d: print(f"running on http://127.0.0.1:{d['port']} (pid {d['pid']})" if d["running"] else "not running")))(res)
        return 0
    if a.background:
        res = background(hub, a.port, a.demo)
        if say:
            say(res)
        elif res.get("ok"):
            print(f"ARLOtope is {'already ' if res.get('already') else ''}running in the background for "
                  f"{res.get('name')} on http://127.0.0.1:{res['port']} (pid {res['pid']}). Stop it with --stop.")
            if headless():
                print(tunnel_hint(res["port"]))
        else:
            print(res.get("error"))
        return 0 if res.get("ok") else 1

    # already running for this lab? just open it
    hit = running_for(hub, a.port)
    if hit:
        url = f"http://127.0.0.1:{hit[0]}/"
        print(f"ARLOtope is already running for {hit[1].get('name')} — {url}")
        if headless():
            print(tunnel_hint(hit[0]))
        elif not a.no_browser:
            webbrowser.open(url)
        return 0

    if not a.foreground and not os.environ.get("ARLOTOPE_BACKGROUND"):
        # the default: a detached server, so closing this window doesn't stop queued runs, retries and campaigns
        res = background(hub, a.port, a.demo)
        if not res.get("ok"):
            print(res.get("error"))
            return 1
        url = f"http://127.0.0.1:{res['port']}/"
        print(f"ARLOtope is running for {res.get('name')} — {url}\n"
              "It keeps working when you close this window; stop it from Settings → About & server "
              "(or: arlo.py --stop).")
        if headless():
            print(tunnel_hint(res["port"]))
        elif not a.no_browser:
            webbrowser.open(url)
        return 0

    port = a.port or next((p for p in PORTS if port_free(p)), None)
    if port is None:
        print(f"ports {PORTS.start}–{PORTS.stop - 1} are all busy — pass --port <free port>")
        return 3
    url = f"http://127.0.0.1:{port}/"

    if headless() and not os.environ.get("ARLOTOPE_BACKGROUND"):
        print(tunnel_hint(port))
    elif not a.no_browser:
        def opener():
            for _ in range(100):
                if ping(port, 0.3):
                    webbrowser.open(url)
                    return
                time.sleep(0.15)
        threading.Thread(target=opener, daemon=True).start()

    sys.path.insert(0, str(HERE / "dashboard"))
    import serve   # noqa: E402 — the dashboard server, in this process
    sys.argv = ["serve.py", "--hub", str(hub), "--port", str(port), *(["--demo"] if a.demo else [])]
    state = state_file(hub)
    labfiles.write_json(state, {'port': port, 'pid': os.getpid(), 'lab': str(hub), 'started': labfiles.now()})
    try:
        return serve.main()
    finally:
        state.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
