# Contributing to ARLOtope

Contributions to the dashboard, tools, procedures, templates and documentation belong here.
Your research records and project repositories belong to your Lab, rather than a product pull request.

Contributions to the Lab are under **AGPL-3.0-only**, unless an explicitly licensed component uses
different terms (including the MIT reusable templates). Preserve third-party notices. See
[licensing](docs/licensing.md) for the scope and source-sharing requirements.

## Development

Install Git, Python 3.10+ and [uv](https://docs.astral.sh/uv/). Clone your fork and create a branch
for one focused change. The hub resolves Python dependencies per command; spawned projects have
their own environment and lockfile. The dashboard uses vendored browser dependencies and needs
no frontend build.

Use a separate scratch Lab to exercise study creation, real agents or remote connections.
Keep personal research, credentials, machine connections and generated run files out of a PR.
Review the diff before committing; do not reset someone else's local Lab state to clean a test.

The shipped configuration is `lab/config.defaults.yaml`. First use creates an ignored, almost empty
`lab/config.yaml` that holds only a person's own changes. Product changes to defaults belong in the
former; personal preferences belong in the latter. Study folders and local Lab records are ignored. This prevents ordinary staging,
not deliberate `git add -f`; inspect `git diff --cached` before pushing.

## Checks

Run the checks relevant to your change, then the CI checks before submitting:

```bash
uv run --with pyyaml python tools/check_lab.py
uv run --with pyyaml --with pytest python -m pytest tests/ -q
uv run --with pyyaml python -c "import sys; sys.path.insert(0,'dashboard'); import sources; print(sources.snapshot()['cold'])"
uv run --with properdocs --with mkdocs-material properdocs build --strict
```

[CI](.github/workflows/ci.yml) tests the tools and generated project on Linux, Windows and macOS.
Changes to `templates/project/` also need the template smoke checks, including an end-to-end
toy run. Tests use isolated Lab fixtures; never point a test at a real research project.

## Where to make changes

| Area | Source |
|---|---|
| Workflows, checkpoints and research rules | `workflow/` |
| Agent procedures | `.claude/skills/<name>/SKILL.md` |
| Subagent roles | `agent-roles/`, rendered by `tools/role_sync.py` |
| Agent execution and harness adapters | `tools/executor/` |
| Project scaffold | `templates/project/` |
| Dashboard and visual Lab | `dashboard/` |
| User guides and site theme | `docs/`, `properdocs.yml` |

Read [AGENTS.md](AGENTS.md) before changing research behavior. Configuration values belong in
configuration files; procedures describe how to use them. Preserve old experiment configurations,
explicit workflow outcomes and the separation between a task ending and a checkpoint being approved.
An independent judge can decide only a checkpoint explicitly delegated to it.

The kernel owns `lab/journal.jsonl` and generates `lab/REGISTRY.md`; do not edit either manually.
Project experiment logs and run registries are append-only. Add corrections instead of rewriting
research history. Test path resolution with a scratch hub passed explicitly or patched at the
module boundary; avoid cached global state that escapes a fixture.

## Documentation and interface changes

Use the dashboard's visible labels and short, concrete language. Explain the next useful action
before exposing advanced settings. Check keyboard navigation, narrow screens and both themes.
Use the [interface language guide](docs/ui-copy.md) for copy changes.

Add public pages to `properdocs.yml`, preserve inbound anchors, and build with `--strict`.
Screenshots in `docs/assets/current/` show an isolated example Lab with execution disabled.
Capture real components with representative sample data; label illustrative remote results and
never include credentials or private research. Keep screenshots small and record their provenance.
Historical plans under `docs/plans/` are excluded from the public site.

## Pull requests and issues

Describe the concrete problem, resulting behavior and validation. Include screenshots for visible
changes and state any platform or provider behavior you could not test. Keep unrelated changes
out of the patch, including personal settings and build output.

For an issue, include the action or command, expected behavior, actual behavior, OS and browser,
and relevant redacted errors. Mention whether the problem occurs with example data as well.
