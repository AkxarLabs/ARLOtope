# The dashboard

The Lab shows agent teams across your studies. Click a character to inspect its task, activity
and conversation. Switch projects without stopping work; Inbox collects questions and decisions
across teams. Screenshots use demonstration data.

## Find the right place

| Control | Use it for |
|---|---|
| **Lab** | Follow working agents and see what needs attention |
| **Studies** | Open a question, its workflow, instructions and history |
| **Library** | Read outputs, documents, notes, sources and saved answers |
| **Workflow** | Build tasks, reuse skills, assign agents and configure checkpoints |
| **New study** | Start from a question, existing folder or GitHub repository |
| **Inbox** | Answer questions, review permissions and make decisions |
| **Assistant** | Ask a separate agent about selected work |

**All agents**, **History** and **Machines** are in the footer. **Settings** holds agent and
execution options. Ctrl/Cmd+K opens search; **?** reopens the ARLO guide.

## Keep your place

Selecting a study, task or agent adds a **Selected work** strip. It carries that selection between
Lab, Workflow and Library. Select other work to change scope, or **×** to clear it.

The shared inspector links each agent to its task, outputs and position in the Lab.
Unsent messages survive switching inspectors in the same browser tab, but not a page refresh.

![A selected study carried into the Library](assets/current/study-context.webp)

## Follow work in the Lab

Use the bottom selector to follow an agent or recorded child. **Show in lab** focuses its character
and task panel. **All rooms** returns to the overview; closing follow leaves the camera in place.

![A character's task panel](assets/current/agent-task-preview.webp)

The panel opens the conversation, study history and retained outputs. Questions and permissions
appear there too. Hover or select a character for dotted links to active agents on the same task
and pass, including recorded children. Other tasks in the same study remain separate.

![Active agents linked by their shared task](assets/current/task-peer-links.webp)

### Inside a room

The task chooses the room; recorded activity chooses a working spot and gesture. Reading can use
a bookshelf, editing a desk, and planning a whiteboard. Agents keep a suitable spot through short
calls rather than walking after every event. These are activity cues; click for the underlying record.

Raised hands and markers distinguish questions, permissions, usage limits, unfinished tasks and
connection problems. Recorded children appear near their parent. Continued sessions keep their
character when a native session ID is available; fresh sessions and forks have separate characters.

**By machine** gives connected machines their own spaces. **Unified** places their agents in shared
rooms. These views use the same records. **+ Machine** connects a project machine.
Studies share rooms; add a new one explicitly in **Workflow → By room**.

**Names** toggles room labels. Theme and reduced-motion choices affect appearance only.
If the world cannot load, use **Retry 3D view** or **View work below**.
See [renderer details](internals.md#visual-activity) for movement and event handling.

## Inspect a study

Open a study from **Studies**, a run or an output. Its primary action shows the next task or decision.
Expand **Workflow map** and select a task to read its instructions, context, outputs and checkpoints.

- **Instructions** adds study-specific guidance.
- **Agents** sets agent preferences for that study.
- **History** groups task passes, agent attempts, notes, decisions and outputs. **Save history to study** creates a readable snapshot.
- **More actions** holds other procedures, notes and controls. **Pending instructions** shows requests awaiting an agent.

![A study overview](assets/current/study-overview.webp)

On narrow screens, **Study section** switches these views. See
[starting and steering work](running-work.md) for launches, holds and multiple studies.

## Answer and recover

Open **Inbox** or the producing run for questions and tool permissions. Checkpoint decisions have
their own evidence sheet. Terminal sessions observed by the Lab still receive input in their terminal.

An agent that stops without its task outcome stays unfinished. Inspect its work before
**Continue task** or **New agent with handoff**. See [recovery](recovering-work.md).

## Outputs and explanations

In **Library**, **Outputs** previews published reports; **Documents** browses existing files;
**Notes & sources** holds retained knowledge. The **Library study** selector carries scope between
tabs. Notes & sources opens one study or Lab-wide records; the other tabs also offer all studies.

**Add note** saves context. **Ask workspace assistant** starts separate Q&A; its **Focus** control
selects work and **Agent & settings** changes its agent. A run's **Visual summary** starts an
independent explainer. Both use your configured agent account.

Instruments pinned to **Lab notes** show compute or other readings. **All instruments** manages
them. **Retry data** rereads data; **Gather now** runs a collector. Custom collectors require code
review before execution; see [instruments](extending.md#collector-execution).

For details: [Notes and sources](knowledge.md) · [Outputs](artifacts.md) ·
[Task instructions](skills.md#read-the-instructions).
