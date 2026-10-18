# Project types

A project type describes the methodology: what a run means, what evidence it produces and how the
Lab’s research rules apply. Choose it when generating a new project. Attaching an existing repository
does not automatically add a methodology scaffold.

## Methodology and domain

| Choice | Sets | Source |
|---|---|---|
| Project type | Runner, staged scale, replication and evaluation discipline | `templates/project-types/<type>/TYPE.md` |
| Domain profile | Venues, data sources and field conventions | `templates/domain-profiles/<domain>.md` |

They compose: a mathematical economics study can use `theory` with `econ`. A profile does not
supply a working data pipeline or field-specific correctness checker.

## Shipped types

| Type | Work unit | Evidence and selection discipline |
|---|---|---|
| `ml` (default) | Train/evaluate a model | Validation selects; held-out test reports; multi-seed confirmation |
| `empirical` | Regression or specification | Recorded estimates, data/specification provenance, bootstrap or appropriate robustness checks |
| `simulation` | Seeded simulation draw | Independent draws; fixed calibration targets and out-of-sample checks |
| `theory` | Proof, derivation or counterexample attempt | Versioned proof/checker artifacts; explicit human verification where machine checking is unavailable |
| `target-driven` | Produce and score an output | Fixed task, metric, output contract, rules and scoring discipline |

The cards adapt the common rules; they do not make ML-style metrics appropriate for every field.
For example, deterministic theory does not gain credibility from repeated random seeds. The theory
card distinguishes machine-checked attempts from a human-checked proof, and requires the loss of
automatic claim verification to be stated.

For external targets, a repeatedly consulted leaderboard is not a pristine held-out test.
Select locally and limit external reads. See [target-driven projects](compete.md) and
[verification limits](research-limits.md).

## Runner contract

Generated projects share the base in `templates/project/`. The type card is copied to the project,
and `control.yaml` records `project_type`. The researcher confirms the type and optional domain
during `/spawn-project`, or an approved campaign chooses within its bounds.

The runner supports:

- **`python-import`**: calls the project package’s experiment function.
- **`shell-command`**: runs an argument list such as Rscript, Stata, Julia or a proof checker.
  It receives `RUN_DIR`, `CONFIG_PATH` and `SEED`, then writes a flat metrics object to
  `$RUN_DIR/result.json`.

```yaml
project_type: empirical
runner: shell-command
runner_command: ["Rscript", "spec.R"]
```

This preserves run/config/provenance recording across languages. The agent must still implement and
check the method, smoke run and analysis. A recorded `checked: true` is only meaningful if the
underlying checker and proof support it.

## Add a type or domain

A researcher can add a type card or domain profile and review it through the normal definition
process. State the evidence, staged progression, selection discipline and failure criteria explicitly.
Use a PI override under `lab/templates/` when applicable. A new card needs no separate executor,
but a method outside the existing runner seam may need an implementation.
