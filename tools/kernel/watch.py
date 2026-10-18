"""Monitoring: what every run did, and flags when something notable happens.

    snapshot(dirs)                     where each repo stood when a run started (git HEAD, what was dirty)
    digest(hub, m, snap, …)            after the run: a computed summary — outcome, time, cost, files changed,
                                       commands, denials, flags — never the agent's own account
    flag(hub, level, say, …)           raise a flag: info (the digest only) · warn · block (the journal, and
                                       Needs you); `hold` pauses that study's launches until acknowledged
    ack(hub, flag_id, note)            the PI acknowledges one
    flags(hub, study=None)             the open ones · holding(hub, study): the open holds

A WATCH is a rule that raises a flag (workflow/rules.yaml `watch:`, and a checkpoint's own `watch:`):

    - {id: eval-edited, writes: ["{project}/eval/**"], level: block, hold: true, say: "evaluation code changed"}
    - {id: tests-removed, deletes: ["{project}/tests/**"], level: warn}
    - {id: pushed, runs: ["git push*"], level: info}
    - {id: refused, denials: 2, level: warn, say: "the run keeps trying what the lab refuses"}
    - {id: ledger-rewritten, check: append-only, level: block}        # a checks/ script, for the run's study

Paths are globs: {project} = the study's project repo, {hub} = the lab, else relative to the lab. File changes
come from git (so a script the agent wrote and ran is seen too); commands from the run's trace. An agent can
always run code — this makes what it did visible, it doesn't stop it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
from pathlib import Path

from . import journal, rules

LEVELS = ("info", "warn", "block")


# ── flags ────────────────────────────────────────────────────────────────────────────────────────
def flag(hub, level: str, say: str, study: str | None = None, run: str | None = None, source: str = "watch",
         detail: str = "", hold: bool = False, rule: str | None = None) -> dict:
    """Raise a flag. Info flags live in the run's digest only; warn and block ones go into the journal."""
    level = level if level in LEVELS else "warn"
    f = {"level": level, "say": str(say)[:300], "study": study, "run": run, "source": source,
         "detail": str(detail or "")[:600] or None, "hold": bool(hold) or None, "rule": rule}
    f["id"] = hashlib.sha256(json.dumps([journal.now(), f], sort_keys=True).encode()).hexdigest()[:10]
    if level == "info":
        return f
    by = source if journal.ID.match(source or "") else "watch"
    return journal.append(hub, study if study and journal.ID.match(study) else "lab", "flag", by,
                          **{k: v for k, v in f.items() if k not in ("study",) and v is not None})


def ack(hub, fid: str, note: str = "", by: str = "pi") -> dict:
    if not any(e.get("id") == fid for e in journal.events(hub, kinds=("flag",))):
        raise ValueError(f"no flag {fid!r}")
    return journal.append(hub, "lab", "ack", by, flag=fid, note=note)


def flags(hub, study: str | None = None, open_only: bool = True) -> list[dict]:
    """Warn and block flags, newest first (acknowledged ones left out unless open_only is False)."""
    acked = {e.get("flag"): e for e in journal.events(hub, kinds=("ack",))}
    out = []
    for e in journal.events(hub, kinds=("flag",)):
        if study is not None and e["study"] != study:
            continue
        if open_only and e.get("id") in acked:
            continue
        out.append(dict(e, acked=acked.get(e.get("id"))))
    return out[::-1]


def holding(hub, study: str) -> list[dict]:
    """The open flags holding this study's launches."""
    return [f for f in flags(hub, study) if f.get("hold")]


# ── what a run changed ───────────────────────────────────────────────────────────────────────────
def _git(cwd: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=15,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _dirty(cwd: Path) -> dict[str, str]:
    """{path: status} of what git sees changed or new in the working tree (relative to the repo root)."""
    out = {}
    for ln in (_git(cwd, "status", "--porcelain", "--untracked-files=all") or "").splitlines():
        if len(ln) > 3:
            out[ln[3:].split(" -> ")[-1].strip().strip('"')] = ln[:2]
    return out


def _journal_mark(hub) -> dict:
    p = journal.path(hub)
    try:
        data = p.read_bytes()
    except OSError:
        return {"size": 0, "sha": None}
    return {"size": len(data), "sha": hashlib.sha256(data).hexdigest()}


def journal_rewritten(hub, mark: dict | None) -> bool:
    """Was the journal changed other than by appending since `mark`? (The kernel only ever appends.)"""
    if not mark or not mark.get("sha"):
        return False
    try:
        data = journal.path(hub).read_bytes()
    except OSError:
        return True
    return len(data) < mark["size"] or hashlib.sha256(data[:mark["size"]]).hexdigest() != mark["sha"]


def snapshot(dirs: list[Path], hub=None) -> dict:
    """{repo root: {head, dirty}} for each dir inside a git repo (others are left out), and the journal's mark."""
    out: dict = {"_journal": _journal_mark(hub)} if hub else {}
    for d in dict.fromkeys(Path(x).resolve() for x in dirs if x):
        top = (_git(d, "rev-parse", "--show-toplevel") or "").strip()
        top = Path(top).as_posix() if top else ""
        if not top or top in out:
            continue
        out[top] = {"head": (_git(Path(top), "rev-parse", "HEAD") or "").strip() or None, "dirty": _dirty(Path(top))}
    return out


def changes(snap: dict) -> dict:
    """What changed in each snapshotted repo since: {"written": [abs], "deleted": [abs], "commits": n}."""
    written, deleted, commits = [], [], 0
    for top, s in (snap or {}).items():
        if top.startswith("_"):
            continue
        root = Path(top)
        now = _dirty(root)
        seen: dict[str, str] = {}
        if s.get("head"):
            for ln in (_git(root, "diff", "--name-status", s["head"]) or "").splitlines():
                parts = ln.split("\t")
                if len(parts) >= 2:
                    seen[parts[-1]] = parts[0][:1]
            commits += len((_git(root, "rev-list", f"{s['head']}..HEAD") or "").split())
        for p, st in now.items():
            if p not in (s.get("dirty") or {}) or (s.get("dirty") or {}).get(p) != st:
                seen.setdefault(p, "D" if "D" in st else "A" if "?" in st else "M")
        for p, st in seen.items():
            (deleted if st == "D" else written).append((root / p).as_posix())
    return {"written": sorted(set(written)), "deleted": sorted(set(deleted)), "commits": commits}


def commands(bus_dirs: list[Path], run_id: str, since: str = "") -> list[str]:
    """The shell commands a run (and its subagents) ran, from the trace's worker logs."""
    out = []
    for bus in dict.fromkeys(Path(b) for b in bus_dirs if b):
        wdir = bus / "workers"
        for f in sorted(wdir.glob("*.jsonl")) if wdir.is_dir() else []:
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for ln in lines:
                if run_id not in ln:
                    continue
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                s = str(e.get("summary") or "")
                if e.get("run_id") == run_id and e.get("event") == "action" and str(e.get("ts") or "") >= since[:19] \
                        and e.get("tool") in ("Bash", "PowerShell", "shell", "bash", "exec_command"):
                    out.append(s.split(": ", 1)[1] if ": " in s else s)
    return out


# ── watches ──────────────────────────────────────────────────────────────────────────────────────
def watches(hub) -> list[dict]:
    return [w for w in (rules.load(hub).get("watch") or []) if isinstance(w, dict) and w.get("id")]


def _expand(pat: str, hub: Path, project: Path | None) -> str | None:
    if "{project}" in pat and not project:
        return None
    s = pat.replace("{project}", project.as_posix() if project else "").replace("{hub}", Path(hub).as_posix())
    return s if Path(s).is_absolute() else (Path(hub) / s).as_posix()


def _match(paths: list[str], pats: list[str], hub: Path, project: Path | None) -> list[str]:
    hits = []
    for pat in pats:
        g = _expand(str(pat), hub, project)
        if g:
            hits += [p for p in paths if fnmatch.fnmatchcase(p.lower(), g.lower())]
    return sorted(set(hits))


def evaluate(hub, ws: list[dict], ch: dict, cmds: list[str], denials: int, project: Path | None,
             study: str | None, run: str | None) -> list[dict]:
    """Raise a flag for each watch the run tripped. → the flags."""
    out = []
    for w in ws:
        hits: list[str] = []
        if w.get("writes"):
            hits += _match(ch["written"], list(w["writes"]), hub, project)
        if w.get("deletes"):
            hits += _match(ch["deleted"], list(w["deletes"]), hub, project)
        if w.get("runs"):
            hits += [c for c in cmds if any(fnmatch.fnmatchcase(c.strip(), str(p)) for p in w["runs"])]
        if w.get("denials") and denials >= int(w["denials"]):
            hits.append(f"{denials} refused calls")
        if w.get("check") and study and (w.get("when") != "project" or project):
            from . import checkpoints  # noqa: PLC0415
            from .model import check_spec  # noqa: PLC0415
            item = w["check"] if isinstance(w["check"], dict) else str(w["check"])
            res = checkpoints.run_checks(hub, study, {"id": w["id"]}, timeout=120, names=[item])
            r = res.get(check_spec(item)[0]) or {}
            if r.get("code") not in (0, None, 127):
                hits.append((r.get("out") or "")[-300:])
        if hits:
            out.append(flag(hub, w.get("level", "warn"), w.get("say") or w["id"].replace("-", " "), study=study,
                            run=run, source="watch", detail="; ".join(hits[:8]), hold=bool(w.get("hold")), rule=w["id"]))
    return out


def checkpoint_watches(hub, study: str | None, wid: str | None) -> list[dict]:
    """A checkpoint's own watches (`watch: [check, …]`) — for a study, its workflow's checkpoints that aren't
    approved yet (once approved, work past them is allowed)."""
    if not study:
        return []
    from . import model, studies  # noqa: PLC0415
    out = []
    for c in model.checkpoints(wid, hub) if model.workflows(hub) else []:
        if studies.approved(hub, study, c["id"]):
            continue
        for item in c.get("watch") or []:
            out.append({"id": f"{c['id']}:{model.check_spec(item)[0]}", "check": item, "level": "block",
                        "say": f"work done past '{c['title']}' without its approval"})
    return out


def _outside_writes(hub, m: dict, ch: dict, study: str | None, run: str | None) -> list[dict]:
    """A run of a procedure that declares `writes:` (its only places) changed something elsewhere: a flag."""
    from . import model  # noqa: PLC0415
    pats = [str(x) for x in ((model.procedure(m.get("skill") or "", hub) or {}).get("writes") or [])] if m.get("skill") else []
    if not pats:
        return []
    out = [p for p in ch["written"] + ch["deleted"] if not _match([p], pats, Path(hub), None)]
    if not out:
        return []
    return [flag(hub, "warn", f"a /{m['skill']} run changed files outside {', '.join(pats)}", study=study, run=run,
                 source="watch", detail="; ".join(out[:8]), rule="writes-outside")]


def digest(hub, m: dict, snap: dict, bus_dirs: list[Path], project: Path | None = None,
           run_dir: Path | None = None) -> dict:
    """A run's computed summary, with the flags its watches raised."""
    run, study = m.get("run_id"), m.get("subject") or None
    since = str(m.get("started") or m.get("created") or "")
    ch = changes(snap)
    cmds = commands(bus_dirs, run, since)
    denials = int(m.get("denials") or 0) + _guard_denials(run_dir)
    moved = [e for e in journal.events(hub, study) if str(e.get("ts") or "") >= since[:19]
             and e["kind"] in ("move", "wait", "finish")] if study else []
    from . import studies  # noqa: PLC0415
    wid = studies.workflow_of(hub, study) if study else None
    ws = watches(hub) + checkpoint_watches(hub, study, wid)
    raised = evaluate(hub, ws, ch, cmds, denials, project, study, run)
    raised += _outside_writes(hub, m, ch, study, run)
    if journal_rewritten(hub, (snap or {}).get("_journal")):
        raised.append(flag(hub, "block", "the journal was rewritten during this run (the kernel only appends)",
                           study=study, run=run, source="watch", rule="journal-rewritten"))
    usage = m.get("usage") or {}
    return {
        "outcome": [{k: e.get(k) for k in ("kind", "from", "to", "outcome", "checkpoint", "at")} for e in moved]
        or ([] if not study else [{"kind": "none"}]),
        "minutes": _minutes(m), "cost_usd": usage.get("cost_usd"), "turns": usage.get("turns"),
        "files": {"written": ch["written"][:200], "deleted": ch["deleted"][:200], "commits": ch["commits"]},
        "commands": len(cmds), "notable": [c for c in cmds if _notable(c)][:20],
        "denials": denials, "flags": [{k: f.get(k) for k in ("id", "level", "say", "detail", "hold", "rule")} for f in raised],
    }


def render(d: dict) -> list[str]:
    """A digest as lines, for a terminal."""
    if not d:
        return ["(no digest — the run predates monitoring, or hasn't finished)"]
    f = d.get("files") or {}
    out = []
    for e in d.get("outcome") or []:
        out.append({"move": f"moved {e.get('from')} → {e.get('to')}" + (f" ({e['outcome']})" if e.get("outcome") else ""),
                    "wait": f"waits for the PI: {e.get('checkpoint') or e.get('outcome')}",
                    "finish": "finished its workflow", "none": "reported no outcome"}.get(e.get("kind"), str(e)))
    out.append(f"{len(f.get('written') or [])} files written, {len(f.get('deleted') or [])} deleted, "
               f"{f.get('commits') or 0} commits, {d.get('commands') or 0} commands, {d.get('denials') or 0} denied")
    out += [f"  + {p}" for p in (f.get("written") or [])[:20]] + [f"  - {p}" for p in (f.get("deleted") or [])[:20]]
    out += [f"  $ {c}" for c in d.get("notable") or []]
    out += [f"  ! [{x.get('level')}] {x.get('say')}" + (" (holds the study)" if x.get("hold") else "") for x in d.get("flags") or []]
    return out


def _guard_denials(rd: Path | None) -> int:
    if not rd:
        return 0
    try:
        return sum(1 for ln in (Path(rd) / "permissions.jsonl").read_text(encoding="utf-8").splitlines()
                   if '"deny"' in ln)
    except OSError:
        return 0


def _minutes(m: dict) -> float | None:
    from datetime import datetime  # noqa: PLC0415
    try:
        a = datetime.fromisoformat(str(m["started"])[:19])
        b = datetime.fromisoformat(str(m.get("finished") or journal.now())[:19])
        return round((b - a).total_seconds() / 60, 1)
    except (KeyError, ValueError, TypeError):
        return None


_NOTABLE = ("git push", "git reset", "git checkout", "rm -", "pip install", "uv add", "npm install", "curl ", "wget ",
            "ssh ", "scp ", "sbatch", "srun", "kill ", "chmod", "sudo")


def _notable(cmd: str) -> bool:
    c = cmd.strip().lower()
    return any(x in c for x in _NOTABLE)
