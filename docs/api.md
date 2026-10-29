# Operate the Lab from a terminal or agent

The dashboard and CLI use the same local HTTP API. Start the Lab first:

```bash
./arlo --background --no-browser
./arlo api GET /api/state
./arlo api routes --output api-schema.json
./arlo open my-study
```

On Windows use `.\arlo.cmd`; `uv run --with pyyaml python arlo.py` also works on all platforms.
Add `--hub /path/to/lab` after the command to select another Lab. Discovery checks the Lab's
identity. An explicit `--port 8787` instead targets that server, including a forwarded SSH port.
`arlo open my-study --print` prints a dashboard link without opening a browser.

`api` accepts `GET`, `POST` and `HEAD`. Request data may be a JSON/YAML object, `--data @file.yaml`,
or `--data -` from stdin. Repeat `--query name=value` for query fields. `--output FILE` saves the
raw response, including downloads. Exit codes: 0 for HTTP success, 1 for an HTTP error, 2 for a
client/input error. Writes are never retried automatically: check the saved record before retrying
after a lost connection.

## Find an operation

`GET /api/schema` returns an OpenAPI route index generated from the running server. It lists all
registered read, write and download routes, composition operations and core request fields.
It is a discovery index, not an exhaustive typed contract for every nested object. Workflow YAML
and the individual operation validate the full request. Invalid requests return an `error` field
and an HTTP error status.

| Work | Routes |
|---|---|
| Inspect the Lab, studies and attention | `GET /api/state`, `/api/starter` |
| Create or attach a study | `POST /api/starter` |
| Read workflow definitions and drafts | `GET /api/compose`, `/api/compose/file` |
| Compose tasks, rooms, skills and gates | `POST /api/compose` |
| Start ready workflow tasks | `POST /api/workflow/run` |
| Launch, inspect and steer agents | `POST /api/run`, `/api/run/reply`, `/api/run/answer`; `GET /api/run`, `/api/run/tail` |
| Ask the workspace assistant | `POST /api/assistant/message`; `GET /api/assistant` |
| Notes and retained records | `GET /api/knowledge`; `POST /api/knowledge/note` |
| Workflow history | `GET /api/study/history`; `POST /api/study/history/save` |
| Browse documents and outputs | `GET /api/library`, `/api/artifacts`; `POST /api/libdoc` |
| Agents and API providers | `GET`/`POST /api/agent-settings`, `/api/providers` |
| Connect machines and browse projects | `/api/project-machines` and its operations in the schema |

For publishing an HTML/Markdown output, use `tools/artifact.py publish`; for adding sources,
attachments or progress records, use `tools/knowledge.py`. These file-oriented tools work without
an open browser and feed the same Library. See [outputs](artifacts.md) and [knowledge](knowledge.md).

## Create and run a study

```yaml
# study.yaml — local is optional; omit it for a new question
confirm: true
slug: evidence-check
title: Evidence check
question: Which observations support this claim?
local: /absolute/path/to/existing/project
workflow: quick
```

```bash
./arlo api POST /api/starter --data @study.yaml
./arlo open evidence-check
./arlo api POST /api/workflow/run --data '{study: evidence-check}'
./arlo api GET /api/study/history --query study=evidence-check
./arlo api POST /api/study/history/save --data '{study: evidence-check}'
```

Creation starts no agent. Launches must be enabled, the selected harness must be installed and
signed in on the execution host, and checkpoints still apply. Use `GET /api/starter` for available
workflows and `POST /api/starter/plan` to validate an existing-work/skip plan before creation.

## Compose and reuse skills

Use the same draft/review/publication boundary as the visual editor:

```bash
./arlo api POST /api/compose --data '{op: workflow, id: evidence-flow, new: true, like: quick, fields: {title: Evidence flow}}'
./arlo api GET /api/compose --output draft.json
```

`op: graph` replaces a workflow's task graph with ordinary [workflow node definitions](workflow.md).
For example, after choosing an existing room ID from `GET /api/compose`:

```yaml
op: graph
workflow: evidence-flow
nodes:
  - id: inspect
    label: Inspect evidence
    room: study
    instructions: Read the supplied evidence and list supported and unsupported claims.
    agent: {role: analyst}
    context: {mode: fresh}
    next: []
```

Room IDs are Lab-defined; replace `study` if your Lab uses another ID. For raw YAML editing, use
`{op: write, path: workflow/workflows/evidence-flow.yaml, text: "..."}`. Import a local skill folder
with `{op: skill-import, path: /absolute/path/to/skill}`. Existing names are refused rather than
overwritten. Add `preview: true` to the same import request to inspect it without importing.

Inspect the draft's changes and problems, then publish explicitly:

```bash
./arlo api POST /api/compose --data @graph.yaml
./arlo api GET /api/compose
./arlo api POST /api/compose --data '{op: publish, note: Add evidence workflow}'
```

Publication changes the shared Lab definition. A managed working agent may prepare a draft;
the PI publishes it. Normal run outcome reporting remains `arlo move`, not a human decision API.

## Ask questions and leave notes

```bash
./arlo api POST /api/assistant/message --data '{study: evidence-check, text: What supports the current conclusion?}'
./arlo api GET /api/assistant
./arlo api POST /api/knowledge/note --data '{study: evidence-check, text: Please consider the second dataset., acknowledge: true}'
./arlo api GET /api/knowledge --query study=evidence-check
```

The assistant answers asynchronously in a separate agent session and saves its answer as a
separate knowledge record. Include `run` and optionally `agent` to focus on a run or recorded
subagent; include `preset` to choose a saved agent. A note is context, not a queued task or approval.

Save API-backed agent choices through `/api/agent-settings`. `settings.presets` is the complete
Lab preset map: read it first and merge, preserving other choices. A preset is ordinary data:
`{label: "My API agent", backend: opencode, model: "openrouter/<model-id>"}`. Set
`settings.default_preset` or `settings.role_presets` to assign it. Read back the settings to verify.

## HTTP access and trust

For a custom client, `GET /api/session` obtains the same HttpOnly, SameSite session cookie as the
dashboard. Retain it for subsequent requests. The server listens on loopback and rejects foreign
browser origins. Use an SSH tunnel to reach another machine; this is not a public hosted API.
`X-Arlotope-Local: 1` targets the server's owning Lab even when its dashboard is showing a connected
Lab. The CLI always sets it and does not follow redirects or use HTTP proxies.

API-provider keys are independent of this local session. Use interactive `--secret key` or stdin
to avoid putting keys in shell history. Never commit request files containing secrets.

Managed agent CLI calls keep `ARLOTOPE_RUN_ID` as their parent when starting work and obey nesting
limits. The client reserves study creation, PI-owned decisions and shared publications for the PI; configuration procedures
retain their existing exception. These are protocol checks in a same-account application, not
OS isolation from another local program. See [approvals](monitoring.md).
