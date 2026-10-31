"""A run's action tree, recorded as it happens — by the supervisor, never by a model.

    <run>.d/actions.jsonl     one line per thing the run's agents did, kept with the run (never pruned):

        {ts, agent, event, …}   agent: null for the run's own agent, else a subagent's key (its spawning call)
        attempt  {n}                          the run (re)started: a first start, a resume, a reply
        action   {kind, tool, summary}        a tool call finished (kind: trace_hook's activity words)
        spawn    {child, type, summary}       an agent started a subagent (child: its key)
        stop     {status, result}             a subagent ended

The supervisor (supervise._Recorder) writes it for every backend from the CLI's own stream. (A Claude CLI too
old to stream its subagents' events reports them through hooks into the worker logs instead.) tree() folds it
into agents with their actions, and outline() prints that tree as indented text — for an explainer, or anyone
looking back.
"""

from __future__ import annotations

import json
from pathlib import Path

from labfiles import append_jsonl, now

FILE = "actions.jsonl"
MAX_TEXT = 400


def record(rd: Path, agent: str | None, event: str, **fields) -> None:
    rec = {"ts": now(), "agent": agent, "event": event}
    for k, v in fields.items():
        if v not in (None, ""):
            rec[k] = v[:MAX_TEXT] if isinstance(v, str) else v
    try:
        append_jsonl(Path(rd) / FILE, rec)
    except OSError:
        pass                                    # a full disk never stops the run


def _events(rd: Path, strict: bool):
    try:
        with (Path(rd) / FILE).open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict):
                    yield event
    except FileNotFoundError:
        return
    except OSError:
        if strict:
            raise


def read(rd: Path, *, strict: bool = False) -> list[dict]:
    return list(_events(rd, strict))


def tree(rd: Path, *, strict: bool = False, include_actions: bool = True) -> dict:
    """{"agents": {id: {id, parent, type, summary, status, result, started, actions: [{ts, kind, tool, summary}]}},
    "attempts": n} — "main" is the run's own agent. Set include_actions=False for metadata only."""
    agents = {"main": {"id": "main", "parent": None, "type": None, "summary": None, "status": None, "actions": []}}
    attempts = 0
    for e in _events(rd, strict):
        who = e.get("agent") or "main"
        a = agents.setdefault(who, {"id": who, "parent": "main", "type": None, "summary": None, "status": None, "actions": []})
        ev = e.get("event")
        if ev == "attempt":
            attempts += 1
        elif ev == "action" and e.get("kind") != "spawn":     # (a spawn's own line stands for its call)
            if include_actions:
                a["actions"].append({k: e.get(k) for k in ("ts", "kind", "tool", "summary")})
        elif ev == "spawn" and e.get("child"):
            c = agents.setdefault(e["child"], {"id": e["child"], "actions": []})
            c.update(parent=who, type=e.get("type"), summary=e.get("summary"), status="working", started=e.get("ts"))
            if include_actions:
                a["actions"].append({"ts": e.get("ts"), "kind": "spawn", "tool": e.get("tool"), "summary": e.get("summary"),
                                     "child": e["child"]})
        elif ev == "stop":
            a.update(status=e.get("status"), result=e.get("result"))
    if not include_actions:
        for agent in agents.values():
            agent.pop('actions', None)
    return {"agents": agents, "attempts": attempts}


def outline(rd: Path, limit: int = 300) -> str:
    """The tree as indented text: each agent, then what it did, its subagents nested under it."""
    t = tree(rd)["agents"]
    lines: list[str] = []

    def walk(aid: str, depth: int) -> None:
        a, pad = t[aid], "  " * depth
        if aid != "main":
            lines.append(f"{pad}subagent {a.get('summary') or a.get('type') or ''} [{a.get('status') or '?'}]")
        for x in a["actions"]:
            if len(lines) >= limit:
                return
            if x.get("child") in t:
                walk(x["child"], depth + 1)
            else:
                lines.append(f"{pad}  {str(x.get('ts') or '')[11:19]} {x.get('kind') or ''} {x.get('summary') or x.get('tool') or ''}")

    walk("main", 0)
    return "\n".join(lines)
