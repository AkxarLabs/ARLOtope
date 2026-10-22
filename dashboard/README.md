# Research dashboard

A local, no-build interface for ARLOtope. Start it with `uv run --with pyyaml python arlotope.py`.
The CLI, native procedures and executor also work without this interface.

The shell is `static/ui/app.js`; Lab is the primary page and `home.js` provides the overview. `starter.js` and `starter.py`
provide question-first creation and non-invasive local/GitHub attachment through
`tools/research_start.py`. Saving a study does not launch an agent or approve a checkpoint.

`compose.py` and `static/ui/compose.js` edit the existing kernel definitions in a reviewed draft.
The ordinary `/design` procedure proposes overlays through the same path. No visual designer runtime
is required. `sources.py` reads the Lab, `runops.py` adapts the existing executor, and `decisions.py`
records decisions through the kernel journal. `serve.py` wires the HTTP routes and protections.

Presentation is split into shared primitives (`ui.css`), shared research controls (`controls.css`)
and the editorial research shell (`research.css`). Fonts and browser libraries are vendored.

`static/lab-view.html` owns the primary renderer and three agent characters. It receives
state through checked same-origin frame messages and emits navigation requests. After the first
visit, its scene is retained between routes and rendering pauses while hidden. `room_design.py` and `ui/room-design.js` reuse this
renderer for private room drafts. `ui/workflow-canvas.js` edits the existing workflow definition;
`assistant.py` reuses the ordinary executor for a continuing workspace conversation. Full skins,
physics and visual studios stay in Newtworks.

`knowledge_api.py` reads project-local Markdown records through `tools/knowledge.py`; `library.py`
combines existing documents with records and published outputs. Human notes do not launch work.
The workspace assistant saves Q&A separately and uses the normal executor and evidence tools.

See `docs/research-first.md`, `docs/dashboard.md` and `docs/internals.md` for usage and architecture.
