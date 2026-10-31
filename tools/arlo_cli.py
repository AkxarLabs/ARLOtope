#!/usr/bin/env python3
"""`arlo <verb>` — the whole lab from a terminal. `arlo api` also exposes every dashboard route; both call
the same code (the kernel in tools/kernel/, tools/panels.py, the executor).

    arlo status                              what needs you, what is running, every study and where it stands
    arlo studies                             the studies, their workflow and step
    arlo log "…" [--study S] [--tag label] [--ref path]          save a contextual study log
    arlo new <study> --title "…" [--workflow W] [--at STEP]      file a study
    arlo move <study> <outcome> [--note "…"]                      report an outcome: the workflow moves it
    arlo move <study> --to <step> [--note "…"]                    (the PI) move it anywhere: revive, jump, skip
    arlo next <study>                        where it stands and what runs next
    arlo brief <procedure> [--study S]       what an agent is told for that work
    arlo checkpoint <study> <checkpoint>     what a checkpoint shows: where, evidence, checks, history
    arlo approve <study> <checkpoint> [--note "…"] [--start] [--yes]
    arlo changes <study> <checkpoint> --note "…"      ask for changes (goes to the agent)
    arlo revoke <study> <checkpoint> [--yes]
    arlo approved <study> <checkpoint>       exit 0 if it is approved (for agents and scripts)
    arlo checks <study> <checkpoint>         run the checkpoint's checks now
    arlo approvals [<study>]                 the record of every decision
    arlo flags [<study>] | ack <flag> [--note "…"]    what the lab's watches flagged; acknowledge one (releases a hold)
    arlo start <procedure> [study] [--args "…"] [--backend B]    (or: arlo ask "…" [--study S])
    arlo runs | run <id> | answer <id> … | reply <id> --text "…" | stop <id> | resume [<id>] | pause
    arlo hold <study> [--reason "…"] | release <study>
    arlo workflow [show [<study>] | set <study> <workflow> | use <study> <procedure>=<variant>
                    | rename-step <old> <new> [--yes]]
    arlo project <study> <path>              where a study's project repository is
    arlo propose <procedure|step:S|role:R> --file F [--study S] [--why "…"]   (agents) suggest added instructions
    arlo extension [list | install <name> [--yes]]   a ready-made addition (extensions/<name>/): its workflows,
                                              steps, skills and checks, laid over the lab after you see what changes
    arlo check [--design <folder>]           validate the lab's definition, rules and generated docs — or a
                                              designer's draft laid over it (and say what it would change)
    arlo docs [--check]                      rewrite the generated parts of the manuals
    arlo room <room>                         what a stage group contains
    arlo panels [list] | panel <id> [--study S] | approve-collector <panel> [--yes]
    arlo config [view | set key=value]
    arlo api routes | api GET /api/state | api POST /api/compose --data @request.yaml
    arlo open [study] [--print]               open the Lab or a study, or print its browser link

The PI's verbs (approve, revoke, changes, move --to, workflow set/use/rename-step, approve-collector) refuse inside an agent
run, and ask you to confirm on a terminal (or pass --yes). Output is plain text; most verbs take --json.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import lab_docs  # noqa: E402
import panels  # noqa: E402
from kernel import brief as kbrief, checkpoints, diff, instructions, journal, model, rules, studies, watch  # noqa: E402

# Every dashboard action has a domain command or the shared API client; test_cli checks coverage.
ROUTE_VERBS = {
    "/api/providers": "api",
    "/api/knowledge/note": "api", "/api/agent-settings": "api",
    "/api/agent-settings/check": "api", "/api/checkpoint/gate": "api",
    "/api/assistant/message": "api", "/api/assistant/update": "api",
    "/api/room-draft": "api", "/api/workflow/run": "api",
    # The starter has its own small CLI, tools/research_start.py, rather than a new kernel verb.
    "/api/starter": "api", "/api/starter/repository": "api", "/api/starter/draft": "api",
    "/api/starter/plan": "api", "/api/study/entry/cancel": "api",
    # Generated history also has tools/study_history.py --save; it is not a kernel verb.
    "/api/study/history/save": "api",
    "/api/study/tags": "tags",
    "/api/run": "start / ask", "/api/run/answer": "answer", "/api/run/reply": "reply", "/api/run/interrupt": "stop",
    "/api/run/explain": "api", "/api/run/handoff": "api",
    "/api/run/stop": "stop", "/api/run/resume": "resume", "/api/run/cancel": "stop", "/api/run/permission": "answer",
    "/api/attention/ack": "api", "/api/escalation/resolve": "api",
    "/api/executor/enable": "config set agents.programmatic.enabled=true", "/api/lab/pause": "pause / resume",
    "/api/executor/config": "config set", "/api/labs/open": "api", "/api/labs/create": "api",
    "/api/labs/forget": "api", "/api/terminal": "api",
    "/api/checkpoint/decide": "approve / changes / revoke", "/api/checkpoint/checks": "checks",
    "/api/study/workflow": "workflow set", "/api/study/use": "workflow use", "/api/study/hold": "hold / release",
    "/api/study/move": "move <study> --to <step>", "/api/flag/ack": "ack",
    "/api/panel/save": "api", "/api/panel/pin": "api", "/api/panel/archive": "api",
    "/api/panel/approve": "approve-collector", "/api/panel/collect": "panel", "/api/panel/design": "start design",
    "/api/campaign": "start autopilot", "/api/campaign/control": "api",
    "/api/doc/save": "api", "/api/workflow/save": "api", "/api/workflow/proposal": "api",
    "/api/compose": "api", "/api/lab/config": "config set", "/api/keys": "api",
    "/api/notify": "api", "/api/notify/test": "api", "/api/setup/complete": "api",
    "/api/server/stop": "arlo.py --stop", "/api/system/scheduler": "config set",
    "/api/directive": "reply", "/api/artifact/reply": "reply", "/api/artifact/seen": "api",
    "/api/withdraw": "api", "/api/command": "start", "/api/tool": "api", "/api/read": "checkpoint",
    "/api/libdoc": "api", "/api/claims": "api",
    # remote machines and the in-browser terminal: in a terminal, ssh and your shell already do these
    **{f"/api/machines/{x}": "api" for x in ("add", "add-lab", "create-lab", "disconnect", "install-uv",
                                                                  "local", "open", "probe", "remove", "use")},
    "/api/fleet/keep": "api",
    **{f"/api/project-machines/{x}": "api" for x in ("connect", "disconnect", "inspect", "terminal", "browse", "projects")},
    **{f"/api/term/{x}": "api" for x in ("open", "write", "resize", "close", "read")},
}


def _hub(a) -> Path:
    return Path(a.hub or os.environ.get("ARLOTOPE_HUB") or HERE.parent).resolve()


def _out(a, data, text: str) -> None:
    print(json.dumps(data, indent=1, default=str) if getattr(a, "json", False) else text)


def _err(msg: str, code: int = 2) -> int:
    print(f"[arlo] {msg}", file=sys.stderr)
    return code


def _confirm(a, what: str) -> bool:
    if getattr(a, "yes", False):
        return True
    if not sys.stdin.isatty():
        print(f"{what} — pass --yes to confirm (no terminal to ask on)", file=sys.stderr)
        return False
    try:
        return input(f"{what}? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _executor(hub: Path):
    import executor  # noqa: PLC0415
    return executor, executor.Lab(hub)


def _label(hub, sid: str | None) -> str:
    return (model.step(sid or "", hub) or {}).get("label", sid or "?")


# ── what needs you / what is going on ────────────────────────────────────────────────────────────
def cmd_status(a) -> int:
    hub = _hub(a)
    rows = studies.rows(hub)
    waiting = [r for r in rows if r.get("waiting")]
    alerts = panels.alert_items(hub)
    try:
        ex, lab = _executor(hub)
        runs = [m for *_x, m in ex.all_runs(lab)]
        live = [m for m in runs if m.get("status") in ex.ACTIVE | {"queued", "waiting_input"}]
        asking = [m for m in runs if m.get("status") == "waiting_input"]
        paused = ex.pause.state(lab)
        holds = ex.pause.holds(lab)
    except Exception:  # noqa: BLE001
        live, asking, paused, holds = [], [], None, {}
    data = {"waiting": [{"study": r["id"], **(r["waiting"] or {})} for r in waiting], "studies": rows,
            "questions": [m.get("run_id") for m in asking], "alerts": alerts, "running": [m.get("run_id") for m in live],
            "paused": paused, "holds": holds}
    lines = []
    if paused:
        lines.append(f"❚❚ The lab is paused (since {paused.get('since')}). `arlo resume` to go on.")
    n = len(waiting) + len(asking) + len(alerts)
    lines.append(f"{n} thing(s) need you." if n else "Nothing needs you.")
    for r in waiting:
        w = r["waiting"]
        if w.get("checkpoint"):
            cp = model.checkpoint(w["checkpoint"], r["workflow"], hub) or {"title": w["checkpoint"]}
            lines.append(f"  ◆ {cp['title']} — {r['title']}   →  arlo checkpoint {r['id']} {w['checkpoint']}")
        else:
            lines.append(f"  ? {r['title']} reported `{w.get('outcome')}` — where should it go?   →  arlo move {r['id']} --to <step>")
    for m in asking:
        lines.append(f"  ? {m.get('command') or m.get('skill')} asks you   →  arlo run {m['run_id']}")
    for al in alerts:
        lines.append(f"  ▲ {al['say']} ({al['title']})   →  arlo panel {al['panel']}")
    lines.append(f"{len(live)} agent run(s) working or queued." + (f" On hold: {', '.join(holds)}." if holds else ""))
    for m in live[:12]:
        lines.append(f"  · {m.get('run_id')}  {m.get('status'):<14} {m.get('command') or m.get('skill')}")
    if rows:
        lines.append("Studies:")
        lines += [f"  {r['id']:<26} {_label(hub, r['state']):<18} {r['next']}" for r in rows]
    _out(a, data, "\n".join(lines))
    return 0


def cmd_tags(a) -> int:
    import tagging
    try:
        if not studies.study(_hub(a), a.study):
            raise ValueError('Choose an existing study.')
        value = tagging.study_tags(_hub(a), a.study) if a.set is None else tagging.set_study_tags(_hub(a), a.study, a.set)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as error:
        return _err(str(error), 1)


def cmd_studies(a) -> int:
    hub = _hub(a)
    rows = studies.rows(hub)
    _out(a, rows, "\n".join(f"{r['id']:<28} {r['state']:<16} {r['workflow'] or '':<10} {r['title']}   {r['next']}"
                            for r in rows) or "No studies yet.")
    return 0


def cmd_new(a) -> int:
    try:
        ev = studies.new(_hub(a), a.study, a.title or "", workflow=a.workflow, at=a.at)
    except (studies.StudyError, model.ModelError) as e:
        return _err(str(e), 1)
    print(f"{a.study} filed at {_label(_hub(a), ev['step'])} ({ev['workflow']} workflow)")
    return 0


def cmd_move(a) -> int:
    hub = _hub(a)
    try:
        if a.to:
            if not _confirm(a, f"Move {a.study} to {_label(hub, a.to)}"):
                return 1
            res = studies.move_to(hub, a.study, a.to, note=a.note or "", by="pi")
        elif a.outcome:
            res = studies.move(hub, a.study, a.outcome, note=a.note or "")
        else:
            return _err("which outcome? (arlo move <study> <outcome>, or --to <step> for the PI)")
    except (studies.StudyError, model.ModelError) as e:
        return _err(str(e), 1)
    if res.get("finished"):
        text = f"{a.study} has finished its workflow."
    elif res.get("moved"):
        nxt = studies.next_for(hub, a.study)
        text = f"{a.study} → {_label(hub, res['step'])}" + (f". Next: /{nxt['procedure']} {a.study}" if nxt["procedure"] else "")
    elif res.get("waiting") == "pi":
        text = f"{a.study} waits for the PI to say where `{res['outcome']}` leads. Stop here."
    elif res.get("waiting"):
        text = f"{a.study} waits for the PI's approval: {res['title']}. Stop here — the approval moves it on."
    else:
        text = f"{a.study} stays at {_label(hub, res.get('step'))}."
    _out(a, res, text)
    return 0


def cmd_next(a) -> int:
    hub = _hub(a)
    try:
        n = studies.next_for(hub, a.study)
    except studies.StudyError as e:
        return _err(str(e), 1)
    if n["finished"]:
        text = f"{a.study} has finished ({n['label']})."
    elif n["shelved"]:
        text = f"{a.study} is {n['label'].lower()}."
    elif n["waiting"]:
        w = n["waiting"]
        cp = model.checkpoint(w.get("checkpoint") or "", n["workflow"], hub) if w.get("checkpoint") else None
        text = f"{a.study} is at {n['label']} and waits for the PI: " + (cp["title"] if cp else f"where `{w.get('outcome')}` leads")
    else:
        text = f"{a.study} is at {n['label']}; next: /{n['procedure']} {a.study}" if n["procedure"] else f"{a.study} is at {n['label']}."
    _out(a, n, text)
    return 0


def cmd_brief(a) -> int:
    try:
        text, _h = kbrief.brief(_hub(a), a.procedure.lstrip("/"), study=a.study)
    except KeyError:
        return _err(f"unknown procedure {a.procedure!r}")
    except ValueError as e:
        return _err(str(e))
    print(text)
    return 0


# ── checkpoints ──────────────────────────────────────────────────────────────────────────────────
def cmd_checkpoint(a) -> int:
    hub = _hub(a)
    try:
        r = checkpoints.readiness(hub, a.study, a.checkpoint)
    except checkpoints.CheckpointError as e:
        return _err(str(e))
    cp = r["checkpoint"]
    rec = r.get("record") or {}
    lines = [f"◆ {cp['title']} — {a.study} ({cp['workflow']} workflow)",
             "  where: " + (f"before {cp['before']}" if cp.get("before") else f"during {cp.get('during')}, at {cp.get('at')}")
             + f" · the study is at {r['state'] or '?'}" + (" (it waits for this)" if r["waiting"] else ""),
             f"  status: {rec.get('decision', 'not approved yet')}" + (f" by {rec.get('by')} ({journal.when(rec)})" if rec else "")]
    if cp.get("means"):
        lines.append(f"  covers: {cp['means']}")
    for ev in r["evidence"]:
        lines.append(f"  evidence: {ev['path']}" + ("" if ev["exists"] else "  (not written yet)"))
    for c in r["checks"]:
        lines.append(f"  check {c['name']}: " + ("not run" if c["code"] is None else "passed" if c["code"] == 0 else f"exit {c['code']}"))
    if rec.get("note"):
        lines.append(f"  your note: {rec['note']}")
    lines.append(f"  → arlo approve {a.study} {cp['id']}   ·   arlo changes {a.study} {cp['id']} --note \"…\"")
    _out(a, r, "\n".join(lines))
    return 0


def _decide(a, decision: str) -> int:
    hub = _hub(a)
    if studies.in_agent_run():
        return _err("approvals are the PI's — an agent run can't make one. Ask the PI.", 1)
    lab_wide = a.checkpoint.startswith(checkpoints.LAB_WIDE)
    try:
        title = a.checkpoint if lab_wide else checkpoints.find(hub, a.study, a.checkpoint)["title"]
    except checkpoints.CheckpointError as e:
        return _err(str(e))
    verb = {"approved": "Approve", "revoked": "Take back the approval of", "changes-requested": "Ask for changes to"}[decision]
    if decision == "changes-requested" and not a.note:
        return _err("say what should change: --note \"…\"")
    if not _confirm(a, f"{verb} '{title}' for {a.study}"):
        return 1
    try:
        if lab_wide:
            rec = checkpoints.decide_lab(hub, a.checkpoint, decision, by="pi", via="cli", note=a.note or "")
        else:
            rec = checkpoints.decide(hub, a.study, a.checkpoint, decision, by="pi", via="cli", note=a.note or "")
    except (checkpoints.CheckpointError, studies.StudyError) as e:
        return _err(str(e), 1)
    print(f"◆ {title} — {decision} ({rec['ts']})")
    moved = rec.get("moved") or {}
    if moved.get("moved"):
        nxt = studies.next_for(hub, a.study)
        print(f"  {a.study} → {_label(hub, moved['step'])}")
        if nxt["procedure"]:
            if getattr(a, "start", False):
                return _start(hub, nxt["procedure"], a.study, "", None)
            print(f"  next: arlo start {nxt['procedure']} {a.study}")
    return 0


def cmd_approve(a) -> int:
    return _decide(a, "approved")


def cmd_revoke(a) -> int:
    return _decide(a, "revoked")


def cmd_changes(a) -> int:
    return _decide(a, "changes-requested")


def cmd_approved(a) -> int:
    hub = _hub(a)
    rec = studies.decisions(hub, a.study).get(a.checkpoint)
    ok = bool(rec) and rec.get("decision") == "approved"
    cp = model.checkpoint(a.checkpoint, studies.workflow_of(hub, a.study), hub) or {"title": a.checkpoint}
    if ok:
        print(f"'{cp['title']}' is approved for {a.study} ({rec.get('by')}, {journal.when(rec)})"
              + (f" — the PI's note: {rec['note']}" if rec.get("note") else ""))
        return 0
    why = {"revoked": "was revoked", "changes-requested": "the PI asked for changes",
           "outdated": "changed since it was approved"}.get((rec or {}).get("decision"),
                                                                                      "is not approved yet")
    print(f"'{cp['title']}' {why} for {a.study} — stop here and ask the PI")
    return 1


def cmd_checks(a) -> int:
    hub = _hub(a)
    try:
        res = checkpoints.run_checks(hub, a.study, checkpoints.find(hub, a.study, a.checkpoint))
    except checkpoints.CheckpointError as e:
        return _err(str(e))
    _out(a, res, "\n".join(f"  {n}: " + ("passed" if r["code"] == 0 else f"exit {r['code']}") for n, r in res.items())
         or "  (this checkpoint has no checks)")
    return 0 if all(r["code"] == 0 for r in res.values()) else 1


def cmd_approvals(a) -> int:
    recs = journal.approvals(_hub(a), a.study or None)
    _out(a, recs, "\n".join(f"{r['ts']}  {r['study']:<24} {r.get('checkpoint'):<24} {r['decision']:<18} {r.get('by')} via {r.get('via')}"
                            + (f" — {r['note']}" if r.get("note") else "") for r in recs[-60:]) or "No decisions recorded yet.")
    return 0


def cmd_flags(a) -> int:
    fl = watch.flags(_hub(a), a.study or None, open_only=not a.all)
    _out(a, fl, "\n".join(f"{f['ts']}  {f['level']:<5} {f['study']:<22} {f['say']}" + (" (held)" if f.get("hold") else "")
                           + (f" — {f['detail']}" if f.get("detail") else "") + f"   → arlo ack {f['id']}"
                           + ("  [acknowledged]" if f.get("acked") else "") for f in fl) or "No flags.")
    return 0


def cmd_ack(a) -> int:
    if studies.in_agent_run():
        return _err("acknowledging a flag is the PI's — ask instead.", 1)
    try:
        watch.ack(_hub(a), a.flag, note=a.note or "")
    except ValueError as e:
        return _err(str(e))
    print(f"acknowledged {a.flag}")
    return 0


# ── runs ─────────────────────────────────────────────────────────────────────────────────────────
def _start(hub: Path, skill: str, study: str | None, args: str, backend: str | None, prompt: str | None = None) -> int:
    ex, lab = _executor(hub)
    try:
        m = ex.enqueue(lab, ex.RunSpec(skill=skill or "", target=study or "hub", args=args or "", backend=backend,
                                       prompt=prompt, created_by="cli"))
    except ex.SpecError as e:
        return _err(str(e), 1)
    print(f"queued {m['run_id']}: {m.get('command') or skill}  (the scheduler starts it; `arlo run {m['run_id']}`)")
    return 0


def cmd_start(a) -> int:
    return _start(_hub(a), a.procedure.lstrip("/"), a.study, a.args, a.backend)


def cmd_ask(a) -> int:
    return _start(_hub(a), "ask", a.study, "", a.backend, prompt=a.text)


def _executor_cli(a, *argv) -> int:
    return subprocess.run([sys.executable, str(HERE / "executor_cli.py"), "--hub", str(_hub(a)), *argv]).returncode


def cmd_runs(a) -> int:
    return _executor_cli(a, "list", *(["--all"] if a.all else []))


def cmd_run(a) -> int:
    if getattr(a, "json", False):
        return _executor_cli(a, "show", a.run_id)
    ex, lab = _executor(_hub(a))
    hit = ex.find_run(lab, a.run_id)
    if not hit:
        return _err(f"no run {a.run_id}", 1)
    m = hit[3]
    print(f"{m.get('run_id')}  /{m.get('skill') or '?'} {m.get('target') or ''}  {m.get('status')}  "
          f"({m.get('backend') or '?'}, started {m.get('started') or '—'})")
    rep = m.get("report") or {}
    if rep.get("summary"):
        print("\n" + str(rep["summary"]).strip()[:1500])
    print("\nWhat it did:")
    print("\n".join("  " + x for x in watch.render(m.get("digest") or {})))
    return 0


def cmd_answer(a) -> int:
    return _executor_cli(a, "answer", a.run_id, *[x for p in (a.pick or []) for x in ("--pick", p)],
                         *(["--text", a.text] if a.text else []))


def cmd_reply(a) -> int:
    return _executor_cli(a, "reply", a.run_id, "--text", a.text)


def cmd_stop(a) -> int:
    return _executor_cli(a, "stop", a.run_id)


def _pi_only() -> int | None:
    """The PI's verbs refuse inside an agent run (ARLOTOPE_RUN_ID)."""
    return _err(studies.PI_ONLY, 1) if studies.in_agent_run() else None


def cmd_resume(a) -> int:
    return _pi_only() or _executor_cli(a, "resume", *([a.run_id] if a.run_id else []))


def cmd_pause(a) -> int:
    return _pi_only() or _executor_cli(a, "pause", *(["--reason", a.reason] if a.reason else []))


def cmd_hold(a) -> int:
    if _pi_only():
        return 1
    ex, lab = _executor(_hub(a))
    ex.pause.hold(lab, a.study, by="PI", reason=a.reason)
    print(f"{a.study} is on hold — nothing new starts for it (`arlo release {a.study}`)")
    return 0


def cmd_release(a) -> int:
    if _pi_only():
        return 1
    ex, lab = _executor(_hub(a))
    print(f"{a.study} released" if ex.pause.release(lab, a.study, by="PI") else f"{a.study} was not on hold")
    return 0


# ── the lab's definition ─────────────────────────────────────────────────────────────────────────
def cmd_workflow(a) -> int:
    hub = _hub(a)
    if a.action == "rename-step":
        if len(a.rest) != 2:
            return _err("usage: arlo workflow rename-step <old-id> <new-id>")
        if not _confirm(a, f"Rename the step {a.rest[0]} to {a.rest[1]} (the studies there move with it)"):
            return 1
        try:
            studies.rename_step(hub, *a.rest)
        except (studies.StudyError, ValueError) as e:
            return _err(str(e), 1)
        lab_docs.render(hub)
        print(f"the step {a.rest[0]} is now {a.rest[1]}, in every workflow; the studies there moved with it")
        return 0
    if a.action in ("set", "use"):
        if len(a.rest) != 2:
            return _err(f"usage: arlo workflow {a.action} <study> " + ("<workflow>" if a.action == "set" else "<procedure>=<variant>"))
        study, val = a.rest
        try:
            if a.action == "set":
                ev = studies.set_workflow(hub, study, val)
                print(f"{study} follows {val}" + (f" — {ev['note']}" if ev.get("note") else ""))
            else:
                proc, _, variant = val.partition("=")
                use = dict((studies.study(hub, study) or {}).get("use") or {})
                if variant:
                    use[proc] = variant
                else:
                    use.pop(proc, None)
                studies.set_use(hub, study, use)
                print(f"{study} uses " + (", ".join(f"/{v} for /{k}" for k, v in use.items()) or "the workflow's procedures"))
        except studies.StudyError as e:
            return _err(str(e), 1)
        return 0
    if a.rest:                                   # arlo workflow show <study>: the workflow that study follows
        try:
            w = model.workflow(studies.workflow_of(hub, a.rest[0]), hub)
        except (studies.StudyError, model.ModelError) as e:
            return _err(str(e), 1)
        lines = [f"{a.rest[0]} follows {w.get('title') or w['id']}: " + " → ".join(w["path"])]
        lines += [f"  ◆ {c['id']:<26} {c['title']} ("
                  + (f"before {c['before']}" if c.get("before") else f"during {c.get('during')}, at {c.get('at')}") + ")"
                  for c in w["checkpoints"]]
        _out(a, w, "\n".join(lines))
        return 0
    print(lab_docs.workflows_line(hub))
    for w in model.workflows(hub):
        for c in w["checkpoints"]:
            print(f"  {w['id']:<10} ◆ {c['id']:<26} {c['title']} — approver: {c.get('approver')}")
    return 0


def cmd_project(a) -> int:
    try:
        studies.set_project(_hub(a), a.study, a.path)
    except studies.StudyError as e:
        return _err(str(e), 1)
    print(f"{a.study}'s project: {a.path}")
    return 0


def cmd_propose(a) -> int:
    hub = _hub(a)
    kind, _, name = a.what.partition(":") if ":" in a.what else ("add", "", a.what)
    name = name or a.what
    try:
        text = Path(a.file).read_text(encoding="utf-8")
        rec = instructions.propose(kind, name.lstrip("/"), text, hub, study=a.study, why=a.why,
                                   by=os.environ.get("ARLOTOPE_RUN_ID", ""))
    except (OSError, ValueError) as e:
        return _err(str(e))
    studies._bus(hub, "instruction_proposal", a.study or "", f"{kind} {name}", proposal=rec["id"])
    print(f"proposal {rec['id']} filed — the PI takes or leaves it in the dashboard (Workflow)")
    return 0


def check_all(hub) -> tuple[list[str], list[Path]]:
    probs = model.check(hub, rules.check_names(hub)) + rules.check(hub)
    try:
        stale = lab_docs.render(hub, check_only=True)
    except Exception as e:  # noqa: BLE001 — an unrenderable definition is reported by check() already
        stale, probs = [], probs + [f"docs: {e}"]
    return probs, stale


def cmd_check(a) -> int:
    hub = _hub(a)
    if a.design:
        probs, said = diff.check_overlay(hub, Path(a.design))
        for x in probs:
            print(f"[arlo] problem: {x}")
        for x in said:
            print(f"[arlo] it {x}")
        if not probs:
            print("[arlo] ok — the design can be taken" + ("" if said else " (it changes nothing)"))
        return 1 if probs else 0
    probs, stale = check_all(hub)
    for x in probs:
        print(f"[arlo] {x}")
    for x in stale:
        print(f"[arlo] {x.as_posix()} is stale — run `arlo docs`")
    for r in model.rooms(hub):      # not a problem: the dashboard draws a room with no look plain
        if not ((model.CODE / "dashboard" / "static" / "world3d" / "rooms" / f"{r['id']}.js").is_file()
                or (hub / "lab" / "rooms3d" / f"{r['id']}.json").is_file()):
            print(f"[arlo] note: room {r['id']} has no look — it is drawn plain")
    if not probs and not stale:
        print("[arlo] ok")
    return 1 if probs or stale else 0


def cmd_docs(a) -> int:
    stale = lab_docs.render(_hub(a), check_only=a.check)
    for x in stale:
        print(f"[arlo] {'stale' if a.check else 'updated'}: {x.as_posix()}")
    return 1 if (a.check and stale) else 0


def cmd_extension(a) -> int:
    hub = _hub(a)
    exts = diff.extensions(hub)
    if a.action == "list":
        _out(a, [{k: x[k] for k in ("name", "title", "blurb", "files")} for x in exts],
             "\n".join(f"{x['name']:<20} {x['title']} — {x['blurb']}" for x in exts) or "no extensions (extensions/<name>/)")
        return 0
    x = next((e for e in exts if e["name"] == a.name), None)
    if not x:
        return _err(f"no extension {a.name!r} (extensions/<name>/extension.yaml)")
    if studies.in_agent_run():
        return _err(studies.PI_ONLY, 1)
    probs, said = diff.check_overlay(hub, x["path"], merge=True)
    print("\n".join(f"  it {line}" for line in said) or "  it changes nothing")
    if probs:
        print("\n".join(f"  problem: {p}" for p in probs))
        return 1
    if not _confirm(a, f"Add {x['title']} to this lab"):
        return 1
    diff.lay(x["path"], hub, merge=True)
    lab_docs.render(hub)
    print(f"added {x['title']} — `arlo workflow` shows it; `arlo new <study> --workflow …` files a study on it")
    return 0


def cmd_room(a) -> int:
    text = lab_docs.room_brief(_hub(a), a.room)
    if not text:
        return _err(f"no room {a.room!r} in the lab (or the PI's draft)")
    print(text)
    return 0


# ── panels, config ───────────────────────────────────────────────────────────────────────────────
def cmd_panels(a) -> int:
    return panels.main(["--hub", str(_hub(a)), "list"])


def cmd_panel(a) -> int:
    return panels.main(["--hub", str(_hub(a)), "show", a.id, *(["--study", a.study] if a.study else []),
                        *(["--json"] if a.json else [])])


def cmd_approve_collector(a) -> int:
    hub = _hub(a)
    p = panels.get(hub, a.id)
    if not p:
        return _err(f"no panel {a.id!r}")
    f = panels._collector(p)
    if f:
        print(f.read_text(encoding="utf-8", errors="replace"))
    if not _confirm(a, f"Let the collector of '{p['title']}' run on this machine (as you)"):
        return 1
    try:
        panels.approve_collector(hub, a.id, via="cli")
    except (ValueError, checkpoints.CheckpointError) as e:
        return _err(str(e), 1)
    print("approved — it runs from now on (until it changes)")
    return 0


def cmd_config(a) -> int:
    if a.action not in (None, "view") and studies.in_agent_run() \
            and os.environ.get("ARLOTOPE_RUN_SKILL") not in (rules.load(_hub(a)).get("config_procedures") or ["setup-lab", "configure"]):
        return _err("the lab's settings are the PI's — they change them in Settings (or ask for it in /configure)", 1)
    argv = ["view"] if a.action in (None, "view") else ["set", *a.rest, "--pi-approved"]
    return subprocess.run([sys.executable, str(HERE / "configure.py"), *argv]).returncode


def cmd_log(a) -> int:
    import knowledge
    try:
        result = knowledge.log_note(_hub(a), a)
    except (OSError, ValueError) as error:
        return _err(str(error), 1)
    _out(a, result, 'Saved log: '+result['id'])
    return 0


def cmd_open(a):
    from api_client import Client
    from urllib.parse import quote
    import webbrowser
    try:
        client=Client(_hub(a),a.port)
        if a.study:
            status,_headers,raw=client.request('GET','/api/state')
            if status!=200 or not any(item['id']==a.study for item in json.loads(raw).get('items',[])):
                return _err('Choose an existing study.')
        url=f'http://127.0.0.1:{client.port}/#/'+('study/'+quote(a.study,safe='') if a.study else '')
        print(url)
        if not a.print_link: webbrowser.open(url)
        return 0
    except (ValueError,OSError) as error:
        return _err(str(error))


def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="arlo", description="ARLOtope from a terminal",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("--hub", default=None)
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="verb", required=True)

    def add(name, fn, *args, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        p.add_argument('--hub',default=argparse.SUPPRESS,help='Lab folder')
        for x in args:
            if isinstance(x, tuple):
                p.add_argument(*x[0], **x[1])
            else:
                p.add_argument(x)
        p.set_defaults(fn=fn)
        return p

    yes = (["--yes", "-y"], {"action": "store_true"})
    note = (["--note"], {"default": ""})
    opt = lambda name: ([name], {"default": None})  # noqa: E731
    import api_client
    add('api',api_client.command, (['method'],{'choices':['GET','POST','HEAD','routes']}),
        (['path'],{'nargs':'?'}),opt('--data'),(['--query'],{'action':'append'}),
        (['--secret'],{'action':'append','help':'prompt privately for a body field'}),
        (['--port'],{'type':int}),(['--timeout'],{'type':float,'default':180}),opt('--output'))
    add('open',cmd_open,(['study'],{'nargs':'?'}),(['--port'],{'type':int}),(['--print'],{'action':'store_true','dest':'print_link'}))
    add("status", cmd_status)
    add("studies", cmd_studies)
    import knowledge
    knowledge.log_arguments(add('log', cmd_log, help='Save a study log with optional tags and evidence references'))
    add('tags', cmd_tags, 'study', (["--set"], {'default':None, 'help':'comma-separated labels; empty clears'}))
    add("new", cmd_new, "study", opt("--title"), opt("--workflow"), opt("--at"))
    add("move", cmd_move, "study", (["outcome"], {"nargs": "?"}), opt("--to"), note, yes)
    add("next", cmd_next, "study")
    add("brief", cmd_brief, "procedure", opt("--study"))
    add("checkpoint", cmd_checkpoint, "study", "checkpoint")
    add("approve", cmd_approve, "study", "checkpoint", note, yes, (["--start"], {"action": "store_true"}))
    add("revoke", cmd_revoke, "study", "checkpoint", yes, note)
    add("changes", cmd_changes, "study", "checkpoint", note, yes)
    add("approved", cmd_approved, "study", "checkpoint")
    add("checks", cmd_checks, "study", "checkpoint")
    add("approvals", cmd_approvals, (["study"], {"nargs": "?"}))
    add("flags", cmd_flags, (["study"], {"nargs": "?"}), (["--all"], {"action": "store_true"}))
    add("ack", cmd_ack, "flag", note)
    add("start", cmd_start, "procedure", (["study"], {"nargs": "?"}), (["--args"], {"default": ""}), opt("--backend"))
    add("ask", cmd_ask, "text", opt("--study"), opt("--backend"))
    add("runs", cmd_runs, (["--all"], {"action": "store_true"}))
    add("run", cmd_run, "run_id")
    add("answer", cmd_answer, "run_id", (["--pick"], {"action": "append"}), opt("--text"))
    add("reply", cmd_reply, "run_id", (["--text"], {"required": True}))
    add("stop", cmd_stop, "run_id")
    add("resume", cmd_resume, (["run_id"], {"nargs": "?"}))
    add("pause", cmd_pause, opt("--reason"))
    add("hold", cmd_hold, "study", opt("--reason"))
    add("release", cmd_release, "study")
    add("workflow", cmd_workflow, (["action"], {"nargs": "?", "default": "show", "choices": ("show", "set", "use", "rename-step")}),
        (["rest"], {"nargs": "*"}), yes)
    add("project", cmd_project, "study", "path")
    add("extension", cmd_extension, (["action"], {"nargs": "?", "default": "list", "choices": ("list", "install")}),
        (["name"], {"nargs": "?"}), yes)
    add("propose", cmd_propose, "what", (["--file"], {"required": True}), opt("--study"), (["--why"], {"default": ""}))
    add("check", cmd_check, opt("--design"))
    add("docs", cmd_docs, (["--check"], {"action": "store_true"}))
    add("room", cmd_room, "room")
    add("panels", cmd_panels)
    add("panel", cmd_panel, "id", opt("--study"))
    add("approve-collector", cmd_approve_collector, "id", yes)
    add("config", cmd_config, (["action"], {"nargs": "?", "choices": ("view", "set")}), (["rest"], {"nargs": "*"}))
    return ap


VERBS = {"status", "studies", "log", "tags", "new", "move", "next", "brief", "checkpoint", "approve", "revoke", "changes", "approved",
         "checks", "approvals", "flags", "ack", "start", "ask", "runs", "run", "answer", "reply", "stop", "resume", "pause", "hold",
         "release", "workflow", "project", "extension", "propose", "check", "docs", "room", "panels", "panel",
         "approve-collector", "config", "api", "open"}


def main(argv=None) -> int:
    a = build().parse_args(argv)
    from labfiles import ensure_lab_files
    if a.verb not in ('api','open'):
        ensure_lab_files(_hub(a))
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
