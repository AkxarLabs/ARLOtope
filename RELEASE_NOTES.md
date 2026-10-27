# Beta notes

ARLOtope lets you visually manage agent teams across research projects. This beta includes the
workflow editor, project records, agent assignments and recovery controls. The code is available
on `main`; tagged releases are listed on GitHub.

## Included

- Start with a question, attach an existing project, or clone a GitHub repository, using the
  connected account for private repositories. Add
  supporting materials and reuse existing work without changing the original project environment.
- Compose tasks, skills, rooms, branches, loops and configurable checkpoints. Choose fresh,
  continued or forked conversations where the selected harness supports them.
- Use Claude Code, Codex, opencode or an ACP adapter. Seven task sessions are allowed by default;
  independent reviewers, explainers and assistants do not consume task slots.
- Keep study-scoped documents, retained sources, human notes, saved Q&A, outputs and workflow
  histories. View Markdown and sandboxed HTML summaries in the dashboard.
- Connect project machines over SSH. Machine and unified world views change presentation, not
  execution. Studies share defined rooms; adding a study does not create another room set.
- Use optional external command-and-artifact workflow tasks, including the Sakana preset. Missing
  dependencies remain unavailable until installed; external tools retain their own requirements.

## Defaults and boundaries

Agent launching ships off. Creating a study does not start an agent or approve a checkpoint.
An agent turn ending does not complete a task without an accepted outcome. Failed or interrupted
work remains visible for recovery. Credentials stay in the harness or SSH login flow.

Lab workflow controls govern recorded progression. Tool execution also depends on harness and
account permissions; prompt instructions and shell-pattern guards are not a universal OS sandbox.
ACP capabilities vary by server. Remote access requires working SSH authentication, and a lost
connection may require signing in again. See the [agent compatibility guide](docs/running-work.md#agent-compatibility),
[recovery guide](docs/recovering-work.md) and [remote connections](docs/remote-projects.md).

## Known limits

- Intermittent asset failures observed during earlier combined-load stress have not been fully
  diagnosed. The interface has a reload notice; a passing stress run does not establish that the
  historical problem is eliminated.
- Automated tests and recorded live smokes cover different scopes. They do not certify every CLI
  version, provider, native fork, desktop browser or SSH authentication environment.
- External-framework visibility depends on emitted activity and declared artifacts. It does not
  grant control over internal workers or make an external tool's checkpoints Lab checkpoints.
- Further CSS/helper cleanup and wider accessibility/lifecycle review remain follow-up work.

The default license is AGPL-3.0-only. Reusable templates remain MIT; third-party components retain
their notices. Research projects and ordinary research outputs keep their own licenses. See
[licensing](docs/licensing.md).
