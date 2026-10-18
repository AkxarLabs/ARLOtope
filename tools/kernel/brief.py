"""The brief: exactly what an agent is told when it runs a procedure — for a study, where that study stands.

    brief(hub, proc, study=None) -> (text, sha)

It says where the study is and in which workflow; how to finish (the outcomes this step can report, where
each leads, and the command that reports one); what the procedure must produce; the PI's own instructions
(lab-wide, then for this study — for the procedure and for the step); and the workflow's checkpoints with
the PI's decisions and notes. Headless runs get it injected; a procedure's SKILL.md tells an agent to load it
(`newts brief <proc> --study <slug>`) when it isn't already in context.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import instructions, journal, model, studies


def newts_cmd(hub) -> str:
    """The command an agent runs to talk to the kernel, from anywhere (the hub or a project repo)."""
    return f'uv run --with pyyaml python "{(Path(hub) / "newts.py").as_posix()}"'


def sha(text: str) -> str:
    return hashlib.sha256((text or "").replace("\r\n", "\n").encode("utf-8")).hexdigest()[:12]


def _where(c: dict) -> str:
    return f"before {c['before']}" if c.get("before") else f"during {c.get('during')}, at {c.get('at')}"


def outcomes_block(hub, slug: str, proc: str | None = None) -> str:
    """How to finish this step: each outcome, where it leads, and the command. A procedure that runs at the
    step alongside its own (`also`) is told to leave the outcome to that one."""
    s = studies.study(hub, slug)
    if not s:
        return ""
    here = model.step(s["step"], hub) or {}
    if here.get("shelf") or s["finished"]:
        return (f"## Where {slug} stands\n\n{slug} is {'finished' if s['finished'] else here.get('label', s['step']).lower()}"
                " — nothing moves it but the PI.")
    wid = s["workflow"]
    w = model.workflow(wid, hub)
    owner = model.does(s["step"], wid, s["use"], hub)
    if proc and owner and proc != owner:
        return (f"## How to finish\n\nYou run at this step alongside its own procedure, /{owner}, which reports where "
                f"the study goes next. Do your work, then stop — don't report an outcome (`newts move`) yourself; say in "
                f"your final message what /{owner} should know.")
    lines = [f"## When your work on this step is done, report its outcome",
             f"`{newts_cmd(hub)} move {slug} <outcome> --note \"<one line: why>\"` — this is how the study moves; "
             "never edit lab/REGISTRY.md or lab/journal.jsonl. Report once, at the end, then stop:"]
    proc = model.procedure(model.does(s["step"], wid, s["use"], hub) or "", hub) or {}
    for o in studies.outcomes_at(hub, s):
        t = model.outcome_target(wid, s["step"], o, hub)
        if o == model.PARK:
            dest = "parks it (not now, maybe later)"
        elif o == model.KILL:
            dest = "kills it (it can't or shouldn't go on — say why)"
        elif t is None:
            dest = "finishes the study"
        elif t == model.ASK:
            dest = "the PI decides where it goes next"
        else:
            dest = f"→ {(model.step(t, hub) or {}).get('label', t)}"
            waits = [c for c in model.before_on_the_way(wid, s["step"], t, hub) if not studies.approved(hub, slug, c["id"])]
            if waits:
                dest += f" (it waits there for the PI's approval: {waits[0]['title']})"
        why = (proc.get("outcome_notes") or {}).get(o)
        if o == model.DONE and studies.study_outputs(hub, s):
            why = "refused until " + ", ".join(studies.study_outputs(hub, s)) + " exist"
        lines.append(f"- `{o}` {dest}" + (f" — {why}" if why else ""))
    lines.append(f"(Workflow: {w.get('title') or wid}. A question for the PI that isn't an outcome goes through "
                 "`python tools/artifact.py publish --question …`, and the run waits for the answer.)")
    return "\n".join(lines)


def checkpoint_block(hub, slug: str | None) -> str:
    """The workflow's checkpoints: where each is, whether it is approved, and the PI's notes."""
    wid = studies.workflow_of(hub, slug) if slug else model.default_workflow(hub)
    if not wid:
        return ""
    w = model.workflow(wid, hub)
    st = studies.decisions(hub, slug) if slug else {}
    head = f"## Checkpoints — workflow \"{w.get('title') or wid}\"" + (f" for {slug}" if slug else "")
    if not w["checkpoints"]:
        return head + "\nThis workflow has no checkpoints: nothing waits for the PI's approval."
    lines = [head, "A checkpoint uses its configured decision maker. A `before:` checkpoint is kept by the kernel: reporting the "
             "outcome that leads past it makes the study wait for it. At a `during:` checkpoint that isn't approved, "
             "stop at that point: do not do the work behind it, say what the PI should look at, and end the run. "
             "The PI, delegated campaign, checks or independent gate reviewer supplies the configured decision. "
             "Only the engine records an automated verdict — never approve your own work or claim approval in prose."]
    for c in w["checkpoints"]:
        rec = st.get(c["id"]) or {}
        state = {"approved": "APPROVED", "revoked": "revoked — not approved",
                 "changes-requested": "the PI asked for changes",
                 "outdated": "not approved — it changed since the PI approved it"}.get(rec.get("decision"), "not approved yet")
        lines.append(f"- **{c['title']}** (`{c['id']}`, {_where(c)}) — {state}."
                     + (f" It covers: {c['means']}." if c.get("means") else "") + (f" {c['tell']}" if c.get("tell") else ""))
        if c.get('approver') == 'agent':
            lines.append('  Independent review: report this checkpoint ID as needs_pi when stopping here. '
                         'The engine queues a fresh reviewer and applies only its declared decision routes: ' + str(c.get('decisions') or {'proceed':'continue'}))
        if rec.get("note"):
            lines.append(f"  - The PI's note: {rec['note']}")
    return "\n".join(lines)


def brief(hub, proc: str, study: str | None = None) -> tuple[str, str]:
    """(text, sha). Raises KeyError for an unknown procedure, ValueError for a bad study slug."""
    hub = model.hub_of(hub)
    p = model.procedure(proc, hub)
    if p is None:
        raise KeyError(proc)
    if study and not model.SLUG.match(study):
        raise ValueError(f"bad study slug {study!r}")
    s = studies.study(hub, study) if study else None
    parts: list[str] = []
    if s:
        here = model.step(s["step"], hub) or {}
        parts.append(f"## Where you are\n\n{study} is at **{here.get('label', s['step'])}** (step `{s['step']}`) in the "
                     f"workflow \"{model.workflow(s['workflow'], hub).get('title')}\". You are running /{proc}: "
                     f"{p.get('does') or p.get('title') or ''}".rstrip())
        parts.append(outcomes_block(hub, study, proc))
    import tagging
    labels = {'Procedure': tagging.normalize(p.get('tags'))}
    if s:
        labels.update(Study=tagging.study_tags(hub, study), Step=tagging.normalize(here.get('tags')),
                      Workflow=tagging.normalize(model.workflow(s['workflow'], hub).get('tags')))
    if any(labels.values()):
        parts.append('## Tags\n\n' + '\n'.join(f"{name}: {', '.join(tags)}" for name, tags in labels.items() if tags)
                     + '\nLabels organize work; they do not change instructions or approvals.')
    if p.get("reads"):
        parts.append("## What it works from\n" + "\n".join(f"- {r}" for r in p["reads"])
                     + "\n(an earlier step produced these; if one is missing, say so instead of guessing)")
    if p.get("outputs") or p.get("show_pi"):
        req = ["## What this procedure must produce"] + [f"- {o}" for o in p.get("outputs") or []]
        if p.get("show_pi"):
            req.append(f"- for the PI to look at (`python tools/artifact.py publish --title \"…\" --file <path>`): "
                       f"{str(p['show_pi']).strip()} — one artifact for what they would want to see, not a running commentary")
        parts.append("\n".join(req))
    project = None
    if s:
        from .checkpoints import project_dir  # noqa: PLC0415
        project = project_dir(hub, study)
    for name, what in (("TYPE.md", "what a run, a stage and the frozen evaluation mean here"),
                       ("DOMAIN.md", "its field's venues, data sources and conventions")):
        if project and (project / name).is_file():
            parts.append(f"## {name[:-3].capitalize()}\n\nThis project's `{name}` ({(project / name).as_posix()}) says "
                         f"{what} — follow it where this work touches them.")
    for who, lvl in (("lab-wide", None), ("for this study", study)):
        if who == "for this study" and not study:
            continue
        adds = []
        if s:
            body = instructions.read("step", s["step"], hub, lvl)
            if body:
                adds.append(f"### At {(model.step(s['step'], hub) or {}).get('label', s['step'])} (whatever runs there)\n\n{body}")
        body = instructions.read("add", proc, hub, lvl)
        if body:
            adds.append(f"### /{proc}\n\n{body}")
        if adds:
            parts.append(f"## The PI's instructions — {who}\n\n" + "\n\n".join(adds))
    cps = checkpoint_block(hub, study)
    if cps:
        parts.append(cps)
    body = "\n\n".join(x for x in parts if x)
    h = sha(body)
    head = (f"NEWTS BRIEF /{proc}{' · study ' + study if study else ''} · sha={h}\n"
            "The procedure's SKILL.md says how to do the work; this says where you are, how to finish, and what the PI "
            "added. AGENTS.md's hard rules always bind. The PI owns these instructions: never edit them — to suggest a "
            f"change, run `{newts_cmd(hub)} propose {proc} --file <draft.md>`.")
    return head + ("\n\n" + body if body else ""), h
