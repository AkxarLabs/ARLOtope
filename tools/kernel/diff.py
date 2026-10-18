"""Comparing two definitions of a lab, and checking a designer's draft against the live one.

    files(root)                  the files that make up a lab's definition (ROOTS), relative path → file
    summary(before, after)       what a change does, in plain lines — every loosened or removed checkpoint first
    affected(hub, root)          what it does to the lab's studies: waits it ends or moves, approvals it outdates
    check_overlay(hub, folder)   a designer's draft (a folder holding some definition files, at the same paths)
                                 laid over the live definition: (problems, summary). `newts check --design`.
    lay(folder, dest, merge)     lay such a folder over a lab. A design replaces each file it holds; an extension
                                 (merge=True) adds — its steps and rooms join the lab's by id.
    extensions(hub)              the extensions a lab can add (extensions/<name>/ with an extension.yaml)
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import yaml

from . import define, model, rules, studies

ROOTS = ("workflow", ".claude/skills", "agent-roles", "checks", "templates/project-types",
         "templates/domain-profiles", "lab/templates", "lab/workflow")
DESIGNABLE = ("workflow/", ".claude/skills/", "agent-roles/", "checks/")   # what a designer's draft may hold


def files(root: Path) -> dict[str, Path]:
    out = {}
    for r in ROOTS:
        d = Path(root) / r
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                    out[f.relative_to(root).as_posix()] = f
    return out


def copy(src: Path, dest: Path) -> dict[str, Path]:
    fs = files(src)
    for rel, f in fs.items():
        (Path(dest) / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, Path(dest) / rel)
    Path(dest).mkdir(parents=True, exist_ok=True)
    return fs


def summary(before: Path, after: Path) -> list[str]:
    """What a definition change does — every loosened or removed checkpoint, and changed watches, first."""
    try:
        a, b = model.load(before), model.load(after)
    except Exception as e:  # noqa: BLE001
        return [f"can't compare: {e}"]
    rank = {"me": 0, "me-or-campaign": 1, "agent": 2, "auto": 2}
    first, rest = [], []
    wa, wb = {w["id"]: w for w in a["workflows"]}, {w["id"]: w for w in b["workflows"]}
    for wid in sorted(set(wa) | set(wb)):
        x, y = wa.get(wid), wb.get(wid)
        name = (y or x).get("title") or wid
        if not y:
            rest.append(f"removes the workflow {name}")
            continue
        if not x:
            cps = "; ".join(f"“{c['title']}” ({'before ' + c['before'] if c.get('before') else 'during ' + str(c.get('during'))}, "
                            f"approved by {c.get('approver')})" for c in y["checkpoints"])
            rest.append(f"adds the workflow {name}: " + " → ".join(y["path"])
                        + (f", with the checkpoints {cps}" if cps else ", with no checkpoints"))
            continue
        ca, cb = {c["id"]: c for c in x["checkpoints"]}, {c["id"]: c for c in y["checkpoints"]}
        for cid in sorted(set(ca) | set(cb)):
            p, q = ca.get(cid), cb.get(cid)
            if p and not q:
                first.append(f"{name}: removes the checkpoint “{p['title']}”")
            elif q and not p:
                rest.append(f"{name}: adds the checkpoint “{q['title']}” ("
                            + (f"before {q['before']}" if q.get("before") else f"during {q.get('during')}") + ")")
            else:
                if q.get("approver") != p.get("approver"):
                    line = f"{name}: “{q['title']}” is approved by {q.get('approver')} now (was {p.get('approver')})"
                    (first if rank.get(q.get("approver"), 0) > rank.get(p.get("approver"), 0) else rest).append(line)
                if (p.get("before"), p.get("during")) != (q.get("before"), q.get("during")):
                    rest.append(f"{name}: “{q['title']}” moves to "
                                + (f"before {q['before']}" if q.get("before") else f"during {q.get('during')}"))
                if p.get('judge') != q.get('judge') or p.get('decisions') != q.get('decisions'):
                    first.append(f"{name}: “{q['title']}” changes its independent review or decision routes")
                for k, what in (("checks", "runs"), ("watch", "watches for")):
                    lost = [c for c in p.get(k) or [] if c not in (q.get(k) or [])]
                    if lost:
                        first.append(f"{name}: “{q['title']}” no longer {what} {', '.join(model.check_label(c) for c in lost)}")
        if x["path"] != y["path"]:
            rest.append(f"{name}: the path becomes " + " → ".join(y["path"]))
        if x["routes"] != y["routes"]:
            rest.append(f"{name}: where outcomes lead changes")
        if x["use"] != y["use"]:
            rest.append(f"{name}: uses " + (", ".join(f"/{v} for /{k}" for k, v in y["use"].items()) or "the steps' own procedures"))
        if x.get('nodes') != y.get('nodes') or x.get('start') != y.get('start'):
            rest.append(f'{name}: task connections, room groups, instructions or agent/context assignments change')
    sa, sb = a["steps"], b["steps"]
    rest += [f"adds the step {sb[s]['label']} ({s})" for s in sb if s not in sa]
    rest += [f"removes the step {sa[s]['label']} ({s})" for s in sa if s not in sb]
    rest += [f"the step {sb[s]['label']} is now done by /{sb[s].get('do')}" for s in sb
             if s in sa and sa[s].get("do") != sb[s].get("do")]
    pa, pb = a["procedures"], b["procedures"]
    rest += [f"adds the procedure /{p}" + (f" (a variant of /{pb[p]['like']})" if pb[p].get("like") else "")
             for p in pb if p not in pa]
    rest += [f"removes the procedure /{p}" for p in pa if p not in pb]
    try:
        if (rules.load(before).get("watch") or []) != (rules.load(after).get("watch") or []):
            first.append("changes what the lab watches for (rules.yaml watch)")
    except Exception:  # noqa: BLE001
        pass
    return first + rest


def affected(hub, root: Path) -> list[str]:
    """What the definition at root would do to the studies of the lab at hub, in plain lines: a study waiting at a
    checkpoint that is gone or no longer on its way moves on (or waits elsewhere), and an approval whose checkpoint's
    terms change no longer stands for a study that hasn't passed it yet (studies.decisions). Read-only."""
    try:
        new = {w["id"]: w for w in model.load(root)["workflows"]}
        rows = studies.all_studies(hub)
    except Exception:  # noqa: BLE001 — a definition that can't be read: problems() says so
        return []
    out = []
    for slug, s in sorted(rows.items()):
        w = new.get(s.get("workflow"))
        if not w or s.get("finished") or s.get("step") not in w["path"]:
            continue                                       # orphans() covers studies the change strands
        title = s.get("title") or slug
        wait = s.get("waiting") or {}
        cid, to = wait.get("checkpoint"), wait.get("to")
        if cid and to in w["path"]:
            ahead = [c for c in model.before_on_the_way(w["id"], s["step"], to, root)]
            if cid not in [c["id"] for c in ahead]:
                held = next((c for c in ahead if not studies.approved(hub, slug, c["id"])), None)
                out.append(f"{title} stops waiting at {cid}: " + (f"it waits at “{held['title']}” instead" if held
                                                                    else f"it moves on to {to}"))
        old = studies.decisions(hub, slug)
        i = w["path"].index(s["step"])
        for c in w["checkpoints"]:
            rec = old.get(c["id"]) or {}
            if rec.get("decision") != "approved" or not rec.get("terms"):
                continue
            if rec["terms"] == model.terms(c) and model.may_approve(c, str(rec.get("by") or "pi")):
                continue
            at = c.get("during") or c.get("before")
            if at in w["path"] and (w["path"].index(at) > i or (c.get("during") and at == s["step"])):
                out.append(f"{title}: your approval of “{c['title']}” no longer stands — the checkpoint changed, "
                           "so it asks you again")
    return out


def orphans(hub, root: Path) -> list[str]:
    """Studies (of the lab at hub) standing on a step the definition at root no longer has, or following a
    workflow it no longer has."""
    try:
        m = model.load(root)
        rows = studies.rows(hub)
    except Exception:  # noqa: BLE001
        return []
    out = [f"Studies stand at `{s}`, which this definition no longer has — move them first (newts move <study> --to <step>)."
           for s in sorted({r["state"] for r in rows if r.get("state") and r["state"] not in m["steps"]})]
    wfs = {w["id"] for w in m["workflows"]}
    out += [f"Studies follow the workflow `{w}`, which this definition no longer has — give them another first."
            for w in sorted({r["workflow"] for r in rows if r.get("workflow") and r["workflow"] not in wfs})]
    workflows = {w['id']: w for w in m['workflows']}
    for row in rows:
        w = workflows.get(row['workflow'])
        if not w:
            continue
        lost = [t['id'] for t in row.get('active_steps', []) if t['id'] not in w['path']]
        if lost:
            out.append(f"{row['id']}: active tasks would be removed ({', '.join(lost)}). Move the study first.")
        if len(row.get('active_steps', [])) > 1 and not w.get('nodes'):
            out.append(f"{row['id']}: finish or explicitly move its parallel tasks before switching to an ordered path.")
    return out


def design_files(folder: Path) -> dict[str, Path]:
    """The definition files a designer's draft holds (only what a designer may change)."""
    return {rel: f for rel, f in files(folder).items() if rel.startswith(DESIGNABLE)}


def lay(folder: Path, dest: Path, merge: bool = False) -> list[str]:
    """Lay a folder's definition files over the lab at dest. → the paths written. A designer's draft replaces each
    file it holds. An extension (merge) only adds: its steps and rooms join the lab's by id (one of the same id is
    replaced), the shelves stay last; its workflows, skills, roles and checks are laid as they are."""
    folder, dest = Path(folder), Path(dest)
    fs = design_files(folder)
    merged = {model.STEPS.as_posix(), model.ROOMS.as_posix()} if merge else set()
    for rel, f in fs.items():
        if rel not in merged:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest / rel)
    if merge and merged & set(fs):
        d = define.read(dest)
        ext = model.normalise({"steps": yaml.safe_load(model._read(folder / model.STEPS)) or {},
                               "rooms": yaml.safe_load(model._read(folder / model.ROOMS)) or [], "workflows": []})
        steps = {k: v for k, v in d["steps"].items() if not v["shelf"]}
        steps.update({k: v for k, v in ext["steps"].items() if not v["shelf"]})
        d["steps"] = {**steps, **{k: v for k, v in d["steps"].items() if v["shelf"]}}
        d["rooms"] = list({**{r["id"]: r for r in d["rooms"]}, **{r["id"]: r for r in ext["rooms"]}}.values())
        define.write(dest, d, {"steps", "rooms"})
    model._cache.clear()
    return sorted(fs)


def extensions(hub) -> list[dict]:
    """The extensions this lab can add: extensions/<name>/ holding an extension.yaml ({title, blurb}) and definition
    files at their lab paths (workflow/…, .claude/skills/…, agent-roles/…, checks/…)."""
    out = []
    root = Path(hub) / "extensions"
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        meta = yaml.safe_load(model._read(d / "extension.yaml")) if (d / "extension.yaml").is_file() else None
        if isinstance(meta, dict) and model.SLUG.match(d.name):
            out.append({"name": d.name, "title": str(meta.get("title") or d.name), "blurb": str(meta.get("blurb") or ""),
                        "path": d, "files": sorted(design_files(d))})
    return out


def check_overlay(hub, folder: Path, merge: bool = False) -> tuple[list[str], list[str]]:
    """(problems, what it changes) for a designer's draft — or an extension (merge) — laid over the live lab."""
    hub, folder = Path(hub), Path(folder)
    if not design_files(folder):
        return ["it holds no definition files (workflow/…, .claude/skills/…)"], []
    with tempfile.TemporaryDirectory(prefix="newts-design-") as tmp:
        t = Path(tmp)
        copy(hub, t)
        try:
            lay(folder, t, merge)
            probs = model.check(t, rules.check_names(t)) + rules.check(t) + orphans(hub, t)
            ra, rb = rules.load(hub), rules.load(t)
            probs += [f"rules.yaml `{k}` can't change in a design" for k in
                      ("pi_owned_config", "protected_paths", "rigor_floors", "config_procedures") if ra.get(k) != rb.get(k)]
        except Exception as e:  # noqa: BLE001
            probs = [f"it can't be read: {e}"]
        said = summary(hub, t)
        model._cache.clear()        # the temporary definition must not linger in the cache
    return probs[:10], said
