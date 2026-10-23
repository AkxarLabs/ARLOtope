"""Run one agent attempt and record everything it does.

`run_process` is the drain loop (spawn → capture stdout → parse → watchdog / stop marker / heartbeat
→ exit).

`supervise` is the body of `executor_cli.py supervise --run <id>`: a small process that owns exactly
one run while it is active. It holds the run's OS lock (its liveness signal), keeps the manifest
current (session id the moment it is known, last action, subagents, heartbeat), classifies the exit
(completed / waiting_input / timeout / killed / failed), and emits the bus events. The dashboard or
CLI that spawned it can die at any time without affecting the run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import actions, backends, live
from .lab import Lab, labfiles, pos_float, pos_int, profile
from .manifest import (append_jsonl, emit, now, read_manifest, run_dir, transition, worker_line,
                       write_manifest)
from .procs import NEW_GROUP, NO_WINDOW, RunLock, graceful_stop, kill_tree, python_exe

MIN_ATTEMPT_SECONDS = 300          # a resumed attempt always gets at least 5 minutes
MAX_SUBAGENTS = 60
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]+")   # a subagent's id, as a worker-log file name


@dataclass
class ProcResult:
    rc: int | None = None
    breached: bool = False
    stopped: bool = False
    cli_missing: bool = False
    parked: bool = False                # live: a question nobody answered — the process was ended to wait
    started: bool = False               # the CLI reported its session (it got past start-up)
    session_id: str | None = None
    last_message: str | None = None
    result: dict | None = None          # the backend's final result event (claude: stop_reason, cost)
    n_actions: int = 0
    wall: float = 0.0
    events: list = field(default_factory=list)


def run_process(cmd: list[str], *, cwd: Path, env: dict, stream_path: Path, backend: str,
                max_seconds: float, max_bytes: int = 200 * 1024 * 1024, stdin_text: str | None = None,
                on_spawn=None, on_event=None, stop_file: Path | None = None, heartbeat=None,
                heartbeat_every: float = 10.0, grace: float = 10.0, popen_flags: dict | None = None,
                live=None, conv=None) -> ProcResult:
    """Spawn `cmd`, stream its stdout into `stream_path` (capped at `max_bytes`), parse every line,
    and enforce the wall clock. Never raises for child failures — the result says what happened.
    `live` (a live.Session) keeps stdin open and turns protocol lines into events; `conv` (its
    live.Conversation) is ticked by the monitor, and the clock stops while the agent waits on the PI."""
    res = ProcResult()
    t0 = time.time()
    try:
        proc = subprocess.Popen(cmd, cwd=str(cwd), env=env,
                                stdin=subprocess.PIPE if (stdin_text is not None or live) else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                **(popen_flags if popen_flags is not None else NEW_GROUP))
    except (FileNotFoundError, PermissionError, OSError):
        res.cli_missing = True
        return res
    if on_spawn:
        on_spawn(proc.pid)
    if live:
        live.open(proc)
    elif stdin_text is not None:
        def _feed():
            try:
                proc.stdin.write(stdin_text)
                proc.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass
        threading.Thread(target=_feed, daemon=True).start()

    done = threading.Event()

    def _monitor():
        deadline = t0 + max_seconds
        next_beat = time.time() + heartbeat_every
        last = time.time()
        while not done.wait(0.5):
            if conv is not None:
                if conv.waiting():
                    deadline += time.time() - last   # waiting on the PI doesn't count
                try:
                    if conv.tick() and not res.parked:
                        res.parked = True
                        kill_tree(proc.pid)
                except Exception:  # noqa: BLE001 — the conversation must never kill the drain
                    pass
            last = time.time()
            if time.time() >= deadline and not res.breached and not res.stopped:
                res.breached = True
                kill_tree(proc.pid)
            if stop_file is not None and not res.stopped and not res.breached and stop_file.exists():
                res.stopped = True
                graceful_stop(proc, grace)
            if heartbeat and time.time() >= next_beat:
                next_beat = time.time() + heartbeat_every
                try:
                    heartbeat()
                except Exception:  # noqa: BLE001 — a heartbeat failure must never kill the drain
                    pass

    mon = threading.Thread(target=_monitor, daemon=True)
    mon.start()
    written, truncated = 0, False

    def store(sf, line: str) -> None:
        nonlocal written, truncated
        if max_bytes <= 0 or written < max_bytes:
            sf.write(line)
            sf.flush()
            written += len(line.encode("utf-8", "replace"))
            if max_bytes > 0 and written >= max_bytes and not truncated:
                sf.write('{"_truncated":"transcript hit max_transcript_mb; further output is parsed '
                         'for activity but no longer stored"}\n')
                sf.flush()
                truncated = True

    with Path(stream_path).open("a", encoding="utf-8") as sf:
        for line in (live.stream(proc) if live else proc.stdout):  # type: ignore[union-attr]
            if not live:
                store(sf, line)
            s = line.strip()
            if not s or not s.startswith("{"):
                continue
            try:
                obj = json.loads(s)
            except json.JSONDecodeError:
                continue
            if live:   # the session translates its protocol: store + parse what it returns
                lines, evs = live.handle(obj)
                for o in lines:
                    store(sf, json.dumps(o) + "\n")
                evs = [ev for o in lines for ev in backends.parse_events(backend, o)] + evs
            else:
                evs = backends.parse_events(backend, obj)
            for ev in evs:
                e = ev.get("event")
                if e == "start":
                    res.started = True
                if ev.get("session_id") and not res.session_id:   # the FIRST session id wins (opencode
                    res.session_id = ev["session_id"]              # child sessions must not overwrite it)
                if e == "result":
                    if ev.get("last_message"):
                        res.last_message = ev["last_message"]
                    res.result = ev
                elif e == "action":
                    res.n_actions += 1
                if on_event:
                    try:
                        on_event(ev)
                    except Exception:  # noqa: BLE001
                        pass
    done.set()
    if live:
        live.close()
    proc.wait()
    mon.join(timeout=grace + 2)
    res.rc = proc.returncode
    if live and live.ended and not (res.stopped or res.breached or res.parked):
        res.rc = 0
    if live and live.error and not (res.stopped or res.breached or res.parked):
        res.rc = res.rc or 1   # the CLI reported a failure without exiting (codex / opencode servers)
        res.last_message = live.error
    res.wall = round(time.time() - t0, 1)
    return res


def classify(res: ProcResult) -> str:
    """Terminal/paused status for one finished attempt. A deferred question is classified by the
    stop reason, never by the exit code."""
    if res.cli_missing:
        return "failed"
    if res.parked:
        return "waiting_input"
    if res.stopped and res.rc != 0:
        return "killed"
    if res.breached and res.rc != 0:
        return "timeout"
    return "completed" if res.rc == 0 else "failed"


# ── the per-run supervisor ───────────────────────────────────────────────────

class _State:
    """The supervisor's in-memory manifest, written atomically under a lock (drain + heartbeat
    threads both touch it). Throttled: activity writes at most once a second."""

    def __init__(self, lab: Lab, path: Path, m: dict):
        self.lab, self.path, self.m = lab, path, m
        self.lock = threading.RLock()
        self._last = 0.0

    def write(self, force: bool = False) -> None:
        with self.lock:
            if force or time.time() - self._last >= 1.0:
                self.m["heartbeat"] = now()
                write_manifest(self.path, self.m)
                self._last = time.time()

    def transition(self, to: str, *, by: str = "supervisor", reason: str | None = None, **fields) -> None:
        with self.lock:
            self.m["heartbeat"] = now()
            transition(self.lab, self.path, self.m, to, by=by, reason=reason, **fields)
            self._last = time.time()


def _env_local(lab: Lab) -> dict:
    """lab/.env.local (git-ignored; written by the dashboard's Research keys form): KEY=value lines a run
    inherits (e.g. S2_API_KEY). Never overrides what the executor itself sets."""
    return {k: v for k, v in labfiles.read_env(lab.lab / ".env.local").items()
            if k.replace("_", "").isalnum() and not k.startswith(("ARLOTOPE_"))}


_CONTINUE = ("This session was interrupted before it finished ({why}). Check what was already done "
             "(the ledgers and git are the memory), then continue the procedure from where it stopped.")


def _late_text(item: dict) -> str:
    """An answer or message that arrived after the session ended, as the resumed session's first turn."""
    if item.get("kind") == "message":
        return str(item.get("text") or "")
    lines = ["The PI answered your question:"]
    for k, v in (item.get("answers") or {}).items():
        lines.append(f"- {k}: {', '.join(v) if isinstance(v, list) else v}")
    if item.get("response"):
        lines.append(str(item["response"]))
    return "\n".join(lines)


def _say(msg: str) -> None:
    """One line to <run>.d/supervisor.log (our stdout) — how an early exit explains itself."""
    print(f"[{now()}] supervise: {msg}", flush=True)


def supervise(lab: Lab, run_id: str, target: str) -> int:
    _say(f"start run={run_id} target={target} pid={os.getpid()}")
    workdir = lab.target_dir(target)
    if not workdir:
        _say(f"exit 2: no workdir for target {target!r}")
        return 2
    adir = lab.agents_dir(workdir)
    mpath = adir / f"{run_id}.json"
    m = read_manifest(mpath, patience=5.0)
    if m is None:
        _say(f"exit 2: manifest unreadable at {mpath}")
        return 2
    rd = run_dir(adir, run_id)
    lock = RunLock(rd / "lock")
    # A reconcile probe (is_locked) holds the lock for an instant to test liveness — retry briefly.
    # A genuine second supervisor holds it for the whole run, so it still loses after the retries.
    deadline = time.time() + 5.0
    while not lock.try_acquire():
        if time.time() > deadline:
            _say("exit 3: another supervisor owns this run")
            return 3
        time.sleep(0.05)
    try:
        m = read_manifest(mpath, patience=5.0) or m   # re-read under the lock
        if m.get("status") not in ("starting", "resuming"):
            _say(f"exit 4: status is {m.get('status')!r} (stale spawn)")
            return 4
        rc = _attempt(lab, Path(workdir), adir, mpath, m, rd)
        _say(f"done rc={rc} status={m.get('status')}")
        return rc
    finally:
        lock.release()
        # Execution-only remote workers leave notifications and scheduling to their owning Lab.
        if not m.get('remote_owner'):
            try:
                from .scheduler import supervisor_finished   # noqa: PLC0415
                supervisor_finished(lab)
            except Exception as e:  # noqa: BLE001 — never let this affect the run's outcome
                _say(f"scheduler handoff: {e}")


_RETRY_ONESHOT = -1


def _attempt(lab: Lab, workdir: Path, adir: Path, mpath: Path, m: dict, rd: Path) -> int:
    """One attempt of a run: live when its backend has a live session and the PI didn't turn that off;
    when the live session can't even start on this machine, the same attempt runs one-shot."""
    st = _State(lab, mpath, m)
    b = backends.get(m.get("backend"))
    entry_status = m.get("status")
    is_live = b.has_live and (getattr(b, 'live_only', False) or live.enabled(lab.prog())) and not m.get("no_live")
    while True:
        rc = _run(lab, b, st, workdir, adir, rd, is_live)
        if rc != _RETRY_ONESHOT:
            return rc
        m["status"], is_live = entry_status, False


def _prepare(lab: Lab, b, st: _State, workdir: Path, rd: Path, is_live: bool):
    """The Attempt (CLI, prompt, env, the backend's sidecars) — or an exit code when it can't start."""
    m, run_id, prog = st.m, st.m["run_id"], lab.prog()
    try:
        m['task_followup'] = bool(profile.begin_run(lab, m))
    except ValueError as error:
        st.transition('failed', reason=str(error), last_message=str(error), finished=now())
        return 1
    if not m.get('remote_owner'):
        from .contexts import validate_head
        try:
            validate_head(lab, m)
        except ValueError as error:
            st.transition('failed', reason=str(error), finished=now())
            return 1
    bcfg = {**((prog.get("backends") or {}).get(b.name) or {}), **(m.get('assignment') or {}).get('options', {})}
    if m.get('assignment'):
        prog = {**prog, 'model': m['assignment'].get('model'), 'effort': m['assignment'].get('effort')}
    cli = backends.resolve_cli(b.name, bcfg)
    if not cli:
        st.transition("failed", reason=f"backend CLI not found: {b.name}", finished=now(),
                      last_message=f"backend CLI '{b.name}' not found — install it, or set "
                                   f"agents.programmatic.backends.{b.name}.command")
        emit(lab, workdir, "agent_finished", detail=run_id, status="failed",
             data={"reason": "cli-not-found", "run_id": run_id})
        return 1
    ver = backends.cli_version(cli) if b.probe_version else None
    m["cli"], m["cli_version"] = (cli[-1] if len(cli) == 1 else " ".join(cli)), backends.version_str(ver)
    resuming = m.get("status") == "resuming"
    if resuming and m.get('session_id') and not m.get('remote_owner'):
        from .contexts import assert_available
        try:
            assert_available(lab, m['session_id'], m['run_id'], expected=m)
        except ValueError as error:
            st.transition('failed', reason=str(error), finished=now())
            return 1
    resume = m.get("resume") or {}
    if not resuming:
        prompt = (rd / "prompt.md").read_text(encoding="utf-8") if (rd / "prompt.md").exists() else ""
    elif (resume.get("mode") or "continue") in ("answer", "reply"):
        prompt = resume.get("text") or ""
    else:
        prompt = _CONTINUE.format(why=m.get("reason") or m.get("status") or "unknown")
    if b.preassign_session and not m.get("session_id"):
        m["session_id"] = str(uuid.uuid4())   # resumable even if it dies before its first line
    attempt = int(m.get("attempt") or 0) + 1
    env = {**os.environ, "ARLOTOPE_RUN_ID": run_id, "ARLOTOPE_RUN_DIR": str(rd), "ARLOTOPE_HUB": str(lab.hub),
           "ARLOTOPE_RUN_TARGET": str(m.get("target")), "ARLOTOPE_ATTEMPT": str(attempt),
           "ARLOTOPE_RUN_SUBJECT": str(m.get("subject") or ""), "ARLOTOPE_RUN_SKILL": str(m.get("skill") or ""),
           "ARLOTOPE_AGENT_DEPTH": str(pos_int(m.get("depth"), 0, 0) + 1)}
    profile.run_env(m, env)                   # what the lab sets for one run
    if not m.get("watch_start"):
        try:   # where the repos stood as it started — the digest compares against this (the lab's monitoring)
            m["watch_start"] = profile.watch_start(lab, m, workdir)
        except Exception as e:  # noqa: BLE001 — monitoring never stops a run
            m["watch_error"] = f"{type(e).__name__}: {e}"[:300]
    env.update(_env_local(lab))
    env["ARLOTOPE_PYTHON"] = python_exe()   # the opencode tracer plugin shells out to trace_hook.py with it
    preamble = (rd / "preamble.md").read_text(encoding="utf-8") if (rd / "preamble.md").exists() else ""
    a = backends.Attempt(lab=lab, m=m, workdir=workdir, rd=rd, prog=prog, cli=cli, ver=ver, prompt=prompt,
                         preamble=preamble, resuming=resuming, live=is_live, env=env, python=python_exe(),
                         guard=profile.GUARD if profile.GUARD.is_file() else None,
                         tracer=profile.TRACER if profile.TRACER.is_file() else None)
    try:
        b.prepare(a)
        a.command = b.command(a)
    except (ValueError, OSError) as e:
        st.transition('failed', reason=str(e), finished=now(), last_message=str(e))
        return 1
    except SystemExit as e:
        st.transition("failed", reason=str(e), finished=now(), last_message=str(e))
        emit(lab, workdir, "agent_finished", detail=run_id, status="failed", data={"run_id": run_id})
        return 1
    return a


def _run(lab: Lab, b, st: _State, workdir: Path, adir: Path, rd: Path, is_live: bool) -> int:
    m, run_id = st.m, st.m["run_id"]
    a = _prepare(lab, b, st, workdir, rd, is_live)
    if isinstance(a, int):
        return a
    return _run_attempt(lab, b, st, workdir, adir, rd, is_live, a)


def _run_attempt(lab: Lab, b, st: _State, workdir: Path, adir: Path, rd: Path, is_live: bool, a) -> int:
    m, run_id = st.m, st.m['run_id']
    prog, cmd, attempt = a.prog, a.command, int(m.get("attempt") or 0) + 1
    max_minutes = pos_float(m.get("max_minutes"), 240.0) or 240.0
    used = sum(pos_float(x.get("wall_seconds"), 0.0) for x in (m.get("attempts") or []))
    stream = adir / (m.get("stream") or f"{run_id}.stream.jsonl")
    append_jsonl(stream, {"_attempt": attempt, "ts": now(), "resume": (m.get("resume") or {}).get("mode"),
                          "notes": cmd.notes or None})
    stop_file = rd / "stop"
    if stop_file.exists():   # the PI pressed stop while the run was still starting
        stop_file.unlink()
        st.transition("killed", reason="stopped by the PI before it started", finished=now())
        emit(lab, workdir, "agent_finished", detail=run_id, status="killed", data={"run_id": run_id})
        return 2
    m.setdefault("attempts", []).append({"n": attempt, "started": now(), "finished": None, "pid": None,
                                         "exit_code": None, "stop_reason": None, "wall_seconds": None,
                                         "resume": (m.get("resume") or {}).get("mode")})
    m.update(attempt=attempt, pending_question=None, transport="live" if is_live else "oneshot")
    m.pop("pending_permissions", None)
    sess = conv = None
    if is_live:
        sess = b.session(a)
        a.env.update(sess.env())
        conv = live.Conversation(sess, st, rd, prog, note=lambda kind, detail=None, **d: emit(
            lab, workdir, kind, detail=detail or run_id, idea=m.get("subject"), data={"run_id": run_id, **d}),
            log=lambda obj: append_jsonl(stream, obj))
    rec = _Recorder(lab, st, workdir, conv, None if cmd.fires_hooks else (lab.bus_of(workdir) / "workers" / f"{run_id}.jsonl"), rd)
    res = run_process(cmd.argv, cwd=a.workdir, env=a.env, stream_path=stream, backend=b.name,
                      max_seconds=max(max_minutes * 60 - used, MIN_ATTEMPT_SECONDS),
                      max_bytes=pos_int(prog.get("max_transcript_mb", 200), 200, 0) * 1024 * 1024,
                      stdin_text=cmd.stdin_text, on_spawn=rec.on_spawn, on_event=rec.on_event, stop_file=stop_file,
                      heartbeat=lambda: st.write(force=True), popen_flags=NO_WINDOW, live=sess, conv=conv)
    if is_live and not getattr(b, 'live_only', False) and not (res.started or res.stopped or res.parked or res.breached) and res.rc and res.wall < 60:
        # the live session never got going here (an old CLI, a flag it doesn't know): retry one-shot
        _say(f"live session ended at start-up (exit {res.rc}) — retrying this attempt one-shot")
        m["attempts"].pop()
        m["attempt"], m["no_live"] = attempt - 1, f"exit {res.rc} at start-up"
        append_jsonl(stream, {"_note": "live session failed at start-up; retrying one-shot", "ts": now()})
        return _RETRY_ONESHOT
    return _finish(lab, b, st, workdir, rd, res, conv, rec, a.cli, max_minutes)


class _Recorder:
    """Keeps the manifest current from the normalized event stream (drain thread; under st.lock): the run and
    every subagent it spawned — who spawned whom, what each is doing right now (`in_tool`: the call in flight,
    with its activity kind), what it did last, and how it ended. When the CLI fires no trace hooks, it also
    writes each agent's worker log (<bus>/workers/<run>.jsonl, and <run>.<subagent>.jsonl per subagent, in
    trace_hook's schema), so every run is traced the same way whatever its backend. And always the run's own
    action tree, kept with the run (<run>.d/actions.jsonl, executor/actions.py)."""

    def __init__(self, lab: Lab, st: _State, workdir: Path, conv, wlog: Path | None, rd: Path | None = None):
        self.lab, self.st, self.workdir, self.conv, self.wlog, self.rd = lab, st, workdir, conv, wlog, rd
        m = st.m
        self.m, self.run_id = m, m["run_id"]
        self.role = m.get("role") or "orchestrator"
        src = lab.source_of(workdir)
        self.idea = m.get("subject") or (src if src != "hub" else None)
        self.subagents: dict = m.setdefault("subagents", {})
        self.resuming = m.get("status") == "resuming"
        self.aliases: dict = {sa["session"]: k for k, sa in self.subagents.items() if sa.get("session")}
        self.calls: dict = {}      # call id → (the agent it belongs to, its in_tool) while it is in flight

    def on_spawn(self, pid) -> None:
        m = self.m
        m["attempts"][-1]["pid"] = pid
        self.st.transition("running", reason=None, pid=pid, supervisor_pid=os.getpid(), started=m.get("started") or now())
        emit(self.lab, self.workdir, "agent_resumed" if self.resuming else "agent_launched", detail=self.run_id,
             data={"backend": m.get("backend"), "role": self.role, "pid": pid, "run_id": self.run_id,
                   "attempt": m.get("attempt"), "skill": m.get("skill")})
        self._worker("start", status="working")
        if self.rd:
            actions.record(self.rd, None, "attempt", n=m.get("attempt"))

    # ── who an event belongs to ──────────────────────────────────────────────────
    def _key(self, *ids) -> str | None:
        """The subagent an id names: its spawning call's id, or its own session / thread / agent id."""
        for x in ids:
            if not x:
                continue
            if x in self.subagents:
                return x
            k = self.aliases.get(x)
            if k in self.subagents:
                return k
        return None

    def _who(self, ev: dict) -> tuple[dict, str | None]:
        k = self._key(ev.get("parent"), ev.get("agent"))
        if k:
            return self.subagents[k], k
        p = ev.get("parent")
        if p and len(self.subagents) < MAX_SUBAGENTS:   # a child heard from before its spawn was: hold its place
            self.subagents[p] = {"type": "subagent", "description": "", "status": "working", "started": now(),
                                 "finished": None, "n_actions": 0, "last_action": None, "result": None, "parent": None,
                                 "depth": 1, "background": False, "provisional": True}
            return self.subagents[p], p
        return self.m, None

    def _alias(self, alias, key) -> None:
        """`alias` (a session / thread / agent id) is the subagent `key`; a provisional entry under it merges in."""
        if not alias or not key or alias == key:
            return
        self.aliases[alias] = key
        ph = self.subagents.get(alias)
        if ph and ph.get("provisional") and key in self.subagents:
            del self.subagents[alias]
            sa = self.subagents[key]
            sa["n_actions"] = int(sa.get("n_actions") or 0) + int(ph.get("n_actions") or 0)
            for f in ("in_tool", "last_action", "last_text"):
                if ph.get(f) and not sa.get(f):
                    sa[f] = ph[f]
            for cid, (k, cur) in list(self.calls.items()):
                if k == alias:
                    self.calls[cid] = (key, cur)

    # ── the worker logs (only when no hooks trace this CLI) ────────────────────────
    def _wid(self, key: str | None) -> str:
        return self.run_id if key is None else f"{self.run_id}.{SAFE_ID.sub('-', key)[:48]}"

    def _worker(self, event: str, key: str | None = None, **fields) -> None:
        if self.rd and event in ("action", "spawn", "stop"):
            extra = ({"child": fields.get("tool_use_id"), "type": fields.get("spawns")} if event == "spawn"
                     else {"status": (self.subagents.get(key) or {}).get("status") or fields.get("status"), "result": fields.get("result")}
                     if event == "stop" else {})
            actions.record(self.rd, key, event, kind=fields.get("kind"), tool=fields.get("tool"),
                           summary=fields.get("summary"), **extra)
        if not self.wlog:
            return
        role = self.role if key is None else (self.subagents.get(key) or {}).get("type") or "general-purpose"
        worker_line(self.wlog.parent / f"{self._wid(key)}.jsonl", worker_id=self._wid(key), role=role, event=event,
                    idea=self.idea, run_id=self.run_id, session_id=self.run_id, subject=self.m.get("subject"), **fields)

    # ── what each agent is doing ─────────────────────────────────────────────────
    def _open(self, who: dict, key, ev: dict) -> None:
        cur = {"ts": now(), "tool": ev.get("tool"), "kind": ev.get("kind") or "tool", "summary": ev.get("summary"),
               "id": ev.get("tool_use_id")}
        who["in_tool"] = cur
        if cur["id"]:
            self.calls[cur["id"]] = (key, cur)
        self._worker("begin", key, tool=cur["tool"], kind=cur["kind"], summary=cur["summary"], tool_use_id=cur["id"])

    def _close(self, call_id) -> tuple[str | None, dict | None]:
        """A call ended: its agent is now in the newest call it still has open, or in none."""
        if call_id not in self.calls:
            return None, None
        key, cur = self.calls.pop(call_id)
        who = self.subagents.get(key) if key else self.m
        if who is not None:
            still = [c for (k, c) in self.calls.values() if k == key]
            if still:
                who["in_tool"] = still[-1]
            else:
                who.pop("in_tool", None)
        return key, cur

    def _ended(self, key: str, status: str, result=None) -> None:
        sa = self.subagents[key]
        if sa.get("status") in ("done", "failed", "stopped"):
            return
        sa.update(status=status, finished=now(), **({"result": str(result)[:1200]} if result else {}))
        sa.pop("in_tool", None)
        for cid in [c for c, (k, _) in self.calls.items() if k == key]:
            self.calls.pop(cid, None)
        self._worker("stop", key, status="done", result=sa.get("result"))
        self._worker("return", sa.get("parent"), tool_use_id=key, result=sa.get("result"))

    def _reopen(self, who: dict, key) -> None:
        if key and who.get("status") != "working":      # a codex / opencode subagent given more to do
            who.update(status="working", finished=None)
            self._worker("start", key, status="working")

    def on_event(self, ev: dict) -> None:
        with self.st.lock:   # the heartbeat thread serializes `m` concurrently
            self._event(ev)

    def _event(self, ev: dict) -> None:
        e, m, subagents = ev.get("event"), self.m, self.subagents
        if e in ("request", "cancelled", "turn_end", "limits"):
            if self.conv:
                self.conv.on_event(ev)
            return
        if e == "start":
            m['conversation_started'] = True
            if m.get('fork_session'):
                m['fork_started'] = True
            if ev.get("session_id") and not m.get("session_id"):
                m["session_id"] = ev["session_id"]
            if ev.get("model"):
                m["model_used"] = ev["model"]
            self.st.write(force=True)
            return
        if e in ("action", "begin"):
            who, key = self._who(ev)
            self._reopen(who, key)
            tu, spawn = ev.get("tool_use_id"), ev.get("spawn")
            if e == "begin" or ev.get("open"):
                self._open(who, key, ev)
            elif tu in self.calls:
                self._close(tu)
            else:
                who.pop("in_tool", None)
            if e == "action":
                who["n_actions"] = int(who.get("n_actions") or 0) + 1
                who["last_action"] = {"ts": now(), "tool": ev.get("tool"), "kind": ev.get("kind"), "summary": ev.get("summary")}
                if not ev.get("open"):
                    self._worker("action", key, tool=ev.get("tool"), kind=ev.get("kind"), summary=ev.get("summary"))
            if spawn and tu and (subagents.get(tu) or {}).get("provisional"):   # its child spoke first
                subagents[tu].pop("provisional")
                subagents[tu].update(type=spawn["subagent_type"], description=spawn["description"], parent=key)
            elif spawn and tu and tu not in subagents and len(subagents) < MAX_SUBAGENTS:
                subagents[tu] = {"type": spawn["subagent_type"], "description": spawn["description"],
                                 "status": "working", "started": now(), "finished": None, "n_actions": 0,
                                 "last_action": None, "result": None, "parent": key,
                                 "depth": int((who.get("depth") or 0) if key else 0) + 1,
                                 "background": bool(spawn.get("background"))}
                if spawn.get("child_session"):   # codex thread id / opencode child session id
                    subagents[tu]["session"] = spawn["child_session"]
                    self._alias(spawn["child_session"], tu)
                self._worker("spawn", key, tool=ev.get("tool"), kind="spawn", summary=ev.get("summary"),
                             tool_use_id=tu, spawns=spawn["subagent_type"], child=self._wid(tu),
                             background=bool(spawn.get("background")) or None)
                self._worker("start", tu, status="working")
        elif e == "tool_result":
            tu = ev.get("tool_use_id")
            key, cur = self._close(tu)
            if cur is not None:
                self._worker("action", key, tool=cur.get("tool"), kind=cur.get("kind"), summary=cur.get("summary"),
                             tool_use_id=tu)
            sa = subagents.get(tu)
            if sa and sa.get("background") and not ev.get("is_error"):
                sa["launched"] = (ev.get("text") or "")[:300]   # the launch ack — it's still working
            elif sa:
                self._ended(tu, "failed" if ev.get("is_error") else "done", ev.get("text"))
        elif e == "task":
            # a subagent's own lifecycle (claude task_* · a codex child thread's turns · an opencode child session)
            tid, tu = ev.get("task_id"), ev.get("tool_use_id")
            if tid and tu:
                self._alias(tid, tu)
            key = self._key(tu, tid)
            if key:
                sa = subagents[key]
                if tid and tid != key:
                    sa.setdefault("agent_id", tid)
                pk = self._key(ev.get("parent_task_id"))
                if pk and pk != key:
                    sa["parent"], sa["depth"] = pk, int(subagents[pk].get("depth") or 1) + 1
                if ev.get("background"):
                    sa["background"] = True
                st = ev.get("status")
                if st == "running":
                    self._reopen(sa, key)
                elif st in ("completed", "failed", "killed", "stopped"):
                    self._ended(key, {"completed": "done", "failed": "failed"}.get(st, "stopped"), ev.get("summary"))
        elif e == "text" and not ev.get("parent"):
            m["last_text"] = (ev.get("text") or "")[:800]
        elif e == "text":
            who, key = self._who(ev)
            if key:
                who["last_text"] = (ev.get("text") or "")[:300]
        elif e == "denied":
            m["denials"] = int(m.get("denials") or 0) + 1
        elif e == "result":
            if m.get('assistant') and self.rd and ev.get('last_message') and not ev.get('parent'):
                import knowledge
                result={'id':uuid.uuid4().hex,'at':knowledge.now(),'text':str(ev['last_message'])[:450000],
                        'error':bool(ev.get('is_error')),'question':m.get('knowledge_question')}
                result['file']='reply-'+result['id']+'.json'
                (self.rd/result['file']).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
                m['last_result']={k:result[k] for k in ('id','at','file')}
                try:
                    if result['question']:knowledge.save_answer(self.lab,result['question'],result)
                except (OSError,ValueError) as error:
                    m['knowledge_error']=str(error)
            if ev.get("last_message"):
                m["last_message"] = str(ev["last_message"])[:2000]
            u = m.setdefault("usage", {})
            if ev.get("cost_usd") is not None:
                u["cost_usd"] = ev["cost_usd"]
            if isinstance(ev.get("usage"), dict):
                u["tokens"] = {k: v for k, v in ev["usage"].items() if isinstance(v, (int, float))}
            if ev.get("num_turns") is not None:
                u["turns"] = ev["num_turns"]
            if ev.get("denials"):
                m["denials"] = max(int(m.get("denials") or 0), int(ev["denials"]))
        elif e == "usage" and isinstance(ev.get("usage"), dict):
            u = m.setdefault("usage", {})
            if "cost_delta" in ev:   # per model step (opencode) → accumulate
                tok = u.setdefault("tokens", {})
                for k, v in ev["usage"].items():
                    tok[k] = tok.get(k, 0) + v
                if isinstance(ev.get("cost_delta"), (int, float)):
                    u["cost_usd"] = round(float(u.get("cost_usd") or 0) + ev["cost_delta"], 6)
            else:                    # per turn totals (codex)
                u["tokens"] = ev["usage"]
        self.st.write()


def _finish(lab: Lab, b, st: _State, workdir: Path, rd: Path, res: ProcResult, conv, rec: _Recorder,
            cli: list[str], max_minutes: float) -> int:
    """Classify the attempt, record it, and move the run on (finished · parked · queued again)."""
    m, run_id = st.m, st.m["run_id"]
    status = classify(res)
    late = []
    if conv:
        late = conv.leftover + [i for i in live.take(rd) if i.get("kind") in ("answer", "message")]
        m.pop("pending_permissions", None)
        if status in ("failed", "waiting_input") and any(r["kind"] == "question" for r in conv.pending.values()):
            status = "waiting_input"   # it ended (or was parked) while asking — the answer resumes it
    m["attempts"][-1].update(finished=now(), exit_code=res.rc, wall_seconds=res.wall,
                             stop_reason=(res.result or {}).get("stop_reason"))
    m.pop("resume", None)
    m.pop("in_tool", None)
    rec.calls.clear()
    for k, sa in rec.subagents.items():   # anything still "working" when the session ended didn't report back
        sa.pop("in_tool", None)
        if sa.get("status") == "working":
            done = sa.get("background") and b.waits_for_background and status == "completed"
            sa.update(status="done" if done else "unfinished", **({"finished": now()} if done else {}))
            rec._worker("stop", k, status="done")
    if res.session_id and not m.get("session_id"):
        m["session_id"] = res.session_id
    if res.last_message:
        m["last_message"] = str(res.last_message)[:2000]
    total_wall = round(sum(pos_float(x.get("wall_seconds"), 0.0) for x in m["attempts"]), 1)
    reason = fkind = lreset = None
    if res.cli_missing:
        reason = f"could not execute {cli[0]}"
        m["last_message"] = f"backend CLI could not be executed: {' '.join(cli)}"
    elif status == "timeout":
        reason, fkind = f"max_minutes={max_minutes:g} breached", "timeout"
    elif status == "killed":
        reason = "stopped by the PI"
    if status == "failed":
        # how to treat it: a campaign waits out a usage limit, backs off a transient error, pauses on sign-in
        blob = f"{res.last_message or ''} {json.dumps(res.result or {})[:4000]}"
        fkind = "cli_missing" if res.cli_missing else backends.failure_kind(blob)
        reason = reason or {"auth": b.sign_in_hint, "usage_limit": "usage limit reached — resume later"}.get(fkind) \
            or f"exit {res.rc}"
        lreset = backends.limit_reset(blob) if fkind == "usage_limit" else None
    if status != "waiting_input":
        rec._worker("stop", status="done")

    if status == "waiting_input" and late and m.get("pending_question"):
        status = "completed"   # answered just as it was parked: resume with the answer (below)
    if late and status in ("completed", "waiting_input"):
        for item in late:
            if item.get('knowledge_question'):m['knowledge_question']=item['knowledge_question']
        st.transition("queued", by="supervisor", reason="PI message after the session ended",
                      resume={"mode": "reply", "text": "\n\n".join(_late_text(i) for i in late)},
                      pending_question=None, wall_seconds=total_wall, exit_code=res.rc, pid=None,
                      post_processed=False, not_before=None)
        return 0
    if status == "waiting_input":   # parked: the question stays in Needs you; the answer resumes it
        st.transition("waiting_input", reason="asking the PI (parked)", wall_seconds=total_wall,
                      exit_code=res.rc, pid=None)
        return 0
    st.transition(status, reason=reason, finished=now(), exit_code=res.rc, wall_seconds=total_wall, pid=None,
                  failure_kind=fkind, limit_reset=lreset)
    emit(lab, workdir, "agent_finished", detail=run_id, status=status, idea=m.get("subject"),
         data={"exit_code": res.rc, "run_id": run_id, "attempt": m.get("attempt"), "skill": m.get("skill")})
    return 0 if status == "completed" else 2
