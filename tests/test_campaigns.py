"""The campaign keeper (tools/executor/campaigns.py): an approved campaign keeps going whatever happens to a
single run — re-entry by how the last cycle ended, dispatch validation, per-study waits, child retries,
stop conditions with a final report cycle — and approvals by delegation: a cycle asks (`campaign_approve`),
and only the keeper records it, only for a checkpoint the PI delegated to this campaign, only when the
checkpoint's checks pass, and never after the PI withdrew the campaign's approval."""

from __future__ import annotations

import json
import os
import sys
import time

import pytest

from conftest import REPO, approve, kernel

K = kernel()

sys.path.insert(0, str(REPO / "tools"))
import executor  # noqa: E402
from executor import campaigns, manifest, scheduler  # noqa: E402
checkpoints = K.checkpoints

from test_executor import Spawns, setup  # noqa: E402

BRIEF = """# Campaign Brief — test

## Direction & targets

- **Research direction(s):** sparse routing
- **Parallelism:** ≤ {par} ideas in flight

## Campaign Log (append-only)

| time | idea | lifecycle step | outcome / route | progress? | note |
|---|---|---|---|---|---|
| 10:00 | idea-a | ideate | filed | yes | |
"""


@pytest.fixture
def camp(hub):
    lab = setup(hub, extra="    max_concurrent_total: 6\n    hub_max_concurrent: 2\n")
    for slug, state in (("idea-a", "proposal"), ("idea-b", "lit-review")):
        if not hub.study(slug):                       # (the executor's setup files them too)
            hub.add_registry_row(slug, state=state, next="/propose")
        (hub.root / "studies" / slug).mkdir(parents=True, exist_ok=True)
    (hub.lab / "campaigns").mkdir(exist_ok=True)

    def make(par=2, **kw):
        (hub.lab / "campaigns" / "2026-09-27-test.md").write_text(BRIEF.format(par=par), encoding="utf-8")
        approve(hub.root, "lab", "campaign:2026-09-27-test", "approved", by="pi", via="dashboard")
        return campaigns.create(lab, "lab/campaigns/2026-09-27-test.md", **kw)
    return lab, make


def _runs(lab, **match):
    return [m for *_x, m in executor.all_runs(lab) if all(m.get(k) == v for k, v in match.items())]


def _cycles(lab):
    return sorted(_runs(lab, skill="autopilot"), key=lambda m: (int(m.get("campaign_cycle") or 0), m.get("created") or ""))


def _finish(lab, run_id, status, **fields):
    _t, workdir, path, m = executor.find_run(lab, run_id)
    manifest.transition(lab, path, m, status, by="test", finished=manifest.now(), **fields)
    return workdir


def _footer(lab, workdir, run_id, **data):
    bus = lab.bus_of(workdir)
    bus.mkdir(parents=True, exist_ok=True)
    with (bus / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": manifest.now(), "kind": "run_report", "run_id": run_id, "data": data}) + "\n")


def _dispatch(lab, cycle_id, **data):
    with (lab.lab / ".bus" / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": manifest.now() + f".{time.time_ns()}", "kind": "campaign_dispatch",
                            "run_id": cycle_id, "data": data}) + "\n")


def _stopped(lab, run_id):
    """Killed, or (a run whose supervisor is still coming up) carrying the stop marker it will obey."""
    _t, _w, path, m = executor.find_run(lab, run_id)
    return m["status"] == "killed" or (manifest.run_dir(path.parent, run_id) / "stop").exists()


def _nb(m):
    return manifest.parse_ts(m.get("not_before")) or 0


# ── re-entry ─────────────────────────────────────────────────────────────────────────────────────
def test_first_tick_starts_a_cycle_and_only_one(camp):
    lab, make = camp
    make()
    sp = Spawns()
    rep = executor.tick(lab, spawn=sp)
    cyc = _cycles(lab)
    assert len(cyc) == 1 and rep["started"] == [cyc[0]["run_id"]] and cyc[0]["campaign_cycle"] == 1
    assert "CAMPAIGN CYCLE 1" in (executor.manifest.run_dir(executor.find_run(lab, cyc[0]["run_id"])[2].parent,
                                                             cyc[0]["run_id"]) / "preamble.md").read_text(encoding="utf-8")
    executor.tick(lab, spawn=sp)
    assert len(_cycles(lab)) == 1              # idempotent: never two live cycles


def test_a_question_left_on_the_card_is_answered_into_the_next_pass(camp):
    lab, make = camp
    make(repeat_minutes=0)
    executor.tick(lab, spawn=Spawns())
    c1 = _cycles(lab)[0]
    st = campaigns.load(lab, campaigns.all_states(lab)[0]["name"])
    st["questions"] = [{"ts": manifest.now(), "run_id": c1["run_id"], "question": "Which baseline?"}]
    campaigns.save(lab, st)
    card = campaigns.summary(lab)[0]["questions"][0]
    assert card["index"] == 0 and "answer" not in card
    with pytest.raises(ValueError):
        campaigns.control(lab, st["name"], "answer", index=3, text="x")
    campaigns.control(lab, st["name"], "answer", index=0, text="the 2024 one")
    w = _finish(lab, c1["run_id"], "completed")
    _footer(lab, w, c1["run_id"], campaign="continue", summary="pass 1")
    executor.tick(lab, spawn=Spawns())
    c2 = _cycles(lab)[-1]
    pre = (manifest.run_dir(executor.find_run(lab, c2["run_id"])[2].parent, c2["run_id"]) / "preamble.md").read_text(encoding="utf-8")
    assert "The PI answered questions from earlier passes" in pre and "Which baseline?" in pre and "the 2024 one" in pre
    assert "recommendation FIRST" in pre and "Never ask the PI" not in pre
    assert campaigns.load(lab, st["name"])["questions"][0]["delivered"] is True   # delivered once


def test_completed_cycle_repeats_after_the_interval(camp):
    lab, make = camp
    make(repeat_minutes=20)
    executor.tick(lab, spawn=Spawns())
    c1 = _cycles(lab)[0]
    w = _finish(lab, c1["run_id"], "completed")
    _footer(lab, w, c1["run_id"], campaign="continue", summary="pass 1")
    executor.tick(lab, spawn=Spawns())
    c2 = _cycles(lab)[-1]
    assert c2["run_id"] != c1["run_id"] and c2["parent"] == c1["run_id"] and c2["status"] == "queued"
    assert 19 * 60 < _nb(c2) - time.time() < 21 * 60


def test_a_usage_limit_waits_until_it_lifts_and_holds_the_backend(camp):
    lab, make = camp
    make()
    executor.tick(lab, spawn=Spawns())
    c1 = _cycles(lab)[0]
    reset = time.time() + 3600
    _finish(lab, c1["run_id"], "failed", failure_kind="usage_limit", limit_reset=reset, reason="usage limit reached")
    executor.tick(lab, spawn=Spawns())
    c2 = _cycles(lab)[-1]
    assert abs(_nb(c2) - (reset + 120)) < 5
    assert scheduler.limits(lab).get("claude")
    other = executor.enqueue(lab, executor.RunSpec(skill="lab-status"))["run_id"]
    executor.tick(lab, spawn=Spawns())
    assert executor.find_run(lab, other)[3]["status"] == "queued"   # the backend is held until the reset
    st = campaigns.load(lab, "2026-09-27-test")
    assert st["consecutive_failures"] == 0 and st["status"] == "active"


def test_transient_failures_back_off_then_stall(camp):
    lab, make = camp
    make(max_failures=2)
    for i in range(2):
        executor.tick(lab, spawn=Spawns())
        c = _cycles(lab)[-1]
        # let a queued (backed-off) cycle "run" and fail
        _t, _w, path, m = executor.find_run(lab, c["run_id"])
        if m["status"] == "queued":
            manifest.transition(lab, path, m, "running", by="test")
        _finish(lab, c["run_id"], "failed", failure_kind="transient", reason="overloaded")
    executor.tick(lab, spawn=Spawns())
    st = campaigns.load(lab, "2026-09-27-test")
    assert st["status"] == "stalled" and "in a row" in st["paused_reason"]
    assert [c["kind"] for c in st["cycles"]] == ["transient", "transient"]


def test_a_timeout_goes_straight_on_and_auth_pauses(camp):
    lab, make = camp
    make()
    executor.tick(lab, spawn=Spawns())
    c1 = _cycles(lab)[0]
    _finish(lab, c1["run_id"], "timeout")
    executor.tick(lab, spawn=Spawns())
    c2 = _cycles(lab)[-1]
    assert c2["run_id"] != c1["run_id"] and _nb(c2) - time.time() < 120
    _t, _w, path, m = executor.find_run(lab, c2["run_id"])
    manifest.transition(lab, path, m, "running", by="test")
    _finish(lab, c2["run_id"], "failed", failure_kind="auth", reason="the claude CLI is not logged in")
    executor.tick(lab, spawn=Spawns())
    st = campaigns.load(lab, "2026-09-27-test")
    assert st["status"] == "paused" and "logged in" in st["paused_reason"] and len(_cycles(lab)) == 2
    campaigns.control(lab, st["name"], "resume")
    executor.tick(lab, spawn=Spawns())
    assert len(_cycles(lab)) == 3


# ── dispatch ─────────────────────────────────────────────────────────────────────────────────────
def test_dispatch_is_validated_and_runs_as_children(camp):
    lab, make = camp
    make(par=1)
    executor.tick(lab, spawn=Spawns())
    cid = _cycles(lab)[0]["run_id"]
    _dispatch(lab, cid, skill="propose", target="idea-a")          # a member (Campaign Log)
    _dispatch(lab, cid, skill="propose", target="idea-a")          # duplicate
    _dispatch(lab, cid, skill="lit-review", target="idea-b")       # not in the campaign
    _dispatch(lab, cid, skill="finalize", target="idea-a")         # never
    _dispatch(lab, cid, skill="autopilot", target="hub")           # never another campaign
    executor.tick(lab, spawn=Spawns())
    kids = _runs(lab, campaign="2026-09-27-test", skill="propose")
    assert len(kids) == 1 and kids[0]["parent"] == cid and kids[0]["created_by"] == "campaign"
    log = {(d["skill"], d["target"]): d["result"] for d in campaigns.load(lab, "2026-09-27-test")["dispatch_log"]}
    assert log[("propose", "idea-a")] in ("started", "refused: already queued or running")
    assert "not in this campaign" in log[("lit-review", "idea-b")]
    assert "is the work of Final" in log[("finalize", "idea-a")] and "can't be dispatched" in log[("autopilot", "hub")]
    assert "CAMPAIGN RUN" in (manifest.run_dir(executor.find_run(lab, kids[0]["run_id"])[2].parent,
                                               kids[0]["run_id"]) / "preamble.md").read_text(encoding="utf-8")
    executor.tick(lab, spawn=Spawns())
    assert len(_runs(lab, campaign="2026-09-27-test", skill="propose")) == 1   # an event is handled once


def test_a_study_waiting_for_the_pi_waits_alone(camp, hub):
    lab, make = camp
    make(par=3)
    executor.tick(lab, spawn=Spawns())
    cid = _cycles(lab)[0]["run_id"]
    _dispatch(lab, cid, skill="propose", target="idea-a")
    executor.tick(lab, spawn=Spawns())
    kid = _runs(lab, skill="propose")[0]
    w = _finish(lab, kid["run_id"], "completed")
    _footer(lab, w, kid["run_id"], needs_pi="approve-proposal", study="idea-a")
    executor.tick(lab, spawn=Spawns())
    st = campaigns.load(lab, "2026-09-27-test")
    assert st["studies"]["idea-a"]["waiting"] == "approve-proposal" and st["status"] == "active"
    _dispatch(lab, cid, skill="propose", target="idea-a")
    executor.tick(lab, spawn=Spawns())
    assert "waiting for the PI" in campaigns.load(lab, "2026-09-27-test")["dispatch_log"][-1]["result"]
    # a phrase in a document approves nothing …
    (hub.root / "studies" / "idea-a" / "proposal.md").write_text("<!-- PI Gate 1 approved via the dashboard x -->\n",
                                                                 encoding="utf-8")
    executor.tick(lab, spawn=Spawns())
    assert campaigns.load(lab, "2026-09-27-test")["studies"]["idea-a"]["waiting"] == "approve-proposal"
    # … the PI's approval (a record) picks the study up again
    approve(hub.root, "idea-a", "approve-proposal", "approved", by="pi", via="dashboard")
    executor.tick(lab, spawn=Spawns())
    assert not campaigns.load(lab, "2026-09-27-test")["studies"]["idea-a"]["waiting"]


def test_children_are_retried_after_a_timeout(camp):
    lab, make = camp
    make(par=2)
    executor.tick(lab, spawn=Spawns())
    _dispatch(lab, _cycles(lab)[0]["run_id"], skill="propose", target="idea-a")
    executor.tick(lab, spawn=Spawns())
    kid = _runs(lab, skill="propose")[0]
    _t, _w, path, m = executor.find_run(lab, kid["run_id"])
    manifest.transition(lab, path, m, "running", by="test", session_id="s-1")
    _finish(lab, kid["run_id"], "timeout")
    executor.tick(lab, spawn=Spawns())
    m = executor.find_run(lab, kid["run_id"])[3]
    assert m["campaign_retries"] == 1 and (m.get("resume") or {}).get("mode") == "continue" or m["status"] != "timeout"


# ── stopping ─────────────────────────────────────────────────────────────────────────────────────
def test_the_deadline_ends_with_a_final_report_cycle(camp):
    lab, make = camp
    make(hours=0.0001)
    time.sleep(0.5)
    executor.tick(lab, spawn=Spawns())
    c = _cycles(lab)[0]
    assert c["campaign_final"] is True
    pre = (manifest.run_dir(executor.find_run(lab, c["run_id"])[2].parent, c["run_id"]) / "preamble.md").read_text(encoding="utf-8")
    assert "FINAL CYCLE" in pre
    _finish(lab, c["run_id"], "completed")
    executor.tick(lab, spawn=Spawns())
    assert campaigns.load(lab, "2026-09-27-test")["status"] == "done" and len(_cycles(lab)) == 1


def test_the_pi_stops_a_campaign(camp):
    lab, make = camp
    make()
    executor.tick(lab, spawn=Spawns())
    c1 = _cycles(lab)[0]
    campaigns.control(lab, "2026-09-27-test", "stop")
    assert _stopped(lab, c1["run_id"])
    _finish(lab, c1["run_id"], "killed", reason="stopped by the PI")   # what its supervisor records
    executor.tick(lab, spawn=Spawns())
    c2 = _cycles(lab)[-1]
    assert c2["campaign_final"] is True                      # one last cycle writes the report


# ── approvals by delegation ──────────────────────────────────────────────────────────────────────
def _paper_ready(hub, slug="idea-a"):
    """The study's paper passed internal review: its agent reported `done`, and it waits for finalize-paper."""
    K.studies.move_to(hub.root, slug, "internal-review", by="pi")
    assert K.studies.move(hub.root, slug, "done")["waiting"] == "finalize-paper"
    p = hub.root / "studies" / slug / "paper"
    (p / "reviews" / "r1").mkdir(parents=True, exist_ok=True)
    (p / "main.pdf").write_bytes(b"%PDF-1.4 test")
    (p / "claims.yaml").write_text("claims: []\n", encoding="utf-8")


def _reviewed(lab, cid, slug="idea-a"):
    _dispatch(lab, cid, skill="review-paper", target=slug)
    executor.tick(lab, spawn=Spawns())
    kid = _runs(lab, skill="review-paper")[0]
    w = _finish(lab, kid["run_id"], "completed")
    _footer(lab, w, kid["run_id"], needs_pi="finalize-paper", study=slug)
    return kid


def _ask(lab, cid, slug="idea-a", checkpoint="finalize-paper"):
    with (lab.lab / ".bus" / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": manifest.now() + f".{time.time_ns()}", "kind": "campaign_approve", "run_id": cid,
                            "data": {"study": slug, "checkpoint": checkpoint, "why": "review accepted"}}) + "\n")


def _log(lab):
    return campaigns.load(lab, "2026-09-27-test").get("approval_log") or []


def test_a_campaign_approves_a_delegated_checkpoint_only_when_its_checks_pass(camp, hub, monkeypatch):
    lab, make = camp
    make(delegates=["finalize-paper"])
    _paper_ready(hub)
    results = {"claims": {"code": 0}, "multiseed": {"code": 2}}
    monkeypatch.setattr(checkpoints, "run_checks", lambda h, s, cp, timeout=600: dict(results))
    executor.tick(lab, spawn=Spawns())
    cid = _cycles(lab)[0]["run_id"]
    _reviewed(lab, cid)
    with pytest.raises(executor.SpecError):                  # nothing finalizes before the approval
        executor.enqueue(lab, executor.RunSpec(skill="finalize", target="idea-a"))
    _ask(lab, cid)
    executor.tick(lab, spawn=Spawns())
    assert not K.journal.approved(hub.root, "idea-a", "finalize-paper")      # a check failed
    assert "multiseed did not pass" in _log(lab)[-1]["result"]
    results["multiseed"] = {"code": 0}
    _ask(lab, cid)
    executor.tick(lab, spawn=Spawns())
    rec = K.journal.latest(hub.root, "idea-a", "finalize-paper")
    assert rec["decision"] == "approved" and rec["by"] == "campaign:2026-09-27-test" and rec["via"] == "keeper"
    fin = _runs(lab, skill="finalize")
    assert len(fin) == 1 and fin[0]["created_by"] == "campaign-approval"
    assert _log(lab)[-1]["result"].startswith("approved; started the work of final")
    assert K.studies.study(hub.root, "idea-a")["step"] == "final"           # the approval carried the move


def test_a_campaign_never_approves_what_was_not_delegated_or_is_held(camp, hub, monkeypatch):
    lab, make = camp
    make(delegates=["approve-full-runs"])                # finalize-paper is not delegated
    _paper_ready(hub)
    monkeypatch.setattr(checkpoints, "run_checks", lambda h, s, cp, timeout=600: {})
    executor.tick(lab, spawn=Spawns())
    cid = _cycles(lab)[0]["run_id"]
    _ask(lab, cid)
    executor.tick(lab, spawn=Spawns())
    assert "may not approve" in _log(lab)[-1]["result"] and not K.journal.approved(hub.root, "idea-a", "finalize-paper")
    st = campaigns.load(lab, "2026-09-27-test")
    st["delegates"] = ["finalize-paper"]
    campaigns.save(lab, st)
    campaigns.control(lab, "2026-09-27-test", "hold", study="idea-a")
    _ask(lab, cid)
    executor.tick(lab, spawn=Spawns())
    assert "holding" in _log(lab)[-1]["result"]
    campaigns.control(lab, "2026-09-27-test", "unhold", study="idea-a")
    approve(hub.root, "lab", "campaign:2026-09-27-test", "revoked", by="pi", via="dashboard")
    _ask(lab, cid)
    executor.tick(lab, spawn=Spawns())
    assert "revoked" in _log(lab)[-1]["result"] and not K.journal.approved(hub.root, "idea-a", "finalize-paper")


def test_a_campaign_may_not_approve_a_checkpoint_only_the_pi_approves(camp, hub, monkeypatch):
    lab, make = camp
    hub.add_registry_row("idea-t", state="active", next="/experiment", workflow="target")
    (hub.root / "studies" / "idea-t").mkdir(parents=True, exist_ok=True)
    make(delegates=["approve-final-output"])           # (the form refuses this; the keeper refuses it too)
    executor.tick(lab, spawn=Spawns())
    st = campaigns.load(lab, "2026-09-27-test")
    st["studies"]["idea-t"] = {"member": True}
    campaigns.save(lab, st)
    monkeypatch.setattr(lab_profile_mod(), "campaign_members", lambda lab_, st_, brief: None)
    _ask(lab, _cycles(lab)[0]["run_id"], slug="idea-t", checkpoint="approve-final-output")
    executor.tick(lab, spawn=Spawns())
    assert "approved by the PI only" in _log(lab)[-1]["result"]


def lab_profile_mod():
    import lab_profile  # noqa: PLC0415
    return lab_profile


def test_agents_never_touch_approvals_or_the_keepers_state(camp, hub, monkeypatch):
    from conftest import load
    lab, make = camp
    make()
    sg = load("signature_guard")
    monkeypatch.setattr(sg, "HUB", hub.root.resolve())
    for path in (hub.lab / ".bus" / "campaigns" / "2026-09-27-test.json", hub.lab / "approvals.jsonl"):
        assert sg.decide({"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(hub.root),
                          "tool_input": {"file_path": str(path), "content": "{}"}})
    assert sg.decide({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(hub.root),
                      "tool_input": {"command": "echo '{}' > lab/.bus/campaigns/2026-09-27-test.json"}})
    assert sg.decide({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(hub.root),
                      "tool_input": {"command": "python arlo.py approve idea-a finalize-paper --yes"}})
    monkeypatch.setenv("ARLOTOPE_RUN_ID", "r-123")              # and the record itself refuses an agent run
    with pytest.raises(K.checkpoints.CheckpointError):
        K.checkpoints.decide(hub.root, "idea-a", "finalize-paper", by="pi", via="cli")


# ── nobody has to keep a window open ─────────────────────────────────────────────────────────────
def test_a_supervisor_starts_a_scheduler_when_none_is_ticking(camp, monkeypatch):
    lab, make = camp
    started = []
    monkeypatch.setattr(scheduler.subprocess, "Popen", lambda argv, **kw: started.append(argv))
    monkeypatch.delenv("ARLOTOPE_NO_AUTOTICKER", raising=False)
    assert not scheduler.ensure_ticker(lab)                      # no work → nothing to start
    make()
    lease = lab.lab / ".bus" / "scheduler.lease"
    if lease.exists():
        lease.unlink()
    assert scheduler.ensure_ticker(lab) and started and started[-1][-2:] == ["serve", "--until-idle"]
    assert not scheduler.ensure_ticker(lab)                      # it just wrote a fresh lease
    executor.tick(lab, spawn=Spawns())
    assert scheduler.lease(lab)["age"] < 5                       # every tick renews it
    monkeypatch.setenv("ARLOTOPE_NO_AUTOTICKER", "1")
    lease.write_text(json.dumps({"ts": 0}), encoding="utf-8")
    assert not scheduler.ensure_ticker(lab)


def test_keep_awake_follows_the_work(camp, monkeypatch):
    from executor import awake
    lab, make = camp
    held = []
    monkeypatch.setattr(awake, "hold", lambda reason: held.append(reason) or True)
    monkeypatch.setattr(awake, "release", lambda: held.append(None))
    awake.update(lab)
    assert held[-1] is None
    make()
    awake.update(lab)
    assert held[-1] and "campaign" in held[-1]
    (lab.lab / "config.yaml").write_text((lab.lab / "config.yaml").read_text(encoding="utf-8")
                                         .replace('lab:\n', 'lab:\n  keep_awake: off\n', 1), encoding="utf-8")
    awake.update(lab)
    assert held[-1] is None


def test_the_spawned_scheduler_takes_over_its_spawners_lease(camp):
    """ensure_ticker writes a lease as it spawns `serve --until-idle`; that process must not mistake it for
    another live ticker and exit (it did, once)."""
    import subprocess as sp
    lab, _make = camp
    scheduler.write_lease(lab, "spawned serve --until-idle")
    r = sp.run([sys.executable, str(REPO / "tools" / "executor_cli.py"), "--hub", str(lab.hub), "serve", "--until-idle",
                "--interval", "0.2", "--idle-seconds", "1"], capture_output=True, text=True, timeout=120,
               env={**__import__("os").environ, "ARLOTOPE_NO_AUTOTICKER": "1"})
    assert "another scheduler is ticking" not in r.stdout, r.stdout
    scheduler.write_lease(lab, "dashboard")
    r = sp.run([sys.executable, str(REPO / "tools" / "executor_cli.py"), "--hub", str(lab.hub), "serve", "--until-idle"],
               capture_output=True, text=True, timeout=60)
    assert "another scheduler is ticking" in r.stdout


def test_detached_processes_get_a_durable_python(monkeypatch, tmp_path):
    """Under `uv run --with …` the interpreter lives in a throwaway env uv deletes on exit: supervisors,
    schedulers and hooks started from it must use the durable ~/.arlotope/py instead (found live: a campaign
    cycle died with 'No pyvenv.cfg file' after the dashboard that started its scheduler exited)."""
    from executor import procs
    tmp = "/home/u/.cache/uv/builds-v0/.tmpAbC/bin/python" if os.name != "nt" else r"C:\u\uv\cache\builds-v0\.tmpAbC\Scripts\python.exe"
    assert procs._ephemeral(tmp) and not procs._ephemeral(sys.executable if not procs._ephemeral(sys.executable) else "/usr/bin/python3")
    monkeypatch.setattr(procs.sys, "executable", tmp)
    monkeypatch.setenv("ARLOTOPE_KEEP_PYTHON", "1")
    assert procs.python_exe() == tmp                        # the suite's own opt-out
    monkeypatch.delenv("ARLOTOPE_KEEP_PYTHON")
    monkeypatch.setenv("ARLOTOPE_HOME", str(tmp_path))
    procs._STABLE.clear()
    stable = tmp_path / "py" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    stable.parent.mkdir(parents=True)
    stable.write_text("", encoding="utf-8")
    monkeypatch.setattr(procs.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    assert procs.python_exe() == str(stable)
    procs._STABLE.clear()


def test_needs_you_shows_the_campaign_not_its_retried_runs(camp, monkeypatch):
    from executor import attention
    lab, make = camp
    make(max_failures=1)
    executor.tick(lab, spawn=Spawns())
    c1 = _cycles(lab)[0]
    _finish(lab, c1["run_id"], "failed", failure_kind="logic", reason="exit 1")
    runs = [(p, m) for *_x, p, m in executor.all_runs(lab)]
    assert not [i for i in attention.run_items(lab, runs) if i["kind"] == "crashed"]   # the keeper handles it
    executor.tick(lab, spawn=Spawns())
    assert campaigns.load(lab, "2026-09-27-test")["status"] == "stalled"
    from conftest import load
    sources = load("dashboard/sources")
    monkeypatch.setattr(sources.ctx, "HUB", lab.hub)
    monkeypatch.setattr(sources.ctx, "LAB", lab.lab)
    items = sources.attention.collect([], [], [], [])
    assert any(i["kind"] == "campaign" and i["sev"] == "block" for i in items)


# ── the campaign form: which checkpoints a campaign may approve is the PI's choice ─────────────────
@pytest.mark.parametrize("delegates", [["approve-proposal", "finalize-paper"], []])
def test_the_form_records_the_approval_and_the_delegated_checkpoints(hub, monkeypatch, tmp_path, delegates):
    import shutil
    from conftest import load
    (hub.root / "templates" / "loop").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO / "templates" / "loop" / "CAMPAIGN.md", hub.root / "templates" / "loop")
    monkeypatch.setenv("ARLOTOPE_HOME", str(tmp_path / "home"))
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    m = load("dashboard/serve")
    monkeypatch.setattr(m.ctx, "HUB", hub.root)
    monkeypatch.setattr(m.ctx, "LAB", hub.lab)
    out, code = m.campaign.campaign_create({"confirm": True, "fields": {
        "direction": "sparse routing", "ideas": 2, "parallel": 1, "full_budget": "3 runs x 60 min", "delegates": delegates}})
    assert code == 200, out
    assert out["delegates"] == delegates
    text = (hub.root / out["file"]).read_text(encoding="utf-8")
    sec = text.split("## Checkpoints this campaign may approve", 1)[1].split("\n## ", 1)[0]
    assert "3 runs x 60 min" in sec
    if delegates:
        assert "`approve-proposal`" in sec and "`finalize-paper`" in sec
    else:
        assert "none — every checkpoint waits for the PI" in sec
    name = out["file"].split("/")[-1][:-3]
    assert K.journal.approved(hub.root, "lab", f"campaign:{name}")       # the approval is a record
    out, code = m.campaign.campaign_create({"confirm": True, "fields": {"direction": "x", "delegates": ["approve-final-output"]}})
    assert code == 400 and "only approve checkpoints that allow it" in out["error"]
