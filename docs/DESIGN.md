# Design rationale

Lab connects a research question to agent work, evidence and human decisions. The default interface
is a persistent 3D Lab, with **Studies**, **Library** and **Workflow** for direct access to the same
records. All agents, History, settings and machine connections are secondary views.

## Keep the research model visible

A **study** holds a question and its history. A **project** is its code and evidence repository.
A **workflow** orders tasks or shared steps and defines checkpoints. A task’s **role** supplies
instructions, its **agent preset** chooses the harness/model, and its **context** chooses a fresh,
continued or forked conversation. **Rooms** group tasks visually; they do not change execution order.

![Workflow task map](assets/current/workflow-editor.png)

A run records one task visit or requested piece of work; successive runs may share a backend session.
A successful agent turn does not establish a scientific finding. The interface keeps its evidence,
outcome, unanswered questions and checkpoint state separate.

![Study overview with its next actions and records](assets/current/study-overview.webp)

## Make consequences reviewable

Human notes save context and optional read acknowledgements without queuing work. Workspace Q&A
uses a separate conversation and saves its answer as a separate Library record. A task starts work.
A published output preserves a copy for review. An approval is a recorded decision at a checkpoint.

Shared workflow changes use draft, review and publish. Room appearance uses a separate private
preview/apply path. Those actions should not be conflated with running a study or approving research.

## Reuse small file contracts

YAML defines workflows and settings; Markdown holds instructions, notes and papers. The kernel keeps
an append-only study journal. An executor adapts native harnesses or ACP; an SSH worker executes
beside a remote project while the owning Lab retains workflow decisions.

Existing projects keep their runners and environments. Generated projects supply a staged experiment
contract, traceable artifacts and shared ledgers. Library reads source documents, published outputs
and retained records from their existing locations. No second artifact application, transcript
database or general collaboration service is implied.

## Interface principles

The scene has three readable scales: **room** for the task's place, **furniture/activity spot** for
observed work, and **gesture/status** for the agent's current condition. Room changes should mark
meaningful transitions; short tool calls need not cause another walk. Family accents identify
related agents. Output objects should open the records they represent.

Task peers and visible output cards connect with dotted lines on hover, inspector selection or follow.
Attention markers distinguish questions, permissions, quotas, unfinished tasks and disconnected machines;
their wording is shared with agent cards and follow controls. Continued native sessions preserve their
character within the open view, while forks create another character. Room previews use sample activity
and optional clearance guides, without model calls.

The selected-work strip carries study, task and agent focus across map, world and records. Readers
reuse one inspector, keeping recent unsent forms in tab memory. Neither creates execution state.
Further directions are filename-bearing work objects where exact paths are retained and handoff history
on selection. Reuse activity, lineage,
request and artifact records without another workflow language or LLM call per animation. Unknown
activity stays unknown; decorative movement must not imply verified progress.

- Use recognizable actions: New study, Save note, Send, Review, Connect, Visual summary.
- Explain a consequential action where it happens: clone, launch, publish, disconnect or approve.
- Keep optional configuration expandable while leaving evidence, errors and pending decisions visible.
- Preserve source, study and run links when presenting a result.
- Check empty states, recovery, keyboard navigation and narrow screens as well as successful journeys.

Browser fixtures catch broken application paths; they do not establish scientific correctness,
provider access or usability for every researcher. Methodology checks and backend capabilities have
practical limits. See [research limits](research-limits.md), [agent capabilities](platforms-and-agents.md)
and [remote projects](remote-projects.md).
