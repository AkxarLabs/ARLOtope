"""What needs the PI, and the executor's status — the dashboard's half of "Needs you". Run-derived items
come from the executor (tools/executor/attention.py); this adds what only the lab's record shows: checkpoints
waiting for the PI's approval, outcomes the PI decides, flags the watches raised, escalations, stalled training
runs, quiet subagents, agents' proposals, campaigns that stopped, and runs whose supervisor went silent.

    collect(items, escalations, workers, runs)  every item, in the executor's normalized shape
    executor_status() / recheck_executor()      launching, the CLIs, caps and load (CLI probes cached 30 s)
"""

from __future__ import annotations

import time

import ctx
from workers import SUBAGENT_STUCK_S

try:
    import executor
except Exception:  # noqa: BLE001 — a broken/missing executor must never blank the dashboard
    executor = None


def lab_items(items: list[dict], escalations: list[dict], roster: list[dict]) -> list[dict]:
    from lab_attention import lab_items as shared
    return shared(ctx.HUB, items, escalations, roster, SUBAGENT_STUCK_S)


def collect(items, escalations, roster, runs) -> list[dict]:
    extra = lab_items(items, escalations, roster)
    from lab_attention import extra_items, stale_items
    extra += extra_items(ctx.HUB) + stale_items(runs or [])
    if executor is None:
        return extra
    try:
        lab = executor.Lab(ctx.HUB)
        manifests = []
        for _t, _w, path, m in executor.all_runs(lab):
            manifests.append((path, m))
        brake = executor.brake(lab, [m for _p, m in manifests])
        got = executor.attention.collect(lab, runs=manifests, extra=extra, brake_reason=brake)
        ours = {x.get("id") for x in extra}
        mine = {(x.get("idea"), (x.get("detail") or {}).get("checkpoint")) for x in extra if x.get("kind") == "checkpoint"}
        # a run that stopped at a checkpoint is the same thing the checkpoint item already says (compared by id:
        # collect() hands items back as copies carrying their `seen` mark)
        return [x for x in got if not (x.get("kind") == "checkpoint" and x.get("id") not in ours
                                       and (x.get("idea"), (x.get("detail") or {}).get("checkpoint")) in mine)]
    except Exception:  # noqa: BLE001 — never blank the dashboard
        return extra


_EXEC_CACHE: dict = {"ts": 0.0, "key": None, "value": None}
ctx.on_change(lambda _old, _new: _EXEC_CACHE.update(ts=0))


def recheck_executor(cli: bool = False) -> None:
    """The next snapshot re-reads the executor's status; `cli` also re-probes the agent CLIs (after a
    sign-in, an install, a backend change)."""
    _EXEC_CACHE["ts"] = 0
    if cli and executor is not None:
        executor.backends.forget_checks()


def executor_status() -> dict:
    """Launching possible? Which CLIs exist? Caps and load. The CLI probe (a subprocess) is cached 30 s."""
    if executor is None:
        return {"available": False, "enabled": False, "reason": "tools/executor is missing"}
    lab = executor.Lab(ctx.HUB)
    key = str(lab.hub)
    if _EXEC_CACHE["key"] == key and time.time() - _EXEC_CACHE["ts"] < 30 and _EXEC_CACHE["value"]:
        base = dict(_EXEC_CACHE["value"])
    else:
        try:
            base = executor.health(lab)
        except Exception as e:  # noqa: BLE001
            base = {"enabled": False, "error": str(e)}
        _EXEC_CACHE.update(ts=time.time(), key=key, value=base)
    prog = lab.prog()
    runs = [m for *_x, m in executor.all_runs(lab)]
    # settings the PI can change here: always fresh (the cached part is only the CLI probes)
    base.update(backend=prog.get("backend") or "claude", permission_mode=prog.get("permission_mode") or "auto",
                caps=executor.caps(lab), config={**(base.get('config') or {}),
                    **{k: prog.get(k) for k in executor.CONFIG_KEYS if k in prog},
                    'acp_command': ((prog.get('backends') or {}).get('acp') or {}).get('command') or []})
    base.update(available=True, enabled=bool(prog.get("enabled")),
                active=sum(1 for m in runs if m.get("status") in executor.ACTIVE),
                queued=sum(1 for m in runs if m.get("status") == "queued"),
                waiting=sum(1 for m in runs if m.get("status") in executor.PAUSED))
    lt = base.get("last_tick")
    if isinstance(lt, dict):
        base["last_tick"] = {k: v for k, v in lt.items() if k != "ts"}   # keep the SSE signature stable
    base.pop("daily", None)
    return base
