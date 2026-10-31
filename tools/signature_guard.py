"""Signature guard — in a headless run, the PI's records and the lab's definition are the PI's.

A PreToolUse hook the executor installs in every launched run (claude: the run's sidecar settings; codex:
`-c hooks.PreToolUse` session flags; opencode: a plugin loaded through OPENCODE_CONFIG_DIR). It reads one
Claude-shaped hook payload on stdin and DENIES (exit 2, the reason on stderr):

  * an edit tool's write to the PI's records — the journal (moves and approvals), the registry written from it,
    check results, campaign state, the PI-action log, the Compose draft — written only by the kernel and the
    dashboard (kernel/rules.py RECORDS)
  * …or to the lab's definition — workflow/ (steps, workflows, rules), the skills, the agent roles, the checks
    and the extensions always; plus every path in rules.yaml `protected_paths` (the manuals, templates, the
    PI's instructions, rooms, panels) (kernel/rules.py DEFINITION)
  * …or to the lab's settings (lab/config.yaml), except in the procedures whose job is changing them with the PI
  * …or, in a run of a procedure that declares `writes:` (globs, e.g. the designers' lab/.bus/designs/**),
    anywhere outside those globs (and the system's temp folder)
  * a shell command that runs the PI's verbs (`arlo approve|revoke|changes|approve-collector`, tools/new.py)

It is an early warning, not the protection: an agent can run code, and no pattern sees every way code writes a
file. What holds is checked from the outside. An approval counts only when the kernel signed it outside a run
(kernel/journal.py), the kernel refuses the PI's actions inside a run, and each attempt's supervisor compares
what only the PI changes before and after (kernel/watch.py fingerprint) — a change holds the lab with a flag
until the PI has looked. If the guard itself fails, it ALLOWS the call and raises a flag — a broken guard must
never wedge a lab. Denials are logged to the run's permissions.jsonl. Interactive sessions never load this (the
PI is present).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HUB = Path(os.environ.get("ARLOTOPE_HUB") or HERE.parent).resolve()
sys.path.insert(0, str(HERE))
from labfiles import append_jsonl, now  # noqa: E402

VERBS = re.compile(r"\barlo(?:\.(?:py|cmd)[\"']?|\b)(?:\s+--?[\w-]+(?:[ =][^\s|;&]+)?)*\s+(?:approve|revoke|changes|approve-collector|ack|hold|release|pause)(?=\s|$|[|;&])"
                   r"|(?:^|[\s/\\\"'])new\.py\b|--skip-guard\b")
EDIT_TOOLS = {"edit", "multiedit", "write", "notebookedit", "create", "patch", "apply_patch", "str_replace",
              "str_replace_based_edit_tool"}
SHELL_TOOLS = {"bash", "shell", "exec_command", "local_shell", "powershell"}
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)


def _rules():
    from kernel import rules  # noqa: PLC0415 — only for a write: a shell call stays import-free and quick
    return rules


def protected() -> list[tuple[str, str]]:
    """(hub-relative regex, why): the records, then the lab's definition (with rules.yaml `protected_paths`)."""
    return _rules().RECORDS + _rules().definition(HUB)


def _config_run() -> bool:
    """A run of a procedure whose job is changing the lab's settings with the PI (rules.yaml config_procedures)."""
    return os.environ.get("ARLOTOPE_RUN_SKILL") in _rules().config_procedures(HUB)


def _writes() -> list[str]:
    """The globs this run's procedure confines its writes to (its `writes:`), or [] for no confinement."""
    skill = os.environ.get("ARLOTOPE_RUN_SKILL")
    if not skill:
        return []
    from kernel import model  # noqa: PLC0415
    return [str(x) for x in ((model.procedure(skill, HUB) or {}).get("writes") or [])]


def _confined(path: Path) -> str | None:
    """Why a confined run may not write this file (outside its procedure's `writes:`), or None."""
    pats = _writes()
    if not pats:
        return None
    rel = _rel(path)
    if any(fnmatch.fnmatchcase(rel, p) for p in pats):
        return None
    if Path(rel).is_absolute():                     # outside the lab: only the system's temp folder
        try:
            path.resolve().relative_to(Path(tempfile.gettempdir()).resolve())
            return None
        except ValueError:
            pass
    return f"a /{os.environ.get('ARLOTOPE_RUN_SKILL')} run writes only {', '.join(pats)}"


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(HUB).as_posix()
    except ValueError:
        return p.as_posix()


def check_path(path: Path) -> str | None:
    """Why a run may not write this file, or None."""
    rel = _rel(path)
    if re.search(_rules().CONFIG, rel):
        return None if _config_run() else "the lab's settings are the PI's — they change them in Settings (or ask for it in /configure)"
    for rx, why in protected():
        if re.search(rx, rel):
            return why
    return _confined(path)


def _abs(fp: str, cwd: str) -> Path:
    p = Path(fp)
    return (p if p.is_absolute() else Path(cwd or ".") / p).resolve()


def paths_of(tool: str, ti: dict, cwd: str):
    """Every file a tool call would write."""
    t = (tool or "").lower()
    if not isinstance(ti, dict):
        return
    if t in ("apply_patch", "patch"):
        text = str(ti.get("command") or ti.get("input") or ti.get("patch") or ti.get("patchText") or "")
        for fp in PATCH_FILE_RE.findall(text):
            yield _abs(fp.strip(), cwd)
        return
    fp = ti.get("file_path") or ti.get("filePath") or ti.get("path") or ti.get("notebook_path")
    if fp:
        yield _abs(str(fp), cwd)


def decide(payload: dict) -> str | None:
    """The deny reason for one PreToolUse payload, or None to allow."""
    tool = str(payload.get("tool_name") or payload.get("tool") or "")
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else (payload.get("args") or {})
    cwd = str(payload.get("cwd") or os.getcwd())
    t = tool.lower()
    if t in SHELL_TOOLS:
        cmd = ti.get("command") if isinstance(ti, dict) else ""
        cmd = " ".join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or "")
        if VERBS.search(cmd):
            return "the PI's verbs (approving, changing the lab's definition) are the PI's — ask instead"
    if t in EDIT_TOOLS:
        for path in paths_of(t, ti, cwd):
            why = check_path(path)
            if why:
                return f"{_rel(path)}: {why}"
    return None


def _log(decision: str, tool: str, why: str) -> None:
    rd = os.environ.get("ARLOTOPE_RUN_DIR")
    if not rd:
        return
    append_jsonl(Path(rd) / "permissions.jsonl", {"ts": now(), "tool": tool, "decision": decision,
                                                   "by": "signature-guard", "summary": why[:300]})


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    except (json.JSONDecodeError, OSError):
        return 0     # never block on a malformed payload
    if not isinstance(payload, dict) or (payload.get("hook_event_name") not in (None, "PreToolUse")):
        return 0
    tool = str(payload.get("tool_name") or "")
    try:
        why = decide(payload)
    except Exception as e:  # noqa: BLE001 — a guard bug must not wedge a run: allow, and say so loudly
        _log("error", tool, f"the guard failed ({type(e).__name__}: {e}) and allowed this call")
        try:
            from kernel import watch  # noqa: PLC0415
            watch.flag(HUB, "warn", f"the signature guard failed and allowed a {tool} call", source="guard",
                       run=os.environ.get("ARLOTOPE_RUN_ID"), detail=f"{type(e).__name__}: {e}"[:300])
        except Exception:  # noqa: BLE001
            pass
        return 0
    if not why:
        return 0
    _log("deny", tool, why)
    sys.stderr.write(f"Denied by the ARLOtope signature guard: {why}. Ask the PI instead; do not try another way "
                     "around it.\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
