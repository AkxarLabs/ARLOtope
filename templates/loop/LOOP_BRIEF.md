# Loop Brief — {{title}}

*Project: `{{slug}}` · Created: {{date}} · Everything above the Loop Log is
FROZEN once the PI approves the loop — changes need a fresh approval.*

## Goal (frozen)

- **Primary metric:** <!-- one metric + direction, e.g. "minimize val_loss" -->
- **Target / done condition:** <!-- e.g. "beat exp-002 baseline by >= X beyond seed noise" -->
- **Headline hypothesis (frozen):** <!-- the central claim the proposal's novelty rests on,
  copied from proposal.md. The loop may reopen NON-headline design decisions autonomously in
  explore mode; reopening this / abandoning it is the escalation boundary (PI note). -->

## Loop mode (frozen)

- **Mode:** `execute` <!-- execute | explore -->
  - `execute` — run the approved PLAN.md (planned experiments → ablations → multi-seed →
    /improve operators), then stop when exhausted. The conservative default.
  - `explore` — autonomous in-project iteration: when the plan is exhausted with budget left,
    the loop may **expand the frontier** (propose results-grounded new lines) and **reopen
    non-headline design decisions** (`decisions.md` whose `Revisit if:` trigger fired), all
    within the frozen set and the budget below. The PI's approval of the loop (with mode `explore`)
    authorizes this wider action space. See docs/autonomy.md.
- **Explore caps** (apply only in explore mode; default from control.yaml `loop.explore_*`):
  - Max expansion rounds: ___  ·  Max new lines per round: ___

## Budget

- **Total wall-clock for the loop:** <!-- e.g. 8 hours -->
- **Max cycles:** <!-- e.g. 40 -->
- **Max runs:** <!-- e.g. 60 -->
- **Full-scale runs:** if the study's workflow has a checkpoint for full-scale runs, only once it is
  approved (the brief says whether it is, and the PI's note on it). Not approved → full-scale work
  stops and asks.

## Stop conditions (any one stops the loop)

1. Goal met (confirmed at `experiment.multi_seed_n` seeds).
2. Budget exhausted (wall-clock, cycles, or runs).
3. Any kill criterion below fires.
4. `loop.no_progress_backoff_cycles` consecutive cycles without progress (see contract).
5. Unrecoverable environment failure (env broken after `experiment.max_debug_depth` fix attempts).

## Kill criteria

<!-- copied VERBATIM from PLAN.md — do not soften them for the loop -->

## Monitoring contract

- While a run is in flight, the only permitted check is
  `python scripts/status.py <run_id> --watch --log-interval <monitoring.log_interval_seconds>
  --poll <loop.monitor_poll_seconds>` (omit `<run_id>` for a sweep) — no log reading, no
  reasoning about partial curves (the Compute panel tracks time and GPU use). `--watch`
  returns on terminal status or two consecutive stalls; `--log-interval` must match the
  experiment's logging cadence so a healthy sparse-logging run isn't killed.
- **Progress** = best-primary-metric improvement beyond seed noise, OR a planned
  question resolved (a clean negative counts; a crash does not).

## Approval

If the study's workflow has a checkpoint for starting an unattended research loop (the brief lists
it, with its id), the PI approves it in the dashboard (the study's sheet → Run overnight) or with
`arlo approve <slug> <checkpoint-id>`; the approval is a record in the lab's journal, and the PI's
note on it carries the mode. A loop never approves itself.
`uv run --with pyyaml python <hub>/arlo.py approved <slug> <checkpoint-id>` says whether it is approved.

## Loop Log (append-only)

| cycle | started | action | run id(s) | best {{metric}} | progress? | note |
|---|---|---|---|---|---|---|
