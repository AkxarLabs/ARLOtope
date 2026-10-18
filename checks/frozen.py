"""guard.py frozen — The frozen evaluation stays frozen: control.yaml says so and keeps the PI-owned blocks.

A check for tools/guard.py: `uv run --with pyyaml python tools/guard.py frozen <study>`. A project's
control.yaml must keep `eval_frozen: true` and its `budgets` and `seeds` blocks (the PI sets them at the
proposal; an agent never unfreezes the evaluation). Read-only. 0 = intact · 1 = broken (listed)."""

from __future__ import annotations

NAME = "frozen"


def add_args(p) -> None:
    p.add_argument("slug")


def run(a, g) -> int:
    pdir = g._project_dir(a.slug)
    if not pdir:
        return g._verdict(1, f"no project dir for {a.slug}")
    ctl = g.labfiles.load_yaml(pdir / "control.yaml")
    problems = []
    if ctl.get("eval_frozen") is not True:
        problems.append("eval_frozen is not true — the eval/test protocol must never be unfrozen by the agent")
    for block in ("budgets", "seeds"):
        if block not in ctl:
            problems.append(f"PI-owned block '{block}' missing from control.yaml")
    if problems:
        for p in problems:
            print(f"  - {p}")
        return g._verdict(1, f"frozen-set integrity FAILED for {a.slug}")
    return g._verdict(0, f"frozen set intact for {a.slug} (eval_frozen + budgets/seeds present)")
