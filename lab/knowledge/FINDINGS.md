# Findings

Confirmed, durable results from lab projects. Append-only; newest first. Every entry must carry an evidence pointer to a run artifact or paper section.

Entry format:

```markdown
## F-NNN: <one-line finding>  (YYYY-MM-DD, project: <slug>)
**Evidence:** project <slug> @ <git sha> — runs/<run_id>/metrics.json (and/or paper section)
**Detail:** 2–5 sentences: what was shown, under what conditions, effect size, seeds.
**Caveats:** scope limits, what this does NOT show.
```

---

*(no findings yet)*

## F-001: Keep design compilation, physical roots and local pose separate (2026-10-13, hub engineering)

**RECIPE. Evidence:** `docs/plans/2026-10-13-design-upgrade-results.md`; `output/design-verification/summary.json`; `tests/test_design_compile.py`, `tests/design_runtime.cjs`, `tests/design_physics.cjs`; synthetic browser reports listed in the summary.

Bounded data authoring with one central compiler lets both products consume the same resolved resources. Physical roots must come from the contact controller; local pose can then add charm without moving through solids. Freeze accepted local dependency data, expose explicit upgrade/undo, reserve internal IDs, and keep stale-hash checks at the write boundary. Relative native sweeps should retain tangent movement; a timed yield resolves the tested narrow passage. Native query filter callbacks should use flags/JS IDs rather than nested native collider getters, which broke our teardown probe.

**Caveats:** these are software integration fixtures, not research results or device performance measurements. Core/conservative colliders, native application-version ownership and external agent-tool sandboxing remain explicit limits.

## F-002: Preserve editor revisions and replace live design snapshots (2026-10-13, hub engineering)

**RECIPE. Evidence:** `docs/plans/2026-10-13-studio-workflow-pass.md`; `output/studio-verification/lab-checks.txt`, `newtworks-checks.txt`, `reload-report.json`; `output/playwright/design-physics/studio-report.json`.

A draft name and a resource ID serve different purposes. Preserve the revision the editor loaded until it explicitly loads another document or completes its own write; Preview and Refresh must not grant overwrite permission by silently adopting newer hashes. Read source/hash from the same bytes. Validate all revision and target checks before any mutation, and isolate broken catalog files. Live runtimes should replace local registrations from the accepted snapshot, compare character recipe revisions, retry failed loads and reject older asynchronous replies. When swapping a character, retain the actor and pose state and find safe physical clearance.

**Caveats:** ordinary write rollback is not crash atomicity. Data-only host boundaries do not sandbox unrestricted external agent tools. Shared room authoring does not remove Newtworks' product-level workflow category restriction, and desktop fixtures do not verify physical phone performance.

## F-003: Confine design models with scoped capabilities and immutable review snapshots (2026-10-13, hub engineering)

**RECIPE. Evidence:** `docs/plans/2026-10-13-private-design-sandboxes.md`; `output/playwright/design-sandbox/summary.json`; `tests/test_design_sandbox.py`.

Use a tool-free model transport and a broker bound to one private workspace; folder-writing prompts do
not restrict reads, shell tools or outside actions. Keep trusted SDK/compiler/renderer references frozen
and hash checked, with no candidate executable code on the preview path. Python validators need `-B`
to avoid changing their own snapshots. Namespace test actors and every copied room's physical bodies
outside author-controlled IDs. Export the complete checked snapshot atomically, and ZIP that immutable
export rather than a draft the model may have changed after the lock was released.

**Caveats:** this is a model capability boundary with a trusted host, not an OS execution sandbox. CLI
capabilities and an empty tool/server inventory must be verified without a general-agent fallback.
Current live Claude transport remains unverified locally; Codex/OpenCode designers are refused.


## F-004: Give confined designers broad authoring and inspection capabilities (2026-10-13, hub engineering)

**RECIPE. Evidence:** `docs/plans/2026-10-13-capable-design-workspace.md`;
`output/playwright/design-capabilities/{AutoScientist,Newtworks}/report.json`, `ui-report.json`,
`shared-hashes.json` and per-product `tests.log`.

Refines F-003: a zero-tool model and non-executable-only previews unnecessarily limit design work.
Expose public reference search plus readable SDK, patch/batch editing and selectable visual feedback.
Allow custom JS/Three/WebGL in an opaque prototype frame with private modules and a frozen SDK;
keep application writes/credentials/promotion outside its capabilities. No fixed inspection sequence
is needed for exporting a compilable draft: include evidence and its freshness for human review.
Share one timed scene player across previews and the runtime, and compose clips instead of growing
lists of special-case gestures. Distinguish author-provided instrumentation from host validation.
Tests of this structure establish working capabilities/isolation; they do not establish better model
visual quality. Live transport/search behavior and actual design performance still need model trials.

## F-005: Separate the designer protocol from harnesses; save styles as overlays (2026-10-14)

**RECIPE. Evidence:** `docs/plans/2026-10-14-design-harnesses-and-styles.md`,
`output/playwright/design-styles/{shared-hashes,ui-report,world-report}.json`, per-product previews
and compiler/broker test logs linked by the report. Refines F-004's implementation limits.

Expose the same bound workspace operations through MCP/JSON and adapt CLI event streams at one
small transport seam. Native provider reference tools remain available; creativity does not need
another scheduler, fixed feedback sequence or a provider allowlist at the workspace boundary.
External harness native tools retain their own permissions, so distinguish broker scope from an
OS sandbox. Protocol fixtures do not prove live model behavior or better model design performance.

Model editable style data as optional inheritance plus ordered merge/selector/JSON Pointer layers,
then compile through the existing geometry/motion/physics contracts. Save source and resolved
snapshot independently of the originals. Scope material changes to private copies, hash character
revisions, rebuild spatial geometry and restore baseline registries when the style is removed.
This lets humans/agents modify existing resources as easily as adding new ones without editing the
original application or introducing a second design engine.


## 2026-10-14 — RECIPE: lightweight appearance packs over reusable resources

Keep resource creation (rooms/assets/clips) separate from appearance packs. Resolve an explicitly
ordered manifest against a frozen full authoring inventory, but compile/save only changed resources
and dependency closure. Map character appearance by stable identity and family selectors; preserve
inline room-owned rig definitions so future resources can receive styles without global registration.
Use the ordinary animation/physics interfaces, and scope optional native rendering extensions to
owned resources and lifecycle hooks. Save source/file trees atomically as one revision bundle; give
designers private edit access and people the save/select flow. Avoid hidden filesystem ordering,
recompiling all resources or a second aesthetic/effects framework.

Validated in both products: 100 regression tests per product plus actual Three/Rapier/Chrome checks;
profile transforms, identity, collision sizing, relative modules, edit-existing copies, restoration,
resource cleanup and portable exports pass. Palette-only fixture: 262,101 bytes of authoring context
becomes a 9,162-byte resolved overlay without spatial replacements. Evidence:
`docs/plans/2026-10-14-world-design-packs.md`, `output/playwright/design-styles/` and the per-product
`output/playwright/design-capabilities/*/pack-suite.log`. This is an interface/fixture result, not a
measurement of LLM design quality or all possible hardware/rendering behavior.


## 2026-10-14 — RECIPE: demonstrate artistic freedom with complete authored packs

A pack's whole directory carries JSON appearance/resource layers; its optional extensions directory
carries code. Full aesthetic changes can stay declarative: replace geometry by logical character ID,
apply family profiles to future IDs, and use an explicit room source for changed spatial layout.
Keep generic palette/material rules broad. Verify examples through the same private broker and saved
revision APIs the designer and app use, then inspect animation close-ups. With the toy-biped data rig,
make articulated limb geometry part of its bound node; auxiliary hand/shoe nodes can otherwise remain
on the torso while the limb moves. Use a character factory for more elaborate attachment/rig designs.

Executive Atelier and Origami Nocturne validate distinct business and paper-theatre design languages
in both products without engine changes. Evidence: docs/plans/2026-10-14-radical-pack-examples.md,
output/playwright/design-packs/browser-report.json, verification.json, per-product example-test.log
and the gallery. Identity/style/physics fixtures are interface checks, not universal artistic quality
or hardware-performance guarantees.


## 2026-10-14 — RECIPE: soft animation extensions and advisory coverage

Keep secondary squash/jiggle in the existing rig update, with bounded spring substeps, no second
animation clock and reduced-motion reset. Keep shared animator snapshot fields at the top level;
put extension state in its own nested field, and restore sensible defaults when another rig lacks it.
Otherwise style switching can inject undefined spring state into a newly replaced live actor.
Use a single smooth gel surface when overlapping head/body meshes create an unwanted neck seam.

Style completeness can remain advisory. Store only baseline identity lists, check new accepted
resources against explicit pattern mappings, and offer a dismissible notice while keeping the pack
usable. Preserve baselines on editing/export. Generic palettes do not establish bespoke object
coverage, and code-driven coverage is declared honestly by the author. Verify dismissal under real
stylesheets: inherited pointer-events:none on transient-toast containers also disables new buttons
unless the persistent notice explicitly enables interaction.

For heavy asynchronous WebGL prototypes, expose a first-render readiness selector, wait for it,
perform interactions and pause before bounded capture when useful. This succeeded without increasing
the preview budget. Evidence: docs/plans/2026-10-14-pudding-pals-and-coverage.md and
output/playwright/pudding-pals/{verification,workflow-report,live-world-report}.json with private
prototype and native-preview records. Visual jiggle remains separate from deformable collision physics.

## 2026-10-14 — RECIPE: pack-owned cinematic surface studies

Physical transmission plus tinted absorption and a pack-local PMREM reflection environment produces
inspectable gel depth; smoothing geometry alone does not. A checker/stripe stage and opaque toggle
make the effect distinguishable from an ordinary glossy color. External facial details should render
after the transmission capture to avoid a duplicated refracted face. Shared deterministic micrograin
textures can use the existing resource cache/reference lifetime; pack-owned reflection targets must
restore the previous environment and dispose on exit. Custom-character wildcard treatment should
preserve geometry, update/rig and physics; explicit builtin variants can share a new stylized rig.
Workspace tree revisions and resolved style hashes are distinct; validate preview-job files/profiles
against the saved bundle. Surface quality and topology/rigging quality are separate art tasks.
Evidence: output/playwright/surface-studies/verification.json, browser-report.json and per-product
native preview/export reports. Tests and source parity pass in both products; fixed body capsules
and realtime transmission remain approximations. Full details: docs/plans/2026-10-14-cinematic-surface-studies.md.

## 2026-10-14 — RECIPE: extension ownership and shared designer guidance

JSON material selectors apply after a pack's material factory; obsolete blanket finish overrides can
erase fabric/skin/metal distinctions. Let the module own its material families, retain only targeted
JSON overrides, and declare honest code coverage. Provide one frozen designer quick start in the
initial model context and expose the same reference in dashboard/MCP flows. Stable IDs, explicit
layer/module order, relative imports, resource-versus-pack authoring and clock/resource cleanup are
the essential contracts. Save/refresh should clear stale preview pixels/diagnostics. Older frozen
workspaces should fall back to guides they already contain, rather than requiring newly added files.
Evidence: output/playwright/design-cleanup/verification.json, dashboard-report.json, per-product
regression logs and native preview/export reports. Details: docs/plans/2026-10-14-design-cleanup-audit.md.
Keep standalone helper copies until shared packaging; cross-pack imports would add hidden dependencies.

## 2026-10-14 — Native designer integration constraints

Confirmed from tools/design_workspace.py: files() scans all authored files and style compilation
UTF-8-decodes their contents. Native browser screenshots and installed package trees must live in a
separate scratch area, or the normal authoring inventory/compiler contract can break. Confirmed from
tools/executor/lab.py: agent registries are discovered for the hub and registered projects; changing
an agent's execution cwd to a private workspace must not move its run record into an undiscoverable
registry. Preserve distinct registry ownership and execution directory when simplifying the launch.
These are implementation constraints, not results from a live designer pilot. Plan and references:
docs/plans/2026-10-14-native-designer-simplification.md. No native-session migration was applied here.

## 2026-10-14 — RECIPE: capable private designers without a second model loop

Reuse the normal executor/harness session for native edit, shell, web and persistent browser tools.
Keep authored text in working/ and binary evidence/dependencies in scratch/ so compiler snapshots
remain text-only. Keep the run record owned by the hub even when execution cwd is private. Serve
one draft through an owned loopback preview and share its scene builder with fixed captures.
Advertise operation fields explicitly and return concise compile summaries; vague errors led the
first actual model pilot to mistake a source error for a missing tool capability. On Resume, send
fresh preview URLs in the actual follow-up message: updating a standing preamble alone did not
reliably replace remembered addresses. Evidence: docs/plans/2026-10-14-native-designer-implementation.md;
research/native-design-pilots/AutoScientist/20261014-143714/verification.json;
research/native-design-pilots/Newtworks/20261014-143857/verification.json;
research/native-resume-smoke/Newtworks/20261014-150217/verification.json.
This is a verified integration recipe, not a benchmark claim about model design quality.

## 2026-10-14 — RECIPE: workflow visits and complete definition snapshots

For a general agent workflow, bind reports to a task visit and run, make completion idempotent, and check current outputs before accepting success. A paused check-in can continue in a new harness session of the same visit: preserve that visit's original output baseline so valid earlier work does not need to be rewritten. Redo and explicit definition updates create new visits.

Reviewed workflow revisions must fingerprint helper resources as well as resolved instructions and YAML, and verify copied resources before publishing the new snapshot. Otherwise a helper can change after the review without changing a schema-only revision token. Verified in Newtworks with visit/continuation and stale-helper regressions; see ../Newtworks/tests/test_composition.py, ../Newtworks/tools/flow/versions.py and output/playwright/newtworks-compose/.

## 2026-10-14 — RECIPE: attach first, customize through plain research definitions

Research onboarding can create a question record and project pointer without modifying an existing
repository, environment or runner. Keep study creation separate from agent launch and approvals;
offer reproducibility/paper scaffolding when requested. Workflow customization remains central even
when visual customization is removed: reuse Markdown procedures, YAML steps/checkpoints, definition
overlays and reviewed publication instead of introducing another designer engine. Keep optional 3D
rendering outside the normal page boot and preserve legacy group keys to avoid a schema migration.

Verified in the research-first Lab implementation with disposable existing-repo comparisons, browser
flows, real GitHub lookup/clone, definition checks and regression follow-ups. Evidence:
docs/plans/2026-10-14-research-first-implementation.md and
output/playwright/research-first/verification.md. Previous visual-designer recipes remain relevant to
Newtworks/the archived reference; that runtime is intentionally absent from the current Lab edition.


## RECIPE — 2026-10-15: visual-first, agent-aware workflows without another engine

The visual research lab remains the primary workspace. Keep tasks (skill/instructions/outputs),
dependencies (parallel and join), agent roles and context, and rooms as separate declarative
concerns. A room can combine tasks from several workflows after composition. Optional graph visits
can be folded over the existing Lab journal; legacy ordered workflows need no migration. Bind
native sessions to exact incoming task visits and permit one active owner. Label portable forks as
handoffs rather than claiming exact context clones. Reuse the native executor for an assistant and
designers; deterministic state and opt-in updates avoid an always-running model. A lean Lab room
preview/apply seam can use the real renderer and room-local geometry without the full Newtworks
style-pack system. This updates the preceding research-first recipe: Lab's 3D view is primary, with
simple movement, three characters and camera following.

Validated with native CLI fixtures, both Chrome flows and regression suites. Evidence:
docs/plans/2026-10-15-agent-aware-visual-workspaces.md and
output/playwright/agent-workspaces/verification.md (links to exact test logs, browser results,
shared-module parity and screenshot gallery). The integration also reproduced and fixed Windows
O_EXCL delete-pending PermissionError collisions; queue mutexes must retry these alongside existing
file collisions. No live research or model benchmark was run, and no new runtime package was added.

## 2026-10-15 — Plain dashboard copy and honest platform checks (RECIPE)

Keep dashboard chrome to concrete names and actions; move concepts to disclosures while retaining
task instructions, evidence and approval consequences. A forked product must own its CI: Newtworks'
inherited Lab checks referenced files and snapshot fields it no longer has. Its own regression suite
now has Windows/Linux/macOS jobs. Source-level OS branches and a configured matrix are not proof of
execution on those OSes; this session's passing tests and Chrome flows are Windows evidence only.
ACP belongs at the existing executor transport seam if adopted, not as a new workflow engine.
Evidence: docs/platforms-and-agents.md and output/playwright/plain-language/verification.md.

## 2026-10-15 — Remote access is workspace access, not task migration

Source audit confirms Lab's SSH manager proxies an entire remote lab; Newtworks' phone relay has a
different purpose and no equivalent SSH machine manager. Remote skills/files/provider login are local
to that remote lab, with no automatic conversation/file sync. Remote creation uses committed HEAD.
The bootstrap assumes POSIX bash. Atomic inbox writes alone are insufficient for crash-safe delivery:
live.take removes messages before handling. An acknowledged receipt is needed across that boundary.
Remote tests rerun on Windows: 6 passed, 5 POSIX integration cases skipped; those use fake SSH anyway.
No real password/MFA/remote-PC validation is claimed. Evidence: docs/plans/2026-10-15-remote-workspaces-and-acp.md
and output/verification/remote-audit/python-remote.txt.

## 2026-10-15 — Hub filesystem assumptions behind remote projects

Inspection: executor.Lab.project_dir and labfiles.project_dir require directories visible to the hub;
lab_profile.render_prompt and the generated project protocol name hub-local procedure paths. Therefore
attaching a machine ID and remote path alone will not enable remote projects. Separate run execution
from hub path access and deliver needed instructions to the project host. The PI wants attached remote
projects in one Lab alongside optional links to independently owned Labs. The thin-worker structure is
proposed, not implemented. Evidence: lab/notebook/2026-10-15-projects-across-machines.md and
docs/plans/2026-10-15-remote-workspaces-and-acp.md (revision section).

## 2026-10-15 — Remote setup can reuse existing entry points

Source inspection: Lab already has the local/GitHub study starter, SSH machine probes/connections,
full-Lab switching/proxy, fleet summaries and purpose-specific agent installer/login helpers. The
proposed remote-project path should extend those seams rather than introduce a second onboarding or
collaboration subsystem. A missing CLI detection is not proof no installation exists; noninteractive
PATH can differ, so retain an explicit path/environment choice before installing another copy. The
remote worker and machine-filtered 3D flow remain proposals. Evidence: dashboard/starter.py,
dashboard/machines.py, tools/terminal.py and lab/notebook/2026-10-15-remote-project-user-flow.md.

## 2026-10-15 — RECIPE: remote execution with one research controller

The earlier remote-project proposal is now implemented in Lab. Reuse the existing supervisor and
native adapters inside an execution-only zipapp; keep workflow admission, outcomes and approvals in
the owning Lab. Send the procedure catalog and small resources in run snapshots. Keep repository
files remote and mirror run metadata/transcripts. Durable dispatch/input receipts cover retries;
uncertain delivery remains explicit. Check a supervisor's OS lock on its execution machine rather
than probing its PID on the controller. ACP is another negotiated adapter, not another workflow engine.

The config writer must serialize command arrays as JSON-compatible YAML, preserve Windows path
characters and quoted # arguments, and remove the previous YAML list when replacing it. Source and
verification evidence: docs/plans/2026-10-15-remote-projects-implementation.md, tests/test_remote_projects.py,
tests/test_acp.py, tests/test_profiles.py and tests/test_serve.py. Real SSH password/MFA and live-provider
interoperability remain unverified; the passing fixtures do not establish those behaviors.


## 2026-10-15 — RECIPE: visual evidence and remote continuation share existing seams

Use the canonical artifact publisher for both local and remote agents. Forward a selected file through
its scoped controller request and retain real run/study/machine provenance; receipt retries reuse the
publication. The Results iframe can run self-contained HTML while remaining isolated from the host
UI. Keep agent tool capabilities independent of the viewer's external-resource policy.

A remote supervisor can finish between the controller's poll and a new PI message. Worker-side polling
must preserve that late message as a continuation under the execution host's process lock, commit the
queued state before acknowledging input, and leave admission to the main scheduler. A stale “running”
mirror is not proof a live process will consume an inbox. Evidence and tests:
tests/test_remote_projects.py, tests/test_acp.py and docs/plans/2026-10-15-lab-experience-audit.md.
The passing fixtures do not establish real SSH/MFA or installed-provider behavior.


## 2026-10-15 — RECIPE: one HTML preview in existing file surfaces

Published HTML already renders in Results, but that alone does not make the run's ordinary changed
files previewable. Classify .html/.htm in run_files, serve only transcript-authorized paths through
the existing raw-file route, and reuse the isolated frame in FileSheet. Keep Results publication for
milestone discovery and feedback rather than inventing a second HTML application. Evidence:
tests/test_artifacts.py and output/playwright/html-files/browser.json.


## 2026-10-15 — RECIPE: route through durable runs, not role names

A workspace assistant needs a small explicit command map alongside current state: resolve a full run
ID from study/task/role, inspect its canonical record/evidence paths, then relay only the requested
follow-up. Subagents route through their parent; traced terminal sessions remain distinguishable from
controllable executor runs. Use code-owned tool paths with an explicit selected-Lab argument. Record
the sending run ID for CLI-mediated actions. Keep existing-session continuation distinct from creating
a new agent; retain execution enablement and normal scheduler/context checks. Source and verification:
dashboard/assistant.py, tools/executor_cli.py, tools/executor/runs.py and
output/verification/assistant-routing/lab/.

## 2026-10-15 — RECIPE: keep view state and organizational labels explicit

Seed an embedded renderer's theme before its first paint, serialize asynchronous scene updates and
discard superseded state. Forward all existing interaction types across a frame boundary, retaining
subagent identity, and resolve durable run IDs at the read endpoint rather than requiring membership
in a bounded snapshot. A compact workflow overview can share its existing node definitions with a
docked inspector, room grouping and checkpoint editing. Flat labels belong in existing study/skill/
workflow metadata, with one normalizer and no parallel taxonomy store; include them in agent briefs
without giving them execution semantics. Evidence: tools/tagging.py, tools/kernel/brief.py,
dashboard/static/ui/lab-view.js, dashboard/static/ui/workflow-canvas.js and
output/playwright/lab-navigation/lab/browser.json; regressions in
output/verification/lab-navigation/lab/python-focused.txt.

## 2026-10-15 — RECIPE: contextual visuals and optional agent transports

Keep a character's compact inspector in the existing UI and project its anchor from the renderer;
reuse normal run/session APIs for details and messages. Reduced-motion camera changes still need an
explicit redraw request. An optional ACP backend belongs behind the existing executor seam: keep
session loading, permission IDs, text deltas and failure semantics intact; never apply native CLI
version probes or one-shot fallback to a JSON-RPC agent. Pass private designer MCP servers through
the protocol rather than creating another designer engine. Verify with an actual stdio peer, then
separately qualify vendor interoperability. Evidence: output/playwright/agent-peek/ and
output/verification/lab-navigation/newtworks/python-focused.txt; Newtworks docs/acp.md.

## 2026-10-16 — RECIPE: retain visual state and reuse the study record system

Keep a single visited 3D renderer mounted between dashboard pages, with an explicit active flag to
pause its animation loop. Ignore zero-size hidden-frame resize events and refit only for actual
viewport/inset changes; otherwise navigation resets the user's camera. Theme-dependent material
values can be declarative day/night data over stable geometry. Keep a rebuild fallback for authored
modules that construct different geometry. In browser checks, use timer polling for hidden frames:
requestAnimationFrame polling can itself stop when the frame is hidden.

Expose existing study/project/evidence locations in every study run's instructions rather than adding
a second memory database. Clearly distinguish shared on-disk records, remote instruction snapshots
and experiment worktrees. For ACP terminals, process exit and complete output are separate events:
report completion only after the output drain finishes. Evidence: the 2026-10-16 notebook entry,
output/playwright/lab-switch-review/browser.json, tests/test_acp.py, tests/test_world.py and docs/projects.md.

## 2026-10-16 — RECIPE: keep camera controls stable during live updates

A native agent selector can remain compact and keyboard-accessible without a second dropdown system.
Update its options only when roster identity/labels change, clear departed selections, and reflect
following initiated from character popups in the same control. Do not reissue followWorker on every
snapshot: that resets zoom even while following the same actor. Evidence: ui/lab-view.js,
output/playwright/follow-controls/browser.json and the follow-controls notebook entry.

## 2026-10-16 — RECIPE: align workflow language with actual session lineage

Fresh means no prior session ID; continue means another message on the saved native session, with
one active owner; portable handoff means a new conversation with evidence, not a full native fork.
Use those meanings consistently in node controls, arrows and docs, and test actual transport calls.
For simple onboarding, choosing a starting point should reveal its fields directly while preserving
source switching and the brief; keep review before cloning/creation. Mobile verification must check
enabled actions against fixed overlays, not only assert that a button exists. Evidence: the study-
journey/context-verification notebook, tests/test_agent_workspaces.py, tests/test_acp.py and
output/playwright/research-ui-pass/browser.json.

## 2026-10-16 — RECIPE: test attention with permission requests that remain running

A native/ACP tool permission can be pending while its run still has status running. Build the
Waiting for you filter and count from pending requests as well as waiting_input and final reports.
Keep tool permissions, agent questions and research checkpoint decisions separate. Embedded visual
previews should receive state only from their parent; retain API fallback for standalone previews,
otherwise a synthetic or machine-filtered view can race a real state fetch. For local UX fixtures,
serve the actual assets through an isolated server without importing the scheduler or exposing
writable APIs. Evidence: the workflow-decisions/local-session-demo notebook and
output/playwright/local-session/browser.json.

## 2026-10-16 — RECIPE: keep turn completion distinct from task completion

A zero agent-process exit or ended conversational turn is not evidence that its assigned workflow
visit completed. Use the accepted journal outcome to settle the task; surface an ended owner with
an unresolved visit as needing follow-up. Free-form chats without a completion contract remain
ambiguous and should show a neutral Your turn state. ACP stable v1 now specifies elicitation/create
for structured questions, with distinct accept/decline/cancel responses; adapter capability absence
must not be described as protocol absence. Native history forks and summary handoffs also require
different configuration meanings. Evidence: the interaction/workflow-design notebook and linked
primary protocol references in docs/plans/2026-10-16-workflow-context-and-interaction-design.md.


## 2026-10-16 — RECIPE: separate workflow evidence from agent transport state

A successful agent exit does not prove task completion. Project follow-up from the owning graph
visit or an ordered run's journal cursor; timestamps alone can confuse earlier same-second moves.
Native continuation/fork checks must compare the remote execution folder, not the controller mirror.
Gate review is Lab policy over an ordinary fresh executor run. Validate its input revision, visit,
allowed decision and required checks before recording a route; a historical review cannot authorize
an ordered back-route or changed evidence. Keep these policies outside the generic executor.

Verified with deterministic backend peers, a packaged localhost worker and the fake-agent
review-to-next-task test. Browser receipts: output/playwright/workflow-interactions/browser.json.
Details: lab/notebook/2026-10-16-workflow-interactions-implementation.md. Live provider/SSH behavior
and other operating systems remain unverified.
# RECIPE — SSH connection verification (2026-10-16)

For project runners on shared SSH hosts, authenticate session delivery through SSH, create private
credential files with mode 0600 at creation, and verify build, account and worker PID. A successful ping
alone does not establish that a cached cookie survived a worker restart. Parse replacement credentials
from authenticated restart output; consume one-shot interactive readiness files so old credentials
cannot overwrite the renewal. Share dispatch admission locks across immutable worker versions.

For UI onboarding, carry project selection directly into the current form rather than writing a draft
and navigating to the same route. Poll connection state separately from installed-agent/auth probes.
Evidence: `tests/test_machine_connections.py`, `tests/test_remote_projects.py`,
`output/playwright/ssh-connection/browser.json`, and
`lab/notebook/2026-10-16-connection-simplification-and-verification.md`.

## RECIPE — Machine views and interactive retries (2026-10-16)

Separate machine layout from execution: keep the full snapshot, namespace visual room/gate instances,
resolve actual execution location before project home, and retain real actor IDs in both layouts.
Give waiting actors a desk per machine and route cross-platform movement through physical bridge
waypoints. A view switch repositions existing rigs rather than starting another scene or filtering work.

Human login is a resumable interaction: retain the host, explicitly restart expired prompts, terminate
expired SSH processes, and guard async UI callbacks after unmount. Retry transient transport failures
with bounds; never repeatedly trigger password/MFA prompts without the user's action.
Evidence: tests/test_machine_connections.py, tests/test_world.py and
lab/notebook/2026-10-16-machine-views-and-login-retries.md.

## RECIPE — Study materials must travel with remote instructions (2026-10-16)

A materials index alone is insufficient for a remote agent: it needs the original files at the paths
in that index. Freeze the study's originals when a remote run is queued and transfer bounded files
separately before dispatch, requiring a worker acknowledgement. Keep suggestion output separate from
researcher fields and mark it stale when the inputs change. This reuses the normal executor without
a parallel model transport or document parser dependency. Evidence:
`output/verification/study-starter-regressions.txt`, `output/verification/study-starter-linux.txt`,
`output/playwright/starter-materials/verification.json`.

## RECIPE — Separate full records from the live snapshot (2026-10-16)

Apply study/run scope and unanswered state before limiting artifact history. Keep the live board's
recent snapshot small, but query full records separately with cursor pagination. Use an explicit
revision signal for old-record feedback and retain loaded pages when refreshing. Key document
selection by study so a previous study's content cannot remain selected after navigation.
Evidence: output/playwright/records/verification.json and
 docs/plans/2026-10-16-backend-records-audit.md. This indexes metadata, not document full text.

## RECIPE — Persistent Windows workspaces need inherited access (2026-10-16)

Do not promote a checkout from an owner-only temporary directory into a permanent agent workspace.
Windows ACLs survive a same-volume rename, and Codex's sandbox user differs from the Lab process's
identity. Use a unique directory that inherits the selected project parent's permissions; keep
private temporary directories for data that remains private to the creating process. Declare shared
Lab workspace access in both Codex live and exec transports, while preserving read-only choices.
Evidence: output/verification/windows-workspace-permissions.json,
output/verification/codex-records-fixed.json and docs/plans/2026-10-16-windows-publication-fix.md.

## RECIPE — Independent explanations need immutable evidence and explicit lineage (2026-10-17)

Keep the producing explainer session separate from the source run/child and its study. Give each
assistant request its own immutable facts file; validate rejected sends before writing it. Capture
bounded observed evidence with source paths and coverage limits, and read remote files against the
source run's recorded machine/path. Normalize supervisor worker IDs while discovering native hook
logs by embedded run ownership. Do not assume nested conversations are fully exported by a harness.
Evidence: docs/plans/2026-10-17-lab-navigation-and-explainers.md,
output/verification/independent-explainer-live.json and tests/test_run_evidence.py.

## 2026-10-17 — RECIPE: role, preset and context stay separate

A task role supplies instructions, a named preset selects harness/model options, and context selects
conversation inheritance. Capture launch options once; a continued/forked session keeps its source
configuration. Resolve causal workflow sources instead of a globally recent run, and reserve a fork's
source until the native session acknowledges startup. The implementation and file formats are in
`docs/agent-workflows.md`; regression evidence is indexed in `lab/notebook/2026-10-17-agent-choices.md`.

A real ACP agent can require authentication separate from its installed editor. Antigravity ACP
1.4.0 completed its own Personal Google OAuth, model turn and same-session reload through the normal
adapter (`output/verification/antigravity-adapter.json`, `antigravity-adapter-resume.json`). Native fork
must remain capability-negotiated. Close probe stdio before bounded process-tree cleanup so packaged
launchers can remove temporary runtimes. Keep executor test fixtures outside a parent Git checkout.
## 2026-10-17 — Separate context, execution and explanations

Human context can stay useful without becoming an execution queue: save a note in project-local
Markdown and request an explicit read acknowledgement at check-in. Keep task directives separate.
For workspace Q&A, record the question and immutable answer/run correlation before attempting
remote delivery; a reconnect or a new question must not strand an earlier answer. Existing ledgers
and source documents need not be rewritten. Use protocol peers across all adapters and keep test
workspaces outside a larger Git checkout. Evidence and file formats are indexed in
`lab/notebook/2026-10-17-knowledge-and-ui-utility.md` and `docs/knowledge.md`.

## 2026-10-17 — RECIPE: verify user guides against the running interface

Capture real components in an isolated Lab with launching disabled and label synthetic records.
Keep human notes, execution directives and Q&A distinct in guides as well as in code. A browser
walkthrough can reveal first-use bugs that populated fixtures hide: an unsent assistant record must
not look up a run before it has one. Document interruption recovery from accepted workflow outcomes,
not from process exit or a plausible final sentence. Evidence: `lab/notebook/2026-10-17-docs-and-recovery.md`.

## 2026-10-17 — RECIPE: remote cancellation belongs to an attempt

A run ID spans several resumed attempts. Scope cancellation and delivery receipts by attempt so an
old Stop cannot kill resumed work and a new Stop is not erased by resume admission. A deliberately
parked question has no active supervisor: preserve it during orphan reconciliation and cancel it
without waiting for a process that has exited. Re-read terminal state after checking the supervisor
lock so a completed write wins. Evidence: `tests/test_remote_recovery.py` and
`lab/notebook/2026-10-17-license-and-e2e.md`. Distributable workers must carry their source and license
notices, including vendored dependencies, independently of the controller's filesystem.

## 2026-10-17 — RECIPE: count execution ownership and settle final attention

A workflow task's process/session is the admission unit; study count and visible character count are
different. Hub and project procedures about one study must share its bucket. A live waiting chat
reserves capacity, while a parked question without a process releases it. Preserve that distinction
in orphan reconciliation, health and scheduler keep-alive logic.

Reuse authoritative Inbox projections for notification channels. Persist per-destination delivery
receipts under a cross-process lock; repeated attempts and checkpoint visits need occurrence IDs.
The last supervisor must settle its report and attempt notification before exit when the controller
server is absent. A fresh lease from a dead or exiting process must not suppress handoff of delayed
work. Evidence: `tests/test_agent_capacity.py`, `tests/test_notification_attention.py` and
`lab/notebook/2026-10-17-capacity-attention-and-live-tests.md`.

## 2026-10-18 — RECIPE: separate task capacity from process liveness

When review, explanation and assistance are exempt from a task cap, keep a separate liveness
predicate for reconciliation, usage accounting and scheduler handoff. Exemption from task capacity
must not hide a process, stop its monitoring, or bypass provider quotas and pauses. Classify
independent reviews through declared roles and existing support metadata, not research-procedure
names embedded in a generic executor. Test helper admission with all task slots full, and verify
that a lost helper supervisor still reconciles. Evidence:
`tests/test_agent_capacity.py` and `lab/notebook/2026-10-18-task-capacity-and-workflow-review.md`.

## 2026-10-18 — RECIPE: put a licensing boundary before unpublished work

Refresh remote refs and verify that every replayed commit is unpublished across all remotes, not
merely ahead of one stale tracking branch. Create the license-only commit at the last pushed base
in a separate worktree, then replay unpublished patches. Compare range-diff, final trees and dirty
working-file hashes before changing the current branch/index. Keep a local backup ref and avoid
pushing that backup. This preserves a dirty development workspace while making the next branch push
begin with the legal boundary. Evidence: `output/verification/license-first.json` and
`lab/notebook/2026-10-18-license-first-release-order.md`.

## 2026-10-17 — RECIPE: verify SSH recovery against the original attempt

Test remote recovery in a disposable project owned by an isolated controller. Disconnect the real
tunnel during active work, verify that collection reports a connection error without classifying
the task as failed, then reconnect through the ordinary authentication flow. Require the completed
output to retain its original session ID and attempt number; successful output from a newly launched
replacement is not the same test. On Narval this passed for a Claude continuation after password/Duo.
Local mirror evidence survives cleanup of the disposable remote project. Evidence:
`output/verification/narval-outage.json` and the follow-up in
`lab/notebook/2026-10-17-capacity-attention-and-live-tests.md`.

---

## 2026-10-18 — RECIPE: Windows process liveness without shell probes

Scheduler startup and legacy-run liveness checks should use a native Windows process handle with a
zero-timeout wait. Launching tasklist for every check can stall the scheduler and slow whole workflow
runs. Keep supervisor file locks as the primary ownership signal, close every process handle, and
reject non-positive PIDs. The regression checks a real child before and after exit while rejecting
subprocess-based probes. See tools/executor/procs.py and tests/test_executor.py in public commit
f401294; the verified check is recorded in the private migration checks/windows-process.txt referenced
by output/verification/repository-migration.json.

---

## 2026-10-18 — RECIPE: Probe the same port-reuse policy as the server

A POSIX HTTP server can reuse a stopped listener's port while accepted connections remain in
TIME_WAIT. A raw bind probe without SO_REUSEADDR incorrectly prevents that restart. Match the
server's reuse setting in the probe, retain Windows' exclusive binding policy, and verify both
an active listener and a recently closed connection. The native macOS reconnect regression passed
with this fix; see public commit 91ab534 and the platform run recorded in
output/verification/repository-migration.json.

Keep compatibility test inputs as explicit fixtures rather than reading historical commits: clean
repositories, source exports and shallow CI checkouts must be able to run the tests independently.

## 2026-10-19 RECIPE: preserve incomplete review evidence separately from rejection

An interrupted multi-agent audit can classify findings with missing verifier outputs as dropped.
Recover the original journal and per-agent verdicts before using its final kept/dropped list; preserve
explicit incomplete/confirmed/partly/refuted states, and do not feed a planner a claim that unfinished
areas were tested. Here the original workflow's 17-kept/23-dropped split included confirmed issues
among the dropped entries because a second verifier hit the usage limit. Evidence and dispositions:
output/verification/claude-audit-20261019/{journal.jsonl,result.json,recovered.json};
output/artifacts/claude-audit-analysis-2026-10-19.md. The findings include overlaps, not forty independent
root causes. Current runtime probes are recorded separately from the original reviewer evidence.

## 2026-10-19 RECIPE: share a bounded snapshot read, isolate its custom renderer

Resolve projects from existing registry rows. Reuse model/config/registry reads inside an explicit
read batch, then discard that batch so later workflow/config edits remain visible. Serialize snapshot
computation separately from invalidation; reject a result if the cache generation changed during its
read. Test read counts and concurrency rather than portable wall-time thresholds.

Custom room geometry remains ordinary JavaScript, but it receives source/data inside an opaque
renderer frame. The owning dashboard handles authenticated reads and source-checked UI intents;
there is no generic API relay. Direct preview links open the normal owning sheet. Evidence:
output/artifacts/priority-fixes-2026-10-19.md and output/verification/priority-fixes/.

### 2026-10-19 — RECIPE: keep cached pixels immutable and UI success evidence-based

Three.js Texture clones share their Source. Cache immutable canvases and create independent Sources
for floors that change image on theme switches; verify repeated round trips against pixel hashes.
For editable forms, separate loading/error/data and ignore obsolete replies. Approval success follows
the server's `ok`, never the end of a press-and-hold gesture. Evidence:
output/artifacts/feedback-fixes-2026-10-19.md and output/verification/feedback-fixes/.

### 2026-10-19 — RECIPE: renderer recovery follows renderer events

Share the isolated frame's loading/failure/Retry shell between the Lab and room drafts. Do not turn
slow state or asset loading into a graphics failure. A real context loss must stay failed across
ordinary snapshot updates until restoration or frame replacement. Keep work records accessible
outside the renderer. Evidence: output/artifacts/clarity-fixes-2026-10-19.md.

### 2026-10-19 — RECIPE: respect composite focus and collapsed sections

Route focus should skip retained hidden views and preserve dialog/form autofocus. When selecting
an editable field, do not rely only on getClientRects(): Chrome can report rectangles for descendants
of collapsed details even though focus fails. Exclude closed details and file pickers explicitly.
Browser checks caught this in Starter; see output/verification/navigation-polish/browser.json and
output/artifacts/navigation-polish-2026-10-19.md. Keep header layout rules with one owner so grid
placement does not depend on an old flex-order override elsewhere.

### 2026-10-19 — RECIPE: permission and task completion have separate evidence

A run's checkpoint request can precede its workflow outcome. Use kernel readiness.waiting for an
approve-and-start affordance, not a display list that also includes run-footer requests. Recording
approval alone does not finish/move a task. If a stale client asks to start without a move, explain
that nothing started rather than manufacturing completion. Regression/browser evidence:
output/verification/workflow-followups/ and output/artifacts/workflow-followups-2026-10-19.md.

### 2026-10-19 — RECIPE: give the same recovery label the same action

Inbox and run-sheet Continue task should share one explicit same-session follow-up. Keep generic
interruption Resume distinct. Offer a fresh evidence handoff when a native session cannot be loaded;
do not silently substitute it while claiming context preservation. Check the actual new prompt and
source lineage as well as its manifest. Evidence: output/verification/agent-recovery/ and
output/artifacts/agent-recovery-2026-10-19.md.

### 2026-10-19 — RECIPE: keep read reuse scoped to one read-only request

Reuse the existing model/registry/config read context across a checkpoint sheet's readiness,
asking-run and title reads; end it before any later request or decision. Resolve evidence locations
once and batch remote file-state requests. Verify later file/definition/approval changes as well as
call counts, and compare response contents to saved source before claiming a performance improvement.
Evidence: output/verification/checkpoint-cleanup/ (210 passing regressions, one POSIX-only skip,
one separately passing extension contract) and output/artifacts/checkpoint-cleanup-2026-10-19.md.

### 2026-10-19 — RECIPE: preserve structured metadata and avoid duplicate route state

When a document reader cannot parse all of a metadata format, show its complete escaped source
behind a small disclosure rather than flattening it into misleading partial fields. No new browser
parser is needed for that view. For shareable filters, derive the filter from the route and update
the route on selection; separate local state otherwise misses same-page links and browser history.
Evidence: output/verification/study-controls/ and output/artifacts/study-controls-2026-10-19.md.

### 2026-10-19 — RECIPE: preserve instruction origin when combining bus views

Targeted hub instructions must remain visible on their study before and after project attachment.
When combining hub and project buses, carry the bus scope as well as record ID/time: separate
buses can mint the same ID in the same second. Aggregate each bus once and send scope back on
withdrawal. Keep pending/seen separate from actual task outcomes. Evidence:
output/verification/study-requests/{tests.txt,browser.json} and
output/artifacts/study-requests-2026-10-19.md.

## RECIPE: validate project identity before recording a local attachment (2026-10-19)

Remote attachment uses `project_identity.register` before writing its owner marker. Do not pre-create
a marker and validate afterward: a rejected portable identity can otherwise leave an unusable local
claim. A real worker HTTP regression covers rejection with unchanged records followed by corrected
retry; the saved worker comparison reproduces the old write order. Keep portable identity and
deliberately retained knowledge separate from local bus history, and explain ignores without editing
an attached repository's policy. Evidence: output/verification/starter-identities/validation-order.json
and tests.txt; docs/knowledge.md records Git and backup guidance.

## RECIPE: review loaded evidence and approve its displayed version (2026-10-19)

Dependent review reads should wait for their real baseline and ignore late replies from older
selections. Reuse the shared loader for metadata, keeping polling/cached data on its own lifecycle.
For executable collector review, derive code and hash from one byte read, then compare the optional
expected hash at approval; refresh a changed file instead of approving unseen code. Legacy callers
need not migrate. Evidence: output/verification/review-loaders/{tests.txt,browser.json,decline.json}.

## RECIPE: execute checked bytes and distinguish unavailable evidence (2026-10-19)

Approval-time hashes do not close a later mutable-path execution gap. Check captured collector
bytes and execute their sibling copy, preserving cwd/resources and exposing the original path.
Evidence readers may retain prior successful data only for their current scope; distinguish an
unreadable record from an absent one at both API and UI boundaries. Reuse the shared loader;
keep best-effort consumers explicit. Evidence: output/verification/evidence-recovery/
{collector-race.json,verified-tests.txt,browser.json,empty-demo.json,denial-tests.txt}.


## 2026-10-19 — RECIPE: retry reads without changing work

Keep read failure distinct from empty evidence and from an empty instruction. Retain last-good data only for its own selection, label it on failure, and preserve unsaved text independently of read state. Scope each poller generation to its owning selection so late replies cannot restart or overwrite a different run. File HEAD checks catch access failures without another full download; they do not certify embedded page scripts or PDF decoding. Evidence: output/verification/library-recovery/{browser.json,drafts-lineage.json,reader-final.txt}; batch report output/artifacts/library-recovery-2026-10-19.md.


## 2026-10-20 — RECIPE: workflow-independent onboarding

Bind reuse/omission to actual task IDs plus a requirements revision; keep those journal events distinct from agent completion. Use the existing graph fold for both preview and readiness so checkpoint waits, joins and first-visit-only behavior agree. Existing evidence has references, not a resumable model session; mixed handoffs retain real causal sources. A control-contract watch should distinguish plain attachment from a declared contract and snapshot prior presence to detect deletion. Evidence: output/artifacts/workflow-entry-2026-10-20.md and output/verification/workflow-entry/{entry-final.txt,browser.json,execution.json}. Real private clone/new OAuth/SSH were not verified in this pass.


## 2026-10-20 — RECIPE: read recovery and inherited runtime ownership

Retry reads against the same session/offset; do not replay uncertain writes. Invalidate in-flight reads at both mutation start and settlement, including while a review screen is open. Preserve stale collector data separately from transport failures. When workspaces do not contain the runtime, name installed commands explicitly and capture/translate inherited resources for remote execution; do not copy another Lab’s research/system/study records as defaults. Evidence: output/artifacts/lifecycle-recovery-2026-10-20.md and output/verification/lifecycle-recovery/. Real Codex publication passed; corrected footer paths were checked with regression tests, not another paid model turn. Sakana comparison is an architecture review, not an experimental result.

## 2026-10-20 — RECIPE: external research engines as ordinary tasks

Keep optional engines behind declarative command/phase/evidence definitions and the existing graph,
roles, rooms and checkpoints. Use stable project-owned run directories, explicit budgets and retries,
and verify current completion receipts before accepting a task outcome. Export tool requirements;
an unavailable external phase must not silently become a prose-only skill. A phase supervisor is
observable without claiming its internal workers are native controllable sessions. Evidence:
output/artifacts/external-frameworks-2026-10-20.md and output/verification/frameworks/. Local fake
frameworks and the real portable worker bundle were exercised; no live Sakana campaign is claimed.

## 2026-10-20 — RECIPE: verify the external runtime before claiming readiness

A real Sakana native investigation completed after moving installation/run state off the Windows
WSL mount, using npm 11 for the pinned Headless Git dependency, and matching the coding CLI version
to the available model catalog. Keep the old pin and failed attempts for diagnosis. CLI sign-in,
model visibility, a tiny model turn, native phase completion, declared evidence checks and full
container-preset readiness are separate tests. Missing Docker still fails the real ARLOtope preflight;
a successful native run must not silently bypass it. Evidence: output/artifacts/sakana-install-2026-10-20.md
and output/verification/sakana-live/{upstream-tests.txt,live-investigation-compatible.json,real-evidence-check.json,arlotope-check.json}.

## 2026-10-20 — RECIPE: separate task completion from completed-output feedback

A live external-framework workflow exposed feedback that queued successfully but failed task admission
once the study finished. Permit an explicit reply only when the journal records completion for that
exact run, node and visit. Retain its original binding, and suppress automatic successor dispatch for
that feedback turn. Do not relax admission for unfinished/replaced visits, ordinary resumes, shelved
studies or newly gated work. Check the unchanged journal with a process-based harness test as well as
admission unit tests. Evidence: output/verification/remaining-tests/{completed-reply-focused.txt,
completed-reply-final.txt,followup-native-final.txt,followup-linux-final.txt,final-live-browser.json}.

The real Docker smoke also demonstrates that a completed_no_winner external phase can satisfy a
software completion contract without supporting a scientific improvement claim. Review original
receipts/manifests, and inspect the resulting explanation: the first HTML mislabelled completed
phases and used broken relative evidence links. A same-session correction published a preserved v2.
Keep resolved runtime repairs clearly distinguished from current instructions. Check readiness from
the supervising shell itself; host readiness alone did not establish sandbox compatibility.
Evidence and limitations: output/artifacts/remaining-tests-2026-10-20.md.

## 2026-10-20 — RECIPE: show external activity without changing execution ownership

Map explicitly named JSONL events to a small activity projection, keeping original files as evidence.
Reuse the existing worker poll and supervising actor rather than creating a telemetry service or
synthetic workers. Bound tail reads and label malformed/truncated history. A completed phase can
contain failed candidates; activity must never grant a checkpoint or write a completion receipt.
For interface previews, derive from the same task graph and layout as the editor. Exercise custom
branches, joins, loops and empty drafts, plus rapid keyboard selection: delayed selection-clearing
effects can erase a user's next action. Keep the reset in the workflow-selection event instead.
Evidence: output/artifacts/visual-workflows-2026-10-20.md and its linked test/browser receipts.

## 2026-10-21 — RECIPE: keep context shared without duplicating controls

Library scope belongs above its views; carry it in existing URLs while retaining per-view filters.
Clear a selected document/record when scope changes. Do not treat a group with zero documents as
populated, and do not show “No outputs yet” while an index is loading. For optional task settings,
native disclosures avoid more component state, but their `open` property must not track an edited
field: changing a conversation mode otherwise closes the section mid-edit. Evidence and bounded
browser coverage: output/artifacts/compact-controls-2026-10-21.md.

## 2026-10-21 — RECIPE: expose workflow records without another ledger

Join the study journal, managed-run manifests/transitions and artifact metadata into a read-only
task/pass view. Keep actual task outcomes separate from agent status: timeout, a completed model
turn or a manual skip cannot establish completed scientific work. Preserve linked support sessions
and explicit missing/stale coverage. Generate optional portable Markdown/JSON snapshots on request,
not on every render/ticker update; never fold them back as execution truth. Current workflow
definitions are export-time context, not evidence of prior code. For character-first access, reuse
the same task panel for clicks and follow actions; freeze its position while it is being used.
Evidence and limitations: output/artifacts/world-and-history-2026-10-21.md.

# RECIPE — 2026-10-21: Verify read-after-create and rendered class ownership

An existing-project starter can save correctly yet briefly hide its new study behind the snapshot
TTL. Invalidate the snapshot before replying to successful creation; frozen-clock tests distinguish
that guarantee from timing luck. Also inspect actual world overlays before removing CSS: a retired
sleep-marker class left text at the corner despite no JavaScript error. Reusing the existing bubble
class fixed it without another style. Evidence: `tests/test_snapshot_reads.py`, the combined journey
in `tests/test_study_history.py`, and `output/verification/remaining-tests/{busy-cache-tests.txt,
busy-linux-tests.txt,busy-browser.json,existing-project-before.json,existing-project-browser.json}`.

# RECIPE — 2026-10-21: Studies share explicit rooms

Keep study identity separate from spatial identity. Define rooms once, assign tasks to them, and
resolve each run from its own task (including a parallel branch), not only the study's displayed
step. Legacy per-project flags must not restore duplication. Machine views may repeat the defined
room set without changing execution. Removing the old clone/scaffold/fallback paths makes the
contract smaller and prevents project attachment from unexpectedly expanding the world. Evidence:
output/artifacts/shared-rooms-2026-10-21.md; tests/test_world.py; verification receipts
output/verification/remaining-tests/shared-rooms-{tests,linux-final,world-final,linux-world-final}.txt
and shared-rooms-handoff.json. No quantitative research result or new remote certification claimed.

# RECIPE — 2026-10-21: Fold controls without losing configured intent

Show the few fields needed for the current action, then group optional controls by their purpose.
Keep configured choices visible in disclosure summaries; preserve one editor and verify its values
survive Review/Back. Folding is presentation, never a reset or alternate configuration model.
For workflow loops distinguish reaching a task from sending a message: initial reuse may skip
execution once without permanently disabling the task or withholding files. Check phone fallback
views against real branched workflows: a branch warning must not replace their task cards.
Evidence: output/artifacts/interface-simplicity-2026-10-21.md and named scoped test/browser receipts.

# RECIPE — 2026-10-21: Evaluate research skill suites at the contract boundary

Before importing an agentic research suite, compare its actual protocols, runtime adapters and
evidence status with existing Lab capabilities. Prompt roles are not automatically isolated
agents; copied prompts do not carry native hooks or calibrated behavior. Preserve one owner for
workflow state and approvals. For Academic Research Skills, source support and revision checks
can extend our existing records/skills; its full passport/state layer would duplicate ours.
Check licensing before copying prompts as well as code. Source-level findings, pinned version
and boundaries: output/artifacts/academic-research-skills-review-2026-10-21.md.

# RECIPE — 2026-10-21: Observe a run relative to its starting workspace

A Git digest must scope enclosing repositories to the run's selected directories and compare
against starting content, not only porcelain status letters. Existing dirty files are not work
done by the run; subsequent edits to those same dirty files, reversions and deletions still matter.
Record fingerprints for the initial dirty set, avoid opening special files, and preserve historical
receipts when correcting later accounting. This remains a Git observation: ignored files and
causal authorship require other evidence. A real disposable Codex run exposed the original issue;
regressions and receipts: output/verification/release-readiness/{digest-scope.json,watch-focused.txt,
final-runtime-tests.txt}; implementation tools/kernel/watch.py and tests/test_kernel.py.

# RECIPE — 2026-10-21: Test the handoff after saving, not only the save response

Creating a study and refreshing the dashboard are separate operations. Do not expose dependent
navigation or an agent instruction until the saved study is present in the displayed snapshot.
A delayed read should preserve the success boundary; a failed read should offer Retry without
repeating creation. Workflow copies should similarly open the copy rather than leave the old
selection active. Generated IDs belong behind a small disclosure while names and next actions
stay prominent. Evidence: output/playwright/journey-review/{creation-race.json,workflow.json,
start.json}; report output/artifacts/user-journeys-2026-10-21.md. These are interface-contract
checks with synthetic studies, not scientific results.

# RECIPE — 2026-10-21: Keep workflow defaults out of generic controls

Resolve a task's method from its workflow node (including explicit null), then study/workflow
substitutions; a shared step's default alone is insufficient for menus or eligibility checks.
Optional skill-local UI metadata can supply task starting points without a second preset registry.
Keep these shortcuts opt-in on variants so copying a method does not duplicate the parent's button.
Evidence: tests/test_kernel.py and tests/test_ui.py replacement/null/substitution cases;
output/verification/workflow-generality/{tests.txt,final-tests.txt,metadata-tests.txt,execution-tests.txt}
and browser snapshots/screenshots. This is software behavior, not a research result.

## 2026-10-22 — RECIPE: reusable methods with project ownership

Keep reusable instructions as ordinary SKILL.md folders. Copy only selected workflow methods and
explicit dependencies into a project; prefer existing project methods and never silently overwrite
them. Save exact resolved resources and the effective workflow with each managed run, then supply
explicit paths to every adapter. Keep import receipts outside upstream folders so provenance cannot
overwrite a supplied file. This preserves editable project methods and auditable run instructions
without a plugin service or a second workflow language.

Evidence: output/verification/arlotope-structure/{regression,final-skills,final-ui,e2e}.log;
implementation tools/skill_resources.py; docs/skills.md. Adapter verification used controlled peers,
not universal live-provider certification.

## 2026-10-22 — CORRECTION: canonical interface replaces compatibility names

The PI rejected the preceding compatibility decision. Active commands, metadata and storage now use
arlotope.py / ARLOTOPE_* / .arlotope exclusively. There are no old-name wrappers, automatic pre-kernel
converters, legacy route redirects or portable-fork aliases. Project identity and ownership share one
configuration file; the discovery index remains a cache. Keep real study-history continuity and current
harness interoperability; those support present workflows, rather than old product versions.

Evidence: clean-break commit 833ce02; Linux CI 1,127 passed in
output/verification/arlotope-clean-name/linux-ci.log. Launcher follow-up 604ac96 has a real process
regression and manual foreground/background receipts; its CI is separate. Interrupted mixed-source local
full runs are not exact-head passing evidence. This supersedes the old namespace advice in earlier notes.

### 2026-10-22 — RECIPE: direct graph editing uses the existing workflow contract
Keep task dependencies separate from conversation sources and visual room assignments. Removing dependencies must invalidate orphaned conversation sources and workflow references, and keyboard deletion must leave focus inside the map so Undo still works. Evidence: lab/notebook/2026-10-22-workflow-interaction.md; output/playwright/workflow-interaction/journey.log; tests/test_workflow_ui_actions.py; tests/test_compose.py.

### 2026-10-22 — RECIPE: document the visual projection without inventing progress
The current room renderer already combines task rooms, furniture uses/stands, observed activity and
shared gestures. Reuse these seams for expressive scenes; distinguish semantic run/task status from
animation and missing telemetry. Run-ID actor identity is not persistent conversation identity.
Refresh guides from canonical definitions and synthetic launch-disabled records, and retain original
scientific test images as dated evidence. Renaming command entry points also requires checking shell
recognizers, not only prose. Evidence: lab/notebook/2026-10-22-docs-world-review.md and its receipts.

### 2026-10-22 — RECIPE: keep visual identity separate from run controls
Reuse a character by scoped native conversation identity, while clicks and replies continue to use
the current run ID. A camera detail change can replace its mesh without replacing the actor; tests
must check actor/animation continuity rather than mesh object equality. Reduced-motion annotation
updates need an explicit render kick when follow ends, and hover exit needs to work across the iframe
boundary. Share attention and task grouping between UI and renderer; sample previews remain synthetic.
Evidence: lab/notebook/2026-10-22-visual-agents.md and the browser/model/resource receipts it names.

<!-- 2026-10-22: engineering recipe, not a scientific finding -->
**RECIPE — Dashboard focus without another execution model.** Carry study/task/agent IDs in URL
and Lab-scoped tab state, derive labels from the existing snapshot, and reuse one inspector for
readers. Preserve unsent forms with bounded tab memory while keeping backend request IDs untouched.
Test refresh scope, cross-study document links and release from a followed character. Evidence:
`lab/notebook/2026-10-22-study-context.md`, `tests/test_focus.py`, `tests/test_study_controls.py`,
`output/playwright/context-journey.js` and `output/playwright/context-world.js`.


**RECIPE — Bind local HTTP without reverse DNS.** Standard HTTPServer resolves a server name even
for 127.0.0.1. A slow macOS resolver stalled dashboard startup in full CI. Share TCP binding with
explicit server_name/server_port and Windows exclusivity between dashboard and project worker;
include the helper in the worker archive. Test with getfqdn raising, and capture a child stack when
startup stalls rather than raising the timeout. Evidence: lab/notebook/2026-10-22-release-cleanup.md,
tools/loopback_http.py, tests/test_serve.py, output/verification/docs-world-review/macos-startup-stack.log.

**RECIPE — Review units and local readability, not just page overflow.** A task capacity limit
excludes independent support work, so an all-active-runs count cannot describe its utilization.
Use the backend's capacity accounting. Likewise a timeline can fit in its scroll container while
its labels overlap; inspect the local component at narrow widths. Evidence:
output/verification/interface-release-review-20261022.md,
output/playwright/release-review-busy-phone.png, tools/executor/manifest.py,
dashboard/static/ui/runs.js.

**RECIPE — Teach through existing screens.** First-visit guidance can be a short declarative list
of topics and navigation actions with Lab-scoped browser progress. Keep it usable before signing
into a model and separate from agent configuration, workflow state and permissions. A guide should
not enable launches or queue work while explaining them. Evidence: dashboard/static/ui/guide.js,
output/playwright/arlo-guide-check.js, lab/notebook/2026-10-23-arlo-guide.md.

**RECIPE — Make instructions inspectable at their point of use (23 October 2026).** A workflow map's
skill labels are insufficient for understanding a task. Reuse a read-only Markdown reader beside task,
role and review-skill selections; keep additions and source paths visible. Separate draft definitions,
project-local skill precedence and historical run inputs. Never generate a preview by enqueueing work
or substitute live skills for missing snapshots. Preserve literal placeholders such as `<slug>` when
rendering instructions. Evidence: dashboard/instructions.py, dashboard/static/ui/workflow.js,
tests/test_instruction_reader.py, lab/notebook/2026-10-23-instruction-reader.md.

**RECIPE — Separate dependencies from conversation history (23 October 2026).** A workflow arrow sets execution order; waiting for all branches and choosing a source conversation are independent decisions. Reuse one small input/context control in both task and arrow inspectors, show joins only where relevant, and keep uncommon outcomes and loop limits under advanced settings. ACP setup should check initialization before saving, preserve defaults, and distinguish protocol success from model access. Explicit argv commands need executable-path resolution for Windows npm shims. Evidence: lab/notebook/2026-10-23-acp-usability.md and output/verification/acp-usability-complete-20261023.md.

**RECIPE — Exercise typing, not only form filling (23 October 2026).** Controlled multiline inputs can pass bulk-fill tests while dropping Enter during normal editing. Verify keystrokes, intermediate empty lines and navigation away from unsaved forms. A strict docs build cannot detect stale UI labels or screenshots; compare them with the live interface. Evidence: output/verification/usability-docs-audit-20261023.md and output/playwright/usability-audit-20261023.js.

**RECIPE — Normalize commands at submission (23 October 2026).** Preserve intermediate multiline input, including trailing and empty lines, so normal typing works. Normalize the command only when checking or saving. Reuse the same small unsaved-form guard across configuration and workflow editors; successful Save and explicit Cancel must not produce false navigation warnings. Keep a single primary task editor and label the separate shared-default scope. Evidence: tests/test_form_controls.py, output/playwright/usability-fixes-check.js, output/verification/usability-fixes-20261023.md.

**RECIPE — Clone-first application, private Lab records (23 October 2026; recorded 24 October).** Keep tracked defaults separate from the active local settings file; seed once without overwriting user choices. Ignore Lab/study records and keep project code in its own repository. Explicitly back up lab/, studies/ and projects, including ignored evidence. A clean-clone test should create a study and note, render an HTML output, and still leave Git clean. Evidence: output/verification/clone-release-pass-20261023.md; final exact-head CI run 40018280159.

**RECIPE — Give sandboxed agents a usable Lab interpreter (24 October 2026).** A Windows Store Python virtualenv can start the controller outside a sandbox yet fail inside Codex's workspace sandbox. Detect the underlying Store interpreter and use uv-managed Python for the existing durable Lab environment. Agents should invoke Lab helpers through ARLOTOPE_PYTHON, while retaining each project's own research environment. Verify publication and a formal workflow outcome in a real bounded task; writing the output file alone is insufficient. Evidence: output/verification/beta-final-20261024.md; candidate c9384e7; final CI 40123328970.


**RECIPE — Ask about a run without steering it (25 October 2026).** Keep assistant Q&A separate from direct working-agent messages. Preserve study, run and child identity from the character or conversation; inspect recorded evidence and expose missing-history coverage. Store the answer separately with its source link. Keep shared protocol in AGENTS/briefs and substantial conditional skill branches in linked references, then verify those resources survive project and run packaging. Evidence: output/verification/assistant-skills-20261025.md; tests/test_agent_workspaces.py; candidate 38e94a2.


**RECIPE — Verify the commands an assistant receives (26 October 2026).** Use the same durable interpreter resolver for generated assistant/explainer argv as for the executor itself. Execute those argv against external project paths and older runs; then check a real assistant continuation re-reads changed evidence. Audit full native command records when shortened action summaries omit the executable name. Settle synthetic completed manifests before byte-identity baselines so normal controller postprocessing is not mistaken for assistant edits. Evidence: output/verification/assistant-access-20261026.md; candidate 1044305.


**RECIPE — Bound frequent views; keep evidence on demand (26 October 2026).** Read recent log tails backward instead of allocating the whole ledger; omit full action arrays from metadata descriptors while retaining source paths. Skip empty-view work before loading shared definitions. Remote polling can stop only after the worker confirms idle state, drained streams and cleared requests, with pending controls waking it again; a completed status alone is insufficient. Measure sequentially and distinguish Python allocations from RSS. Evidence: output/verification/efficiency-audit-20261026.md; candidate c4a8500.


**Confirmed engineering gap — Ordered history loses task assignment (26 October 2026).** Managed ordered runs save assigned_step and assigned_journal_index, but the current study-history projection groups only workflow_node/workflow_visit records and omits the ordered assignment fields. A disposable queued proposal run reproduces empty visits despite its recorded assignment; it was not launched. Existing assignment/cursor evidence can support the shared history projection without another execution engine. The UI/logging extension is still a proposal. Evidence: output/verification/study-history-ordered-probe-20261026.json; output/artifacts/study-history-design-20261026.md.


## 2026-10-26 — RECIPE: derive readable workflow history from ownership records

Use saved assignment cursors for ordered tasks and journal bindings for graph tasks. A completed model turn is not a workflow outcome. Keep exported responses and human exchanges outside capped transcripts; lazy readers can then show them without putting full conversation payloads into every study snapshot. Preserve expanded UI state during refresh, and include remote archive offsets in refresh dependencies so late mirrored bytes become readable.

Evidence: output/verification/history-release-check-20261026.xml, output/verification/history-final-projection-20261026.xml, output/playwright/study-history-20261026/browser.json and output/verification/history-native-recovery-20261026.json. Details and remaining environment limits are in lab/notebook/2026-10-26-study-history-implementation.md.


## 2026-10-26 — RECIPE: test worker imports from the packaged artifact

A new executor dependency must be included in the remote worker's explicit module list. Test supervisor imports in an isolated Python process with only the zipapp on the import path; starting the worker or importing the unpackaged module alone does not exercise this dependency. The history recorder omission and correction are documented in lab/notebook/2026-10-26-study-history-ci-fix.md. Evidence: output/verification/history-ci-fix-focused-20261026.xml and output/verification/history-ci-fix-remote-20261026.xml; original failing CI run 40349209903.

## 2026-10-28 — RECIPE: preserve source snapshots and let reads settle

When a workflow forks and continues one native conversation, reserve the fork copies before allowing the original to advance. Admission can use the existing run/context records; an independent executor is unnecessary. Treat empty optional event fields as absent, since the journal may omit them. For a UI that discards superseded reads, poll after the previous response settles rather than resetting its key on a fixed interval: otherwise a slow response can remain invisible indefinitely. Include recorded context lineage in assistant summaries and point to the original records for verification.

Implementation and evidence: lab/notebook/2026-10-28-release-acceptance.md; output/verification/beta-acceptance-20261028/receipt.json. These are engineering lessons from software acceptance fixtures, not research findings.
