---
name: design
description: Draft a research workflow or procedure change for the researcher to review and publish.
arlotope:
  kind: utility
  level: hub
  mode: headless
  args: text
  launchable: true
  writes: ["lab/.bus/designs/workflow/**"]
  hint: the workflow or procedure change you want
  title: Adapt a workflow
  does: Drafts changes to research steps, procedures and checkpoints for review.
  stops: with a validated proposal waiting under Workflow
  ui: {where: none}
---

# Adapt a workflow

Use the harness's ordinary file, shell, browser and research tools. Produce a proposal; the PI reviews
and publishes it through **Workflow**.

1. Read the request, relevant `workflow/` definitions and skills, plus `docs/agent-workflows.md`
   and `docs/skills.md`. Read tags, room design or external-framework docs only when needed.
   Ask only for missing decisions that affect the result.
2. Create `lab/.bus/designs/workflow/<short-unique-id>/`. Save `request.md` and concise `notes.md`.
   Place complete replacement files at their original relative paths inside this folder, such as
   `workflow/workflows/replication.yaml` or `.claude/skills/replicate/SKILL.md`.
3. Use the existing declarative structure:
   - Tasks define skills or instructions, outputs and an agent role. No research stage is mandatory.
     Reusable methods belong in skills; task-specific context belongs in node instructions.
   - Connections order execution. `join: true` waits for parallel inputs; alternative routes do not
     need that join. Named `outcomes` replace `next` for that decision; bound loops where appropriate.
   - Context is separate: `fresh` starts a conversation, optional `handoff` supplies a summary;
     `continue` resumes one source; `native-fork` copies one source into a separate session.
     A fresh handoff may use multiple `from` sources. A self-source needs `initial: fresh`.
     Independent reviewers start fresh without the author's summary, using declared evidence.
   - Checkpoints declare their approver, evidence and routes. Agent gates use `approver: agent`
     with a judge skill/rubric and named `decisions`. Preserve existing approvals unless the request
     changes them; never invent approval records.
   - Rooms group tasks visually across workflows and studies; they do not determine execution.
     New room resources use their own private room draft and preview.
   - Leave `agent.preset` unset to inherit role defaults, or use a saved preset. Do not invent model
     IDs, install harnesses or change agent settings as part of a workflow proposal.
4. Preserve unrelated definitions. Imported skills need no `arlotope` block: retain their body,
   resources and license. Project-local skills take precedence; runs save exact copies.
   Use node `skills` for several methods in one conversation. Optional `arlotope.ui.task`
   (`{label: "Collect evidence", role: analyst}`) offers a task starting point; tags only organize.
   External frameworks use `workflow/frameworks/<id>.yaml` and node `external` phase declarations,
   with project inputs/budgets in `.arlotope/frameworks.yaml`; do not add another scheduler.
5. Run `uv run --with pyyaml python arlo.py check --design <folder>`. Fix errors and explain any
   changed checkpoint. Return the folder path and a short account of the proposed behavior.

Write only in this proposal folder. Do not change live definitions, approvals, code or another
proposal, launch research, move studies or apply the design. The normal harness permissions apply;
this write scope is not an OS sandbox.
