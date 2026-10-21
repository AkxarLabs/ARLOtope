"""Checkpoints at work: what a study's checkpoint shows the PI, its checks, and deciding it.

    find(hub, slug, cid)            the checkpoint in the study's workflow
    evidence(hub, slug, cp)         the files the PI looks at ({study}/{project} filled in)
    run_checks(hub, slug, cp)       run its checks → {name: {code, out}} (0 = passed)
    readiness(hub, slug, cid)       everything the sheet shows: where the study is, evidence, checks, history
    decide(hub, slug, cid, …)       record a decision, enforcing who may make it; approving one the study
                                    waits at moves it on
    waiting(hub, slug)              the checkpoint a study waits at now, if any

A check is a script in checks/ (run through tools/guard.py, `<name> <study>`) or a named audit in rules.yaml.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import journal, model, rules, studies

TOOLS = Path(__file__).resolve().parents[1]


class CheckpointError(ValueError):
    pass


def find(hub, slug: str, cid: str) -> dict:
    wid = studies.workflow_of(hub, slug)
    cp = model.checkpoint(cid, wid, hub)
    if cp is None:
        raise CheckpointError(f"'{cid}' is not a checkpoint of {slug}'s workflow ({wid})")
    return cp


def project_dir(hub, slug: str) -> Path | None:
    """The study's project repository: where the journal says, else <projects_root>/<slug> when it exists."""
    s = studies.study(hub, slug) or {}
    if str(s.get('project') or '').startswith('newts+ssh://'):
        return None
    if s.get("project"):
        p = Path(s["project"])
        return p if p.is_absolute() else (Path(hub) / p).resolve()
    sys.path.insert(0, str(TOOLS))
    import labfiles  # noqa: PLC0415
    cand = labfiles.projects_root(hub) / slug
    return cand if cand.exists() else None


def _fill(hub: Path, slug: str, rel: str) -> Path | None:
    if "{project}" in rel:
        pdir = project_dir(hub, slug)
        if not pdir:
            return None
        rel = rel.replace("{project}", pdir.as_posix())
    p = Path(rel.replace("{study}", slug))
    return p if p.is_absolute() else Path(hub) / p


def evidence(hub, slug: str, cp: dict) -> list[dict]:
    import remote_projects as remote

    refs = [str(rel) for rel in cp.get("evidence") or []]
    needs_project = any('{project}' in rel for rel in refs)
    location = remote.project(hub, slug) if needs_project else None
    pdir = project_dir(hub, slug) if needs_project and not location else None
    paths = [rel[len('{project}/'):].replace('{study}', slug) for rel in refs
             if location and rel.startswith('{project}/')]
    states = {}
    if paths:
        try:
            states = remote.file_states(hub, slug, paths)
        except remote.RemoteError:
            pass  # an unavailable worker leaves evidence visible, marked missing
    out = []
    for rel in refs:
        if location and rel.startswith('{project}/'):
            path = rel[len('{project}/'):].replace('{study}', slug)
            out.append({'path':remote.uri(location['machine'],location['path'].rstrip('/')+'/'+path),
                        'name':path,'exists':states.get(path) is not None,'dir':False,'remote':True})
            continue
        if '{project}' in rel and not pdir:
            continue
        p = _fill(Path(hub), slug, rel.replace('{project}', pdir.as_posix()) if pdir else rel)
        try:
            shown = p.resolve().relative_to(Path(hub).resolve()).as_posix()
        except ValueError:
            shown = p.as_posix()
        out.append({"path": shown, "name": p.name or shown, "exists": p.exists(), "dir": p.is_dir()})
    return out


def _cache(hub: Path, slug: str, cid: str) -> Path:
    return Path(hub) / "lab" / ".bus" / "checks" / slug / f"{cid}.json"


def argv(hub, slug: str, name: str, params: dict | None = None) -> list[str] | None:
    """How to run one check for a study: a named audit (rules.yaml), else checks/<name>.py via tools/guard.py —
    with the checkpoint's parameters for it as `--param value`."""
    hub = Path(hub)
    extra = [x for k, v in (params or {}).items() for x in ([f"--{k}"] if v is True else [] if v is False else [f"--{k}", str(v)])]
    a = next((x for x in rules.audits(hub) if x["name"] == name), None)
    paper = (hub / "studies" / slug / "paper").as_posix()
    pdir = project_dir(hub, slug)
    if a:
        tool = next((d / a["run"][0] for d in rules.check_roots(hub) if (d / a["run"][0]).is_file()), None)
        if not tool:
            return None
        return [sys.executable, str(tool), *[str(x).format(paper=paper, study=slug, project=pdir.as_posix() if pdir else "")
                                              for x in a["run"][1:]], *extra]
    if any((d / f"{name.replace('-', '_')}.py").is_file() or (d / f"{name}.py").is_file() for d in rules.check_roots(hub)):
        return [sys.executable, str(TOOLS / "guard.py"), name, slug, *extra]
    return None


def run_checks(hub, slug: str, cp: dict, timeout: float = 600, names: list | None = None) -> dict:
    """{name: {code, out}} for each check (0 = passed; anything else blocks a delegated or automatic
    approval). `names`: entries as a checkpoint lists them (a name, or {name: {params}}). Cached for the sheet."""
    hub = Path(hub)
    res = {}
    for item in names if names is not None else cp.get("checks") or []:
        name, params = model.check_spec(item)
        cmd = argv(hub, slug, name, params)
        if not cmd:
            res[name] = {"code": 127, "out": f"no audit or check called {name}"}
            continue
        try:
            r = subprocess.run(cmd, cwd=str(hub), capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace", env=dict(os.environ, NEWTS_HUB=str(hub.resolve())))
            res[name] = {"code": r.returncode, "out": ((r.stdout or "") + (r.stderr or "")).strip()[-1200:]}
        except (OSError, subprocess.TimeoutExpired) as e:
            res[name] = {"code": 124, "out": str(e)[:300]}
    if names is None:
        f = _cache(hub, slug, cp["id"])
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"ts": journal.now(), "results": res}, indent=1), encoding="utf-8")
    return res


def cached_checks(hub, slug: str, cid: str) -> dict:
    try:
        return json.loads(_cache(Path(hub), slug, cid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def readiness(hub, slug: str, cid: str) -> dict:
    cp = find(hub, slug, cid)
    s = studies.study(hub, slug) or {}
    at = model.waits_at(cp, cp["workflow"], hub)
    if s.get('active_steps') is not None:
        at = cp.get('before') or cp.get('during')
    rec = studies.decisions(hub, slug).get(cid)
    if rec and rec.get('decision') == 'approved' and not studies.approved(hub, slug, cid):
        rec = dict(rec, decision='outdated', why='The reviewed evidence changed.')
    cached = cached_checks(hub, slug, cid)
    checks = [{"name": n, "code": (cached.get("results") or {}).get(n, {}).get("code"),
               "out": (cached.get("results") or {}).get(n, {}).get("out", "")}
              for n in (model.check_spec(x)[0] for x in cp.get("checks") or [])]
    return {"ok": True, "study": slug, "checkpoint": cp, "state": s.get("step") or "", "waits_at": at,
            "here": s.get("step") == at or any(t['id'] == at for t in s.get('active_steps', [])),
            "waiting": ((s.get("waiting") or {}).get("checkpoint") == cid) or any(t['checkpoint'] == cid for t in s.get('task_waits', [])),
            "approved": bool(rec) and rec.get("decision") == "approved", "record": rec,
            "history": journal.approvals(hub, slug, cid)[-10:],
            "evidence": evidence(hub, slug, cp), "checks": checks, "checked_at": cached.get("ts")}


VIAS = ("dashboard", "cli", "keeper", "kernel", "migration")


def decide(hub, slug: str, cid: str, decision: str = "approved", by: str = "pi", via: str = "dashboard",
           note: str = "", checks: dict | None = None, **extra) -> dict:
    """Record a decision on a study's checkpoint. `by`: pi | campaign:<name> | auto. A campaign may approve only a
    `me-or-campaign` checkpoint and `auto` only an `auto` one — both only with every check passing. Approving the
    checkpoint a study waits at moves it on (the record's `moved` says where)."""
    if decision not in journal.DECISIONS:
        raise CheckpointError(f"decision must be one of {', '.join(journal.DECISIONS)}")
    if via not in VIAS:
        raise CheckpointError(f"via must be one of {', '.join(VIAS)}")
    if studies.in_agent_run() and via not in ("keeper", "kernel"):
        raise CheckpointError(studies.PI_ONLY)
    cp = find(hub, slug, cid)
    appr = cp.get("approver", "me")
    if by.startswith("campaign:") and decision == "approved":
        if appr not in ('me-or-campaign', 'auto'):
            raise CheckpointError(f"'{cp['title']}' is approved by the PI only" if appr=='me' else f"'{cp['title']}' does not allow campaign approval")
    elif by == "auto" and decision == "approved":
        if appr != "auto":
            raise CheckpointError(f"'{cp['title']}' does not approve itself")
    elif by.startswith('judge:'):
        if appr != 'agent' or via != 'kernel':
            raise CheckpointError('This checkpoint does not delegate approval to this judge.')
    elif by != "pi":
        raise CheckpointError(f"unknown approver {by!r}")
    if by != "pi" and decision == "approved" and cp.get("checks"):
        res = checks if checks is not None else run_checks(hub, slug, cp)
        bad = [n for n, r in res.items() if (r or {}).get("code") != 0]
        if bad:
            raise CheckpointError(f"'{cp['title']}' can't be approved by {by}: " + ", ".join(bad) + " did not pass")
    rec = journal.append(hub, slug, "approval", by, checkpoint=cid, decision=decision, via=via,
                         note=str(note or "").strip()[:journal.MAX_NOTE], workflow=cp["workflow"], terms=model.terms(cp),
                         **{k: v for k, v in extra.items() if v is not None})
    studies.render_registry(hub)
    if decision == "approved" and via != "kernel":
        moved = studies.resume(hub, slug, by)
        if moved:
            rec = dict(rec, moved=moved)
    return rec


LAB_WIDE = ("campaign:", "panel:")      # approvals of the lab as a whole: a campaign brief, a panel's collector


def decide_lab(hub, what: str, decision: str = "approved", by: str = "pi", via: str = "dashboard",
               note: str = "", **extra) -> dict:
    """A decision about the lab as a whole — `campaign:<name>` (a campaign brief) or `panel:<id>` (a collector's
    code): the PI's only, recorded under the study "lab"."""
    if not str(what).startswith(LAB_WIDE) or not journal.ID.match(str(what)):
        raise CheckpointError(f"{what!r} is not a lab-wide approval (campaign:<name> or panel:<id>)")
    if decision not in journal.DECISIONS:
        raise CheckpointError(f"decision must be one of {', '.join(journal.DECISIONS)}")
    if via not in VIAS:
        raise CheckpointError(f"via must be one of {', '.join(VIAS)}")
    if studies.in_agent_run() or by != "pi":
        raise CheckpointError(studies.PI_ONLY)
    return journal.append(hub, "lab", "approval", by, checkpoint=what, decision=decision, via=via,
                          note=str(note or "").strip()[:journal.MAX_NOTE], **{k: v for k, v in extra.items() if v is not None})


def waiting(hub, slug: str) -> list[dict]:
    """The checkpoint a study waits at now (a list of at most one), not yet approved."""
    s = studies.study(hub, slug) or {}
    w = s.get("waiting") or {}
    if not w.get("checkpoint") or studies.approved(hub, slug, w["checkpoint"]):
        return []
    cp = model.checkpoint(w["checkpoint"], s.get("workflow"), hub)
    return [cp] if cp else []
