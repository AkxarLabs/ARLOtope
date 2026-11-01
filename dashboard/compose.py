"""Compose: the lab's own definition, edited as a draft and published as one change (the Workflow lens).

What it covers is every file that says how this lab works (ROOTS): the steps, workflows, rooms and rules
(workflow/), the procedures and their variants (.claude/skills/), the subagent roles (agent-roles/), the checks
(checks/), the project types and domain profiles (templates/…, lab/templates/)
and the lab-wide instructions (lab/workflow/). Settings (lab/config.yaml) stay on the Settings page; one study's
own instructions and swaps stay on its page.

The first edit copies those files into a draft (lab/.bus/compose/draft/, their shas in draft.json). Every edit
after that changes only the draft: the lab and every run keep using the published files. An edit of the
definition reads it (tools/kernel/model.py), changes it, and writes the small file back whole
(tools/kernel/define.py) — the same code tools/new.py use. `problems()` is the kernel's
check on the draft, plus what no lab changes from here (the rules' safety tables, the hard rules' numbering)
and studies left on steps the draft no longer has. Publishing copies the changed files over the lab's
(refusing any the lab changed since the draft began), renders the docs and the role files, and keeps the
replaced files so it can be undone. What a draft — or a designer's draft — changes is said in plain lines, the
checkpoints first (tools/kernel/diff.py).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import textwrap
import time
from pathlib import Path

import yaml
import tagging

import ctx  # noqa: E402
from executor import procs  # noqa: E402
from kernel import define, diff, model, rules, studies  # noqa: E402

ROOTS = diff.ROOTS
TEXT_EXT = {".md", ".yaml", ".yml", ".py", ".js", ".txt", ".json", ".toml", ".tex", ".bib", ".cfg", ".ini", ".sh", ".csv"}
LOCKED_TABLES = ("pi_owned_config", "protected_paths", "rigor_floors", "config_procedures")
MAX_FILE = 400_000
RULES = "workflow/rules.yaml"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")


class ComposeError(ValueError):
    """Refused, with a message fit to show the PI."""


def _new():
    return ctx.tool("new")


def _home() -> Path:
    return ctx.LAB / ".bus" / "compose"


def _draft() -> Path:
    return _home() / "draft"


def _meta() -> dict | None:
    try:
        return json.loads((_home() / "draft.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def active() -> bool:
    return _meta() is not None and _draft().is_dir()


def _root() -> Path:
    return _draft() if active() else ctx.HUB


def _sha(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.is_file() else None


_walk = diff.files


def _begin() -> Path:
    """The draft, made on the first edit: a copy of the lab's definition files."""
    if active():
        return _draft()
    d = _draft()
    if d.exists():
        shutil.rmtree(d)
    files = diff.copy(ctx.HUB, d)
    (_home() / "draft.json").write_text(json.dumps({"created": ctx.ts(), "base": {r: _sha(f) for r, f in files.items()}},
                                                   indent=1), encoding="utf-8")
    return d


def changes() -> list[dict]:
    m = _meta()
    if not m or not _draft().is_dir():
        return []
    base, now = m.get("base") or {}, _walk(_draft())
    out = []
    for rel in sorted(set(base) | set(now)):
        if rel not in now:
            out.append({"path": rel, "status": "removed"})
        elif rel not in base:
            out.append({"path": rel, "status": "added"})
        elif _sha(now[rel]) != base[rel]:
            out.append({"path": rel, "status": "changed"})
    return out


# ── what's wrong with a definition, and what one changes ─────────────────────────────────────────
def problems(root: Path | None = None) -> list[str]:
    root = root or _root()
    try:
        probs = model.check(root, rules.check_names(root)) + rules.check(root)
    except Exception as e:  # noqa: BLE001 — a broken YAML file is a problem to show, not a crash
        return [f"the lab's definition can't be read: {e}"]
    return probs + (_locks(root) if root != ctx.HUB else []) + diff.orphans(ctx.HUB, root)


def _locks(root: Path) -> list[str]:
    out = []
    try:
        ra, rb = rules.load(ctx.HUB), rules.load(root)
    except Exception:  # noqa: BLE001 — reported by check
        return out
    for k in LOCKED_TABLES:
        if ra.get(k) != rb.get(k):
            out.append(f"rules.yaml `{k}` is read by the lab's safety code and can't change from here.")
    ids_a = [r.get("id") for r in ra.get("hard_rules") or []]
    ids_b = [r.get("id") for r in rb.get("hard_rules") or []]
    if ids_b[:len(ids_a)] != ids_a:
        out.append("Hard rules are cited by number: edit their text or add new ones at the end, but don't "
                   "remove or reorder them.")
    return out


# ── reading and writing the draft ────────────────────────────────────────────────────────────────
def _rel(path, *, text=True) -> str:
    rel = str(path or "").replace("\\", "/").strip().strip("/")
    parts = rel.split("/")
    if not rel or any(p in ("", ".", "..") for p in parts) or not any(rel.startswith(r + "/") for r in ROOTS):
        raise ComposeError(f"`{path}` is not part of the lab's definition")
    if text and Path(rel).suffix.lower() not in TEXT_EXT and Path(rel).name not in ('LICENSE', 'NOTICE'):
        raise ComposeError(f"`{rel}` is not a text file Compose edits")
    return rel


def _file(rel: str, root: Path | None = None) -> Path:
    base = root or _draft()
    path = base / rel
    parts = Path(rel).parts
    if not path.is_file() and parts[:2] == ('.claude', 'skills') and len(parts) > 3:
        from skill_resources import folders
        folder = folders(base).get(parts[2])
        if folder:
            path = folder.joinpath(*parts[3:])
    return path


def _read(rel: str, root: Path | None = None) -> str:
    return (ctx.read(_file(rel, root)) or "").replace("\r\n", "\n")


def _put(rel: str, text: str | None) -> None:
    """Write one file of the draft (None removes it)."""
    d = _begin()
    p = d / rel
    parts = Path(rel).parts
    if text is not None and parts[:2] == ('.claude', 'skills') and len(parts) > 3:
        from skill_resources import folders, copy
        folder = folders(d).get(parts[2])
        if folder and not (d / '.claude/skills' / parts[2]).exists():
            copy(folder, d / '.claude/skills' / parts[2])
    if text is None:
        if p.is_file():
            p.unlink()
            _prune(p.parent, d)
        return
    if len(text) > MAX_FILE:
        raise ComposeError(f"`{rel}` is too long ({len(text)} characters)")
    p.parent.mkdir(parents=True, exist_ok=True)
    ctx.write_keep_eol(p, ctx.read(p) or "", text)


def _prune(d: Path, top: Path) -> None:
    stops = {top} | {top / r for r in ROOTS}
    while d not in stops and d.is_dir() and not any(d.iterdir()):
        d.rmdir()
        d = d.parent


def _rmtree(rel: str) -> None:
    d = _begin()
    if (d / rel).is_dir():
        shutil.rmtree(d / rel)
        _prune((d / rel).parent, d)


def _edit(rel: str, fn) -> None:
    _put(rel, fn(_read(rel, _begin())))


def _definition() -> dict:
    """The draft's definition as plain data, to change and write back with _save()."""
    return define.read(_begin())


def export_procedure(query):
    from workflow_export import export
    try:
        return export(_root(), str(query.get('workflow') or '')), 200
    except ValueError as error:
        return {'error':str(error)}, 400


def _save(d: dict, only: set[str] | None = None) -> None:
    define.write(_begin(), d, only)


def _workflow(d: dict, wid: str) -> dict:
    w = next((x for x in d["workflows"] if x["id"] == wid), None)
    if not w:
        raise ComposeError(f"no workflow `{wid}`")
    return w


def _slug(v, what="id") -> str:
    v = str(v or "").strip()
    if not SLUG.fullmatch(v):
        raise ComposeError(f"the {what} must be lower-case letters, digits and dashes")
    return v


def _skill_md(name: str) -> str:
    return f".claude/skills/{name}/SKILL.md"


def _set_skill_meta(name: str, fields: dict) -> None:
    """Rewrite a SKILL.md's frontmatter: `description`, and the `arlotope:` block (the procedure's definition)."""
    rel = _skill_md(name)
    text = _read(rel, _begin())
    m = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ComposeError(f"/{name}'s SKILL.md has no frontmatter")
    chunks: list[list] = []
    for ln in m.group(1).split("\n"):
        if ln[:1] not in ("", " ", "\t", "#") and ":" in ln:
            chunks.append([ln.split(":", 1)[0].strip(), [ln]])
        elif chunks:
            chunks[-1][1].append(ln)
        else:
            chunks.append([None, [ln]])
    block = dict(model.skill_meta(text).get("arlotope") or {})
    fields = dict(fields)
    if "description" in fields:
        desc = " ".join(str(fields.pop("description") or "").split())
        line = [f"description: {json.dumps(desc, ensure_ascii=False)}"]
        hit = next((c for c in chunks if c[0] == "description"), None)
        if hit:
            hit[1] = line
        else:
            chunks.insert(1, ["description", line])
    for k, v in fields.items():
        if v is None or v == "" or v == []:
            block.pop(k, None)
        else:
            block[k] = v
    metadata = ("arlotope:\n" + textwrap.indent(yaml.safe_dump(block, sort_keys=False, allow_unicode=True, width=110), "  ")).rstrip("\n").split("\n") if block else None
    hit = next((c for c in chunks if c[0] == "arlotope"), None)
    if hit and metadata:
        hit[1] = metadata
    elif metadata:
        chunks.append(["arlotope", metadata])
    elif hit:
        chunks.remove(hit)
    fm = "\n".join(ln for c in chunks for ln in c[1])
    _put(rel, f"---\n{fm}\n---\n" + text[m.end():])


PROC_FIELDS = {"title", "does", "stops", "description", "kind", "level", "mode", "args", "hint", "launchable",
                 "dispatchable", "start", "outputs", "outcomes", "show_pi", "tags"}
CP_FIELDS = ("title", "before", "during", "at", "approver", "checks", "watch", "evidence", "means", "tell", "confirm", 'judge', 'decisions')


# ── the operations (POST /api/compose {op, …}) ───────────────────────────────────────────────────
def _op_write(b: dict) -> str:
    rel = _rel(b.get("path"))
    text = b.get("text")
    if text is not None and not isinstance(text, str):
        raise ComposeError("text must be a string (or null to remove the file)")
    _put(rel, text.replace("\r\n", "\n") if isinstance(text, str) else None)
    return f"{'removed' if text is None else 'saved'} {rel}"


def _op_instructions(b: dict) -> str:
    """Lab-wide added instructions: kind add (a procedure) | step | role (empty text removes them)."""
    kind, name = str(b.get("kind") or ""), str(b.get("name") or "")
    ins = ctx.tool("kernel").instructions
    if kind not in ins.KINDS:
        raise ComposeError("kind must be add | step | role")
    ins.write(kind, name, str(b.get("text") or ""), _begin())
    return "saved" if str(b.get("text") or "").strip() else "removed"


def _op_procedure(b: dict) -> str:
    """A procedure's own definition (its frontmatter)."""
    name = str(b.get("name") or "")
    if name not in model.load(_begin())["procedures"]:
        raise ComposeError(f"no procedure /{name}")
    fields = {k: v for k, v in (b.get("fields") or {}).items() if k in PROC_FIELDS}
    if not fields:
        raise ComposeError("nothing to change")
    if 'tags' in fields:
        from tagging import normalize
        fields['tags'] = normalize(fields['tags'])
    _set_skill_meta(name, fields)
    return f"/{name} updated"


def _op_step(b: dict) -> str:
    """Add (new: true, after: <step>, in: <workflow> to put it on that path), change (fields: label, do, also,
    room) or remove (remove: true — it leaves every path, with its routes and the checkpoints standing on it)."""
    sid = _slug(b.get("id"), "step id")
    d = _definition()
    f = b.get("fields") or {}
    procs = model.load(_begin())["procedures"]
    if b.get("remove"):
        if sid not in d["steps"] or d["steps"][sid].get("shelf"):
            raise ComposeError(f"no step `{sid}` to remove")
        del d["steps"][sid]
        for w in d["workflows"]:
            w["path"] = [x for x in w["path"] if x != sid]
            w["routes"] = {k: {o: t for o, t in v.items() if t != sid} for k, v in w["routes"].items() if k != sid}
            w["checkpoints"] = [c for c in w["checkpoints"] if (c.get("before") or c.get("during")) != sid]
        _save(d)
        _put(f"lab/workflow/step.{sid}.add.md", None)
        return f"step {sid} removed"
    if b.get("new"):
        if sid in d["steps"]:
            raise ComposeError(f"there is already a step `{sid}`")
        new = {"id": sid, "label": str(f.get("label") or sid.replace("-", " ").capitalize()), "also": []}
        steps = {}
        after = str(b.get("after") or "")
        for k, v in d["steps"].items():
            if v.get("shelf") and sid not in steps:
                steps[sid] = new
            steps[k] = v
            if k == after:
                steps[sid] = new
        steps.setdefault(sid, new)
        d["steps"] = steps
        wid = str(b.get("in") or "")
        if wid:
            w = _workflow(d, wid)
            at = w["path"].index(after) + 1 if after in w["path"] else len(w["path"])
            w["path"].insert(at, sid)
    if sid not in d["steps"]:
        raise ComposeError(f"no step `{sid}`")
    s = d["steps"][sid]
    if 'tags' in f:
        from tagging import normalize
        s['tags'] = normalize(f['tags'])
    if "label" in f and str(f["label"]).strip():
        s["label"] = " ".join(str(f["label"]).split())
    if "do" in f:
        if f["do"] and f["do"] not in procs:
            raise ComposeError(f"no procedure /{f['do']}")
        s["do"] = f["do"] or None
    if isinstance(f.get("also"), list):
        bad = [p for p in f["also"] if p not in procs]
        if bad:
            raise ComposeError(f"no procedure /{bad[0]}")
        s["also"] = [str(p) for p in f["also"]]
    if "room" in f:
        if f["room"] and f["room"] not in {r["id"] for r in d["rooms"]}:
            raise ComposeError(f"no room `{f['room']}`")
        s["room"] = f["room"] or None
    _save(d)
    return f"step {sid} {'added' if b.get('new') else 'updated'}"


def _op_room(b: dict) -> str:
    rid, f = str(b.get("id") or ""), b.get("fields") or {}
    d = _definition()
    r = next((x for x in d["rooms"] if x["id"] == rid), None)
    if not r:
        raise ComposeError(f"no room `{rid}`")
    for k in ("label", "title"):
        if str(f.get(k) or "").strip():
            r[k] = str(f[k]).strip()
    _save(d, {"rooms"})
    return "room updated"


def _op_workflow(b: dict) -> str:
    """Create (new: true, optionally like: <workflow> to copy), change (fields: title, blurb, path, use) or make
    default (default: true) one workflow."""
    wid = _slug(b.get("id"))
    f = b.get("fields") or {}
    d = _definition()
    said = []
    if b.get("new"):
        if any(w["id"] == wid for w in d["workflows"]):
            raise ComposeError(f"there is already a workflow `{wid}`")
        like = next((w for w in d["workflows"] if w["id"] == b.get("like")), None)
        w = json.loads(json.dumps(like)) if like else {"path": [], "routes": {}, "use": {}, "checkpoints": []}
        taken = {c["id"] for x in d["workflows"] for c in x["checkpoints"]}
        for c in w["checkpoints"]:          # a copy's checkpoints get ids of their own: approvals are kept per id
            base, n = f"{c['id']}-{wid}", 2
            c["id"] = base
            while c["id"] in taken:
                c["id"], n = f"{base}-{n}", n + 1
            taken.add(c["id"])
        w.update(id=wid, default=False, title=str(f.get("title") or (like or {}).get("title") or wid).strip())
        if b.get('preset') == 'single-agent':
            sid = wid[:36]+'-work'
            base, suffix = sid, 2
            while sid in d['steps']:
                sid, suffix = base+'-'+str(suffix), suffix+1
            room = d['rooms'][0]['id'] if d['rooms'] else None
            d['steps'][sid] = {'label':'Research','room':room,'do':None,'also':[]}
            w['path'] = [sid]
            w['nodes'] = {sid:{'label':'Research','procedure':None,'skills':[], 'instructions':
                'Investigate the research question. Follow the chosen skills in order. Record evidence, respect checkpoints and stop with a clear result or question.',
                'outputs':[], 'room':room,'context':{'mode':'fresh'},'agent':{'role':'general'},'next':[]}}
        d["workflows"].append(w)
        said.append(f"added the workflow {w['title']}")
    w = _workflow(d, wid)
    if 'tags' in f:
        from tagging import normalize
        w['tags'] = normalize(f['tags'])
    for k in ("title", "blurb"):
        if k in f:
            w[k] = " ".join(str(f[k] or "").split()) or None
    if isinstance(f.get("path"), list):
        w["path"] = [str(x) for x in f["path"]]
        w["routes"] = {k: v for k, v in w["routes"].items() if k in w["path"]}
        w["checkpoints"] = [c for c in w["checkpoints"] if (c.get("before") or c.get("during")) in w["path"]]
    if isinstance(f.get("use"), dict):
        w["use"] = {str(k): str(v) for k, v in f["use"].items() if v}
    if b.get("default"):
        for x in d["workflows"]:
            x["default"] = x is w
        said.append(f"{w.get('title') or wid} is now the default")
    _save(d)
    return "; ".join(said) or "workflow updated"


def _op_workflow_delete(b: dict) -> str:
    wid = _slug(b.get("id"))
    d = _definition()
    _workflow(d, wid)
    if len(d["workflows"]) == 1:
        raise ComposeError("the lab needs at least one workflow")
    was_default = any(w["id"] == wid and w.get("default") for w in d["workflows"])
    d["workflows"] = [w for w in d["workflows"] if w["id"] != wid]
    if was_default:
        d["workflows"][0]["default"] = True
    _save(d)
    return f"workflow {wid} removed"


def _op_graph(b: dict) -> str:
    from workflow_graph import validate
    nodes = b.get('nodes')
    problems = validate(nodes)
    if problems:
        raise ComposeError('; '.join(problems))
    d = _definition()
    w = _workflow(d, _slug(b.get('workflow'), 'workflow'))
    rooms = {r['id'] for r in d['rooms']}
    procs = model.load(_root())['procedures']
    for n in nodes:
        sid = _slug(n['id'], 'task')
        if 'tags' in n:
            n['tags'] = tagging.normalize(n['tags'])
        if n.get('room') not in rooms:
            raise ComposeError(f'{sid}: choose an existing room.')
        if n.get('procedure') and n['procedure'] not in procs:
            raise ComposeError(f'{sid}: choose an existing skill or own instructions.')
        d['steps'].setdefault(sid, {'label': n.get('label') or sid, 'room': n['room'], 'do': n.get('procedure') or None, 'also': []})
    removed = set(w['path']) - {n['id'] for n in nodes}
    w['path'] = [n['id'] for n in nodes]
    w['nodes'] = {n['id']: {k: v for k, v in n.items() if k != 'id'} for n in nodes}
    w['checkpoints'] = [c for c in w['checkpoints'] if (c.get('before') or c.get('during')) in w['path']]
    w['routes'] = {k: {name: to for name, to in routes.items() if to not in removed}
                   for k, routes in w['routes'].items() if k in w['path']}
    for checkpoint in w['checkpoints']:
        if checkpoint.get('decisions'):
            checkpoint['decisions'] = {name: to for name, to in checkpoint['decisions'].items() if to not in removed}
    if w.get('start'):
        from workflow_graph import targets
        w['start'] = [sid for sid in targets(w['start']) if sid not in removed]
    _save(d)
    return 'composition saved to your draft'


def _op_route(b: dict) -> str:
    """Where an outcome reported at a step leads, in one workflow: `to` a step of its path, a shelf, `ask` (you
    decide), or null to remove the route (the outcome then comes to you)."""
    wid, sid, outcome = _slug(b.get("workflow"), "workflow"), str(b.get("step") or ""), _slug(b.get("outcome"), "outcome")
    if outcome in model.RESERVED:
        raise ComposeError(f"`{outcome}` always means the same thing; it can't be routed")
    d = _definition()
    w = _workflow(d, wid)
    if sid not in w["path"]:
        raise ComposeError(f"{sid} is not on {wid}'s path")
    to = b.get("to")
    routes = w["routes"].setdefault(sid, {})
    if to in (None, ""):
        routes.pop(outcome, None)
    else:
        if to != model.ASK and to not in w["path"] and to not in model.SHELF_LABEL:
            raise ComposeError(f"{to} is not a step of {wid}")
        routes[outcome] = str(to)
    w["routes"] = {k: v for k, v in w["routes"].items() if v}
    _save(d, {f"workflow:{wid}"})
    return "route saved" if to else "route removed"


def _op_checkpoint(b: dict) -> str:
    """Add (new: true), change (fields) or remove (remove: true) one checkpoint of a workflow. Placement is
    `before: <step>` or `during: <step>` + `at:`; setting one clears the other."""
    wid, cid = _slug(b.get("workflow"), "workflow"), _slug(b.get("id"), "checkpoint id")
    f = {k: v for k, v in (b.get("fields") or {}).items() if k in CP_FIELDS}
    d = _definition()
    w = _workflow(d, wid)
    hit = next((c for c in w["checkpoints"] if c["id"] == cid), None)
    if b.get("remove"):
        if not hit:
            raise ComposeError(f"no checkpoint `{cid}` in {wid}")
        w["checkpoints"] = [c for c in w["checkpoints"] if c["id"] != cid]
        _save(d, {f"workflow:{wid}"})
        return "checkpoint removed"
    if b.get("new"):
        if any(c["id"] == cid for x in d["workflows"] for c in x["checkpoints"]):
            raise ComposeError(f"a checkpoint `{cid}` already exists; give this one another id")
        hit = {"id": cid, "approver": "me"}
        w["checkpoints"].append(hit)
    if not hit:
        raise ComposeError(f"no checkpoint `{cid}` in {wid}")
    if f.get("before"):
        hit.pop("during", None)
        hit.pop("at", None)
    if f.get("during"):
        hit.pop("before", None)
    for k, v in f.items():
        if isinstance(v, list):          # a check with parameters ({name: {param: value}}) is kept as it is
            v = [x if isinstance(x, dict) else str(x).strip() for x in v if isinstance(x, dict) or str(x).strip()]
        elif isinstance(v, str):
            v = " ".join(v.split())
        if v in (None, "", []):
            hit.pop(k, None)
        else:
            hit[k] = v
    _save(d, {f"workflow:{wid}"})
    return "checkpoint saved"


def _op_role(b: dict) -> str:
    name, f = str(b.get("name") or ""), b.get("fields") or {}
    rel = f"agent-roles/{name}.yaml"
    if not (_begin() / rel).is_file():
        raise ComposeError(f"no role {name}")

    def fn(text):
        for k in ("label", "description"):
            if k in f:
                v = json.dumps(" ".join(str(f[k] or "").split()), ensure_ascii=False)
                rx = re.compile(rf"^{k}:[ \t]*(?:\"(?:[^\"\\]|\\.)*\"|'[^']*'|[^#\n]*?)([ \t]+#[^\n]*)?$", re.M)
                text = rx.sub(lambda m, v=v, k=k: f"{k}: {v}{m.group(1) or ''}", text, count=1) if rx.search(text) \
                    else text.rstrip("\n") + f"\n{k}: {v}\n"
        return text
    _edit(rel, fn)
    return "role updated"


def _rule_span(text: str, rid: str) -> tuple[int, int]:
    m = re.search(rf"^  - id: {re.escape(rid)}[ \t]*$", text, re.M)
    if not m:
        raise ComposeError(f"no rule `{rid}`")
    nxt = re.search(r"^(?:  - |\S)", text[m.end():], re.M)
    end = m.end() + (nxt.start() if nxt else len(text) - m.end())
    while text[m.start():end].endswith("\n\n"):
        end -= 1
    return m.start(), end


def _op_rule(b: dict) -> str:
    rid = str(b.get("id") or "")
    if b.get("remove"):
        _edit(RULES, lambda t: (lambda a, e: t[:a] + t[e:])(*_rule_span(t, rid)))
        return f"rule {rid} removed"
    text = " ".join(str(b.get("text") or "").split())
    if not text:
        raise ComposeError("a rule needs its text")
    checks = [str(c) for c in (b.get("checks") or []) if str(c).strip()]
    entry = f"  - id: {rid}\n" + (f"    checks: [{', '.join(checks)}]\n" if checks else "") + \
        f"    text: {json.dumps(text, ensure_ascii=False)}\n"

    def fn(t):
        a, e = _rule_span(t, rid)
        return t[:a] + entry + t[e:]
    _edit(RULES, fn)
    return f"rule {rid} updated"


def _blank_type(name: str, title: str | None) -> None:
    """A project type from nothing — for a lab that has none to copy yet: one TYPE.md to fill in."""
    rel = f"lab/templates/project-types/{name}/TYPE.md"
    if (_begin() / rel).exists() or (_begin() / f"templates/project-types/{name}/TYPE.md").exists():
        raise ComposeError(f"there is already a project type '{name}'")
    _put(rel, f"# Project type: `{name}`\n\n{title or 'What a project of this type is, in a sentence or two.'}\n\n"
              "- **An experiment is:** …\n- **Runner:** …\n- **Conventions:** what every agent in a project of this type should know.\n")


def _op_copy(b: dict) -> str:
    """Add a component by copying the closest one (tools/new.py, run on the draft)."""
    new, d = _new(), _begin()
    kind, name, like = str(b.get("kind") or ""), str(b.get("name") or "").strip(), str(b.get("like") or "")
    title = str(b.get("title") or "").strip() or None
    try:
        if kind == "procedure":
            new.new_skill(d, name, like, step=str(b.get("step") or "") or None, title=title)
        elif kind == "step":
            new.new_step(d, name, like, do=str(b.get("do") or "") or None, label=title,
                         workflow=str(b.get("in") or "") or None, after=str(b.get("after") or "") or None)
        elif kind == "workflow":
            new.new_workflow(d, name, like, title=title)
        elif kind == "room":
            new.new_room(d, name, like, steps=[s for s in (b.get("steps") or []) if s], title=title, plain=bool(b.get("plain")))
        elif kind == "role":
            new.new_role(d, name, like, label=title)
        elif kind == "check":
            new.new_check(d, name, like)
        elif kind == "type" and not like:
            _blank_type(new._name(name), title)
        elif kind == "type":
            new.new_type(d, name, like)
        elif kind == "rule":
            new.new_rule(d, name, str(b.get("text") or ""), which=str(b.get("list") or "hard"),
                         check=str(b.get("check") or "") or None)
        else:
            raise ComposeError("kind must be procedure | step | workflow | room | role | check | type | rule")
    except new.NewError as e:
        raise ComposeError(str(e)) from None
    return f"made {name} from {like}" if like else f"added {name}"


def _op_delete(b: dict) -> str:
    kind, name = str(b.get("kind") or ""), str(b.get("name") or "")
    d = _begin()
    if not re.match(r"^[a-z0-9][a-z0-9._-]{0,79}$", name):
        raise ComposeError(f"bad name {name!r}")
    if kind == "procedure":
        from skill_resources import folders, exclude
        if name not in folders(d):
            raise ComposeError(f"no procedure /{name}")
        used = [s for s, x in model.load(d)["steps"].items() if x.get("do") == name]
        if used:
            raise ComposeError(f"/{name} does the work of {', '.join(used)} ; give those steps another procedure first")
        _rmtree(f".claude/skills/{name}")
        _put(f".claude/skills/.imports/{name}.json", None)
        exclude(d, name)
        _put(f"lab/workflow/{name}.add.md", None)
        defn = _definition()
        for s in defn["steps"].values():
            s["also"] = [p for p in s["also"] if p != name]
        for w in defn["workflows"]:
            w["use"] = {k: v for k, v in w["use"].items() if name not in (k, v)}
        _save(defn)
    elif kind == "role":
        for f in (f"agent-roles/{name}.yaml", f"agent-roles/{name}.md", f"lab/workflow/roles/{name}.add.md"):
            _put(f, None)
    elif kind == "check":
        _put(f"checks/{name.replace('-', '_')}.py", None)
    elif kind == "type":
        own = f"lab/templates/project-types/{name}"
        _rmtree(own if (d / own).is_dir() else f"templates/project-types/{name}")
    elif kind == "room":
        defn = _definition()
        if not any(r["id"] == name for r in defn["rooms"]):
            raise ComposeError(f"no room `{name}`")
        here = [s for s, x in defn["steps"].items() if x.get("room") == name]
        move = str(b.get("move_to") or "")
        if here and move not in {r["id"] for r in defn["rooms"]} - {name}:
            raise ComposeError(f"say which room its steps ({', '.join(here)}) move to")
        for s in here:
            defn["steps"][s]["room"] = move
        defn["rooms"] = [r for r in defn["rooms"] if r["id"] != name]
        _save(defn, {"rooms", "steps"})
    elif kind == "step":
        return _op_step({"id": name, "remove": True})
    elif kind == "workflow":
        return _op_workflow_delete({"id": name})
    else:
        raise ComposeError("kind must be procedure | role | check | type | room | step | workflow")
    return f"{kind} {name} removed"


# ── designs: what a designer agent drafted, taken whole into the draft ───────────────────────────
def _designs_dir() -> Path:
    return ctx.LAB / ".bus" / "designs"








def workflow_designs() -> list[dict]:
    """Definition changes a designer drafted (/design workflow …), newest first: each a folder laid over the
    lab's definition (workflow/workflows/<id>.yaml, workflow/steps.yaml, .claude/skills/<variant>/…), with
    the PI's request, the designer's notes, its problems and what it changes."""
    out, d = [], _designs_dir() / "workflow"
    for f in sorted((x for x in d.iterdir() if x.is_dir()), key=lambda x: x.stat().st_mtime, reverse=True)[:10] if d.is_dir() else []:
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,60}$", f.name):
            continue
        probs, said = diff.check_overlay(ctx.HUB, f)
        out.append({"id": f.name, "ts": ctx.ts(f.stat().st_mtime),
                    "request": (ctx.read(f / "request.md") or "").strip()[:600],
                    "notes": (ctx.read(f / "notes.md") or "").strip()[:2000],
                    "files": sorted(diff.design_files(f)), "problems": probs, "changes": said})
    return out


def _op_workflow_design_use(b: dict) -> str:
    """Take a designer's draft into yours (Review shows the change and the full check before you publish)."""
    did = str(b.get("id") or "")
    folder = _designs_dir() / "workflow" / did
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,60}$", did) or not folder.is_dir():
        raise ComposeError("no such design")
    probs, _said = diff.check_overlay(ctx.HUB, folder)
    if probs:
        raise ComposeError("this design has problems (" + "; ".join(probs[:2]) + "); ask for another")
    for rel, f in diff.design_files(folder).items():
        _put(rel, f.read_text(encoding="utf-8"))
    return "the design is in your draft; review it, then publish"


def _op_extension_use(b: dict) -> str:
    """Take a ready-made extension (extensions/<name>/) into the draft: its workflows, skills and checks as they are,
    its steps and rooms joined to the lab's. Review shows what it changes and checks the lab before you publish."""
    x = next((e for e in diff.extensions(ctx.HUB) if e["name"] == str(b.get("name") or "")), None)
    if not x:
        raise ComposeError("no such extension")
    diff.lay(x["path"], _begin(), merge=True)
    return f"{x['title']} is in your draft; review it, then publish"


def _op_discard(b: dict) -> str:
    if _draft().exists():
        shutil.rmtree(_draft())
    (_home() / "draft.json").unlink(missing_ok=True)
    model._cache.clear()
    return "draft discarded; the lab is unchanged"


def _op_skill_import(body):
    from skill_resources import inspect, copy, exclude
    info = inspect(body.get('path') or '')
    if info['name'] in model.load(_root())['procedures']:
        raise ComposeError('This skill name is already in the Lab. Use it, or import a separately named variant.')
    target = _begin() / '.claude/skills' / info['name']
    copy(body['path'], target)
    receipt = target.parent / '.imports' / (info['name'] + '.json')
    receipt.parent.mkdir(exist_ok=True)
    receipt.write_text(json.dumps({'source': Path(body['path']).name, 'sha256': info['sha256']}, indent=2) + '\n', encoding='utf-8')
    exclude(_draft(), info['name'], False)
    return f"Imported /{info['name']} into your draft"


def _op_skill_create(body):
    name = _slug(body.get('name'))
    if name in model.load(_root())['procedures']:
        raise ComposeError('This skill name already exists.')
    description = str(body.get('description') or '').strip()
    text = str(body.get('text') or '').strip()
    if not description or not text:
        raise ComposeError('Add a description and instructions.')
    _put(f'.claude/skills/{name}/SKILL.md', '---\nname: ' + name + '\ndescription: ' + json.dumps(description) + '\n---\n\n' + text + '\n')
    return f'Created /{name} in your draft'


OPS = {"skill-import": _op_skill_import, "skill-create": _op_skill_create, "graph": _op_graph, "write": _op_write, "instructions": _op_instructions, "procedure": _op_procedure, "step": _op_step,
       "room": _op_room, "role": _op_role, "rule": _op_rule, "copy": _op_copy,
       "delete": _op_delete, "discard": _op_discard, "workflow": _op_workflow, "workflow-delete": _op_workflow_delete,
       "route": _op_route, "checkpoint": _op_checkpoint,
       "workflow-design-use": _op_workflow_design_use, "extension-use": _op_extension_use}


def op(body: dict) -> tuple[dict, int]:
    """One edit of the draft. After it the draft's generated text (each skill's head) is refreshed, so what the
    review shows is what will be published."""
    name = str(body.get("op") or "")
    if name == 'skill-import' and body.get('preview'):
        from skill_resources import inspect
        try:
            info = inspect(body.get('path') or '')
            return {'ok': True, 'skill': info, 'exists': info['name'] in model.load(_root())['procedures']}, 200
        except (ValueError, OSError, UnicodeError) as error:
            return {'error': str(error)}, 400
    if name == "publish":
        return publish(body)
    if name == "undo":
        return undo(body)
    fn = OPS.get(name)
    if not fn:
        return {"error": f"unknown op {name!r}"}, 400
    try:
        note = fn(body)
    except (ComposeError, ValueError, OSError, yaml.YAMLError, model.ModelError) as e:
        return {"error": str(e)}, 400
    if active():
        try:
            ctx.tool("lab_docs").render(_draft())
        except Exception:  # noqa: BLE001 — a broken file shows up in problems()
            pass
    return {"ok": True, "note": note, "draft": draft_info()}, 200


# ── publish and undo ─────────────────────────────────────────────────────────────────────────────
def _after_change(touched: list[str]) -> list[str]:
    """What follows a change to the live definition: the generated docs and role files, and every study waiting at
    a checkpoint the change removed or moved is decided again (studies.reconcile) — said in the result."""
    warnings = []
    try:
        for r in ctx.tool("kernel").studies.reconcile(ctx.HUB, by="pi"):
            res = r["result"]
            warnings.append(f"{r['study']} no longer waits at {r['checkpoint']}: "
                            + (f"it moved to {res['step']}" if res.get("moved") else f"it now waits at {res.get('waiting')}"))
    except Exception as e:  # noqa: BLE001 — the publish is done; say what could not follow
        warnings.append(f"the studies waiting at changed checkpoints could not be updated: {e}")
    try:
        ctx.tool("lab_docs").render(ctx.HUB)
    except Exception as e:  # noqa: BLE001
        warnings.append(f"the generated docs could not be refreshed: {e}")
    if any(p.startswith(("agent-roles/", "lab/workflow/roles/")) for p in touched):
        r = procs.run([sys.executable, str(ctx.HUB / "tools" / "role_sync.py"), "render"], cwd=str(ctx.HUB),
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            warnings.append("re-rendering the role files failed: " + (r.stderr or r.stdout)[-300:])
    return warnings


def _history() -> list[dict]:
    out = []
    for f in sorted((_home() / "history").glob("*/publish.json"), reverse=True):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def publish(body: dict) -> tuple[dict, int]:
    ch = changes()
    if not ch:
        return {"error": "the draft has no changes"}, 400
    probs = problems()
    if probs:
        return {"error": "fix these first: " + " · ".join(probs[:3]), "problems": probs}, 409
    base = (_meta() or {}).get("base") or {}
    moved = [c["path"] for c in ch if _sha(ctx.HUB / c["path"]) != base.get(c["path"])]
    if moved:
        return {"error": "changed in the lab since your draft began (by a proposal you accepted, or by hand): "
                         + ", ".join(moved[:5]) + "; discard the draft and redo the edit", "conflicts": moved}, 409
    said = diff.summary(ctx.HUB, _draft())
    hid = time.strftime("%Y%m%d-%H%M%S")
    hdir = _home() / "history" / hid
    rec = {"id": hid, "ts": ctx.ts(), "note": str(body.get("note") or "").strip()[:300], "files": [], "changes": said}
    for c in ch:
        rel, real = c["path"], ctx.HUB / c["path"]
        if real.is_file():
            (hdir / "before" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(real, hdir / "before" / rel)
        if c["status"] == "removed":
            real.unlink(missing_ok=True)
            _prune(real.parent, ctx.HUB)
        else:
            real.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_draft() / rel, real)
        rec["files"].append({"path": rel, "status": c["status"], "after": _sha(real)})
    hdir.mkdir(parents=True, exist_ok=True)
    (hdir / "publish.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    _op_discard({})
    warnings = _after_change([f["path"] for f in rec["files"]])
    ctx.pi_log({"action": "compose.publish", "id": hid, "files": [f["path"] for f in rec["files"]], "note": rec["note"]})
    ctx.emit_hub("lab_composed", detail=rec["note"] or (said[0] if said else f"{len(ch)} change(s) to the lab's definition"))
    return {"ok": True, "id": hid, "note": f"Published {len(ch)} change{'s' if len(ch) != 1 else ''}; runs started "
                                            "from now use them", "warnings": warnings}, 200


def undo(body: dict) -> tuple[dict, int]:
    hid = str(body.get("id") or "")
    hist = [h for h in _history() if not h.get("undone")]
    if not hist or hist[0].get("id") != hid:
        return {"error": "only the latest publish can be undone"}, 400
    if active():
        return {"error": "publish or discard your draft first"}, 409
    rec, hdir = hist[0], _home() / "history" / hid
    moved = [f["path"] for f in rec["files"] if _sha(ctx.HUB / f["path"]) != f.get("after")]
    if moved:
        return {"error": "changed since that publish: " + ", ".join(moved[:5]), "conflicts": moved}, 409
    for f in rec["files"]:
        real, before = ctx.HUB / f["path"], hdir / "before" / f["path"]
        if before.is_file():
            real.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(before, real)
        else:
            real.unlink(missing_ok=True)
            _prune(real.parent, ctx.HUB)
    rec["undone"] = ctx.ts()
    (hdir / "publish.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    warnings = _after_change([f["path"] for f in rec["files"]])
    ctx.pi_log({"action": "compose.undo", "id": hid})
    ctx.emit_hub("lab_composed", detail=f"undid the publish of {rec['ts']}")
    return {"ok": True, "note": "Undone: the lab is back as it was before that publish", "warnings": warnings}, 200


# ── what the page shows (GET /api/compose, /api/compose/file) ─────────────────────────────────────
def draft_info() -> dict:
    on = active()
    ch = changes() if on else []
    return {"active": on, "created": (_meta() or {}).get("created") if on else None, "changes": ch,
            "problems": problems() if on else [], "summary": diff.summary(ctx.HUB, _draft()) if on and ch else [],
            "affects": diff.affected(ctx.HUB, _draft()) if on and ch else []}


def _origin(rel: str) -> str:
    """'built-in' when this code ships the same path, else 'yours'."""
    return "built-in" if (ctx.ROOT / rel).exists() else "yours"


def _plain(md: str) -> str:
    """Markdown → one line of plain text: no backticks, emphasis, links or HTML comments."""
    t = re.sub(r"<!--.*?-->", " ", md or "", flags=re.S)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", t.replace("`", ""))
    t = re.sub(r"(?<!\w)_{1,2}([^_]+)_{1,2}(?!\w)", r"\1", t)
    return " ".join(t.split())


_CMD = re.compile(r"`?((?:uv run|python3?)\s[^`\n]*)`?")


def _check_doc(text: str) -> tuple[str, list[str]]:
    """A check's docstring → (a one-line plain description, the commands that run it)."""
    m = re.search(r'"""(.*?)"""', text or "", re.S)
    doc = m.group(1) if m else ""
    usage = [" ".join(c.split()).rstrip(".") for c in _CMD.findall(doc)]
    first = next((p for p in re.split(r"\n\s*\n", doc.strip()) if p.strip() and not _CMD.search(p.strip().split("\n")[0])), "")
    first = re.sub(r"^\s*guard\.py\s+[\w-]+\s+[—-]+\s*", "", first)   # "guard.py name — what it checks"
    return _plain(first)[:220], usage[:3]


def _type_card(txt: str) -> tuple[str, str]:
    """TYPE.md → (its first heading, its first paragraph), both as plain text."""
    lines = re.sub(r"<!--.*?-->", "", (txt or "").replace("\r\n", "\n"), flags=re.S).split("\n")
    head = next((ln.lstrip("#").strip() for ln in lines if ln.startswith("#")), "")
    body, para = [], False
    for ln in lines:
        if ln.startswith("#"):
            continue
        if ln.strip():
            if ln.lstrip().startswith(("-", "*", "|", ">")) and not body:
                break
            body.append(ln.strip())
            para = True
        elif para:
            break
    return _plain(head), _plain(" ".join(body))[:400]


def view(q: dict | None = None) -> tuple[dict, int]:
    on = active()
    root = _draft() if on else ctx.HUB
    labfiles = ctx.labfiles
    out: dict = {"ok": True, "draft": draft_info()}
    try:
        m = model.load(root)
        v = model.view(root)
    except Exception as e:  # noqa: BLE001 — show the draft and the error; the PI fixes the file
        out["error"] = f"the lab's definition can't be read: {e}"
        return out, 200
    from skill_resources import folders
    skill_folders = folders(root)
    procs = {}
    for name, p in m["procedures"].items():
        folder = skill_folders[name]
        meta = model.skill_meta(ctx.read(folder / 'SKILL.md') or '')
        own = meta.get("arlotope") or {}
        procs[name] = {**{k: v for k, v in p.items() if not k.startswith("_")}, "description": meta.get("description", ""),
                       "own": sorted(own), "like": own.get("like"), "origin": _origin(f".claude/skills/{name}/SKILL.md"),
                       "steps": [s for s, d in m["steps"].items() if name in [d.get("do"), *d["also"]]],
                       "variants": sorted(n for n, x in m["procedures"].items() if x.get("like") == name),
                       "files": sorted('.claude/skills/' + name + '/' + f.relative_to(folder).as_posix() for f in folder.rglob("*")
                                       if f.is_file() and "__pycache__" not in f.parts) if folder.is_dir() else []}
    roles = []
    rdir = root / "agent-roles"
    for r, label in model.roles(root).items():
        y = labfiles.load_yaml(rdir / f"{r}.yaml")
        roles.append({"name": r, "label": label, "description": str(y.get("description") or ""),
                      "like": y.get("like"), "origin": _origin(f"agent-roles/{r}.yaml"),
                      "files": [f"agent-roles/{r}.yaml", f"agent-roles/{r}.md"]})
    rl = rules.load(root)
    rule_lists = {g: [{"id": x.get("id"), "text": str(x.get("text") or ""), "checks": x.get("checks") or []}
                      for x in rl.get(f"{g}_rules") or []] for g in ("hard", "subagent", "project")}
    checks = []
    files = {f.name: f for d in (ctx.ROOT / "checks", root / "checks") if d.is_dir() for f in d.glob("*.py")}   # the lab's win
    for fname, f in sorted(files.items()):
        txt = ctx.read(f) or ""
        nm = re.search(r'^NAME = "([^"]+)"', txt, re.M)
        doc, usage = _check_doc(txt)
        checks.append({"name": nm.group(1) if nm else f.stem.replace("_", "-"), "file": f"checks/{fname}",
                       "guard": bool(nm), "doc": doc, "usage": usage, "origin": _origin(f"checks/{fname}")})
    types = []
    for name, txt in labfiles.project_types(root).items():
        own = (root / "lab" / "templates" / "project-types" / name).is_dir()
        base = f"{'lab/templates' if own else 'templates'}/project-types/{name}"
        head, desc = _type_card(txt)
        types.append({"name": name, "title": head or name, "description": desc, "origin": "yours" if own else "built-in",
                      "files": sorted(f.relative_to(root).as_posix() for f in (root / base).rglob("*") if f.is_file())})
    domains = [{"name": n, "file": p.relative_to(root).as_posix() if p.is_relative_to(root) else None}
               for n, p in labfiles.domain_profiles(root).items()]
    ins = ctx.tool("kernel").instructions
    out.update({
        'frameworks': __import__('frameworks').installed(__import__('frameworks').definitions(root)),
        "steps": v["steps"], "workflows": v["workflows"], "rooms": v["rooms"], "procedures": procs, "roles": roles,
        "tags": tagging.catalog(ctx.HUB, m),
        "audits": [a["name"] for a in rules.audits(root)], "watch": rl.get("watch") or [],
        "workflow_designs": workflow_designs(),
        "extensions": [{"name": x["name"], "title": x["title"], "blurb": x["blurb"],
                        "added": all((root / f).is_file() for f in x["files"] if f.startswith("workflow/workflows/"))}
                       for x in diff.extensions(ctx.HUB)],
        "rules": rule_lists, "locked": {k: rl.get(k) for k in LOCKED_TABLES if k in rl}, "checks": checks,
        "types": types, "domains": domains, "custom": ins.status(root),
        "proposals": [{k: r.get(k) for k in ("id", "kind", "name", "study", "why", "by", "ts")} for r in ins.proposals(ctx.HUB)],
        "history": [{k: h.get(k) for k in ("id", "ts", "note", "undone", "changes")} | {"n": len(h.get("files") or []),
                    "files": [f["path"] for f in h.get("files") or []][:12]} for h in _history()[:15]],
        "studies_at": _study_counts(),
    })
    return out, 200


def _study_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        for r in studies.rows(ctx.HUB):
            if r.get("state"):
                out[r["state"]] = out.get(r["state"], 0) + 1
    except Exception:  # noqa: BLE001
        pass
    return out


def run_tasks(body):
    import executor
    import lab_profile
    slug = ctx.safe_id(body.get('study'))
    if not slug:
        return {'error': 'Choose a study.'}, 400
    try:
        executor.check_enabled(executor.Lab(ctx.HUB), parent=body.get('parent') or None)
        ids = lab_profile.start_graph(executor.Lab(ctx.HUB), slug, executor.enqueue, executor.RunSpec,
                                      retry=body.get('retry') is True, parent=body.get('parent') or None,
                                      created_by='run:'+str(body['parent']) if body.get('parent') else 'dashboard')
        ctx.KICK.set()
        return {'ok': True, 'runs': ids}, 200
    except (ValueError, OSError) as error:
        return {'error': str(error)}, 400


def file_get(q: dict) -> tuple[dict, int]:
    """One definition file: as the draft has it (or the lab, with no draft) and as published."""
    try:
        rel = _rel(q.get("path"), text=False)
    except ComposeError as e:
        return {"error": str(e)}, 400

    def norm(s):
        return s.replace("\r\n", "\n") if s is not None else None
    if Path(rel).suffix.lower() not in TEXT_EXT and Path(rel).name not in ('LICENSE', 'NOTICE'):
        file = _file(rel, _root())
        return {'ok': True, 'path': rel, 'resource': True, 'bytes': file.stat().st_size if file.is_file() else 0}, 200
    cur, pub = _read(rel, _root()) or None, _read(rel, ctx.HUB) or None
    if cur is None and pub is None and rel.startswith("checks/"):
        cur = pub = ctx.read(ctx.ROOT / rel)      # a check this code ships that the lab doesn't override
    return {"ok": True, "path": rel, "text": norm(cur), "published": norm(pub)}, 200
