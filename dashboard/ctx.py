"""The dashboard's shared state: which lab it serves (or the remote lab it proxies), and the few helpers
every module needs. Every dashboard module imports this; it imports none of them — serve.py wires the
server, and nothing reaches back into it.

    HUB, LAB          the lab this dashboard shows (switch_hub re-points it, live)
    REMOTE            a machines.Conn when the lab is on another machine (set_remote)
    on_change(fn)     fn(old_hub, new_hub) after a switch / a remote change (caches clear themselves)
    KICK              wakes the scheduler thread (a run was queued, answered, …)
    pi_log / emit_hub the PI's audit trail and the hub's bus
    safe_id / slug    a client-supplied id for writing (strict) / reading (cleaned)
    pdir              a registered idea's project dir
    tool(name)        a lab tool module from tools/ (markers, workflow, profiles, …)
    config() / ts()   the shown lab's config.yaml / a timestamp in the lab's format
"""

from __future__ import annotations

import importlib
import re
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # the code this dashboard runs (the template for new labs)
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import labfiles  # noqa: E402 — the lab's files and the shared readers (tools/labfiles.py)
HUB = ROOT
LAB = HUB / "lab"
REMOTE = None
SERVER = None   # the running HTTP server (serve.main sets it; labs.server_stop shuts it down)
KICK = threading.Event()
_listeners: list = []


def on_change(fn) -> None:
    _listeners.append(fn)


def _changed(old) -> None:
    for fn in _listeners:
        try:
            fn(old, HUB)
        except Exception:  # noqa: BLE001 — a cache that can't clear must not block a switch
            pass
    KICK.set()


def switch_hub(hub) -> None:
    """Re-point the dashboard at another lab, live (the lab picker). Runs are detached supervisors, so
    nothing running is touched."""
    global HUB, LAB
    old = HUB
    HUB = Path(hub).resolve()
    LAB = HUB / "lab"
    _changed(old)


def set_remote(conn) -> None:
    global REMOTE
    REMOTE = conn
    _changed(HUB)


# Every WRITE path builds a filesystem path from a client-supplied idea/target, so the id must be a bare
# registry-style slug — no separators, no leading dot, no '..'.
safe_id = labfiles.safe_id


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def slug(s) -> str:
    """A read-side slug: unsafe characters stripped, and never a path step (`..`, a leading dot)."""
    s = _UNSAFE.sub("", (s or "").strip() if isinstance(s, str) else "")[:80]
    return "" if (".." in s or s.startswith(".")) else s


def pdir(slug: str | None) -> Path | None:
    """A registered idea's project dir — the registry's Project column first (an /adopt-ed repo can live
    anywhere), then projects_root/<slug>. Only an existing directory counts."""
    if not slug:
        return None
    import sources  # noqa: PLC0415 — sources imports ctx
    row = next((r for r in sources.parse_registry() if r.get("id") == slug), None) or {"id": slug, "project": ""}
    p = sources._project_path(row)
    return p if (p and p.is_dir()) else None


def pi_log(rec: dict) -> None:
    """Append-only audit trail of PI actions taken through the dashboard. `default=str` keeps it robust
    to YAML-parsed values (e.g. an `expires:` date) that aren't natively JSON-serializable."""
    labfiles.append_jsonl(LAB / ".bus" / "pi-actions.jsonl", {**rec, "ts": ts()})


def emit_hub(kind: str, **fields) -> None:
    labfiles.append_jsonl(LAB / ".bus" / "events.jsonl", {"ts": ts(), "source": "hub", "kind": kind, **fields})


def no_executor() -> tuple[dict, int]:
    return {"error": "the executor (tools/executor) is not available in this checkout"}, 503


def tool(name: str):
    """A module from the lab's tools/ (markers, workflow, profiles, …), importable whatever sys.path
    currently holds."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    return importlib.import_module(name)


ts = labfiles.now


def config() -> dict:
    """The shown lab's settings (labfiles.config)."""
    return labfiles.config(HUB)


def set_config(changes: dict) -> str | None:
    """Change the shown lab's settings (labfiles.set_config): None, or what went wrong."""
    return labfiles.set_config(HUB, changes)


def config_problems() -> list[str]:
    return labfiles.config_problems(HUB)


def read(p: Path) -> str | None:
    """A text file as written (newlines kept), or None."""
    try:
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            return f.read()
    except OSError:
        return None


def write_keep_eol(p: Path, original: str, text: str) -> None:
    """Write `text` with the line endings `original` used."""
    eol = "\r\n" if "\r\n" in original else "\n"
    labfiles.write_atomic(p, text.replace("\r\n", "\n").replace("\n", eol))


def row(slug: str) -> dict | None:
    """The idea's registry row."""
    import sources  # noqa: PLC0415
    return next((r for r in sources.parse_registry() if r.get("id") == slug), None)


def need_slug(body: dict, key: str = "idea") -> str | None:
    return safe_id(body.get(key) or "")
