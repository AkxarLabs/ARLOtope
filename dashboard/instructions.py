"""The PI's own instructions — added to a procedure, to a step, or to a subagent role — lab-wide (Workflow's
editors) or for one study (its page), and agents' proposals for them (take / leave). The files and the brief are
the kernel's (tools/kernel/instructions.py, brief.py); this is their API.
"""

from __future__ import annotations

import re
import subprocess
import sys

import ctx  # noqa: E402
import sources  # noqa: E402
from kernel import brief as kbrief, instructions, model  # noqa: E402

executor = sources.executor   # tools/executor, or None


def _study_arg(v) -> str | None:
    v = str(v or "").strip()
    if not v or v == "lab":
        return None
    if not re.match(r"^[a-z0-9][a-z0-9._-]{0,79}$", v) or not (ctx.HUB / "studies" / v).is_dir():
        raise ValueError(f"no study '{v}'")
    return v


def _body(text: str) -> str:
    m = re.match(r"\A---\n.*?\n---\n?", (text or "").replace("\r\n", "\n"), re.S)
    return (text[m.end():] if m else text or "").strip()


def workflow_item(q: dict) -> tuple[dict, int]:
    """One procedure, step or role with the PI's added instructions on it — lab-wide, or one study's (and the
    brief an agent gets)."""
    hub = ctx.HUB
    kind = str(q.get("kind") or "procedure")
    name = str(q.get("name") or "")
    try:
        study = _study_arg(q.get("study"))
        m = model.load(hub)
        if kind == "procedure":
            p = m["procedures"].get(name)
            if not p:
                return {"error": f"unknown procedure '{name}'"}, 404
            out = {"ok": True, "kind": kind, "name": name, "study": study, "procedure": p,
                   "skill": _body(ctx.read(hub / ".claude" / "skills" / name / "SKILL.md") or ""),
                   "variants": sorted(n for n, x in m["procedures"].items() if x.get("like") == name),
                   "steps": [s for s, d in m["steps"].items() if name in [d.get("do"), *d["also"]]],
                   "lab": {"add": instructions.read("add", name, hub)}}
            if study:
                out["study_layer"] = {"add": instructions.read("add", name, hub, study)}
            out["brief"], out["brief_sha"] = kbrief.brief(hub, name, study=study)
            return out, 200
        if kind == "step":
            st = m["steps"].get(name)
            if not st:
                return {"error": f"unknown step '{name}'"}, 404
            out = {"ok": True, "kind": kind, "name": name, "study": study, "step": st,
                   "lab": {"add": instructions.read("step", name, hub)}}
            if study:
                out["study_layer"] = {"add": instructions.read("step", name, hub, study)}
            return out, 200
        if kind == "role":
            if name not in model.roles(hub):
                return {"error": f"unknown role '{name}'"}, 404
            return {"ok": True, "kind": kind, "name": name, "study": None,
                    "contract": (ctx.read(hub / "agent-roles" / f"{name}.md") or "").strip(),
                    "lab": {"add": instructions.read("role", name, hub)}}, 200
    except ValueError as e:
        return {"error": str(e)}, 400
    return {"error": "kind must be procedure | step | role"}, 400


def workflow_save(body: dict) -> tuple[dict, int]:
    """Save (empty text = remove) one set of added instructions: kind add | step | role, lab-wide or for a study."""
    hub = ctx.HUB
    kind, name = str(body.get("kind") or ""), str(body.get("name") or "")
    text = body.get("text")
    if kind not in instructions.KINDS or not isinstance(text, str):
        return {"error": "kind (add | step | role), name and text"}, 400
    try:
        study = _study_arg(body.get("study"))
        m = model.load(hub)
        known = {"add": m["procedures"], "step": m["steps"], "role": model.roles(hub)}[kind]
        if name not in known:
            return {"error": f"unknown {'procedure' if kind == 'add' else kind} '{name}'"}, 404
        path = instructions.write(kind, name, text, hub, study)
    except ValueError as e:
        return {"error": str(e)}, 400
    warnings = []
    if kind == "role":
        r = subprocess.run([sys.executable, str(hub / "tools" / "role_sync.py"), "render"], cwd=str(hub),
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            warnings.append("saved, but re-rendering the role files failed: " + (r.stderr or r.stdout)[-300:])
    rel = path.relative_to(hub).as_posix() if path else None
    ctx.pi_log({"action": "workflow.save", "kind": kind, "name": name, "study": study, "chars": len(text.strip()),
               "file": rel})
    where = f"for {study}" if study else "lab-wide"
    return {"ok": True, "note": (f"saved {where}" if path else f"removed ({where})"), "file": rel,
            "warnings": warnings}, 200


def workflow_proposal(body: dict) -> tuple[dict, int]:
    """Take or leave an agent's suggested instructions."""
    pid, accept = str(body.get("id") or ""), body.get("accept")
    if not isinstance(accept, bool):
        return {"error": "accept must be true or false"}, 400
    try:
        rec = instructions.resolve(pid, accept, ctx.HUB)
    except (OSError, ValueError) as e:
        return {"error": str(e)}, 400
    if rec["kind"] == "role" and accept:
        subprocess.run([sys.executable, str(ctx.HUB / "tools" / "role_sync.py"), "render"], cwd=str(ctx.HUB),
                       capture_output=True, timeout=120)
    ctx.emit_hub("instruction_resolved", idea=rec.get("study"), detail=f"{rec['status']}: {rec['kind']} {rec['name']}")
    ctx.pi_log({"action": "workflow.proposal", "id": pid, "accept": accept, "kind": rec["kind"], "name": rec["name"],
               "study": rec.get("study")})
    return {"ok": True, "note": "added to the instructions" if accept else "declined"}, 200


def workflow_proposal_get(q: dict) -> tuple[dict, int]:
    pid = str(q.get("id") or "")
    for r in instructions.proposals(ctx.HUB, pending_only=False):
        if r.get("id") == pid:
            return {"ok": True, **r}, 200
    return {"error": "no such proposal"}, 404
