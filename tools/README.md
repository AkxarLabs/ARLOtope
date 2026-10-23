# tools/ — the harness

The code that records workflow progression and connects the
dashboard to coding agents. Everything a lab *defines* lives elsewhere: procedures in
`.claude/skills/` (with their method helpers in each skill's own `tools/`), the workflow and the rules in
`workflow/`, mechanical checks in `checks/`, roles in `agent-roles/`, templates in `templates/`. stdlib +
pyyaml; run with uv's ephemeral env:

```bash
uv run --with pyyaml python arlo.py <verb> …                          # `arlo`: the whole lab from a terminal (status, move, approve, brief, check, docs, …)
uv run --with pyyaml python tools/guard.py <check> <slug> …           # run one of the lab's checks/ (--list)
uv run --with pyyaml python tools/new.py skill|step|workflow|room|role|check|type|rule <name> --like <existing>   # add by copying
uv run --with pyyaml python tools/check_lab.py                        # lab lint (registry, wiring, workflow)
uv run --with pyyaml python tools/configure.py view|set|profile …     # owner-aware config edits
uv run --with pyyaml python tools/show_config.py [<project> [exp.yaml]]  # 3-layer config with provenance
uv run --with pyyaml python tools/panels.py list | show <id>          # the lab's panels (instruments)
uv run python tools/lab_bus.py emit|inbox|ack|escalate …             # the event bus + PI directives
uv run --with pyyaml python tools/executor_cli.py enqueue|serve|list|answer|stop …   # headless runs
uv run --with pyyaml python tools/upgrade_project.py --all [--check]  # bring older projects up to date
```

| Group | Files | What they do |
|---|---|---|
| **The kernel** | `kernel/` | the lab's definition (`workflow/steps.yaml`, `workflow/workflows/`, `workflow/rooms.yaml`, the skills' frontmatter), where every study stands (`lab/journal.jsonl`, REGISTRY.md generated from it), moving a study by an outcome, checkpoints and approvals, the brief, the PI's instructions, a draft's or an extension's overlay, run digests and flags, migrating an older lab — see `docs/workflow.md` |
| **Checks and protections** | `guard.py`, `signature_guard.py` | run the lab's `checks/`; refuse a headless run that writes the PI's records or the lab's definition, or runs the PI's verbs (it fails open with a flag — `docs/monitoring.md`) |
| **The lab's files** | `labfiles.py`, `new.py`, `lab_docs.py` | the lab's files read one way; adding a component by copying one; the generated parts of the manuals and skills |
| **The PI's terminal** | `arlo_cli.py` | `arlo <verb>`: everything the dashboard does, from a terminal (status, approve, revoke, hold, pause, panels, …) |
| **Instruments** | `panels.py`, `artifact.py` | the dashboard's panels (the shipped Compute panel tracks GPU-hours and raises alerts); a collector runs only once the PI approved that version; show the PI an artifact |
| **Observability** | `lab_bus.py`, `trace_hook.py` | the append-only event bus and directive inbox; the per-agent action tracer (both ship into every project too) |
| **Coordination** | `hub_writeback.py`, `process_writebacks.py` | the project→hub write-back boundary |
| **Agents** | `executor/`, `executor_cli.py`, `lab_profile.py`, `role_sync.py` | launch Claude, Codex, opencode or configured ACP agents; provide Lab briefs and campaign coordination; pause launches or hold a study (`executor/pause.py`); render native role files |
| **Knowledge** | `knowledge.py`, `project_identity.py` | project identity, plain Markdown notes/sources/answers, search, read acknowledgements and separate workspace-answer persistence |
| **Remote projects** | `remote_projects.py`, `project_worker.py`, `project_control.py`, `ssh_worker_install.py` | existing SSH connections, a small project execution worker, mirrored run evidence and owning-Lab control requests |
| **Setup and config** | `spawn_project.py`, `new_lab.py`, `configure.py`, `profiles.py`, `show_config.py`, `check_lab.py`, `upgrade_project.py`, `system_probe.py`, `terminal.py` | stamp projects and labs; owner-aware config; lint; what this machine offers; a terminal for a CLI's sign-in |

Exit codes for checks: **0 = OK · 1 = BLOCKED · 2 = WARN**. A check never grants an approval; approvals are
the PI's (or a campaign's, or an automatic checkpoint's whose checks pass), recorded in the journal. See `docs/tools.md` for each tool and `docs/extending.md` for adding to the
lab.
