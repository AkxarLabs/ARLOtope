"""The PI's decisions in the dashboard — all through the kernel (tools/kernel/), the same code `arlotope` uses:

    checkpoint_view(q)   GET  /api/checkpoint?study=&id=      the sheet: where, evidence, checks, history
    decide(body)         POST /api/checkpoint/decide          approved | changes-requested | revoked; approving the
                                                              checkpoint a study waits at moves it on (+ start)
    run_checks(body)     POST /api/checkpoint/checks          run its checks now
    move(body)           POST /api/study/move                 move a study to any step, or off a shelf (revive)
    set_workflow(body)   POST /api/study/workflow             which workflow a study follows
    set_use(body)        POST /api/study/use                  a study's own procedure swaps (variants)
    hold_study(body)     POST /api/study/hold                 hold / release one study's launches
    ack_flag(body)       POST /api/flag/ack                   acknowledge a flag (releases its hold)

Nothing here writes into a document: a decision is a journal record.
"""

from __future__ import annotations

import ctx  # noqa: E402
import labfiles  # noqa: E402
import sources  # noqa: E402
import runops  # noqa: E402
from kernel import checkpoints, journal, model, studies, watch  # noqa: E402

executor = sources.executor


def checkpoint_view(q: dict) -> tuple[dict, int]:
    slug, cid = ctx.safe_id(q.get("study", "")), ctx.safe_id(q.get("id", ""))
    if not slug or not cid:
        return {"error": "which study and checkpoint?"}, 400
    try:
        with labfiles.read_batch():
            out = checkpoints.readiness(ctx.HUB, slug, cid)
            out["asking"] = _asking(slug, cid)
            out["title"] = (ctx.row(slug) or {}).get("title") or slug
    except checkpoints.CheckpointError as e:
        return {"error": str(e)}, 400
    return out, 200


def gate(body):
    slug, cid = ctx.need_slug(body, 'study'), ctx.safe_id(body.get('checkpoint') or '')
    if not slug or not cid or body.get('confirm') is not True:
        return {'error':'Choose a study and gate, and confirm the action.'}, 400
    try:
        import gate_reviews as judges
        lab = executor.Lab(ctx.HUB)
        cp = checkpoints.find(ctx.HUB, slug, cid)
        if body.get('review'):
            ready = checkpoints.readiness(ctx.HUB, slug, cid)
            if cp.get('approver') != 'agent' or not (ready['here'] or ready['waiting']):
                raise ValueError('This study is not waiting for an agent review here.')
            runs = judges.start_waiting(lab, slug, requested=cid, retry=True)
            if not runs:
                raise ValueError('No review queued. Check the evidence, active review and review limits.')
            result = {'ok':True,'run_id':runs[0]}
        else:
            if cp.get('confirm')=='type' and str(body.get('typed') or '').strip()!=slug:
                raise ValueError('Type the study identifier to make this decision.')
            rec = judges.choose(lab, slug, cid, str(body.get('choice') or ''), str(body.get('note') or '').strip())
            result = {'ok':True,'record':rec}
            try:
                from executor import enqueue
                import executor as runner
                runner.profile.start_step(lab, slug, enqueue, runner)
            except ValueError as error:
                result['note'] = 'Decision recorded. ' + str(error)
        ctx.pi_log({'action':'gate.review' if body.get('review') else 'gate.decision','study':slug,'checkpoint':cid,'choice':body.get('choice')})
        ctx.KICK.set()
        return result, 200
    except (ValueError, OSError) as error:
        return {'error':str(error)}, 400


def _asking(slug: str, cid: str) -> dict | None:
    """The latest run of this study that ended with it waiting here (its summary is the agent's case)."""
    if executor is None:
        return None
    s = studies.study(ctx.HUB, slug) or {}
    w = s.get("waiting") or {}
    run = str(w.get("by") or "")
    best = None
    try:
        for *_x, m in executor.all_runs(executor.Lab(ctx.HUB)):
            if m.get("subject") != slug:
                continue
            if (run.startswith("run:") and m.get("run_id") == run[4:]) or (m.get("report") or {}).get("needs_pi") == cid:
                if not best or (m.get("finished") or "") > (best.get("finished") or ""):
                    best = m
    except Exception:  # noqa: BLE001
        return None
    if not best:
        return None
    return {"run_id": best["run_id"], "skill": best.get("skill"), "backend": best.get("backend"),
            "summary": (best.get("report") or {}).get("summary"), "finished": best.get("finished"),
            "session": bool(best.get("session_id"))}


def _start_next(slug: str, backend=None) -> tuple[dict | None, str | None]:
    """Queue the work of the step a study stands at now. → (the launch result, its procedure)."""
    nxt = studies.next_for(ctx.HUB, slug)
    s=studies.study(ctx.HUB,slug)
    if s and s.get('active_steps') is not None:
        try:
            import lab_profile
            runs=lab_profile.start_graph(executor.Lab(ctx.HUB),slug,executor.enqueue,executor.RunSpec,**({'backend':backend} if backend else {}))
            ctx.KICK.set()
            return ({'ok':True,'run_id':runs[0],'runs':runs} if runs else None),'workflow'
        except (ValueError,OSError) as error:
            return {'failed':True,'error':str(error)},'workflow'
    if not nxt["procedure"]:
        return None, None
    res, code = runops.launch_run({"skill": nxt["procedure"], "target": slug, "confirm": True, "backend": backend},
                                  by="checkpoint")
    return (res if code == 200 else dict(res, failed=True)), nxt["procedure"]


def decide(body: dict) -> tuple[dict, int]:
    slug, cid = ctx.need_slug(body, "study"), ctx.safe_id(body.get("checkpoint") or "")
    decision = str(body.get("decision") or "approved")
    if not slug or not cid:
        return {"error": "which study and checkpoint?"}, 400
    if decision not in ("approved", "changes-requested", "revoked"):
        return {"error": "decision must be approved, changes-requested or revoked"}, 400
    if not body.get("confirm"):
        return {"error": "a decision needs explicit confirm"}, 400
    note = str(body.get("note") or "").strip()[:2000]
    try:
        cp = checkpoints.find(ctx.HUB, slug, cid)
        if decision == "changes-requested" and not note:
            return {"error": "say what should change; it goes to the agent"}, 400
        if cp.get("confirm") == "type" and decision == "approved" and str(body.get("typed") or "").strip() != slug:
            return {"error": f"type the study's name ({slug}) to approve this one"}, 400
        rec = checkpoints.decide(ctx.HUB, slug, cid, decision, by="pi", via="dashboard", note=note)
    except (checkpoints.CheckpointError, studies.StudyError) as e:
        return {"error": str(e)}, 400
    kind = {"approved": "checkpoint_approved", "revoked": "checkpoint_revoked",
            "changes-requested": "checkpoint_changes"}[decision]
    ctx.emit_hub(kind, idea=slug, detail=f"{cp['title']}: {decision} (PI via dashboard)", data={"checkpoint": cid})
    ctx.pi_log({"action": "checkpoint", "idea": slug, "checkpoint": cid, "decision": decision, "note": note or None})
    moved = (rec.get("moved") or {}).get("moved")
    out = {"ok": True, "record": rec, "note": {"approved": f"{cp['title']}: approved",
                                               "revoked": f"{cp['title']}: approval taken back",
                                               "changes-requested": "your changes went to the agent"}[decision]}
    if moved:
        label = (model.step(rec["moved"]["step"], ctx.HUB) or {}).get("label", rec["moved"]["step"])
        out["moved"] = rec["moved"]
        out["note"] = f"{cp['title']}: approved; {slug} moved to {label}"
        if body.get("start"):
            res, proc = _start_next(slug, body.get("backend"))
            if res is not None:
                out["launch"] = res
                if not res.get("failed"):
                    out["note"] += f", /{proc} started"
    if decision == "approved" and body.get("start") and not moved:
        out["warnings"] = ["Approval recorded. No workflow step moved, so no task was started. Continue the current task from its run."]
    if decision == "changes-requested":
        asking = _asking(slug, cid)
        if asking and asking.get("session") and executor is not None:
            try:
                executor.reply(executor.Lab(ctx.HUB), asking["run_id"],
                               f"The PI asked for changes before approving '{cp['title']}':\n\n{note}")
                out["sent_to"] = asking["run_id"]
            except Exception as e:  # noqa: BLE001
                out["warnings"] = [f"could not reach the agent ({e}); your note is recorded"]
    return out, 200


def run_checks(body: dict) -> tuple[dict, int]:
    slug, cid = ctx.need_slug(body, "study"), ctx.safe_id(body.get("checkpoint") or "")
    if not slug or not cid:
        return {"error": "which study and checkpoint?"}, 400
    try:
        cp = checkpoints.find(ctx.HUB, slug, cid)
    except checkpoints.CheckpointError as e:
        return {"error": str(e)}, 400
    res = checkpoints.run_checks(ctx.HUB, slug, cp, timeout=300)
    return {"ok": True, "results": res, "passed": all(r.get("code") == 0 for r in res.values())}, 200


def move(body: dict) -> tuple[dict, int]:
    """The PI moves a study to any step of its workflow — revive a parked one, send one back, skip ahead, or say
    where an outcome the workflow left open leads. Recorded with the PI's reason."""
    slug, to = ctx.need_slug(body, "study"), ctx.safe_id(body.get("to") or "")
    if not slug or not to:
        return {"error": "which study, and to which step?"}, 400
    if not body.get("confirm"):
        return {"error": "moving a study needs explicit confirm"}, 400
    note = str(body.get("note") or "").strip()[:500]
    try:
        res = studies.move_to(ctx.HUB, slug, to, note=note, by="pi")
    except studies.StudyError as e:
        return {"error": str(e)}, 400
    ctx.pi_log({"action": "move", "idea": slug, "to": to, "note": note or None})
    label = (model.step(to, ctx.HUB) or {}).get("label", to)
    out = {"ok": True, "result": res, "note": f"{slug} is at {label}"}
    if body.get("start") and res.get("moved"):
        launch, proc = _start_next(slug, body.get("backend"))
        if launch is not None:
            out["launch"] = launch
            if not launch.get("failed"):
                out["note"] += f"; /{proc} started"
    return out, 200


def set_workflow(body: dict) -> tuple[dict, int]:
    slug, wid = ctx.need_slug(body, "study"), ctx.safe_id(body.get("workflow") or "")
    if not slug or not wid:
        return {"error": "which study and workflow?"}, 400
    try:
        ev = studies.set_workflow(ctx.HUB, slug, wid, by="pi")
    except (studies.StudyError, model.ModelError) as e:
        return {"error": str(e)}, 400
    ctx.pi_log({"action": "set_workflow", "idea": slug, "workflow": wid})
    return {"ok": True, "note": f"{slug} follows {wid}" + (f": {ev['note']}" if ev.get("note") else "")}, 200


def set_use(body: dict) -> tuple[dict, int]:
    """A study's own swaps {procedure: variant} (an empty variant drops the swap)."""
    slug = ctx.need_slug(body, "study")
    use = body.get("use")
    if not slug or not isinstance(use, dict):
        return {"error": "which study, and use: {procedure: variant}"}, 400
    try:
        studies.set_use(ctx.HUB, slug, {str(k): str(v) for k, v in use.items() if v}, by="pi")
    except studies.StudyError as e:
        return {"error": str(e)}, 400
    ctx.pi_log({"action": "set_use", "idea": slug, "use": use})
    return {"ok": True, "note": f"{slug}'s procedures updated"}, 200


def hold_study(body: dict) -> tuple[dict, int]:
    slug = ctx.need_slug(body, "study")
    if not slug:
        return {"error": "which study?"}, 400
    if executor is None:
        return ctx.no_executor()
    from executor import pause  # noqa: PLC0415
    lab = executor.Lab(ctx.HUB)
    if body.get("hold", True):
        pause.hold(lab, slug, by="PI", reason=str(body.get("reason") or "")[:300])
        note = f"{slug} is on hold; nothing new starts for it"
    else:
        pause.release(lab, slug, by="PI")
        note = f"{slug} is released"
    ctx.pi_log({"action": "study.hold" if body.get("hold", True) else "study.release", "idea": slug})
    return {"ok": True, "note": note}, 200


def timeline(q: dict) -> tuple[dict, int]:
    """A study's history, as the journal has it: filed, moved, waited, approved, flagged — and the lab's step
    renames, which moved it too. Newest last."""
    slug = ctx.need_slug(q, "study")
    if not slug:
        return {"error": "which study?"}, 400
    acked = {e.get("flag") for e in journal.events(ctx.HUB, "lab", kinds=("ack",))}
    evs = journal.events(ctx.HUB, slug) + journal.events(ctx.HUB, "lab", kinds=("remap",))
    evs.sort(key=lambda e: str(e.get("ts") or ""))
    keep = ("ts", "kind", "by", "from", "to", "outcome", "checkpoint", "decision", "note", "step", "at", "workflow",
            "use", "path", "map", "level", "say", "run", "id", "node", "visit", "refs", "run_id", "selected_by", "workflow_revision")
    return {"ok": True, "events": [dict({k: e[k] for k in keep if k in e}, **({"acked": True} if e.get("id") in acked else {}))
                                    for e in evs][-300:]}, 200


def ack_flag(body: dict) -> tuple[dict, int]:
    fid = ctx.safe_id(body.get("flag") or "")
    if not fid:
        return {"error": "which flag?"}, 400
    try:
        watch.ack(ctx.HUB, fid, note=str(body.get("note") or "").strip()[:500])
    except ValueError as e:
        return {"error": str(e)}, 400
    ctx.pi_log({"action": "flag.ack", "flag": fid})
    return {"ok": True, "note": "acknowledged"}, 200


def history(q, save=False):
    import study_history
    slug=ctx.need_slug(q,'study')
    if not slug:
        return {'error':'Choose a study.'},400
    try:
        return (study_history.save(ctx.HUB,slug) if save else {'ok':True,**study_history.read(ctx.HUB,slug)}),200
    except (ValueError,OSError) as error:
        return {'error':str(error)},400
