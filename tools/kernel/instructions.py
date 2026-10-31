"""The PI's own instructions, added to what agents are told — and agents' proposals for them.

    lab/workflow/<proc>.add.md          added to a procedure, lab-wide
    lab/workflow/step.<step>.add.md     added to whatever runs at a step, lab-wide
    lab/workflow/roles/<role>.add.md    added to a subagent role (tools/role_sync.py renders it in)
    studies/<slug>/workflow/…           the same names, for one study (they come after the lab's)

To do a procedure differently altogether, make a variant of its skill and use it (`like:`, `use:`) — these
files only ADD. Agents never edit them: `arlo propose` files a proposal the PI takes or leaves.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import labfiles

from . import model

KINDS = ("add", "step", "role")
MAX = 20000
_FM = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


def _safe(name: str) -> bool:
    return bool(name) and bool(model.SLUG.match(name))


def folder(hub, study: str | None = None) -> Path:
    h = model.hub_of(hub)
    if study:
        if not _safe(study):
            raise ValueError(f"bad study slug {study!r}")
        return h / "studies" / study / "workflow"
    return h / "lab" / "workflow"


def file(kind: str, name: str, hub=None, study: str | None = None) -> Path:
    if not _safe(name):
        raise ValueError(f"bad name {name!r}")
    d = folder(hub, study)
    if kind == "add":
        return d / f"{name}.add.md"
    if kind == "step":
        return d / f"step.{name}.add.md"
    if kind == "role":
        if study:
            raise ValueError("role instructions are lab-wide")
        return d / "roles" / f"{name}.add.md"
    raise ValueError(f"unknown kind {kind!r} (add | step | role)")


def read(kind: str, name: str, hub=None, study: str | None = None) -> str:
    p = file(kind, name, hub, study)
    try:
        text = p.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    except OSError:
        return ""
    m = _FM.match(text)
    return (text[m.end():] if m else text).strip()


def write(kind: str, name: str, text: str, hub=None, study: str | None = None) -> Path | None:
    """Save (or, with empty text, remove) one set of instructions."""
    text = (text or "").replace("\r\n", "\n").strip()
    if len(text) > MAX:
        raise ValueError(f"too long ({len(text)} characters; the limit is {MAX})")
    p = file(kind, name, hub, study)
    if not text:
        if p.exists():
            p.unlink()
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nupdated: {labfiles.now()}\n---\n{text}\n", encoding="utf-8", newline="\n")
    return p


def status(hub=None, study: str | None = None) -> dict:
    """What has instructions: {procedures: {p: True}, steps: {s: True}, roles: {r: True}}."""
    m = model.load(hub)
    out = {"procedures": {}, "steps": {}, "roles": {}}
    for name in m["procedures"]:
        if file("add", name, hub, study).is_file():
            out["procedures"][name] = True
    for sid in m["steps"]:
        if file("step", sid, hub, study).is_file():
            out["steps"][sid] = True
    if not study:
        d = folder(hub) / "roles"
        for f in sorted(d.glob("*.add.md")) if d.is_dir() else []:
            out["roles"][f.name[:-len(".add.md")]] = True
    return out


def studies_with_instructions(hub=None) -> dict[str, dict]:
    root = model.hub_of(hub) / "studies"
    out = {}
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if (d / "workflow").is_dir() and _safe(d.name) and any((d / "workflow").glob("*.md")):
            out[d.name] = status(hub, d.name)
    return out


# ── proposals: the only way an agent changes instructions ───────────────────────────────────────
def proposals_dir(hub=None) -> Path:
    return model.hub_of(hub) / "lab" / ".bus" / "workflow-proposals"


def propose(kind: str, name: str, text: str, hub=None, study: str | None = None, why: str = "", by: str = "") -> dict:
    file(kind, name, hub, study)                          # validates the kind and names
    m = model.load(hub)
    known = {"add": m["procedures"], "step": m["steps"]}.get(kind)
    if known is not None and name not in known:
        raise ValueError(f"unknown {'procedure' if kind == 'add' else 'step'} {name!r}")
    text = (text or "").replace("\r\n", "\n").strip()
    if not text or len(text) > MAX:
        raise ValueError(f"the proposal must be 1–{MAX} characters")
    import hashlib  # noqa: PLC0415
    pid = time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256((kind + name + text).encode()).hexdigest()[:6]
    rec = {"id": pid, "kind": kind, "name": name, "study": study, "text": text, "why": (why or "")[:1000],
           "by": by or "", "ts": labfiles.now(), "status": "pending"}
    d = proposals_dir(hub)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def proposals(hub=None, pending_only: bool = True) -> list[dict]:
    d = proposals_dir(hub)
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not pending_only or r.get("status") == "pending":
            out.append(r)
    return out


def resolve(pid: str, accept: bool, hub=None) -> dict:
    if not re.match(r"^[\w-]{1,60}$", pid or ""):
        raise ValueError("bad proposal id")
    f = proposals_dir(hub) / f"{pid}.json"
    r = json.loads(f.read_text(encoding="utf-8"))
    if r.get("status") != "pending":
        raise ValueError(f"already {r.get('status')}")
    if accept:
        cur = read(r["kind"], r["name"], hub, r.get("study"))
        write(r["kind"], r["name"], (cur + "\n\n" + r["text"]) if cur else r["text"], hub, r.get("study"))
    r["status"] = "accepted" if accept else "declined"
    r["resolved"] = labfiles.now()
    f.write_text(json.dumps(r, indent=1), encoding="utf-8")
    return r
