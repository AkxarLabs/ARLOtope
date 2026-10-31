"""Durable run records.

  <bus>/agents/<run_id>.json          the manifest — CURRENT state of one run (atomic replace)
  <bus>/agents/<run_id>.stream.jsonl  the full captured CLI stdout, all attempts ({"_attempt": n} separators)
  <bus>/agents/<run_id>.d/            sidecars (prompt, settings, mcp config, lock, stop marker,
                                      question/answer files, permission log, supervisor log)
  lab/.bus/runs.jsonl                 APPEND-ONLY ledger of every state transition, lab-wide

<bus> is `lab/.bus` for hub-level runs and `<project>/.bus` for project runs. Sidecars live in a
sub-directory (not `<id>.x.json` siblings) so every existing `agents/*.json` reader — the dashboard,
keeps seeing exactly one file per run.

State machine (see docs/dashboard.md):
  queued → starting → running → completed | waiting_input | timeout | killed | failed
  waiting_input / completed / failed / timeout / killed --(answer | reply | resume)--> queued (resume)
  queued (resume) → resuming → running (attempt n+1)
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .lab import Lab, labfiles, read_jsonl
from .procs import excl_lock

SCHEMA = 2
ACTIVE = {"starting", "running", "resuming"}          # an admitted attempt has a supervisor
TERMINAL = {"completed", "failed", "timeout", "killed"}
PAUSED = {"waiting_input"}                             # a live chat or a fully parked question
STATUSES = {"queued"} | ACTIVE | TERMINAL | PAUSED
RESUMABLE = TERMINAL | PAUSED                          # given a known session id


def is_live(run: dict) -> bool:
    """An admitted attempt or an open chat process, including support sessions."""
    pid = run.get('pid')
    return run.get('status') in ACTIVE or (run.get('status') == 'waiting_input' and type(pid) is int and pid > 0)


def is_support(run: dict) -> bool:
    """Review, explanation and assistance remain observable but do not use task capacity."""
    return bool(run.get('assistant') or run.get('explains') or run.get('judge')
                or run.get('role') in ('assistant', 'explainer', 'reviewer', 'fresh-context-reviewer', 'overseer'))


def uses_slot(run: dict) -> bool:
    """Only live task execution uses capacity; parked questions release it."""
    return is_live(run) and not is_support(run)


def slugify(s: str, n: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(s)).strip("-.")[:n] or "run"


# ── files ────────────────────────────────────────────────────────────────────

def read_manifest(path: Path, patience: float = 0.0) -> dict | None:
    """Read a manifest, never crashing. A reader can race the atomic replace on Windows (a sharing
    violation, or even a transient not-found) — retry briefly; `patience` > 0 keeps retrying a
    missing/unreadable file for that many seconds (for readers that know it must exist)."""
    deadline = time.time() + patience
    while True:
        for _ in range(3):
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                return data if isinstance(data, dict) else None
            except FileNotFoundError:
                break
            except (OSError, json.JSONDecodeError):
                time.sleep(0.02)
        if time.time() >= deadline:
            return None
        time.sleep(0.05)


def run_dir(agents_dir: Path, run_id: str) -> Path:
    return Path(agents_dir) / f"{run_id}.d"


def list_manifests(agents_dir: Path) -> list[tuple[Path, dict]]:
    agents_dir = Path(agents_dir)
    if not agents_dir.is_dir():
        return []
    out = []
    for f in sorted(agents_dir.glob("*.json")):
        m = read_manifest(f)
        if m is not None:
            out.append((f, m))
    return out


def emit(lab: Lab, workdir: Path, kind: str, **fields) -> None:
    """One bus event on the run's own bus, in the canonical lab_bus.py shape. Best-effort."""
    rec = {"ts": labfiles.now(), "source": lab.source_of(workdir), "kind": kind}
    rec.update({k: v for k, v in fields.items() if v is not None})
    labfiles.append_jsonl(lab.bus_of(workdir) / "events.jsonl", rec)


def worker_line(wlog: Path, **fields) -> None:
    """One worker-log line in the exact schema tools/trace_hook.py writes and the dashboard reads."""
    rec = {"ts": labfiles.now()}
    rec.update({k: v for k, v in fields.items() if v is not None})
    labfiles.append_jsonl(wlog, rec)


# ── transitions ──────────────────────────────────────────────────────────────

def transition(lab: Lab, path: Path, m: dict, to: str, *, by: str, reason: str | None = None,
               **fields) -> dict:
    """Move a run to `to`, persist the manifest, and append the transition to lab/.bus/runs.jsonl.
    Mutates and returns `m`. The ledger is the history; the manifest is the current view."""
    if to not in STATUSES:
        raise ValueError(f"unknown run status {to!r}")
    frm = m.get("status")
    m.update(fields)
    m["status"] = to
    m["status_ts"] = labfiles.now()
    m["reason"] = reason
    labfiles.write_json(path, m)
    labfiles.append_jsonl(lab.runs_ledger, {
        "ts": m["status_ts"], "run_id": m.get("run_id") or m.get("agent_id"), "target": m.get("target"),
        "from": frm, "to": to, "reason": reason, "by": by, "attempt": m.get("attempt"), "pid": m.get("pid"),
    })
    return m


# ── locks ────────────────────────────────────────────────────────────────────

def scheduler_lock(lab: Lab, wait: float = 30.0):
    """Serializes every queue mutation (enqueue excepted) and every tick, across processes."""
    return excl_lock(lab.bus / ".scheduler.lock", wait=wait)


# ── lookup ───────────────────────────────────────────────────────────────────

def new_run_id(agents_dir: Path, base: str) -> tuple[str, Path]:
    """A unique run id under `agents_dir`, reserved by creating its manifest file exclusively."""
    agents_dir = Path(agents_dir)
    agents_dir.mkdir(parents=True, exist_ok=True)
    base = slugify(base, 100)
    for i in range(0, 1000):
        rid = base if i == 0 else f"{base}-{i}"
        path = agents_dir / f"{rid}.json"
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        os.close(fd)
        return rid, path
    raise RuntimeError("could not allocate a run id")


def find_run(lab: Lab, run_id: str) -> tuple[str, Path, Path, dict] | None:
    """Locate a run across the hub and every project: (target, workdir, manifest_path, manifest)."""
    rid = labfiles.safe_id(run_id)
    if not rid:
        return None
    for target, workdir, adir in lab.all_agent_dirs():
        path = adir / f"{rid}.json"
        if path.exists():
            m = read_manifest(path)
            if m is not None:
                return target, workdir, path, m
    return None


def all_runs(lab: Lab) -> list[tuple[str, Path, Path, dict]]:
    out = []
    for target, workdir, adir in lab.all_agent_dirs():
        for path, m in list_manifests(adir):
            out.append((target, workdir, path, m))
    return out


def ledger(lab: Lab, tail: int | None = 2000) -> list[dict]:
    return read_jsonl(lab.runs_ledger, tail=tail)
