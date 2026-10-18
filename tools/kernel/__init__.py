"""The kernel: the lab's definition, where its studies stand, and the only way they move.

    model         the definition — steps, workflows, rooms, procedures (workflow/, .claude/skills/)
    journal       the record — lab/journal.jsonl: moves, waits, approvals; every study's state is a fold of it
    studies       acting — file a study, report an outcome, the PI's moves; lab/REGISTRY.md is its view
    checkpoints   the PI's approvals at work — evidence, checks, decisions (approving moves a waiting study on)
    brief         what an agent is told for one procedure and study
    instructions  the PI's own added instructions, and agents' proposals for them
    rules         workflow/rules.yaml
    define        writing the definition back (Compose, designers, migration)
    diff          what a change to the definition does; a designer's draft checked against the live one
    watch         monitoring: each run's computed digest, watches, flags
    migrate       bringing an older lab onto all this, once

Import-safe (pyyaml + stdlib, no I/O at import). `newts <verb>` (tools/newts_cli.py) is its command line.
"""

from . import brief, checkpoints, define, diff, instructions, journal, migrate, model, rules, studies, watch  # noqa: F401
