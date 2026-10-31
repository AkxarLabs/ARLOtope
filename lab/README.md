# Local Lab records

This folder holds this installation's settings and research records. Git ignores personal state;
ignoring a file does not delete it or back it up.

| Path | Purpose |
|---|---|
| `config.defaults.yaml` | Every setting and its default; tracked as product source |
| `config.yaml` | Only the settings you changed, laid over the defaults; created almost empty on first use |
| `identity.json` | Stable Lab identity; keep it when moving or restoring this Lab |
| `journal.jsonl`, `REGISTRY.md` | Workflow history and its generated view |
| `knowledge/`, `notebook/`, `records/` | Research memory, human notes and saved answers |
| `.bus/` | Managed runs, transcripts, published outputs and directives |
| `workflow/`, `templates/`, `rooms3d/` | Local instruction, template and room customizations |

Back up **this folder and `../studies/` together**, plus the external project repositories. Restore
the same Lab identity and journal with them. `~/.arlotope/` also contains machine-local discovery,
server information and the durable Python runtime; it is not the research record. Provider accounts
remain in their own tools.

To update the application, review `git status`, stop the dashboard and pull the source changes.
Your `config.yaml` is never overwritten; settings you did not change follow the new defaults. Shared definitions edited under `workflow/`,
`.claude/skills/` or `agent-roles/` are source changes: commit them on your own branch before pulling
and review conflicts. Private research should not be pushed to the public application repository.
