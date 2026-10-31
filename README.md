<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/arlotope-wordmark-dark.svg">
  <img src="docs/assets/brand/arlotope-wordmark.svg" alt="ARLOtope" width="480">
</picture>

**Visually manage agent teams across your research projects.**

Move several research projects forward at once. Build workflows, assign teams, and follow your
agents in a shared 3D lab. See who is working, where your input is needed, and what each project
has produced—all while keeping your existing repositories and tools.

[Documentation](https://akxarlabs.github.io/ARLOtope/) ·
[Install](docs/install.md) ·
[First study](docs/getting-started.md) · [Build a workflow](docs/agent-workflows.md)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/current/lab-dark.webp">
  <img src="docs/assets/current/lab-light.webp" alt="The visual lab with agents working in shared research rooms">
</picture>

*Dashboard with demonstration studies.*

## What you can do

- **Work across projects.** Run studies side by side, with separate workflows and records. Switch focus without stopping other teams.
- **Use your own agents.** Claude Code, Codex, opencode and compatible [ACP agents](docs/acp.md). Use your accounts or [API keys](docs/api-providers.md), including OpenRouter.
- **Build your process.** Connect tasks, reuse Markdown skills, run parallel agents, and add loops and review checkpoints. Research workflows are included as starting points.
- **See what is happening.** Follow characters between rooms, inspect conversations, and answer questions from one Inbox.
- **Keep a research record.** Each study brings together task history, notes, sources and outputs, including interactive HTML reports.
- **Keep your tools.** Attach existing repositories without replacing their environment or runner. Work locally or over [SSH](docs/remote-projects.md).

## Get started

**Windows** (PowerShell):

```powershell
irm https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.ps1 | iex
```

**macOS and Linux**:

```bash
curl -fsSL https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.sh | sh
```

Then run `arlo` or open the ARLOtope launcher. See [installing](docs/install.md) for where things live,
updating and uninstalling. To work from source instead, install
[Git](https://git-scm.com/downloads) and [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
git clone https://github.com/AkxarLabs/ARLOtope.git
cd ARLOtope
uv run --with pyyaml python arlo.py
```

The dashboard opens in your browser. No frontend build is needed. Works on Windows, macOS and Linux.

1. Connect an installed agent in **Settings → Agents & models** and enable launches in **Limits & permissions**.
2. Choose **New study**. Start with a question, browse to an existing folder, or choose a GitHub repository. Add a brief or other files if useful.
3. Review the workflow, create the study, then start its first task.

Creating a study does not launch an agent. The first-visit ARLO guide shows you around;
reopen it with **?**. See the [first-study walkthrough](docs/getting-started.md) for screenshots.

## Yours to inspect and change

Workflows are YAML, skills are Markdown, and records are plain files. Edit them in the dashboard
or with your own tools. Agent turns and task completion are tracked separately; interrupted work
stays visible for [recovery](docs/recovering-work.md).

Use the same actions from a terminal or agent with [`arlo api`](docs/api.md).

Private Lab records are ignored by Git. Back up `lab/`, `studies/` and your project repositories;
see [storage and backups](docs/projects.md#storage-updates-and-backups).

[Beta notes](RELEASE_NOTES.md) · [Contributing](CONTRIBUTING.md) ·
[AGPL-3.0-only](LICENSE) ([template and third-party terms](docs/licensing.md))
