# Iterate and checkpoints

## The loop — this is the point

The method space is **open** (no headline-hypothesis boundary), so fan out toward the metric, with the
engine's normal discipline:

- `/experiment <slug>` — the next planned line, SMOKE→PILOT→FULL; one `EXPERIMENT_LOG.md` entry +
  `runs/registry.jsonl` row + one git commit per attempt (rules 7, 8, 11).
- `/improve <slug> explore` — fan out variants. It **expands the frontier** only if the PI has set
  `loop.mode: explore` and `loop.explore_max_expansion_rounds` > 0 (PI-owned); at the defaults it does
  nothing, because a target project has no settled decisions to reopen.
- `/ideate --in-project <slug>` — generate **divergent approaches** inside the project (scoped to
  the frozen set: task/metric/output/rules/deadline). Fully in-bounds here (no headline boundary to
  trip), so it is the main idea-generator for the climb (requires `ideation.in_project: true`; if
  `false`, use a successor hub `/ideate`).
- `/research-loop <slug>` — unattended climbing under a `LOOP_BRIEF.md`, with **`target.done` and the
  deadline as stop conditions** (it checks the loop's approval itself). `Mode: explore` is subject to the
  same PI-owned settings as `/improve explore`.
- **Selection discipline (hard rule 5, sharpened):** tune/select on the **local** validation
  split; when scoring is external, the scorer **is** the held-out test — read it sparingly via
  `scripts/report_score.py`, never select on external rank alone.

## Checkpoints & the outward action

The workflow's checkpoints bind like any study's: the brief lists them with their ids, status and the
PI's notes.

- **External scoring is an outward action.** Before sending an output to a scorer or leaderboard, find
  the brief's `during` checkpoint whose `at` covers it and check it:
  `arlo.py approved <slug> <checkpoint-id>` (exit 0 = approved). Not
  approved → stop and ask (headless: `needs_pi=<checkpoint-id>`). `scripts/report_score.py` also
  refuses an external read until it is approved. How many reads the PI allows is in their note on
  that approval — follow it. The deadline **hard-blocks** an external read in `report_score.py` and
  stops the `/research-loop`; `check_output.py` only **warns** on it (it validates a file, it doesn't
  block submission).
- **The final output is the PI's.** When the target is met or the budget is spent, the step's
  procedure reports `done`; the workflow holds the study for the PI to choose the final output (their
  note names the run). Present the best runs and stop. The approval starts the next step's procedure
  (`/finalize <slug>`: a reproducibility pass on the chosen run; cited artifacts/output secured in the
  project). Sending anything outside the lab beyond the approved scorer is the PI's.
