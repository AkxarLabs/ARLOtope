"""The dashboard as an end-to-end product (dashboard/labs.py, decisions.py, campaign.py, settings.py, instructions.py + the serve.py wiring).

Free-form runs, checkpoint decisions (records in the journal; approving the checkpoint a study waits at moves it
on, and with start launches its new step's work; /finalize runs only for a study at its final step), workflows,
swaps and holds, campaign approval, moving a study (revive), research keys, lab settings,
labs (create / open / switch), setup state, and the HTTP protection (session cookie, JSON-only,
Origin: null). Launches only ENQUEUE (the scheduler thread is never started).
"""

from __future__ import annotations

import http.client
import json
import shutil
import sys
import threading

import pytest

from conftest import REPO, approve, kernel, load

K = kernel()

FAKE = REPO / "tests" / "fake_claude.py"


@pytest.fixture
def m(hub, monkeypatch, tmp_path):
    (hub.lab / "config.yaml").write_text(
        'lab:\n  projects_root: "../projects"\n'
        "compute:\n  max_concurrent_runs: 1\n"
        "dashboard:\n  port: 8787\n"
        "agents:\n  programmatic:\n    enabled: true\n    backend: claude\n    max_depth: 1\n"
        "    backends:\n      claude:\n"
        f"        command: {json.dumps([sys.executable, str(FAKE)])}\n", encoding="utf-8")
    (hub.root / "templates" / "loop").mkdir(parents=True)
    shutil.copy(REPO / "templates" / "loop" / "CAMPAIGN.md", hub.root / "templates" / "loop")
    monkeypatch.setenv("NEWTS_HOME", str(tmp_path / "home"))
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    mod = load("dashboard/serve")
    monkeypatch.setattr(mod.ctx, "HUB", hub.root)
    monkeypatch.setattr(mod.ctx, "LAB", hub.lab)
    return mod


def _pi(hub):
    f = hub.lab / ".bus" / "pi-actions.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def _manifest(m, hub, rid):
    return m.executor.find_run(m.executor.Lab(hub.root), rid)[3]


# ── free-form runs ────────────────────────────────────────────────────────────

def test_free_form_run(m, hub):
    out, code = m.runops.launch_run({"prompt": "Summarize the open questions\nand suggest two ideas.", "confirm": True})
    assert code == 200, out
    man = _manifest(m, hub, out["run_id"])
    assert man["skill"] == "ask" and man["kind"] == "ask" and man["command"] is None
    assert man["label"].startswith("Summarize the open questions")
    rd = hub.lab / ".bus" / "agents" / f"{out['run_id']}.d"
    assert (rd / "prompt.md").read_text(encoding="utf-8").startswith("Summarize")
    assert "PI's own instruction" in (rd / "preamble.md").read_text(encoding="utf-8")
    assert _pi(hub)[-1]["prompt"].startswith("Summarize")
    assert m.runops.launch_run({"prompt": "   ", "confirm": True})[1] == 400
    assert m.runops.launch_run({"prompt": "x" * 9000, "confirm": True})[1] == 400
    assert m.runops.launch_run({"prompt": "go", "chain": "loop", "confirm": True})[1] == 400


def test_free_form_run_inside_a_project(m, hub):
    hub.add_registry_row("idea-p", state="active")
    pdir = hub.make_project("idea-p")
    out, code = m.runops.launch_run({"prompt": "check the last pilot", "target": "idea-p", "confirm": True})
    assert code == 200
    assert _manifest(m, hub, out["run_id"])["cwd"] == str(pdir)


# ── checkpoints: decisions are records (dashboard/decisions.py) ──────────────

def _ready_paper(hub, slug="idea-g"):
    """A study whose paper passed internal review: its agent reported `done`; it waits for finalize-paper."""
    hub.add_registry_row(slug, state="internal-review")
    K.studies.move(hub.root, slug, "done")
    paper = hub.root / "studies" / slug / "paper"
    (paper / "reviews").mkdir(parents=True)
    (paper / "reviews" / "meta-review.md").write_text("# Meta\n\n## Decision\n\nAccept.\n", encoding="utf-8")
    (paper / "main.pdf").write_bytes(b"%PDF-1.4 fake")
    return paper


def _appr(m):
    return m.ctx.tool("kernel").journal


def test_finalize_never_launches_without_the_approval(m, hub):
    """A click on /finalize is refused until finalize-paper is recorded approved — a "Gate 3 approved" in
    the paper's notes changes nothing."""
    paper = _ready_paper(hub)
    (paper / "gate3-approval.md").write_text("Gate 3 approved\n- signed_via: dashboard:2026-09-01T10:00\n", encoding="utf-8")
    out, code = m.runops.launch_run({"skill": "finalize", "target": "idea-g", "confirm": True})
    assert code == 400 and "the work of Final" in out["error"]


def test_a_studys_history_is_its_journal(m, hub):
    """The study page's History: filed, moved, waited, approved — and the lab's step renames — oldest first."""
    hub.add_registry_row("tl", state="proposal")
    K = __import__("conftest").kernel()
    K.studies.move(hub.root, "tl", "done", note="proposal written")
    K.checkpoints.decide(hub.root, "tl", "approve-proposal", via="dashboard", note="go")
    out, code = m.decisions.timeline({"study": "tl"})
    kinds = [e["kind"] for e in out["events"]]
    assert code == 200 and kinds[:2] == ["new", "wait"] and "approval" in kinds and kinds[-1] == "move"
    assert out["events"][1]["note"] == "proposal written" and out["events"][-1]["to"] == "setup"
    assert m.decisions.timeline({"study": "../x"})[1] == 400
    assert "/api/study/timeline" in m.GET_ROUTES


def test_checkpoint_sheet_shows_where_the_study_stands(m, hub):
    _ready_paper(hub)
    out, code = m.decisions.checkpoint_view({"study": "idea-g", "id": "finalize-paper"})
    assert code == 200 and out["here"] and out["waiting"] and out["waits_at"] == "internal-review" and not out["approved"]
    ev = {e["name"]: e for e in out["evidence"]}
    assert ev["main.pdf"]["exists"] and ev["claims.yaml"]["exists"] is False
    assert [c["name"] for c in out["checks"]] == ["claims", "multiseed", "ablations", "eval", "prereg"]
    assert all(c["code"] is None for c in out["checks"])            # not run yet
    assert m.decisions.checkpoint_view({"study": "idea-g", "id": "nope"})[1] == 400
    assert m.decisions.checkpoint_view({"study": "../x", "id": "finalize-paper"})[1] == 400


def test_decide_approves_moves_and_starts_the_next_steps_work(m, hub):
    """Approving records a decision (pi, dashboard), moves the waiting study on and, with start, launches its new
    step's work; it needs confirm; a changes-request needs a note; a revoke takes it back."""
    _ready_paper(hub)
    body = {"study": "idea-g", "checkpoint": "finalize-paper"}
    assert m.decisions.decide(dict(body))[1] == 400                                       # needs confirm
    assert m.decisions.decide(dict(body, confirm=True, decision="maybe"))[1] == 400
    assert m.decisions.decide(dict(body, confirm=True, decision="changes-requested"))[1] == 400   # say what
    assert m.decisions.decide({"study": "idea-g", "checkpoint": "approve-final-output", "confirm": True})[1] == 400
    out, code = m.decisions.decide(dict(body, confirm=True, note="Mind the ablation table.", start=True))
    assert code == 200, out
    rec = _appr(m).latest(hub.root, "idea-g", "finalize-paper")
    assert (rec["decision"], rec["by"], rec["via"], rec["note"]) == ("approved", "pi", "dashboard", "Mind the ablation table.")
    assert out["moved"]["step"] == "final" and hub.study("idea-g")["step"] == "final"
    man = _manifest(m, hub, out["launch"]["run_id"])
    assert man["skill"] == "finalize" and man["subject"] == "idea-g"
    assert "/finalize started" in out["note"]
    assert _pi(hub)[-1]["action"] == "run.launch" and _pi(hub)[-2]["action"] == "checkpoint"
    kinds = [json.loads(x)["kind"] for x in (hub.lab / ".bus" / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "checkpoint_approved" in kinds
    out, code = m.decisions.decide(dict(body, confirm=True, decision="revoked"))
    assert code == 200 and not _appr(m).approved(hub.root, "idea-g", "finalize-paper")


def test_decide_changes_requested_is_recorded_and_approves_nothing(m, hub):
    hub.add_registry_row("idea-1", state="proposal")
    K.studies.move(hub.root, "idea-1", "done")
    out, code = m.decisions.decide({"study": "idea-1", "checkpoint": "approve-proposal", "confirm": True,
                                    "decision": "changes-requested", "note": "Tighten the kill criteria."})
    assert code == 200 and out["note"] == "your changes went to the agent"
    assert _appr(m).latest(hub.root, "idea-1", "approve-proposal")["decision"] == "changes-requested"
    assert hub.study("idea-1")["waiting"]["checkpoint"] == "approve-proposal"   # it still waits
    assert m.runops.launch_run({"skill": "spawn-project", "target": "idea-1", "confirm": True})[1] == 400
    out, code = m.decisions.decide({"study": "idea-1", "checkpoint": "approve-proposal", "confirm": True})
    assert code == 200 and "launch" not in out                       # approved and moved, nothing started without start
    assert m.runops.launch_run({"skill": "spawn-project", "target": "idea-1", "confirm": True})[1] == 200


def test_chains_reach_finalize_only_through_the_approval(m, hub):
    from executor.scheduler import parse_next   # noqa: E402 — the executor on sys.path via sources
    assert parse_next("/ask do anything") is None
    _ready_paper(hub)
    spec = parse_next("/finalize idea-g")
    lab = m.executor.Lab(hub.root)
    with pytest.raises(m.executor.SpecError):
        m.executor.enqueue(lab, spec)
    K.checkpoints.decide(hub.root, "idea-g", "finalize-paper", via="cli")
    assert m.executor.enqueue(lab, spec)["skill"] == "finalize"


def test_run_checks_runs_and_caches_a_checkpoints_checks(m, hub):
    """A checkpoint with no checks passes trivially; the results are cached for the sheet."""
    hub.add_registry_row("idea-c", state="proposal")
    out, code = m.decisions.run_checks({"study": "idea-c", "checkpoint": "approve-proposal"})
    assert code == 200 and out["results"] == {} and out["passed"] is True
    assert (hub.lab / ".bus" / "checks" / "idea-c" / "approve-proposal.json").is_file()
    assert m.decisions.run_checks({"study": "idea-c", "checkpoint": "nope"})[1] == 400


# ── loop, workflow, holds ─────────────────────────────────────────────────────

def test_the_research_loop_is_an_ordinary_checkpoint(m, hub):
    """Approving a study's research loop is the `approve-loop` checkpoint (its note says the mode) — a campaign
    may be allowed to approve it like any `me-or-campaign` checkpoint."""
    hub.add_registry_row("idea-l", state="active")
    hub.make_project("idea-l")
    out, code = m.decisions.decide({"study": "idea-l", "checkpoint": "approve-loop", "confirm": True, "note": "mode: explore"})
    assert code == 200, out
    rec = _appr(m).latest(hub.root, "idea-l", "approve-loop")
    assert rec["decision"] == "approved" and rec["note"] == "mode: explore"
    assert "approve-loop" in {c["id"] for c in m.campaign.delegable(hub.root)}


def test_set_workflow_swaps_and_hold_a_study(m, hub):
    hub.add_registry_row("idea-w", state="seed")
    assert m.decisions.set_workflow({"study": "idea-w", "workflow": "nope"})[1] == 400
    out, code = m.decisions.set_workflow({"study": "idea-w", "workflow": "quick"})
    assert code == 200 and hub.study("idea-w")["workflow"] == "quick"
    out, code = m.decisions.set_use({"study": "idea-w", "use": {"triage": "discuss"}})
    assert code == 200 and hub.study("idea-w")["use"] == {"triage": "discuss"}
    assert m.decisions.set_use({"study": "idea-w", "use": {"triage": "nope"}})[1] == 400
    out, code = m.decisions.hold_study({"study": "idea-w", "reason": "budget"})
    assert code == 200 and "on hold" in out["note"]
    assert m.runops.launch_run({"skill": "discuss", "target": "idea-w", "confirm": True})[1] == 400
    assert m.decisions.hold_study({"study": "idea-w", "hold": False})[1] == 200


def test_campaign_form_records_its_approval(m, hub, monkeypatch):
    """The form writes the brief and records `campaign:<name>` approved for the lab — that record, not a
    ticked box, is what lets /autopilot run it."""
    out, code = m.campaign.campaign_create({"confirm": True, "fields": {
        "direction": "sparse routing for small MoEs", "ideas": 2, "parallel": 1, "compute_total": "8 GPU-h",
        "full_runs": 3, "full_minutes": 60, "wall_clock": "tonight, 8h", "mode": "execute"}})
    assert code == 200, out
    f = hub.root / out["file"]
    text = f.read_text(encoding="utf-8")
    assert "sparse routing for small MoEs" in text and "carry up to 2 ideas" in text and "___" not in text.split("## Campaign Log")[0]
    assert _appr(m).approved(hub.root, "lab", f"campaign:{f.stem}")       # a journal record
    spec_out, code = m.runops.launch_run({"skill": "autopilot", "args": out["file"], "confirm": True})
    assert code == 200, spec_out
    other = hub.lab / "campaigns" / "2026-01-01-unapproved.md"
    other.write_text(text.replace("- [ ] Authorized", "- [x] Authorized"), encoding="utf-8")
    assert m.runops.launch_run({"skill": "autopilot", "args": "lab/campaigns/" + other.name, "confirm": True})[1] == 400


# ── revive ────────────────────────────────────────────────────────────────────

def test_moving_a_study_and_reviving_a_shelved_one(m, hub):
    hub.add_registry_row("idea-k", state="killed")
    assert m.decisions.move({"study": "idea-k", "to": "lit-review"})[1] == 400                 # needs confirm
    assert m.decisions.move({"study": "idea-k", "to": "nowhere", "confirm": True})[1] == 400
    out, code = m.decisions.move({"study": "idea-k", "to": "lit-review", "confirm": True, "note": "new data"})
    assert code == 200 and "is at Literature review" in out["note"]
    row = next(r for r in m.sources.parse_registry() if r["id"] == "idea-k")
    assert row["state"] == "lit-review"
    ev = _appr(m).events(hub.root, "idea-k")[-1]
    assert (ev["kind"], ev["from"], ev["to"], ev["by"], ev["note"]) == ("move", "killed", "lit-review", "pi", "new data")


# ── keys, settings, setup, docs ───────────────────────────────────────────────

def test_keys_are_stored_but_never_read_back(m, hub):
    assert m.keys.keys_set({"key": "S2_API_KEY", "value": "secret-123"})[1] == 200
    assert "S2_API_KEY=secret-123" in (hub.lab / ".env.local").read_text(encoding="utf-8")
    st, _ = m.keys.keys_status()
    assert "secret-123" not in json.dumps(st) and next(k for k in st["keys"] if k["key"] == "S2_API_KEY")["set"]
    assert "lab/.env.local" in (hub.root / ".gitignore").read_text(encoding="utf-8")
    assert "secret-123" not in json.dumps(_pi(hub))
    assert m.keys.keys_set({"key": "NEWTS_RUN_ID", "value": "x"})[1] == 400
    sup = load("tools/executor/supervise.py") if False else None   # noqa: F841 — _env_local is tested below
    from executor.supervise import _env_local
    assert _env_local(m.executor.Lab(hub.root))["S2_API_KEY"] == "secret-123"


def test_lab_settings_and_setup(m, hub):
    out, code = m.settings.lab_config_set({"confirm": True, "changes": {"name": "Moe lab", "max_concurrent_runs": 2,
                                                                        "venue": "neurips"}})
    assert code == 200, out
    cfg = m.ctx.labfiles.load_yaml(hub.lab / "config.yaml")
    assert cfg["lab"]["name"] == "Moe lab" and cfg["compute"]["max_concurrent_runs"] == 2 and cfg["writing"]["venue"] == "neurips"
    assert m.settings.lab_config_set({"confirm": True, "changes": {"agents.x": 1}})[1] == 400
    assert not m.settings.setup_status()["completed"]
    assert m.settings.setup_complete({})[1] == 200
    assert m.settings.setup_status()["completed"]
    assert m.settings.doc_save({"doc": "system", "text": "# This machine\n1 GPU\n"})[1] == 200
    assert m.settings.doc_get("system")[0]["text"].startswith("# This machine")
    assert m.settings.doc_save({"doc": "../../etc", "text": "x"})[1] == 400


def test_programmatic_switch_inserts_a_missing_key(m, hub):
    (hub.lab / "config.yaml").write_text("agents:\n  programmatic:\n    backend: claude\n", encoding="utf-8")
    out, code = m.runops.set_programmatic({"enabled": True, "confirm": True})
    assert code == 200 and m.ctx.labfiles.load_yaml(hub.lab / "config.yaml")["agents"]["programmatic"]["enabled"] is True


# ── labs ──────────────────────────────────────────────────────────────────────

def test_create_open_and_switch_labs(m, hub, tmp_path):
    dest = tmp_path / "labs" / "second"
    out, code = m.labs.labs_create({"confirm": True, "name": "Second lab", "path": str(dest), "open": False})
    assert code == 200, out
    assert (dest / "lab" / "config.yaml").exists() and not (dest / ".github").exists()
    assert m.ctx.labfiles.load_yaml(dest / "lab" / "config.yaml")["lab"]["name"] == "Second lab"
    listed, _ = m.labs.labs_list()
    assert any(l["path"] == str(dest) for l in listed["labs"])
    out, code = m.labs.labs_open({"path": str(dest)})
    assert code == 200 and m.ctx.HUB == dest.resolve()
    assert m.labs.labs_open({"path": str(tmp_path)})[1] == 400                     # not a lab
    assert m.labs.labs_create({"confirm": True, "path": str(dest)})[1] == 400      # not empty


# ── HTTP protection ───────────────────────────────────────────────────────────

@pytest.fixture
def server(m):
    srv = m.LabServer(("127.0.0.1", 0), m.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()


def _req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    return r.status, dict(r.getheaders()), data


def test_session_cookie_and_json_only(server):
    port = server
    assert _req(port, "GET", "/api/state")[0] == 403                                       # no session
    st, hd, _ = _req(port, "GET", "/")
    assert st == 200
    cookie = hd.get("Set-Cookie", "").split(";", 1)[0]
    assert cookie.startswith(f"newts_{port}=") and "SameSite=Strict" in hd["Set-Cookie"] and "HttpOnly" in hd["Set-Cookie"]
    assert _req(port, "GET", "/api/state", headers={"Cookie": cookie})[0] == 200
    assert _req(port, "GET", "/api/ping")[0] == 200                                        # the launcher's probe
    body = json.dumps({"target": "hub", "text": "hi"})
    assert _req(port, "POST", "/api/directive", body, {"Cookie": cookie, "Content-Type": "text/plain"})[0] == 415
    assert _req(port, "POST", "/api/directive", body, {"Content-Type": "application/json"})[0] == 403
    assert _req(port, "POST", "/api/directive", body, {"Cookie": cookie, "Content-Type": "application/json",
                                                       "Origin": "null"})[0] == 403
    assert _req(port, "POST", "/api/directive", body, {"Cookie": cookie, "Content-Type": "application/json"})[0] == 200


# ── terminal (sign-in / install) — fixed commands only ────────────────────────

def test_terminal_opens_only_fixed_commands(m, hub, monkeypatch):
    sys.path.insert(0, str(REPO / "tools"))
    import terminal
    calls = []
    monkeypatch.setattr(terminal.subprocess, "Popen", lambda *a, **k: calls.append((a, k)))
    monkeypatch.setattr(terminal.shutil, "which", lambda exe: exe if exe == "xterm" else None)
    out, code = m.labs.terminal_open({"purpose": "login", "backend": "claude"})
    assert code == 200, out
    argv = calls[-1][0][0]
    flat = " ".join(map(str, argv))
    assert "auth login" in flat and "fake_claude.py" in flat          # the configured CLI, its own login
    assert m.labs.terminal_open({"purpose": "login", "backend": "rm -rf /"})[1] == 400
    assert m.labs.terminal_open({"purpose": "exec", "backend": "claude"})[1] == 400
    out, code = m.labs.terminal_open({"purpose": "install", "backend": "codex"})
    assert code == 200 and "@openai/codex" in " ".join(map(str, calls[-1][0][0]))
    assert _pi(hub)[-1]["action"] == "terminal.install"


# ── System & compute ──────────────────────────────────────────────────────────

def test_system_probe_and_scheduler_block(m, hub):
    out, code = m.system.system_info({"fresh": "1"})
    assert code == 200 and out["facts"]["cpus"] and "suggested_scheduler" in out["facts"]
    assert out["scheduler"]["kind"] == "local"
    sc = {"kind": "slurm", "stages": ["PILOT", "FULL"], "slurm": {"partition": "gpu", "gpus_per_run": 2, "mem": "32G",
                                                                   "setup": ["module load cuda/12.4"], "extra_args": ["--exclusive"]}}
    out, code = m.system.system_scheduler_set({"scheduler": sc, "confirm": True})
    assert code == 200, out
    cfg = m.ctx.labfiles.load_yaml(hub.lab / "config.yaml")
    got = cfg["compute"]["scheduler"]
    assert got["kind"] == "slurm" and got["slurm"]["gpus_per_run"] == 2 and got["slurm"]["setup"] == ["module load cuda/12.4"]
    assert cfg["compute"]["max_concurrent_runs"] == 1 and cfg["agents"]["programmatic"]["enabled"] is True   # the rest kept
    # a second save replaces the block in place (no duplicate key)
    assert m.system.system_scheduler_set({"scheduler": {"kind": "local"}, "confirm": True})[1] == 200
    text = (hub.lab / "config.yaml").read_text(encoding="utf-8")
    assert text.count("scheduler:") == 1 and m.ctx.labfiles.load_yaml(hub.lab / "config.yaml")["compute"]["scheduler"]["kind"] == "local"
    bad = [{"kind": "pbs"}, {"kind": "slurm", "slurm": {"partition": "gpu; rm -rf /"}},
           {"kind": "slurm", "slurm": {"extra_args": ["exclusive"]}}, {"kind": "custom", "custom": {"submit": "qsub"}}]
    for b in bad:
        assert m.system.system_scheduler_set({"scheduler": b, "confirm": True})[1] == 400, b


# ── the PI's own instructions, per procedure / step / role ─────────────────────

def _wf_hub(hub):
    import shutil
    shutil.copytree(REPO / "workflow", hub.root / "workflow", dirs_exist_ok=True)
    shutil.copytree(REPO / ".claude" / "skills", hub.root / ".claude" / "skills", dirs_exist_ok=True)   # a lab ships its skills
    (hub.root / "studies" / "alpha").mkdir(parents=True, exist_ok=True)


def test_workflow_instructions_round_trip(m, hub):
    _wf_hub(hub)
    hub.add_registry_row("alpha", state="proposal")
    out, code = m.instructions.workflow_save({"kind": "add", "name": "propose", "text": "Name a publishable negative result."})
    assert code == 200 and out["file"] == "lab/workflow/propose.add.md"
    out, code = m.instructions.workflow_save({"kind": "add", "name": "propose", "study": "alpha", "text": "Alpha: three seeds."})
    assert code == 200 and out["file"] == "studies/alpha/workflow/propose.add.md"
    out, code = m.instructions.workflow_save({"kind": "step", "name": "proposal", "text": "Budget in GPU-hours."})
    assert code == 200 and out["file"] == "lab/workflow/step.proposal.add.md"
    item, code = m.instructions.workflow_item({"kind": "procedure", "name": "propose", "study": "alpha"})
    assert code == 200 and item["lab"]["add"] == "Name a publishable negative result." and item["study_layer"]["add"] == "Alpha: three seeds."
    assert item["steps"] == ["proposal"] and "Alpha: three seeds." in item["brief"] and "Budget in GPU-hours." in item["brief"]
    view = m.sources._workflow_view()
    assert view["custom"]["procedures"]["propose"] and view["study_custom"]["alpha"]["procedures"]["propose"]
    assert m.instructions.workflow_save({"kind": "add", "name": "propose", "study": "alpha", "text": ""})[1] == 200
    assert not (hub.root / "studies" / "alpha" / "workflow" / "propose.add.md").exists()
    assert "workflow.save" in (hub.lab / ".bus" / "pi-actions.jsonl").read_text(encoding="utf-8")


def test_workflow_refuses_bad_input(m, hub):
    _wf_hub(hub)
    assert m.instructions.workflow_save({"kind": "method", "name": "propose", "text": "x"})[1] == 400   # a variant does that
    assert m.instructions.workflow_save({"kind": "add", "name": "nope", "text": "x"})[1] == 404
    assert m.instructions.workflow_save({"kind": "step", "name": "nowhere", "text": "x"})[1] == 404
    assert m.instructions.workflow_save({"kind": "add", "name": "propose", "study": "../etc", "text": "x"})[1] == 400
    assert m.instructions.workflow_save({"kind": "add", "name": "propose", "study": "ghost", "text": "x"})[1] == 400


def test_agent_proposals_are_accepted_or_declined_by_the_pi(m, hub):
    _wf_hub(hub)
    rec = K.instructions.propose("add", "propose", "Also list compute risks.", hub.root, why="missing")
    items = [a for a in m.sources.attention.lab_items([], [], []) if a["kind"] == "proposal"]
    assert [a["detail"]["proposal"] for a in items] == [rec["id"]]
    assert m.instructions.workflow_proposal({"id": rec["id"], "accept": "yes"})[1] == 400
    assert m.instructions.workflow_proposal({"id": rec["id"], "accept": True})[1] == 200
    assert "Also list compute risks." in m.instructions.workflow_item({"kind": "procedure", "name": "propose"})[0]["lab"]["add"]
    assert m.instructions.workflow_proposal({"id": rec["id"], "accept": True})[1] == 400      # already resolved
    assert not [a for a in m.sources.attention.lab_items([], [], []) if a["kind"] == "proposal"]


def test_autonomy_settings_round_trip(m, hub):
    cfg = hub.lab / "config.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "loop:\n  mode: execute\n  explore_max_expansion_rounds: 0\n"
                   "ideation:\n  in_project_approval: pi\n", encoding="utf-8")
    out, code = m.settings.lab_config_set({"confirm": True, "changes": {"keep_awake": "off", "loop_mode": "explore",
                                                                        "explore_rounds": 2, "in_project_approval": "campaign_auto"}})
    assert code == 200, out
    got = m.settings.lab_config_get()[0]["config"]
    assert (got["keep_awake"], got["loop_mode"], got["explore_rounds"], got["in_project_approval"]) == ("off", "explore", 2, "campaign_auto")
    assert m.settings.lab_config_set({"confirm": True, "changes": {"keep_awake": "auto"}})[1] == 200
    assert m.settings.lab_config_get()[0]["config"]["keep_awake"] == "auto"
    assert m.settings.lab_config_set({"confirm": True, "changes": {"loop_mode": "yolo"}})[1] == 400


# ── phone notifications (Settings → Notifications) ─────────────────────────────

def test_notifications_are_stored_outside_config_and_masked(m, hub, inbox):
    keys = m.keys
    out, code = keys.notify_set({"confirm": True, "ntfy": "not a url"})
    assert code == 400
    base, got = inbox
    out, code = keys.notify_set({"confirm": True, "ntfy": f"{base}/secret-topic-123", "link": "http://pc:8787"})
    assert code == 200, out
    st, _ = keys.notify_status()
    assert "secret-topic" not in st["ntfy"] and st["link"] == "http://pc:8787" and not st["webhook"]
    assert "secret-topic" not in (hub.lab / "config.yaml").read_text(encoding="utf-8")
    assert [k["key"] for k in keys.keys_status()[0]["keys"] if k["key"].startswith("NEWTS_")] == []
    out, code = keys.notify_test({})
    assert code == 200 and got and got[0]["path"] == "/secret-topic-123"


def test_read_side_slugs_never_step_out_of_a_folder(m):
    assert m.ctx.slug("..") == "" and m.ctx.slug("../x") == "" and m.ctx.slug(".hidden") == "" and m.ctx.slug("a..b") == ""
    assert m.ctx.slug("idea-1") == "idea-1" and m.ctx.slug("my idea!") == "myidea"


def test_the_agents_models_are_set_from_settings(m, hub):
    """Settings → Agents: each tool's model and effort, the subagent tiers and which tier each role uses — written
    to lab/config.yaml (and the role files re-rendered); anything that isn't a model name is refused."""
    out, code = m.settings.lab_config_set({"confirm": True, "changes": {
        "claude_model": "claude-sonnet-5-5", "claude_effort": "low", "codex_model": "gpt-6-luna", "codex_effort": "minimal",
        "opencode_model": "opencode/some-free-model", "tier_strong": "opus", "reviewer_model": "strong", "critic_effort": "high"}})
    assert code == 200, out
    assert "role files" in out["note"]                     # re-rendered (or why not), every time a model changes
    cfg = m.ctx.labfiles.load_yaml(hub.lab / "config.yaml")
    be = cfg["agents"]["programmatic"]["backends"]
    assert (be["claude"]["model"], be["claude"]["effort"], be["codex"]["reasoning_effort"]) == ("claude-sonnet-5-5", "low", "minimal")
    assert be["opencode"]["model"] == "opencode/some-free-model"
    assert cfg["agents"]["tiers"]["strong"] == "opus" and cfg["agents"]["reviewer_model"] == "strong" and cfg["agents"]["critic_effort"] == "high"
    for bad in ({"claude_model": "--dangerously-skip-permissions"}, {"claude_model": "sonnet; rm -rf ~"}, {"claude_effort": "turbo"},
                {"codex_model": "a/b"}):
        assert m.settings.lab_config_set({"confirm": True, "changes": bad})[1] == 400, bad
    assert m.settings.lab_config_set({"confirm": True, "changes": {"claude_model": ""}})[1] == 200   # blank = the tool's default
