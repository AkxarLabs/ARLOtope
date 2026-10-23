"""Read-only world model for the ARLOtope dashboard.

The lab's files ARE the database — this module only reads them, tolerantly:
  - lab/journal.jsonl      -> the studies: where each stands, what it waits for, the PI's decisions, flags
                              (through the kernel, tools/kernel/)
  - lab/.bus/events.jsonl  -> hub events;  <project>/.bus/events.jsonl -> per-project events
  - lab/.bus/directives.jsonl + ack events -> the directive threads (pending/seen/acted)
  - <project>/runs/registry.jsonl          -> completed-run record
  - <project>/runs/<id>/meta.json + metrics.jsonl -> in-flight liveness (status.py semantics)
  - lab/campaigns/*.md     -> latest campaign log (if any)

Everything is best-effort: a malformed line is skipped, a missing file is empty, a moved
project path is reported as unreachable — never a crash. Nothing here writes.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx  # noqa: E402 — the lab being shown (ctx.HUB / ctx.LAB): one place, re-pointed live
import tagging

# The executor (tools/executor) is optional for the dashboard: import it from THIS repo's tools/
# (never from a monkeypatched HUB), and degrade to observe-and-sign if it's missing.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
try:
    import executor  # noqa: E402
except Exception:  # noqa: BLE001 — a broken/missing executor must never blank the dashboard
    executor = None
from kernel import instructions, model, studies, watch  # noqa: E402 — the lab's definition and record
import labfiles  # noqa: E402 — the lab's files, read one way (tools/labfiles.py)
import workers  # noqa: E402 — who is working: runs + the traced agents
import attention  # noqa: E402 — what needs the PI; the executor's status


# ── registry ──────────────────────────────────────────────────────────────────

def parse_registry() -> list[dict]:
    return labfiles.registry_rows(ctx.HUB)


def projects_root() -> Path:
    return labfiles.projects_root(ctx.HUB)


def _project_path(row: dict) -> Path | None:
    """A registry row's project dir, preferring its explicit Project column."""
    return labfiles.project_dir(ctx.HUB, row["id"], row)


# ── run liveness (status.py semantics) ────────────────────────────────────────

def _inflight_runs(project_dir: Path, log_interval: float = 60.0) -> list[dict]:
    runs_dir = project_dir / "runs"
    if not runs_dir.exists():
        return []
    out = []
    for run_dir in runs_dir.iterdir():
        meta_path = run_dir / "meta.json"
        if not (run_dir.is_dir() and meta_path.exists()):
            continue
        try:
            meta = json.loads(labfiles.read_text(meta_path))
        except json.JSONDecodeError:
            continue
        if meta.get("status") == "queued":   # waiting in the machine's job scheduler
            sch = meta.get("scheduler") or {}
            out.append({"run_id": meta.get("run_id", run_dir.name), "stage": meta.get("stage"), "elapsed_s": 0,
                        "budget_min": (meta.get("budget") or {}).get("max_minutes"), "state": "queued",
                        "last": {}, "job": sch.get("job"), "scheduler": sch.get("kind"), "queued": meta.get("queued")})
            continue
        if meta.get("status") != "running":
            continue
        stream = run_dir / "metrics.jsonl"
        elapsed = time.time() - meta_path.stat().st_ctime
        last, stalled = {}, False
        if stream.exists() and stream.stat().st_size:
            age = time.time() - stream.stat().st_mtime
            stalled = age > 2 * log_interval
            tail = labfiles.read_text(stream).strip().splitlines()
            if tail:
                try:
                    rec = json.loads(tail[-1])
                    last = {k: v for k, v in rec.items()
                            if isinstance(v, (int, float)) and k not in ("t", "step")}
                except json.JSONDecodeError:
                    pass
        budget = (meta.get("budget") or {}).get("max_minutes")
        out.append({
            "run_id": meta.get("run_id", run_dir.name), "stage": meta.get("stage"),
            "elapsed_s": round(elapsed), "budget_min": budget,
            "state": "stalled" if stalled else "alive", "last": last,
        })
    return out


def _best_metric(rows: list[dict]) -> dict | None:
    """A small sparkline-able series of the last completed runs' first numeric metric."""
    series = []
    for r in rows:
        if r.get("status") != "completed":
            continue
        m = r.get("metrics") or {}
        num = next((v for v in m.values() if isinstance(v, (int, float))), None)
        if num is not None:
            series.append({"run_id": r.get("run_id"), "value": num})
    return {"series": series[-20:]} if series else None


# ── checkpoints and flags: what each study waits for, what was decided, what the watches saw ────────

def _checkpoint_view(row: dict, runs_by_subject: dict) -> dict:
    """{workflow, checkpoints: {id: latest decision}, waiting: [checkpoint ids], asks: {outcome, at} | None,
    flags: [open flags], slipped: [{id, why}]} for one study.

    waiting: the checkpoint the study waits at (the journal says so: an agent reported the outcome that leads
    past it). asks: an outcome the workflow doesn't route — the PI says where it goes. A `during` checkpoint
    its latest run stopped at (the run footer's needs_pi) waits too. slipped: what a checkpoint's own watch
    found done past it without approval (a flag)."""
    slug = row["id"]
    st = studies.decisions(ctx.HUB, slug)
    w = row.get("waiting") or {}
    waiting = [w["checkpoint"]] if w.get("checkpoint") and (st.get(w["checkpoint"]) or {}).get("decision") != "approved" \
        and model.checkpoint(w["checkpoint"], row.get("workflow"), ctx.HUB) else []      # (one the definition still has)
    waiting = list(dict.fromkeys(waiting + [t['checkpoint'] for t in row.get('task_waits', [])]))
    asks = {"outcome": w.get("outcome"), "at": w.get("at"), "note": w.get("note")} if w and not w.get("checkpoint") else None
    last = runs_by_subject.get(slug)
    needs = ((last or {}).get("report") or {}).get("needs_pi")
    if needs and needs not in waiting and (st.get(needs) or {}).get("decision") != "approved" \
            and model.checkpoint(needs, row.get("workflow"), ctx.HUB):
        waiting.append(needs)
    flags = watch.flags(ctx.HUB, slug)
    slipped = [{"id": str(f["rule"]).split(":", 1)[0], "why": f.get("detail") or f.get("say")}
               for f in flags if ":" in str(f.get("rule") or "")]
    return {"workflow": row.get("workflow"), "checkpoints": st, "waiting": waiting, "asks": asks,
            "flags": [{k: f.get(k) for k in ("id", "ts", "level", "say", "detail", "hold", "rule", "run")} for f in flags],
            "slipped": slipped}


_NB_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _notebook_status() -> dict:
    """Latest lab/notebook entry + its age — makes hard-rule-11 write-back cadence visible ('last
    write-back 2 d ago') so a PI can see a lab that's stopped recording. Best-effort; {} if absent.
    Age is derived from the entry's DATED FILENAME, not st_mtime: a `git clone`/`checkout`/`pull`
    resets mtimes, which would make a lab that stopped recording weeks ago read as fresh. Selecting by
    the filename string also means no stat() in the hot path (no glob→stat TOCTOU race)."""
    nb = ctx.LAB / "notebook"
    if not nb.exists():
        return {}
    dated = [f for f in nb.glob("*.md") if f.name.lower() != "readme.md"]
    if not dated:
        return {}
    latest = max(dated, key=lambda f: f.name)   # ISO-dated names sort chronologically as strings
    m = _NB_DATE.match(latest.name)
    if not m:
        return {"latest": latest.name}          # undated name → surface it, but no age we can trust
    try:
        entry_epoch = time.mktime((int(m.group(1)), int(m.group(2)), int(m.group(3)), 0, 0, 0, 0, 0, -1))
    except (ValueError, OverflowError):
        return {"latest": latest.name}
    return {"latest": latest.name, "age_hours": round(max(0.0, (time.time() - entry_epoch) / 3600.0), 1)}


def editor_scheme() -> str:
    """URI scheme for the 'open in editor' deep-links (vscode|cursor|…|none). The dashboard is
    local-only, so a `<scheme>://file/<abs-path>` opens the PI's own editor. Default vscode."""
    return str((ctx.config().get("dashboard") or {}).get("editor", "vscode")).strip().lower()


# ── paper artifacts (the compiled PDF a back-half session produced) ────────────
#
# A paper lives in the HUB at studies/<slug>/paper/ (main.tex → main.pdf via /write-paper's blocking
# latexmk gate; figures synced into figures/). We only report whether the PDF exists + its mtime, so
# the viewer's button shows and the snapshot diff (hence the SSE push) auto-refreshes it on recompile.

def _paper_status(slug: str) -> dict | None:
    pdir = ctx.HUB / "studies" / slug / "paper"
    pdf = pdir / "main.pdf"
    try:
        if not pdf.is_file():
            return None
        out = {"pdf": True, "mtime": int(pdf.stat().st_mtime)}
        tex = pdir / "main.tex"
        if tex.is_file():
            out["tex"] = str(tex.resolve())   # absolute, for the "edit source" editor link
        return out
    except OSError:
        return None


def _claims_count(slug: str) -> int:
    """How many claims studies/<slug>/paper/claims.yaml holds (0 if absent/empty). Drives the
    'claims (N)' button — claims.yaml can exist before the PDF, so this is independent of _paper_status."""
    f = ctx.HUB / "studies" / slug / "paper" / "claims.yaml"
    if not f.is_file():
        return 0
    doc = labfiles.load_yaml(f)
    cl = doc.get("claims") if isinstance(doc, dict) else None
    # count only dict items, matching serve.claims_map's filter so "claims (N)" == rendered rows
    return sum(1 for c in cl if isinstance(c, dict)) if isinstance(cl, list) else 0


# ── directives (threads with pending/seen/acted state) ────────────────────────

def _synth_id(d: dict) -> str:
    """Stable synthesized id for a hand-written/legacy directive with no id — the same scheme
    tools/lab_bus.py uses, so the dashboard and the agent `inbox` name the same directive."""
    import hashlib
    return "d?" + hashlib.sha1(f"{d.get('ts', '')}|{d.get('text', '')}".encode()).hexdigest()[:8]


def _directive_threads(bus_dir: Path, default_target: str = "hub") -> list[dict]:
    directives = labfiles.read_jsonl(bus_dir / "directives.jsonl")
    events = labfiles.read_jsonl(bus_dir / "events.jsonl")
    withdrawn = {d.get("ref") for d in directives if d.get("kind") == "withdraw"}
    acks: dict[str, dict] = {}
    for e in events:
        if str(e.get("kind", "")).startswith("directive_"):
            ref = (e.get("data") or {}).get("ref")
            if not ref:
                continue
            state = e["kind"].split("_", 1)[1]           # seen | done | blocked
            prev = acks.get(ref)
            # terminal acks are STICKY (matches lab_bus.unresolved_directives): once done/blocked, a
            # later 'seen' can't reopen the directive — else an out-of-order ack reopens it in the
            # dashboard while the agent considers it closed.
            if prev and prev["state"] in ("done", "blocked") and state == "seen":
                continue
            acks[ref] = {"state": state, "ts": e.get("ts"),
                         "note": (e.get("data") or {}).get("note"),
                         "evidence": (e.get("data") or {}).get("evidence")}
    threads = []
    for d in directives:
        if d.get("kind") == "withdraw":
            continue
        did = d.get("id") or _synth_id(d)               # surface id-less directives, like the inbox does
        ack = acks.get(did)
        state = "withdrawn" if did in withdrawn else (ack["state"] if ack else "pending")
        threads.append({"id": did, "ts": d.get("ts"), "text": d.get("text", ""),
                        "state": state, "ack": ack, "scope": "hub" if default_target == "hub" else "project",
                        "target": d.get("target") or default_target,   # the record's own target wins (M2)
                        "kind": d.get("kind", "note"), "action": d.get("action"),
                        "args": d.get("args")})
    return threads


def _escalations(events: list[dict]) -> list[dict]:
    """Unresolved escalations, paired with their escalation_resolved events by ref. An escalation
    with no matching resolver stays 'needs you'; once an agent emits escalation_resolved (data.ref =
    the escalation id) it drops off — so a handled escalation stops nagging the bell forever (its
    id defaults to a synthesized hash when the emitter didn't set one)."""
    def _eid(e: dict) -> str:
        return str((e.get("data") or {}).get("id") or "").strip() or _synth_id(
            {"ts": e.get("ts"), "text": e.get("detail", "")})
    resolved = {str((e.get("data") or {}).get("ref") or "").strip()
                for e in events if e.get("kind") == "escalation_resolved"}
    out = []
    for e in events:
        if e.get("kind") != "escalation":
            continue
        eid = _eid(e)
        if eid in resolved:
            continue
        out.append({"id": eid, "ts": e.get("ts"), "source": e.get("source"),
                    "detail": e.get("detail", ""),
                    "severity": (e.get("data") or {}).get("severity")})
    return out


# ── campaigns (/autopilot) — first-class grouping of delegated projects ─────────
#
# A campaign is a PI-approved /autopilot brief (lab/campaigns/*.md, optional YAML frontmatter) that works
# across studies; the executor's keeper holds its live state (see _autonomy_view).

def _first_heading(text: str) -> str | None:
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()
    return None


def _excerpt(text: str, n: int = 240) -> str:
    body = text
    if body.lstrip().startswith("---"):
        parts = body.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]
    body = "\n".join(ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#"))
    return (body[:n] + "…") if len(body) > n else body


def campaigns(rows: list[dict] | None = None) -> list[dict]:
    rows = rows if rows is not None else parse_registry()
    cmap: dict[str, dict] = {}
    cdir = ctx.LAB / "campaigns"
    for f in (sorted(cdir.glob("*.md")) if cdir.exists() else []):
        text = labfiles.read_text(f)
        meta = {}
        if text.lstrip().startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    meta = {}
        name = str(meta.get("name") or f.stem)
        projects = meta.get("projects") or meta.get("ideas") or []
        if isinstance(projects, str):
            projects = [projects]
        cmap[name] = {
            "name": name, "title": meta.get("title") or _first_heading(text) or name,
            "status": str(meta.get("status") or "active"),
            "signed": meta.get("signed_by") or meta.get("signed"),
            "started": meta.get("started"), "budget": meta.get("budget") or meta.get("envelope"),
            "projects": [str(p).strip() for p in projects], "file": f"campaigns/{f.name}",
            "detail": _excerpt(text),
        }
    return list(cmap.values())


# ── the snapshot ──────────────────────────────────────────────────────────────

def _artifacts_view() -> list[dict]:
    import artifacts  # noqa: PLC0415 — artifacts imports this module
    return artifacts.snapshot_view()




@labfiles.read_batch()
def snapshot() -> dict:
    import remote_projects
    rows = parse_registry()
    hub_bus = ctx.LAB / ".bus"
    hub_directives = _directive_threads(hub_bus)
    items, all_events = [], []
    proj_ids = {r["id"] for r in rows if _project_path(r) is not None}
    roster = workers.scan(hub_bus, None, proj_ids)
    hub_runs = workers.agents_in(hub_bus / "agents")

    for e in labfiles.read_jsonl(hub_bus / "events.jsonl", tail=400):
        all_events.append(e)
    last_run: dict = {}   # each study's latest finished run (its footer may say which checkpoint it stopped at)
    if executor is not None:
        try:
            for *_x, m in executor.all_runs(executor.Lab(ctx.HUB)):
                if m.get("subject") and m.get("status") in executor.TERMINAL and m.get("report"):
                    prev = last_run.get(m["subject"])
                    if not prev or (m.get("finished") or "") > (prev.get("finished") or ""):
                        last_run[m["subject"]] = m
        except Exception:  # noqa: BLE001 — never blank the dashboard
            pass

    for row in rows:
        pdir = _project_path(row)
        remote = remote_projects.location(row.get('project'))
        item = {
            "id": row["id"], "title": row["title"], "state": row["state"], "tags":row.get('tags', []),
            "updated": row.get("touched") or row["updated"], "next": row["next"], "finished": row["finished"], "use": row.get("use") or {}, "was": row.get("was"),
            "has_project": pdir is not None, "project_dir": str(pdir) if pdir else None,
            "project_mode": model.skill_meta(ctx.read(ctx.HUB / "studies" / row["id"] / "IDEA.md") or "").get("project_mode"),
            **_checkpoint_view(row, last_run),
            "paper": _paper_status(row["id"]),   # the compiled PDF on disk (drives the paper viewer)
            "claims": _claims_count(row["id"]),  # number of claims in claims.yaml (drives the claims↔artifact map)
            "inflight": [], "best": None, "loop_active": False, "events": [],
        }
        item["directives"] = [d for d in hub_directives if d["target"] == row["id"]]
        for key in ('active_steps', 'runnable', 'task_waits', 'completed_steps', 'joins', 'blocked_reason', 'entry', 'entry_cancelled'):
            if key in row:
                item[key] = row[key]
        item["agents"] = []
        item['machine'] = remote['machine'] if remote else 'local'
        item['remote_project'] = remote
        if remote:
            item['has_project'], item['project_dir'] = True, remote['path']
            if executor:
                mirror = executor.Lab(ctx.HUB).project_workdir(row['id'])
                item['agents'] = workers.launched_agents(mirror)
                item['events'] = labfiles.read_jsonl(mirror / '.bus/events.jsonl', tail=20)
        item["n_workers"] = 0
        if pdir is not None:
            registry = labfiles.read_jsonl(pdir / "runs" / "registry.jsonl")
            item["n_runs"] = sum(1 for r in registry if r.get("run_id"))
            item["best"] = _best_metric(registry)
            item["inflight"] = _inflight_runs(pdir)
            item["loop_active"] = (pdir / ".bus" / ".loop-active").exists()
            item["agents"] = workers.launched_agents(pdir)
            item["directives"] += _directive_threads(pdir / ".bus", default_target=row["id"])
            ctrl = pdir / "control.yaml"
            cfg = labfiles.load_yaml(ctrl) if ctrl.exists() else {}
            item["project_type"] = str(cfg.get("project_type") or "ml")   # the world draws its lab by it
            pevents = labfiles.read_jsonl(pdir / ".bus" / "events.jsonl", tail=80)
            item["events"] = pevents[-12:]
            all_events.extend(pevents)
            roster.extend(workers.scan(pdir / ".bus", row["id"], proj_ids))
        item["directives"].sort(key=lambda d: d.get("ts") or "")
        items.append(item)

    # hub-bus workers promoted to a project (its /improve worktrees) count toward that project too
    for item in items:
        item["n_workers"] = sum(1 for w in roster if w["project"] == item["id"] and w["status"] != "done")
    runs = hub_runs + [a for it in items for a in (it.get("agents") or [])]
    from task_completion import flag_runs
    flag_runs(ctx.HUB, runs)
    from framework_activity import view as framework_view
    for run in runs:
        if run.get('workflow_node') and run.get('status') in ('starting', 'running', 'resuming'):
            run['external_activity'] = framework_view(ctx.HUB, run)
    workers.LIVE_IDS.clear()
    workers.LIVE_IDS.update(x for r in runs if r.get("status") in ("starting", "running", "resuming", "waiting_input")
                     for x in (r.get("run_id"), r.get("session_id")) if x)
    workers.join_runs(roster, runs)
    workers.link_workers(roster)
    roster.sort(key=lambda w: w.get("last_ts") or "")

    all_events.sort(key=lambda e: e.get("ts", ""))
    return {
        "now": ctx.ts(),
        "editor": editor_scheme(),
        "items": items,
        "room_designs": __import__('room_resources').read(ctx.HUB),
        "machines": [{'id': 'local', 'name': 'This computer', 'state': 'connected'},
                     *__import__('project_machines').view()[0]['machines']],
        "events": all_events[-200:],
        "escalations": (esc := _escalations(all_events)),
        "notebook": _notebook_status(),
        "directives": hub_directives,
        "workers": roster[-200:],
        "agents": workers.agents(runs, roster),     # every agent at work, one shape (the world draws these)
        "campaigns": campaigns(rows),
        "checkpoints_waiting": sum(len(it["waiting"]) for it in items),
        "cold": len(rows) == 0,
        "runs": sorted(runs, key=lambda r: r.get("created") or r.get("started") or "", reverse=True)[:100],
        "hub_agents": hub_runs,
        "attention": attention.collect(items, esc, roster, runs),
        "executor": attention.executor_status(),
        "skills": (executor.registry(ctx.HUB) if executor else {}),
        "workflow": _workflow_view(),
        "tags": tagging.catalog(ctx.HUB),
        "panels": _panels_view(),
        "artifacts": _artifacts_view(),
        'artifact_revision':ctx.tool('artifact').revision(ctx.HUB),
        "lab_paused": _lab_paused(),
        **_autonomy_view(),
    }


def _lab_paused() -> dict | None:
    """null, or {since, by} while the whole lab is paused (POST /api/lab/pause; tools/executor/pause.py)."""
    if executor is None:
        return None
    try:
        st = executor.pause.state(executor.Lab(ctx.HUB))
    except Exception:  # noqa: BLE001 — never blank the dashboard
        return None
    return {"since": st.get("since"), "by": st.get("by")} if st else None


def _autonomy_view() -> dict:
    """The campaigns the executor keeps, whether a scheduler is ticking, whether the machine is held awake."""
    if executor is None:
        return {"campaign_states": [], "scheduler": {}, "awake": {}, "holds": {}}
    try:
        lab = executor.Lab(ctx.HUB)
        from executor import awake, campaigns as _camps, pause as _pause  # noqa: PLC0415
        return {"campaign_states": _camps.summary(lab), "scheduler": executor.scheduler.lease(lab),
                "awake": awake.status(), "holds": _pause.holds(lab)}
    except Exception as e:  # noqa: BLE001 — never blank the dashboard
        return {"campaign_states": [], "scheduler": {"error": str(e)}, "awake": {}, "holds": {}}


def _panels_view() -> dict:
    try:
        return ctx.tool("panels").snapshot_view(ctx.HUB)
    except Exception as e:  # noqa: BLE001 — never blank the dashboard
        return {"error": str(e), "panels": []}


def _workflow_view() -> dict:
    """The lab's definition as the dashboard reads it (steps, workflows, rooms, procedures), with the roles,
    the PI's added instructions and agents' pending proposals."""
    try:
        v = model.view(ctx.HUB)
        roles = model.roles(ctx.HUB)
        v.update(roles=list(roles), role_labels=roles, custom=instructions.status(ctx.HUB),
                 study_custom=instructions.studies_with_instructions(ctx.HUB),
                 proposals=[{k: r.get(k) for k in ("id", "kind", "name", "study", "why", "by", "ts")}
                            for r in instructions.proposals(ctx.HUB)])
        return v
    except Exception as e:  # noqa: BLE001 — a broken definition shows as a problem, never a blank dashboard
        return {"error": str(e)}




