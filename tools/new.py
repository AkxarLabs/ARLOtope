#!/usr/bin/env python3
"""Add something to the lab by copying the closest thing it already has — no hand-edited YAML.

    uv run --with pyyaml python tools/new.py skill    <name> --like <skill>    [--step <step>] [--title "…"]
    uv run --with pyyaml python tools/new.py step     <id>   --like <step>     [--do <proc>] [--label "…"] [--in <workflow> --after <step>]
    uv run --with pyyaml python tools/new.py workflow <id>   --like <workflow> [--title "…"]
    uv run --with pyyaml python tools/new.py room     <id>   --like <room>     [--steps a,b] [--title "…"] [--plain]
    uv run --with pyyaml python tools/new.py role     <name> --like <role>     [--label "…"]
    uv run --with pyyaml python tools/new.py check    <name> --like <check>
    uv run --with pyyaml python tools/new.py type     <name> --like <type>
    uv run --with pyyaml python tools/new.py rule     <id>   --text "**Title.** What it says." [--list hard|subagent|project] [--check <name>]

What each one does:
  skill     copies the skill's folder; the copy says `like: <skill>`, so it inherits the definition (level,
            mode, args, outcomes, …) and overrides what you change. It is a VARIANT: use it in a workflow
            (`use:`), for one study (`newts workflow use`), or as a step's work (`--step` offers it there).
  step      copies a step (its label, work and room) under a new id; `--in W --after S` puts it on workflow W's
            path right after S.
  workflow  copies a workflow file under a new id (checkpoint ids get `-<id>` so they stay unique).
  room      adds a stage group to workflow/rooms.yaml; `--steps` moves those steps into it.
  role      copies agent-roles/<role>.yaml + .md with `like: <role>` and renders it for every CLI.
  check     copies checks/<check>.py under the new name (the guard finds it by itself).
  type      copies templates/project-types/<type>/ into lab/templates/project-types/<name>/.
  rule      appends a rule to workflow/rules.yaml.
Then the generated docs are refreshed (`newts docs`). A lab's own components are the PI's: a headless run
can't write them, and the signature guard refuses this tool from a run.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HUB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from kernel import define, model, rules  # noqa: E402

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


class NewError(ValueError):
    """Refused, with a message fit to show the PI."""


def _name(name: str) -> str:
    if not NAME_RE.match(name or ""):
        raise NewError(f"'{name}': use lower-case letters, digits and dashes (e.g. data-room)")
    return name


def _title(name: str) -> str:
    return name.replace("-", " ").capitalize()


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def _rename_refs(text: str, old: str, new: str) -> str:
    """`/old` (the slash command) and `brief old` → the new name; other mentions are left to the PI."""
    text = re.sub(r"(?<![\w/-])/" + re.escape(old) + r"(?![\w-])", "/" + new, text)
    return re.sub(r"\bbrief " + re.escape(old) + r"(?![\w-])", "brief " + new, text)


definition = define.read      # the lab's definition as plain data to change and write back (define.write)


# ── skill ────────────────────────────────────────────────────────────────────────────────────────
def new_skill(hub: Path, name: str, like: str, step: str | None = None, title: str | None = None) -> list[Path]:
    name = _name(name)
    skills = hub / ".claude" / "skills"
    from skill_resources import folders
    src, dst = folders(hub).get(like, skills / like), skills / name
    if not (src / "SKILL.md").is_file():
        raise NewError(f"no skill '{like}' to copy (.claude/skills/{like}/SKILL.md)")
    if dst.exists():
        raise NewError(f".claude/skills/{name}/ already exists")
    text = _read(src / "SKILL.md")
    m = re.match(r"\A---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    if not m:
        raise NewError(f"/{like}'s SKILL.md has no frontmatter")
    meta = model.skill_meta(text)
    desc = str(meta.get("description") or "").replace('"', "'")
    fm = (f"---\nname: {name}\ndescription: \"A variant of /{like} — say here what /{name} does. ({desc[:200]})\"\n"
          f"newts:\n  like: {like}            # its definition is /{like}'s, except what is listed below\n"
          f"  title: {title or _title(name)}\n---\n")
    body = _rename_refs(text.replace("\r\n", "\n")[m.end():], like, name)
    out = [dst / "SKILL.md"]
    _write(dst / "SKILL.md", fm + body)
    for extra in sorted(src.iterdir()):
        if extra.name != "SKILL.md":
            (shutil.copytree if extra.is_dir() else shutil.copy2)(extra, dst / extra.name)
            out.append(dst / extra.name)
    if step:
        d = definition(hub)
        if step not in d["steps"] or d["steps"][step].get("shelf"):
            raise NewError(f"no step '{step}'")
        if name not in d["steps"][step]["also"]:
            d["steps"][step]["also"].append(name)
        out += define.write(hub, d, {"steps"})
    return out


# ── step, workflow ───────────────────────────────────────────────────────────────────────────────
def new_step(hub: Path, sid: str, like: str, do: str | None = None, label: str | None = None,
             workflow: str | None = None, after: str | None = None) -> list[Path]:
    sid = _name(sid)
    d = definition(hub)
    if sid in d["steps"]:
        raise NewError(f"there is already a step '{sid}'")
    if like not in d["steps"] or d["steps"][like].get("shelf"):
        raise NewError(f"no step '{like}' to copy")
    if do and do not in model.load(hub)["procedures"]:
        raise NewError(f"no procedure '{do}' (a skill folder in .claude/skills/)")
    base = d["steps"][like]
    new = {"id": sid, "label": label or _title(sid), "do": do or base.get("do"), "room": base.get("room"), "also": []}
    steps = {}
    for k, v in d["steps"].items():
        steps[k] = v
        if k == like:
            steps[sid] = new
    d["steps"] = steps
    only = {"steps"}
    if workflow:
        w = next((x for x in d["workflows"] if x["id"] == workflow), None)
        if not w:
            raise NewError(f"no workflow '{workflow}'")
        at = after or like
        if at not in w["path"]:
            raise NewError(f"'{at}' is not on {workflow}'s path")
        w["path"].insert(w["path"].index(at) + 1, sid)
        only.add(f"workflow:{workflow}")
    return define.write(hub, d, only)


def new_workflow(hub: Path, wid: str, like: str, title: str | None = None) -> list[Path]:
    wid = _name(wid)
    d = definition(hub)
    if any(w["id"] == wid for w in d["workflows"]):
        raise NewError(f"there is already a workflow '{wid}'")
    src = next((w for w in d["workflows"] if w["id"] == like), None)
    if not src:
        raise NewError(f"no workflow '{like}' to copy")
    w = dict(src, id=wid, title=title or _title(wid), default=False,
             checkpoints=[dict(c, id=f"{c['id']}-{wid}") for c in src["checkpoints"]])
    d["workflows"].append(w)
    return define.write(hub, d, {f"workflow:{wid}"})


# ── room ─────────────────────────────────────────────────────────────────────────────────────────


def new_room(hub: Path, rid: str, like: str, steps: list[str] | None = None, title: str | None = None,
             plain: bool = False) -> list[Path]:
    rid = _name(rid)
    d = definition(hub)
    rooms = {r["id"]: r for r in d["rooms"]}
    if rid in rooms:
        raise NewError(f"there is already a room '{rid}'")
    if like not in rooms:
        raise NewError(f"no room '{like}' to copy")
    steps = [s for s in (steps or []) if s]
    for s in steps:
        if s not in d["steps"]:
            raise NewError(f"no step '{s}'")
    out = []
    d["rooms"].append({"id": rid, "label": _title(rid), "title": title or "The " + _title(rid)})
    for s in steps:
        d["steps"][s]["room"] = rid
    return out + define.write(hub, d, {"rooms", "steps"} if steps else {"rooms"})


# ── role, check, type, rule ──────────────────────────────────────────────────────────────────────
def new_role(hub: Path, name: str, like: str, label: str | None = None) -> list[Path]:
    name = _name(name)
    d = hub / "agent-roles"
    if not (d / f"{like}.yaml").is_file():
        raise NewError(f"no role '{like}' to copy (agent-roles/{like}.yaml)")
    if (d / f"{name}.yaml").exists():
        raise NewError(f"agent-roles/{name}.yaml already exists")
    _write(d / f"{name}.yaml", f"name: {name}\nlabel: {label or _title(name)}\nlike: {like}             # tools, model key and "
                               f"codex settings are {like}'s unless set here\ndescription: \"A variant of {like} — say here what it does.\"\n")
    _write(d / f"{name}.md", _read(d / f"{like}.md"))
    import role_sync  # noqa: PLC0415
    old, role_sync.HUB = role_sync.HUB, hub
    try:
        role_sync.render()
    finally:
        role_sync.HUB = old
    return [d / f"{name}.yaml", d / f"{name}.md"]


def new_check(hub: Path, name: str, like: str) -> list[Path]:
    name = _name(name)
    src = next((d / f"{like.replace('-', '_')}.py" for d in (hub / "checks", HUB / "checks")
                if (d / f"{like.replace('-', '_')}.py").is_file()), None)
    if not src:
        raise NewError(f"no check '{like}' to copy (checks/{like.replace('-', '_')}.py)")
    dst = hub / "checks" / f"{name.replace('-', '_')}.py"
    if dst.exists():
        raise NewError(f"checks/{dst.name} already exists")
    text = re.sub(r'^NAME = "[^"]*"', f'NAME = "{name}"', _read(src), count=1, flags=re.M)
    _write(dst, text.replace(f"guard.py {like}", f"guard.py {name}"))
    return [dst]


def new_type(hub: Path, name: str, like: str) -> list[Path]:
    name = _name(name)
    import labfiles  # noqa: PLC0415
    src = labfiles.template(hub, f"project-types/{like}")
    if not (src / "TYPE.md").is_file():
        raise NewError(f"no project type '{like}' to copy")
    if name in labfiles.project_types(hub):
        raise NewError(f"there is already a project type '{name}'")
    dst = hub / "lab" / "templates" / "project-types" / name
    shutil.copytree(src, dst)
    card = dst / "TYPE.md"
    text = re.sub(r"\A# Project type: `[^`]*`( \(default\))?", f"# Project type: `{name}`", _read(card), count=1)
    _write(card, text)
    return [card]


def new_rule(hub: Path, rid: str, text: str, which: str = "hard", check: str | None = None) -> list[Path]:
    rid = _name(rid)
    p = hub / "workflow" / "rules.yaml"
    body = _read(p)
    key = f"{which}_rules"
    if any(r.get("id") == rid for g in rules.GROUPS for r in (rules.load(hub).get(g) or [])):
        raise NewError(f"there is already a rule '{rid}'")
    if not (text or "").strip():
        raise NewError("say what the rule is (--text)")
    start = re.search(rf"^{key}:", body, re.M)
    if not start:
        raise NewError(f"workflow/rules.yaml has no {key}: list")
    nxt = re.search(r"^\S", body[start.end():], re.M)
    end = start.end() + (nxt.start() if nxt else len(body) - start.end())
    while body[end - 1:end] == "\n" and body[end - 2:end] == "\n\n":
        end -= 1
    # a JSON string is a valid YAML scalar, and escapes everything that needs it
    entry = f"  - id: {rid}\n" + (f"    checks: [{check}]\n" if check else "") + f"    text: {json.dumps(text.strip(), ensure_ascii=False)}\n"
    _write(p, body[:end] + entry + body[end:])
    return [p]


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="kind", required=True)
    for kind in ("skill", "step", "workflow", "room", "role", "check", "type"):
        p = sub.add_parser(kind)
        p.add_argument("name")
        p.add_argument("--like", required=True, help=f"the {kind} to copy")
        if kind in ("skill", "workflow", "room"):
            p.add_argument("--title")
        if kind == "skill":
            p.add_argument("--step")
        if kind == "step":
            p.add_argument("--do")
            p.add_argument("--label")
            p.add_argument("--in", dest="workflow")
            p.add_argument("--after")
        if kind == "room":
            p.add_argument("--steps", default="")
            p.add_argument("--plain", action="store_true")
        if kind == "role":
            p.add_argument("--label")
    r = sub.add_parser("rule")
    r.add_argument("name")
    r.add_argument("--text", required=True)
    r.add_argument("--list", default="hard", choices=["hard", "subagent", "project"])
    r.add_argument("--check")
    a = ap.parse_args(argv)
    try:
        if a.kind == "skill":
            files = new_skill(HUB, a.name, a.like, a.step, a.title)
        elif a.kind == "step":
            files = new_step(HUB, a.name, a.like, a.do, a.label, a.workflow, a.after)
        elif a.kind == "workflow":
            files = new_workflow(HUB, a.name, a.like, a.title)
        elif a.kind == "room":
            files = new_room(HUB, a.name, a.like, [s.strip() for s in a.steps.split(",")], a.title, a.plain)
        elif a.kind == "role":
            files = new_role(HUB, a.name, a.like, a.label)
        elif a.kind == "check":
            files = new_check(HUB, a.name, a.like)
        elif a.kind == "type":
            files = new_type(HUB, a.name, a.like)
        else:
            files = new_rule(HUB, a.name, a.text, a.list, a.check)
    except NewError as e:
        print(f"[new] {e}", file=sys.stderr)
        return 2
    import lab_docs  # noqa: PLC0415
    lab_docs.render(HUB)
    for f in files:
        print(f"[new] wrote {f.relative_to(HUB).as_posix() if f.is_relative_to(HUB) else f}")
    probs = model.check(HUB, rules.check_names(HUB)) + rules.check(HUB)
    for x in probs:
        print(f"[new] check: {x}")
    return 1 if probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
