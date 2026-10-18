# Tasks, agents and rooms

Use **Workflow** to compose work, choose who performs it and decide which conversation each task uses. The same saved definition appears in **Flow**, **Sequence** and **By room**.

## Edit a task

1. Select a task card in **Flow**. Its inspector opens beside the map, or below it on narrow screens.
2. Give the task a useful name. Choose a **Skill / procedure** or **Own instructions**. A **Skill sequence** supplies several methods within one task.
3. Write **Task instructions** and **Expected output files**. Output paths are relative to the study's working area; keep them specific enough to check.
4. Choose **Run this task as**, an agent choice and **Agent context**.
5. Open **Connections & execution** for destinations, named outcomes, joins, tags and an optional visit limit.
6. **Save composition to draft**, then **Review & publish** the shared change.

![A workflow map with tasks and branches](assets/current/workflow-map.webp)

*Demonstration fixture: connections describe task readiness and routes.*

![A selected task and its editable inspector](assets/current/workflow-task.webp)

*Demonstration fixture: the task's method, agent and context are separate choices.*

**Task starting points** offers Literature, Experiment, Analyze, Independent review and Write. These fill ordinary editable task fields; they do not create a new kind of runner. **Duplicate task** copies an existing task. Changing a role preserves your instructions; choosing Reviewer starts fresh with no author-summary handoff. You can explicitly change that context afterward, but inherited context is not an independent review.

Use the Reviewer role for independent review tasks. Reviewers, explainers and assistants remain
visible and monitored but do not count against the default seven-task capacity. Analyst, writer,
designer and custom task roles count normally. See [capacity](compute.md#agent-slots-and-experiment-jobs).

## Choose agents

Open **Settings → Agents & models → Agent choices** to save named presets. A preset selects a harness and optional model/effort; multiple presets may use one harness. ACP presets can use different compatible commands. Save a preset before **Test**. An executable check or ACP initialization is not proof of authentication or model access; those are checked when a task starts.

![Named agent choices and role preferences](assets/current/agent-presets.webp)

*Demonstration fixture: presets are launch settings, not permanently running agents.*

Choose a Lab default and optional role-specific choices. **New study → Agent choices (optional)** saves study preferences; existing studies expose **Agents**. A general study default preserves inherited specialist choices. **Use study default** on a role deliberately removes that inherited specialization.

For fresh tasks, selection order is:

1. Explicit choice for this launch.
2. Task preset or custom harness settings.
3. Study role setting, then Lab role setting.
4. Study default, then Lab default and the existing machine/backend defaults.

Choose **Use role defaults** for an inherited choice. Changing the role can change that inherited agent; a pinned preset remains pinned. Effort is exposed by the current Claude/Codex adapters. Models depend on the configured harness; do not assume a model identifier works with another provider.

New launches capture their selected options. Editing preferences does not silently change queued/running work. Continued and forked conversations retain their source configuration. A different harness or incompatible model/profile requires a new conversation with handoff. Native child agents use their harness's own role/model facilities; a Lab preset does not make arbitrary internal children cross-provider.

## Choose context

| Inspector choice | Meaning |
|---|---|
| **New conversation** | New native session; optional prior-work handoff |
| **Continue conversation** | Next task in the selected source conversation |
| **Fork conversation** | New native conversation copied from a supported source boundary |

For a new conversation, **Include a summary of prior work** enables handoff; **Evidence from** selects its source tasks. A handoff supplies summaries and evidence links, not hidden model state. It can cross harnesses when the receiving agent can actually access the files.

Continue/fork chooses one **Context from** source. It may be an earlier causal task rather than an immediate predecessor: Draft → Review → Revise can wait for Review while continuing Draft's writer. It cannot select unrelated live work or rewind a session after later work has changed it. Missing, stale or unsupported sources produce an error instead of silently starting fresh. A task can select its previous loop visit with an initial fresh visit.

Only one task can own a continued session at a time. Native fork support depends on the harness/version; ACP requires advertised capabilities. A native fork creates another conversation, not an isolated repository or worktree. Legacy `context.mode: fork` means a portable handoff; native forks use `native-fork`.

## Connect tasks and outcomes

Connections control when tasks become ready. Several ordinary destinations launch parallel branches, subject to execution limits. **Wait for all incoming branches** joins work that must all finish. Leave it off for mutually exclusive outcomes; an all-input join cannot wait for a branch that never ran.

A named outcome replaces the ordinary `done` route. For example, a review can report `revise` to return to writing or `more-experiments` to return to experiments. Set **Maximum task visits** to bound a loop. Rooms only group the display; they do not change these connections.

**Run ready tasks** starts eligible work. Each task visit has an owning run; finishing a branch does not finish other branches. Declared outputs and the task's accepted outcome matter separately from process exit. A task that stops without its outcome remains unfinished. Inspect it, then **Continue task** or use **New agent with handoff** if the original conversation cannot resume.

## Questions, checkpoints and permissions

Native questions and tool permissions appear in the run and Inbox when the adapter exports them. Terminal/editor sessions still receive input in their terminal. A pending question is answered in its producing conversation; the workspace assistant does not answer it by changing focus.

Checkpoints separately govern authorized research progression. They can use the researcher, named checks or an explicitly configured independent judge. Review the evidence and configured decision routes. A new agent choice does not grant approval, and a fresh model alone does not establish reviewer independence.

For checkpoint fields and commands, see [workflow reference](workflow.md). For agents that stop or fail, use the [dashboard recovery controls](dashboard.md#answer-and-recover).

## Rooms and export

Switch to **By room** after composing tasks. Select tasks and **Group in room**, or **Create room & group**. **Design room** opens a separate preview/apply draft; see [room design](room-design.md).

**Download procedure** exports a saved composition as a Markdown skill and ZIP of its local resources. Save edits first. The export describes the workflow; Lab execution is still needed for its recorded gates, parallel tasks and native conversation operations.

For a small process, **New workflow → One lead agent** lets one task follow a skill sequence. Use separate tasks when independent contexts, parallel work or recorded transitions matter.
