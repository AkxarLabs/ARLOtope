"""Project → hub write-back, atomically. Run from a PROJECT session at session-end.

    uv run --with pyyaml python <hub>/tools/hub_writeback.py --slug <slug> \
        [--notebook "..."] [--finding "..."] [--failure "..."] [--question "..."] \
        [--outcome <outcome>] [--evidence "..."]

The normal write-back path (hard rule 11) as one safe call: appends a dated `lab/notebook/`
entry, promotes durable insights to `lab/knowledge/{FINDINGS,FAILURES,OPEN-QUESTIONS}.md`, and
(with `--outcome`) reports the study's outcome to the kernel, which moves it as its workflow says
(`arlo move`). The hub is found from this script's own location. Appends are single-write (atomic for
small blocks). If you CANNOT run this tool (hub unreachable), append a `HUB-WRITEBACK-PENDING:`
block to the project's `EXPERIMENT_LOG.md` instead (see the project CLAUDE.md) — a hub session
reconciles it via `tools/process_writebacks.py --apply`.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/
from kernel import studies  # noqa: E402 — the only way a study moves

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HUB = Path(__file__).resolve().parents[1]
LAB = HUB / "lab"


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _append(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:        # single write — atomic for small blocks
        f.write(text)


def _promote(name: str, slug: str, text: str, evidence: str) -> None:
    ev = f" (evidence: {evidence})" if evidence else ""
    _append(LAB / "knowledge" / name, f"\n- [{_today()}] ({slug}) {text}{ev}\n")


def _notebook(slug: str, text: str, evidence: str) -> str:
    nb = LAB / "notebook" / f"{_today()}-{slug}.md"
    if not nb.exists():
        _append(nb, f"# Notebook — {slug} — {_today()}\n")
    block = f"\n## {time.strftime('%H:%M')} — {slug}\n\n{text}\n"
    if evidence:
        block += f"\n_evidence: {evidence}_\n"
    _append(nb, block)
    return str(nb.relative_to(HUB))


def _report(slug: str, outcome: str, note: str) -> str:
    """Report the study's outcome to the kernel (`arlo move`): its workflow says where it goes."""
    try:
        res = studies.move(HUB, slug, outcome, note=note)
    except studies.StudyError as e:
        return str(e)
    if res.get("moved"):
        return f"ok: → {res['step']}"
    if res.get("finished"):
        return "ok: finished"
    return "ok: it waits for the PI"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--notebook")
    ap.add_argument("--finding")
    ap.add_argument("--failure")
    ap.add_argument("--question")
    ap.add_argument("--outcome")
    ap.add_argument("--evidence")
    args = ap.parse_args()

    if not LAB.exists():
        print("[hub_writeback] hub lab/ not found — append a HUB-WRITEBACK-PENDING block to "
              "EXPERIMENT_LOG.md instead", file=sys.stderr)
        return 1

    did = []
    if args.notebook:
        did.append("notebook:" + _notebook(args.slug, args.notebook, args.evidence or ""))
    if args.finding:
        _promote("FINDINGS.md", args.slug, args.finding, args.evidence or "")
        did.append("finding")
    if args.failure:
        _promote("FAILURES.md", args.slug, args.failure, args.evidence or "")
        did.append("failure")
    if args.question:
        _promote("OPEN-QUESTIONS.md", args.slug, args.question, args.evidence or "")
        did.append("question")
    refused = False
    if args.outcome:
        r = _report(args.slug, args.outcome, args.notebook or "")
        did.append(f"outcome {args.outcome}: {r}")
        refused = not r.startswith("ok")               # a refused outcome must be visible

    if not did:
        print("[hub_writeback] nothing to write — give "
              "--notebook/--finding/--failure/--question/--outcome")
        return 1
    print("hub write-back done: " + ", ".join(did))
    # Non-zero when the outcome was refused, so an exit-code-driven caller never mistakes a study that
    # stayed put for one that moved.
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
