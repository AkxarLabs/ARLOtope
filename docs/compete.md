# Target-driven projects

Use `/compete` for a fixed target: improve a benchmark metric, meet a scored output contract or
reach a task-specific threshold. Use `/ideate` for a research direction and `/adopt` to continue
existing work. A target project can be useful without producing a paper.

## Define the target first

The interview records:

- Task, metric and direction, done-condition and any deadline.
- Data/resources, local validation and the held-out or external evaluation.
- Output format, identifiers, required columns and row count, when relevant.
- Allowed data, models, runtime and account rules.
- Stage and total compute budgets.
- Internal scoring or an external scorer, its command and authorized read limits.

An optional `/discuss target` session can clarify these choices first. Record credential *names*
and setup instructions, never secrets, in `TARGET.md`.

The shipped `target` workflow starts at `active` and ends at `final`; it has no separate proposal
stage. The interview establishes setup and budgets, but does not approve any checkpoint. Inspect the
actual workflow if it has been customized.

## Work and evidence

New projects use the common scaffold plus `templates/compete/`. Existing repositories keep their
code and runners; add the agreed output/evidence contract around them rather than replacing them.

| File | Purpose |
|---|---|
| `TARGET.md` | Task, rules, metric, deadline and output contract |
| `control.yaml → target` | Machine-readable target and scoring configuration |
| `PLAN.md` | Baselines, staged attempts, ablations and stopping criteria |
| `scripts/check_output.py` | Validate a produced output |
| `scripts/report_score.py` | Obtain/record scores and append the scoring ledger |
| `runs/scores.jsonl` | Score-read history alongside ordinary run artifacts |

Run SMOKE before PILOT and FULL. Use `/experiment` for planned attempts, `/improve` for variants,
and `/ideate --in-project` for new approaches when enabled. A target opens the method space; it
does not permit changing the task, rules, metric, validation split, budget or deadline to make a
result look better.

`/research-loop` needs its own approved scope and applicable workflow permission. A workflow without
a loop checkpoint is not a blanket instruction to run unattended.

## Score without turning the test into training data

Internal validation can guide selection. Keep a separate final evaluation. External scoring sends
an output outside the Lab and waits for the applicable approval. A public leaderboard consulted
repeatedly becomes part of selection, so do not present it as untouched held-out evidence.

Before an external read, the generated helper checks the workflow’s scoring approval and deadline,
validates the output, then records the attempt:

```bash
uv run --with pyyaml python scripts/report_score.py --run-id <id> --via command --note "baseline"
```

`target.scoring.score_command` is supplied for the actual scorer; no Kaggle or provider integration
is assumed. Manual scores can be recorded with `--score`. `--record-only` appends a score for an
already-counted read; it does not authorize a new submission.

The researcher’s approval note defines permitted reads. The current helper records reads and checks
approval/deadline; it does not parse that prose into an enforced daily or total quota. Agents must
track and respect the agreed limit. A failed command is recorded separately; if it may have submitted
successfully, inspect the scorer before retrying.

## Decisions and stopping

The shipped workflow has two researcher-owned checkpoints:

| Checkpoint | Decision |
|---|---|
| Approve external scoring | Which outputs may leave the Lab and the allowed scoring scope |
| Choose the final output | Which recorded run supplies the final result |

![Review a checkpoint and its evidence](assets/current/checkpoint.webp)

Reaching a target or exhausting the budget stops iteration. Present the local evidence, external
reads, remaining uncertainty and candidate output. The researcher chooses the final run.
Finalization preserves its configuration and evidence; it does not make a submission on its own.

See [project types](project-types.md), [configuration](configuration.md) and
[research limits](research-limits.md).
