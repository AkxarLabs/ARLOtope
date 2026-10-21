# Customize your research process

Open **Workflow** to adapt how work is done. Begin with a copy of a nearby workflow if you want a reusable variation; use study-specific instructions when only one study should differ.

If a definition or instruction cannot be read, choose **Retry**. A failed read does not create an empty editable instruction. Existing unsaved text stays in the editor during a retry; saving is unavailable until the definition has loaded.

## Choose the smallest edit

| Need | Edit |
|---|---|
| Add context for one study | Study **Instructions** |
| Change an individual task's goal or output | Task inspector |
| Reuse a method in several tasks | Procedure/skill or its variant |
| Use another agent or model | [Agent choices](agent-workflows.md#choose-agents) |
| Return a review to writing | Named outcome and destination |
| Require a decision before costly work | Checkpoint |
| Change where work appears | Room grouping or [room design](room-design.md) |
| Leave context without starting work | [Add note](knowledge.md#add-a-human-note) |

## Edit a shared workflow

1. Select the workflow. Use **Make a copy** for a separate version or **New workflow** for a new starting point.
2. Select a task in **Flow**. Edit its skill, instructions, role, agent, context and expected files.
3. Under **Connections & loops**, set destinations, named outcomes, joins and a pass limit if needed.
4. Open a checkpoint diamond or **+ Checkpoint** to edit when work waits, its reviewer, evidence and checks.
5. **Save workflow draft**. Then use **Review & publish** to inspect validation problems, changed files and affected studies before publication.

![Selecting and editing a task in the workflow](assets/current/workflow-task.webp)

*Demonstration fixture: task edits belong to the shared draft until publication.*

Shared changes are not installed by an agent's recommendation. Review the publication summary, especially changes that loosen a checkpoint. **Change history** can undo the latest publication when it does not conflict with later edits.

If a changed file's comparison cannot load, its row shows **Retry** rather than an empty diff.
Reloading a comparison does not edit or publish the draft.

## Ask an agent to propose an edit

Expand **Describe a change to an agent** and explain the method or process you want. The ordinary agent writes a proposal under `lab/.bus/designs/workflow/`. Inspect the proposal and take it into the shared draft, then review and publish. The proposing agent does not publish its own definition.

For a single study, its **Instructions** tab saves additional step or procedure guidance in `studies/<slug>/workflow/`. Removing that local guidance restores the Lab's instructions. A study can also choose an existing procedure variant without changing other studies.

If an instruction sheet cannot load, choose **Retry**; it does not open an empty editor over unread instructions. An agent's suggested instruction change shows its comparison only after both the suggestion and current instructions load. **Accept** waits for that comparison; **Decline** remains available when the suggestion itself has loaded.

## Edit the files directly

The UI uses readable files: `workflow/steps.yaml`, `workflow/workflows/*.yaml`, procedure `SKILL.md` files and `lab/workflow/` overlays. After direct edits, run:

```bash
uv run --with pyyaml python newts.py check
```

Use the dashboard draft path when you want a reviewable publication. Roles, rules, checks, templates and research instruments are under **Advanced**. See [workflow file reference](workflow.md) for formats and [extending the Lab](extending.md) for larger additions.
