"""The lab's definition as plain data, and written back: steps.yaml, rooms.yaml and one file per workflow, each a
plain YAML dump under a fixed header (so Compose, a designer's draft, tools/new.py and `newts migrate` all write the
same shape, and an edit is a whole-file rewrite — no line surgery).

    read(root) -> {steps, rooms, workflows}      change it, then write(root, d)
    rename_step(d, old, new)                     a step's new id, everywhere the definition names it
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import model
from .model import ROOMS, STEPS, WORKFLOWS


def read(root) -> dict:
    """The definition under root as plain data to change and write back."""
    m = model.load(root)
    return {"steps": {k: dict(v, also=list(v["also"])) for k, v in m["steps"].items()},
            "rooms": [dict(r) for r in m["rooms"]],
            "workflows": [dict(w, path=list(w["path"]), routes={k: dict(v) for k, v in w["routes"].items()},
                               use=dict(w["use"]), checkpoints=[dict(c) for c in w["checkpoints"]])
                          for w in m["workflows"]]}


def rename_step(d: dict, old: str, new: str) -> dict:
    """Give a step a new id everywhere the definition names it: the step list (in place), every workflow's path,
    its routes (from and to) and the checkpoints on it. Raises ValueError for an unknown or taken id."""
    if old not in d["steps"] or d["steps"][old].get("shelf"):
        raise ValueError(f"no step {old!r} to rename")
    if not model.SLUG.match(new or "") or new in d["steps"]:
        raise ValueError(f"{new!r} is not a free step id (lowercase letters, digits, - . _)")
    d["steps"] = {(new if k == old else k): dict(v, id=new) if k == old else v for k, v in d["steps"].items()}
    swap = (lambda x: new if x == old else x)
    for w in d["workflows"]:
        w["path"] = [swap(x) for x in w["path"]]
        w["routes"] = {swap(k): {o: swap(t) for o, t in v.items()} for k, v in w["routes"].items()}
        if w.get('nodes'):
            from workflow_graph import targets
            w['nodes'] = {swap(k): dict(v, next=[swap(t) for t in targets(v.get('next'))])
                          if 'next' in v else dict(v) for k, v in w['nodes'].items()}
            for v in w['nodes'].values():
                if (v.get('context') or {}).get('from') == old:
                    v['context']['from'] = new
            if w.get('start'):
                w['start'] = [swap(t) for t in targets(w['start'])]
        for c in w["checkpoints"]:
            for k in ("before", "during"):
                if c.get(k) == old:
                    c[k] = new
    return d

STEPS_HEAD = """\
# The places a study can be — shared by every workflow (workflow/workflows/*.yaml walks some of them, in its
# own order). Each step names the procedure that does its work (`do:` — a skill in .claude/skills/, or any
# variant of one) and the others a study there can run (`also:`). `room:` is where it stands in the
# dashboard's world (workflow/rooms.yaml).
#
# A procedure never names a step: it ends by reporting an outcome (`newts move <study> <outcome>`) and the
# study's workflow says where that leads. `parked` and `killed` are the two shelves every lab has — `park`
# and `kill` lead there from anywhere. The PI shapes this file (agents never edit it); `newts check`
# validates it.

"""

WORKFLOW_HEAD = """\
# A workflow: the path a study walks, where each outcome leads, and the PI's checkpoints on the way.
#
#   path        the steps in order (workflow/steps.yaml); `done` moves a study to the next one, and `done` at
#               the last step finishes it
#   routes      where any other outcome leads, per step; an outcome with no route goes to the PI, who decides
#   use         swap a procedure for another (a variant) in this workflow only: {lit-review: lit-review-quick}
#   checkpoints the PI's approvals:
#                 before: <step>             a study can't enter that step until it is approved
#                 during: <step> + at: "…"   the agent stops at that point inside the step and asks
#                 approver: me | me-or-campaign | auto | agent (fresh evidence review)
#                 judge: {skill: gate-review, rubric: "…", max_attempts: 3, max_visits: 3}
#                 decisions: {proceed: continue, revise: <step>, stop: parked}
#                 checks: [...]   scripts the checkpoint shows (and `auto` needs passing) — checks/<name>.py
#                 watch: [...]    checks that flag work done past it without approval
#                 evidence: [...] what you look at ({study} = the study's slug, {project} = its project repo)
#                 means / tell    what it covers, and what agents are told about it
#
# Approving a `before:` checkpoint moves the waiting study on, and its new step's work can start.

"""

ROOMS_HEAD = """\
# Research stage groups, also used as columns on the Studies board. A step belongs to the group
# its `room:` names in workflow/steps.yaml. The legacy key keeps existing workflows compatible.
# The optional Lab view draws these groups using fixed built-in rooms; `per_project: true` draws
# one instance per live project. Existing placement metadata remains readable.

"""

STEP_KEYS = ("label", "do", "room", "also", "tags", "agent")
WORKFLOW_KEYS = ("title", "blurb", "default", "path", "routes", "use", "checkpoints", "nodes", "start", "tags")
CP_KEYS = ("id", "title", "before", "during", "at", "approver", "checks", "watch", "evidence", "means", "tell", "confirm", 'judge', 'decisions')


def _flow(d) -> str:
    return yaml.safe_dump(d, default_flow_style=True, sort_keys=False, width=10_000, allow_unicode=True).strip()


def _scalar(v) -> str:
    """One scalar on one line (a newline inside text becomes a space)."""
    if isinstance(v, str):
        v = " ".join(v.split("\n"))
    s = yaml.safe_dump(v, width=10_000, allow_unicode=True).strip()
    return s[:-3].strip() if s.endswith("...") else s


def dump_steps(steps: dict[str, dict]) -> str:
    """One step per line, its fields as a flow mapping; the shelves last."""
    order = [k for k, s in steps.items() if not s.get("shelf")] + [k for k, s in steps.items() if s.get("shelf")]
    width = max((len(k) for k in order), default=0) + 1
    lines = []
    for k in order:
        s = steps[k]
        d = {x: s[x] for x in STEP_KEYS if s.get(x) not in (None, "", [])}
        if order and k == next((x for x in order if steps[x].get("shelf")), None):
            lines.append("")
        lines.append(f"{(k + ':').ljust(width)} {_flow(d)}")
    return STEPS_HEAD + "\n".join(lines) + "\n"


def dump_workflow(w: dict) -> str:
    """A workflow file: scalars first, the path and each route on one line, checkpoints in block style."""
    out = []
    for k in ("title", "blurb"):
        if w.get(k):
            out.append(f"{k}: {_scalar(w[k])}")
    if w.get("default"):
        out.append("default: true")
    out.append("")
    out.append(f"path: {_flow(list(w.get('path') or []))}")
    if w.get("routes"):
        out += ["", "routes:"]
        width = max(len(k) for k in w["routes"]) + 1
        out += [f"  {(k + ':').ljust(width)} {_flow(v)}" for k, v in w["routes"].items() if v]
    if w.get("use"):
        out += ["", f"use: {_flow(w['use'])}"]
    for key in ('nodes', 'start', 'tags'):
        if w.get(key):
            out += ['', yaml.safe_dump({key: w[key]}, sort_keys=False, allow_unicode=True).rstrip()]
    cps = [{k: c[k] for k in CP_KEYS if c.get(k) not in (None, "", [])} for c in w.get("checkpoints") or []]
    if cps:
        out += ["", "checkpoints:"]
        for c in cps:
            first = True
            for k, v in c.items():
                val = _flow(v) if isinstance(v, (list, dict)) else _scalar(v)
                out.append(f"  {'- ' if first else '  '}{k}: {val}")
                first = False
    return WORKFLOW_HEAD + "\n".join(out).lstrip("\n") + "\n"


def dump_rooms(rooms: list[dict]) -> str:
    keep = ("id", "label", "title", "place", "facing", "per_project")
    return ROOMS_HEAD + "\n".join(f"- {_flow({k: r[k] for k in keep if k in r})}" for r in rooms) + "\n"


def write(root: Path, d: dict, only: set[str] | None = None) -> list[Path]:
    """Write a definition {steps, workflows, rooms} under root/workflow/. `only`: {"steps", "rooms",
    "workflow:<id>"} limits what is written; a file whose text wouldn't change is left alone. Workflow files of
    workflows no longer in d are removed when `only` is None. Returns the files written."""
    root = Path(root)
    done = []

    def put(rel: Path, text: str):
        p = root / rel
        try:
            if p.read_text(encoding="utf-8").replace("\r\n", "\n") == text:
                return                                   # unchanged: leave the file (and its timestamp) alone
        except OSError:
            pass
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        done.append(p)

    if only is None or "steps" in only:
        put(STEPS, dump_steps(d["steps"]))
    if only is None or "rooms" in only:
        put(ROOMS, dump_rooms(d.get("rooms") or []))
    ids = {w["id"] for w in d.get("workflows") or []}
    for w in d.get("workflows") or []:
        if only is None or f"workflow:{w['id']}" in only:
            put(WORKFLOWS / f"{w['id']}.yaml", dump_workflow(w))
    if only is None and (root / WORKFLOWS).is_dir():
        for f in (root / WORKFLOWS).glob("*.yaml"):
            if f.stem not in ids:
                f.unlink()
    return done
