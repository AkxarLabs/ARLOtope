"""Hermetic test harness for the hub's trust tools.

Every hub tool resolves paths from a module-global ``HUB = Path(__file__).resolve().parents[1]``
(and some have ``LAB = HUB / "lab"``). The tools read those globals *at call time*, so each test
loads the tool as a fresh module object and ``monkeypatch.setattr``-s its globals to a throwaway
``tmp_path`` fake hub built by the ``hub`` fixture. Nothing here touches the real lab, the network,
or a port — pure ``tmp_path`` and in-process function calls.

Exposed:
  REPO         — absolute Path to the repo root (so tests load the *real* tool source).
  load(name)   — import a tool module fresh from ``REPO/tools/<name>.py`` (or a full relative path).
  hub fixture  — builds a minimal fake hub under tmp_path and returns a small handle object.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import textwrap
from pathlib import Path

import pytest

# tests/ lives directly under the repo root.
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))

# a supervisor that exits with work left starts its own scheduler when none is running (the dashboard
# was closed) — never inside the test suite, where each test drives the scheduler itself
os.environ.setdefault("ARLOTOPE_NO_AUTOTICKER", "1")
# the suite runs under `uv run --with …` (a throwaway env) but lives shorter than it: keep this interpreter
# for the processes it starts instead of building the durable ~/.arlotope/py one
os.environ.setdefault("ARLOTOPE_KEEP_PYTHON", "1")


@pytest.hookimpl(tryfirst=True)
def pytest_cmdline_main(config):
    """Each run keeps its temp dirs in its own folder under tests/ (gitignored): the OS temp base is not
    writable in some sandboxes, and one shared --basetemp is wiped by every run, so concurrent runs would
    collide. xdist workers nest under it. Pass --basetemp to choose the place."""
    if config.option.basetemp is None:
        config.option.basetemp = Path(__file__).parent / f".pytmp-{os.getpid()}"


def pytest_sessionfinish(session, exitstatus):
    """A passing run leaves nothing behind (a failing one keeps its folder to look into)."""
    base = session.config.option.basetemp
    if exitstatus == 0 and base and Path(base).name.startswith(".pytmp-") and not hasattr(session.config, "workerinput"):
        shutil.rmtree(base, onerror=lambda fn, path, _exc: (os.chmod(path, 0o700), fn(path)))   # git objects are read-only on Windows


def load(name: str):
    """Load a tool module fresh from the repo, by short name or relative path.

    ``load("guard")``  -> REPO/tools/guard.py — a short name is looked up in tools/, then checks/, then
                          the skills' own tools (.claude/skills/*/tools/)
    ``load("dashboard/sources")`` -> REPO/dashboard/sources.py
    Each call produces an independent module object so a test's global overrides never leak.
    """
    if "/" in name or name.endswith(".py"):
        rel = name if name.endswith(".py") else f"{name}.py"
        path = REPO / rel
        mod_name = f"_hubtest_{Path(rel).stem}_{abs(hash(rel))}"
    else:
        hits = [REPO / "tools" / f"{name}.py", REPO / "checks" / f"{name}.py",
                *sorted((REPO / ".claude" / "skills").glob(f"*/tools/{name}.py"))]
        path = next((h for h in hits if h.is_file()), hits[0])
        mod_name = f"_hubtest_{name}_{abs(hash(name))}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    # Register so dataclasses / relative imports that look themselves up resolve.
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def approve(hub_root, study, checkpoint, decision="approved", by="pi", via="cli", note="", **extra):
    """Record a decision straight into the journal (a test's setup — the kernel's rules are tested elsewhere)."""
    k = kernel()
    return k.journal.append(hub_root, study, "approval", by, checkpoint=checkpoint, decision=decision, via=via,
                            note=note, **extra)


# ── the fake-hub fixture ──────────────────────────────────────────────────────

_CONFIG_YAML = textwrap.dedent(
    """\
    lab:
      projects_root: "../projects"
      stale_days: 14
    compute:
      max_concurrent_runs: 1
      stale_slot_minutes: 360
    dashboard:
      port: 8787
    """
)

_REGISTRY_HEADER = "# Lab Registry\n"


def kernel():
    """The kernel package from this repo's tools/ (where every tool imports it from)."""
    if str(REPO / "tools") not in sys.path:
        sys.path.insert(0, str(REPO / "tools"))
    import kernel as k  # noqa: PLC0415
    return k


class FakeHub:
    """Handle to a fake hub built under tmp_path. ``root`` is the hub dir; ``projects_root`` is its
    sibling project root (``../projects`` per the fixture config)."""

    def __init__(self, root: Path):
        self.root = root
        self.lab = root / "lab"
        self.projects_root = (root / ".." / "projects").resolve()
        self._rows: list[dict] = []

    # --- studies (the kernel's journal) --------------------------------------------
    def add_registry_row(self, id, title="T", state="seed", idea="-", project="-",
                         paper="-", updated="2026-06-19", next="-", workflow=None):
        """File a study standing at `state` (a shelf: filed, then shelved; the workflow's last step: finished),
        with its project path when given — as the kernel records it (lab/journal.jsonl)."""
        k = kernel()
        wf = k.model.workflow(workflow, self.root)
        at = state if state in wf["path"] else wf["path"][0]
        k.studies.new(self.root, id, title, workflow=workflow, at=at, by="cli")
        if state in k.model.SHELF_LABEL:
            k.studies.move_to(self.root, id, state, by="pi")
        elif state != at:
            raise ValueError(f"{state!r} is not a step of the {wf['id']} workflow")
        elif state == wf["path"][-1]:
            k.journal.append(self.root, id, "finish", "cli")
            k.studies.render_registry(self.root)
        if project not in ("-", "", None):
            k.studies.set_project(self.root, id, project, by="cli")
        self._rows.append(dict(id=id, title=title, state=state, project=project))
        if not k.studies.study(self.root, id)["finished"] and state not in k.model.SHELF_LABEL:
            self.produce(id)                     # filed at a step, with that step's work written

    def study(self, slug):
        return kernel().studies.study(self.root, slug)

    def produce(self, slug):
        """Write what the study's current step must produce (its procedure's outputs in studies/<slug>/), as a
        procedure that finished its work would — so `done` can be reported."""
        k = kernel()
        for rel in k.studies.missing_outputs(self.root, k.studies.study(self.root, slug)):
            f = self.root / rel
            if rel.endswith("/"):
                f.mkdir(parents=True, exist_ok=True)
            else:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(f"# {f.name}\n", encoding="utf-8")

    # --- project scaffolding --------------------------------------------------
    def make_project(self, slug: str, *, control: bool = True, eval_frozen=True,
                     gate2=None, in_root: bool = True) -> Path:
        """Create a project dir (under projects_root by default) with a minimal control.yaml. `gate2` writes an
        older lab's `gate2_envelope` block (only tools/migrate_approvals.py still reads it)."""
        pdir = (self.projects_root / slug) if in_root else (self.root / ".." / "elsewhere" / slug).resolve()
        pdir.mkdir(parents=True, exist_ok=True)
        if control:
            self.write_control(pdir, eval_frozen=eval_frozen, gate2=gate2)
        return pdir

    def write_control(self, pdir: Path, *, eval_frozen=True, gate2=None):
        import yaml
        doc = {
            "eval_frozen": eval_frozen,
            "budgets": {"max_minutes": 10},
            "seeds": [0, 1, 2],
        }
        if gate2 is not None:
            doc["gate2_envelope"] = gate2
        (pdir / "control.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    def write_metrics(self, pdir: Path, rel: str, data: dict):
        import json
        f = pdir / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data), encoding="utf-8")
        return f

    def notebook_entry(self, name: str, body: str):
        nb = self.lab / "notebook"
        nb.mkdir(parents=True, exist_ok=True)
        (nb / name).write_text(body, encoding="utf-8")


@pytest.fixture
def hub(tmp_path) -> FakeHub:
    """A minimal fake hub: lab/config.yaml (projects_root -> ../projects), REGISTRY.md header,
    empty knowledge/notebook dirs. Sibling projects_root is created too."""
    root = tmp_path / "hub"
    lab = root / "lab"
    (lab / "knowledge").mkdir(parents=True, exist_ok=True)
    (lab / "notebook").mkdir(parents=True, exist_ok=True)
    (lab / "config.yaml").write_text(_CONFIG_YAML, encoding="utf-8")
    (lab / "REGISTRY.md").write_text(_REGISTRY_HEADER, encoding="utf-8")
    for kf in ("FINDINGS.md", "FAILURES.md", "OPEN-QUESTIONS.md", "REFERENCES.md"):
        (lab / "knowledge" / kf).write_text(f"# {kf}\n", encoding="utf-8")
    h = FakeHub(root)
    h.projects_root.mkdir(parents=True, exist_ok=True)
    return h


@pytest.fixture(autouse=True)
def isolated_user_state(tmp_path, monkeypatch):
    """Fixtures must not register simulated projects or machines in the user's real state."""
    monkeypatch.setenv('ARLOTOPE_HOME', str(tmp_path/'arlotope-user-state'))


@pytest.fixture
def inbox():
    """A local HTTP server that records every POST (stands in for ntfy / a webhook)."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    got = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
            got.append({"path": self.path, "headers": dict(self.headers), "body": body})
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", got
    srv.shutdown()
