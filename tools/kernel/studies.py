"""Where the lab's studies stand, and the only way they move.

    new(hub, slug, title, workflow=None, at=None)    file a study at its workflow's first step (or `at`)
    move(hub, slug, outcome, note="")                 report an outcome; the workflow says where it leads
    move_to(hub, slug, step, note="")                 the PI moves a study anywhere (revive, jump back, skip)
    decide(hub, slug, checkpoint, decision, by=…)     the PI's (or a delegate's) decision on a checkpoint;
                                                      approving one a study waits at carries the move through
    set_workflow / set_use / set_project              which workflow it follows, its own swaps, its project
    rows(hub) / study(hub, slug) / next_for(hub, slug)   reading it

A move is refused when it isn't legal, and waits when a checkpoint on the way isn't approved: the study stays
where it is, the journal says what it waits for, and the PI's approval moves it on. Everything here goes
through the journal (kernel/journal.py); lab/REGISTRY.md is rewritten from it after every change.

Who acts: `by` is pi | cli | run:<id> | campaign:<name> | auto | migration. Inside an agent run ($NEWTS_RUN_ID)
the PI's actions — approving, moving a study anywhere, changing its workflow — are refused.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import journal, model

PI_ONLY = "approvals and moves outside the workflow are the PI's — ask instead"


class StudyError(ValueError):
    pass


def in_agent_run() -> bool:
    return bool(os.environ.get("NEWTS_RUN_ID"))


def actor(default: str = "cli") -> str:
    rid = os.environ.get("NEWTS_RUN_ID")
    return f"run:{rid}" if rid else default


def _pi(by: str, via: str = "") -> None:
    if in_agent_run() and via != "keeper":
        raise StudyError(PI_ONLY)
    if by.startswith("run:"):
        raise StudyError(PI_ONLY)


# ── reading ──────────────────────────────────────────────────────────────────────────────────────
def ensure(hub) -> None:
    """A lab with a registry but no journal yet (made before the journal existed) gets one, once."""
    if not journal.path(hub).exists() and (Path(hub) / "lab" / "REGISTRY.md").is_file():
        from . import migrate  # noqa: PLC0415
        migrate.journal_from_registry(hub)


def all_studies(hub) -> dict[str, dict]:
    ensure(hub)
    st = journal.fold(journal.events(hub), tuple(model.SHELF_LABEL))
    wids = {w["id"] for w in model.workflows(hub)}
    default = model.default_workflow(hub)
    for s in st.values():
        if s["workflow"] not in wids:
            s["workflow"] = default
    from . import branches
    evs = journal.events(hub)
    for slug, s in list(st.items()):
        if model.workflow(s['workflow'], hub).get('nodes'):
            st[slug] = branches.fold(hub, s, evs)
    return st


def study(hub, slug: str) -> dict | None:
    return all_studies(hub).get(slug) if slug else None


def workflow_of(hub, slug: str | None) -> str | None:
    s = study(hub, slug) if slug else None
    return (s or {}).get("workflow") or model.default_workflow(hub)


def _title(hub, s: dict) -> str:
    """The study's title: its IDEA.md says it (the document is the study's own), else what it was filed as."""
    text = Path(hub) / "studies" / s["id"] / "IDEA.md"
    try:
        for ln in text.read_text(encoding="utf-8-sig").splitlines()[:30]:
            if ln.startswith("title:"):
                t = ln.partition(":")[2].strip().strip("'\"")
                if t and "{{" not in t:
                    return t
    except OSError:
        pass
    return s["title"] or s["id"]


def next_for(hub, slug: str) -> dict:
    """What happens next for a study: {step, label, procedure, waiting, finished, shelved, workflow}."""
    s = study(hub, slug)
    if not s:
        raise StudyError(f"no study {slug!r}")
    wid = s["workflow"]
    st = model.step(s["step"], hub) or {}
    proc = None if (s["finished"] or s["waiting"] or st.get("shelf")) else model.does(s["step"], wid, s["use"], hub)
    return {"study": slug, "workflow": wid, "step": s["step"], "label": st.get("label", s["step"]),
            "procedure": proc, "waiting": s["waiting"], "finished": s["finished"], "shelved": bool(st.get("shelf"))}


def _next_text(hub, s: dict) -> str:
    st = model.step(s["step"], hub) or {}
    if st.get("shelf"):
        return st.get("label", s["step"]).lower()
    if s["finished"]:
        return "finished"
    w = s["waiting"]
    if w:
        if w.get("checkpoint"):
            cp = model.checkpoint(w["checkpoint"], s["workflow"], hub) or {}
            return f"waits for you: {cp.get('title') or w['checkpoint']}"
        return f"waits for you: it reported `{w.get('outcome')}`"
    proc = model.does(s["step"], s["workflow"], s["use"], hub)
    return f"/{proc}" if proc else ""


def rows(hub) -> list[dict]:
    """The registry as rows: {id, title, state (its step), workflow, project, updated, next, finished, waiting,
    use, was (the step a shelved study left), touched (when its last event was, in full)}."""
    out = []
    from tagging import study_tags
    for s in all_studies(hub).values():
        out.append({"id": s["id"], "title": _title(hub, s), "state": s["step"] or "", "workflow": s["workflow"],
                    "project": s["project"] or "", "updated": (s["since"] or s["updated"] or "")[:10],
                    "next": _next_text(hub, s), "finished": s["finished"], "waiting": s["waiting"], "use": s["use"], "was": s["was"],
                    "touched": s["updated"] or "", "tags": study_tags(hub, s['id'])})
        for key in ('active_steps', 'runnable', 'task_waits', 'completed_steps', 'joins', 'blocked_reason'):
            if key in s:
                out[-1][key] = s[key]
    return out


REGISTRY_HEAD = """# Lab Registry

Where every study stands. **Generated** from `lab/journal.jsonl` after every change — never edit it by hand:
studies move with `newts move <study> <outcome>` (or in the dashboard), and `newts status` shows the same.

| ID | Title | Step | Workflow | Project | Updated | Next |
|----|-------|------|----------|---------|---------|------|
"""


def render_registry(hub) -> None:
    lines = [REGISTRY_HEAD.rstrip("\n")]
    for r in rows(hub):
        cells = [r["id"], r["title"], r["state"], r["workflow"] or "", r["project"] or "—", r["updated"], r["next"]]
        lines.append("| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in cells) + " |")
    p = Path(hub) / "lab" / "REGISTRY.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _bus(hub, kind: str, slug: str, detail: str, **data) -> None:
    """A nudge on the dashboard's event bus (best-effort; the journal is the record)."""
    try:
        import json  # noqa: PLC0415
        bus = Path(hub) / "lab" / ".bus"
        bus.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": journal.now(), "source": "hub", "kind": kind, "idea": slug, "run_id":
                           os.environ.get("NEWTS_RUN_ID"), "detail": detail, "data": data}) + "\n"
        with (bus / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _record(hub, slug: str, kind: str, by: str, **fields) -> dict:
    ev = journal.append(hub, slug, kind, by, **fields)
    render_registry(hub)
    return ev


# ── acting ───────────────────────────────────────────────────────────────────────────────────────
def new(hub, slug: str, title: str = "", workflow: str | None = None, at: str | None = None,
        by: str | None = None) -> dict:
    """File a study. Slugs are never reused — a killed or parked one keeps its record."""
    by = by or actor()
    if os.environ.get('NEWTS_GATE_JUDGE'):
        raise StudyError('Return the gate verdict. Only the engine applies its decision.')
    if not model.SLUG.match(slug or ""):
        raise StudyError(f"bad study slug {slug!r} (lowercase letters, digits, - . _)")
    if slug in all_studies(hub):
        raise StudyError(f"{slug} already exists — pick another slug (a killed or parked study keeps its own)")
    w = model.workflow(workflow, hub)
    if workflow and w["id"] != workflow:
        raise StudyError(f"no workflow {workflow!r}")
    first = at or w["path"][0]
    if first not in w["path"]:
        raise StudyError(f"{first!r} is not a step of the {w['id']} workflow")
    passed = model.before_on_the_way(w["id"], w["path"][0], first, hub) if first != w["path"][0] else []
    if passed and str(by).startswith("run:"):
        raise StudyError(f"filing {slug} at {first} would pass {passed[0]['title']} — only the PI places a study "
                         "past a checkpoint (file it at the start, and ask)")
    ev = _record(hub, slug, "new", by, workflow=w["id"], title=title.strip()[:200], step=first)
    _bus(hub, "state_change", slug, f"filed at {first}")
    return ev


def decisions(hub, slug: str) -> dict[str, dict]:
    """{checkpoint: the study's latest decision on it}, as it stands now: an approval given under terms the
    checkpoint no longer has (model.terms), or by someone its approver no longer allows, reads `outdated` — the PI
    approves it again. (An approval recorded before terms were kept stands as it was.)"""
    s = study(hub, slug) or {}
    out = {}
    for cid, rec in journal.decisions(hub, slug).items():
        cp = model.checkpoint(cid, s.get("workflow"), hub) if s else None
        if cp and rec.get('judge_scope'):
            from gate_reviews import valid_approval
            if not valid_approval(hub, s, cp, rec):
                rec = dict(rec, decision='outdated', why='A new task visit needs a new gate review.')
        if rec.get("decision") == "approved" and cp is not None and (
                (rec.get("terms") and rec["terms"] != model.terms(cp)) or not model.may_approve(cp, str(rec.get("by") or "pi"))):
            rec = dict(rec, decision="outdated", why="the checkpoint changed since it was approved")
        out[cid] = rec
    return out


def approved(hub, slug: str, cid: str) -> bool:
    """Whether the study's checkpoint is approved, under its terms as they are now."""
    record = decisions(hub, slug).get(cid) or {}
    if record.get('decision') != 'approved':
        return False
    if record.get('evidence_revision'):
        s, cp = study(hub, slug), model.checkpoint(cid, None, hub)
        node = cp.get('before') or cp.get('during')
        if s['step'] == node or (s.get('waiting') or {}).get('checkpoint') == cid or any(t['id']==node for t in s.get('active_steps', [])):
            from gate_reviews import current_evidence
            return current_evidence(hub, s, cp, record)
    return True


_approved = approved


def _try_auto(hub, slug: str, cp: dict) -> bool:
    """An automatic checkpoint approves itself when its checks pass."""
    if cp.get("approver") != "auto":
        return False
    from . import checkpoints  # noqa: PLC0415
    try:
        checkpoints.decide(hub, slug, cp["id"], "approved", by="auto", via="kernel", note="its checks passed")
        return True
    except (checkpoints.CheckpointError, StudyError):
        return False


def _go(hub, slug: str, s: dict, target: str, outcome: str, by: str, note: str) -> dict:
    """Move s to target unless a before-checkpoint on the way isn't approved (then it waits)."""
    gates = model.before_on_the_way(s['workflow'], s['step'], target, hub)
    gates += [cp for cp in model.workflow(s['workflow'], hub)['checkpoints']
              if cp.get('before') == target and cp.get('approver') == 'agent' and cp['id'] not in {c['id'] for c in gates}]
    for cp in gates:
        allowed = _approved(hub, slug, cp['id'])
        rec = journal.decisions(hub, slug).get(cp['id'], {})
        if allowed and rec.get('judge_scope'):
            from gate_reviews import current_evidence
            allowed = current_evidence(hub, s, cp, rec, entering=True)
        if not allowed and not _try_auto(hub, slug, cp):
            _record(hub, slug, "wait", by, at=s["step"], to=target, outcome=outcome, checkpoint=cp["id"], note=note)
            _bus(hub, "gate_waiting", slug, f"waits for {cp['title']}", checkpoint=cp["id"])
            return {"moved": False, "waiting": cp["id"], "title": cp["title"], "step": s["step"], "to": target}
    _record(hub, slug, "move", by, **{"from": s["step"], "to": target, "outcome": outcome, "note": note})
    _bus(hub, "state_change", slug, f"{s['step']} → {target}" + (f" ({outcome})" if outcome else ""))
    path = model.workflow(s["workflow"], hub)["path"]
    if target == path[-1] and not (model.step(target, hub) or {}).get("do"):   # an end with no work to do: done
        _record(hub, slug, "finish", by, note="reached the end of its workflow")
        return {"moved": True, "step": target, "from": s["step"], "finished": True}
    return {"moved": True, "step": target, "from": s["step"]}


def reconcile(hub, by: str = "pi") -> list[dict]:
    """After the lab's definition changes: a study waiting at a checkpoint that is gone, or no longer on its way, is
    decided again against the checkpoints there are now — it moves on, or waits where it now must. Nothing is approved
    for it, and a wait whose destination step is gone stays for the PI to move. → [{study, checkpoint, result}]"""
    out = []
    for slug, s in all_studies(hub).items():
        if model.workflow(s['workflow'], hub).get('nodes'):
            continue  # Task waits are derived independently; never reset other active branches.
        w = s.get("waiting") or {}
        cid, to = w.get("checkpoint"), w.get("to")
        if not cid or s["finished"] or not to or to not in model.workflow(s["workflow"], hub)["path"]:
            continue
        if cid in [c["id"] for c in model.before_on_the_way(s["workflow"], s["step"], to, hub)]:
            continue          # still a checkpoint on its way: it still waits there
        res = _go(hub, slug, s, to, w.get("outcome") or model.DONE, by,
                  f"no longer waits at {cid}: the lab's definition changed")
        out.append({"study": slug, "checkpoint": cid, "result": res})
    if out:
        render_registry(hub)
    return out


def outcomes_at(hub, s: dict) -> list[str]:
    """The outcomes a study can report where it stands: done, park, kill, its procedure's own, and the routes'."""
    proc = model.procedure(model.does(s["step"], s["workflow"], s["use"], hub) or "", hub) or {}
    routed = list((model.workflow(s["workflow"], hub)["routes"].get(s["step"]) or {}))
    return list(dict.fromkeys([model.DONE, *proc.get("outcomes", []), *routed, model.PARK, model.KILL]))


def move(hub, slug: str, outcome: str, note: str = "", by: str | None = None) -> dict:
    """Report an outcome for a study. → {moved, step} | {moved: False, waiting: <checkpoint>|"pi"} | {finished}.
    Raises StudyError when the outcome isn't one this study can report here."""
    if os.environ.get('NEWTS_GATE_JUDGE'):
        raise StudyError('Return the gate verdict. Only the engine applies its decision.')
    by = by or actor()
    s = study(hub, slug)
    if not s:
        raise StudyError(f"no study {slug!r} (file it first: newts new {slug} --title …)")
    if model.workflow(s['workflow'], hub).get('nodes'):
        from . import branches
        return branches.move(hub, s, outcome, note, by)
    here = model.step(s["step"], hub)
    if not here:
        raise StudyError(f"{slug} is at {s['step']!r}, which is no longer a step — the PI moves it (newts move {slug} --to <step>)")
    if here["shelf"]:
        raise StudyError(f"{slug} is {here['label'].lower()} — only the PI brings it back")
    if s["finished"]:
        raise StudyError(f"{slug} has finished its workflow")
    allowed = outcomes_at(hub, s)
    if outcome not in allowed:
        raise StudyError(f"{outcome!r} is not an outcome of {s['step']} — report one of: {', '.join(allowed)}")
    missing = missing_outputs(hub, s) if outcome == model.DONE else []
    if missing:
        raise StudyError(f"`done` means the step's work is there, and {', '.join(missing)} is not — write it, then "
                         "report done again (or report another outcome)")
    target = model.outcome_target(s["workflow"], s["step"], outcome, hub)
    if target is None:
        _record(hub, slug, "finish", by, note=note)
        _bus(hub, "state_change", slug, f"finished ({s['step']})")
        return {"moved": False, "finished": True, "step": s["step"]}
    if target == model.ASK:
        _record(hub, slug, "wait", by, at=s["step"], outcome=outcome, note=note)
        _bus(hub, "gate_waiting", slug, f"reported {outcome}: the PI decides where it goes")
        return {"moved": False, "waiting": "pi", "step": s["step"], "outcome": outcome}
    return _go(hub, slug, s, target, outcome, by, note)


def study_outputs(hub, s: dict) -> list[str]:
    """The files the procedure doing this step says it produces in the study's own folder (`outputs:` naming a
    path under studies/<slug>/) — what `done` needs to exist. Paths elsewhere (a project repo, a ledger entry)
    aren't the kernel's to check."""
    proc = model.procedure(model.does(s["step"], s["workflow"], s["use"], hub) or "", hub) or {}
    out = []
    for o in proc.get("outputs") or []:
        rel = model._path_of(o)
        if rel.startswith("studies/<slug>/") and "<" not in rel[len("studies/<slug>/"):]:
            out.append(rel.replace("<slug>", s["id"]))
    return out


def missing_outputs(hub, s: dict) -> list[str]:
    return [rel for rel in study_outputs(hub, s) if not (Path(hub) / rel).exists()]


def move_to(hub, slug: str, to: str, note: str = "", by: str = "pi") -> dict:
    """The PI moves a study to any step of its workflow, or onto a shelf, or back off one. No checkpoint is
    asked: the PI's move is the decision."""
    _pi(by)
    s = study(hub, slug)
    if not s:
        raise StudyError(f"no study {slug!r}")
    w = model.workflow(s["workflow"], hub)
    if to not in w["path"] and to not in model.SHELF_LABEL:
        raise StudyError(f"{to!r} is not a step of the {w['id']} workflow ({', '.join(w['path'])})")
    if to == s["step"] and not s["finished"] and not s["waiting"]:
        return {"moved": False, "step": to}
    _record(hub, slug, "move", by, **{"from": s["step"], "to": to, "note": note})
    _bus(hub, "state_change", slug, f"{s['step']} → {to} (the PI)")
    return {"moved": True, "step": to, "from": s["step"]}


def resume(hub, slug: str, by: str) -> dict | None:
    """After an approval: carry a waiting study's move through if nothing else on the way waits."""
    s = study(hub, slug)
    if s and model.workflow(s['workflow'], hub).get('nodes'):
        return {'moved': bool(s['runnable']), 'step': s['step'], 'runnable': s['runnable']}
    w = (s or {}).get("waiting")
    if not s or not w or not w.get("to") or not w.get("checkpoint"):
        return None
    if w["at"] != s["step"]:
        return None
    return _go(hub, slug, s, w["to"], w.get("outcome") or "", by, "")


def set_workflow(hub, slug: str, wid: str, by: str = "pi") -> dict:
    _pi(by)
    s = study(hub, slug)
    if not s:
        raise StudyError(f"no study {slug!r}")
    w = model.workflow(wid, hub)
    if w["id"] != wid:
        raise StudyError(f"no workflow {wid!r}")
    ev = _record(hub, slug, "workflow", by, workflow=wid)
    if s["step"] not in w["path"] and s["step"] not in model.SHELF_LABEL:
        ev["note"] = f"{s['step']} is not on {wid}'s path — move it to one of its steps"
    return ev


def set_use(hub, slug: str, use: dict, by: str = "pi") -> dict:
    """A study's own swaps: {procedure: variant}, for this study only."""
    _pi(by)
    if not study(hub, slug):
        raise StudyError(f"no study {slug!r}")
    procs = model.load(hub)["procedures"]
    for a, b in (use or {}).items():
        if a not in procs or b not in procs:
            raise StudyError(f"unknown procedure in {a} → {b}")
    return _record(hub, slug, "use", by, use=dict(use or {}))


def set_project(hub, slug: str, path: str, by: str | None = None) -> dict:
    """Where a study's project repository is (spawn-project and adopt record it)."""
    if not study(hub, slug):
        raise StudyError(f"no study {slug!r}")
    import remote_projects
    if remote_projects.location(path):
        _pi(by or actor())
        return _record(hub, slug, 'project', by or actor(), path=path)
    p = Path(path)
    try:
        shown = p.resolve().relative_to(Path(hub).resolve()).as_posix() if p.is_absolute() else p.as_posix()
    except ValueError:
        shown = p.as_posix()
    return _record(hub, slug, "project", by or actor(), path=shown)


def rename_step(hub, old: str, new: str, by: str = "pi") -> dict:
    """The PI gives a step a new id: the definition says so everywhere (define.rename_step), the PI's
    instructions for that step follow it, and every study standing there moves with it (one `remap` event, so
    each study's timeline shows the rename)."""
    from . import define, instructions  # noqa: PLC0415
    _pi(by)
    d = define.rename_step(define.read(hub), old, new)
    define.write(hub, d)
    model._cache.clear()
    root = Path(hub) / "studies"
    for study in [None, *(p.name for p in root.iterdir() if p.is_dir())] if root.is_dir() else [None]:
        try:
            a, b = instructions.file("step", old, hub, study), instructions.file("step", new, hub, study)
        except ValueError:
            continue
        if a.is_file() and not b.exists():
            a.rename(b)
    ev = remap(hub, {old: new}, by=by)
    render_registry(hub)
    return ev


def remap(hub, mapping: dict[str, str], by: str = "pi") -> dict:
    """Steps were renamed (old id → new id): every study standing on one moves with it."""
    return _record(hub, "lab", "remap", by, map=dict(mapping))
