"""The lab's rules — workflow/rules.yaml: the rules agents follow (rendered into their manuals), the named
audits a checkpoint can run, the config keys only the PI changes, the rigor floors no profile may lower, and
the paths an agent may never write (RECORDS, and the lab's definition: DEFINITION + `protected_paths`)."""

from __future__ import annotations

import fnmatch
from pathlib import Path

import yaml

from .model import CODE, hub_of

REL = Path("workflow") / "rules.yaml"
GROUPS = ("hard_rules", "subagent_rules", "project_rules")
_cache: dict[str, tuple[int, dict]] = {}


def path(hub=None) -> Path:
    h = hub_of(hub)
    return h / REL if (h / REL).is_file() else CODE / REL


def load(hub=None) -> dict:
    """rules.yaml as a dict ({} when absent). Raises a yaml error on a malformed file."""
    p = path(hub)
    if not p.is_file():
        return {}
    mt = p.stat().st_mtime_ns
    hit = _cache.get(str(p))
    if hit and hit[0] == mt:
        return hit[1]
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    _cache[str(p)] = (mt, data)
    return data


def audits(hub=None) -> list[dict]:
    """The named audits checkpoints can run (`audits:`; `gate3_audits:` in an older lab)."""
    rl = load(hub)
    return [a for a in (rl.get("audits") or rl.get("gate3_audits") or []) if isinstance(a, dict) and a.get("name")]


def check_roots(hub=None) -> list[Path]:
    """Where checks live: the lab's own checks/ and this code's (the lab's first)."""
    return [d for d in dict.fromkeys([hub_of(hub) / "checks", CODE / "checks"]) if d.is_dir()]


def check_names(hub=None) -> set[str]:
    """Every name a checkpoint may list: a checks/<name>.py (dashes or underscores) or a named audit."""
    names = {a["name"] for a in audits(hub)}
    for d in check_roots(hub):
        for f in d.glob("*.py"):
            if not f.name.startswith("_"):
                names |= {f.stem, f.stem.replace("_", "-")}
    return names


# What a run may never write, whatever rules.yaml says: (hub-relative regex, why). The PI's and the kernel's
# records change while a run works (the kernel and the dashboard write them); the lab's definition does not, so
# besides the signature guard refusing an edit, each attempt's supervisor compares its files before and after.
RECORDS = [
    (r"^lab/journal\.jsonl$", "the journal is the kernel's — studies move with `arlo move`, approvals are the PI's"),
    (r"^lab/REGISTRY\.md$", "the registry is written from the journal — `arlo move` moves a study"),
    (r"^lab/approvals\.jsonl", "approvals are the PI's"),
    (r"^lab/\.bus/(checks|campaigns|compose)/", "the dashboard's and the keeper's records are not a run's to change"),
    (r"^lab/\.bus/(limits\.json|pi-actions\.jsonl)$", "the executor's and the PI's records are not a run's to change"),
    (r"^lab/\.bus/panels/approved\.json$", "which panel collectors may run is the PI's decision"),
    (r"^lab/\.bus/artifacts/[^/]+/(reply\.json|seen)$", "the PI's replies are the PI's"),
]
PROPOSE = "suggest a change with `arlo propose`"
DEFINITION = [
    (r"^workflow/", "the lab's definition is the PI's — suggest a change (`arlo propose`) or ask a designer"),
    (r"^\.claude/skills/", "the lab's procedures are the PI's — " + PROPOSE),
    (r"^\.claude/agents/", "the lab's roles are the PI's — " + PROPOSE),
    (r"^\.codex/agents/", "the lab's roles are the PI's — " + PROPOSE),
    (r"^\.opencode/agents/", "the lab's roles are the PI's — " + PROPOSE),
    (r"^agent-roles/", "the lab's roles are the PI's — " + PROPOSE),
    (r"^checks/", "the lab's checks are the PI's — a run can't add or change what checks it"),
    (r"^extensions/", "the lab's extensions are the PI's to add — " + PROPOSE + " instead"),
    (r"^tools/signature_guard\.py$", "the guard is the PI's — a run can't switch it off"),
    (r"^tools/executor/opencode_guard\.js$", "the guard is the PI's — a run can't switch it off"),
]
PROTECTED = "the lab's procedures, rules, roles, templates and the PI's instructions are the PI's — " + PROPOSE
CONFIG = r"^lab/config\.yaml$"
RENDERED = (r"^\.claude/agents/", r"^\.codex/agents/", r"^\.opencode/agents/")   # role files role_sync renders from it


def definition(hub=None) -> list[tuple[str, str]]:
    """(regex, why) of the lab's definition: the floor no rules.yaml can lower, then its `protected_paths`."""
    try:
        extra = [str(p) for p in (load(hub).get("protected_paths") or []) if isinstance(p, str)]
    except Exception:  # noqa: BLE001 — unreadable rules: the floor still holds
        extra = []
    return DEFINITION + [(p, PROTECTED) for p in extra]


def config_procedures(hub=None) -> list[str]:
    """The procedures whose job is changing the lab's settings with the PI (`config_procedures`)."""
    try:
        return [str(x) for x in load(hub).get("config_procedures") or ["setup-lab", "configure"]]
    except Exception:  # noqa: BLE001
        return ["setup-lab", "configure"]


def pi_owned(key: str, hub=None) -> bool:
    """A config key only the PI changes (`pi_owned_config`): an entry covers that key and everything under it
    (`agents` → `agents.tiers.strong`); `*` is a wildcard (`loop.explore_*`)."""
    return any(key == k or key.startswith(k + ".") or fnmatch.fnmatchcase(key, k)
               for k in (str(x) for x in load(hub).get("pi_owned_config") or []))


def rigor_violations(flat: dict, hub=None) -> list[str]:
    """Why these {dotted.key: value} settings would lower a rigor floor (`rigor_floors`)."""
    out = []
    for key, value in flat.items():
        f = (load(hub).get("rigor_floors") or {}).get(key)
        if not isinstance(f, dict):
            continue
        why = f.get("why", "a rigor floor")
        if "min" in f:
            try:
                if float(value) < float(f["min"]):
                    out.append(f"{key}={value} < {f['min']} ({why})")
            except (TypeError, ValueError):
                out.append(f"{key}={value!r} is not a number ({why})")
        if "never" in f and (value == f["never"] or str(value).lower() == str(f["never"]).lower()):
            out.append(f"{key}={value} ({why})")
    return out


def check(hub=None) -> list[str]:
    """Problems with rules.yaml: every rule has an id and text, ids are unique, every check a rule names exists,
    every audit's script exists."""
    try:
        rl = load(hub)
    except (OSError, yaml.YAMLError) as e:
        return [f"{REL.as_posix()}: {e}"]
    probs, seen = [], set()
    have = check_names(hub)
    for group in GROUPS:
        for r in rl.get(group) or []:
            rid = (r or {}).get("id")
            if not rid or not str((r or {}).get("text") or "").strip():
                probs.append(f"rules.yaml {group}: every rule needs an id and text ({rid or r!r})")
                continue
            if rid in seen:
                probs.append(f"rules.yaml: duplicate rule id {rid}")
            seen.add(rid)
            for c in r.get("checks") or []:
                if c not in have:
                    probs.append(f"rules.yaml {rid}: unknown check {c!r} (no checks/{c}.py)")
    for a in audits(hub):
        script = ((a or {}).get("run") or [None])[0]
        if not script or not any((d / script).is_file() for d in check_roots(hub)):
            probs.append(f"rules.yaml audits: no checks/{script}")
    wids = set()
    for w in rl.get("watch") or []:
        wid = (w or {}).get("id") if isinstance(w, dict) else None
        if not wid:
            probs.append(f"rules.yaml watch: every watch needs an id ({w!r})")
            continue
        if wid in wids:
            probs.append(f"rules.yaml watch: duplicate id {wid}")
        wids.add(wid)
        if not any(w.get(k) for k in ("writes", "deletes", "runs", "denials", "check")):
            probs.append(f"rules.yaml watch {wid}: say what it watches (writes, deletes, runs, denials or check)")
        if w.get("level", "warn") not in ("info", "warn", "block"):
            probs.append(f"rules.yaml watch {wid}: level must be info, warn or block")
        if w.get("check"):
            from .model import check_spec  # noqa: PLC0415
            name = check_spec(w["check"])[0]
            if name not in have:
                probs.append(f"rules.yaml watch {wid}: unknown check {name!r}")
    return probs
