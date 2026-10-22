# Newts' Lab

A local research workspace for scientists working with coding agents. Bring a question or an existing
project, work with your own tools, and keep a clear record of methods, evidence and decisions.

Licensed under [AGPL-3.0-only](LICENSE). Commercial use is allowed, with the license's source-sharing
requirements. Reusable templates retain MIT terms; third-party components retain their own licenses.
See [licensing](docs/licensing.md).

![Newts’ Lab visual workspace](docs/assets/current/lab-light.webp)

*Current interface with demonstration data.*

## Start

Install [uv](https://docs.astral.sh/uv/) and Git, then clone this repository or use it as a template.
Double-click **Start Newts Lab.cmd** on Windows or **start-newts.command** on macOS, or run:

```bash
uv run --with pyyaml python newts.py
```

The local dashboard opens in your browser. **New study** guides you through:

1. A research question, an existing project on this or a connected machine, or a GitHub `owner/repository`. Private repositories use the connected GitHub account.
2. A research goal and workflow. Optionally upload a brief or supporting files and ask an agent to suggest details.
3. Review, then create the study. A GitHub clone downloads source without installing or running it.

Attach existing work without moving files, replacing its package manager, or adding a new runner.
Connect Claude Code, Codex, opencode or an [ACP agent](docs/acp.md) when you want an agent's help.
Use the CLI's own sign-in. Projects can stay on [remote machines](docs/remote-projects.md) without
installing another full Lab there.
Creating a study does not start an agent or approve a checkpoint.
Use **Browse** to choose project folders. Uploaded materials stay with the study and are available to its agents.
**Library → Notes & sources** keeps human notes, saved workspace answers and retained papers with
each study. Notes do not queue work; their optional acknowledgement records that an agent read them.
See [study knowledge](docs/knowledge.md).

## Research, your way

- **Explore and plan:** discuss topics, review literature, define hypotheses and plan a study.
- **Work in existing projects:** inspect code, run requested tasks and add structured experiment
  tracking when useful. New projects can use reproducible templates.
- **Analyze and communicate:** link results to evidence, generate figures, draft and review papers.
- **Adapt the process:** add or reorder steps, edit procedures, and configure your own checkpoints.
  Shared edits stay in a draft until you review and publish them.
- **Stay in control:** inspect agent conversations, answer questions, review evidence, pause or stop
  work, and choose budgets and permissions. Background loops and campaigns are optional.
- **Use research compute:** local commands, SSH, Slurm and custom schedulers remain available.

The visual lab is the primary workspace, with a restrained light/dark interface and three agent
avatars: newt, scientist and robot. Compose workflows, assign agents, group tasks into rooms and
refine a room through a small prompt/preview/apply flow.
See [tasks, agents and rooms](docs/agent-workflows.md).

Use **Library → Outputs → Ask for a visual summary**, or **Visual summary** on a run, to review recorded work
as an interactive page. [Published outputs](docs/artifacts.md) stay linked to their study and agent;
feedback goes back to that conversation.

## Plain files, small machinery

Procedures are Markdown skills; workflows and checkpoints are YAML; study history is an append-only
journal. Code and experiments stay in project repositories, which may live anywhere. The visual
dashboard needs no frontend build. Agents can also read `AGENTS.md` and follow procedures directly;
the CLI and executor are available independently.

```bash
# Attach a repository without scaffolding it
uv run --with pyyaml python tools/research_start.py --title "My study" \
  --question "What would I like to understand?" --local /absolute/path/to/project

# Inspect the lab from a terminal
uv run --with pyyaml python newts.py status
```

For an agent session, start your installed harness in the lab and use `/discuss`, `/ideate`, `/adopt`
or another procedure. Procedures live in `.claude/skills/` and are readable across harnesses. Native
integration differs by backend; see [the operating manual](AGENTS.md).

## Interrupted work

An agent turn ending does not complete a workflow task. The workflow advances only after an
accepted outcome. Quota failures, crashes and unanswered questions remain visible; an assigned
step with no outcome is marked unfinished. Resume the saved session or start a new agent with a
handoff. See [recovery](docs/recovering-work.md) for limits, retries and what is preserved.

## Documentation

[Public beta candidate notes](RELEASE_NOTES.md) describe the included features and known limits.

[Getting started](docs/getting-started.md) · [Research-first tour](docs/research-first.md) ·
[Customizing research](docs/customising.md) · [Workflow format](docs/workflow.md) ·
[Configuration](docs/configuration.md) · [Compute](docs/compute.md) ·
[Background work](docs/autonomy.md) · [Notes & sources](docs/knowledge.md) · [Contributing](CONTRIBUTING.md)

The [documentation website](https://akxarlabs.github.io/newts-lab/) is built from `docs/` with
`properdocs.yml`. Historical implementation plans stay in the repository and are excluded from the
public site. Build it locally with `uv run --with properdocs --with mkdocs-material properdocs build --strict`.

The Lab preserves evidence provenance and explicit approvals. Workflow controls govern official
progression; native tool actions also depend on the agent harness's permissions.
