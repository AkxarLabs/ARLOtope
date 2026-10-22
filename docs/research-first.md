# Research-first Lab

Newts' Lab keeps a research question, its evidence and its decisions together while agents work with your existing tools. Start with a study rather than configuring a complete paper pipeline.

For the first-run walkthrough, use [Getting started](getting-started.md). This page explains how the pieces fit.

## A study is the unit of work

A study has a title, question, workflow and durable record under `studies/<slug>/`. It may attach an existing project or begin without one. Attached projects retain their own code, environment and runner; attachment adds Lab identity files and does not certify their results.

Creating a study records a starting point. Launching an agent is a separate action. A task can be as small as inspecting a repository or clarifying a hypothesis. Research procedures provide more structure when you need literature review, experiments, analysis or a paper.

Terminal users can create the same lightweight study:

```bash
uv run --with pyyaml python tools/research_start.py --title "Replication study" \
  --question "Which assumptions explain the published result?" --local /absolute/path/to/project
```

Omit `--local` for a question-only study, or use `--repo owner/repository` for a public clone. `--workflow` selects a process and `--slug` selects an ID. The dashboard can also clone private repositories through the connected GitHub account. Existing private checkouts can be attached without cloning again.

## Keep method, execution and decisions distinct

| Piece | What it controls |
|---|---|
| Task | The work requested and its expected output |
| Procedure or skill | Reusable instructions for doing that work |
| Role | Working instructions such as analyst, writer or reviewer |
| Agent preset | A configured harness and optional model/effort |
| Context | A fresh, continued or forked conversation |
| Checkpoint | Whether a particular transition or kind of work is authorized |
| Room | Where tasks appear in the visual Lab |

A different avatar or room does not change authority. A successful process exit does not prove that an experiment succeeded. A reviewer's recommendation is evidence for a decision, not a researcher-only approval.

## Evidence stays accessible

**Library** brings together outputs, documents and retained records without moving every project file into a new database. Notes are separate files; saved Q&A does not edit the document being discussed. Reports and figures should point to the underlying evidence. Negative and failed attempts belong in the record too.

Agents use their normal shell, file and research tools. Local and remote evidence may have different availability. A summary should disclose missing, clipped or stale records rather than suggest access to private model state.

## Add structure when it helps

Use **Workflow** to adapt tasks, routes and checkpoints. Shared changes stay in a draft until reviewed and published. Per-study instructions and agent preferences let a study differ without changing every other study.

Budgets, autonomous campaigns, native subagents and remote compute remain explicit choices. Workflow checks govern official progression and supported launches; native tool actions also depend on the harness's permissions. The Lab does not provide a universal operating-system sandbox.

See [workflow concepts and files](workflow.md), [tasks and agents](agent-workflows.md), [knowledge records](knowledge.md) and [publishing outputs](artifacts.md).
