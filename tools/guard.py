"""The lab's checks — one file each in checks/ (this code's, plus the lab's own) — run from one command.

    uv run --with pyyaml python tools/guard.py <check> <study> …      # e.g. append-only, writeback, frozen
    uv run --with pyyaml python tools/guard.py --list

A check is a module with NAME, add_args(parser) and run(args, guard) → exit code: 0 = OK · 1 = BLOCKED (do not
proceed) · 2 = WARNING. Checkpoints run them (`checks:`), watches run them, rules name them, and agents run
them where a procedure says so. They get this module as `guard`: HUB, LAB, labfiles, study(slug),
_row(slug), _project_dir(slug), _verdict(code, msg), _today().

Where a study stands and whether a checkpoint is approved is the kernel's (tools/kernel/, `arlotope status`,
`arlotope approved <study> <checkpoint>`), not a check.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# the lab being checked: $ARLOTOPE_HUB when a caller names it (a run, the checkpoint sheet), else this checkout
HUB = Path(os.environ.get("ARLOTOPE_HUB") or Path(__file__).resolve().parents[1]).resolve()
LAB = HUB / "lab"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import labfiles  # noqa: E402 — the lab's files, read one way
from kernel import checkpoints as _cps, studies as _studies  # noqa: E402


def study(slug: str) -> dict | None:
    return _studies.study(HUB, slug)


def _row(slug: str) -> dict | None:
    return labfiles.row(HUB, slug)


def _project_dir(slug: str, row: dict | None = None) -> Path | None:
    return _cps.project_dir(HUB, slug)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _verdict(code: int, msg: str) -> int:
    print(f"[guard] {({0: 'OK', 1: 'BLOCKED', 2: 'WARN'})[code]}: {msg}")
    return code


def _load_checks() -> dict:
    import importlib.util  # noqa: PLC0415
    out = {}
    roots = dict.fromkeys([Path(__file__).resolve().parents[1] / "checks", HUB / "checks"])
    for root in roots:
        for f in sorted(root.glob("*.py")) if root.is_dir() else []:
            if f.name.startswith("_"):
                continue
            spec = importlib.util.spec_from_file_location(f"arlotope_check_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception as e:  # noqa: BLE001 — a broken check is reported, never fatal to the others
                print(f"[guard] WARN: checks/{f.name} did not load: {e}", file=sys.stderr)
                continue
            if callable(getattr(mod, "run", None)) and callable(getattr(mod, "add_args", None)):
                out[getattr(mod, "NAME", f.stem.replace("_", "-"))] = mod
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    checks = _load_checks()
    if "--list" in argv:
        for name, mod in checks.items():
            print(f"{name:<28} {((mod.__doc__ or '').strip().splitlines() or [''])[0]}")
        return 0
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(description="run one of the lab's checks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, mod in checks.items():
        p = sub.add_parser(name, help=((mod.__doc__ or "").strip().splitlines() or [""])[0])
        mod.add_args(p)
        p.set_defaults(mod=mod)
    a = ap.parse_args(argv)
    return a.mod.run(a, sys.modules[__name__])


if __name__ == "__main__":
    sys.exit(main())
