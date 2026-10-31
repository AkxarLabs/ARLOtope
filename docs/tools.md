# Tools

Most Lab tools use Python's standard library and PyYAML. Run hub commands through `uv`; generated
project helpers ship with spawned projects. Existing attached repositories keep their own tooling.
Method-specific helpers live with their skill; research checks live in `checks/`. Use a command's
`--help` for its complete arguments.

## Find a command

| I want to… | Tool |
|---|---|
| Launch the dashboard or inspect studies | `arlo` / `arlo.py` |
| Attach a project | `tools/research_start.py` |
| Read notes or retained sources | `tools/knowledge.py` |
| Queue, inspect or resume an agent | `tools/executor_cli.py` |
| Inspect or save workflow history | `tools/study_history.py` |
| Publish a report | `tools/artifact.py` |
| Inspect effective settings | `tools/show_config.py` |
| Validate Lab definitions | `arlo check` |
| Use any dashboard API from a terminal | `arlo api` ([guide](api.md)) |
| Open a study in the browser | `arlo open <study>` |

For dashboard steps, use [Start and follow work](running-work.md). This page covers terminal and
developer tools. Commands do not require installing a separate ARLOtope package.

## Checks (`checks/`)

The lab's mechanical rules, one file each — see `checks/README.md`. The guard checks (`append-only`,
`writeback`, `evolve`, `decisions`, `frozen`, `plan-trace`, `full-runs-without-approval`) run through `tools/guard.py <check>`; the paper audits
below are scripts of their own. A lab adds a check by dropping a file here (and naming it in
`workflow/rules.yaml`), or removes one it doesn't use.

### `audit_claims.py` — verify a paper's numbers against artifacts

```bash
uv run --with pyyaml python checks/audit_claims.py studies/<slug>/paper [--rel-tol 1e-3] [--check-commits]
```

For every claim in the paper's `claims.yaml`, each number must be found in the referenced run artifacts (resolved via `lab.projects_root`):

| Status | Meaning | Exit |
|---|---|---|
| `PASS` | number found directly in an artifact (tolerance = half-ULP of printed precision) | 0 if all pass |
| `PASS-derived` | matches the mean/std of a metric across the claim's artifact list (the "mean over N seeds" case) | 0 |
| `MANUAL` | no match but a derivation is stated — a human must verify; never silently passed | 2 |
| `FAIL` | artifact missing or no match (closest value reported) | 1 |

`/review-paper` Part A runs this and **blocks** the qualitative review on any FAIL or unresolved MANUAL. `--scan-integers` additionally flags bare integers sitting near result words (samples/tasks/runs/seeds/…), excluding years (1900–2099) and structural refs — off by default (integers otherwise swamp the scan with counts and section numbers).

`--scan-novelty` flags priority or superiority claims such as “first to” or “state-of-the-art”
without a citation or `% Cnnn/Nnnn` evidence pointer. It is a conservative regex check (exit 2),
not a novelty judgment. The writing procedure surfaces warnings; review and finalization require
them to be resolved against the literature notes. The word `novel` alone is not flagged.

### `audit_multiseed.py` · `audit_ablation_coverage.py` · `audit_eval_discipline.py` · `audit_prereg.py` — paper integrity

```bash
uv run --with pyyaml python checks/audit_multiseed.py         studies/<slug>/paper
uv run --with pyyaml python checks/audit_ablation_coverage.py studies/<slug>/paper
uv run --with pyyaml python checks/audit_eval_discipline.py   studies/<slug>/paper
uv run --with pyyaml python checks/audit_prereg.py            studies/<slug>/paper
```

Four focused audits that mechanize the hard rules `audit_claims.py` doesn't cover — each exits **0 clean · 2 needs-human-review · 1 violation**:

- **multi-seed** (hard rule 6): a claim marked `headline: true` in `claims.yaml` must be backed by ≥ `seeds.multi_seed_n` (project) / `experiment.multi_seed_n` (lab, default 3) distinct seeds — resolved by mapping each artifact's `runs/<run_id>/…` to its seed in `runs/registry.jsonl`. A `multi_seed_waiver:` (rationale) routes to MANUAL.
- **ablation coverage**: every bullet under the proposal's `### Planned ablations` must leave a trace in the project's `PLAN.md`/`EXPERIMENT_LOG.md`, be marked waived/N-A/dropped, or route back — none silently dropped (heuristic; the reviewer reads the table).
- **eval discipline** (hard rule 5): the frozen `§4` protocol must define both a validation and a held-out test set, and no `headline` claim may declare `split: validation` (reporting a selection-time metric). Theory/simulation types relax to MANUAL (the TYPE card defines the analogue).
- **pre-registration**: the proposal's frozen analysis plan names the primary comparison, the uncertainty method and the decision rule; `PLAN.md`'s test-split access log reads the held-out split once per configuration; every claim carries `status: confirmatory | exploratory`, and an exploratory one says so.

New optional `claims.yaml` fields these read: `headline: true` (marks a load-bearing claim), `split: test|validation` (which set it's reported on), `multi_seed_waiver: <rationale>`. Wired **WARN** in `/write-paper` (surface gaps while drafting) and **blocking** in `/review-paper` Part A + `/finalize`.

## Hub tools (`tools/`)

### `research_start.py` — create or attach a study

```bash
uv run --with pyyaml python tools/research_start.py --title "Replication" --question "Can we reproduce the reported result?" --local /absolute/project
uv run --with pyyaml python tools/research_start.py --title "First study" --question "What should we test?"
```

The dashboard's **New study** uses the same attach-first entry point. `--repo owner/repository`
clones a public GitHub repository; `--machine <id> --local <remote-path>` attaches on a connected
machine. It creates study records without installing project dependencies or starting research.
Attachment preserves the repository's files and environment.

`study_materials.py` manages optional starter briefs and original supporting uploads, plus reviewed
field suggestions from an ordinary agent run. Originals are kept under `studies/<study>/materials/`
with a `MATERIALS.md` index. Model suggestions do not create a study or approve work automatically.
`project_files.py` supplies one-folder browsing for local and remote folder pickers, without a
recursive scan. See [Getting started](getting-started.md).

### `knowledge.py` — shared records and human notes

```bash
uv run --with pyyaml python tools/knowledge.py --study <study> list
uv run --with pyyaml python tools/knowledge.py --study <study> search "evaluation"
uv run --with pyyaml python tools/knowledge.py --study <study> show <id>
uv run --with pyyaml python tools/knowledge.py --study <study> add --title "Data caveat" --text "Check the missing rows." --acknowledge
uv run --with pyyaml python tools/knowledge.py --study <study> ack <id>
```

Omit `--study` for Lab records; use `--project /absolute/project` for project-local access without
the hub. Markdown records and attachments live in the location from `.arlotope/project.json`, normally
`.arlotope/knowledge/`. Notes do not enqueue tasks. `ack` records that a requested note was read;
it does not accept an instruction, approve work or start an agent. Workspace Q&A saves a full separate
answer record. `--kind source` supports URL, DOI, version and coverage metadata so a reference link
is not confused with a captured full text. See [Shared knowledge](knowledge.md).

### `project_identity.py` · `remote_projects.py` · `project_worker.py`

These libraries handle stable Lab/project identities, the per-user discovery index, scoped remote
execution and the small SSH worker. The worker bundles the existing executor; it does not install a
second research Lab. Inputs, original materials, remote outcomes, knowledge records and artifact
publication use the same project/run identity. A disconnected tunnel does not stop a remote job.
Connect and browse through the dashboard; see [Machines and compute](compute.md).

### `check_lab.py` — lab state lint

```bash
uv run --with pyyaml python tools/check_lab.py [--stale-days N] [--strict]
```

Checks that every `studies/<slug>/` has an `IDEA.md` and is a study in the journal, orphan study/project dirs (`studies/<slug>/` in the hub and projects scanned at `lab.projects_root`; transient `-wt-` worktrees ignored), stale studies, that the lab's definition is consistent and every study stands on one of its steps, and the executor (a backend CLI that can't be found, runs stuck live). Exit 1 on real inconsistencies. `/lab-status` runs it every session.

### `s2.py` (in `.claude/skills/lit-review/tools/`) — literature search, BibTeX, citation verification, cite-from-lit-review lint

```bash
uv run --with pyyaml python .claude/skills/lit-review/tools/s2.py search "small LM distillation" [--limit 10] [--year 2023:] [--bulk]
uv run --with pyyaml python .claude/skills/lit-review/tools/s2.py bibtex arXiv:2504.08066 [--append studies/<slug>/paper/references.bib]
uv run --with pyyaml python .claude/skills/lit-review/tools/s2.py bibtex DOI:10.48550/arXiv.2504.08066   # the agentic websearch→DOI fallback
uv run --with pyyaml python .claude/skills/lit-review/tools/s2.py verify studies/<slug>/paper/references.bib [--threshold 0.85]
uv run --with pyyaml python .claude/skills/lit-review/tools/s2.py citecheck studies/<slug>/paper
```

The helper uses Semantic Scholar with OpenAlex fallback:

- **`search`** logs queries and returns paper metadata. Exit 3 means both services were unreachable,
  not that no related work exists.
- **`bibtex`** tries Semantic Scholar, DOI content negotiation, Crossref and OpenAlex. `--append`
  retains unique entries by key/DOI. If identifiers are missing, find the DOI and retry with `DOI:<doi>`.
- **`verify`** checks title, year and retraction metadata. Use `--threshold` to set the title-match
  threshold. Any nonzero exit blocks paper review.
- **`citecheck`** matches paper citations to `references.bib` and literature notes. A missing bibliography
  entry exits 1; a citation without a matching note exits 2 for manual review.

Env keys: `S2_API_KEY` and `OPENALEX_API_KEY`. Configure research service keys in Settings when a
service requires them or rate-limits anonymous requests. DOI/Crossref resolution supplies additional
fallback paths. If the retraction service is unavailable, `verify` prints **retraction check unavailable**;
that warning is not evidence that a paper has never been retracted.

### `show_config.py` — the effective config with provenance

```bash
uv run --with pyyaml python tools/show_config.py [<project-path> [exp-NNN.yaml]]
```

Prints the lab layer, the project's control.yaml, the effective skill values (control-first, lab fallback), and — given an experiment — the fully resolved run config with the layer that set each key. Backs `/configure`. See [Configuration](configuration.md).

### `profiles.py` — budget tiers & engine config profiles

```bash
uv run --with pyyaml python tools/profiles.py list|show <name>|diff <name>|validate <name>|apply <name>|save <name>
```

`apply` writes the profile's settings while preserving comments and checks the configured integrity
floors. Changes under `agents.*` re-render role files. `save` stores current settings as a named
profile. See [profiles and budget tiers](configuration.md#profiles-budget-tiers).

### `guard.py` — run the lab's checks

```bash
uv run --with pyyaml python tools/guard.py <append-only|writeback|evolve|decisions|frozen|plan-trace|…> <slug> [args]
uv run --with pyyaml python tools/guard.py --list     # every check in checks/ (the lab's own included)
```

One command for the checks in `checks/`, found by the guard: `append-only` (ledgers only appended),
`writeback` (rule 11 done), `evolve` (rule 11's write-back operators fired where the study's place
demands — BLOCK on a killed study that began work with no CORRECTION in FAILURES.md/NOTES, WARN on a
study that finished its workflow with no RECIPE in FINDINGS.md/NOTES), `decisions` (settled non-headline
decisions carry a machine-checkable Revisit predicate; `--strict` blocks on a missing one), `frozen`
(`eval_frozen` is true and the PI-owned `budgets` and `seeds` blocks are present), `plan-trace` (every
non-baseline PLAN.md row traces to a `D-NNN`/`(expand Rn)` origin; a `Headline-change: yes` row bypassing
`/propose` is blocked), and `full-runs-without-approval` (a checkpoint's `watch:` names it). Exit
**0 = proceed · 1 = blocked · 2 = warn**. Checkpoints run them (`checks:`), watches run them, and agents
run them where a procedure says so.

Where a study stands and whether a checkpoint is approved are the kernel's, not a check's: `arlo move`
refuses an illegal move and holds a study at an unapproved `before` checkpoint, and
`arlo approved <slug> <checkpoint>` exits 0 only when that checkpoint is approved. A check never grants
an approval.

### `kernel/` — the lab's definition, its studies and the journal

A library, not a command (`arlo` is its command line). stdlib + pyyaml, import-safe.

| Module | What it does |
|---|---|
| `model.py` | reads the definition: `workflow/steps.yaml`, `workflow/workflows/<id>.yaml`, `workflow/rooms.yaml` and each skill's `arlotope:` frontmatter; resolves variants (`like:`, `use:`); `check()` validates it |
| `journal.py` | `lab/journal.jsonl`, the one append-only record: every move, wait, approval and finish; a study's place is a fold over it, and `lab/REGISTRY.md` is a view written from it |
| `studies.py` | file a study, report an outcome (`move`), the PI's moves anywhere (`move_to`), its workflow, swaps and project |
| `checkpoints.py` | what a checkpoint shows (evidence, checks, history) and deciding it, enforcing who may approve (`approver: me \| me-or-campaign \| auto \| agent`); approving a `before` checkpoint a study waits at moves it on |
| `brief.py` | what an agent is told for one procedure and study: where it stands, the outcomes it can report and where each leads, the PI's instructions, the checkpoints ahead |
| `branches.py` | graph task visits, claims, joins, accepted outcomes and output freshness over the same journal |
| `instructions.py` | the PI's added instructions (`lab/workflow/`, `studies/<slug>/workflow/`) and agents' proposals for them |
| `rules.py` | `workflow/rules.yaml`: the rules, the named audits, PI-owned config, rigor floors and protected paths |
| `define.py` · `diff.py` | writing the definition back (Compose, designers, `tools/new.py`); what a change does, and a designer's draft checked against the live lab |
| `watch.py` | each run's computed digest, the watches, and flags (`info` · `warn` · `block`, `hold`) |

A journal line is `{ts, study, kind, by, …}`. `kind` is `new`, `move`, `wait`, `finish`, `approval`
(`decision`: `approved`, `changes-requested` or `revoked`), `workflow`, `use`, `project` or `remap`.
`study` is a slug, or `lab` for the lab as a whole (a campaign's brief, `campaign:<name>`; a panel's
collector, `panel:<id>`). `by` is `pi`, `cli`, `run:<id>`, `campaign:<name>`, `auto`.
Only the kernel writes it; the PI's verbs refuse inside an agent run, and the signature guard refuses
the file and the commands.

### `arlo_cli.py` — the lab from a terminal (`arlo <verb>`)

```bash
uv run --with pyyaml python arlo.py status                        # what needs you, what is running, every study
uv run --with pyyaml python arlo.py next <study>                  # where it stands and what runs next
uv run --with pyyaml python arlo.py move <study> <outcome> [--note "…"]
uv run --with pyyaml python arlo.py checkpoint <study> <checkpoint>
uv run --with pyyaml python arlo.py approve <study> <checkpoint> [--note "…"] [--start] [--yes]
uv run --with pyyaml python arlo.py changes <study> <checkpoint> --note "…"
uv run --with pyyaml python arlo.py revoke <study> <checkpoint> [--yes]
uv run --with pyyaml python arlo.py hold <study> [--reason "…"] | release <study> | pause | resume
uv run --with pyyaml python arlo.py panel compute
```

Core study and process actions have verbs here and share the dashboard's kernel. Browser-specific
features also use their focused tools and server routes:

- studies: `status`, `studies`, `new`, `move` (an outcome; or `--to <step>`, the PI's), `next`, `project`;
- checkpoints: `checkpoint`, `approve` (`--start` also starts the next step's procedure), `changes`,
  `revoke`, `approved`, `checks`, `approvals`;
- monitoring: `flags`, `ack`;
- runs: `start`, `ask`, `runs`, `run`, `answer`, `reply`, `stop`, `resume`, `pause`, `hold`, `release`;
- the definition: `workflow [show|set|use|rename-step]`, `brief`, `propose`, `check [--design <folder>]`,
  `docs [--check]`, `extension [list|install]`, `room`;
- `panels`, `panel`, `approve-collector` and `config`.

`arlo.py <verb>` dispatches to it (`arlo.py <verb> --help` for one verb's arguments). The PI's verbs
(`approve`, `revoke`, `changes`, `move --to`, `workflow set|use|rename-step`, `approve-collector`) refuse
inside an agent run, and ask you to confirm on a terminal (or pass `--yes`). Most verbs take `--json`.

### `new.py` — add to the lab by copying

```bash
uv run --with pyyaml python tools/new.py skill    <name> --like <skill>    [--step <step>]
uv run --with pyyaml python tools/new.py step     <id>   --like <step>     [--in <workflow> --after <step>]
uv run --with pyyaml python tools/new.py workflow|room|role|check|type <name> --like <existing>
uv run --with pyyaml python tools/new.py rule     <id>   --text "**Title.** What it says."
```

Copies the closest thing the lab already has under a new name, as a starting point for further edits. A copied skill
says `like: <skill>`: it is a variant, used in a workflow (`use:`), for one study (`arlo workflow use`),
or as a step's work. Then the generated docs are refreshed. The signature guard refuses it from a run.

### `lab_docs.py` — the generated parts of the manuals

Writes the spans between `<!-- arlotope:<name> … -->` markers from the lab's definition: the rules and
workflows in `AGENTS.md`, the head of every SKILL.md (how it finishes, what it must produce), the steps
table in [The workflow](workflow.md), and the dashboard's built-in copy of the definition. `arlo docs`
writes them; `arlo check` reports stale ones. It also writes the room brief (`arlo room <room>`).

### `labfiles.py` — the lab's files, read one way

A library: `lab/config.yaml`, the studies (from the journal), where a study's project lives, templates,
project types and domain profiles, and the defensive readers every tool shares.

### `panels.py` — the lab's instruments

```bash
uv run --with pyyaml python tools/panels.py list
uv run --with pyyaml python tools/panels.py show <id>       # its summary and data (collects if stale)
```

A panel is a folder with `panel.yaml`, a `view.html` and, optionally, a collector script. Panels come from
`dashboard/static/panels/shipped/` (the lab's own, e.g. Compute), `~/.arlotope/panels/` (yours, across
labs) and `lab/panels/` (this lab's); a later one overrides an earlier one. A view runs in a sandboxed
frame with no network. A collector is code, so it runs only once the PI approved that exact version
(`arlo approve-collector <panel>`, a record `panel:<id>`); shipped collectors need no approval. A
panel's data may carry alerts; each becomes a Inbox item, and an alert holds a study only if the PI
let that panel hold (`may_hold`).

### `configure.py` — owner-aware config view/set/profile

```bash
uv run --with pyyaml python tools/configure.py view [--project <slug|path>] [--experiment <yaml>]
uv run --with pyyaml python tools/configure.py set <key=value> [--project <slug|path>] [--pi-approved]
uv run --with pyyaml python tools/configure.py profile <list|show|diff|apply|save> [<name>]
```

`view` shows effective settings. `set` writes one value to `lab/config.yaml`, or project
`control.yaml` with `--project`, while preserving comments. Researcher-owned keys from
`workflow/rules.yaml → pi_owned_config` require explicit authorization and `--pi-approved`.
The flag records that authorization; it is not permission for an agent to grant itself.
Agent-setting changes re-render role files; `profile` delegates to profile validation.
See [configuration ownership](configuration.md).

### `spawn_project.py` — mechanical project scaffolder

```bash
uv run --with pyyaml python tools/spawn_project.py --slug <slug> --title "<title>" \
  --project-type ml [--domain econ] [--overlay compete] [--run-smoke] [--skip-guard]
```

This tool creates the project scaffold for `/spawn-project`. It:

- Copies `templates/project/` into `<projects_root>/<slug>`, fills placeholders as UTF-8 without a BOM,
  and removes template caches and runtime records. Hub paths use forward slashes so YAML works on Windows.
- Adds the project type, `control.yaml` setting and any selected domain or target-driven overlay.
  It copies `lab/SYSTEM.md` when present.
- Checks that the current study step offers `/spawn-project`, unless `--skip-guard` was supplied.
  It refuses to overwrite a project with commits or a non-empty `runs/` directory.
- With `--run-smoke`, installs the project environment through `uv sync`, runs its smoke test,
  tests and readiness check, then commits only if they all pass.
- Registers the project path with the kernel.

The skill handles the research choices: fill `PLAN.md` from the proposal, set the agreed budgets,
and report the workflow outcome.

### `role_sync.py` — render backend-native subagent role files

```bash
uv run --with pyyaml python tools/role_sync.py render   # write/update generated role files
uv run --with pyyaml python tools/role_sync.py check    # CI drift guard — exit 1 if any is stale
```

One canonical source per subagent role in `agent-roles/` (`<name>.yaml` metadata + `<name>.md` instruction body) renders Claude, Codex and opencode role files in the hub and project template. The five named roles are `fresh-context-reviewer`, `experiment-runner`, `overseer`, `ideation-critic` and `scoping-advocate`. Critics and advocates share the configured critic model/effort keys. Claude resolves model/effort through the Lab's tiers; Codex uses its role settings and supported effort; opencode inherits its session model. Native availability depends on the installed harness. Gemini CLI and Cursor remain compatibility-only until their role-file schemas have a CLI smoke check; use sequential role approximation or an executor run per unit of work. `resolve <role>` prints a configured model/effort for callers that need an explicit binding. `check` detects generated-file drift; edit `agent-roles/`, then render.

### `executor_cli.py` — headless procedure runs (the dashboard's engine)

```bash
uv run --with pyyaml python tools/executor_cli.py enqueue --skill <name> [--target <slug>] [--args "..."] \
    [--backend claude|codex|opencode|acp] [--preset <id>] [--chain off|next|loop] [--repeat-minutes N] [--wait]
uv run --with pyyaml python tools/executor_cli.py enqueue --prompt-file brief.md [--target <slug>]
uv run --with pyyaml python tools/executor_cli.py serve | tick | list | show <run> | attention | health | skills
uv run --with pyyaml python tools/executor_cli.py answer <run> --pick "<question>=<label>" | --text "..."
uv run --with pyyaml python tools/executor_cli.py reply <run> --text "..." | resume | stop | cancel <run>
```

Runs a launchable Lab procedure (`skills` lists them), or an explicit free-form instruction, as a headless
agent session in a detached supervisor (`tools/executor/`): queued → started by the scheduler under
the caps → live transcript + manifest + `lab/.bus/runs.jsonl` ledger → waiting on a PI question and
resumed on the answer (same session). A `run_report` footer supplies `next`, `needs_pi` and
`summary`; a missing footer falls back to the last message. Workflow completion still requires an
accepted kernel outcome, independently of process success. PI-owned, off by default (`agents.programmatic.enabled`); every checkpoint still binds, and a
run that reaches an unapproved one stops with `needs_pi=<checkpoint id>`. The dashboard's task launcher, assistant, gate reviewers and visual-summary agents use this same
engine. `show <run> --files` includes available record paths; `evidence <run>` inspects evidence and
`explain <run>` requests a visual summary. See [Autonomy](autonomy.md#headless-runs-the-executor) and
[Recovering interrupted work](recovering-work.md).

A step's procedure is refused for a study that is not at that step. For example, `/finalize` waits
until the study has passed its final checkpoint when the workflow defines one.

`task_completion.py` marks a completed formally assigned run **Task unfinished** when its ordered
step or exact graph task visit still lacks an accepted outcome. It never guesses that from prose.
A recognized usage-limit error holds that backend's queue; it does not automatically retry an
ordinary failed run. Approved campaigns have separate bounded recovery.

### `signature_guard.py` — protect approval records (a hook, not a command)

A check installed through native tool hooks: Claude's per-run settings, Codex
`-c hooks` flags, and an opencode plugin via `OPENCODE_CONFIG_DIR`. ACP client file writes and
terminal commands call it too; an ACP agent's private tools are outside that client boundary.
It reads one hook payload on
stdin and exits **2** (the reason on stderr) when an edit tool would write something only the PI may
change:

- the PI's records: `lab/journal.jsonl` (moves and approvals), `lab/REGISTRY.md` (written from it), the
  checkpoints' check results, the campaigns' state, which panel collectors may run, the PI-action log;
- an artifact's `reply.json` or `seen` (only the dashboard writes them);
- `lab/config.yaml` (except in `/setup-lab` and `/configure`);
- the lab's definition: `workflow/`, the skills, the roles, `checks/` and `extensions/` always, plus
  the manuals, templates, the PI's instructions, rooms and panels (`protected_paths` in
  `workflow/rules.yaml`); an agent proposes a change with `arlo propose` instead;
- and a shell command that runs `arlo approve|revoke|changes|approve-collector|ack`, `tools/new.py` or
  `--skip-guard`.

The list lives in `tools/kernel/rules.py`. It is an early warning, not an OS sandbox: an agent can run code,
so what holds is checked from outside — the kernel refuses the PI's verbs inside a run and counts only
approvals it signed, each attempt's supervisor flags a change to the lab's definition (holding the lab), and
the run digest flags observed changes outside the allowed paths. If the guard itself fails, it allows the
call and raises a flag. Denials are logged to the run's `permissions.jsonl`. See
[Monitoring](monitoring.md#the-protections).

### `lab_profile.py` — this lab's half of running agents

A library the executor (`tools/executor/`) reads: what may be launched (the skills' frontmatter), the
standing instructions and brief every headless run gets, refusing a step's procedure for a study that
isn't at that step, the campaign brief, queuing the next step's procedure after a study moves, and the
hooks a run carries (the signature guard, the tracer, the bus). A different kind of lab replaces this file.

### `hub_writeback.py` · `process_writebacks.py` — project → hub write-back

```bash
uv run --with pyyaml python <hub>/tools/hub_writeback.py --slug <slug> [--notebook "…"] [--finding "…"]     [--failure "…"] [--question "…"] [--outcome <outcome>] [--evidence "…"]
uv run --with pyyaml python tools/process_writebacks.py [--apply]
```

`hub_writeback.py` is hard rule 11 as one call from a project session: a dated `lab/notebook/` entry,
durable insights promoted to `lab/knowledge/`, and, with `--outcome`, the study's outcome reported to the
kernel (as `arlo move`). When the hub is unreachable a project appends a `HUB-WRITEBACK-PENDING:` block
to its `EXPERIMENT_LOG.md` instead; `process_writebacks.py --apply` applies those later, once each.

### `lab_bus.py` · `trace_hook.py` — the event bus and the activity tracer

```bash
uv run python tools/lab_bus.py emit|inbox|ack|escalate …
uv run python tools/lab_bus.py emit run_report --data next="…" --data needs_pi=none|<checkpoint id> --data summary="…"
```

`lab_bus.py` appends signals to `lab/.bus/` (or a project's `.bus/`) for the dashboard, reads the PI's
directives, and carries a headless run's `run_report` footer. `trace_hook.py` is a hook that appends one
line per tool call to a per-worker log. Both are best-effort and never block: they are not ledgers.
Spawned projects carry copies (`scripts/lab_bus.py`, `scripts/trace_hook.py`).

### `artifact.py` — show the PI something

```bash
uv run --with pyyaml python tools/artifact.py publish --title "Pilot results" --file analysis/pilot.md [--study <slug>] [--note "…"]
uv run --with pyyaml python tools/artifact.py publish --title "Which eval set?" --question "Freeze A or B?" --choices "A;B"
uv run --with pyyaml python tools/artifact.py replies [--id <artifact>] [--run <run_id>]
uv run --with pyyaml python tools/artifact.py list [--study <slug>]
```

Publishes something an agent made for the PI to look at to **Library → Outputs**: `.md`
(rendered), `.html` (sandboxed), an image, a `.pdf`, a `.csv`/`.tsv` table or text; or, with no file, a
question alone. A `--question` (with `--choices`, `;`-separated) waits in the **Inbox**. The PI's reply
goes to the publishing run as its next message, or, if that run cannot accept it, becomes a directive
for the study's next agent (or the Lab inbox for a Lab-wide output);
`replies` prints what the PI answered (JSON lines). Stored in `lab/.bus/artifacts/<id>/`; the run, its
procedure and its study come from `$ARLOTOPE_RUN_ID` / `$ARLOTOPE_RUN_SKILL` / `$ARLOTOPE_RUN_SUBJECT`.
Publishing asks for a look; it never approves anything. `--about <run>[:<subagent>]` associates a
visual explanation with the run it describes. The list API filters by study/run before paging; remote
publication and replies are forwarded through the owning Lab. See [The dashboard](dashboard.md).

### `new_lab.py` — optional local Lab copy

```bash
uv run --with pyyaml python tools/new_lab.py <dest> [--name "My lab"] [--projects-root ../my-lab-projects]
```

Normal installation uses `git clone`. The dashboard's *Create a new lab* offers a separate local copy:

- copies this checkout's committed files (`git archive HEAD`);
- empties the journal (and the registry written from it), the knowledge base, the notebook and `studies/`;
- sets `lab.name` and `lab.projects_root`;
- runs `git init` and makes the first commit.

### `terminal.py` — a terminal window for a CLI's own sign-in or install

```bash
uv run --with pyyaml python tools/terminal.py login claude     # opens a window running `claude auth login`
uv run --with pyyaml python tools/terminal.py install codex
```

This CLI helper opens a visible console (Windows Command Prompt, macOS Terminal, or a Linux terminal
emulator) running a fixed command per backend. Sign in through the CLI's own flow. The dashboard can
instead use a browser terminal on a remote or headless controller; that terminal's input and output
pass through the server. SSH connection prompts use their native SSH window. See
[machines and sign-in](compute.md#connect-a-project-machine).

### `arlo.py` (repo root) — start the dashboard

```bash
uv run --with pyyaml python arlo.py [--hub <lab>] [--port N] [--no-browser]
```

It starts `dashboard/serve.py` for the lab and opens the browser. On a machine you reached over SSH
(or with no display) it prints the `ssh -N -L …` line to use from your own computer instead.
`--background` detaches it, so it outlives your SSH session; `--status` and `--stop` manage it, and
`--json` makes the output machine-readable. If the dashboard is already running
for that lab it just opens the browser, and if 8787 is busy it picks the next free port. The
double-click launchers (`Start ARLOtope.cmd`, `start-arlotope.command`, `start-arlotope.sh`) run it.

### `system_probe.py` — what this machine offers

```bash
uv run --with pyyaml python tools/system_probe.py [--hub <lab>]
```

It prints JSON: CPUs, memory, GPUs, disk, schedulers (SLURM with its partitions and accounts, PBS, LSF),
environment modules and tools, plus a suggested `compute.scheduler`. The dashboard's Settings → This machine &
compute runs it on the lab's machine. See [Machines & compute](compute.md).

### `run.py` — the single entry point

```bash
uv run python scripts/run.py --config configs/experiments/exp-004.yaml [--seed N] [-o key=value ...]
```

Loads the layered config, seeds everything, creates `runs/<run_id>/` (resolved config + git SHA + seed + metrics), appends to `registry.jsonl`. The run's `budget.max_minutes` is recorded in `meta.json`; through a job scheduler it becomes the job's time limit. run.py does not stop a run at its budget: budgets are what agents plan by, and the Compute panel flags a run that goes well past its budget.

### `sweep.py` — multi-seed / grid launcher

```bash
uv run python scripts/sweep.py --config <exp.yaml> --seeds 0,1,2 [--grid k=v1,v2 ...] [--parallel N]
```

One `run.py` subprocess per (combo × seed); a job that dies without finishing is recorded as failed. Ends with a mean ± std markdown table per combo, pasteable into the ledger. This is how the multi-seed rule (`experiment.multi_seed_n`) gets satisfied in one command.

### `compare.py` — query the run record

```bash
uv run python scripts/compare.py best --metric val_loss --minimize
uv run python scripts/compare.py seeds --metric val_loss
uv run python scripts/compare.py experiments exp-003 exp-004 --metric val_loss
uv run python scripts/compare.py list --last 20
```

Reads only `runs/registry.jsonl`; markdown output with seed-aggregated mean ± std and deltas.

### `figures.py` — the paper-grade figure & table library (`src/project_pkg/`)

Not a CLI — the module every `scripts/figures/` script imports, for shared figure dimensions, styling and artifact readers:

- `new_fig(width="single"|"double")` — axes at **final printed width** (3.3 in / 6.9 in), warm-free venue-neutral style: vector PDF, TrueType fonts (`fonttype 42` — Type 3 fails camera-ready checks), 7–8 pt labels, Okabe-Ito colorblind-safe cycle, constrained layout.
- `save_fig(fig, name, consumed_runs=[...])` — PDF + review PNG, printing the run ids consumed (provenance for `claims.yaml`).
- `load_registry()` / `metric_curve(run_id, metric)` / `seed_stats(rows, metric)` — artifact access; headline comparisons must go through `seed_stats`.
- `format_measurement(mean, std, n)` — sig-fig discipline (std to 2 sig figs, mean to match: `71.28 ± 0.39`).
- `emit_table(headers, rows, path)` — booktabs `.tex` files the paper `\input`s, to generate result tables directly from recorded measurements.

`/make-figures` orchestrates these per paper; matplotlib is imported lazily (add it to the project's pyproject when plotting starts).

### `status.py` — run monitor { #statuspy-zero-token-run-monitor }

```bash
uv run python scripts/status.py [<run_id>] [--log-interval 60]
```

One line: `alive | stalled | done | failed | timeout · elapsed/budget · last metric`. The lightweight check used while a run is in flight — liveness from `meta.json` + `metrics.jsonl` mtime, no log dumps, no judgment about partial curves. Exit 3 on `stalled` (two in a row → treat the run as failed).

### `check_project.py` — readiness lint + orientation

```bash
uv run --with pyyaml python scripts/check_project.py
```

The project-side analogue of `check_lab.py`: required files present, no unfilled template placeholders, `control.yaml` parses (with a budgets block), `registry.jsonl` readable — then an orientation block regardless: runs recorded, last run + status, compute spent vs `budgets.total_minutes`, SYSTEM.md present or not, and a **suggested next procedure**. Exit 0 ready, 1 not. Run it on any fresh clone, after `/spawn-project`, or whenever an agent cold-starts in the project directory.

## Design note

The Python executor owns deterministic scheduling and records; procedures supply the agent's
research instructions. These tools share file contracts instead of requiring a database service or
an additional model SDK. A helper may print Markdown or structured JSON depending on its caller.

## `upgrade_project.py` — bring spawned projects up to date

A project is a snapshot of `templates/project/` at spawn, so later improvements to agent tracing never reach it on
their own. This copies only the template-owned plumbing — `scripts/trace_hook.py`, `scripts/lab_bus.py`, the
`hooks` block of `.claude/settings.json` (permissions untouched), `.codex/hooks.json`, the opencode tracer plugin
and the role files — never research content. Idempotent; it does not commit.

```bash
uv run --with pyyaml python tools/upgrade_project.py --all --check   # report stale files (exit 1 if any)
uv run --with pyyaml python tools/upgrade_project.py --all           # or: <slug> [<slug>…]
```
