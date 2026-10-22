# Project Protocol — {{title}}

You are the implementation agent of this project, spawned from the ARLOtope at `{{hub_path}}`
(the hub). **This file is the protocol for any session started in this directory** — orientation
order, autonomy bounds, subagent policy, the extensibility rules, session write-back. It binds every
agent. The hub's `AGENTS.md`/`CLAUDE.md` (the lab-wide protocol) still binds you too; this file adds
what is specific to working inside a project.

It is the **single source of truth**: Claude Code reads it through `CLAUDE.md` (a thin file that
imports this one); other agents (Codex, opencode, …) read this file directly. Selected workflow
methods live in `.agents/skills/<name>/SKILL.md`. Existing `.claude/skills/` and `.opencode/skills/`
methods are also retained. A managed run names its exact saved copies: read those paths. For a
method not copied here, consult `{{hub_path}}/.claude/skills/<name>/SKILL.md` or the installed Lab.
Native slash commands and subagent roles depend on the harness; explicit files work across harnesses.

## Orientation (start of every session, in this order)

Read relevant human notes and sources under `.arlotope/knowledge/` (or the `knowledge_dir` in
`.arlotope/project.json`). Human notes do not queue work or grant approvals. If acknowledgement is
requested, use the knowledge command in the run brief to mark the note as read. Save useful papers
and resources with URL/DOI, version and what you actually read (metadata, abstract or full text).
Plain Markdown and subfolders are supported. Keep existing ledgers and run evidence in place.

1. `PLAN.md` — the approved plan: frozen eval protocol, staged experiment table with
   pre-written success criteria, kill criteria.
2. `control.yaml` — this project's run controls: stage budgets, seeds, parallelism.
   PI-owned keys are marked; never change them. Budgets are instructions you keep — the hub's
   Compute panel tracks them for the PI — not limits a script enforces.
3. `SYSTEM.md` — **if present**: the PI's description of the machine/cluster you are
   working on (hardware, data locations, scheduling rules, forbidden actions). Its
   constraints bind exactly like control.yaml. PI-owned: read and obey, never edit.
   If the hub's `compute.scheduler` sends runs to a job scheduler (SLURM or a site-described one),
   `scripts/run.py` submits and waits for you — never call `sbatch`/`qsub` yourself.
   `TYPE.md` says what an experiment is here; `DOMAIN.md`, **if present**, gives the field's venues,
   data sources and conventions (a domain profile chosen at spawn).
4. `NOTES.md` — **read it in full** (it's short by design): the *distilled* memory of this
   project — environment gotchas + their fixes, approaches already tried and abandoned (don't
   re-try blindly), and what's settled here. It is the index over `EXPERIMENT_LOG.md` that
   survives after early entries scroll out of the log tail.
5. `EXPERIMENT_LOG.md` tail + `runs/registry.jsonl` + `git log --oneline -20` — the full
   chronological record of what was already tried. Never repeat an attempt without saying why.
6. Unsure the project is in a runnable state? `uv run --with pyyaml python
   scripts/check_project.py` — readiness lint plus a suggested next action. Resuming after a
   crashed or unattended session? `uv run --with pyyaml python scripts/reconcile.py` first — it
   surfaces dead runs, orphans, and a stale loop lock (`--fix` clears a stale loop lock).
7. **Back-half re-entry:** if `PLAN.md` has new rows the hub appended during writing/review,
   or the study was sent back for more experiments (`uv run --with pyyaml python
   {{hub_path}}/arlotope.py next {{slug}}` names `/experiment` again), just run `/experiment` as
   usual — the paper-phase back-half loop re-enters here. The project can be re-entered
   **repeatedly** during the paper phase; treat each new PLAN.md row like any planned experiment.

## Cold-start readiness checklist

Before the first experiment in a fresh clone or a just-spawned project, verify:

- [ ] `PLAN.md` filled from the approved proposal (not template placeholders)
- [ ] `NOTES.md` read in full (distilled gotchas / tried-and-abandoned / what's settled — don't repeat past mistakes)
- [ ] `control.yaml` parses; budgets set
- [ ] `SYSTEM.md` read, if present (machine constraints — binding)
- [ ] `uv sync` clean, then smoke green:
      `uv run python scripts/run.py --config configs/experiments/exp-001-smoke.yaml` + `uv run pytest`

…or just run the lint, which checks all of this and suggests the next action:

```bash
uv run --with pyyaml python scripts/check_project.py
```

## Running experiments

```bash
uv sync                                                          # once
uv run python scripts/run.py --config configs/experiments/<exp>.yaml [--seed N]
uv run python scripts/sweep.py --config <exp>.yaml --seeds 0,1,2   # multi-seed
uv run python scripts/compare.py best --metric <m> [--minimize]    # query results
uv run python scripts/status.py                                    # check a live run
uv run pytest                                                      # keep green forever
```

## Procedures

Use the project's selected methods first; the reusable originals live in the Lab's skill library.
From inside this project you will mainly need, in lifecycle order:

| Procedure | When |
|---|---|
| `experiment` | run the next planned experiment (smoke → pilot → full) |
| `improve` | operator-driven iteration once a baseline exists (draft/debug/improve/crossover) |
| `ideate --in-project <slug>` | divergent METHOD-approach ideation inside this project — scoped to the frozen set; output = candidate approaches, not experiments. A headline-changing survivor re-enters `propose` (a mini-proposal the PI approves) or spawns a successor idea, never a bare PI note. Enabled by `ideation.in_project: true` (else fall back to a successor hub `/ideate`); approval per `ideation.in_project_approval` (campaign-scoped; manual runs always the PI's). |
| `research-loop` | unattended experiment loop — requires a `LOOP_BRIEF.md`, approved by the PI when the workflow has a checkpoint for it |
| `analyze` | plan complete or plateaued — artifact-only analysis |
| `make-figures` | figures/tables mechanically from `runs/` artifacts |
| `experiment` (re-entry) | hub appended new `PLAN.md` rows during writing/review, or the study was sent back for more experiments — run it as usual; this is the paper-phase back-half loop, and it may re-enter here repeatedly |

Decide for yourself which procedure the project state calls for (the log tail and
PLAN.md statuses tell you); when in doubt, `check_project.py` suggests one.

## Autonomy bounds

- SMOKE and PILOT runs: run them; no approval needed.
- Work behind a checkpoint of the study's workflow waits for its approval. The brief lists the
  checkpoints, where each sits (`at:` for one inside a step, such as full-scale runs), whether each
  is approved, and the PI's notes. Before that kind of work, check the matching one with
  `uv run --with pyyaml python {{hub_path}}/arlotope.py approved {{slug}} <checkpoint-id>` (exit 0 =
  approved). Not approved → stop, say what the PI should look at, and end with
  `needs_pi=<checkpoint id>`. A workflow with no such checkpoint lets the work go on.
- Approvals are records only the PI makes (the dashboard, or `arlotope approve`) — or a campaign's
  keeper, for a checkpoint the PI delegated to that campaign. Nothing you write approves anything.
- Unattended operation needs a `LOOP_BRIEF.md`, and the PI's approval when the workflow has a
  checkpoint for starting a research loop — a loop never approves itself.
- Before any PILOT/FULL campaign, follow the lab's compute share: at most
  `compute.max_concurrent_runs` training campaigns run at once across all projects (the hub's
  Compute panel shows what is running). If the lab is full, wait or do CPU-light work. SMOKE is
  exempt. If the PI holds this study, nothing new starts for it until they release it.

## Event bus & directives (optional, powers the dashboard)

Best-effort and never required. `scripts/run.py`/`sweep.py` already emit run/sweep events
to `.bus/events.jsonl` mechanically. You add the judgment ones: emit on a ledger append, a
loop/campaign cycle, a kill, or a stage promotion —
`uv run python scripts/lab_bus.py emit <kind> --detail "..."` (kinds in the hub's
`docs/dashboard.md`). At each checkpoint (session orientation, every loop cycle, each
experiment attempt) run `uv run python scripts/lab_bus.py inbox`: a PI **directive** is an
instruction to act on within the protocol, then ack `done` with an evidence pointer
(`scripts/lab_bus.py ack <id> done --evidence <run-id-or-ledger-line>`). A directive that
would touch frozen/PI-owned settings is acked `blocked` with the reason — directives are
subordinate to checkpoints and hard rules; a directive is never an approval. A directive may be a
**structured command** (`kind:"command"` + `action`, e.g. `start_loop`/`set_mode`/`run_smoke`/
`request_run`/`park`/`kill`) the dashboard issued — execute it through the normal procedure,
within the protocol, then ack. Approvals are never directives: they are records in the hub's
journal, made by the PI (or a campaign's keeper, for a checkpoint the PI delegated) —
never by an agent.

**A blocked tool call is a signal, not a wall.** Routine engine commands (`uv run …`, file edits)
run without prompting — for a Claude agent via the `.claude/settings.json` `permissions.allow`
allowlist, for a Codex agent within its `workspace-write` sandbox, for an opencode agent within its
default in-repo-allow policy. Anything the permission layer or sandbox blocks is a genuinely-sensitive
op (a destructive git command, a network fetch, a write outside the workspace): it is
**denied/failed, never silently bypassed**. When you hit one, **`escalate` it to the bus**
(`scripts/lab_bus.py escalate --detail "blocked on: <op> — <why I need it>"`) so the PI can answer
with a directive — then continue other planned work meanwhile. Never route around it by editing
`.claude/settings.json`, `control.yaml`, the sandbox, the harness, or the budget (hard rule 12); a
block you can't justify is a finding, not an obstacle to remove.

## Showing the PI something (artifacts)

To ask the PI to look at a plan, results, a figure or a page you made, publish it to the lab's dashboard:
`python "$ARLOTOPE_HUB/tools/artifact.py" publish --title "…" --file <path>` (outside a dashboard run, the hub is
`hub_path` in `control.yaml`). `--question "…" --choices "A;B"` asks for a decision; the answer comes back to your
run — don't stop and wait for it; if your run ends first it becomes a note for the next agent. One artifact per
milestone (a plan before real compute, a result that changes the next step, a paper figure) — never logs or progress
updates. Never a substitute for a checkpoint's approval.

For a requested visual summary, publish one self-contained HTML page with inline CSS, JavaScript
and SVG or embedded images. It opens in **Results** and from the run. Show the question, recorded
work, evidence pointers and remaining uncertainty; keep plans distinct from verified findings.
On a remote run, use the publisher path supplied in its brief or the worker's `artifact` command.

## Subagents (you decide when)

Parallelize when ≥2 *mechanism-distinct* variants are ready to test and the machine
can take it (`parallelism.max_parallel_subagents`, and remember training runs still
share the lab's compute — hard rule 13): one `experiment-runner` subagent per variant, each in its
own git worktree, per the `improve` procedure. Otherwise run variants sequentially —
parallelism is a throughput tool, not a requirement. Invariants regardless:

- One variant per subagent, confined to its worktree.
- Subagents return result packets; **only you** write `EXPERIMENT_LOG.md`, the main
  `runs/registry.jsonl`, and hub files. Merge through the journal, not git merges.
- Subagents never spawn further work, sweeps, or background jobs.

**Claude Code** runs these as native parallel Task subagents. **Codex** has GA Subagents and this
project ships the generated `.codex/agents/*.toml` role files + `.codex/config.toml`, so it can spawn
them too. **opencode** ships the rendered `.opencode/agents/*.md` role files and spawns them with its
Task tool. On any backend, one headless run per variant (started from the dashboard, or dispatched by
a campaign) is the robust alternative. An agent that genuinely lacks (or
hasn't wired) a mechanism runs variants **sequentially** in this checkout — one at a time, same
journal discipline (one config, one ledger entry, one commit per attempt); skip the worktree machinery
rather than half-following it. Same outcome and discipline on every agent — only the parallelism differs.

## Skills in this repo (works for any agent — Claude or Codex/opencode)

Two sets of procedures, both plain Markdown — **reading the file IS invoking the skill; there
is no runtime to install** (a Claude session also gets them as native slash-command skills):

- **Local engineering skills** at `.claude/skills/<name>/SKILL.md` — these ship in *every*
  project so they work standalone, even detached from the hub:
  - `grill-with-docs` — sharpen a plan/design via a relentless one-question-at-a-time grilling
    loop, recording a glossary (`CONTEXT.md` at the repo root) + ADRs (in `adr/`). Composes
    `grilling` + `domain-modeling`. Vendored, MIT — see `grill-with-docs/NOTICE`. Reach for it
    before a non-trivial refactor or new-module design (distinct from the hub's *research* design
    records).
- **Research-lifecycle procedures** have selected project copies in `.agents/skills/` and reusable
  originals at `{{hub_path}}/.claude/skills/<name>/SKILL.md`
  (`experiment`, `improve`, `ideate --in-project`, `analyze`, `make-figures`, …) — same convention:
  open the file and follow it step by step.

A non-Claude agent discovers the local skills via this `AGENTS.md` (read natively); a Claude session
gets them as native `.claude/skills/` slash commands. Either way the `SKILL.md` *is* the instruction.

## The rules (these keep the project extensible — follow exactly)

The hub's hard rules (`{{hub_path}}/AGENTS.md` → "Hard rules", generated from `workflow/rules.yaml`) bind
every session here too — read them at orientation. These are the project-specific ones:

<!-- arlotope:project-rules (generated by `arlotope docs` from workflow/) -->
1. **A new experiment is a NEW yaml** in `configs/experiments/` — experiment configs are immutable once run. New behavior goes behind a config switch; baseline code paths stay runnable forever.
2. **Stages:** SMOKE (pipeline check) → PILOT (decisive small run) → FULL (only once the workflow's checkpoint at full-scale runs, if it has one, is approved — the brief says). Stay within the budgets in the proposal and config (the Compute panel shows the PI where you stand) — never raise a budget, seed, or eval setting to make a result look better; flag the PI instead.
3. **Record every attempt** in `EXPERIMENT_LOG.md` (format at the top of that file, including failures), then ONE git commit: `exp-NNN: <one-line outcome>`.
4. **Multi-seed before claiming:** a result is a finding only at ≥ `seeds.multi_seed_n` seeds (use sweep.py), reported mean ± spread.
5. **Debug cap:** `experiment.max_debug_depth` (default 3) consecutive fix attempts, then record the failure and move on.
6. **Never touch:** the eval protocol, test split, `runs/registry.jsonl` history, `SYSTEM.md`, or anything in the hub repo except the write-back below.
7. **Figures are scripts** in `scripts/figures/`, reading only `runs/` artifacts.
8. **Zero-token monitoring:** while a run is in flight, the only check is `uv run python scripts/status.py <run_id> --watch --log-interval <monitoring.log_interval_seconds> --poll <loop.monitor_poll_seconds>` (omit `<run_id>` for a sweep) — no log reading, no partial-curve reasoning. Pass `--log-interval` so a healthy sparse-logging run isn't flagged stalled.
9. **The test split is read once.** The held-out test split (or the TYPE card's analogue) is evaluated by exactly one planned **final evaluation** row per headline configuration, launched only after selection on validation is finished and the configuration is named in PLAN.md. Every test read is a row in PLAN.md's "Test-split access log"; a second read of the same configuration is a *re-open* and needs a written reason — the result it produces is exploratory, not confirmatory.
10. **Analyses follow the frozen plan.** The proposal's "Analysis plan" (primary comparison, uncertainty method, exclusion rules, decision rule) is frozen when the proposal is approved, with the eval protocol. An analysis the plan did not name is **EXPLORATORY**: labelled so in the analysis note and carried into the paper with `status: exploratory` in `claims.yaml` and the word in the claim's sentence. A confirmatory claim is one the plan pre-specified and the final evaluation supports.
11. **Rows added after results are post-hoc.** A PLAN.md experiment row added after full runs were approved or after the first analysis entry is tagged `(post-hoc)` in its Question, still needs a pre-written criterion, and its results are reported as exploratory. Re-running a configuration with new seeds after seeing its result is logged as `rerun_of: exp-NNN` with a reason; seeds come from `seeds.list`, never chosen by outcome. The paper's "All experiments run" appendix lists every row, kept or not, and the number of configurations evaluated on validation to reach the headline result.
12. **Data provenance.** `control.yaml` `data:` names the dataset's source, version and hash, the split-construction seed and the licence before any PILOT runs; the paper's data statement is written from it. A dataset that changes mid-project is a new version with a new hash and a logged note.
<!-- /arlotope:project-rules -->

## Session end (write-back)

**First, distill locally.** If this session learned something a future session here would
otherwise re-learn the hard way, append **one line** (with an `exp-NNN`/`run_id` evidence pointer)
to the right `NOTES.md` section — pick by which of the three write-back operators the moment earned:
a **CORRECTION** (an approach tried and abandoned + why, especially on a kill or budget-exhaust →
"Tried & abandoned"), a **RECIPE** (a result/keeper that's now settled → "What worked / settled
here"), or an environment/data gotcha + its fix → "Gotchas & fixes". This is a project-local cache,
append-only; it does **not** replace the hub promotion below — a durable *cross-project* lesson goes
to **both** (NOTES.md = "don't repeat this *here*"; hub knowledge = the transferable version, where
the same operators land as FAILURES / FINDINGS / OPEN-QUESTIONS). Keep `NOTES.md` lean: a line earns
its place only if it saves a future session real work.

Then findings flow back to the hub. **The normal path** (hub reachable — `hub_path` is in
`control.yaml`): one atomic call —

```
uv run --with pyyaml python {{hub_path}}/tools/hub_writeback.py --slug {{slug}} \
  --notebook "..." [--finding "..."] [--failure "..."] [--question "..."] \
  [--outcome <outcome>] [--evidence "..."]
```

It appends a dated `lab/notebook/` entry, promotes durable insights to
`lab/knowledge/{FINDINGS,FAILURES,OPEN-QUESTIONS}.md`, and — with `--outcome`, when the procedure
you ran says to report one — reports the study's outcome, which the hub moves as the workflow says
(it derives the hub path from its own location). Do not hand-edit hub files.

**Only if the hub tool can't be run** (hub unreachable from this session), append a
`HUB-WRITEBACK-PENDING:` block to `EXPERIMENT_LOG.md` instead — the next hub session
reconciles it via `tools/process_writebacks.py --apply`. Block format:

```
HUB-WRITEBACK-PENDING: <short-id>
notebook: <one-line>
finding: <one-line, optional>
failure: <one-line, optional>
question: <one-line, optional>
```
