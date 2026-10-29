"""Tests for the dashboard's executor surface (dashboard/serve.py) — handler functions, no socket.

Launch / answer / reply / stop / resume / cancel, the transcript tail, the master-switch toggle,
dashboard commands that also start the procedure that consumes them, the approve-and-start follow-up,
escalation resolution, route precedence, the SSE change signature, and the registry-row bus fix.
Launches only ENQUEUE here (nothing is spawned): the scheduler thread is never started.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from conftest import REPO, kernel, load

K = kernel()

FAKE = REPO / "tests" / "fake_claude.py"


def _mod(hub, monkeypatch, *, enabled=True, dashboard_extra: str = ""):
    (hub.lab / "config.yaml").write_text(
        'lab:\n  projects_root: "../projects"\n'
        f"dashboard:\n  port: 8787\n{dashboard_extra}"
        "agents:\n  programmatic:\n"
        f"    enabled: {str(bool(enabled)).lower()}   # master switch\n"
        "    backend: claude\n    max_depth: 1\n"
        "    backends:\n      claude:\n"
        f"        command: {json.dumps([sys.executable, str(FAKE)])}\n",
        encoding="utf-8")
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    m = load("dashboard/serve")
    monkeypatch.setattr(m.ctx, "HUB", hub.root)
    monkeypatch.setattr(m.ctx, "LAB", hub.lab)
    for slug, step in (("idea-a", "proposal"), ("idea-q", "proposal")):
        if not hub.study(slug):
            hub.add_registry_row(slug, state=step)
    return m


def _pi_actions(hub):
    f = hub.lab / ".bus" / "pi-actions.jsonl"
    return [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


# ── launch ────────────────────────────────────────────────────────────────────

def test_launch_queues_a_run_and_logs(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    out, code = m.runops.launch_run({"skill": "propose", "target": "idea-a", "confirm": True})
    assert code == 200 and out["status"] == "queued" and out["command"] == "/propose idea-a"
    assert (hub.lab / ".bus" / "agents" / f"{out['run_id']}.json").exists()
    assert _pi_actions(hub)[-1]["action"] == "run.launch"
    assert m.ctx.KICK.is_set()                                     # the scheduler is woken at once


def test_api_child_launch_keeps_depth_and_context(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    parent, _ = m.runops.launch_run({'prompt':'Read evidence', 'confirm':True})
    body = {'prompt':'Independently check it', 'confirm':True, 'parent':parent['run_id']}
    out, code = m.runops.launch_run(body)
    assert code == 400 and 'depth' in out['error']
    config = hub.lab/'config.yaml'
    config.write_text(config.read_text().replace('max_depth: 1','max_depth: 2'))
    out, code = m.runops.launch_run(body)
    assert code == 200
    lab = m.executor.Lab(hub.root)
    child = m.executor.find_run(lab,out['run_id'])[3]
    assert child['depth'] == 1 and child['parent'] == parent['run_id']
    assert child['created_by'] == 'run:'+parent['run_id']
    grandchild, code = m.runops.launch_run({**body,'parent':child['run_id']})
    assert code == 400 and 'depth' in grandchild['error']
    # Explicit context reaches the existing validator; it is never silently dropped.
    out, code = m.runops.launch_run({'prompt':'Continue', 'confirm':True,
        'context':{'mode':'continue','run_id':'missing'}})
    assert code == 400 and 'source' in out['error']


def test_launch_refusals(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    assert m.runops.launch_run({"skill": "propose", "target": "idea-a"})[1] == 400             # no confirm
    out, code = m.runops.launch_run({"skill": "finalize", "target": "idea-a", "confirm": True})
    assert code == 400 and "the work of Final" in out["error"]           # not where idea-a stands
    out, code = m.runops.launch_run({"skill": "lab-status", "args": "x\ny", "confirm": True})
    assert code == 400
    out, code = m.runops.launch_run({"skill": "propose", "target": "../../etc", "confirm": True})
    assert code == 400 and "invalid target" in out["error"]
    m2 = _mod(hub, monkeypatch, enabled=False)
    out, code = m2.runops.launch_run({"skill": "lab-status", "confirm": True})
    assert code == 400 and "off" in out["error"]


# ── answer / reply / stop / resume / cancel ──────────────────────────────────

def _waiting_run(m, hub):
    K.studies.move(hub.root, "idea-q", "done")
    K.checkpoints.decide(hub.root, "idea-q", "approve-proposal", via="cli")
    out, _ = m.runops.launch_run({"skill": "spawn-project", "target": "idea-q", "confirm": True})
    lab = m.executor.Lab(hub.root)
    _t, _w, path, man = m.executor.find_run(lab, out["run_id"])
    m.executor.manifest.transition(lab, path, man, "waiting_input", by="test", session_id="S1",
                                   pending_question={"tool_use_id": "tq", "input": {"questions": [
                                       {"question": "Type?", "options": [{"label": "ml"}]}]}})
    return out["run_id"]


def test_answer_then_run_is_queued_to_resume(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    rid = _waiting_run(m, hub)
    out, code = m.runops._run_op("answer", {"run_id": rid, "answers": {"Type?": "ml"}})
    assert code == 200 and out["status"] == "queued"
    run = m.runops.run_detail(rid)[0]["run"]
    assert run["pending_question"] is None and run["qa"][0]["answers"] == {"Type?": "ml"}
    assert m.runops._run_op("answer", {"run_id": rid, "answers": {"Type?": "ml"}})[1] == 400   # no longer waiting


def test_reply_stop_cancel_and_bad_ids(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    rid = _waiting_run(m, hub)
    assert m.runops._run_op("reply", {"run_id": rid, "text": "use theory"})[0]["status"] == "queued"
    assert m.runops._run_op("stop", {"run_id": rid})[1] == 400                                # needs confirm
    out, code = m.runops._run_op("stop", {"run_id": rid, "confirm": True})                     # queued → cancelled
    assert code == 200 and out["status"] == "killed"
    assert m.runops._run_op("resume", {"run_id": "../x"})[1] == 400
    assert m.runops._run_op("cancel", {"run_id": "no-such-run"})[1] == 400


# ── transcript tail ──────────────────────────────────────────────────────────

def test_run_tail_offsets_whole_lines_and_subagent_labels(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    out, _ = m.runops.launch_run({"skill": "lab-status", "confirm": True})
    rid = out["run_id"]
    lab = m.executor.Lab(hub.root)
    _t, _w, path, man = m.executor.find_run(lab, rid)
    man["subagents"] = {"tuS": {"type": "experiment-runner", "description": "exp-004"}}
    m.executor.manifest.write_manifest(path, man)
    stream = path.parent / man["stream"]
    lines = [{"_attempt": 1, "ts": "t"},
             {"type": "system", "subtype": "init", "session_id": "abcdef123"},
             {"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}},
             {"type": "assistant", "parent_tool_use_id": "tuS", "message": {"content": [
                 {"type": "tool_use", "id": "x", "name": "Bash", "input": {"command": "uv run a"}}]}},
             {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "tuS",
                                                       "content": "PACKET ok"}]}}]
    stream.write_text("".join(json.dumps(x) + "\n" for x in lines) + '{"partial": ', encoding="utf-8")
    res, code = m.runops.run_tail(rid, 0)
    kinds = [x["k"] for x in res["lines"]]
    assert code == 200 and kinds == ["attempt", "start", "text", "tool", "sub"]
    assert res["lines"][3]["who"].startswith("experiment-runner") and res["lines"][4]["t"] == "PACKET ok"
    assert not res["eof"]                                       # the partial last line is held back
    with stream.open("a", encoding="utf-8") as f:
        f.write('"x"}\n' + json.dumps({"type": "result", "result": "done", "stop_reason": "end_turn"}) + "\n")
    res2, _ = m.runops.run_tail(rid, res["offset"])
    assert [x["k"] for x in res2["lines"]] == ["end"] and res2["eof"]
    assert m.runops.run_tail("nope", 0)[1] == 404


# ── master switch toggle (in-process stamp: never touches the real repo) ─────

def test_set_programmatic_flips_config_and_logs(hub, monkeypatch):
    m = _mod(hub, monkeypatch, enabled=False)
    assert m.runops.set_programmatic({"enabled": True})[1] == 400                              # needs confirm
    out, code = m.runops.set_programmatic({"enabled": True, "confirm": True})
    assert code == 200 and out["enabled"] is True
    text = (hub.lab / "config.yaml").read_text(encoding="utf-8")
    import re
    assert re.search(r"enabled: true\s+# master switch", text)                           # comment preserved
    assert _pi_actions(hub)[-1] == {**_pi_actions(hub)[-1], "action": "executor.enable", "enabled": True}
    (hub.lab / "config.yaml").write_text("lab: {}\n", encoding="utf-8")
    assert m.runops.set_programmatic({"enabled": True, "confirm": True})[1] == 400             # key absent → refused


# ── commands that also launch the consumer ───────────────────────────────────

def test_command_launch_maps_actions(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    hub.add_registry_row("demo", state="active", project=str(proj))
    out = m.runops.command_launch("demo", "run_smoke", {}, "")
    assert out["ok"] and out["command"] == "/experiment demo"
    out = m.runops.command_launch("demo", "ideate", {}, "")
    assert out["command"] == "/ideate --in-project demo"
    out = m.runops.command_launch("hub", "ideate", {"direction": "efficient small LMs"}, "")
    assert out["command"] == "/ideate efficient small LMs"
    assert m.runops.command_launch("demo", "park", {}, "") is None                 # registry edits stay directives


def test_stop_loop_stops_live_research_loop(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    hub.add_registry_row("demo", state="active", project=str(proj))
    out, _ = m.runops.launch_run({"skill": "research-loop", "target": "demo", "confirm": True})
    lab = m.executor.Lab(hub.root)
    _t, _w, path, man = m.executor.find_run(lab, out["run_id"])
    m.executor.manifest.transition(lab, path, man, "running", by="test", pid=None)
    m.executor.manifest.transition(lab, path, man, "running", by="test", status_ts="2000-01-01T00:00:00")
    stopped = m.runops.command_stop_loop("demo")
    assert stopped == [out["run_id"]]
    assert m.executor.find_run(lab, out["run_id"])[3]["status"] == "killed"   # no supervisor → killed now


# ── approve and start ───────────────────────────────────────────────────────

def test_approving_moves_the_study_and_starts_its_next_step_only_when_asked(hub, monkeypatch):
    """Approving the checkpoint a study waits at moves it on; its new step's work (/spawn-project) starts only
    with start=true — without it the approval is recorded, the study moved, and nothing queued."""
    m = _mod(hub, monkeypatch)
    for start in (False, True):
        slug = f"idea-{int(start)}"
        hub.add_registry_row(slug, state="proposal", next="/propose")
        K.studies.move(hub.root, slug, "done")
        res, code = m.decisions.decide({"study": slug, "checkpoint": "approve-proposal", "confirm": True, "start": start})
        assert code == 200 and res["ok"] and res["moved"]["step"] == "setup" and "moved to Project set-up" in res["note"]
        if start:
            assert res["launch"]["command"] == f"/spawn-project {slug}" and "started" in res["note"]
        else:
            assert "launch" not in res
    lab = m.executor.Lab(hub.root)
    assert [x[-1]["subject"] for x in m.executor.all_runs(lab)] == ["idea-1"]


# ── misc ──────────────────────────────────────────────────────────────────────

def test_resolve_escalation_writes_on_the_raising_bus(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    hub.add_registry_row("demo", state="active", project=str(proj))
    assert m.bus.resolve_escalation({"ref": "not-an-id"})[1] == 400
    out, code = m.bus.resolve_escalation({"ref": "e-abcdef123456", "source": "demo"})
    assert code == 200
    ev = json.loads((proj / ".bus" / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert ev["kind"] == "escalation_resolved" and ev["data"]["ref"] == "e-abcdef123456"


def test_exact_routes_precede_prefix_routes(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    for r in ("/api/run", "/api/run/answer", "/api/run/stop", "/api/attention/ack", "/api/executor/enable"):
        assert r in m.POST_ROUTES


def test_sse_signature_ignores_the_clock(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    a = {"now": "2026-01-01T00:00:00", "items": [1]}
    assert m._sig(a) == m._sig({**a, "now": "2026-01-01T00:00:09"})
    assert m._sig(a) != m._sig({**a, "items": [2]})


def test_bus_dir_honours_registry_project_column(hub, monkeypatch):
    """An /adopt-ed project outside projects_root must get its directives on ITS bus, not the hub's."""
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("adopted", in_root=False)
    hub.add_registry_row("adopted", state="active", project=str(proj))
    assert m.bus._bus_dir("adopted") == proj / ".bus"
    assert m.bus._bus_dir("pre-spawn-idea") == hub.lab / ".bus"


def test_health_and_snapshot_expose_executor(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    h, code = m.runops.executor_health()
    assert code == 200 and h["available"] and h["enabled"] and h["clis"]["claude"]["found"]
    snap = m.sources.snapshot()
    assert snap["executor"]["enabled"] is True and "lab-status" in snap["skills"]


def test_a_step_run_goes_on_to_the_next_step_unless_the_lab_says_not(hub, monkeypatch):
    """The kernel names each next step; by default a run of the step a study stands at follows them (chain=loop,
    up to a checkpoint). Other runs stop; the PI's explicit choice wins; `follow_steps: false` turns it off."""
    m = _mod(hub, monkeypatch)
    lab = m.executor.Lab(hub.root)
    chain = lambda body: m.executor.find_run(lab, m.runops.launch_run(dict(body, confirm=True))[0]["run_id"])[3]["chain"]  # noqa: E731
    assert chain({"skill": "propose", "target": "idea-a"}) == "loop"             # idea-a stands at proposal
    assert chain({"skill": "propose", "target": "idea-q", "chain": "off"}) == "off"
    assert chain({"skill": "lab-status"}) == "off"
    cfg = hub.lab / "config.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("    max_depth: 1\n", "    max_depth: 1\n    follow_steps: false\n"),
                   encoding="utf-8")
    assert chain({"skill": "propose", "target": "idea-q"}) == "off"
    assert m.executor.health(lab)["config"]["follow_steps"] is False       # Settings shows the toggle off


def test_explain_starts_a_separate_agent_from_recorded_actions(hub, monkeypatch):
    """A fresh explainer reads recorded subagent evidence and leaves the source session unchanged."""
    m = _mod(hub, monkeypatch, dashboard_extra="")
    cfg = hub.lab / "config.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("    max_depth: 1\n", "    max_depth: 1\n    writing: ste80\n"),
                   encoding="utf-8")
    lab = m.executor.Lab(hub.root)
    out, _ = m.runops.launch_run({"skill": "lab-status", "confirm": True})
    _t, _w, path, man = m.executor.find_run(lab, out["run_id"])
    man["subagents"] = {"tu_1": {"type": "lit-scout", "description": "find prior work", "status": "done"}}
    m.executor.manifest.transition(lab, path, man, "completed", by="test", session_id="S1")
    assert m.runops.explain_run({"run_id": out["run_id"], "agent": "nope"})[1] == 400
    res, code = m.runops.explain_run({"run_id": out["run_id"], "agent": "tu_1"})
    assert code == 200, res
    original = m.executor.find_run(lab, out['run_id'])[3]
    assert original['status']=='completed' and original['session_id']=='S1' and not original.get('resume')
    _,_,own,explainer=m.executor.find_run(lab,res['run_id'])
    assert explainer['explains']['run']==out['run_id'] and explainer['context']['mode']=='fresh'
    pre=(m.executor.run_dir(own.parent,res['run_id'])/'preamble.md').read_text(encoding='utf-8')
    assert '80% of the way to ASD-STE100' in pre
    dossier=json.loads(Path(explainer['explains']['evidence']).read_text())
    assert dossier['agents']['tu_1']['description']=='find prior work'
    tree, code = m.runops.run_actions({"run_id": out["run_id"]})
    assert code == 200 and tree["agents"]["main"]["actions"] == []


def test_the_writing_style_reaches_every_run(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    lab = m.executor.Lab(hub.root)
    prof = m.executor.profile
    assert prof.writing_style(lab) == prof.WRITING["plain"]
    cfg = hub.lab / "config.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("    max_depth: 1\n", "    max_depth: 1\n    writing: Bullet points, numbers first.\n"),
                   encoding="utf-8")
    out, _ = m.runops.launch_run({"skill": "lab-status", "confirm": True})
    rd = m.executor.run_dir(m.executor.find_run(lab, out["run_id"])[2].parent, out["run_id"])
    assert "write in this style: Bullet points, numbers first." in (rd / "preamble.md").read_text(encoding="utf-8")
