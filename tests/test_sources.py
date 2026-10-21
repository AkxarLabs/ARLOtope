"""Tests for dashboard/sources.py — the read-only world model the dashboard renders."""

from __future__ import annotations

import json

import pytest

from conftest import kernel, load


def _mod(hub, monkeypatch):
    m = load("dashboard/sources")
    monkeypatch.setattr(m.ctx, "HUB", hub.root)
    monkeypatch.setattr(m.ctx, "LAB", hub.lab)
    return m


def test_parse_registry_reads_rows(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", title="Demo", state="active", project="../projects/demo")
    rows = m.parse_registry()
    assert len(rows) == 1
    assert rows[0]["id"] == "demo"
    assert rows[0]["state"] == "active"
    assert rows[0]["title"] == "Demo"


def test_parse_registry_skips_header_and_divider(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    # empty registry (header only) -> no rows
    assert m.parse_registry() == []


def test_snapshot_cold_when_registry_empty(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    snap = m.snapshot()
    assert snap["cold"] is True
    # documented keys present
    for key in ("items", "events", "workers", "directives", "checkpoints_waiting", "panels", "holds", "cold"):
        assert key in snap
    for gone in ("gates_waiting", "slots", "envelope"):        # the old gate model's keys
        assert gone not in snap


def test_snapshot_not_cold_with_a_row(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    hub.add_registry_row("demo", state="active", project=str(proj))
    snap = m.snapshot()
    assert snap["cold"] is False
    assert len(snap["items"]) == 1
    assert snap["items"][0]["id"] == "demo"
    assert snap["items"][0]["has_project"] is True


def _approve(hub, slug, cid, decision="approved"):
    return kernel().checkpoints.decide(hub.root, slug, cid, decision, via="cli", note="x" if decision != "approved" else "")


def _waits(hub, slug):
    """The study's agent reported its step done: it waits at the checkpoint on the way."""
    return kernel().studies.move(hub.root, slug, "done")


def test_snapshot_counts_the_studies_waiting_at_a_checkpoint(hub, monkeypatch):
    """A study waits at approve-proposal once its proposal is reported done, until it is approved (which moves it)."""
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="proposal", project="-", next="/propose")
    assert m.snapshot()["items"][0]["waiting"] == []                   # still writing its proposal
    _waits(hub, "demo")
    snap = m.snapshot()
    it = snap["items"][0]
    assert snap["checkpoints_waiting"] == 1 and it["waiting"] == ["approve-proposal"]
    assert it["workflow"] == "research" and it["checkpoints"] == {} and it["flags"] == []
    _approve(hub, "demo", "approve-proposal")
    snap = m.snapshot()
    it = snap["items"][0]
    assert snap["checkpoints_waiting"] == 0 and it["waiting"] == [] and it["state"] == "setup"
    assert it["checkpoints"]["approve-proposal"]["decision"] == "approved"


def test_project_path_prefers_explicit_column(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo", in_root=False)
    p = m._project_path({"id": "demo", "project": str(proj)})
    assert p == proj.resolve()


def test_project_path_falls_back_to_projects_root(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")  # under projects_root
    p = m._project_path({"id": "demo", "project": "-"})
    assert p == proj.resolve()


def test_project_path_unreachable_returns_none(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    # no such project anywhere
    assert m._project_path({"id": "ghost", "project": "-"}) is None


# ── workers feed ──────────────────────────────────────────────────────────────

def _worker_log(bus_dir, name, lines):
    wdir = bus_dir / "workers"
    wdir.mkdir(parents=True, exist_ok=True)
    with (wdir / name).open("w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(ln) + "\n")


def test_workers_marks_done(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    bus = hub.lab / ".bus"
    _worker_log(bus, "w1.jsonl", [
        {"ts": "2026-06-19T10:00:00", "role": "experiment-runner", "event": "start"},
        {"ts": "2026-06-19T10:01:00", "event": "action", "tool": "Read", "summary": "Read: x",
         "kind": "read"},
        {"ts": "2026-06-19T10:02:00", "event": "stop"},
    ])
    workers = m.workers.scan(bus, None)
    assert len(workers) == 1
    w = workers[0]
    assert w["role"] == "experiment-runner"
    assert w["status"] == "done"  # saw a stop event
    assert w["n_actions"] == 1


def test_workers_marks_working(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    bus = hub.lab / ".bus"
    # fresh activity, no stop -> working (file mtime is now)
    _worker_log(bus, "w2.jsonl", [
        {"ts": "2026-06-19T10:00:00", "role": "orchestrator", "event": "start"},
        {"ts": "2026-06-19T10:01:00", "event": "action", "tool": "Edit", "summary": "Edit: y",
         "kind": "edit"},
    ])
    workers = m.workers.scan(bus, None)
    assert workers[0]["status"] == "working"


# ── editor deep-links + paper status ───────────────────────────────────────────

def test_snapshot_includes_editor_scheme(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    # the fixture config has no `editor` key -> the documented default
    assert m.snapshot()["editor"] == "vscode"


def test_editor_scheme_reads_config(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    (hub.lab / "config.yaml").write_text("dashboard:\n  editor: cursor\n", encoding="utf-8")
    assert m.editor_scheme() == "cursor"


def test_paper_status_none_without_pdf(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    assert m._paper_status("demo") is None


def test_paper_status_reports_pdf_and_tex(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    pdir = hub.root / "studies" / "demo" / "paper"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "main.pdf").write_bytes(b"%PDF-1.5")
    (pdir / "main.tex").write_text("x", encoding="utf-8")
    st = m._paper_status("demo")
    assert st and st["pdf"] is True and isinstance(st["mtime"], int)
    assert st["tex"].endswith("main.tex")


def test_snapshot_item_carries_paper(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="writing", project="-")
    pdir = hub.root / "studies" / "demo" / "paper"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "main.pdf").write_bytes(b"%PDF")
    it = m.snapshot()["items"][0]
    assert it["paper"] and it["paper"]["pdf"] is True


def test_claims_count(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    assert m._claims_count("demo") == 0                  # no file
    paper = hub.root / "studies" / "demo" / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "claims.yaml").write_text("claims:\n  - id: C001\n  - id: C002\n", encoding="utf-8")
    assert m._claims_count("demo") == 2


def test_claims_count_counts_only_dict_items(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    paper = hub.root / "studies" / "demo" / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    # a bare-string list item must NOT be counted — parity with serve.claims_map's dict filter,
    # so the "claims (N)" button never disagrees with the rendered rows
    (paper / "claims.yaml").write_text("claims:\n  - id: C001\n  - just a string\n  - id: C002\n", encoding="utf-8")
    assert m._claims_count("demo") == 2


def test_snapshot_item_carries_claims_count(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="writing", project="-")
    paper = hub.root / "studies" / "demo" / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "claims.yaml").write_text("claims:\n  - id: C001\n", encoding="utf-8")
    assert m.snapshot()["items"][0]["claims"] == 1


# ── H2: dirty (non-UTF-8) bytes must never crash the snapshot ──────────────────

def test_read_text_tolerates_non_utf8_bytes(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    f = hub.lab / "dirty.txt"
    f.write_bytes(b"ok \xff\xfe not utf8\n")   # invalid UTF-8 — read_text(utf-8-sig) would raise
    assert "not utf8" in m.labfiles.read_text(f)        # errors='replace' → no UnicodeDecodeError


def test_snapshot_survives_non_utf8_event_line(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    hub.add_registry_row("demo", state="active", project=str(proj))
    bus = proj / ".bus"
    bus.mkdir(parents=True, exist_ok=True)
    (bus / "events.jsonl").write_bytes(b'{"ts":"2026-06-19T10:00:00","kind":"note","detail":"\xff\xfe"}\n')
    snap = m.snapshot()                          # a cp1252 byte in a tailed file used to 500 the whole snapshot
    assert snap["cold"] is False


# ── the registry's next-action text means nothing for checkpoints ─────────────

def test_registry_text_never_makes_or_clears_a_checkpoint(hub, monkeypatch):
    """Only the journal decides: a hand-edited registry line means nothing."""
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("b", state="proposal", project="-")
    _waits(hub, "b")
    reg = hub.lab / "REGISTRY.md"
    reg.write_text(reg.read_text(encoding="utf-8").replace("waits for you", "approved, go ahead"), encoding="utf-8")
    snap = m.snapshot()
    assert snap["items"][0]["waiting"] == ["approve-proposal"] and snap["checkpoints_waiting"] == 1
    assert all("gate" not in it for it in snap["items"])


# ── L4: directive terminal acks are sticky (parity with lab_bus.unresolved_directives) ──

def test_directive_threads_terminal_ack_is_sticky(hub, monkeypatch):
    import json
    m = _mod(hub, monkeypatch)
    bus = hub.lab / ".bus"
    bus.mkdir(parents=True, exist_ok=True)
    (bus / "directives.jsonl").write_text(json.dumps({"id": "d-001", "text": "do x"}) + "\n", encoding="utf-8")
    # done THEN a later out-of-order 'seen' must not reopen the directive
    (bus / "events.jsonl").write_text(
        json.dumps({"ts": "2026-06-19T10:00:00", "kind": "directive_done", "data": {"ref": "d-001"}}) + "\n"
        + json.dumps({"ts": "2026-06-19T10:05:00", "kind": "directive_seen", "data": {"ref": "d-001"}}) + "\n",
        encoding="utf-8")
    th = next(t for t in m._directive_threads(bus) if t["id"] == "d-001")
    assert th["state"] == "done"


def test_directive_threads_carry_record_target(hub, monkeypatch):
    import json
    m = _mod(hub, monkeypatch)
    bus = hub.lab / ".bus"
    bus.mkdir(parents=True, exist_ok=True)
    # a directive aimed at 'spark-1' that landed on the hub bus (pre-spawn) keeps its target
    (bus / "directives.jsonl").write_text(json.dumps({"id": "d-001", "text": "park", "target": "spark-1"}) + "\n", encoding="utf-8")
    th = m._directive_threads(bus)[0]
    assert th["target"] == "spark-1"


def test_snapshot_keeps_targeted_hub_instructions_before_and_after_project_attachment(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row('pending', state='proposal')
    hub.add_registry_row('other', state='proposal')
    bus = hub.lab / '.bus'
    bus.mkdir(parents=True, exist_ok=True)
    rows = [{'id': f'd-{i:03}', 'target': 'pending', 'ts': f'2026-10-19T10:00:0{i}',
             'kind': 'command', 'action': action, 'text': action} for i, action in enumerate(('park', 'kill', 'prioritize'), 1)]
    rows += [{'id': 'd-004', 'target': 'hub', 'text': 'Lab instruction'},
             {'id': 'd-005', 'target': 'other', 'text': 'Another study'}]
    (bus / 'directives.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    first = m.snapshot()
    item = next(it for it in first['items'] if it['id'] == 'pending')
    assert not item['has_project'] and item['state'] == 'proposal'
    assert [d['action'] for d in item['directives']] == ['park', 'kill', 'prioritize']
    assert all(d['scope'] == 'hub' and d['state'] == 'pending' for d in item['directives'])
    assert len(first['directives']) == 5, 'the existing hub API remains complete'
    project = hub.make_project('pending')
    (project / '.bus').mkdir()
    (project / '.bus/directives.jsonl').write_text(json.dumps({'id': 'd-001', 'ts': '2026-10-19T11:00:00', 'text': 'Project instruction'}) + '\n', encoding='utf-8')
    (bus / 'events.jsonl').write_text(json.dumps({'kind': 'directive_seen', 'data': {'ref': 'd-001'}}) + '\n', encoding='utf-8')
    second = m.snapshot()
    item = next(it for it in second['items'] if it['id'] == 'pending')
    assert item['has_project'] and len(item['directives']) == 4
    assert item['directives'][0]['state'] == 'seen'
    assert item['directives'][-1]['scope'] == 'project'
    assert item['state'] == 'proposal', 'a pending instruction never claims its outcome happened'


# ── escalation lifecycle: an escalation_resolved event clears it ───────────────

def test_escalations_unresolved_and_resolved(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    evs = [
        {"ts": "2026-06-19T10:00:00", "source": "p1", "kind": "escalation", "detail": "need env bump", "data": {"id": "e-aaa"}},
        {"ts": "2026-06-19T10:01:00", "source": "p2", "kind": "escalation", "detail": "blocked", "data": {"id": "e-bbb"}},
        {"ts": "2026-06-19T10:02:00", "source": "p1", "kind": "escalation_resolved", "data": {"ref": "e-aaa"}},
    ]
    out = m._escalations(evs)
    ids = {e["id"] for e in out}
    assert ids == {"e-bbb"}                               # e-aaa resolved → dropped


def test_snapshot_includes_escalations_and_notebook(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    snap = m.snapshot()
    assert "escalations" in snap and isinstance(snap["escalations"], list)
    assert "notebook" in snap


# ── hardening from the adversarial verification pass ──────────────────────────

def test_load_yaml_non_mapping_returns_empty_dict(hub, monkeypatch):
    # a valid-YAML but non-mapping file must not make load_yaml(...).get(...) raise AttributeError
    m = _mod(hub, monkeypatch)
    for content in ("42\n", "- a\n- b\n", "just a bare string\n"):
        f = hub.lab / "x.yaml"
        f.write_text(content, encoding="utf-8")
        assert m.labfiles.load_yaml(f) == {}


def test_snapshot_survives_non_mapping_control_yaml(hub, monkeypatch):
    # a project whose control.yaml is valid YAML but a scalar/list must not blank the whole snapshot
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo", control=False)
    (proj / "control.yaml").write_text("42\n", encoding="utf-8")
    hub.add_registry_row("demo", state="active", project=str(proj))
    snap = m.snapshot()
    assert snap["cold"] is False and snap["items"][0]["project_type"] == "ml"
    assert snap["items"][0]["workflow"] == "research"


def test_notebook_age_from_dated_filename_not_mtime(hub, monkeypatch):
    # age comes from the ISO-dated filename (git-stable), not st_mtime which git ops reset
    import os
    m = _mod(hub, monkeypatch)
    old = hub.lab / "notebook" / "2020-01-01-ancient.md"
    old.write_text("# old\n", encoding="utf-8")
    os.utime(old, None)   # mtime = now, but the filename says 2020 → should read as very old
    nb = m._notebook_status()
    assert nb["latest"] == "2020-01-01-ancient.md"
    assert nb["age_hours"] > 24 * 365 * 3   # >3 years by the dated name, regardless of fresh mtime


def test_notebook_status_picks_latest_dated_and_ignores_readme(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    for name in ("2026-06-01-a.md", "2026-07-02-b.md", "README.md"):
        (hub.lab / "notebook" / name).write_text("x\n", encoding="utf-8")
    assert m._notebook_status()["latest"] == "2026-07-02-b.md"


# ── checkpoints and flags: waiting, decisions, what the watches saw ──────────

def test_changes_requested_still_waits_and_the_latest_record_shows(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="proposal")
    _waits(hub, "demo")
    _approve(hub, "demo", "approve-proposal", "changes-requested")
    it = m.snapshot()["items"][0]
    assert it["waiting"] == ["approve-proposal"]
    assert it["checkpoints"]["approve-proposal"]["decision"] == "changes-requested"


def test_an_outcome_the_workflow_leaves_open_asks_the_pi(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="analysis")
    kernel().studies.move(hub.root, "demo", "null-result", note="no effect at all")
    snap = m.snapshot()
    it = snap["items"][0]
    assert it["asks"] == {"outcome": "null-result", "at": "analysis", "note": "no effect at all"} and it["waiting"] == []
    ask = next(a for a in snap["attention"] if a["kind"] == "outcome")
    assert ask["sev"] == "block" and "null-result" in ask["body"] and ask["detail"]["study"] == "demo"


def test_full_runs_without_their_approval_are_flagged(hub, monkeypatch):
    """approve-full-runs is a `during` checkpoint with a watch that finds FULL runs started without (before) it:
    a run about the study raises a flag — on the item, as `slipped`, and in Needs you."""
    import time
    import types
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    hub.add_registry_row("demo", state="active", project=str(proj))
    for rid, stage in (("exp-001-pilot", "PILOT"), ("exp-002-full", "FULL")):
        (proj / "runs" / rid).mkdir(parents=True)
        (proj / "runs" / rid / "meta.json").write_text(json.dumps({"run_id": rid, "stage": stage,
                                                                   "started": "2026-01-01T00:00:00"}), encoding="utf-8")
    dg = kernel().watch.digest(hub.root, {"run_id": "r1", "subject": "demo", "started": "2026-01-01T00:00:00"}, {}, [], proj)
    assert any(f["rule"] == "approve-full-runs:full-runs-without-approval" for f in dg["flags"])
    it = m.snapshot()["items"][0]
    assert [x["id"] for x in it["slipped"]] == ["approve-full-runs"] and "exp-002-full" in it["slipped"][0]["why"]
    flag = next(a for a in m.snapshot()["attention"] if a["kind"] == "flag")
    assert flag["sev"] == "block" and flag["detail"]["study"] == "demo"
    kernel().watch.ack(hub.root, flag["detail"]["flag"], note="seen")
    assert m.snapshot()["items"][0]["slipped"] == []
    _approve(hub, "demo", "approve-full-runs")                       # approved: its watch stops looking
    assert kernel().watch.checkpoint_watches(hub.root, "demo", "research") == []
    # the check itself still names a FULL run that started before the approval, and clears one started after
    guard = load("guard")
    monkeypatch.setattr(guard, "HUB", hub.root)
    check = guard._load_checks()["full-runs-without-approval"]
    ns = types.SimpleNamespace(slug="demo", checkpoint="approve-full-runs")
    assert check.run(ns, guard) == 1
    later = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + 60))
    (proj / "runs" / "exp-002-full" / "meta.json").write_text(json.dumps({"run_id": "exp-002-full", "stage": "FULL",
                                                                          "started": later}), encoding="utf-8")
    assert check.run(ns, guard) == 0


def test_a_run_that_stopped_at_a_during_checkpoint_makes_the_study_wait(hub, monkeypatch):
    """The latest finished run's footer said needs_pi=approve-full-runs: the study waits there until approved."""
    import sys
    m = _mod(hub, monkeypatch)
    from conftest import REPO
    (hub.lab / "config.yaml").write_text(
        'lab:\n  projects_root: "../projects"\nagents:\n  programmatic:\n    enabled: true\n    backend: claude\n'
        f"    backends:\n      claude:\n        command: {json.dumps([sys.executable, str(REPO / 'tests' / 'fake_claude.py')])}\n",
        encoding="utf-8")
    hub.add_registry_row("demo", state="active", project=str(hub.make_project("demo")))
    ex = m.executor
    lab = ex.Lab(hub.root)
    run = ex.enqueue(lab, ex.RunSpec(skill="experiment", target="demo"))
    _t, _w, path, man = ex.find_run(lab, run["run_id"])
    ex.manifest.transition(lab, path, man, "completed", by="test", finished=ex.manifest.now(),
                           report={"needs_pi": "approve-full-runs", "summary": "pilots met the bar"})
    snap = m.snapshot()
    assert snap["items"][0]["waiting"] == ["approve-full-runs"] and snap["checkpoints_waiting"] == 1
    _approve(hub, "demo", "approve-full-runs")
    assert m.snapshot()["items"][0]["waiting"] == []


def test_a_study_follows_its_own_workflow(hub, monkeypatch):
    """A quick study has no checkpoints: reporting done moves it straight on, nothing waits."""
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("fast", state="proposal", workflow="quick")
    _waits(hub, "fast")
    it = m.snapshot()["items"][0]
    assert it["workflow"] == "quick" and it["state"] == "setup" and it["waiting"] == [] and it["slipped"] == []


# ── subagent visibility: tree, liveness, results, attribution, run join ──────────

def _wlog(bus, wid, lines):
    import time as _t
    wdir = bus / "workers"
    wdir.mkdir(parents=True, exist_ok=True)
    ts = _t.strftime("%Y-%m-%dT%H:%M:%S")
    (wdir / f"{wid}.jsonl").write_text(
        "\n".join(json.dumps({"ts": ts, "worker_id": wid, **ln}) for ln in lines) + "\n", encoding="utf-8")


def test_worker_tree_links_spawn_to_child_with_label_and_result(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    bus = hub.lab / ".bus"
    _wlog(bus, "SESS", [
        {"role": "orchestrator", "event": "start", "session_id": "SESS"},
        {"role": "orchestrator", "event": "spawn", "session_id": "SESS", "tool_use_id": "tuA",
         "spawns": "ideation-critic", "summary": "Agent: ideation-critic: Novelty skeptic: sparse attn"},
        {"role": "orchestrator", "event": "return", "session_id": "SESS", "tool_use_id": "tuA",
         "result": "verdict: bruised — closest work is X"},
    ])
    _wlog(bus, "agent-1", [
        {"role": "ideation-critic", "event": "start", "session_id": "SESS"},
        {"role": "ideation-critic", "event": "action", "session_id": "SESS", "tool": "WebSearch", "summary": "q"},
    ])
    ws = {w["worker_id"]: w for w in m.workers.link_workers(m.workers.scan(bus, None))}
    child, parent = ws["agent-1"], ws["SESS"]
    assert child["is_subagent"] and child["parent"] == "SESS" and parent["children"] == ["agent-1"]
    assert child["label"] == "Novelty skeptic: sparse attn" and child["spawn_id"] == "tuA"
    assert child["result"].startswith("verdict: bruised")          # from the parent's return line
    assert parent["n_actions"] == 1                                 # the Post(Agent) 'return' isn't double-counted


def test_worker_inside_long_tool_stays_working(hub, monkeypatch):
    import os
    import time as _t
    m = _mod(hub, monkeypatch)
    bus = hub.lab / ".bus"
    _wlog(bus, "agent-2", [
        {"role": "experiment-runner", "event": "start", "session_id": "S"},
        {"role": "experiment-runner", "event": "begin", "session_id": "S", "tool": "Bash",
         "summary": "Bash: uv run scripts/run.py", "kind": "run"},
    ])
    old = _t.time() - 1500                                          # 25 min into a PILOT run
    os.utime(bus / "workers" / "agent-2.jsonl", (old, old))
    w = m.workers.scan(bus, None)[0]
    assert w["status"] == "working" and w["in_tool"]["tool"] == "Bash"   # not idle, not dropped


def test_done_worker_lingers_with_result_and_resume_reopens(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    bus = hub.lab / ".bus"
    _wlog(bus, "agent-3", [{"role": "overseer", "event": "start", "session_id": "S"},
                           {"role": "overseer", "event": "stop", "session_id": "S", "result": "SUPPORTED"}])
    w = m.workers.scan(bus, None)[0]
    assert w["status"] == "done" and w["result"] == "SUPPORTED"
    _wlog(bus, "S", [{"event": "start", "session_id": "S"}, {"event": "stop", "session_id": "S"},
                     {"event": "start", "session_id": "S", "source": "resume"}])
    w = next(x for x in m.workers.scan(bus, None) if x["worker_id"] == "S")
    assert w["status"] != "done"                                    # a resumed session is live again


def test_hub_worker_promoted_to_project_from_worktree(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    hub.add_registry_row("demo", state="active", project=str(proj))
    _wlog(hub.lab / ".bus", "agent-4", [
        {"role": "experiment-runner", "event": "action", "session_id": "S", "project": "demo",
         "variant": "exp-004", "summary": "Bash: uv run x"}])
    snap = m.snapshot()
    w = next(x for x in snap["workers"] if x["worker_id"] == "agent-4")
    assert w["project"] == "demo" and w["variant"] == "exp-004"
    assert next(it for it in snap["items"] if it["id"] == "demo")["n_workers"] == 1


def test_snapshot_joins_headless_run_to_its_session_worker(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    adir = hub.lab / ".bus" / "agents"
    adir.mkdir(parents=True)
    (adir / "hub-propose-x-1.json").write_text(json.dumps({
        "schema": 2, "run_id": "hub-propose-x-1", "agent_id": "hub-propose-x-1", "status": "running",
        "session_id": "SID9", "command": "/propose x", "level": "hub", "target": "x", "backend": "claude",
        "started": "2026-01-01T00:00:00", "attempts": [{"started": "2026-01-01T00:00:00"}]}), encoding="utf-8")
    _wlog(hub.lab / ".bus", "SID9", [{"event": "start", "session_id": "SID9"}])
    snap = m.snapshot()
    assert snap["runs"][0]["run_id"] == "hub-propose-x-1" and snap["hub_agents"]
    w = next(x for x in snap["workers"] if x["worker_id"] == "SID9")
    assert w["run_id"] == "hub-propose-x-1" and w["label"] == "/propose x"
    for key in ("runs", "attention", "executor", "skills"):
        assert key in snap
    assert snap["executor"]["available"] is True and "propose" in snap["skills"]


def test_attention_lab_items_carry_checkpoints_and_flags(hub, monkeypatch):
    """attention.lab_items turns each study's waiting checkpoint into a `checkpoint` item (cp:<study>:<id>) and
    each open flag into a `flag` item (flag:<id>)."""
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("idea-g", state="proposal", next="/propose")
    _waits(hub, "idea-g")
    hub.add_registry_row("idea-s", state="active")
    f = kernel().watch.flag(hub.root, "warn", "tests were deleted", study="idea-s", rule="tests-removed")
    items = m.snapshot()["items"]
    by = {it["id"]: it for it in m.attention.lab_items(items, [], [])}
    cp = by["cp:idea-g:approve-proposal"]
    assert cp["kind"] == "checkpoint" and cp["sev"] == "block" and cp["title"] == "Approve the proposal"
    assert cp["detail"] == {"checkpoint": "approve-proposal", "study": "idea-g"}
    fl = by[f"flag:{f['id']}"]
    assert fl["kind"] == "flag" and fl["sev"] == "warn" and "tests were deleted" in fl["title"]


def test_attention_shows_a_waiting_checkpoint_in_needs_you(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("idea-g", state="proposal", next="/propose")
    _waits(hub, "idea-g")
    by = {it["id"]: it for it in m.snapshot()["attention"]}
    assert by["cp:idea-g:approve-proposal"]["kind"] == "checkpoint"


def test_attention_includes_flags_alerts_and_escalations(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("idea-g", state="proposal", next="/propose")
    hub.add_registry_row("idea-s", state="active")
    (hub.lab / ".bus").mkdir(parents=True, exist_ok=True)
    (hub.lab / ".bus" / "events.jsonl").write_text(json.dumps(
        {"ts": "2026-01-01T00:00:00", "source": "hub", "kind": "escalation", "detail": "need FULL run",
         "data": {"id": "e-1"}}) + "\n", encoding="utf-8")
    pd = hub.lab / "panels" / "gpu"
    pd.mkdir(parents=True)
    (pd / "panel.yaml").write_text("title: GPU\nsource: registry\n", encoding="utf-8")
    cache = hub.lab / ".bus" / "panels" / "data"
    cache.mkdir(parents=True)
    (cache / "gpu.json").write_text(json.dumps({"ts": "2026-01-01T00:00:00", "alerts": [
        {"level": "block", "say": "over the GPU budget", "study": "idea-s", "hold": True}]}), encoding="utf-8")
    kernel().watch.flag(hub.root, "block", "a ledger was rewritten", study="idea-s", hold=True, rule="ledger-rewritten")
    att = m.snapshot()["attention"]
    fl = next(it for it in att if it["kind"] == "flag")
    assert fl["sev"] == "block" and fl["detail"]["study"] == "idea-s" and fl["title"].endswith("— held")
    al = next(it for it in att if it["kind"] == "alert")
    assert al["sev"] == "block" and al["title"] == "over the GPU budget" and al["detail"]["panel"] == "gpu"
    assert al["detail"]["held"] is False                     # the PI did not let this panel hold launches
    esc = next(it for it in att if it["kind"] == "escalation")
    assert esc["detail"]["id"] == "e-1"
    assert not any(it["kind"] == "gate" for it in att)


def test_a_run_that_ended_ends_its_subagents_too(hub, monkeypatch):
    """A killed run's subagents (no SubagentStop ever came) leave with it — no ghosts in the world."""
    m = _mod(hub, monkeypatch)
    ws = [{"worker_id": "sess-1", "status": "working", "session_id": "sess-1"},
          {"worker_id": "sub-a", "status": "working", "is_subagent": True, "session_id": "sess-1", "run_id": "r-1"},
          {"worker_id": "sub-b", "status": "idle", "is_subagent": True, "session_id": "sess-1"}]
    m.workers.join_runs(ws, [{"run_id": "r-1", "session_id": "sess-1", "status": "killed"}])
    assert [w["status"] for w in ws] == ["done", "done", "done"]
