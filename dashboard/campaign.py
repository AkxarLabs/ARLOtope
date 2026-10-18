"""Campaigns: write lab/campaigns/<date>-<slug>.md from the form and record the PI's approval of it (with the
checkpoints it may approve), the PI's controls on a running one (pause, resume, stop, take a checkpoint back,
hold a study, answer, withdraw), and the walk-away preflight.
"""

from __future__ import annotations

import re
import time

import ctx  # noqa: E402
import sources  # noqa: E402
import attention  # noqa: E402

executor = sources.executor   # tools/executor, or None


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return (s[:40] or "campaign").strip("-")


def delegable(hub=None) -> list[dict]:
    """The checkpoints a campaign may be allowed to approve (approver `me-or-campaign`), across workflows."""
    model = ctx.tool("kernel").model
    seen, out = set(), []
    for w in model.workflows(hub or ctx.HUB):
        for c in w["checkpoints"]:
            if c.get("approver") == "me-or-campaign" and c["id"] not in seen:
                seen.add(c["id"])
                out.append({"id": c["id"], "title": c["title"], "workflow": w.get("title") or w["id"],
                            "means": c.get("means", "")})
    return out


def campaign_create(body: dict) -> tuple[dict, int]:
    if not body.get("confirm"):
        return {"error": "approving a campaign needs explicit confirm"}, 400
    f = body.get("fields") or {}
    direction = str(f.get("direction") or "").strip()
    if not direction:
        return {"error": "describe the research direction"}, 400
    try:
        n = lambda k, lo=0, d=None: max(lo, int(f.get(k) if f.get(k) not in (None, "") else d))  # noqa: E731
        ideas, parallel = n("ideas", 1, 3), n("parallel", 1, 1)
        budget_total = str(f.get("compute_total") or "").strip() or "—"
        full_budget = str(f.get("full_budget") or "").strip() or "—"
        open_q = n("max_open_questions", 0, 2)
        rounds, lines_per = n("explore_rounds", 0, 1), n("explore_lines", 0, 2)
    except (TypeError, ValueError):
        return {"error": "numbers must be whole numbers"}, 400
    try:
        hours = float(f.get("hours") if f.get("hours") not in (None, "") else 12)
        agent_hours = float(f.get("agent_hours") if f.get("agent_hours") not in (None, "") else 0)
        cycle_minutes = float(f.get("cycle_minutes") if f.get("cycle_minutes") not in (None, "") else 90)
        repeat_minutes = float(f.get("repeat_minutes") if f.get("repeat_minutes") not in (None, "") else 20)
        # a hard $ cap on what the campaign's runs spend (estimated from token use); blank / 0 = no cap
        spend_cap = float(f.get("spend_cap") if f.get("spend_cap") not in (None, "") else 0)
    except (TypeError, ValueError):
        return {"error": "hours, minutes and the spend cap must be numbers"}, 400
    if spend_cap < 0 or spend_cap != spend_cap or spend_cap > 1e6:
        return {"error": "the spend cap must be 0 (no cap) or a positive dollar amount"}, 400
    if not (0 < hours <= 24 * 30) or agent_hours < 0 or not (10 <= cycle_minutes <= 24 * 60) or not (5 <= repeat_minutes <= 24 * 60):
        return {"error": "hours 0–720; longest pass 10–1440 min; a pass every 5–1440 min"}, 400
    allowed = {c["id"]: c for c in delegable()}
    delegates = [str(x) for x in (f.get("delegates") or []) if str(x) in allowed]
    if len(delegates) != len(f.get("delegates") or []):
        return {"error": "a campaign may only approve checkpoints that allow it (approver: me-or-campaign)"}, 400
    deadline = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + hours * 3600))
    wall = str(f.get("wall_clock") or "").strip() or f"{hours:g} h (until {deadline})"
    mode = str(f.get("mode") or "execute")
    if mode not in ("execute", "explore"):
        return {"error": "loop mode must be execute or explore"}, 400
    for v in (direction, budget_total, full_budget, wall):
        if len(v) > 600 or "\n## " in v:
            return {"error": "keep each field short (no section headings)"}, 400
    tpl = ctx.read(ctx.labfiles.template(ctx.HUB, "loop/CAMPAIGN.md"))
    if tpl is None:
        return {"error": "templates/loop/CAMPAIGN.md is missing"}, 500
    date = time.strftime("%Y-%m-%d")
    slug = _slugify(str(f.get("name") or direction))
    name = f"{date}-{slug}.md"
    dest = ctx.LAB / "campaigns" / name
    i = 2
    while dest.exists():
        name = f"{date}-{slug}-{i}.md"
        dest = ctx.LAB / "campaigns" / name
        i += 1
    t = tpl.replace("{{date}}-{{slug}}", name[:-3])
    t = t.replace("**Research direction(s):** <!-- from the PI -->", f"**Research direction(s):** {direction}")
    t = t.replace("carry up to ___ ideas", f"carry up to {ideas} ideas")
    t = t.replace("≤ ___ ideas in flight", f"≤ {parallel} ideas in flight")
    t = t.replace("- none — every checkpoint waits for the PI",
                  "\n".join(f"- **{allowed[c]['title']}** (`{c}`)" for c in delegates)
                  or "- none — every checkpoint waits for the PI")
    t = t.replace("- Budget: ___ in total; each study's full-scale runs within ___",
                  f"- Budget: {budget_total} in total; each study's full-scale runs within {full_budget}")
    t = t.replace("with ≤ ___ open questions", f"with ≤ {open_q} open questions")
    t = re.sub(r"\*\*Loop mode for spawned projects:\*\* `execute`", f"**Loop mode for spawned projects:** `{mode}`", t)
    t = t.replace("caps: ___ expansion rounds, ___ new lines/round", f"caps: {rounds} expansion rounds, {lines_per} new lines/round")
    t = re.sub(r"\*\*Total wall-clock:\*\* ___ \([^)]*\)", f"**Total wall-clock:** {wall}", t)
    t = t.replace("**Total compute:** ___", f"**Total compute:** {budget_total}"
                  + (f" · agent time ≤ {agent_hours:g} h" if agent_hours else "")
                  + (f" · spend ≤ ${spend_cap:,.2f} (hard cap: the lab stops the campaign there)" if spend_cap else ""))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(t, encoding="utf-8")
    rel = f"lab/campaigns/{name}"
    try:
        ctx.tool("kernel").checkpoints.decide_lab(ctx.HUB, f"campaign:{name[:-3]}", "approved", by="pi", via="dashboard",
                                                  note=("may approve: " + ", ".join(delegates)) if delegates else "")
    except ValueError as e:
        return {"error": f"could not record the approval: {e}"}, 400
    ctx.emit_hub("campaign_signed", detail=f"campaign {rel} approved (PI via dashboard)")
    ctx.pi_log({"action": "campaign.approve", "file": rel, "fields": f})
    out = {"ok": True, "file": rel, "note": f"campaign approved: {rel}", "delegates": delegates,
           "spend_cap_usd": spend_cap or None}
    if body.get("launch"):
        try:
            from executor import campaigns  # noqa: PLC0415 — tools/ is on sys.path via sources
            lab = sources.executor.Lab(ctx.HUB)
            sources.executor.check_enabled(lab)
            st = campaigns.create(lab, rel, hours=hours, agent_minutes=agent_hours * 60, cycle_minutes=cycle_minutes,
                                  repeat_minutes=repeat_minutes, delegates=delegates,
                                  backend=body.get("backend") or None, spend_usd=spend_cap)
        except Exception as e:  # noqa: BLE001 — the brief is approved either way; say why it didn't start
            out["note"] = f"campaign approved ({rel}) but not started: {e}"
            out["warnings"] = [str(e)]
            return out, 200
        ctx.pi_log({"action": "campaign.start", "file": rel, "hours": hours, "agent_hours": agent_hours,
                   "cycle_minutes": cycle_minutes, "repeat_minutes": repeat_minutes, "delegates": delegates,
                   "spend_cap_usd": spend_cap or None})
        out.update(campaign=st["name"], note=f"campaign approved and started; the lab keeps it going until {deadline}")
    return out, 200


CAMPAIGN_ACTIONS = ("pause", "resume", "stop", "revoke", "hold", "unhold", "answer", "withdraw")


def campaign_control(body: dict) -> tuple[dict, int]:
    """The PI's controls on a running campaign (the campaign card). `withdraw` takes back the PI's approval of
    the whole campaign: the keeper approves nothing more, and the campaign stops."""
    name, action = str(body.get("name") or ""), str(body.get("action") or "")
    if action not in CAMPAIGN_ACTIONS:
        return {"error": f"action must be one of {', '.join(CAMPAIGN_ACTIONS)}"}, 400
    if action in ("stop", "revoke", "withdraw") and not body.get("confirm"):
        return {"error": "confirm first"}, 400
    try:
        from executor import campaigns  # noqa: PLC0415
        lab = sources.executor.Lab(ctx.HUB)
        if action == "withdraw":
            ctx.tool("kernel").checkpoints.decide_lab(ctx.HUB, f"campaign:{name}", "revoked", by="pi", via="dashboard")
            st = campaigns.control(lab, name, "stop")
        else:
            st = campaigns.control(lab, name, action, study=body.get("study") or None,
                                   text=body.get("checkpoint") or body.get("text"), index=body.get("index"))
    except (ValueError, OSError) as e:
        return {"error": str(e)}, 400
    ctx.pi_log({"action": f"campaign.{action}", "campaign": name, "study": body.get("study"),
                "checkpoint": body.get("checkpoint")})
    words = {"pause": "paused", "resume": "resumed", "stop": "stopping; it writes its final report",
             "revoke": "that checkpoint is yours again for this campaign", "hold": "held from campaign approvals",
             "unhold": "released", "answer": "answered; the next pass gets it",
             "withdraw": "approval withdrawn; the campaign stops and approves nothing more"}
    return {"ok": True, "note": words[action], "status": st.get("status")}, 200


def campaign_preflight(q: dict) -> tuple[dict, int]:
    """Can the lab run on its own right now? What a walk-away start needs, checked."""
    ex = sources.executor
    if ex is None:
        return {"ok": True, "ready": False, "checks": [{"id": "executor", "ok": False, "label": "The executor is available",
                                                        "detail": "tools/executor is missing"}]}, 200
    lab = ex.Lab(ctx.HUB)
    prog = lab.prog()
    status = attention.executor_status()
    backend = prog.get("backend") or "claude"
    cli = (status.get("clis") or {}).get(backend) or {}
    checks = [{"id": "launch", "ok": bool(prog.get("enabled")), "label": "Agents may be started from the dashboard",
               "detail": "Settings → Limits & permissions → Let the dashboard start agents for you", "fix": "settings/autonomy"},
              {"id": "cli", "ok": bool(cli.get("found") or cli.get("path") or cli.get("version")),
               "label": f"The {backend} CLI is installed", "detail": cli.get("version") or cli.get("error") or "",
               "fix": "settings/agents"}]
    li = cli.get("logged_in")
    checks.append({"id": "auth", "ok": li is not False, "label": f"{backend} is signed in",
                   "detail": "" if li else ("not signed in: Settings → Agents & models → Sign in…" if li is False else
                                            "can't tell from here; checked on the first run"), "fix": "settings/agents"})
    pm = str(prog.get("permission_mode") or "auto")
    checks.append({"id": "perm", "ok": pm in ("auto", "acceptEdits", "dontAsk"),
                   "label": "Agents won't stop to ask for tool permissions", "detail": f"permission mode: {pm}",
                   "fix": "settings/autonomy"})
    root = lab.projects_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".newts-write-test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    checks.append({"id": "projects", "ok": writable, "label": "The projects folder is writable", "detail": str(root),
                   "fix": "settings/lab"})
    import shutil as _sh  # noqa: PLC0415
    tex = bool(_sh.which("latexmk") or _sh.which("pdflatex") or _sh.which("tectonic"))
    checks.append({"id": "latex", "ok": tex, "warn_only": True, "label": "LaTeX is installed (papers compile to PDF)",
                   "detail": "" if tex else "without it papers stay .tex (the paper checks need the PDF)"})
    try:
        from executor import awake  # noqa: PLC0415
        aw = awake.status()
    except Exception:  # noqa: BLE001
        aw = {"available": False, "detail": ""}
    checks.append({"id": "awake", "ok": bool(aw.get("available")), "warn_only": True,
                   "label": "The computer stays awake while agents work", "detail": aw.get("detail") or ""})
    return {"ok": True, "checks": checks, "ready": all(c["ok"] for c in checks if not c.get("warn_only"))}, 200
