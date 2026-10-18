---
name: design
description: Draft a research workflow or procedure change for the researcher to review and publish.
newts:
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

Use normal native read, edit, shell and research tools. This is an ordinary agent task, with no
separate model loop, renderer SDK, browser installation or special tool protocol.

1. Read `docs/agent-workflows.md`, `docs/tags.md`, `docs/room-design.md` and `docs/extending.md`, the relevant `workflow/` definitions and existing procedure files.
   Read the PI's request. Ask only for missing decisions that affect the design.
2. Create a new folder `lab/.bus/designs/workflow/<short-unique-id>/` (letters, digits, dashes).
   Write `request.md` with the request and `notes.md` explaining the proposed behavior.
3. Put changed files there at their original relative paths, for example
   `workflow/workflows/replication.yaml` or `.claude/skills/replicate/SKILL.md`.
   A file replaces the corresponding definition in the proposal overlay. Copy complete definitions
   before editing; preserve unrelated steps, checkpoints and procedures. Prefer the existing data
   format and small instruction changes. Task connections control execution; agent context is explicit;
   rooms may group tasks from several workflows after composition. Keep joins explicit and make
   independent review fresh by default, with the author summary off and declared evidence paths supplied.
   `context.mode: continue` resumes the source; `native-fork` copies its conversation into a new session.
   Legacy `fork` means portable handoff; never silently change that meaning. For new independent agents,
   use `mode: fresh` and optional `handoff: true` plus `from` for the summary. Use node `skills` for a
   single conversation following several skills. Named node `outcomes` replace its ordinary `next`
   destinations; `join: true` is for parallel branches, not alternative-route merges. Bound loops with
   `max_visits` where appropriate. Agent gates use `approver: agent`, declared `evidence`, a `judge`
   skill/rubric and `decisions` mapped to `continue`, a task ID or a shelf. Preserve researcher-owned
   default approvals unless the request explicitly changes them. See docs/agent-workflows.md.
   Include role instructions, skills and expected outputs.
   Leave `agent.preset` unset to inherit role defaults, or reference an existing saved preset.
   Do not invent model IDs, install agents or modify Lab/study agent settings in a workflow proposal.
   Context sources may be earlier causal tasks: a revision can continue its writer after an independent
   review. A fresh handoff may select several sources with `from: [task-a, task-b]`; continuation and
   native fork select one. A self-source needs `initial: fresh` for its first loop visit.
   Add optional `tags` to workflows, steps, nodes or procedure `newts` metadata where useful;
   reuse existing labels. Tags organize definitions and their instructions, never grant approvals.
   For necessary room resources, use a separate private room draft and preview it; publication and
   room application remain separate reviewed operations. No new engine code unless separately requested.
4. Validate with `uv run --with pyyaml python newts.py check --design <folder>`.
   Resolve errors; explain any intentionally added, moved or removed checkpoint.
5. Finish with the folder path and a concise explanation. The proposal appears in **Workflow →
   Agent proposals**. Only the PI takes it into the draft, reviews it and publishes it.

Write only inside your proposal folder. Never change the live workflow, procedures, checks, approvals,
application code or another proposal. Do not launch research, move studies or install the proposal.
The normal harness permissions and signature guard apply; this scope is not an OS sandbox.
