"""Signature guard — in a headless run, the PI's records and the lab's definition are the PI's.

A PreToolUse hook the executor installs in every launched run (claude: the run's sidecar settings; codex:
`-c hooks.PreToolUse` session flags; opencode: a plugin loaded through OPENCODE_CONFIG_DIR). It reads one
Claude-shaped hook payload on stdin and DENIES (exit 2, the reason on stderr) a tool call that writes:

  * the PI's records — the journal (moves and approvals), the registry written from it, check results,
    campaign state, the PI-action log, the Compose draft — written only by the kernel and the dashboard
  * the lab's definition — workflow/ (steps, workflows, rules), the skills, the agent roles, the checks and
    the extensions always; plus every path in rules.yaml `protected_paths` (the manuals, templates, the PI's instructions,
    rooms, panels)
  * the lab's settings (lab/config.yaml), except in the procedures whose job is changing them with the PI
  * or runs the PI's verbs (`arlo approve|revoke|changes|approve-collector`, tools/new.py)
  * and, in a run of a procedure that declares `writes:` (globs, e.g. the designers' lab/.bus/designs/**),
    anything outside those globs (and the system's temp folder) — through its edit tools or a shell redirect

One list drives both the file check and the shell check. It is a speed bump, not a vault: an agent can run
code, so the kernel refuses the PI's actions inside a run on its own, and anything that slips past shows on
the run's digest and as a flag. If the guard itself fails, it ALLOWS the call and raises a flag — a broken
guard must never wedge a lab. Denials are logged to the run's permissions.jsonl. Interactive sessions never
load this (the PI is present).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HUB = Path(os.environ.get("ARLOTOPE_HUB") or HERE.parent).resolve()
sys.path.insert(0, str(HERE))

# the floor no rules.yaml can lower: the kernel's records, and the core of the definition (workflow/ holds
# rules.yaml itself; skills, roles and checks are what every agent runs under)
FLOOR = [
    (r"^lab/journal\.jsonl$", "the journal is the kernel's — studies move with `arlo move`, approvals are the PI's"),
    (r"^lab/REGISTRY\.md$", "the registry is written from the journal — `arlo move` moves a study"),
    (r"^lab/approvals\.jsonl", "approvals are the PI's"),
    (r"^lab/\.bus/(checks|campaigns|compose)/", "the dashboard's and the keeper's records are not a run's to change"),
    (r"^lab/\.bus/(limits\.json|pi-actions\.jsonl)$", "the executor's and the PI's records are not a run's to change"),
    (r"^lab/\.bus/panels/approved\.json$", "which panel collectors may run is the PI's decision"),
    (r"^lab/\.bus/artifacts/[^/]+/(reply\.json|seen)$", "the PI's replies are the PI's"),
    (r"^workflow/", "the lab's definition is the PI's — suggest a change (`arlo propose`) or ask a designer"),
    (r"^\.claude/(skills|agents)/", "the lab's procedures and roles are the PI's — suggest a change with `arlo propose`"),
    (r"^\.(codex|opencode)/agents/", "the lab's roles are the PI's — suggest a change with `arlo propose`"),
    (r"^agent-roles/", "the lab's roles are the PI's — suggest a change with `arlo propose`"),
    (r"^checks/", "the lab's checks are the PI's — a run can't add or change what checks it"),
    (r"^extensions/", "the lab's extensions are the PI's to add — suggest a change with `arlo propose` instead"),
    (r"^tools/(signature_guard\.py|executor/opencode_guard\.js)$", "the guard is the PI's — a run can't switch it off"),
]
DEFINITION = "the lab's procedures, rules, roles, templates and the PI's instructions are the PI's — suggest a change with `arlo propose`"
CONFIG = r"^lab/config\.yaml$"
VERBS = re.compile(r"\barlo(?:\.(?:py|cmd)[\"']?|\b)(?:\s+--?[\w-]+(?:[ =][^\s|;&]+)?)*\s+(?:approve|revoke|changes|approve-collector|ack|hold|release|pause)(?=\s|$|[|;&])"
                   r"|(?:^|[\s/\\\"'])new\.py\b|--skip-guard\b")
WRITE_HINT = re.compile(r"(?<![0-9&])>(?!&)|\btee\b|sed\s+-i|perl\s+-\w*i|Set-Content|Add-Content|Out-File|"
                        r"\.write\(|write_text|write_bytes|open\([^)]*['\"][wa+]|\bcp\s|\bmv\s|\brm\s|\bln\s|"
                        r"Copy-Item|Move-Item|Remove-Item|New-Item|yaml\.(safe_)?dump|git\s+(checkout|restore)\b", re.I)
REDIRECT_NOISE = re.compile(r"\d?>\s*&\s*\d|\d?>\s*/dev/null|\d?>\s*\$null|\d?>\s*nul\b|->|=>|>=", re.I)
EDIT_TOOLS = {"edit", "multiedit", "write", "notebookedit", "create", "patch", "apply_patch", "str_replace",
              "str_replace_based_edit_tool"}
SHELL_TOOLS = {"bash", "shell", "exec_command", "local_shell", "powershell"}
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)


def protected() -> list[tuple[str, str]]:
    """(hub-relative regex, why): the floor, then the lab's rules.yaml `protected_paths`."""
    try:
        from kernel import rules  # noqa: PLC0415
        extra = [str(p) for p in (rules.load(HUB).get("protected_paths") or []) if isinstance(p, str)]
    except Exception:  # noqa: BLE001 — unreadable rules: the floor still holds
        extra = []
    return FLOOR + [(p, DEFINITION) for p in extra]


def _config_run() -> bool:
    """A run of a procedure whose job is changing the lab's settings with the PI (rules.yaml config_procedures)."""
    try:
        from kernel import rules  # noqa: PLC0415
        allowed = rules.load(HUB).get("config_procedures") or ["setup-lab", "configure"]
    except Exception:  # noqa: BLE001
        allowed = ["setup-lab", "configure"]
    return os.environ.get("ARLOTOPE_RUN_SKILL") in allowed


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


REDIRECT_TARGET = re.compile(r"(?<![0-9&-])>>?\s*([^\s|;&<>]+)|\btee\s+(?:-a\s+)?([^\s|;&<>]+)"
                             r"|\b(?:Out-File|Set-Content|Add-Content)\s+(?:-(?:File)?Path\s+)?([^\s|;&<>]+)", re.I)


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(HUB).as_posix()
    except ValueError:
        return p.as_posix()


def check_path(path: Path) -> str | None:
    """Why a run may not write this file, or None."""
    rel = _rel(path)
    if re.search(CONFIG, rel):
        return None if _config_run() else "the lab's settings are the PI's — they change them in Settings (or ask for it in /configure)"
    for rx, why in protected():
        if re.search(rx, rel):
            return why
    return _confined(path)


def _in_command(rx: str, cmd: str) -> bool:
    """A hub-relative path pattern, found as a path in a shell command: at a word start, after ./, or under the
    hub's own path (so a project's own `templates/` is not the hub's)."""
    body = rx[1:] if rx.startswith("^") else rx
    body = body[:-1] if body.endswith("$") else body
    hub = re.escape(HUB.as_posix())
    return re.search(rf"(?:^|[\s'\"=(]|\./|{hub}/){body}", cmd, re.I) is not None


def check_shell(cmd: str, cwd: str = "") -> str | None:
    if VERBS.search(cmd):
        return "the PI's verbs (approving, changing the lab's definition) are the PI's — ask instead"
    norm = REDIRECT_NOISE.sub(" ", cmd.replace("\\", "/"))
    if not WRITE_HINT.search(norm):
        return None
    if _in_command(CONFIG, norm) and not _config_run():
        return "the lab's settings are the PI's — they change them in Settings (or ask for it in /configure)"
    for rx, why in protected():
        if _in_command(rx, norm):
            return "this command writes something only the PI changes — " + why
    if _writes():
        for m in REDIRECT_TARGET.finditer(norm):
            target = next(g for g in m.groups() if g).strip("'\"")
            why = _confined(_abs(target, cwd))
            if why:
                return f"{target}: {why}"
    return None


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
        return check_shell(" ".join(map(str, cmd)) if isinstance(cmd, list) else str(cmd or ""), cwd)
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
    try:
        with (Path(rd) / "permissions.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tool": tool, "decision": decision,
                                "by": "signature-guard", "summary": why[:300]}) + "\n")
    except OSError:
        pass


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
