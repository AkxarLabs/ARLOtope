"""Lint lab state: studies vs their folders, orphan dirs, stale studies, the definition.

    uv run --with pyyaml python tools/check_lab.py [--stale-days N] [--strict]

Checks:
  1. Every studies/<slug>/ has an IDEA.md and is a study in the journal (lab/journal.jsonl).
  2. Orphans: studies/<slug>/ or <projects_root>/<slug> that is no study, and studies with no folder.
     (The paper lives at studies/<slug>/paper/ — nested under the study, so it needs no separate check.)
  3. Stale: studies that are still going but haven't moved in --stale-days (default lab/config.yaml
     lab.stale_days, else 14). The definition is consistent and every study stands on one of its steps.
  4. Executor (headless runs): a configured backend CLI that can't be found; dashboard
     runs stuck "live"
     past 2x their max_minutes (orphans — `executor_cli.py reconcile`); runs waiting days for an answer.

Exit 1 on mismatches/orphans (always) or stale items (with --strict); else 0.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HUB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import labfiles  # noqa: E402 — the lab's files, read one way
from kernel import model, rules, studies  # noqa: E402


def slug_dirs(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {d.name for d in root.iterdir() if d.is_dir()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stale-days", type=int, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config = labfiles.config(HUB)
    lab_cfg = config.get("lab") or {}
    stale_days = args.stale_days if args.stale_days is not None else lab_cfg.get("stale_days", 14)
    projects_root = labfiles.projects_root(HUB)

    rows = {r["id"]: r for r in studies.rows(HUB)}
    problems, stale = [], []

    # 1. Each studies/<slug>/ is a study with an IDEA.md.
    study_dirs = slug_dirs(HUB / "studies")
    for slug in sorted(study_dirs):
        if not (HUB / "studies" / slug / "IDEA.md").exists():
            problems.append(f"studies/{slug}/ has no IDEA.md")
        elif slug not in rows:
            problems.append(f"studies/{slug}/ is not a study in the journal (newts new {slug} --title …)")

    # 2. Orphans. Worktree dirs (<slug>-wt-*) in the projects root are transient — skip them.
    #    A paper at studies/<slug>/paper/ needs no separate check — it's nested under the study,
    #    which is already orphan-checked above.
    for slug, row in rows.items():
        if slug not in study_dirs:
            problems.append(f"study '{slug}' has no studies/{slug}/ dir")
    for slug in sorted(slug_dirs(projects_root)):
        if slug not in rows and "-wt-" not in slug and not slug.endswith("-wt"):  # skip transient worktrees (matches trace_hook)
            problems.append(f"{projects_root.name}/{slug}/ belongs to no study")

    # 3. Staleness.
    today = date.today()
    for slug, row in rows.items():
        if row["finished"] or (model.step(row["state"], HUB) or {}).get("shelf"):
            continue
        try:
            updated = datetime.strptime(row["updated"], "%Y-%m-%d").date()
            if (today - updated).days > stale_days:
                stale.append(f"{slug}: not updated since {row['updated']} (> {stale_days}d), state {row['state']}")
        except ValueError:
            stale.append(f"{slug}: unparseable Updated date '{row['updated']}'")

    # 4. The definition (workflow/) is consistent; every study stands on one of its steps.
    problems.extend(model.check(HUB, rules.check_names(HUB)) + rules.check(HUB))
    known = set(model.steps(HUB))
    for slug, row in rows.items():
        if row["state"] not in known:
            problems.append(f"{slug}: it stands at '{row['state']}', which is not a step (newts move {slug} --to <step>)")

    # 5. Executor hygiene (review-level: configuration and orphans, never a hard inconsistency).
    stale.extend(executor_checks(config, rows, projects_root))

    print(f"## Lab check — {len(rows)} studies, {len(study_dirs)} study dirs\n")
    if problems:
        print("**Inconsistencies (fix now):**")
        for p in problems:
            print(f"- {p}")
    if stale:
        print("\n**Stale (review):**")
        for s in stale:
            print(f"- {s}")
    if not problems and not stale:
        print("All consistent.")

    if problems or (args.strict and stale):
        return 1
    return 0


def _tracing_stale(pdir: Path) -> bool:
    """A spawned project missing the current tracer plumbing (subagents then show up less completely)."""
    tmpl = HUB / "templates" / "project"
    for rel in ("scripts/trace_hook.py", ".opencode/plugins/newts-trace.js", ".codex/hooks.json"):
        want, have = tmpl / rel, pdir / rel
        try:
            if want.exists() and (not have.exists() or
                                  have.read_bytes().replace(b"\r\n", b"\n") != want.read_bytes().replace(b"\r\n", b"\n")):
                return True
        except OSError:
            return True
    return False


def executor_checks(config: dict, rows: dict, projects_root: Path) -> list[str]:
    out = []
    prog = ((config.get("agents") or {}).get("programmatic")) or {}
    dash = config.get("dashboard") or {}
    for name, b in (prog.get("backends") or {}).items():
        cmd = (b or {}).get("command") if isinstance(b, dict) else None
        if isinstance(cmd, str) and cmd.strip() and not (Path(cmd).expanduser().exists() or shutil.which(cmd)):
            out.append(f"agents.programmatic.backends.{name}.command = {cmd!r} was not found")
    try:
        max_min = float(prog.get("max_minutes") or 240)
    except (TypeError, ValueError):
        max_min = 240.0
    dirs = [HUB / "lab" / ".bus" / "agents"]
    for slug, row in rows.items():
        raw = (row.get("project") or "").strip().strip("`")
        pdir = (Path(raw) if Path(raw).is_absolute() else (HUB / raw).resolve()) if raw and raw not in ("-", "—") \
            else projects_root / slug
        dirs.append(pdir / ".bus" / "agents")
        if (pdir / "control.yaml").exists() and _tracing_stale(pdir):
            out.append(f"project {slug}: its subagent-tracing files predate the template (trace_hook / hooks / "
                       "opencode plugin) — run `tools/upgrade_project.py " + slug + "`")
    now = time.time()
    for d in dirs:
        for f in (sorted(d.glob("*.json")) if d.is_dir() else []):
            try:
                m = json.loads(f.read_text(encoding="utf-8-sig"))
                ts = time.mktime(time.strptime(str(m.get("status_ts") or m.get("started") or "")[:19], "%Y-%m-%dT%H:%M:%S"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            age_min = (now - ts) / 60
            rid = m.get("run_id") or m.get("agent_id") or f.stem
            if m.get("status") in ("starting", "running", "resuming") and age_min > 2 * float(m.get("max_minutes") or max_min):
                out.append(f"run {rid} has been '{m.get('status')}' for {age_min:.0f} min (> 2x max_minutes) — "
                           "orphaned? run `executor_cli.py reconcile`")
            elif m.get("status") == "waiting_input" and age_min > 3 * 24 * 60:
                out.append(f"run {rid} has waited {age_min / 1440:.0f} days for your answer (dashboard → Needs you)")
    return out


if __name__ == "__main__":
    sys.exit(main())
