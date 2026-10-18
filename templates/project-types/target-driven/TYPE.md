# Project type: `target-driven`

A task with a **fixed, straightforward target** — a benchmark to beat, a metric to hit, a
leaderboard to climb, an internal KPI — iterating toward the number instead of writing a paper.
This type **is** `/compete`: it applies the `templates/compete/` overlay on top of the base.

- **An experiment is:** a run that produces a **scored output** + a local metric.
- **Runner:** `python-import` (or `shell-command` to wrap a starter kernel in any language).
- **Frozen set (reinterpreted):** `{task data/resources, metric + direction, output contract,
  rules, deadline}`. There is **no headline-hypothesis boundary** — model/feature/approach changes
  and `/ideate --in-project` are all in-bounds.
- **Selection discipline:** an **external scorer IS the held-out test** — tune/select on local CV,
  treat each external read as scarce. Sending output out waits for the `target` workflow's
  "Approve external scoring" checkpoint (`scripts/report_score.py` refuses until it is approved);
  selecting the final output is the PI's "Choose the final output" checkpoint.
- **Multi-seed / staged scale:** as `ml` (seeds; SMOKE→PILOT→FULL).
- **Output:** the target output (no paper layer; `/ideate→/lit-review→/scope→/propose` are N/A).
- **Brief:** `TARGET.md` (PI-owned) + `control.yaml` `target:`. On-ramp: `/compete`; close-out: `/finalize`.
- **Skills:** `/experiment`, `/improve` (explore), `/ideate --in-project`, `/research-loop`. The
  paper skills (`/write-paper`, `/review-paper`, novelty gate) do **not** apply.
