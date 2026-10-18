"""Who is working: the agent runs launched from here and every agent/subagent the tracer saw, joined into
one roster (run → session → subagents). Read-only and best-effort, like the rest of the snapshot.

    agents_in(dir) / launched_agents(project)   run manifests (<bus>/agents/*.json), compacted for the UI
    compact_run(manifest)                       the fields the dashboard renders
    workers(bus, project, project_ids)          the trace files (<bus>/workers/*.jsonl) folded into a roster
    join_runs(workers, runs) / link_workers()   nest each worker under its run and its spawning parent
    agents(runs, workers)                       every agent at work, in one shape: what the world draws
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import ctx
from ctx import labfiles

# ── workers (per-agent activity from .bus/workers/*.jsonl — the traceability feed) ──
#
# tools/trace_hook.py (a Claude Code hook) writes ONE file per agent/subagent. We fold each file into
# a roster entry: who it is (role + a readable label), what it's doing (status, the tool it is inside
# right now, recent actions), where (project / idea / worktree variant), who spawned it (parent) and
# what it handed back (result). Best-effort and non-canonical, like the rest of the bus.
#
# Tree: a subagent's lines carry the PARENT session's id in `session_id`; its parent's file holds a
# `spawn` line (tool_use_id, subagent type, description) and later a `return` line (the result
# packet). `link_workers` matches each child to its spawn, so the UI can draw
# run → session → subagents with every subagent's label, status and result.


RUN_KEYS = ("assignment", "explains", "context", "workflow_node", "workflow_visit", "assigned_step", "pending_questions", "external_interactions", "judge", "judge_error", "judge_result", "needs_followup", "assistant", "agent_id", "run_id", "backend", "role", "status", "started", "finished", "wall_seconds",
             "exit_code", "prompt_summary", "session_id", "skill", "command", "target", "subject", "level",
             "attempt", "reason", "status_ts", "pending_question", "report", "usage", "chain", "chain_child",
             "parent", "created_by", "created", "max_minutes", "n_actions", "denials", "mode", "label", "in_tool",
             "cli_version", "model_used", "repeat_minutes", "not_before", "answers_given", "schema",
             "kind", "args", "model", "effort", "max_repeats", "repeat_index", "campaign",
             "repeat_child", "campaign_cycle", "campaign_final", "failure_kind", "limit_reset", "campaign_retries",
             "brief_sha", "chain_step", "transport", "pending_permissions", "assumed", "limits", "pid")


def _r10(x) -> int | None:
    return None if x is None else int(x // 10 * 10)


def _call(t) -> dict | None:
    """A call in flight, as the dashboard shows it: what kind of work (the tracer's activity), the tool, a line."""
    if not isinstance(t, dict):
        return None
    return {"kind": t.get("kind") or "tool", "tool": t.get("tool"), "summary": (t.get("summary") or "")[:200] or None,
            "since": t.get("ts") or t.get("since")}


def compact_run(m: dict) -> dict:
    """A run manifest → the fields the dashboard renders. Time-varying numbers are rounded to 10 s
    so the SSE signature (which ignores `now`) doesn't change every tick."""
    out = {k: m.get(k) for k in RUN_KEYS}
    out["run_id"] = out["run_id"] or out["agent_id"]
    out["last_message"] = (m.get("last_message") or "")[:1200] or None
    out["last_text"] = (m.get("last_text") or "")[:400] or None
    la = m.get("last_action")
    out["last_action"] = {"tool": la.get("tool"), "summary": (la.get("summary") or "")[:200], "ts": la.get("ts"),
                          "kind": la.get("kind")} if isinstance(la, dict) else None
    out["in_tool"] = _call(m.get("in_tool"))
    now = time.time()
    st = m.get("status")
    started = labfiles.parse_ts(m.get("started"))
    if st in ("starting", "running", "resuming") and started:
        prior = sum(float(a.get("wall_seconds") or 0) for a in (m.get("attempts") or [])[:-1])
        cur = labfiles.parse_ts(((m.get("attempts") or [{}])[-1] or {}).get("started")) or started
        out["elapsed_s"] = _r10(prior + max(0.0, now - cur))
    else:   # a finished run's wall time never changes → exact (only LIVE numbers are rounded for SSE)
        out["elapsed_s"] = round(float(m.get("wall_seconds") or 0)) if m.get("wall_seconds") is not None else None
    hb = labfiles.parse_ts(m.get("heartbeat"))
    out["heartbeat_age_s"] = _r10(now - hb) if (hb and st in ("starting", "running", "resuming")) else None
    subs = m.get("subagents") or {}
    out["subagents"] = [{"id": k, "type": v.get("type"), "description": v.get("description"),
                         "status": v.get("status"), "n_actions": v.get("n_actions"),
                         "last_action": (v.get("last_action") or {}).get("summary"),
                         "in_tool": _call(v.get("in_tool")), "depth": v.get("depth"),
                         "agent_id": v.get("agent_id"), "said": (v.get("last_text") or "")[:200] or None,
                         "result": (v.get("result") or "")[:600] or None,
                         "started": v.get("started"), "finished": v.get("finished"),
                         "parent": v.get("parent"), "session": v.get("session"), "background": v.get("background")}
                        for k, v in list(subs.items())[-40:]]
    out["n_qa"] = len(m.get("qa") or [])
    d = m.get("digest")
    if isinstance(d, dict):     # what the run did (kernel/watch.py) — the lists trimmed for the snapshot
        f = d.get("files") or {}
        out["digest"] = {**{k: d.get(k) for k in ("outcome", "commands", "denials", "flags", "notable")},
                         "written": len(f.get("written") or []), "deleted": len(f.get("deleted") or []),
                         "commits": int(f.get("commits") or 0),
                         "files": (f.get("written") or [])[:30], "gone": (f.get("deleted") or [])[:30]}
    return out


def launched_agents(project_dir: Path) -> list[dict]:
    """Headless agents launched into this project (tools/executor runs, or older launcher
    launches) — each is a <project>/.bus/agents/<id>.json manifest; the full transcript lives next to
    it as <id>.stream.jsonl. Best-effort, absent dir => []."""
    return agents_in(project_dir / ".bus" / "agents")


def agents_in(adir: Path) -> list[dict]:
    if not adir.exists():
        return []
    out = []
    for f in sorted(adir.glob("*.json")):
        try:
            m = json.loads(labfiles.read_text(f))
        except json.JSONDecodeError:
            continue
        if isinstance(m, dict):
            out.append(compact_run(m))
    return out


_WORKER_DONE_KEEP_S = 1800   # a finished worker stays on the roster (greyed, with its result) this long


_WORKER_DEAD_S = 7200        # a file with no 'stop' untouched this long = a session that died uncleanly


_WORKER_STALE_S = 150        # no activity, no open tool, no stop -> idle (not "working")


SUBAGENT_STUCK_S = 1200     # an idle, unfinished subagent this long is surfaced as needing a look


_MAX_RECENT = 40




_WORKER_CACHE: dict[str, tuple] = {}


_WORKER_IN_TOOL_MAX_S = 3 * 86400   # inside one tool call (a long training run, a SLURM queue wait) this long


LIVE_IDS: set = set()               # session / run ids of runs that were live at the last snapshot


def _fold_worker(lines: list[dict]) -> dict:
    """One worker file's lines → its roster facts (pure; cached by file mtime+size)."""
    role, idea, proj, variant, sid = "orchestrator", None, None, None, None
    run_id = subject = depth = None
    stop_i, start_i = -1, -1
    actions, spawns, returns = [], [], {}
    open_tool, result, n_actions = None, None, 0
    for i, ln in enumerate(lines):
        if ln.get("role"):
            role = ln["role"]
        if ln.get("idea"):
            idea = ln["idea"]
        if ln.get("project"):
            proj, variant = ln["project"], ln.get("variant") or variant
        if ln.get("session_id") and not sid:
            sid = ln["session_id"]
        if ln.get("run_id") and not run_id:
            run_id, subject, depth = ln["run_id"], ln.get("subject") or subject, ln.get("depth", depth)
        ev = ln.get("event")
        if ev == "start":
            start_i = i
        elif ev == "stop":
            stop_i = i
            if ln.get("result"):
                result = ln["result"]
        elif ev == "begin":
            open_tool = {"tool": ln.get("tool"), "summary": ln.get("summary"), "since": ln.get("ts"),
                         "kind": ln.get("kind"), "tool_use_id": ln.get("tool_use_id")}
        elif ev in ("action", "spawn", "return"):
            if ev == "spawn":
                spawns.append({"tool_use_id": ln.get("tool_use_id"), "type": ln.get("spawns") or "general-purpose",
                               "summary": ln.get("summary"), "ts": ln.get("ts"), "background": ln.get("background")})
            if ev == "return" and ln.get("tool_use_id"):
                returns[ln["tool_use_id"]] = ln.get("result")
            if ln.get("child") and ln.get("tool_use_id"):   # codex / opencode name the child exactly
                for sp in spawns:
                    if sp.get("tool_use_id") == ln["tool_use_id"]:
                        sp["child"] = ln["child"]
            if ev in ("action", "return"):
                open_tool = None          # the call that was in flight has finished
            if ev != "return":
                n_actions += 1
            actions.append({"ts": ln.get("ts"), "text": ln.get("summary") or ln.get("tool") or ev,
                            "kind": ln.get("kind") or ev, "event": ev})
    done = stop_i >= 0 and stop_i >= start_i    # a later 'start' (a resumed session) reopens it
    return {"role": role, "idea": idea, "project_hint": proj, "variant": variant, "session_id": sid,
            "run_id": run_id, "subject": subject, "depth": depth,
            "done": done, "open_tool": None if done else open_tool, "result": result,
            "spawns": spawns, "returns": returns, "n_actions": n_actions,
            "recent_actions": actions[-_MAX_RECENT:], "started": lines[0].get("ts"),
            "last_ts": lines[-1].get("ts")}


def scan(bus_dir: Path, project: str | None = None, projects: set | None = None) -> list[dict]:
    known = {"orchestrator", *ctx.tool("kernel").model.roles(ctx.HUB)}   # the lab's roles (agent-roles/*.yaml)
    wdir = bus_dir / "workers"
    if not wdir.exists():
        return []
    now = time.time()
    out = []
    for f in sorted(wdir.glob("*.jsonl")):
        try:
            st = f.stat()
        except OSError:
            continue
        age = now - st.st_mtime
        key = str(f)
        hit = _WORKER_CACHE.get(key)
        if age > max(_WORKER_DEAD_S, _WORKER_DONE_KEEP_S) and f.stem not in LIVE_IDS and\
                not (hit and hit[2].get("open_tool") and age < _WORKER_IN_TOOL_MAX_S):
            continue   # never parsed: roster cost stays O(recent) before trace_hook's retention sweep
        if hit and hit[0] == st.st_mtime and hit[1] == st.st_size:
            fold = hit[2]
        else:
            lines = labfiles.read_jsonl(f)
            if not lines:
                continue
            fold = _fold_worker(lines)
            _WORKER_CACHE[key] = (st.st_mtime, st.st_size, fold)
        if fold["done"] and age > _WORKER_DONE_KEEP_S:
            continue
        if fold["done"]:
            status = "done"
        elif fold["open_tool"]:
            status = "working"            # inside a tool call — however long it takes
        elif age > _WORKER_STALE_S:
            status = "idle"
        else:
            status = "working"
        wid = f.stem
        # attribution: an explicit project bus wins; a hub-bus worker whose calls named a registered
        # project (its /improve worktree, its runs/…) is promoted to that project so the project's
        # lab view and worker count include it
        proj = project
        if not proj:
            for cand in (fold["project_hint"], fold["idea"]):
                if cand and projects and cand in projects:
                    proj = cand
                    break
        sid = fold["session_id"]
        is_sub = bool(sid and sid != wid)
        out.append({
            "worker_id": wid,
            "role": fold["role"],
            "role_known": fold["role"] in known,
            "status": status,
            "project": proj,
            "idea": fold["idea"] or (proj if proj != project else None),
            "variant": fold["variant"],
            "session_id": sid,
            "parent": sid if is_sub else None,
            "is_subagent": is_sub,
            "children": [],
            "label": None,
            "spawns": fold["spawns"][-1]["type"] if fold["spawns"] else None,
            "spawned": fold["spawns"][-20:],
            "started": fold["started"],
            "last_ts": fold["last_ts"],
            "idle_s": int(age // 10 * 10),
            "in_tool": fold["open_tool"],
            "result": fold["result"],
            "n_actions": fold["n_actions"],
            "recent_actions": fold["recent_actions"],
            "run_id": fold.get("run_id"),
            "subject": fold.get("subject"),
            "depth": fold.get("depth"),
            "_returns": fold["returns"],
        })
    return out


def link_workers(workers: list[dict]) -> list[dict]:
    """Match each subagent to the spawn line in its parent's log (same session, same type, in order)
    → a readable label, the spawn id, and the result packet if the child's own stop didn't carry it.
    Fills parent.children. Mutates and returns `workers`."""
    by_id = {w["worker_id"]: w for w in workers}
    kids: dict[str, list[dict]] = {}
    for w in workers:
        if w["is_subagent"]:
            kids.setdefault(w["parent"], []).append(w)
    for root_id, children in kids.items():
        root = by_id.get(root_id)
        children.sort(key=lambda c: c.get("started") or "")
        if root is None:
            continue
        # every spawn in this session — the root's and its subagents' own (a subagent of a subagent)
        owners = [root] + children
        free = [(o, s) for o in owners for s in (o.get("spawned") or [])]
        for c in children:
            before = [(o, s) for (o, s) in free if o is not c and (s.get("ts") or "") <= (c.get("started") or "~")]
            match = next(((o, s) for (o, s) in free if s.get("child") == c["worker_id"]), None) or\
                next(((o, s) for (o, s) in before if s["type"] == c["role"] and not s.get("child")), None) or\
                (next(((o, s) for (o, s) in before if s["type"] == "general-purpose"), None)
                 if c["role"] == "general-purpose" else None)
            owner = root
            if match:
                free.remove(match)
                owner, sp = match
                desc = (sp.get("summary") or "").split(": ", 2)[-1]
                c["label"] = desc[:160] or None
                c["spawn_id"] = sp.get("tool_use_id")
                c["background"] = bool(sp.get("background"))
                if not c.get("result") and sp.get("tool_use_id"):
                    c["result"] = (owner.get("_returns") or {}).get(sp["tool_use_id"])
            c["parent"] = owner["worker_id"]
            c["depth_in_session"] = 1 if owner is root else 2
            owner.setdefault("children", [])
            if c["worker_id"] not in owner["children"]:
                owner["children"].append(c["worker_id"])
            if not c.get("project") and root.get("project"):
                c["project"] = root["project"]
            if not c.get("run_id") and root.get("run_id"):
                c["run_id"] = root["run_id"]
    for w in workers:
        w.pop("_returns", None)
        w.pop("spawned", None)
    return workers


def join_runs(workers: list[dict], runs: list[dict]) -> None:
    """A headless run's orchestrator IS a worker (its session id names the trace file): tag it with
    the run so the roster nests run → session → subagents, and give it the run's role/label."""
    by_sid = {r["session_id"]: r for r in runs if r.get("session_id")}
    by_run = {r["run_id"]: r for r in runs if r.get("run_id")}
    for w in workers:
        r = by_run.get(w.get("run_id")) or by_run.get(w["worker_id"]) or by_sid.get(w["worker_id"]) or\
            (by_sid.get(w.get("session_id")) if w.get("is_subagent") else None)
        if not r:
            w["interactive"] = not w.get("is_subagent")   # a session the PI started by hand
            if w["interactive"] and not w.get("label"):
                w["label"] = "Terminal session (started outside the dashboard)"
            continue
        w["run_id"] = r["run_id"]
        if r.get("subject") and not w.get("idea") and not w.get("project"):
            w["idea"] = r["subject"]
        ended = r.get("status") in ("completed", "failed", "timeout", "killed", "cancelled")
        if not w.get("is_subagent"):
            w["label"] = r.get("command") or r.get("prompt_summary")
            if r.get("status") == "waiting_input" and w["status"] != "done":
                w["status"] = "idle"
        if ended and w["status"] != "done":      # a run that ended ended every agent it ran, its subagents too
            w["status"] = "done"


# ── the agents at work: one roster for the world, the rail and the Runs page ──
#
# A run launched from here is its own record: the supervisor keeps, from the CLI's stream, the run's main agent
# and every subagent it spawned (who spawned whom, the call each is in, how each ended). A session nobody launched
# from here (yours, in a terminal) is known only from its trace files. Both become the same rows, so whatever
# draws them has one loop and no special cases.

LIVE = ("starting", "running", "resuming")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
STALL_S = 180          # a live run whose heartbeat is older than this has gone quiet


def _due(r: dict, now: float) -> bool:
    nb = labfiles.parse_ts(r.get("not_before")) if r.get("not_before") else None
    return not nb or nb <= now


def agents(runs: list[dict], roster: list[dict]) -> list[dict]:
    """Every agent at work in the lab, one row each, parents before their children:

        {id, parent, depth, run_id, sub, worker_id, role, label, backend, status, doing, last, said,
         subject, target, skill, background, interactive}

    `status`: working · idle · asking (it waits for the PI) · queued · stalled. `doing`: the call it is in right
    now — {kind, tool, summary, since}, kind from the tracer's vocabulary (read · search · edit · run · bash · git ·
    spawn · ask · plan · skill · mcp · tool) — or None between calls. A subagent's `parent` is the agent that
    spawned it (a subagent of a subagent nests under its own parent, not the run)."""
    now = time.time()
    out: list[dict] = []
    known = {r.get("run_id") for r in runs}
    traces = {}   # a run's subagent → its trace file (the supervisor's, or the hooks')
    for w in roster:
        for k in (w.get("spawn_id"), w["worker_id"]):
            if k:
                traces[(w.get("run_id"), k)] = w["worker_id"]
    for r in sorted(runs, key=lambda x: x.get("created") or x.get("started") or ""):
        st, rid = r.get("status"), r.get("run_id")
        if not rid or (st not in (*LIVE, "waiting_input", "queued") and not r.get('needs_followup')) or (st == "queued" and not _due(r, now)):
            continue
        main, doing = f"run:{rid}", r.get("in_tool")
        asking = st == "waiting_input" or bool(r.get("pending_permissions")) or r.get('needs_followup') or (doing or {}).get("kind") == "ask"
        status = "queued" if st == "queued" else "asking" if asking else \
            "stalled" if (r.get("heartbeat_age_s") or 0) > STALL_S else "working"
        base = {"run_id": rid, "backend": r.get("backend"), "subject": r.get("subject"), "target": r.get("target"),
                "skill": r.get("skill"), "interactive": False}
        out.append({**base, "id": main, "parent": None, "depth": 0, "sub": None, "worker_id": rid,
                    "role": r.get("role") or "orchestrator", "label": r.get("label") or r.get("command") or r.get("skill"),
                    "status": status, "doing": doing if st in LIVE else None,
                    "last": (r.get("last_action") or {}).get("summary"), "said": None, "background": False})
        if st not in LIVE:
            continue          # a queued or parked run has no subagent at work
        subs = {x["id"]: x for x in (r.get("subagents") or [])}
        working = {k for k, x in subs.items() if x.get("status") == "working"}

        def up(k):            # the nearest ancestor still at work (the run itself, failing that)
            seen = set()
            while k and k not in working and k not in seen:
                seen.add(k)
                k = (subs.get(k) or {}).get("parent")
            return f"{main}/{k}" if k in working else main
        for k in sorted(working, key=lambda x: (subs[x].get("depth") or 1, subs[x].get("started") or "")):
            sa = subs[k]
            parent = up(sa.get("parent"))
            out.append({**base, "id": f"{main}/{k}", "parent": parent, "depth": 1 + parent.count("/"), "sub": k,
                        "worker_id": traces.get((rid, k)) or traces.get((rid, f"{rid}.{_SAFE.sub('-', k)[:48]}"))
                        or traces.get((rid, sa.get("agent_id"))),
                        "role": sa.get("type") or "general-purpose", "label": sa.get("description"),
                        "status": "working", "doing": sa.get("in_tool"), "last": sa.get("last_action"),
                        "said": sa.get("said"), "background": bool(sa.get("background"))})
    by_id = {w["worker_id"]: w for w in roster}
    for w in sorted(roster, key=lambda x: (1 if x.get("is_subagent") else 0, x.get("started") or "")):
        if w["status"] == "done" or (w.get("run_id") and w["run_id"] in known):
            continue          # a run's own agents come from the run
        parent = w.get("parent") if w.get("is_subagent") else None
        if parent and (parent not in by_id or by_id[parent]["status"] == "done"):
            parent = w.get("session_id") if w.get("session_id") in by_id else None
        t = w.get("in_tool")
        out.append({"id": f"w:{w['worker_id']}", "parent": f"w:{parent}" if parent else None,
                    "depth": (w.get("depth_in_session") or 1) if parent else 0, "run_id": None, "sub": None,
                    "worker_id": w["worker_id"], "role": w.get("role") or "orchestrator", "label": w.get("label"),
                    "backend": w.get("backend"), "status": "stalled" if w["status"] == "stalled" else w["status"],
                    "doing": _call(t), "last": ((w.get("recent_actions") or [{}])[-1] or {}).get("text"),
                    "said": None, "subject": w.get("project") or w.get("idea"), "target": w.get("project"),
                    "skill": None, "background": bool(w.get("background")), "interactive": bool(w.get("interactive"))})
    return out
