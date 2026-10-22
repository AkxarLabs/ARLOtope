"""The lab's definition: its steps, its workflows, the rooms of its world and its procedures.

    workflow/steps.yaml            the places a study can be, shared by every workflow
    workflow/workflows/<id>.yaml   a workflow: its path of steps, where each outcome leads, its checkpoints
    workflow/rooms.yaml            where the steps stand in the dashboard's world
    .claude/skills/<name>/SKILL.md a procedure: its frontmatter's `newts:` block defines it

A study walks its workflow's `path`. Each step names the procedure that does its work (`do:`); a procedure
never names a step — it ends by reporting an OUTCOME, and the workflow says where that leads: `done` goes to
the next step on the path, `park` and `kill` to the two shelves every lab has, and any other outcome to where
the workflow's `routes:` send it (or to the PI, who decides). A checkpoint is the PI's approval: `before:` a
step (a study can't enter it unapproved) or `during:` one (the agent stops at that point inside it).

Pure and import-safe: no I/O at import; everything is read from a hub (the lab's own files, else this code's)
and cached until a file changes. A lab made before steps existed (workflow/stages.yaml) is read through
`convert()`, the same conversion `newts migrate` writes out.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

import yaml
import tagging
import labfiles

CODE = Path(__file__).resolve().parents[2]          # this code's own hub (the template a lab was made from)
WORKFLOW = Path("workflow")
STEPS = WORKFLOW / "steps.yaml"
WORKFLOWS = WORKFLOW / "workflows"
ROOMS = WORKFLOW / "rooms.yaml"
LEGACY = WORKFLOW / "stages.yaml"
SKILLS = Path(".claude") / "skills"

DONE, PARK, KILL, ASK = "done", "park", "kill", "ask"
SHELVES = {PARK: "parked", KILL: "killed"}            # outcome → the shelf it puts a study on
SHELF_LABEL = {"parked": "Parked", "killed": "Killed"}
RESERVED = {DONE, PARK, KILL}
APPROVERS = ("me", "me-or-campaign", "auto", 'agent')

# what a skill's `newts:` block may leave out (a skill with no block at all is a launchable utility)
PROC_DEFAULTS = {"kind": "utility", "level": "hub", "mode": "headless", "args": "text?", "launchable": True}
KINDS = ("stage", "driver", "entry", "utility")
_NOT_INHERITED = {"title", "does", "start", "brief_note", "like", "_own"}   # what a `like:` copy says for itself
SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_FM = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
_cache: dict[str, tuple[tuple, dict]] = {}


class ModelError(ValueError):
    pass


# ── reading ──────────────────────────────────────────────────────────────────────────────────────
def hub_of(hub=None) -> Path:
    return Path(hub).resolve() if hub else CODE


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def _yaml(p: Path):
    return yaml.safe_load(_read(p)) if p.is_file() else None


def root_of(hub=None) -> Path:
    """Where the lab's definition lives: the lab's own workflow/ folder, else this code's."""
    h = hub_of(hub)
    return h if (h / STEPS).is_file() or (h / LEGACY).is_file() else CODE


def skills_root(hub=None) -> Path:
    h = hub_of(hub)
    return h / SKILLS if (h / SKILLS).is_dir() else CODE / SKILLS


def _files(root: Path, skills: Path) -> list[Path]:
    out = [root / STEPS, root / ROOMS, root / LEGACY]
    out += sorted((root / WORKFLOWS).glob("*.yaml")) if (root / WORKFLOWS).is_dir() else []
    out += sorted(f for f in skills.glob("*/SKILL.md") if f.is_file()) if skills.is_dir() else []
    return out


def _sig(files: list[Path]) -> tuple:
    out = []
    for f in files:
        try:
            out.append((str(f), f.stat().st_mtime_ns))
        except OSError:
            out.append((str(f), None))
    return tuple(out)


def load(hub=None) -> dict:
    """The signature-checked definition, reused inside an explicit read batch."""
    return labfiles.cached_read(('model', hub_of(hub)), lambda: _load(hub))


def _load(hub=None) -> dict:
    """The definition, normalised (cached until any of its files changes):

        steps      {id: {id, label, do, also, room, shelf}}   in library order, the two shelves last
        workflows  [{id, title, blurb, default, path, routes, use, checkpoints}]   the default first
        rooms      [{id, label, title, place?, facing?}]
        procedures {name: definition}

    Raises ModelError (or a yaml error) on a file it can't read."""
    root, skills = root_of(hub), skills_root(hub)
    from skill_resources import folders
    methods = [p / 'SKILL.md' for p in folders(hub_of(hub)).values()]
    files = _files(root, skills) + methods + [CODE / SKILLS / '.excluded.json', hub_of(hub) / SKILLS / '.excluded.json']
    sig = _sig(files)
    key = f"{hub_of(hub)}|{root}|{skills}"
    hit = _cache.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    if (root / STEPS).is_file():
        raw = {"steps": _yaml(root / STEPS) or {}, "rooms": _yaml(root / ROOMS) or [],
               "workflows": [dict(_yaml(f) or {}, id=f.stem) for f in sorted((root / WORKFLOWS).glob("*.yaml"))]
               if (root / WORKFLOWS).is_dir() else []}
    else:
        raw = convert(_yaml(root / LEGACY) or {})
    m = normalise(raw)
    m["procedures"] = procedures(skills, m, files=methods)
    _cache[key] = (sig, m)
    return m


def normalise(raw: dict) -> dict:
    """Fill defaults and put things in their order; never validates (check() does)."""
    if not isinstance(raw.get("steps"), dict):
        raise ModelError("steps.yaml must map each step id to its definition")
    steps: dict[str, dict] = {}
    for sid, s in raw["steps"].items():
        s = dict(s or {}) if isinstance(s, dict) else {}
        s.update(id=str(sid), label=str(s.get("label") or str(sid).replace("-", " ").capitalize()),
                 also=[str(x) for x in (s.get("also") or [])], shelf=str(sid) in SHELF_LABEL)
        if 'tags' in s:
            s['tags'] = tagging.normalize(s['tags'])
        steps[str(sid)] = s
    for sid, label in SHELF_LABEL.items():                       # every lab has both shelves
        steps.setdefault(sid, {"id": sid, "label": label, "also": [], "shelf": True})
    steps = {k: v for k, v in steps.items() if not v["shelf"]} | {k: v for k, v in steps.items() if v["shelf"]}
    wfs = []
    for w in raw.get("workflows") or []:
        if not isinstance(w, dict) or not w.get("id"):
            continue
        w = dict(w)
        if 'tags' in w:
            w['tags'] = tagging.normalize(w['tags'])
        if isinstance(w.get('nodes'), dict):
            w['nodes'] = {key:dict(value, tags=tagging.normalize(value['tags'])) if isinstance(value, dict) and 'tags' in value else value
                          for key,value in w['nodes'].items()}
        w["id"] = str(w["id"])
        w.setdefault("title", w["id"].replace("-", " ").capitalize())
        w["path"] = [str(x) for x in (w.get("path") or [])]
        w["routes"] = {str(k): {str(o): str(t) for o, t in (v or {}).items()}
                       for k, v in (w.get("routes") or {}).items() if isinstance(v, dict)}
        w["use"] = {str(k): str(v) for k, v in (w.get("use") or {}).items()}
        cps = []
        for c in w.get("checkpoints") or []:
            if isinstance(c, dict) and c.get("id"):
                c = dict(c)
                c.setdefault("approver", "me")
                c.setdefault("title", str(c["id"]).replace("-", " ").capitalize())
                cps.append(c)
        w["checkpoints"] = cps
        w["default"] = bool(w.get("default"))
        wfs.append(w)
    wfs.sort(key=lambda w: (not w["default"], str(w.get("order", "")), w["title"].lower()))
    rooms = [{k:v for k,v in r.items() if k != 'per_project'}
             for r in (raw.get("rooms") or []) if isinstance(r, dict) and r.get("id")]
    return {"steps": steps, "workflows": wfs, "rooms": rooms}


# ── procedures: a skill folder each ──────────────────────────────────────────────────────────────
def skill_meta(text: str) -> dict:
    """A SKILL.md's frontmatter, read the way agent CLIs read it: top-level `key: value` lines taken as text
    (descriptions need not be strict YAML), and the `newts:` block — the procedure definition — as YAML."""
    m = _FM.match((text or "").replace("\r\n", "\n"))
    out: dict = {}
    if not m:
        return out
    key, buf = None, []

    def flush():
        if key == "newts":
            try:
                block = yaml.safe_load(textwrap.dedent("\n".join(buf[1:])))
            except yaml.YAMLError:
                block = None
            out["newts"] = block if isinstance(block, dict) else {}
        elif key:
            out[key] = " ".join(x.strip() for x in buf).strip().strip("'\"")

    for ln in m.group(1).split("\n"):
        if ln[:1] not in ("", " ", "\t", "#") and ":" in ln:
            flush()
            key, _, val = ln.partition(":")
            key, buf = key.strip(), [val]
        else:
            buf.append(ln)
    flush()
    return out


def procedures(skills: Path, m: dict | None = None, files=None) -> dict[str, dict]:
    """{name: definition} from each skill's frontmatter: the steps' procedures first, in step order. A skill
    with `like: <other>` inherits the other's definition and overrides what it lists itself."""
    found = {}
    files = files if files is not None else (sorted(f for f in skills.glob("*/SKILL.md") if f.is_file()) if skills.is_dir() else [])
    for f in files:
        fm = skill_meta(_read(f))
        block = fm.get("newts")
        p = dict(PROC_DEFAULTS)
        if not isinstance(block, dict):          # an older lab's skill with no block: this code's definition of it
            ours = CODE / SKILLS / f.parent.name / "SKILL.md"
            if ours.is_file() and ours.resolve() != f.resolve():
                p.update(skill_meta(_read(ours)).get("newts") or {})
        p.update(block if isinstance(block, dict) else {})
        if 'tags' in p:
            p['tags'] = tagging.normalize(p['tags'])
        p["_own"] = set(block) if isinstance(block, dict) else set()
        p.setdefault("title", fm.get("name") or f.parent.name)
        p.setdefault("does", str(fm.get("description") or "").split(". ")[0][:200])
        outs = p.get("outcomes") or []          # [done, not-novel], or {not-novel: "what it means"}
        if isinstance(outs, dict):
            p["outcome_notes"] = {str(k): str(v) for k, v in outs.items() if v}
        p["outcomes"] = [str(x) for x in outs]
        for k in ("reads", "outputs", "writes"):   # lists of text; one line given alone is a list of one
            v = p.get(k)
            if v is not None:
                p[k] = [str(x) for x in v] if isinstance(v, list) else [str(v)]
        found[f.parent.name] = p
    for name, p in found.items():
        base, seen = p.get("like"), {name}
        while base in found and base not in seen:
            seen.add(base)
            parent = found[base]
            for k, v in parent.items():
                if k not in p["_own"] and k not in _NOT_INHERITED:
                    p[k] = v
            base = parent.get("like") if "like" in parent.get("_own", set()) else None
    for p in found.values():
        if p.get('like') and 'ui' not in p['_own'] and isinstance(p.get('ui'), dict):
            p['ui'] = {k: v for k, v in p['ui'].items() if k != 'task'}
        p.pop("_own", None)
    order = {"stage": 0, "driver": 1, "entry": 2, "utility": 3}
    stepped = list(dict.fromkeys(x for s in (m or {}).get("steps", {}).values()
                                 for x in [s.get("do"), *s.get("also", [])] if x in found))
    rest = sorted((n for n in found if n not in stepped), key=lambda n: (order.get(found[n].get("kind"), 9), n))
    return {n: found[n] for n in stepped + rest}


# ── asking the definition ────────────────────────────────────────────────────────────────────────
def steps(hub=None) -> dict[str, dict]:
    return load(hub)["steps"]


def step(sid: str, hub=None) -> dict | None:
    return steps(hub).get(sid)


def workflows(hub=None) -> list[dict]:
    return load(hub)["workflows"]


def default_workflow(hub=None) -> str | None:
    wfs = workflows(hub)
    return wfs[0]["id"] if wfs else None


def workflow(wid: str | None = None, hub=None) -> dict:
    """A workflow by id (the default for None or an unknown id). Raises ModelError when the lab has none."""
    wfs = workflows(hub)
    if not wfs:
        raise ModelError("the lab has no workflow (workflow/workflows/*.yaml)")
    return next((w for w in wfs if w["id"] == wid), wfs[0])


def procedure(name: str, hub=None) -> dict | None:
    return load(hub)["procedures"].get(name)


def checkpoints(wid: str | None = None, hub=None) -> list[dict]:
    return workflow(wid, hub)["checkpoints"]


def all_checkpoints(hub=None) -> dict[str, dict]:
    """{checkpoint id: definition (+ its workflow)} across every workflow (ids are unique per lab)."""
    out: dict[str, dict] = {}
    for w in workflows(hub):
        for c in w["checkpoints"]:
            out.setdefault(c["id"], dict(c, workflow=w["id"]))
    return out


def checkpoint(cid: str, wid: str | None = None, hub=None) -> dict | None:
    if wid:
        return next((dict(c, workflow=wid) for c in checkpoints(wid, hub) if c["id"] == cid), None)
    return all_checkpoints(hub).get(cid)


def does(sid: str, wid: str | None = None, use: dict | None = None, hub=None) -> str | None:
    """The procedure that does a step's work: a study's own `use:` swap, else its workflow's, else the step's."""
    s = step(sid, hub)
    node = workflow(wid, hub).get('nodes', {}).get(sid, {}) if workflows(hub) else {}
    if 'procedure' in node:
        proc = node['procedure']
    else:
        proc = (s or {}).get('do')
    if not proc:
        return None
    for swap in (use or {}, workflow(wid, hub)["use"] if workflows(hub) else {}):
        if proc in swap:
            return swap[proc]
    return proc


def offers(sid: str, wid: str | None = None, use: dict | None = None, hub=None) -> list[str]:
    """What a study at this step can run: its procedure first, then the step's others (with swaps applied)."""
    s = step(sid, hub) or {}
    swaps = [use or {}, workflow(wid, hub)["use"] if workflows(hub) else {}]
    owner = does(sid, wid, use, hub)
    out = [owner] if owner else []
    for p in s.get("also") or []:
        for swap in swaps:
            if p in swap:
                p = swap[p]
                break
        out.append(p)
    return list(dict.fromkeys(out))


def outcome_target(wid: str | None, sid: str, outcome: str, hub=None) -> str | None:
    """Where an outcome reported at a step leads: a step id, a shelf, ASK (the PI decides), or None (`done`
    at the end of the path: the study is finished)."""
    if outcome in SHELVES:
        return SHELVES[outcome]
    w = workflow(wid, hub)
    if outcome == DONE:
        path = w["path"]
        if sid not in path:
            return ASK
        i = path.index(sid)
        return path[i + 1] if i + 1 < len(path) else None
    return (w["routes"].get(sid) or {}).get(outcome, ASK)


def before_on_the_way(wid: str | None, frm: str, to: str, hub=None) -> list[dict]:
    """The `before:` checkpoints a move frm → to passes: every one in front of a step after frm, up to and
    including to (a move back, or onto a shelf, passes none)."""
    w = workflow(wid, hub)
    path = w["path"]
    if to not in path:
        return []
    j = path.index(to)
    i = path.index(frm) if frm in path else -1
    if j <= i:
        return []
    ahead = set(path[i + 1:j + 1])
    return [dict(c, workflow=w["id"]) for c in w["checkpoints"] if c.get("before") in ahead]


TERMS = ("before", "during", "at", "means", "checks")     # what approving a checkpoint agrees to


def terms(cp: dict) -> str:
    """A checkpoint's terms, as a short fingerprint: where it stands, what it covers and what it checks. An approval
    records the terms it was given under; change them and the approval no longer stands (its title, the agents'
    `tell` and its evidence list are wording, not terms)."""
    import hashlib  # noqa: PLC0415
    import json  # noqa: PLC0415
    body = json.dumps({k: cp.get(k) for k in (*TERMS, *(k for k in ('judge','decisions') if k in cp))}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def may_approve(cp: dict, by: str) -> bool:
    """Whether `by` (pi | campaign:<name> | auto) may approve this checkpoint as it is defined now."""
    appr = cp.get("approver", "me")
    if str(by).startswith("campaign:"):
        return appr in ('me-or-campaign', 'auto')
    if by == "auto":
        return appr == "auto"
    if str(by).startswith('judge:'):
        return appr == 'agent'
    return True


def waits_at(cp: dict, wid: str | None = None, hub=None) -> str | None:
    """The step where a study waits for this checkpoint: the step before its `before`, or its `during` step."""
    if cp.get("during"):
        return cp["during"]
    path = workflow(wid, hub)["path"]
    b = cp.get("before")
    return path[path.index(b) - 1] if b in path and path.index(b) > 0 else None


def is_end(sid: str, wid: str | None = None, hub=None) -> bool:
    """A shelf, or the last step of the workflow's path."""
    s = step(sid, hub)
    if s and s["shelf"]:
        return True
    path = workflow(wid, hub)["path"] if workflows(hub) else []
    return bool(path) and path[-1] == sid


def roles(hub=None) -> dict[str, str]:
    """{subagent role: its label} — agent-roles/<role>.yaml (the lab's own, else this code's)."""
    h = hub_of(hub)
    d = h / "agent-roles" if (h / "agent-roles").is_dir() else CODE / "agent-roles"
    out = {}
    for f in sorted(d.glob("*.yaml")):
        try:
            meta = yaml.safe_load(_read(f)) or {}
        except yaml.YAMLError:
            meta = {}
        out[f.stem] = str((meta if isinstance(meta, dict) else {}).get("label") or f.stem.replace("-", " ").capitalize())
    return out


def rooms(hub=None) -> list[dict]:
    """The world's rooms, each with the steps that stand in it."""
    st = steps(hub)
    return [dict(r, steps=[s for s, d in st.items() if d.get("room") == r["id"]]) for r in load(hub)["rooms"]]


# ── validation ───────────────────────────────────────────────────────────────────────────────────
def check_spec(item) -> tuple[str, dict]:
    """One entry of a checkpoint's `checks:` or `watch:` — a check's name, or `{name: {param: value}}`, whose
    parameters the check receives as `--param value` (its own add_args says which it takes)."""
    if isinstance(item, dict) and len(item) == 1:
        (name, params), = item.items()
        return str(name), dict(params) if isinstance(params, dict) else {}
    return str(item), {}


def check_label(item) -> str:
    name, params = check_spec(item)
    return name + (" (" + ", ".join(f"{k}={v}" for k, v in params.items()) + ")" if params else "")


def _path_of(output) -> str:
    """The file an `outputs:` entry names: its first word ('studies/<slug>/proposal.md with …')."""
    words = str(output).split()
    return words[0].rstrip(":,;") if words else ""


def check(hub=None, checks: set[str] | None = None) -> list[str]:
    """Problems with the definition (empty = consistent). `checks`: the names a checkpoint may run (the caller
    knows them: checks/ scripts and rules.yaml audits); None skips that test."""
    try:
        m = load(hub)
    except (OSError, yaml.YAMLError, ModelError) as e:
        return [f"workflow: {e}"]
    probs: list[str] = []
    st, procs, room_ids = m["steps"], m["procedures"], {r["id"] for r in m["rooms"]}
    for sid, s in st.items():
        if not SLUG.match(sid):
            probs.append(f"step {sid!r}: ids are lowercase letters, digits, - . _")
        for p in [s.get("do")] * bool(s.get("do")) + s["also"]:
            if p not in procs:
                probs.append(f"step {sid}: unknown procedure {p!r} (no .claude/skills/{p}/SKILL.md)")
        if s.get("room") and room_ids and s["room"] not in room_ids:
            probs.append(f"step {sid}: unknown room {s['room']!r}")
        if s["shelf"] and s.get("do"):
            probs.append(f"step {sid}: a shelf does no work (no do:)")
        if s.get('agent') is not None and (not isinstance(s['agent'], dict) or
                not isinstance(s['agent'].get('role', ''), str)):
            probs.append(f'step {sid}: agent.role must be a role identifier.')
    plots: dict[tuple, str] = {}
    for r in m["rooms"]:
        pl, rid = r.get("place"), r["id"]
        if pl is not None:
            if not (isinstance(pl, list) and len(pl) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in pl)):
                probs.append(f"room {rid}: place must be [column, row], two whole numbers")
            elif pl == [0, 0]:
                probs.append(f"room {rid}: place [0, 0] is the plaza with the PI's desk")
            elif tuple(pl) in plots:
                probs.append(f"rooms {plots[tuple(pl)]} and {rid} both stand at {pl}")
            else:
                plots[tuple(pl)] = rid
        if r.get("facing") is not None and r.get("facing") not in ("n", "e", "s", "w"):
            probs.append(f"room {rid}: facing must be n, e, s or w")
    if not m["workflows"]:
        probs.append("the lab has no workflow (workflow/workflows/<id>.yaml)")
    if sum(w["default"] for w in m["workflows"]) > 1:
        probs.append("more than one workflow says default: true")
    cids: set[str] = set()
    for w in m["workflows"]:
        probs += _check_workflow(w, st, procs, cids, checks)
        for sid, node in (w.get('nodes') or {}).items() if isinstance(w.get('nodes'), dict) else []:
            if isinstance(node, dict) and isinstance(node.get('external'), dict):
                import frameworks
                external = node['external']
                try:
                    frameworks.validate(external)
                    definition = frameworks.definitions(hub).get(external['framework']) or {}
                    if external['phase'] not in definition.get('phases', {}):
                        probs.append(f'workflow {w["id"]}: task {sid} names an unknown framework phase')
                except ValueError:
                    pass  # the graph validator reports the malformed external field
            if isinstance(node, dict) and isinstance(node.get('room'), str) and node['room'] and node['room'] not in room_ids:
                probs.append(f"workflow {w['id']}: task {sid} names an unknown room")
    from skill_resources import folders
    inventory = folders(hub_of(hub))
    for name, p in procs.items():
        fm_name = skill_meta(_read(inventory[name] / 'SKILL.md')).get('name')
        if fm_name and fm_name != name:
            probs.append(f"skill {name}: its frontmatter says name: {fm_name} (the folder name is the procedure)")
        if p.get("kind") not in KINDS:
            probs.append(f"procedure {name}: kind must be one of {', '.join(KINDS)}")
        if p.get("level") not in ("hub", "project") or p.get("mode") not in ("headless", "interactive"):
            probs.append(f"procedure {name}: level must be hub|project and mode headless|interactive")
        for o in p["outcomes"]:
            if not SLUG.match(o):
                probs.append(f"procedure {name}: outcome {o!r} is not a plain name")
        if p.get("like") and p["like"] not in procs:
            probs.append(f"procedure {name}: like {p['like']!r} is not a procedure")
        ui = p.get('ui')
        if isinstance(ui, dict) and 'task' in ui:
            task = ui['task']
            if not isinstance(task, dict) or not isinstance(task.get('label'), str) or not task['label'].strip() or (
                    'role' in task and (not isinstance(task['role'], str) or not SLUG.fullmatch(task['role']))):
                probs.append(f"procedure {name}: ui.task needs a label and an optional role identifier")
    h = hub_of(hub)
    rdir = h / "agent-roles" if (h / "agent-roles").is_dir() else CODE / "agent-roles"
    for r in roles(hub):
        if not (rdir / f"{r}.md").is_file():
            probs.append(f"role {r}: no agent-roles/{r}.md beside its .yaml")
    return probs


def _check_workflow(w: dict, st: dict, procs: dict, cids: set, checks: set | None) -> list[str]:
    wid, probs = w["id"], []
    if not SLUG.match(wid):
        return [f"workflow {wid!r}: ids are lowercase letters, digits, - . _"]
    path = w["path"]
    if w.get('nodes') and not isinstance(w['nodes'], dict):
        return ['Node settings must map task IDs to definitions.']
    if w.get('nodes'):
        from .branches import nodes
        from workflow_graph import validate, targets
        if any(not isinstance(n, dict) for n in w['nodes'].values()):
            return ['Each node setting must be an object.']
        probs += validate(nodes(w, st))
        if not isinstance(w['nodes'], dict) or any(s not in path for s in w['nodes']):
            probs.append('Node settings must map task IDs on this workflow path.')
        for node in nodes(w, st):
            if node.get('procedure') and node['procedure'] not in procs:
                probs.append(f"Task {node['id']}: unknown procedure.")
            if isinstance(node.get('skills'), list) and any(p not in procs for p in node['skills']):
                probs.append(f"Task {node['id']}: unknown skill in sequence.")
        if any(s not in path for s in targets(w.get('start') or path[:1])):
            probs.append('Choose existing start tasks.')
    if not path:
        probs.append(f"workflow {wid}: its path has no steps")
    for s in path:
        if s not in st:
            probs.append(f"workflow {wid}: unknown step {s!r} (add it to workflow/steps.yaml)")
        elif st[s]["shelf"]:
            probs.append(f"workflow {wid}: {s} is a shelf, not a step on a path")
    if len(set(path)) != len(path):
        probs.append(f"workflow {wid}: a step appears twice on its path")
    for sid, outs in w["routes"].items():
        if sid not in path:
            probs.append(f"workflow {wid}: routes from {sid!r}, which is not on its path")
        for o, t in outs.items():
            if o in RESERVED:
                probs.append(f"workflow {wid}: {sid}: `{o}` always means the same thing and can't be routed")
            elif not SLUG.match(o):
                probs.append(f"workflow {wid}: {sid}: outcome {o!r} is not a plain name")
            if t != ASK and t not in path and t not in SHELF_LABEL:
                probs.append(f"workflow {wid}: {sid}: {o} → {t!r} is not a step of this workflow")
    for a, b in w["use"].items():
        for p in (a, b):
            if p not in procs:
                probs.append(f"workflow {wid}: use: unknown procedure {p!r}")
    for c in w["checkpoints"]:
        cid = str(c["id"])
        if not SLUG.match(cid):
            probs.append(f"workflow {wid}: checkpoint {cid!r} needs a plain id")
            continue
        if cid in cids:
            probs.append(f"checkpoint id {cid} is used twice (ids are unique across workflows)")
        cids.add(cid)
        where = [k for k in ("before", "during") if c.get(k)]
        if len(where) != 1:
            probs.append(f"checkpoint {cid}: give exactly one of before: <step> or during: <step>")
        for k in where:
            if c[k] not in path:
                probs.append(f"checkpoint {cid}: {k} {c[k]!r} is not a step of {wid}")
        if c.get("before") and path and c["before"] == path[0] and not w.get('nodes'):
            probs.append(f"checkpoint {cid}: nothing comes before the first step")
        if c.get("during") and not str(c.get("at") or "").strip():
            probs.append(f"checkpoint {cid}: a during-checkpoint needs at: (the point the agent stops at)")
        if c.get("approver") not in APPROVERS:
            probs.append(f"checkpoint {cid}: approver must be one of {', '.join(APPROVERS)}")
        if c.get("approver") == "auto" and not c.get("checks"):
            probs.append(f"checkpoint {cid}: an automatic checkpoint needs checks: to pass")
        if c.get('approver') == 'agent':
            judge = c.get('judge') or {}
            if not isinstance(judge, dict) or not isinstance(judge.get('skill', 'gate-review'), str) or judge.get('skill', 'gate-review') not in procs or not c.get('evidence'):
                probs.append(f'checkpoint {cid}: an agent judge needs an existing skill and evidence files.')
            if isinstance(judge, dict) and (type(judge.get('max_attempts', 3)) is not int or not 1 <= judge.get('max_attempts', 3) <= 100):
                probs.append(f'checkpoint {cid}: choose a positive judge attempt limit.')
            if isinstance(judge, dict):
                for field in ('max_visits', 'max_minutes'):
                    if field in judge and (type(judge[field]) is not int or judge[field] < 1):
                        probs.append(f'checkpoint {cid}: {field} must be a positive integer.')
        decisions = c.get('decisions') or {}
        if not isinstance(decisions, dict):
            probs.append(f'checkpoint {cid}: decisions must map names to destinations.')
            decisions = {}
        for choice, destination in decisions.items():
            if not isinstance(choice, str) or not SLUG.match(choice) or destination not in [*path, 'continue', *SHELF_LABEL]:
                probs.append(f'checkpoint {cid}: choose named decisions and existing destinations.')
        for x in list(c.get("checks") or []) + list(c.get("watch") or []):
            name, params = check_spec(x)
            if isinstance(x, dict) and (len(x) != 1 or not isinstance(next(iter(x.values())), dict)
                                        or not all(isinstance(v, (str, int, float, bool)) for v in params.values())):
                probs.append(f"checkpoint {cid}: a check with parameters is written {{name: {{param: value}}}}")
            elif checks is not None and name not in checks:
                probs.append(f"checkpoint {cid}: unknown check {name!r} (checks/{name.replace('-', '_')}.py, or a rules.yaml audit)")
    made: set[str] = set()                     # what the steps so far produce, for the next ones' reads:
    for s in path:
        if s not in st:
            continue
        do = (w.get('nodes', {}).get(s) or {}).get('procedure', st[s].get("do"))
        here = ([w["use"].get(do, do)] if do else []) + list(st[s]["also"])
        for p in here:
            for r in (procs.get(p) or {}).get("reads") or []:
                if str(r) not in made:
                    probs.append(f"workflow {wid}: at {s}, /{p} reads {r}, which no step before it produces "
                                 "(a procedure's outputs:)")
        made |= {_path_of(o) for p in here for o in (procs.get(p) or {}).get("outputs") or []}
    return probs


# ── the dashboard's view ─────────────────────────────────────────────────────────────────────────
PROC_VIEW = ("title", "does", "stops", "kind", "level", "mode", "args", "hint", "launchable", "outputs", "outcomes", "tags",
             "reads", "uses", "start", "ui", "show_pi", "guide", "world", "like")


def view(hub=None) -> dict:
    """The definition as the dashboard reads it."""
    m = load(hub)
    wfs = []
    for w in m["workflows"]:
        wfs.append({k: w[k] for k in ("id", "title", "blurb", "default", "path", "routes", "use", "checkpoints", "nodes", "start", "tags") if k in w})
    return {
        "steps": [{k: v for k, v in s.items() if v not in (None, [], False) or k in ("id", "shelf")} for s in m["steps"].values()],
        "workflows": wfs, "rooms": rooms(hub),
        "procedures": {n: {k: p[k] for k in PROC_VIEW if k in p} for n, p in m["procedures"].items()},
    }


# ── an older lab: workflow/stages.yaml → steps + workflows + rooms ───────────────────────────────
def convert(doc: dict) -> dict:
    """An older manifest (states, stages, rooms with state lists, next/offer_for_state, back_edges, workflows
    or numbered gates) as the new definition. Each state becomes a step that does what next_for_state said
    came next there; each back-edge a route; a checkpoint's `then:` becomes the work of the step it guards
    (or a step of its own when that step already does something else)."""
    states = [s for s in doc.get("states") or [] if isinstance(s, dict) and s.get("id")]
    side = [s for s in doc.get("side_states") or [] if isinstance(s, dict) and s.get("id")]
    nxt = doc.get("next_for_state") or {}
    offer = doc.get("offer_for_state") or {}
    room_of = {x: r["id"] for r in doc.get("rooms") or [] for x in r.get("states") or []}
    steps: dict[str, dict] = {}
    for s in states + side:
        sid = s["id"]
        do = nxt.get(sid)
        do = do.get("unsigned") if isinstance(do, dict) else do
        d = {"label": s.get("label") or sid}
        if do and sid not in SHELF_LABEL:
            d["do"] = do
        also = [p for p in offer.get(sid) or [] if p != do]
        if also:
            d["also"] = also
        if s.get("room") or room_of.get(sid):
            d["room"] = s.get("room") or room_of.get(sid)
        steps[sid] = d
    order = [s["id"] for s in states]
    wfs = [w for w in doc.get("workflows") or [] if isinstance(w, dict) and w.get("id")]
    if not wfs:
        names = {1: "approve-proposal", 2: "approve-full-runs", 3: "finalize-paper"}
        cps = []
        for g in doc.get("gates") or []:
            n = g.get("n")
            cp = {"id": names.get(n, f"gate-{n}"), "title": g.get("title") or f"Gate {n}", "means": g.get("means", "")}
            if g.get("before"):
                cp["before"] = g["before"]
            else:
                cp.update({"during": g.get("at"), "at": "full-scale runs"})
            cps.append(cp)
        wfs = [{"id": "research", "title": "Research paper", "steps": order, "checkpoints": cps}]
    edges = [tuple(e) for e in doc.get("back_edges") or [] if isinstance(e, (list, tuple)) and len(e) == 2]
    out_wfs = []
    for i, w in enumerate(wfs):
        path = list(w.get("steps") or order)
        cps = []
        for c in w.get("checkpoints") or []:
            c = dict(c)
            then = c.pop("then", None)
            if c.get("detect"):
                c["watch"] = [c.pop("detect")]
            b = c.get("before")
            if then and b in path:
                if not steps.get(b, {}).get("do"):
                    steps.setdefault(b, {"label": b})["do"] = then
                elif steps[b]["do"] != then:
                    if then not in steps:
                        steps[then] = {"label": then.replace("-", " ").capitalize(), "do": then}
                        if steps[b].get("room"):
                            steps[then]["room"] = steps[b]["room"]
                    if then not in path:
                        path.insert(path.index(b), then)
                    c["before"] = then
            cps.append(c)
        routes: dict[str, dict] = {}
        for a, b in edges:
            if a in path and b in path:
                routes.setdefault(a, {})[f"to-{b}"] = b
        out_wfs.append({"id": w["id"], "title": w.get("title") or w["id"], "blurb": w.get("blurb", ""),
                        "default": i == 0, "path": path, "routes": routes, "checkpoints": cps})
    rooms = [{k: v for k, v in r.items() if k not in ('states', 'per_project')}
             for r in doc.get("rooms") or [] if isinstance(r, dict)]
    return {"steps": steps, "workflows": out_wfs, "rooms": rooms}
