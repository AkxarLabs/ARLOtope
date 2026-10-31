# Open Questions

Threads worth pursuing. `/ideate` reads this file first — it is the lab's compounding idea pipeline. Append freely during any procedure; prune during ideation triage.

Entry format:

```markdown
## Q-NNN: <the question>  (added YYYY-MM-DD, source: <project/paper/lit-review/session>)
Why it matters, what a first experiment might look like, related findings/failures (F-/X- ids).
Status: open | promoted → studies/<slug> | retired (reason)
```

---

## Q-001: How should the lab prevent drift between executable authorization/configuration paths and prose? (added 2026-10-05, source: codebase-tour session)

Engineering maintenance thread, not an empirical research finding. The codebase tour found stale absolute wording about headless Gate 3 despite authorized dashboard/campaign paths, a broad config-layer description that omits the runner's base/CLI layers, and orientation prose attributing registry updates to a pending-write-back reconciler that only applies notebook/knowledge fields. Evidence: `tools/lab_profile.py::run_env`, `tools/gate3.py`, `dashboard/gates.py`, `templates/project/src/project_pkg/config.py::load_config`, `tools/process_writebacks.py::main`, `tools/hub_writeback.py`, and `lab/notebook/2026-10-05-codebase-tour.md`. A maintenance pass could align those descriptions and add focused documentation consistency checks without changing the PI's research rules.

Update 2026-10-11 (verified against the code):
- **Gate 3 wording: moot.** The numbered gates are gone, and `tools/gate3.py` and `dashboard/gates.py` were deleted in `6d91df6`.
- **Config layers: fixed.** AGENTS.md and docs/configuration.md now say what `load_config` does: `-o` > experiment yaml > `configs/base.yaml` > `control.yaml`, and a run never reads `lab/config.yaml`.
- **Write-back attribution: fixed.** AGENTS.md no longer says `process_writebacks` updates the registry; it appends to the notebook and knowledge only.

What remains open is the general question: a check that keeps prose like this in step with the code.

Status: open (maintenance; the three instances are resolved; do not treat as a scientific idea candidate)

## Q-002: How should Gate 2 authorize the resolved configuration across the runner/guard boundary? (added 2026-10-07, source: gates-compose-engine inspection)

Engineering maintenance thread, not an empirical research finding. A temporary-fixture reproducer used the supported `stage=FULL` CLI override on an original SMOKE config, with an unsigned Gate-2 envelope. The runner preflight saw the resolved FULL stage, but `guard.py full-run --config <original-file>` reread SMOKE and returned success before envelope checks. Actual guard/preflight logic was exercised via an injected subprocess adapter; no experiment, approval or compute slot was launched. Evidence: `research/gate2-inspection.py`, `templates/project/scripts/_runner_guards.py::gate2_preflight`, `tools/guard.py::c_full_run`, `templates/project/src/project_pkg/config.py::load_config`, and `lab/notebook/2026-10-07-gates-compose-engine.md`. A fix should check the effective stage/config and cover the real runner-to-guard handoff, including sweeps and inheritance, rather than relying solely on mocked guard exit codes.

Update 2026-10-10/11: moot.
- `_runner_guards.py` (with `gate2_preflight`) and `guard.py::c_full_run` were removed in `6d91df6`. `tests/test_guard.py` asserts `c_full_run` is gone.
- The runner performs no approval preflight (`templates/project/scripts/run.py`). This removed the preventive boundary; it does not repair an enforced gate.
- Full runs are now a workflow checkpoint (`approve-full-runs`, a `during` stop the agent observes), watched after the fact by `checks/full_runs_without_approval.py`.
- `research/gate2-inspection.py` no longer runs, because it loads the deleted file.
- `tools/upgrade_project.py` no longer lists the deleted file.

Status: retired (the Gate-2 preflight and full-run guard were removed in 6d91df6; see docs/plans/2026-10-10-implementation-status.md)

## Q-003: How should checkpoint edits reconcile active waits and invalidate old approvals? (added 2026-10-10, source: workflow implementation audit)

Engineering maintenance thread, not an empirical research finding. Isolated fake-lab probes show that deleting a checkpoint leaves a study waiting in the journal while its approval sheet shows no checkpoint; changing a checkpoint's meaning and required checks preserves its old approval. A simulated Write to core engine source is also not denied by the current signature guard, so designer candidate-only confinement needs a separate runtime boundary. Evidence: research/implementation-audit-probes.py, research/implementation-audit-2026-10-10-probes.json, tools/kernel/journal.py::approved, tools/kernel/studies.py::next_for, dashboard/compose.py::_after_change, tools/signature_guard.py::check_path. First checks should cover removed pending checkpoints, semantic revision changes, affected-study previews and candidate-only designer writes. No live approval or study was changed by this audit.

Update 2026-10-11 (each part reproduced independently in a fresh fake lab):
- **Removed pending checkpoint: fixed.** The wait was stale rather than stuck: reporting `done` again, or a PI move, cleared it. But the views disagreed and the review button failed. Publishing or undoing now calls `studies.reconcile()`, which re-decides each affected study without approving anything, and the dashboard no longer lists a wait for a missing checkpoint.
- **Stale approvals: fixed (a46ed03).** An approval records its checkpoint's terms (`model.terms`: before/during/at, means, checks); when they change, or a campaign's approval becomes the PI's alone, it reads `outdated` and a study that hasn't passed the checkpoint waits again. Approvals recorded before terms were kept still stand.
- **Designer confinement: fixed (a46ed03).** A procedure may declare `writes:`; the designers declare `lab/.bus/designs/**`. The guard refuses their edit-tool writes and shell redirects elsewhere, and the digest flags anything else they change (`writes-outside`). Earlier, the guard script itself was put on the guard's floor.
- **Preview of affected studies before publishing: fixed (a46ed03).** Review & publish lists "Studies it affects" (`diff.affected`).

The evidence under `research/` is git-ignored, so it exists only on this machine.

Status: resolved 2026-10-11 (all four parts fixed; legacy approvals without recorded terms are the one accepted gap)

## Q-004: What is the smallest trustworthy completion and approval boundary for Newtworks? (added 2026-10-13)

Engineering direction from the PI-requested fork comparison, not an empirical research finding. Newtworks' per-project workflow snapshots and four main UI concepts are a useful simplification. Isolated probes show that its approval function accepts an agent environment, repeated `done` reports advance without required outputs, file-existence fallback accepts old placeholders, and `move()` advances stopped projects. Decision-only guard probes deny direct Write/redirects outside a project but allow Python filesystem-write shell text. A valid `draft: true` workflow is usable before an explicit acceptance operation. Backend-native sandboxing is a separate layer; these observations do not establish escape from it.

Direction: retain the small flow kernel; bind completion to run/project/expected step with idempotency, require current-attempt output evidence, refuse stopped-project movement, keep OKs on a trusted app path, and constrain each designer to an individually accepted candidate. Update copied CI and distinguish website demos from shipped per-step human ownership. Evidence: `docs/plans/2026-10-13-newtworks-comparison.md`, `research/newtworks-audit-20261013.py` and `.json`. Verification: Python rerun and mobile logic logs referenced there. Newtworks source was read-only; no production state was changed. Research evidence files are local and git-ignored.

Status: open (analysis only; no fixes implemented in this session)

## Q-005: How should the shared visual substrate own resources and bound design cost? (added 2026-10-13)

Engineering direction from the PI-requested design audit. Both products reuse the same kit/component/layout/model sources but maintain separate art/scene copies; the phone adds another scene implementation. Isolated browser diagnostics show GPU geometry/texture counts grow with theme changes and do not fall when actors are removed; ambient-off rendering continues and desktop reduced mode animates stationary rigs. Validator-only probes accept unknown references, out-of-room stations, unbounded/nonfinite props, global built-in overrides and a custom instance expansion above the definition-part cap. No extreme geometry was built and no real app state was changed.

Direction: establish per-world/actor ownership and safe shared-cache disposal, palette updates without rebuilding, bounded detail/quality settings, a common motion policy, component bounds/interaction ports and instance-expanded cost validation. Then extract a small shared art package and expand accessories, character-specific locomotion, furniture interaction and world finishes. Evidence: `docs/plans/2026-10-13-design-substrate-audit.md`, `output/playwright/design-audit/report.json`, `source-report.json`, `world-tests.xml`; scratch probe sources under ignored `research/`. Final browser diagnostics used fresh software-WebGL processes, with shadows disabled after the production baseline; counters are not hardware frame-rate measurements.

Status: open (analysis and expansion plan; implementation not requested in this session)

Update 2026-10-13 (PI-authorized implementation): initial substrate fixes now applied to both codebases, including Newtworks phone bundles and website art copies. RECIPE: track actual live mesh resource users, release only at the last user, and preserve appearance-only switches in place. Validate every consumer against the same typed object catalog before adding assets; ignored prop parameters in phone/site scenery became invalid under the stricter contract and were corrected. Keep semantic poses current when stopping animation and explicitly wake reduced renderers for user input. Evidence: `docs/plans/2026-10-13-design-implementation.md`, `docs/design-runtime.md`, `output/playwright/design-implementation/{report,deliverables-report,previews-report,site-report,source-parity}.json`. These are engineering checks, not research findings or device FPS evidence.

Status: foundation implemented; shared packaging, structural diff/batching, crowds/contact poses, expansion packs, stronger world accessibility and physical-device validation remain open. The earlier analysis-only status above is historical.

Planning update 2026-10-13: the next generalizable authoring direction is reusable JSON recipes/room instances/clips, named anchors with optional interaction ports, and two placement forms (absolute or anchor+offset) resolved by one compiler before rendering. Add bounded semantic animation clips with fixed channel layers and per-character capability adapters; deliver a small cute motion/content pack with the first implementation. Avoid a runtime constraint solver, arbitrary expressions/scripts, full animation graph or universal retargeter. The creator writes only its candidate, while trusted compilation/acceptance emits reproducible manifests; schema restrictions do not replace filesystem/tool confinement. Plan: `docs/plans/2026-10-13-expandable-design-language.md`. Status: proposed; no new runtime language or production code implemented in this planning session.

Scope revision 2026-10-13: the PI now requires 3D collision physics and more expressive resource design, plus caricature/polish for the six newer Newtworks characters. The previous primitive-only recipe and deferred-physics boundaries are superseded. Proposed bounded curved geometry/parameters/repeated layouts and one real physics adapter (Rapier candidate, pending cross-consumer proof). DIRECTION: separate path intent, collision-constrained root motion and local animation; verify simultaneous actor-pair contact, doorway/crowd recovery, hover/glide and dynamic carry/release rather than treating kinematic bodies as an automatic crowd solver. Preserve core-volume proxy bounds independently of render detail, and polish species silhouette/motion before tiny decoration. Evidence/proposal: `docs/plans/2026-10-13-expressive-design-physics-character-polish.md`; visual baseline `output/playwright/design-audit/newtworks-cast.png`; official physics references linked in the plan. Status: planned, not implemented or device-benchmarked.


## 2026-10-15 — DIRECTION: evidence access before more workflow machinery

The Lab audit found that remote execution and HTML summaries work while several paper audits still
expect a local project tree. Extend the existing worker read/export seam with a shared, hash-aware
evidence reader before claiming remote paper verification. Some audits also retain ML seed/metric
assumptions despite theory/empirical/simulation cards; define small typed evidence contracts rather
than inventing surrogate seeds. A shorter exploration/replication preset and explicit findings review
state would improve the starter journey without replacing the workflow engine. Details and evidence:
docs/plans/2026-10-15-lab-experience-audit.md.

## 2026-10-16 — Codex Windows publication read denial

A real Codex task could read uploaded materials and create HTML, but its publisher could not read
that HTML; a second new shell-written file met the same denial, as did a hub bus tool read. Resolve
active profile/managed permissions/Windows file access before claiming real end-to-end publication
on this installation. No ACL or sandbox changes were attempted. Provider-neutral fixture checks
passed. Evidence: output/verification/codex-records-recovery.json and
 docs/plans/2026-10-16-backend-records-audit.md.

## 2026-10-16 — RESOLVED: Windows publication read denial

The failed fixture used an owner-only protected temporary directory. The Lab and Codex sandbox use
different Windows identities, so owner-only inheritance broke reciprocal reads. A normally inherited
workspace passed a real Codex brief-to-HTML-to-publication check. Clone staging and Codex shared
workspace declarations were corrected; no global ACL or sandbox setting changed. See
 docs/plans/2026-10-16-windows-publication-fix.md and
 output/verification/codex-records-inherited.json. The earlier unresolved entry is retained as history.

## 2026-10-19 — Hub engineering: bind collector execution to reviewed code

Q01: a controlled edit after the approved-hash check but before process launch executed changed
collector bytes once. The next check rejects them. Preserve working-directory/path behavior while
closing this execution gap; the displayed-SHA approval fix alone does not close it. Evidence:
output/verification/quick-audit/collector-race.json; details and priorities in
output/artifacts/quick-audit-2026-10-19.md. No product fix made during the quick audit.

## 2026-10-19 — RESOLVED: collector source edit at execution

Q01 now checks captured custom-collector bytes and executes their temporary sibling copy. An
edit before checking is refused; one at launch cannot replace the checked script. The original
path is exposed as NEWTS_COLLECTOR; cwd/sibling resources remain. This covers script bytes, not
their other dependencies. Evidence: output/verification/evidence-recovery/collector-race.json and
verified-tests.txt. The original finding is retained above as history.
