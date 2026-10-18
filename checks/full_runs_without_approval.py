"""guard.py full-runs-without-approval — Full-scale runs started before their checkpoint was approved.

A check for tools/guard.py: `uv run --with pyyaml python tools/guard.py full-runs-without-approval <slug>
[--checkpoint approve-full-runs]`. It is a watch of the research workflow's "Approve full runs"
checkpoint: the checkpoint itself is an approval the agent stops for, and this finds work done past it — every
run in the project's runs/*/meta.json whose stage is FULL and that started before the checkpoint was approved
(or while it isn't). Read-only. 0 = none · 1 = found (listed)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

NAME = "full-runs-without-approval"


def add_args(p) -> None:
    p.add_argument("slug")
    p.add_argument("--checkpoint", default="approve-full-runs")


def offending(hub: Path, slug: str, pdir: Path | None, checkpoint: str = "approve-full-runs") -> list[dict]:
    """[{run_id, started}] for FULL runs that started without (before) the approval."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from kernel import journal  # noqa: PLC0415
    ok_since = None
    for r in journal.approvals(hub, slug, checkpoint):
        if r.get("decision") == "approved":
            ok_since = ok_since or r.get("ts")
        else:
            ok_since = None
    out = []
    for meta in sorted((pdir / "runs").glob("*/meta.json")) if pdir and (pdir / "runs").is_dir() else []:
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str(m.get("stage") or "").upper() != "FULL":
            continue
        started = str(m.get("started") or "")
        if ok_since is None or (started and started < ok_since):
            out.append({"run_id": m.get("run_id") or meta.parent.name, "started": started})
    return out


def run(a, g) -> int:
    pdir = g._project_dir(a.slug)
    bad = offending(g.HUB, a.slug, pdir, a.checkpoint)
    if not bad:
        return g._verdict(0, f"no full-scale run of {a.slug} started before its approval")
    for b in bad[:20]:
        print(f"  - {b['run_id']} (started {b['started'] or '?'})")
    return g._verdict(1, f"{len(bad)} full-scale run(s) of {a.slug} started without the '{a.checkpoint}' approval")
