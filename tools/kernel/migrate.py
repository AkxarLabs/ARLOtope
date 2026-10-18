"""Bringing an older lab onto the kernel — once, and in one place.

    run(hub)                    everything below that the lab still needs; returns what it did
    definition(hub)             workflow/stages.yaml → steps.yaml + workflows/<id>.yaml + rooms.yaml
    journal_from_registry(hub)  lab/REGISTRY.md + lab/approvals.jsonl + the old prose marks → lab/journal.jsonl

A lab whose old manifest is this code's own former one gets this code's current definition, and its studies
move to the step that does what came next for them (a `triaged` study is now at `lit-review`, whose work is
the literature review; one whose proposal was approved stands at `setup`). Any other lab's manifest is
converted as it is (model.convert). Old files are kept beside the new ones with a `.pre-kernel` suffix.

`newts migrate` runs this by hand; the dashboard runs it when it opens a lab that needs it.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml

from . import define, journal, model

# this code's former manifest: its state ids, and where each such study stands now
SHIPPED_LEGACY = ["seed", "triaged", "lit-review", "scoping", "proposal", "active", "analysis", "writing",
                  "internal-review", "final"]
SHIFT = {"triaged": "lit-review", "lit-review": "scoping", "scoping": "proposal"}
OLD_CHECKPOINT = {"loop": "approve-loop"}
SUFFIX = ".pre-kernel"
REG_COLS = ["id", "title", "state", "idea", "project", "paper", "updated", "next"]

GATE1_RE = re.compile(r"gate ?1 approved|gate1_approved|^\s*-\s*\[[xX]\]\s*Approved\b", re.I | re.M)
GATE3_RE = re.compile(r"gate ?3 approved|PI Gate 3|gate3_approved|Gate 3:\s*approved", re.I)
AUTH_BOX_RE = re.compile(r"-\s*\[[xX]\]\s*Authorized", re.I)
CAMPAIGN_RE = re.compile(r"lab/campaigns/([A-Za-z0-9][A-Za-z0-9._-]*)\.md")


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _keep(p: Path) -> None:
    """Set an old file aside (never overwriting an earlier one)."""
    if p.exists():
        dest = p.with_name(p.name + SUFFIX)
        if not dest.exists():
            p.rename(dest)
        else:
            p.unlink()


# ── the definition ───────────────────────────────────────────────────────────────────────────────
def needs_definition(hub) -> bool:
    h = Path(hub)
    return (h / model.LEGACY).is_file() and not (h / model.STEPS).is_file()


def definition(hub) -> dict:
    """Write the new definition files from workflow/stages.yaml. → {"map": {old: new}, "written": [...]}"""
    h = Path(hub)
    doc = yaml.safe_load(_read(h / model.LEGACY)) or {}
    ids = [s.get("id") for s in doc.get("states") or [] if isinstance(s, dict)]
    mapping: dict[str, str] = {}
    if ids == SHIPPED_LEGACY:
        new = model.normalise({"steps": yaml.safe_load(_read(model.CODE / model.STEPS)) or {},
                               "rooms": yaml.safe_load(_read(model.CODE / model.ROOMS)) or [],
                               "workflows": [dict(yaml.safe_load(_read(f)) or {}, id=f.stem)
                                             for f in sorted((model.CODE / model.WORKFLOWS).glob("*.yaml"))]})
        old_cps = {c.get("id"): c for w in doc.get("workflows") or [] for c in w.get("checkpoints") or []
                   if isinstance(c, dict)}
        for w in new["workflows"]:                   # the lab's own words on each checkpoint carry over
            for c in w["checkpoints"]:
                o = old_cps.get(c["id"]) or {}
                for k in ("title", "approver", "evidence", "means", "tell", "checks", "confirm"):
                    if o.get(k) not in (None, ""):
                        c[k] = o[k]
        have = {w["id"] for w in new["workflows"]}
        extra = [w for w in model.convert(doc)["workflows"] if w["id"] not in have]
        new["workflows"] += [dict(w, default=False) for w in extra]
        mapping = dict(SHIFT)
        rooms_old = {r.get("id"): r for r in doc.get("rooms") or [] if isinstance(r, dict)}
        for r in new["rooms"]:                       # where the PI put each room stays
            for k in ("place", "facing"):
                if k in (rooms_old.get(r["id"]) or {}):
                    r[k] = rooms_old[r["id"]][k]
    else:
        new = model.normalise(model.convert(doc))
    written = define.write(h, new)
    _keep(h / model.LEGACY)
    return {"map": mapping, "written": [p.relative_to(h).as_posix() for p in written]}


# ── the journal ──────────────────────────────────────────────────────────────────────────────────
def registry_rows(hub) -> list[dict]:
    """The old hand-kept REGISTRY.md table, parsed by position."""
    out = []
    for line in _read(Path(hub) / "lab" / "REGISTRY.md").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < len(REG_COLS) or cells[0] in ("ID", "", "—") or set(cells[0]) <= {"-"}:
            continue
        out.append(dict(zip(REG_COLS, cells)))
    return out


def _workflow_of(hub: Path, slug: str, row: dict, ids: list[str]) -> str | None:
    m = re.search(r"^workflow:\s*([\w.-]+)", _read(hub / "studies" / slug / "IDEA.md"), re.M)
    if m and m.group(1) in ids:
        return m.group(1)
    raw = (row.get("project") or "").strip().strip("`")
    if raw and raw not in ("—", "-") and "target" in ids:
        p = Path(raw)
        p = p if p.is_absolute() else (hub / p)
        if re.search(r"^target:\s*\n(?:[ \t].*\n)*?[ \t]+active:\s*true", _read(p / "control.yaml"), re.M):
            return "target"
    return None


def prose_marks(hub, slugs: list[str], projects: dict[str, Path]) -> list[dict]:
    """[{study, checkpoint, by, note}] — every approval an older lab wrote as a mark inside a document."""
    hub = Path(hub)
    out = []

    def by(text: str) -> str:
        m = CAMPAIGN_RE.search(text or "")
        return f"campaign:{m.group(1)}" if m else "pi"

    for slug in slugs:
        mark = next((ln for ln in _read(hub / "studies" / slug / "proposal.md").splitlines() if GATE1_RE.search(ln)), "")
        if mark:
            out.append({"study": slug, "checkpoint": "approve-proposal", "by": by(mark),
                        "note": "carried over from the proposal's Gate 1 mark"})
        note = _read(hub / "studies" / slug / "paper" / "gate3-approval.md")
        if note and GATE3_RE.search(note):
            m = re.search(r"signed_via:\s*campaign:(\S+)", note)
            out.append({"study": slug, "checkpoint": "finalize-paper", "by": by(m.group(1)) if m else "pi",
                        "note": "carried over from gate3-approval.md"})
        pdir = projects.get(slug)
        if pdir:
            try:
                ctl = yaml.safe_load(_read(pdir / "control.yaml")) or {}
            except yaml.YAMLError:
                ctl = {}
            env = ctl.get("gate2_envelope") or {} if isinstance(ctl, dict) else {}
            if isinstance(env, dict) and env.get("pi_signed") is True:
                caps = ", ".join(f"{k}={env[k]}" for k in ("full_runs", "per_run_max_minutes", "total_max_minutes",
                                                          "expires") if env.get(k) not in (None, ""))
                out.append({"study": slug, "checkpoint": "approve-full-runs", "by": by(str(env.get("signed_via") or "")),
                            "note": "Stay within the old envelope" + (f": {caps}" if caps else "") + "."})
            tgt = ctl.get("target") or {} if isinstance(ctl, dict) else {}
            if isinstance(tgt, dict) and str(tgt.get("final_run_id") or "").strip():
                out.append({"study": slug, "checkpoint": "approve-final-output", "by": "pi",
                            "note": f"final output: run {tgt['final_run_id']}"})
            loop = _read(pdir / "LOOP_BRIEF.md")
            if AUTH_BOX_RE.search(loop):
                mode = re.search(r"\*\*Mode:\*\*\s*`(execute|explore)`", loop)
                out.append({"study": slug, "checkpoint": "approve-loop", "by": by(loop),
                            "note": f"mode: {mode.group(1)}" if mode else ""})
    cdir = hub / "lab" / "campaigns"
    for f in sorted(cdir.glob("*.md")) if cdir.is_dir() else []:
        sec = _read(f).split("## PI authorization", 1)
        if len(sec) == 2 and AUTH_BOX_RE.search(sec[1].split("\n## ", 1)[0]) and journal.ID.match(f.stem):
            out.append({"study": "lab", "checkpoint": f"campaign:{f.stem}", "by": "pi",
                        "note": "carried over from the brief's Authorized box"})
    return out


def journal_from_registry(hub, mapping: dict[str, str] | None = None) -> int:
    """Write lab/journal.jsonl from what an older lab kept: its registry, its approvals file and the approval
    marks in its documents. → the number of events written. Does nothing when a journal exists."""
    hub = Path(hub)
    jp = journal.path(hub)
    if jp.exists():
        return 0
    mapping = mapping or {}
    m = model.load(hub)
    ids = [w["id"] for w in m["workflows"]]
    rows = registry_rows(hub)
    lines: list[dict] = []
    projects: dict[str, Path] = {}

    def ev(study, kind, by="migration", **f):
        e = {"ts": f.pop("ts", None) or journal.now(), "study": study, "kind": kind, "by": by}
        e.update({k: v for k, v in f.items() if v not in (None, "")})
        lines.append(e)

    decided: dict[tuple, dict] = {}
    for r in journal_lines(hub / "lab" / "approvals.jsonl"):
        cid = OLD_CHECKPOINT.get(r.get("checkpoint"), r.get("checkpoint"))
        if r.get("decision") in journal.DECISIONS and r.get("study") and cid:
            decided[(r["study"], cid)] = r
    for r in rows:
        slug = r["id"]
        if not model.SLUG.match(slug):
            continue
        wid = _workflow_of(hub, slug, r, ids)
        raw = (r.get("project") or "").strip().strip("`")
        if raw and raw not in ("—", "-"):
            p = Path(raw)
            projects[slug] = p if p.is_absolute() else (hub / p).resolve()
        step = mapping.get(r["state"], r["state"])
        ts = (r.get("updated") or "")[:10]
        ts = f"{ts}T00:00:00" if re.match(r"^\d{4}-\d{2}-\d{2}$", ts) else None
        ev(slug, "new", ts=ts, workflow=wid, title=r.get("title"), step=step)
        if slug in projects:
            ev(slug, "project", path=raw)
    slugs = [r["id"] for r in rows if model.SLUG.match(r["id"])]
    for x in prose_marks(hub, slugs, projects):
        decided.setdefault((x["study"], x["checkpoint"]), {"decision": "approved", "by": x["by"], "via": "migration",
                                                            "note": x["note"]})
    for (slug, cid), r in decided.items():
        ev(slug, "approval", by=r.get("by") or "pi", ts=r.get("ts"), checkpoint=cid, decision=r["decision"],
           via=r.get("via") if r.get("via") in ("dashboard", "cli", "keeper", "migration") else "migration",
           note=r.get("note"))
    if not lines:
        return 0
    # a study standing where an approved checkpoint waited has that checkpoint's work still to do
    st = journal.fold(lines)
    for slug, s in st.items():
        if slug == "lab" or not s["step"]:
            continue
        wid = s["workflow"] or model.default_workflow(hub)
        path = model.workflow(wid, hub)["path"]
        for cp in model.checkpoints(wid, hub):
            if cp.get("before") and model.waits_at(cp, wid, hub) == s["step"] and (slug, cp["id"]) in decided \
                    and decided[(slug, cp["id"])].get("decision") == "approved":
                ev(slug, "move", **{"from": s["step"], "to": cp["before"], "note": "its checkpoint was approved before the journal"})
                s["step"] = cp["before"]
        if path and s["step"] == path[-1]:
            ev(slug, "finish", note="finished before the journal")
    jp.parent.mkdir(parents=True, exist_ok=True)
    with jp.open("w", encoding="utf-8", newline="\n") as f:
        for e in lines:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    _keep(hub / "lab" / "approvals.jsonl")
    from . import studies  # noqa: PLC0415
    studies.render_registry(hub)
    return len(lines)


def journal_lines(p: Path) -> list[dict]:
    out = []
    for ln in _read(p).splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


def needed(hub) -> bool:
    h = Path(hub)
    return needs_definition(h) or (not journal.path(h).exists() and bool(registry_rows(h)))


def missing_procedures(hub) -> list[str]:
    """Procedures the lab's definition names (a step's `do` or `also`, a workflow's `use`) that it has no skill for
    but this code ships — an older lab meeting a step that is new (e.g. the idea step's /triage)."""
    h = Path(hub)
    try:
        m = model.load(h)
    except model.ModelError:
        return []
    named = {p for s in m["steps"].values() for p in [s.get("do"), *s.get("also", [])] if p}
    named |= {v for w in m["workflows"] for v in (w.get("use") or {}).values()}
    have = model.skills_root(h)
    return sorted(p for p in named if not (have / p / "SKILL.md").is_file()
                  and (model.CODE / model.SKILLS / p / "SKILL.md").is_file())


def bring_procedures(hub) -> list[str]:
    """Copy in the skills of missing_procedures() from this code."""
    h = Path(hub)
    names = missing_procedures(h)
    for p in names:
        shutil.copytree(model.CODE / model.SKILLS / p, model.skills_root(h) / p,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if names:
        model._cache.clear()
    return names


def run(hub) -> list[str]:
    """Whatever this lab still needs. → a line per thing done (empty: it was already on the kernel)."""
    h = Path(hub)
    done = []
    mapping: dict[str, str] = {}
    if needs_definition(h):
        res = definition(h)
        mapping = res["map"]
        done.append("wrote " + ", ".join(res["written"]) + f" (workflow/stages.yaml kept as stages.yaml{SUFFIX})")
    brought = bring_procedures(h)
    if brought:
        done.append("added the procedures its steps name: " + ", ".join(f"/{p}" for p in brought))
    if not journal.path(h).exists():
        n = journal_from_registry(h, mapping)
        if n:
            done.append(f"wrote lab/journal.jsonl ({n} events from the registry, the approvals and the old marks)")
    elif mapping:
        from . import studies  # noqa: PLC0415
        studies.remap(h, mapping, by="migration")
        done.append("moved the studies onto the new steps: " + ", ".join(f"{a} → {b}" for a, b in mapping.items()))
    return done
