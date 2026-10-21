# Start work and follow it

Creating a study saves its question, workflow and materials. Starting an agent is a separate action.
You can create several studies before launching any work.

## Start a task

1. Connect an installed harness in **Settings → Agents & models** and enable launching in
   **Limits & permissions**. Each harness uses its own account and model access.
2. Choose **New study**, review its details and create it. For an existing study, open **Studies**.
3. Use the study's next-task button, or write a direct instruction. For a composed graph,
   **Run ready tasks** queues eligible task nodes. Check the selected agent, role and context.
4. Launch. The Lab saves the instruction and agent settings, then queues the run. The scheduler
   checks capacity, holds, workflow eligibility, gates, backend availability and usage backoff.
5. Use **Show in lab** to focus the character and its task panel, open its conversation, or use **All agents**. A queued task waits for
   admission; creating or queuing it does not mean the model is already running.

An accepted task outcome updates the workflow. Ordered tasks can follow the next step when that
launch option is enabled. Graph tasks use their connections to make branches ready; joins wait for
their declared inputs. An agent turn ending without its task outcome stays unfinished. See
[recovery](recovering-work.md).

The study's **History** tab keeps task passes and agent attempts together. Saving its generated
history snapshot is optional; the underlying workflow and run records are already retained.

## Work on several studies

Repeat **New study** for each question or repository, then start a task in each. Existing tasks
keep running while you navigate elsewhere. Use **Studies** to see each study's status, **All agents**
for sessions across studies, and **Inbox** for decisions. Tags organize the list without affecting
execution. There is no three-study limit.

The default is **7 task sessions across the Lab**, with a separate default of 7 per study.
Parallel branches that perform tasks each use a slot. Independent reviewers, gate judges, explainers
and assistants are excluded. Tasks beyond available capacity queue rather than
being refused. Change the limits in **Settings → Limits & permissions**. A campaign additionally
has its own approved project/dispatch limits; those do not restrict manually started studies.

An open task chat process reserves a slot even while waiting for your next message. A fully parked
question releases it. Native subagents and independently started terminals are outside the managed
session cap. See [what counts as a slot](compute.md#agent-slots-and-experiment-jobs).

## Hold or steer a study

**Hold** prevents new agents from starting for that study; existing work keeps running. Use
**View hold** or the study's **Controls** to release it. Checkpoint decisions can still be recorded
while held, but starting the next task waits for release.

**Prioritize**, **Park** and **Kill** send instructions for an agent's next inbox check. They do
not immediately change the workflow state. **Pending instructions** shows them in the study's
Overview and Controls, including before a project folder exists. The study list shows a pending
count. **Seen; awaiting action** means an agent has read an instruction without completing it yet.
Use **Withdraw** to cancel a pending request. Inbox and History also keep these records.

These instructions are separate from [human notes](knowledge.md#add-a-human-note), which provide
context and optional read receipts without queuing work.

## Know when something needs you

**Inbox** is the durable attention list. It includes questions, tool permissions, workflow decisions,
unfinished or failed tasks, alerts and escalations. The navigation badge and browser-tab title show
its non-informational count. Opening an item does not dismiss it. Resolving the underlying request
removes it; **Dismiss** hides that occurrence. A flag's **Acknowledge** action is separate and can
release its hold.

Character state and the conversation show exported agent questions. Failed or stopped agents may
leave the scene; their records and warnings remain in Inbox and All agents. The Lab cannot infer
every unstated human request from arbitrary model prose; task-outcome checks catch formally
assigned work that ended without completing its contract.

**Settings → Notifications** has optional delivery:

- **Desktop:** requires browser permission and the local preference. New items notify while the tab
  is in the background; simultaneous items are grouped. Opening the page does not replay its entire
  existing Inbox. Browser notifications require the page to remain open.
- **Phone & chat:** configure ntfy or a webhook. The scheduler sends actionable Inbox items even
  without a browser tab, once per destination. Failed deliveries retry without repeating successful
  destinations while a scheduler is running. The last supervisor also attempts delivery before
  exiting if the dashboard server has stopped. If that attempt fails with no work left, delivery
  retries when a scheduler runs again. Information-only completion reports are excluded.

Neither channel is enabled automatically. Messages contain a title and short excerpt, which can
include sensitive project text. No files or full transcripts are attached. A notification's dashboard
link needs an address reachable from that device, through an appropriate tunnel or proxy; changing
the link does not expose the loopback-only server. Inbox remains usable if delivery is unavailable.

Questions, notes and tool permissions do not approve a research checkpoint. Review those decisions
in their checkpoint sheet.
