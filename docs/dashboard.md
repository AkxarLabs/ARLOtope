# The dashboard

Run `uv run --with pyyaml python newts.py` or use the platform launcher. The local browser interface normally opens on port 8787; it can choose another free port.

## Find the right place

| Control | Use it for |
|---|---|
| **Lab** | Visual workspace, active agents, decisions and recent outputs |
| **Studies** | A study's question, tasks, files, instructions and history |
| **Library** | Outputs, existing documents, notes, sources and saved Q&A |
| **Workflow** | Tasks, reusable methods, roles, routes, rooms and checkpoints |
| **New study** | Create a study from a question, existing folder or public repository |
| **Inbox** | Answer questions, review permissions and handle decisions |
| **Assistant** | Ask a separate workspace agent about selected work |

**All agents**, **History** and **Machines & compute** are in the footer. Ctrl/Cmd+K opens search. Settings contains agent, execution and appearance options.

For launch steps, multiple studies, session limits and notification behavior, see
[Start and follow work](running-work.md).

![The Lab workspace in its light theme](assets/current/lab-light.webp)

*Demonstration fixture: the scene and the records below it provide two ways to reach the same work.*

![The Lab workspace in its dark theme](assets/current/lab-dark.webp)

*The same fixture in the dark theme; changing appearance does not change study state.*

## Follow work in the Lab

Use the bottom camera/agent controls to follow a main agent or recorded child. Click a character for its task, activity and a link to details. **All rooms** returns to the overview; the close control stops following without resetting the camera. Viewing a character does not launch work.

**By machine** gives connected machines their own spaces; **Unified** groups their agents into shared rooms. These are views of the same records. **+ Machine** and **Connections** open machine connection controls. The rest of the application remains usable when the 3D view is unavailable.

## Inspect a study

Open a study from **Studies**, an output or a run. Its overview links the active task, documents, recent outputs and notes. Use **Instructions** for local method guidance and **Agents** for saved agent preferences. Attached project files stay in their project.

![A demonstration study overview](assets/current/study-overview.webp)

*Demonstration fixture: start from the study to keep tasks and evidence in context.*

## Answer and recover

Open **Inbox** or the run conversation for a question or tool permission. Read the producing agent and request before answering. Terminal/editor sessions observed by the Lab keep their input in their original terminal.

Research checkpoints have their own evidence and decision sheet. A tool permission allows one native request; it is not approval of an experiment plan or paper. Holding a study, pausing the Lab and stopping one run have different scopes.

![A demonstration stopped task with recovery controls](assets/current/agents-recovery.webp)

*Demonstration fixture: inspect the recorded stopping point before continuing or handing work to a new agent.*

## Outputs and explanations

- **Library → Outputs** displays published reports, pages, tables and figures. Search and study filters help find older work.
- **Documents** browses files from the Lab, studies and projects.
- **Notes & sources** stores separate notes, retained sources and Q&A records.
- **Add note** saves human context. Its default acknowledgement option requests a read receipt without queuing a task.
- **Ask workspace assistant** opens separate Q&A with the selected document or output as context. Sending uses an agent turn and saves the question and answer separately.

A run's **Visual summary** starts an independent explainer. It does not message the working source agent. Automatic assistant briefings are optional and use your agent account.

See [knowledge records](knowledge.md), [outputs and feedback](artifacts.md), [tasks and agents](agent-workflows.md) and [getting started](getting-started.md).
