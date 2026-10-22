# Autonomy and running agents

Choose how much work to delegate. The workflow, its checkpoints and the research rules still apply
at every pace. Start with **New study**; `/setup-lab` is an optional configuration interview, not a
prerequisite.

| Pace | What you ask for | Where it stops |
|---|---|---|
| One procedure | `/ideate`, `/lit-review`, `/analyze`, or another procedure | At that procedure's result or a question |
| One workflow step | `/advance <study>` | After the next step, with evidence to review |
| Several workflow steps | Enable following steps when launching | At a checkpoint, question, failure or chain cap |
| A project loop | `/research-loop <study>` with an approved brief | At its budget, stop condition or a checkpoint |
| A portfolio | `/autopilot` with an approved campaign brief | At the campaign's limits, a pause or completion |

A process finishing is separate from a workflow step finishing. The agent must report an accepted
outcome through the kernel. See [Recovering interrupted work](recovering-work.md) for **Task unfinished**,
usage limits and resuming a conversation.

## Step by step: `/advance`

`arlotope next <study>` identifies the next procedure. `/advance <study>` runs one step and stops with
what changed, evidence to inspect and what would happen next. An outcome such as `more-experiments`
can route back to an earlier step; that work is the next invocation.

The dashboard uses the same engine. Ordered workflows can follow their next step automatically.
Graph workflows can start ready tasks, including parallel branches, using their connection and
context settings. Neither treats an ordinary turn ending as a workflow outcome.

## Project loop: `execute` vs `explore`

`/research-loop` follows a project's `LOOP_BRIEF.md`, `PLAN.md` and `control.yaml`. The default research
workflow requires the `approve-loop` checkpoint before an unattended loop. A custom workflow defines
its own checkpoints.

- **`execute`** follows the approved experiment plan, including planned ablations and confirmation,
  then stops when the plan is exhausted.
- **`explore`** can reopen supporting decisions when their written `Revisit if:` triggers are met.
  With an expansion allowance, it can also add results-grounded experiment lines with success
  criteria written before running them.

The brief's `Mode:` selects the mode. `loop.explore_max_expansion_rounds` defaults to `0`, so changing
the mode alone does not authorize frontier expansion. To allow it, the PI also changes that cap in
`control.yaml`, for example:

```text
/configure <study> set loop.explore_max_expansion_rounds=2
```

The evaluation set, seeds, budgets and kill criteria remain frozen. A decision marked `Headline: yes`
in `studies/<study>/decisions.md` needs escalation when reopening it changes the proposal's central
claim. Changing the headline is not ordinary experiment iteration.

`/ideate --in-project <study>` is the separate procedure for proposing a new approach within a
project. `ideation.in_project` enables it; `ideation.in_project_approval` controls approval. Surviving
approaches return through proposal review or become a successor study. A campaign can delegate only
what its approved brief and the workflow allow. See [Configuration](configuration.md).

## Campaigns

`/autopilot` helps write a campaign brief: direction, studies in flight, budgets, deadline and any
delegated checkpoints. Approving the brief authorizes that campaign, not arbitrary future work.

The deterministic campaign keeper runs scheduling passes and dispatches procedures as ordinary
executor runs. It checks membership, waiting studies, duplicate work, procedure eligibility and
parallelism before launching. A study waiting for the PI does not stop other campaign studies.

Campaign recovery has two distinct parts:

| What ended | What the keeper does |
|---|---|
| A dispatched task timed out | Retry the same resumable run after 30 seconds, within the retry cap |
| A dispatched task hit a recognized usage limit | Retry after the parsed reset, or a 30-minute fallback, plus 2 minutes |
| A dispatched task hit a recognized transient error | Retry with increasing backoff |
| A dispatched task failed for another reason | Leave it for inspection; it is not a generic automatic retry |
| A scheduling pass timed out | Schedule another pass after 1 minute |
| A scheduling pass hit a usage limit | Wait for the reset or fallback, plus 2 minutes |
| A scheduling pass needs sign-in or a missing CLI | Pause the campaign |

Dispatched-task retries require a saved session and allow at most **three retries**. The transient
backoff sequence is 2, 5, 15, 30 and 60 minutes; the task retry cap limits how far a task reaches in
that sequence. A campaign also stops or stalls at its configured bounds. Retrying an agent does not
raise an experiment's approved compute budget.

Campaign runs deny new backend permission requests immediately. For an unanswered structured
multiple-choice question, the live transport can take the first option after
`live.campaign_question_minutes` (30 by default) and record it as **Assumed**. Agents are instructed to
put their recommendation first; this is not a separate judgment model. Questions without usable
options, including ACP forms, remain unanswered and can be parked. These answers never grant a
workflow approval.

## The authorization model

Checkpoints belong to a workflow; they can be changed or removed through the normal definition
review process. A checkpoint's approver determines who can decide it:

| Approver | How a decision is recorded |
|---|---|
| `me` | The PI decides in the dashboard or with `arlotope approve` |
| `me-or-campaign` | The PI, or a keeper acting within an approved campaign's delegated bounds |
| `auto` | The engine applies the checkpoint's configured checks |
| `agent` | An independent gate reviewer returns a validated decision; configured checks still apply |

An approval is a journal record. A working agent cannot approve its own task. A note, artifact reply,
chat message or read receipt does not grant approval. The kernel holds movement at unapproved
`before` checkpoints. `during` checkpoints require the agent to check before the named work; watches
can flag violations afterwards. See [Monitoring and guardrails](monitoring.md) for these limits.

![A checkpoint and its evidence](assets/current/checkpoint.webp)

## Headless runs (the executor)

The executor runs a launchable procedure or a free-form instruction using **Claude, Codex, opencode
or an ACP agent**. Enable launching in **Settings → Limits & permissions**, then select installed
agents in **Settings → Agents & models**. ACP support depends on capabilities the agent negotiates;
it does not make every CLI feature interchangeable.

![Agent limits and permissions](assets/current/settings-limits.webp)

```bash
uv run --with pyyaml python tools/executor_cli.py enqueue --skill propose --target my-study
uv run --with pyyaml python tools/executor_cli.py enqueue --prompt-file brief.md --target my-study
uv run --with pyyaml python tools/executor_cli.py serve
uv run --with pyyaml python tools/executor_cli.py list
uv run --with pyyaml python tools/executor_cli.py show <run>
uv run --with pyyaml python tools/executor_cli.py reply <run> --text "Continue with the smaller example."
uv run --with pyyaml python tools/executor_cli.py resume <run>
```

Each run has a detached supervisor, durable manifest, transcript and action history. A dashboard
reload does not restart the conversation. The scheduler enforces launch concurrency, per-run time
allowances and daily launch brakes. Training concurrency and experiment compute budgets are separate
research controls; see [Machines and compute](compute.md).

Live transports deliver messages, questions and permissions to a running agent. If a native live
transport fails at startup, the supervisor can retry one-shot. ACP is live-only. One-shot agents
cannot offer the same interactive approval channel. A completed free-form conversation shows
**Your turn**; a completed assigned task with no accepted outcome shows **Task unfinished**.
The Lab does not invent a question from the agent's prose.

The supervisor deducts elapsed attempt time when resuming a run, with a minimum of five minutes for
an attempt. Campaign retries grant their configured agent-time allowance. These are agent process
limits, not experiment budget changes or an estimate of model-provider billing.

Checkpoints, context ownership and current study state are rechecked when work starts. A continued
session has one active owner. A fresh agent receives a new session; a fork copies context only where
the backend supports it. A portable handoff passes selected instructions and evidence rather than
pretending to copy hidden conversation state. See [Agent workflows](agent-workflows.md).

## Autonomy inside the project directory

Spawned projects include their own `AGENTS.md`, backend role files, procedures and `control.yaml`.
They can be used from a terminal without keeping a hub conversation open. Attached repositories
retain their existing structure; attachment does not impose the spawned-project scaffold.

An optional PI-owned `SYSTEM.md` records machine conventions, data locations and local restrictions.
It supplies instructions, not an operating-system sandbox. Project write-backs can be reconciled
when the owning Lab is reachable again. Human notes are shared context, not a queue of work.

## Research checks

Autonomy does not verify a scientific claim. The research procedures require traceable run
artifacts, staged experiments, selection discipline and evidence-based responses to reviews.
Independent reviewers and overseers check assigned evidence; they do not replace reproducible
results or the PI's judgment. See [Research workflow limits](research-limits.md).
