"""Settings: whitelisted keys, parsed and saved into lab/config.yaml (labfiles.set_config), the PI's
documents, and first-run setup. (Research keys and notifications: keys.py; the
System page and compute.scheduler: system.py.)
"""

from __future__ import annotations

import re
import json
import sys
import time

import ctx  # noqa: E402
from executor import procs  # noqa: E402
import sources  # noqa: E402
import attention  # noqa: E402
from labs import lab_name  # noqa: E402

executor = sources.executor   # tools/executor, or None


# ── lab/config.yaml: one path for every setting ─────────────────────────────
# A table maps a setting to (its dotted path, a parser). Parsers raise ValueError with what they want.

def _enum(*allowed):
    def f(v):
        v = str(v).strip()
        if v not in allowed:
            raise ValueError(f"one of {', '.join(allowed)}")
        return v
    return f


def _num(lo, integer=False, hi=None):
    def f(v):
        x = int(v) if integer else float(v)
        if x != x or x < lo or (hi is not None and x > hi):
            raise ValueError(f"a {'whole ' if integer else ''}number ≥ {lo}" + (f" and ≤ {hi}" if hi is not None else ""))
        return int(x) if float(x).is_integer() else x
    return f


def _text(maxlen, rx=None):
    def f(v):
        v = str(v).strip()
        if not v or len(v) > maxlen or (rx and not re.match(rx, v)):
            raise ValueError("a short text value")
        return v
    return f


def _bool(v):
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def _writing(v):
    """A writing preset's name (lab_profile.WRITING), or the PI's own words for the style."""
    v = " ".join(str(v or "").split())
    if not v or len(v) > 800:
        raise ValueError("a preset (plain, ste80, ste) or your own description, up to 800 characters")
    return v


def _model(v):
    v = str(v).strip() or "inherit"
    if v != "inherit" and not executor.spec.MODEL_RE.match(v):
        raise ValueError("a model id or alias")
    return v


_P = ["agents", "programmatic"]


def _command(v):
    if isinstance(v, str):
        v = json.loads(v)
    if not isinstance(v, list) or not v or not all(isinstance(x, str) and x and '\0' not in x for x in v):
        raise ValueError('Use a JSON command array, for example ["my-agent", "--acp"].')
    return v


EXEC_CONFIG = {
    'acp_command': (_P + ['backends', 'acp', 'command'], _command),
    "backend": (_P + ["backend"], _enum(*(executor.backends.BACKENDS if executor else ("claude",)))),
    "model": (_P + ["model"], _model),
    # bypassPermissions is deliberately absent: it would remove the human-in-loop floor
    "permission_mode": (_P + ["permission_mode"], _enum("auto", "acceptEdits", "default", "plan", "dontAsk")),
    "max_minutes": (_P + ["max_minutes"], _num(5)),
    "max_concurrent": (_P + ["max_concurrent"], _num(1, True)),
    "max_concurrent_total": (_P + ["max_concurrent_total"], _num(1, True)),
    "hub_max_concurrent": (_P + ["hub_max_concurrent"], _num(1, True)),
    "daily_max_runs": (_P + ["daily_max_runs"], _num(0, True)),
    "daily_max_minutes": (_P + ["daily_max_minutes"], _num(0)),
    "chain_max_steps": (_P + ["chain_max_steps"], _num(1, True)),
    "follow_steps": (_P + ["follow_steps"], _bool),
    "writing": (_P + ["writing"], _writing),
    "live": (_P + ["live", "enabled"], _bool),
    "park_minutes": (_P + ["live", "park_minutes"], _num(1)),
    "permission_minutes": (_P + ["live", "permission_minutes"], _num(1)),
    "campaign_question_minutes": (_P + ["live", "campaign_question_minutes"], _num(1)),
    "linger_minutes": (_P + ["live", "linger_minutes"], _num(0)),
}
def _model(provider: bool = False):
    rx = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._:-]{0,79}" + (r"(?:/[A-Za-z0-9][A-Za-z0-9._:-]{0,79})?" if provider else "") + r")?$")

    def parse(v):
        v = "" if v is None else str(v).strip()
        if not rx.match(v):
            raise ValueError("a model name like sonnet or claude-sonnet-5-5" + (" (provider/model for opencode)" if provider else "")
                             + ", inherit, or blank")
        return v
    return parse


LAB_CONFIG = {
    "name": (["lab", "name"], _text(80)),
    "projects_root": (["lab", "projects_root"], _text(300, r"^[^\n\"]+$")),
    "max_concurrent_runs": (["compute", "max_concurrent_runs"], _num(1, True, 64)),
    "gpu_hours_budget": (["compute", "gpu_hours_budget"], _num(0, False, 10_000_000)),
    "oversight": (["oversight", "level"], _enum("standard", "strict")),
    "venue": (["writing", "venue"], _text(40, r"^[A-Za-z0-9 ._-]+$")),
    "page_limit": (["writing", "page_limit"], _num(1, True, 100)),
    "max_concurrent_projects": (["autopilot", "max_concurrent_projects"], _num(1, True, 16)),
    "loop_mode": (["loop", "mode"], _enum("execute", "explore")),
    "explore_rounds": (["loop", "explore_max_expansion_rounds"], _num(0, True, 20)),
    "in_project_approval": (["ideation", "in_project_approval"], _enum("pi", "campaign_auto")),
    # "off" is stored as YAML false (a bare `off` would read back as false anyway)
    "keep_awake": (["lab", "keep_awake"], _enum("auto", "off")),
    # ── the agents: which model each tool runs, and which model each kind of subagent gets ──
    "claude_model": (["agents", "programmatic", "backends", "claude", "model"], _model()),
    "claude_effort": (["agents", "programmatic", "backends", "claude", "effort"], _enum("", "low", "medium", "high", "xhigh", "max")),
    "codex_model": (["agents", "programmatic", "backends", "codex", "model"], _model()),
    "codex_effort": (["agents", "programmatic", "backends", "codex", "reasoning_effort"], _enum("", "minimal", "low", "medium", "high", "xhigh")),
    "opencode_model": (["agents", "programmatic", "backends", "opencode", "model"], _model(provider=True)),
    "opencode_variant": (["agents", "programmatic", "backends", "opencode", "variant"], _text(40, r"^[A-Za-z0-9._-]*$")),
    **{f"tier_{t}": (["agents", "tiers", t], _model()) for t in ("strong", "standard", "fast")},
    **{f"{r}_model": (["agents", f"{r}_model"], _model()) for r in ("reviewer", "runner", "overseer", "critic")},
    **{f"{r}_effort": (["agents", f"{r}_effort"], _enum("", "low", "medium", "high", "xhigh", "max")) for r in ("reviewer", "runner", "overseer", "critic")},
}
AGENT_KEYS = {k for k in LAB_CONFIG if k.endswith(("_model", "_effort", "_variant")) or k.startswith("tier_")}


def _parse(table: dict, changes) -> tuple[dict, str | None]:
    """{setting: value} → ({setting: parsed value}, None) — or ({}, what's wrong)."""
    if not isinstance(changes, dict) or not changes:
        return {}, "no changes"
    out = {}
    for k, v in changes.items():
        if k not in table:
            return {}, f"'{k}' can't be changed here"
        try:
            out[k] = table[k][1](v)
        except (TypeError, ValueError) as e:
            return {}, f"{k}: must be {e}"
    return out, None


def _save(table: dict, parsed: dict) -> str | None:
    """Parsed {setting: value} into lab/config.yaml. None, or what went wrong."""
    return ctx.set_config({".".join(table[k][0]): v for k, v in parsed.items()})


def set_executor_config(body: dict) -> tuple[dict, int]:
    """Executor settings (whitelisted, validated, all-or-nothing; confirmed and logged)."""
    if executor is None:
        return ctx.no_executor()
    if not body.get("confirm"):
        return {"error": "changing settings needs explicit confirm"}, 400
    parsed, err = _parse(EXEC_CONFIG, body.get("changes"))
    err = err or _save(EXEC_CONFIG, parsed)
    if err:
        return {"error": err}, 400
    ctx.pi_log({"action": "executor.config", "changes": parsed})
    attention.recheck_executor()   # re-probe (e.g. the new backend's CLI) on the next snapshot
    ctx.KICK.set()
    return {"ok": True, "changes": parsed, "note": f"saved {len(parsed)} setting(s) to lab/config.yaml"}, 200


PI_DOCS = {"research": "lab/RESEARCH.md", "system": "lab/SYSTEM.md", "open-questions": "lab/knowledge/OPEN-QUESTIONS.md"}


def doc_get(which: str) -> tuple[dict, int]:
    rel = PI_DOCS.get(which)
    if not rel:
        return {"error": "unknown document"}, 400
    p = ctx.HUB / rel
    text = ctx.read(p)
    if text is None and which == "system":
        text = ctx.read(ctx.labfiles.template(ctx.HUB, "SYSTEM.md")) or "# This machine\n"
        return {"ok": True, "rel": rel, "text": text, "exists": False}, 200
    return {"ok": True, "rel": rel, "text": text or "", "exists": text is not None}, 200


def doc_save(body: dict) -> tuple[dict, int]:
    rel = PI_DOCS.get(str(body.get("doc") or ""))
    if not rel:
        return {"error": "this document can't be edited here"}, 400
    text = body.get("text")
    if not isinstance(text, str) or len(text) > 200_000:
        return {"error": "text missing or too long"}, 400
    p = ctx.HUB / rel
    old = ctx.read(p) or ""
    p.parent.mkdir(parents=True, exist_ok=True)
    ctx.write_keep_eol(p, old, text)
    ctx.pi_log({"action": "doc.save", "doc": rel, "chars": len(text)})
    return {"ok": True, "note": f"saved {rel}"}, 200


def lab_config_get() -> tuple[dict, int]:
    cfg = ctx.config()
    out = {}
    for k, (path, _p) in LAB_CONFIG.items():
        node = cfg
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        out[k] = node
    out["name"] = out.get("name") or ctx.HUB.name
    out["keep_awake"] = "off" if out["keep_awake"] is False else (out["keep_awake"] or "auto")
    return {"ok": True, "config": out, "setup": setup_status(), "problems": ctx.config_problems()}, 200


def lab_config_set(body: dict) -> tuple[dict, int]:
    if not body.get("confirm"):
        return {"error": "changing lab settings needs explicit confirm"}, 400
    changes = dict(body.get("changes") or {})
    tier = changes.pop("budget_tier", None)
    parsed, err = _parse(LAB_CONFIG, changes) if changes else ({}, None)
    if err or (tier is None and not parsed):
        return {"error": err or "no changes"}, 400
    notes = []
    if tier is not None:
        if tier not in ("low", "medium", "high"):
            return {"error": "budget tier must be low, medium or high"}, 400
        r = procs.run([sys.executable, str(ctx.HUB / "tools" / "profiles.py"), "apply", tier],
                           cwd=str(ctx.HUB), capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return {"error": f"could not apply the {tier} budget profile: {(r.stderr or r.stdout)[-400:]}"}, 400
        notes.append(f"applied the {tier} budget profile")
    if parsed:
        err = _save(LAB_CONFIG, parsed)
        if err:
            return {"error": err}, 400
        notes.append(f"saved {len(parsed)} setting(s)")
    if AGENT_KEYS & set(changes):        # the subagents' role files carry their model: render them again
        r = procs.run([sys.executable, str(ctx.HUB / "tools" / "role_sync.py"), "render"], cwd=str(ctx.HUB),
                           capture_output=True, text=True, timeout=60)
        notes.append("role files updated" if r.returncode == 0 else f"role files NOT updated: {(r.stderr or r.stdout)[-300:]}")
    ctx.pi_log({"action": "lab.config", "changes": parsed, "budget_tier": tier})
    attention.recheck_executor()
    return {"ok": True, "changes": parsed, "note": "; ".join(notes) or "nothing changed"}, 200


# ── first-run setup ──────────────────────────────────────────────────────────

def setup_status() -> dict:
    cfg = ctx.config()
    done = (cfg.get("dashboard") or {}).get("setup_completed")
    rows = [r for r in sources.parse_registry() if r.get("id")]
    return {"completed": bool(done), "completed_at": str(done) if done else None,
            "fresh": not rows, "lab": {"name": lab_name(ctx.HUB), "path": str(ctx.HUB)}}


def setup_complete(body: dict) -> tuple[dict, int]:
    done = body.get("done", True)
    err = ctx.set_config({"dashboard.setup_completed": time.strftime("%Y-%m-%d") if done else None})
    if err:
        return {"error": err}, 400
    ctx.pi_log({"action": "setup.complete", "done": bool(done)})
    return {"ok": True}, 200
