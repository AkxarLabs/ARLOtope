# checks/ — the lab's mechanical rules

A **check** turns one of the lab's rules (`workflow/rules.yaml`) from prose into something an agent can't
skip: it reads the lab's files and exits **0 = OK · 1 = BLOCKED · 2 = WARN**. The skills call checks at
the moments that need them, and a workflow's checkpoints name them (`checks:` to approve, `watch:` to
flag work done past them). Where a study may move, and whether a checkpoint is approved, are the kernel's
(`arlo move`, `arlo approved`), not a check's.

A check takes one of two forms:

1. **A guard check** — a module with `NAME`, `add_args(parser)` and `run(args, guard) -> int`. The guard
   finds it by itself, so it runs as `uv run --with pyyaml python tools/guard.py <NAME> …` (and
   `tools/guard.py --list` shows it). `guard` gives it the lab: `HUB`, `LAB`, `labfiles`,
   `_row(slug)`, `_project_dir(slug)`, `_today()`, and `_verdict(code, message)` to print and return the
   result. `writeback.py` is the smallest example.
2. **A standalone script** with its own arguments — the paper audits (`audit_*.py`). Run it as
   `uv run --with pyyaml python checks/<script>.py …`. Naming one under `audits:` in
   `workflow/rules.yaml` lets a checkpoint list it under `checks:` (`workflow/workflows/<id>.yaml`): the
   checkpoint sheet shows its result, and a campaign (or an `auto` checkpoint) may approve only when
   every one exits 0. A checkpoint can give a check parameters — `{budget-under: {usd: 50}}` — which it
   receives as `--usd 50` (declare them in `add_args`).

| Check | Enforces | Called by |
|---|---|---|
| `append-only` | the project's ledgers were only appended | `/experiment`, `/improve`, the loop |
| `writeback` | the session wrote back to the hub | session end |
| `evolve` | a kill left a CORRECTION; a result left a RECIPE | after a kill, at results-stage exits |
| `decisions` | settled non-headline decisions carry a Revisit predicate | `/scope`, the loop |
| `plan-trace` | every PLAN.md row traces to an authorized origin | the loop, `/improve` |
| `full-runs-without-approval` | no full-scale run started before its checkpoint was approved | the `watch:` of the default research workflow's approve-full-runs checkpoint |
| `audit_claims.py` | every paper number traces to a run artifact | `/write-paper`, `/review-paper`, `/finalize`, a checkpoint that lists it |
| `audit_multiseed.py` | headline claims are multi-seed | the same |
| `audit_ablation_coverage.py` | every planned ablation ran, was waived, or was routed back | the same |
| `audit_eval_discipline.py` | tuned on validation, reported on held-out test | the same |
| `audit_spec_conformance.py` | cited runs used the planned data, split, metric and benchmark, or say otherwise | the same |

**Adding a rule with a check:** add the rule to `workflow/rules.yaml` (with `checks: [<name>]`), drop the
check here, call it from the skills that need it, and run `arlo docs`. A lab that
does not use a method (say, `decisions.md`) can delete its check and the calls to it.
