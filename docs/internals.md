# Dashboard internals

The Lab uses plain files, a Python server and a browser interface. There is one executor for
dashboard tasks, workflow tasks, gate reviewers, the workspace assistant and visual summaries.
For everyday use, see [The dashboard](dashboard.md).

Launcher probes connect directly to loopback without system proxy discovery. Public static files
use ETags and revalidate on each load; unchanged files return 304. The session page and API responses
remain uncached. The renderer's sandbox and content policy are unchanged.

## Records and identity

| Record | Purpose |
|---|---|
| `workflow/` and procedure files | The process definition, rooms, rules and available skills |
| `lab/journal.jsonl` | Authoritative study moves, waits, approvals and other kernel decisions |
| `lab/REGISTRY.md` | A generated view of the journal |
| `studies/<study>/` | Study brief, process overrides, materials and research documents |
| `lab/.bus/` and project `.bus/` | Signals, run manifests, transcripts, interaction inboxes and scheduler state |
| `lab/records/` | Lab-wide shared records |
| `<project>/.arlotope/knowledge/` | Project-local documents, sources, notes, answers, outputs and logs |
| `<project>/.arlotope/project.json` | Stable project identity and its relative knowledge directory |
| `lab/identity.json` | Lab identity and execution owner used when attaching projects |

The journal is append-only; other state files have their own update rules. The bus is a signal and
transport layer, not an alternative source of approvals. A `run_report` is an agent's summary;
accepted workflow outcomes come from the kernel journal.

`tools/project_identity.py` maintains a small per-user discovery index under `~/.arlotope/` (or
`ARLOTOPE_HOME`). It supports finding attached projects without an account service or a filesystem-wide
scan. Project ownership prevents an accidental second Lab attachment; it is not a multi-user
authorization system.

`tools/knowledge.py` reads and writes Markdown records with metadata and optional attachments.
Human notes do not enqueue work. A requested acknowledgement is only a read receipt. Workspace Q&A
saves a separate answer record rather than editing the source document. Source metadata distinguishes
a link or abstract from material actually captured and read. See [Shared knowledge](knowledge.md).

## The bus

The Lab bus lives in `lab/.bus/`; a project's ordinary bus lives in `<project>/.bus/`.
`tools/lab_bus.py` appends and reads signals. Main event groups include:

- lifecycle: `state_change`, `gate_waiting`, `checkpoint_approved`, `checkpoint_revoked`,
  `checkpoint_changes`;
- experiments: `run_started`, `run_finished`, `sweep_*`, `panel_alert`;
- research activity: `cycle`, `review_verdict`, `replan`, `frontier_expand`, `decision_revisit`;
- attention: `escalation`, `escalation_resolved`;
- agents: `agent_launched`, `agent_waiting`, `agent_resumed`, `agent_finished`, `run_report`.

Directives are instructions, not approvals. Structured interactions are delivered through a run's
inbox. The supervisor owns delivery and replies, so a browser reload does not need to keep a request
in memory.

## Tracing and run lifecycle

The native adapters normalize Claude streams, Codex app-server or exec events, and opencode server
or run events. Installed hooks supply additional tracing where supported. ACP uses negotiated
session updates and client file/terminal requests; it cannot expose activity its agent never reports.

Worker logs are `<bus>/workers/<worker>.jsonl`. Supervisors fold activity into the run manifest,
retain the transcript and append a durable action history to `<run>.d/actions.jsonl`. Subagents are
nested when their parent and identity are available. Outside terminal/editor sessions can appear
through repository hooks; they are traced sessions, not automatically supervised executor runs.

`dashboard/sources.py` joins these records into the snapshot used by the Lab world, **Agents**, the
Inbox and run sheets. A quiet tool call does not imply that the agent has disappeared.

`tools/executor/supervise.py` owns each launched process and its interaction channel.
`scheduler.py` owns queue limits, post-processing and orphan reconciliation. The supervisor's OS
lock is the local liveness signal. The scheduler rereads a manifest before declaring an orphan,
so a just-completed run wins over an older snapshot.

`tools/task_completion.py` separately projects **Task unfinished** for completed assigned runs
whose task still has no accepted outcome. It uses ordered assignment cursors or exact graph
node/visit/run ownership. It does not infer success from prose or from the presence of a report
footer. [Recovering interrupted work](recovering-work.md) explains the user-facing states.

## Workflows and agent context

`tools/workflow_graph.py` validates task connections and context settings.
`tools/kernel/branches.py` folds optional graph nodes over the same study journal. It owns visits,
joins, incoming run lineage, task claims, launch revalidation and output freshness. Ordered workflows
use their existing lifecycle fold.

`tools/lab_profile.py` dispatches eligible tasks through the executor.
`tools/executor/assignments.py` resolves task/role presets.
`tools/executor/contexts.py` enforces one active owner per continued conversation and handles
supported native forks or portable handoffs. A fresh reviewer can receive evidence without the
author's summary. Role, backend choice and conversation context remain separate settings.

`dashboard/compose.py` is the draft, validate, publish and undo boundary for process definitions.
`ui/workflow-canvas.js` provides graph, list and room views. Rooms can group tasks from several
workflows; visual placement does not define execution order. See [Agent workflows](agent-workflows.md).

## The server

`dashboard/serve.py` uses the standard-library `ThreadingHTTPServer` with shared context in
`ctx.py`. Routes delegate to small modules:

- state and reading: `sources.py`, `workers.py`, `attention.py`, `library.py`, `artifacts.py`;
- studies and work: `starter.py`, `runops.py`, `decisions.py`, `campaign.py`, `compose.py`,
  `instructions.py`, `knowledge_api.py`, `assistant.py`;
- configuration and connections: `settings.py`, `agent_settings.py`, `system.py`, `keys.py`,
  `labs.py`, `machines.py`, `project_machines.py`, `term.py`;
- scheduling and instruments: `ticker.py`, `panels_api.py`.

`GET /api/state` is a short-lived cached snapshot; `GET /api/events` streams updates with SSE.
State-changing requests use validated JSON POSTs. Actions that widen authority use explicit
confirmation; the server records PI actions separately from agent activity.

The server binds loopback. Host/Origin checks and a per-server `SameSite=Strict`, `HttpOnly` cookie
protect browser API access; `/api/ping` is a deliberate unauthenticated identification endpoint.
`Origin: null` is refused. Agent HTML and SVG are served with a sandbox CSP and displayed in a
sandboxed frame. These browser protections do not sandbox an agent's operating-system account.
See [Monitoring](monitoring.md).

## Remote projects

The owning Lab retains research state and communicates with a small project worker through an SSH
tunnel. `tools/remote_projects.py` sends captured run inputs, scoped control messages and selected
files; `tools/project_worker.py` runs the existing executor on the remote project. The worker does
not need a second dashboard or a copy of the whole research hub.

Workers run immutable bundled code. A private per-user session file stores their token; the
controller obtains it through authenticated SSH and checks worker identity/build before use.
Public ping does not disclose that token. A disconnected controller cannot conclude that a remote
process stopped. Reconnection and remote reconciliation recover observable state.

Remote publication forwards selected artifacts to the owning Lab. Knowledge remains project-local
and can be read through the same worker. Remote support does not mirror all datasets or turn every
scientific audit into a remote-aware tool. See [Machines and compute](compute.md) and
[Research workflow limits](research-limits.md).

## The front end and 3D Lab

`dashboard/static/ui/*.js` uses vendored Preact and htm, with no frontend build step. Shared CSS and
`research.css` provide the editorial interface, light/dark tokens and bundled fonts. Hash routes
select Lab, Studies, Library and Workflow, with secondary routes for agents, connections and Settings.

`static/lab-view.html` owns the `world3d/` renderer in an iframe. The application shell does not
load Three.js. Same-origin messages send snapshots, theme and motion preferences; checked replies
open studies, agents, checkpoints or artifacts. Once visited, the world stays mounted while hidden
and receives an inactive signal, so returning does not rebuild it. Other pages remain usable
without WebGL.

**By machine** is the default layout: each machine has rooms and agents connected to the others by
bridges. **Unified** groups all work into one set of rooms. Both use the same snapshot and renderer;
neither filters out other machines' agents.

Newt, human and robot characters share activity mappings and simple movement. There is no collision
engine or style-pack runtime in Lab. `dashboard/room_design.py` and `tools/room_resources.py` support
private room drafts and reviewed application through that same renderer. Optional `extra.js`
geometry stays beside its room definition. See [Room design](room-design.md).

`agent-view.js` shares activity labels, task-peer grouping, attention causes and scoped native-session
identity between the dashboard and isolated renderer. It projects existing records without writing
workflow or execution state. `world3d/annotations.js` owns pooled dotted links and room clearance aids.

`ui/focus.js` carries viewing IDs in the URL and current tab, scoped to the Lab. It derives labels
from the snapshot and sends focus to the world; it is not another task store. Readers opt into the
existing overlay manager's `inspector` slot. Recent form drafts use a bounded, Lab-scoped tab-memory
cache in `components.js`; no transcript, draft database or browser-storage dependency is added.

`world3d/model.js` maps a run/task to a room, folds furniture `uses`/`stands` into activity spots,
and supplies coarse within-room paths. `world.js` reserves spots, smooths activity changes and routes
actors through doors and streets. `newt.js` supplies the shared activity/pose animator; `characters.js`
uses it for the three available rigs. These are projections of records, not another workflow engine.

`dashboard/assistant.py` assembles current workspace facts and routes one ordinary executor
conversation. Users choose its study, run or document focus and can start a fresh session. It has no
separate model runtime. Visual summaries are separate scoped explanation runs, saved as artifacts.

## Demo mode and dependencies

`arlo.py --demo`, opened with `/?demo`, provides synthetic studies, agents and outputs for interface
inspection. Demo browser actions are intercepted rather than launching real work.

Vendored browser libraries and their licences live in `static/vendor/`: Three.js, Preact, htm,
marked, DOMPurify and KaTeX. Python tools use the standard library and PyYAML unless a method-specific
helper declares additional requirements.
