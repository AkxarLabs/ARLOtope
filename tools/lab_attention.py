"""Lab attention projection shared by the dashboard and background notifications.

No queue is stored here. Items retain the executor's IDs, acknowledgements and lifecycle.
"""
from kernel import instructions, model, studies, watch
import labfiles
import panels
import time


def lab_items(hub, items: list[dict], escalations: list[dict], roster: list[dict], subagent_stuck_s=1200) -> list[dict]:
    """Lab-derived items in the executor's normalized shape (checkpoints, escalations, stalled runs,
    stuck subagents). Run-derived items come from executor.attention."""
    out = []
    for it in items:
        name = it.get("title") or it["id"]
        if it.get('blocked_reason'):
            out.append({'id':f"workflow-block:{it['id']}:{it.get('updated')}", 'kind':'outcome', 'sev':'block',
                        'ts':it.get('updated'), 'target':it['id'], 'idea':it['id'], 'run_id':None,
                        'title':name+': workflow paused', 'body':it['blocked_reason'], 'detail':{'study':it['id']},
                        'actions':[{'id':'move','label':'Review next step'}]})
        for cid in it.get("waiting") or []:
            cp = model.checkpoint(cid, it.get("workflow"), hub) or {"title": cid}
            from gate_reviews import scope
            study = studies.study(hub, it['id'])
            visit = (scope(hub, study, cp) or {}).get('visit', 1) if study and cp.get('id') else 1
            occurrence = f':{visit}' if visit > 1 else ''
            out.append({"id": f"cp:{it['id']}:{cid}{occurrence}", "kind": "checkpoint", "sev": "block", "ts": it.get("updated"),
                        "target": it["id"], "idea": it["id"], "run_id": None, "skill": None,
                        "title": cp["title"], "body": f"{name}: " + (cp.get("means") or "waiting for your approval"),
                        "detail": {"checkpoint": cid, "study": it["id"]},
                        "actions": [{"id": "checkpoint", "label": "review"}]})
        ask = it.get("asks")
        if ask:
            out.append({"id": f"ask:{it['id']}:{ask.get('outcome')}", "kind": "outcome", "sev": "block",
                        "ts": it.get("updated"), "target": it["id"], "idea": it["id"], "run_id": None, "skill": None,
                        "title": f"{name}: where should it go?",
                        "body": f"It reported `{ask.get('outcome')}` at {(model.step(ask.get('at') or '', hub) or {}).get('label', ask.get('at'))}"
                                + (f": {ask['note']}" if ask.get("note") else "") + ". The workflow leaves this to you.",
                        "detail": {"study": it["id"], "outcome": ask.get("outcome"), "at": ask.get("at")},
                        "actions": [{"id": "move", "label": "decide"}]})
        for f in it.get("flags") or []:
            out.append({"id": f"flag:{f['id']}", "kind": "flag", "sev": "block" if f.get("level") == "block" else "warn",
                        "ts": f.get("ts"), "target": it["id"], "idea": it["id"], "run_id": f.get("run"), "skill": None,
                        "title": f"{name}: {f.get('say')}" + (" — held" if f.get("hold") else ""),
                        "body": f.get("detail") or "", "detail": {"flag": f["id"], "study": it["id"], "rule": f.get("rule")},
                        "actions": [{"id": "ack", "label": "acknowledge"}]})
        for r in it.get("inflight") or []:
            if r.get("state") == "stalled":
                out.append({"id": f"stalled:{it['id']}:{r.get('run_id')}", "kind": "stalled", "sev": "warn",
                            "ts": None, "target": it["id"], "idea": it["id"], "run_id": None, "skill": None,
                            "title": f"Run {r.get('run_id')} looks stalled", "body": f"stage {r.get('stage')}. Open the run to check, or dismiss.",
                            "detail": r, "actions": [{"id": "dismiss", "label": "dismiss"}]})
    try:
        for pr in instructions.proposals(hub):
            what = "add instructions to " + ("the step " if pr.get("kind") == "step" else "role " if pr.get("kind") == "role" else "/")
            out.append({"id": f"proposal:{pr['id']}", "kind": "proposal", "sev": "warn", "ts": pr.get("ts"),
                        "target": pr.get("study") or "hub", "idea": pr.get("study"), "run_id": None, "skill": None,
                        "title": "An agent suggests: " + what + str(pr.get("name")) + (f" ({pr['study']})" if pr.get("study") else ""),
                        "body": pr.get("why") or pr.get("text", "")[:200], "detail": {"proposal": pr["id"]},
                        "actions": [{"id": "proposal", "label": "review"}]})
    except Exception:  # noqa: BLE001 — never blank the dashboard
        pass
    for f in watch.flags(hub, "lab"):        # about the lab, not one study (e.g. the guard failed)
        out.append({"id": f"flag:{f['id']}", "kind": "flag", "sev": "block" if f.get("level") == "block" else "warn",
                    "ts": f.get("ts"), "target": "hub", "idea": None, "run_id": f.get("run"), "skill": None,
                    "title": f"The lab: {f.get('say')}", "body": f.get("detail") or "",
                    "detail": {"flag": f["id"], "rule": f.get("rule")}, "actions": [{"id": "ack", "label": "acknowledge"}]})
    for e in escalations:
        out.append({"id": f"esc:{e['id']}", "kind": "escalation", "sev": "warn" if e.get("severity") != "high" else "block",
                    "ts": e.get("ts"), "target": e.get("source"), "idea": e.get("source"), "run_id": None,
                    "skill": None, "title": "Escalation from " + str(e.get("source")), "body": e.get("detail") or "",
                    "detail": e, "actions": [{"id": "reply", "label": "reply"}, {"id": "resolve", "label": "mark handled"}]})
    for w in roster:
        if w.get("is_subagent") and w["status"] == "idle" and not w.get("in_tool") and w.get("idle_s", 0) >= subagent_stuck_s:
            out.append({"id": f"subagent:{w['worker_id']}:{w.get('last_ts')}", "kind": "subagent", "sev": "warn",
                        "ts": w.get("last_ts"), "target": w.get("project") or "hub", "idea": w.get("idea"),
                        "run_id": w.get("run_id"), "skill": None,
                        "title": f"{w.get('role')} has been silent for {w['idle_s'] // 60} min",
                        "body": w.get("label") or "", "detail": {"worker_id": w["worker_id"]},
                        "actions": [{"id": "inspect", "label": "inspect"}, {"id": "dismiss", "label": "dismiss"}]})
    return out


def extra_items(hub):
    from executor import Lab
    extra = []
    import artifact
    try:
        for m in artifact.all_artifacts(hub, limit=None, state='asking'):
            extra.append({"id": f"artifact:{m['id']}", "kind": "artifact", "sev": "warn", "ts": m.get("created"),
                          "target": m.get("study") or "hub", "idea": m.get("study"), "run_id": m.get("run_id"),
                          "skill": m.get("skill"), "title": m["title"],
                          "body": f"asks you: {m.get('question') or m['title']}. The agent keeps working.",
                          "detail": {"artifact": m["id"]}, "actions": [{"id": "artifact", "label": "answer"}]})
    except (OSError, ValueError):
        pass
    try:   # a panel's alert (over a GPU budget, a run past its expected time, …)
        for a in panels.alert_items(hub):
            extra.append({"id": f"alert:{a['panel']}:{a.get('study') or ''}:{a['say'][:60]}", "kind": "alert",
                          "sev": "block" if a.get("level") == "block" else "warn", "ts": a.get("ts"),
                          "target": a.get("study") or "hub", "idea": a.get("study"), "run_id": None, "skill": None,
                          "title": a["say"], "body": a["title"] + (" · this study's launches are on hold" if a.get("hold") else ""),
                          "detail": {"panel": a["panel"], "study": a.get("study"), "held": a.get("hold")},
                          "actions": [{"id": "panel", "label": "open"}, {"id": "dismiss", "label": "dismiss"}]})
    except Exception:  # noqa: BLE001 — never blank the dashboard
        pass
    try:   # a campaign that stopped and needs the PI (stalled, paused on a sign-in problem) — one item for it
        from executor import campaigns as _camps  # noqa: PLC0415
        for c in _camps.all_states(Lab(hub)):
            if c.get("status") in ("stalled", "paused") and c.get("paused_reason") and c.get("paused_reason") != "paused by the PI":
                extra.append({"id": f"campaign:{c['name']}:{c.get('status')}:{len(c.get('cycles') or [])}", "kind": "campaign",
                              "sev": "block", "ts": (c.get("events") or [{}])[-1].get("ts"), "target": "hub", "idea": None,
                              "run_id": None, "skill": "autopilot", "title": f"Campaign {c['name']} stopped and needs you",
                              "body": c.get("paused_reason") or "", "detail": {"campaign": c["name"]},
                              "actions": [{"id": "campaign", "label": "open the campaign"}]})
            for q in (c.get("questions") or [])[-3:]:
                extra.append({"id": f"cq:{c['name']}:{q.get('ts')}", "kind": "question", "sev": "warn", "ts": q.get("ts"),
                              "target": "hub", "idea": None, "run_id": None, "skill": "autopilot",
                              "title": q.get("question") or "A campaign pass asked a question",
                              "body": f"left by campaign {c['name']} . It carried on without an answer. Reply with a note and the next pass reads it.",
                              "detail": {"campaign": c["name"]}, "actions": [{"id": "campaign", "label": "open the campaign"}]})
    except Exception:  # noqa: BLE001
        pass
    return extra


def stale_items(runs):
    out = []
    for run in runs:
        if run.get('schema') != 2 or run.get('status') not in ('starting', 'running', 'resuming'):
            continue
        heartbeat = labfiles.parse_ts(run.get('heartbeat'))
        age = run.get('heartbeat_age_s')
        if age is None and heartbeat:
            age = time.time() - heartbeat
        if age is not None and age > 120:
            out.append({'id': 'stale:' + run['run_id'], 'kind': 'stalled', 'sev': 'warn', 'ts': run.get('status_ts'),
                        'target': run.get('subject') or 'hub', 'idea': run.get('subject'), 'run_id': run['run_id'],
                        'skill': run.get('skill'), 'title': f"{run.get('command') or run['run_id']} has gone quiet",
                        'body': f'no heartbeat from its supervisor for {int(age // 60)} min; the scheduler is checking whether it is alive',
                        'detail': {'heartbeat_age_s': age}, 'actions': [{'id': 'tail', 'label': 'open'}, {'id': 'stop', 'label': 'stop'}]})
    return out


def for_notifications(lab):
    """Read authoritative state when no dashboard is open; use the same item builders."""
    from executor import attention, all_runs
    manifests = [(p, m) for _t, _w, p, m in all_runs(lab)]
    latest = {}
    for _path, run in manifests:
        slug = run.get('subject')
        if slug and run.get('status') in ('completed', 'failed', 'timeout', 'killed') and run.get('report'):
            if slug not in latest or (run.get('finished') or '') > (latest[slug].get('finished') or ''):
                latest[slug] = run
    items = []
    for row in studies.rows(lab.hub):
        waiting = row.get('waiting') or {}
        decisions = studies.decisions(lab.hub, row['id'])
        ids = [waiting['checkpoint']] if waiting.get('checkpoint') else []
        ids += [t['checkpoint'] for t in row.get('task_waits', [])]
        needs = ((latest.get(row['id']) or {}).get('report') or {}).get('needs_pi')
        if needs:
            ids.append(needs)
        row['waiting'] = [cid for cid in dict.fromkeys(ids)
                          if (decisions.get(cid) or {}).get('decision') != 'approved'
                          and model.checkpoint(cid, row.get('workflow'), lab.hub)]
        row['asks'] = waiting if waiting and not waiting.get('checkpoint') else None
        row['flags'] = watch.flags(lab.hub, row['id'])
        items.append(row)
    events = []
    for folder in [lab.bus, *[lab.bus_of(p) for _slug, p in lab.project_dirs()]]:
        events += labfiles.read_jsonl(folder / 'events.jsonl', tail=400)
    import hashlib
    def event_id(event):
        return str((event.get('data') or {}).get('id') or '').strip() or 'd?' + hashlib.sha1(
            f"{event.get('ts', '')}|{event.get('detail', '')}".encode()).hexdigest()[:8]
    resolved = {str((event.get('data') or {}).get('ref') or '').strip()
                for event in events if event.get('kind') == 'escalation_resolved'}
    escalations = [{'id': event_id(e), 'ts': e.get('ts'), 'source': e.get('source'),
                    'detail': e.get('detail', ''), 'severity': (e.get('data') or {}).get('severity')}
                   for e in events if e.get('kind') == 'escalation' and event_id(e) not in resolved]
    extras = lab_items(lab.hub, items, escalations, []) + extra_items(lab.hub) + stale_items([m for _path, m in manifests])
    result = attention.collect(lab, runs=manifests, extra=extras)
    checkpoints = {(item.get('idea'), item.get('detail', {}).get('checkpoint'))
                   for item in extras if item['kind'] == 'checkpoint'}
    extra_ids = {item['id'] for item in extras}
    return [item for item in result if not (
        item['kind'] == 'checkpoint' and item['id'] not in extra_ids
        and (item.get('idea'), item.get('detail', {}).get('checkpoint')) in checkpoints)]
