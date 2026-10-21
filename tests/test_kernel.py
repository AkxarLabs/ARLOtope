"""The kernel (tools/kernel/): the lab's definition, where its studies stand, and the only way they move.

    the definition   steps + one file per workflow + rooms + each skill's frontmatter; check() validates it
    moving           a procedure reports an outcome; the workflow says where it leads; a checkpoint on the way
                     makes the study wait, and the PI's approval carries the move through
    the journal      one append-only record — moves, waits, approvals, flags — that every view is a fold of
    approvals        the PI approves anything; a campaign only `me-or-campaign`, `auto` only an automatic
                     checkpoint, both only with every check passing; nothing inside an agent run approves
    migration        an older lab (stages.yaml, a hand-kept registry, approvals.jsonl, prose marks) comes over once
    the brief        where the study stands, how to finish, what the PI added, the checkpoints
    designs          a designer's draft is an overlay, checked like any draft, its loosened checkpoints listed first
    watch            each run's digest is computed from git and the trace; watches raise flags; a hold stops launches
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest
import yaml

from conftest import REPO, kernel, load

K = kernel()
model, studies, checkpoints, journal = K.model, K.studies, K.checkpoints, K.journal


@pytest.fixture(autouse=True)
def _not_in_a_run(monkeypatch):
    monkeypatch.delenv("NEWTS_RUN_ID", raising=False)


@pytest.fixture
def lab(hub):
    """A hub with its own definition (a copy of this repo's workflow/ and skills), so tests can edit it."""
    shutil.copytree(REPO / "workflow", hub.root / "workflow")
    shutil.copytree(REPO / ".claude" / "skills", hub.root / ".claude" / "skills")
    shutil.copytree(REPO / "agent-roles", hub.root / "agent-roles")
    return hub


def _edit_workflow(hub, wid, fn):
    p = hub.root / "workflow" / "workflows" / f"{wid}.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    fn(doc)
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _audits(hub, scripts: dict):
    """The lab's own audits: checks/<name>.py exiting with the given codes, named in rules.yaml."""
    (hub.root / "checks").mkdir(exist_ok=True)
    for name, code in scripts.items():
        (hub.root / "checks" / f"{name}.py").write_text(f"import sys\nprint('{name} ran')\nsys.exit({code})\n", encoding="utf-8")
    rp = hub.root / "workflow" / "rules.yaml"
    rl = yaml.safe_load(rp.read_text(encoding="utf-8"))
    rl["audits"] = (rl.get("audits") or []) + [{"name": n.replace("_", "-"), "run": [f"{n}.py", "{paper}"]} for n in scripts]
    rp.write_text(yaml.safe_dump(rl, sort_keys=False), encoding="utf-8")


# ── the definition ───────────────────────────────────────────────────────────────────────────────
def test_the_shipped_definition_is_consistent_and_its_docs_current():
    assert model.check(None, K.rules.check_names(None)) == []
    assert K.rules.check(None) == []
    sys.path.insert(0, str(REPO / "tools"))
    import lab_docs
    assert lab_docs.render(REPO, check_only=True) == [], "run `newts docs`"


def test_steps_workflows_and_where_outcomes_lead():
    st = model.steps()
    assert st["parked"]["shelf"] and st["killed"]["shelf"] and not st["seed"]["shelf"]
    assert model.default_workflow() == "research"
    assert model.outcome_target("research", "analysis", "done") == "writing"
    assert model.outcome_target("research", "analysis", "more-experiments") == "active"
    assert model.outcome_target("research", "analysis", "null-result") == model.ASK
    assert model.outcome_target("research", "analysis", "anything-else") == model.ASK   # unrouted: the PI decides
    assert model.outcome_target("research", "final", "done") is None                    # the end: finished
    assert model.outcome_target("quick", "seed", "done") == "proposal"                  # each workflow its own path
    assert model.outcome_target("target", "active", "kill") == "killed"
    assert [c["id"] for c in model.before_on_the_way("research", "proposal", "setup")] == ["approve-proposal"]
    assert model.before_on_the_way("research", "analysis", "active") == []              # a move back passes none
    assert [c["id"] for c in model.before_on_the_way("research", "seed", "final")] == ["approve-proposal", "finalize-paper"]


def test_a_procedure_variant_is_used_where_a_workflow_or_study_says(lab):
    K_new = __import__("conftest").load("new")
    K_new.new_skill(lab.root, "lit-review-quick", "lit-review", title="A quick scan")
    p = model.procedure("lit-review-quick", lab.root)
    assert p["like"] == "lit-review" and p["title"] == "A quick scan" and p["args"] == "slug"   # inherited
    _edit_workflow(lab, "quick", lambda d: d.update(use={"triage": "lit-review-quick"}))
    assert model.does("seed", "quick", None, lab.root) == "lit-review-quick"
    assert model.does("seed", "research", None, lab.root) == "triage"
    assert model.does("seed", "research", {"triage": "lit-review-quick"}, lab.root) == "lit-review-quick"


def test_check_catches_what_would_break(lab):
    def bad(d):
        d["path"].append("nowhere")
        d["routes"]["analysis"]["done"] = "active"                       # done can't be routed
        d["routes"]["analysis"]["oops"] = "lit-review-x"
        d["checkpoints"].append({"id": "x1", "title": "X", "before": "seed"})
        d["checkpoints"].append({"id": "x2", "title": "X", "during": "active"})
        d["checkpoints"].append({"id": "approve-proposal", "title": "dup", "before": "writing"})
        d["checkpoints"].append({"id": "x3", "title": "X", "before": "writing", "approver": "auto"})
        d["checkpoints"].append({"id": "x4", "title": "X", "before": "writing", "checks": ["no-such-check"]})
    _edit_workflow(lab, "research", bad)
    probs = "\n".join(model.check(lab.root, K.rules.check_names(lab.root)))
    for frag in ("unknown step 'nowhere'", "`done` always means the same thing", "oops → 'lit-review-x'",
                 "nothing comes before the first step", "needs at:", "used twice", "needs checks: to pass",
                 "unknown check 'no-such-check'"):
        assert frag in probs, frag


def test_a_new_skill_folder_is_a_procedure_with_no_other_edit(lab):
    d = lab.root / ".claude" / "skills" / "survey"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: survey\ndescription: Survey the field: a quick look. Argument; a topic.\n---\n\n"
                                "# Survey\n", encoding="utf-8")
    p = model.procedure("survey", lab.root)
    assert p["kind"] == "utility" and p["launchable"] and p["does"].startswith("Survey the field")
    (d / "SKILL.md").write_text("---\nname: survey\ndescription: Survey.\nnewts:\n  kind: stage\n  args: slug\n"
                                "  outcomes: {done: settled, nothing-there: 'the field is empty'}\n---\n# Survey\n", encoding="utf-8")
    p = model.procedure("survey", lab.root)
    assert p["outcomes"] == ["done", "nothing-there"] and p["outcome_notes"]["nothing-there"] == "the field is empty"
    assert not [x for x in model.check(lab.root) if "survey" in x]


def test_a_skills_frontmatter_need_not_be_strict_yaml():
    meta = model.skill_meta("---\nname: x\ndescription: With `--flag <v>`: does y: z.\nnewts:\n  kind: entry\n---\nbody")
    assert meta["description"].startswith("With `--flag") and meta["newts"] == {"kind": "entry"}


def test_the_definition_writes_back_whole_and_reads_the_same(lab, tmp_path):
    m = model.load(lab.root)
    d = {"steps": m["steps"], "rooms": m["rooms"], "workflows": m["workflows"]}
    out = tmp_path / "copy"
    shutil.copytree(lab.root / ".claude", out / ".claude")
    K.define.write(out, d)
    m2 = model.load(out)
    assert m2["steps"] == m["steps"] and m2["rooms"] == m["rooms"]
    assert [(w["id"], w["path"], w["routes"], w["checkpoints"]) for w in m2["workflows"]] == \
           [(w["id"], w["path"], w["routes"], w["checkpoints"]) for w in m["workflows"]]
    text = (out / "workflow" / "workflows" / "research.yaml").read_text(encoding="utf-8")
    assert text.startswith("# A workflow:") and "\npath: [seed, lit-review" in text and "default: true" in text


def _done(lab, slug):
    """The study's procedure finished its work (what it must produce is written) and reports done."""
    lab.produce(slug)
    return studies.move(lab.root, slug, "done")


# ── moving ───────────────────────────────────────────────────────────────────────────────────────
def test_a_study_walks_its_workflow_by_outcomes(lab):
    studies.new(lab.root, "alpha", "Alpha")
    assert studies.study(lab.root, "alpha")["step"] == "seed"
    with pytest.raises(studies.StudyError, match="IDEA.md is not"):          # done means the step's work is there
        studies.move(lab.root, "alpha", "done")
    for want in ("lit-review", "scoping", "proposal"):
        assert _done(lab, "alpha")["step"] == want
    res = _done(lab, "alpha")                         # the proposal's checkpoint is ahead
    assert res == {"moved": False, "waiting": "approve-proposal", "title": "Approve the proposal", "step": "proposal",
                   "to": "setup"}
    assert studies.next_for(lab.root, "alpha")["procedure"] is None       # nothing runs while it waits
    rec = checkpoints.decide(lab.root, "alpha", "approve-proposal", via="cli", note="10 GPU-h")
    assert rec["moved"]["step"] == "setup"                                 # the approval carries the move
    assert studies.next_for(lab.root, "alpha")["procedure"] == "spawn-project"
    _done(lab, "alpha")
    _done(lab, "alpha")
    assert studies.move(lab.root, "alpha", "more-experiments")["step"] == "active"   # a route back
    _done(lab, "alpha")
    assert studies.move(lab.root, "alpha", "null-result") == {"moved": False, "waiting": "pi", "step": "analysis",
                                                               "outcome": "null-result"}
    row = next(r for r in studies.rows(lab.root) if r["id"] == "alpha")
    assert row["next"] == "waits for you: it reported `null-result`"
    studies.move_to(lab.root, "alpha", "writing", note="write it up as a negative result")
    _done(lab, "alpha")
    assert _done(lab, "alpha")["waiting"] == "finalize-paper"
    checkpoints.decide(lab.root, "alpha", "finalize-paper", via="cli")
    assert _done(lab, "alpha") == {"moved": False, "finished": True, "step": "final"}
    with pytest.raises(studies.StudyError, match="finished"):
        _done(lab, "alpha")
    reg = (lab.lab / "REGISTRY.md").read_text(encoding="utf-8")
    assert "| alpha | Alpha | final | research |" in reg and "finished" in reg and "Generated" in reg


def test_the_quick_workflow_runs_end_to_end(lab):
    """The lab's shortest workflow: no checkpoints, analysis straight to final."""
    studies.new(lab.root, "q1", "Quick one", workflow="quick")
    seen = [_done(lab, "q1").get("step") for _ in range(5)]
    assert seen == ["proposal", "setup", "active", "analysis", "final"]
    assert _done(lab, "q1")["finished"]


def test_moves_that_are_not_legal_are_refused(lab):
    studies.new(lab.root, "b", "B")
    with pytest.raises(studies.StudyError, match="not an outcome of seed"):
        studies.move(lab.root, "b", "more-experiments")
    with pytest.raises(studies.StudyError, match="no study"):
        studies.move(lab.root, "nope", "done")
    with pytest.raises(studies.StudyError, match="already exists"):
        studies.new(lab.root, "b", "again")
    studies.move(lab.root, "b", "park", note="not now")
    with pytest.raises(studies.StudyError, match="only the PI brings it back"):
        studies.move(lab.root, "b", "done")
    assert studies.study(lab.root, "b")["was"] == "seed"
    studies.move_to(lab.root, "b", "lit-review", note="back on")         # the PI revives it
    assert studies.study(lab.root, "b")["step"] == "lit-review"
    with pytest.raises(studies.StudyError, match="not a step of the research workflow"):
        studies.move_to(lab.root, "b", "nowhere")


def test_inside_an_agent_run_only_the_agents_own_moves_are_allowed(lab, monkeypatch):
    studies.new(lab.root, "c", "C", at="proposal")
    lab.produce("c")
    monkeypatch.setenv("NEWTS_RUN_ID", "hub-1")
    assert studies.move(lab.root, "c", "done")["waiting"] == "approve-proposal"
    assert journal.events(lab.root, "c")[-1]["by"] == "run:hub-1"
    for act in (lambda: checkpoints.decide(lab.root, "c", "approve-proposal", via="cli"),
                lambda: checkpoints.decide(lab.root, "c", "approve-proposal", by="pi", via="dashboard"),
                lambda: studies.move_to(lab.root, "c", "setup"),
                lambda: studies.set_workflow(lab.root, "c", "quick"),
                lambda: checkpoints.decide_lab(lab.root, "campaign:x", via="cli")):
        with pytest.raises((studies.StudyError, checkpoints.CheckpointError), match="the PI's"):
            act()
    assert not journal.approved(lab.root, "c", "approve-proposal")


def test_a_study_follows_its_own_workflow_and_swaps(lab):
    studies.new(lab.root, "t", "Target", workflow="target")
    assert studies.study(lab.root, "t")["step"] == "active"
    ev = studies.set_workflow(lab.root, "t", "quick")
    assert ev["workflow"] == "quick" and "not on quick's path" not in str(ev.get("note"))
    studies.set_use(lab.root, "t", {"experiment": "improve"})
    assert studies.next_for(lab.root, "t")["procedure"] == "improve"
    with pytest.raises(studies.StudyError, match="unknown procedure"):
        studies.set_use(lab.root, "t", {"experiment": "nope"})


def test_renaming_steps_moves_the_studies_with_them(lab):
    studies.new(lab.root, "r", "R", at="active")
    studies.remap(lab.root, {"active": "running"})
    assert studies.study(lab.root, "r")["step"] == "running"


# ── approvals ────────────────────────────────────────────────────────────────────────────────────
def test_approver_rules_and_checks(lab):
    studies.new(lab.root, "d", "D", at="proposal")
    with pytest.raises(checkpoints.CheckpointError, match="does not approve itself"):
        checkpoints.decide(lab.root, "d", "approve-proposal", by="auto", via="kernel")
    with pytest.raises(checkpoints.CheckpointError, match="unknown approver"):
        checkpoints.decide(lab.root, "d", "approve-proposal", by="someone", via="cli")
    rec = checkpoints.decide(lab.root, "d", "approve-proposal", by="campaign:c1", via="keeper")
    assert rec["by"] == "campaign:c1" and rec["workflow"] == "research"
    with pytest.raises(checkpoints.CheckpointError):                     # a campaign can't take one back
        checkpoints.decide(lab.root, "d", "approve-proposal", "revoked", by="campaign:c1", via="keeper")
    studies.new(lab.root, "tg", "T", workflow="target")
    with pytest.raises(checkpoints.CheckpointError, match="PI only"):
        checkpoints.decide(lab.root, "tg", "approve-final-output", by="campaign:c1", via="keeper")
    studies.new(lab.root, "e", "E", at="internal-review")
    good = {n: {"code": 0} for n in ("claims", "multiseed", "ablations", "eval", "prereg")}
    bad = dict(good, prereg={"code": 1})
    with pytest.raises(checkpoints.CheckpointError, match="prereg did not pass"):
        checkpoints.decide(lab.root, "e", "finalize-paper", by="campaign:c1", via="keeper", checks=bad)
    checkpoints.decide(lab.root, "e", "finalize-paper", by="pi", via="cli", checks=bad)   # the PI decides
    assert journal.approved(lab.root, "e", "finalize-paper")


def test_an_automatic_checkpoint_approves_itself_on_the_move_when_its_checks_pass(lab):
    _edit_workflow(lab, "research", lambda d: d["checkpoints"].append(
        {"id": "auto-gate", "title": "Auto gate", "before": "writing", "approver": "auto", "checks": ["the-audit"]}))
    _audits(lab, {"the_audit": 1})
    studies.new(lab.root, "f", "F", at="analysis")
    assert studies.move(lab.root, "f", "done")["waiting"] == "auto-gate"                 # its check failed
    assert checkpoints.cached_checks(lab.root, "f", "auto-gate")["results"]["the-audit"]["code"] == 1   # on its sheet
    (lab.root / "checks" / "the_audit.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    assert studies.move(lab.root, "f", "done")["step"] == "writing"                      # passes now: it moves on
    assert journal.latest(lab.root, "f", "auto-gate")["by"] == "auto"


def test_the_sheet_shows_evidence_checks_and_history(lab):
    lab.add_registry_row("g", state="proposal", project="../projects/g")
    lab.make_project("g")
    (lab.root / "studies" / "g" / "proposal.md").write_text("# P\n", encoding="utf-8")
    studies.move(lab.root, "g", "done")
    r = checkpoints.readiness(lab.root, "g", "approve-proposal")
    assert r["waiting"] and r["here"] and not r["approved"]
    ev = {e["path"]: e["exists"] for e in r["evidence"]}
    assert ev["studies/g/proposal.md"] and not ev["studies/g/lit-review.md"]
    assert [c["id"] for c in checkpoints.waiting(lab.root, "g")] == ["approve-proposal"]
    checkpoints.decide(lab.root, "g", "approve-proposal", via="cli", note="ok")
    r = checkpoints.readiness(lab.root, "g", "approve-proposal")
    assert r["approved"] and r["record"]["note"] == "ok" and len(r["history"]) == 1 and checkpoints.waiting(lab.root, "g") == []


def test_a_check_runs_against_the_lab_being_approved(lab):
    import time
    _edit_workflow(lab, "research", lambda d: d["checkpoints"][0].update(checks=["writeback"]))
    lab.add_registry_row("zz-only-here", state="proposal")
    lab.notebook_entry(f"{time.strftime('%Y-%m-%d')}-zz.md", "worked on zz-only-here today\n")
    cp = checkpoints.find(lab.root, "zz-only-here", "approve-proposal")
    assert checkpoints.run_checks(lab.root, "zz-only-here", cp)["writeback"]["code"] == 0
    assert checkpoints.run_checks(lab.root, "zz-only-here", {"id": "x", "checks": ["no-such"]}) == \
        {"no-such": {"code": 127, "out": "no audit or check called no-such"}}


def test_lab_wide_approvals_are_the_pis(lab):
    rec = checkpoints.decide_lab(lab.root, "campaign:c1", via="dashboard", note="may approve: approve-proposal")
    assert rec["study"] == "lab" and journal.approved(lab.root, "lab", "campaign:c1")
    with pytest.raises(checkpoints.CheckpointError, match="not a lab-wide approval"):
        checkpoints.decide_lab(lab.root, "approve-proposal", via="cli")


def test_the_journal_is_append_only_and_tolerant(lab):
    studies.new(lab.root, "h", "H")
    with journal.path(lab.root).open("a", encoding="utf-8") as f:
        f.write("{torn line\n\n" + json.dumps({"no": "kind"}) + "\n")
    _done(lab, "h")
    assert studies.study(lab.root, "h")["step"] == "lit-review"
    assert [e["kind"] for e in journal.events(lab.root, "h")] == ["new", "move"]


# ── migration ────────────────────────────────────────────────────────────────────────────────────
def _old_lab(hub):
    """An older lab: the former manifest, a hand-kept registry, approvals.jsonl, marks in documents."""
    (hub.root / "workflow").mkdir(exist_ok=True)
    old = (REPO / "tests/fixtures/legacy-stages.yaml").read_text(encoding="utf-8")
    (hub.root / "workflow" / "stages.yaml").write_text(old, encoding="utf-8")
    shutil.copytree(REPO / ".claude" / "skills", hub.root / ".claude" / "skills")
    rows = [("a", "lit-review", "-"), ("b", "active", "../projects/b"), ("c", "proposal", "-"), ("d", "final", "-"),
            ("e", "killed", "-"), ("t", "active", "../projects/t")]
    head = ("# Lab Registry\n\n| ID | Title | State | Idea | Project | Paper | Updated | Next action |\n"
            "|----|-------|-------|------|---------|-------|---------|-------------|\n")
    (hub.lab / "REGISTRY.md").write_text(head + "".join(f"| {i} | Title {i} | {s} | x | {p} | - | 2026-09-01 | n |\n"
                                                         for i, s, p in rows), encoding="utf-8")
    hub.make_project("b")
    pt = hub.make_project("t")
    ctl = yaml.safe_load((pt / "control.yaml").read_text(encoding="utf-8"))
    ctl["target"] = {"active": True, "final_run_id": "exp-9"}
    (pt / "control.yaml").write_text(yaml.safe_dump(ctl), encoding="utf-8")
    (hub.root / "studies" / "c").mkdir(parents=True)
    (hub.root / "studies" / "c" / "proposal.md").write_text("<!-- PI Gate 1 approved via dashboard -->\n", encoding="utf-8")
    (hub.lab / "approvals.jsonl").write_text(json.dumps({"ts": "2026-09-02T10:00:00", "study": "b", "checkpoint": "loop",
                                                         "decision": "approved", "by": "pi", "via": "dashboard",
                                                         "note": "mode: explore"}) + "\n", encoding="utf-8")


def test_an_older_lab_comes_over_once(hub):
    _old_lab(hub)
    shutil.rmtree(hub.root / ".claude" / "skills" / "triage")         # a step that is new since the lab was made
    assert K.migrate.needed(hub.root)
    done = K.migrate.run(hub.root)
    assert any("steps.yaml" in x for x in done) and any("journal.jsonl" in x for x in done)
    assert any("/triage" in x for x in done) and (hub.root / ".claude" / "skills" / "triage" / "SKILL.md").is_file()
    assert (hub.root / "workflow" / "stages.yaml.pre-kernel").exists() and not (hub.lab / "approvals.jsonl").exists()
    assert model.check(hub.root) == []
    st = {s["id"]: s for s in studies.all_studies(hub.root).values()}
    assert st["a"]["step"] == "scoping"                       # its literature review was done: scope comes next
    assert st["b"]["step"] == "active" and st["b"]["project"] == "../projects/b"
    assert st["c"]["step"] == "setup"                         # its proposal was approved: the project comes next
    assert st["d"]["finished"] and st["e"]["step"] == "killed"
    assert st["t"]["workflow"] == "target"
    assert journal.latest(hub.root, "b", "approve-loop")["note"] == "mode: explore"
    assert journal.latest(hub.root, "c", "approve-proposal")["via"] == "migration"
    assert journal.approved(hub.root, "t", "approve-final-output")
    assert K.migrate.run(hub.root) == [] and not K.migrate.needed(hub.root)


def test_a_lab_that_changed_its_manifest_is_converted_as_it_is(hub):
    (hub.root / "workflow").mkdir()
    doc = {"states": [{"id": "idea", "label": "Idea", "room": "r"}, {"id": "build", "label": "Build", "room": "r"},
                      {"id": "done", "label": "Done", "room": "r"}],
           "side_states": [{"id": "parked"}, {"id": "killed"}], "back_edges": [["done", "build"]],
           "rooms": [{"id": "r", "label": "R", "states": ["idea", "build", "done"]}],
           "next_for_state": {"idea": "discuss", "build": "experiment"},
           "workflows": [{"id": "mine", "steps": ["idea", "build", "done"],
                          "checkpoints": [{"id": "ok-build", "before": "build", "then": "spawn-project"}]}]}
    (hub.root / "workflow" / "stages.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    shutil.copytree(REPO / ".claude" / "skills", hub.root / ".claude" / "skills")
    K.migrate.run(hub.root)
    w = model.workflow("mine", hub.root)
    assert w["path"] == ["idea", "spawn-project", "build", "done"]          # `then:` became a step of its own
    assert w["checkpoints"][0]["before"] == "spawn-project" and w["routes"] == {"done": {"to-build": "build"}}


# ── the brief, instructions, proposals ───────────────────────────────────────────────────────────
def test_the_brief_says_where_how_to_finish_and_what_the_pi_added(lab):
    studies.new(lab.root, "k", "K", at="analysis")
    K.instructions.write("add", "analyze", "Report effect sizes with intervals.", lab.root)
    K.instructions.write("step", "analysis", "Plot every seed.", lab.root, study=None)
    (lab.root / "studies" / "k").mkdir(parents=True)
    K.instructions.write("add", "analyze", "This study: look at layer 7.", lab.root, study="k")
    checkpoints.decide(lab.root, "k", "approve-full-runs", via="cli", note="3 seeds max")
    text, h = K.brief.brief(lab.root, "analyze", study="k")
    assert text.startswith("NEWTS BRIEF /analyze · study k · sha=" + h)
    assert "k is at **Analysis**" in text and "`more-experiments` → Experiments" in text
    assert "`done` → Writing" in text and "`null-result` the PI decides" in text
    assert K.brief.newts_cmd(lab.root) + ' move k' in text
    assert text.index("Report effect sizes") < text.index("look at layer 7")             # lab-wide, then the study's
    assert "Plot every seed." in text and "The PI's note: 3 seeds max" in text
    with pytest.raises(KeyError):
        K.brief.brief(lab.root, "no-such-procedure")


def test_agents_propose_instructions_and_only_the_pi_takes_them(lab):
    rec = K.instructions.propose("add", "scope", "Always list two alternatives.", lab.root, why="seen twice", by="r1")
    assert [p["id"] for p in K.instructions.proposals(lab.root)] == [rec["id"]]
    K.instructions.resolve(rec["id"], True, lab.root)
    assert K.instructions.read("add", "scope", lab.root) == "Always list two alternatives."
    with pytest.raises(ValueError, match="already accepted"):
        K.instructions.resolve(rec["id"], False, lab.root)
    with pytest.raises(ValueError, match="unknown step"):
        K.instructions.propose("step", "nowhere", "x", lab.root)


# ── designs ──────────────────────────────────────────────────────────────────────────────────────
def test_a_designers_draft_is_checked_against_the_live_lab_loosening_first(lab, tmp_path):
    d = tmp_path / "design"
    wf = yaml.safe_load((lab.root / "workflow" / "workflows" / "research.yaml").read_text(encoding="utf-8"))
    wf["checkpoints"] = [c for c in wf["checkpoints"] if c["id"] != "approve-full-runs"]
    next(c for c in wf["checkpoints"] if c["id"] == "finalize-paper")["approver"] = "auto"
    wf["path"].insert(wf["path"].index("writing"), "replication")
    (d / "workflow" / "workflows").mkdir(parents=True)
    (d / "workflow" / "workflows" / "research.yaml").write_text(yaml.safe_dump(wf, sort_keys=False), encoding="utf-8")
    probs, said = K.diff.check_overlay(lab.root, d)
    assert any("unknown step 'replication'" in x for x in probs)
    steps = yaml.safe_load((lab.root / "workflow" / "steps.yaml").read_text(encoding="utf-8"))
    steps["replication"] = {"label": "Replication", "do": "experiment", "room": "lab"}
    (d / "workflow" / "steps.yaml").write_text(yaml.safe_dump(steps, sort_keys=False), encoding="utf-8")
    probs, said = K.diff.check_overlay(lab.root, d)
    assert probs == []
    assert any("removes the checkpoint “Approve full runs”" in x for x in said[:2])
    assert any("is approved by auto now (was me-or-campaign)" in x for x in said[:2])
    assert any("adds the step Replication" in x for x in said)


# ── monitoring ───────────────────────────────────────────────────────────────────────────────────
def _git(cwd, *a):
    subprocess.run(["git", *a], cwd=str(cwd), check=True, capture_output=True)


def test_watch_compares_existing_dirty_content_and_reversions(tmp_path):
    _git(tmp_path, 'init', '-q')
    file = tmp_path / 'method.py'
    file.write_text('original\n', encoding='utf-8')
    _git(tmp_path, 'add', '.')
    _git(tmp_path, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'baseline')
    file.write_text('existing edit\n', encoding='utf-8')
    snap = K.watch.snapshot([tmp_path])
    assert K.watch.changes(snap) == {'written': [], 'deleted': [], 'commits': 0}
    file.write_text('new edit, same dirty status\n', encoding='utf-8')
    assert K.watch.changes(snap)['written'] == [file.as_posix()]
    _git(tmp_path, 'checkout', '--', 'method.py')
    assert K.watch.changes(snap)['written'] == [file.as_posix()]
    file.unlink()
    snap = K.watch.snapshot([tmp_path])
    assert K.watch.changes(snap)['deleted'] == []  # An existing deletion is not a new run action.


def test_watch_limits_an_enclosing_repo_to_all_selected_folders(tmp_path):
    _git(tmp_path, 'init', '-q')
    _git(tmp_path, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'baseline', '--allow-empty')
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir(); second.mkdir()
    outside = tmp_path / 'unrelated.txt'
    outside.write_text('prior edit\n', encoding='utf-8')
    snap = K.watch.snapshot([first, second])
    outside.write_text('concurrent edit elsewhere\n', encoding='utf-8')
    for folder in (first, second):
        (folder / 'result.md').write_text('in scope\n', encoding='utf-8')
    assert K.watch.changes(snap)['written'] == sorted((p / 'result.md').as_posix() for p in (first, second))
    _git(tmp_path, 'add', 'unrelated.txt')
    _git(tmp_path, '-c', 'user.email=t@t', '-c', 'user.name=t', 'commit', '-qm', 'outside selected folders')
    assert K.watch.changes(snap)['commits'] == 0
    snap = K.watch.snapshot([first])
    (first / 'result.md').unlink()
    assert K.watch.changes(snap)['deleted'] == [(first / 'result.md').as_posix()]


def test_a_runs_digest_flags_what_it_did(lab):
    pdir = lab.make_project("w")
    lab.add_registry_row("w", state="active", project=str(pdir))
    for d in (pdir,):
        _git(d, "init", "-q")
        _git(d, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
    (pdir / "configs").mkdir()
    snap = K.watch.snapshot([pdir], lab.root)
    (pdir / "configs" / "base.yaml").write_text("eval: changed\n", encoding="utf-8")   # a watched file
    (pdir / "notes.txt").write_text("fine\n", encoding="utf-8")
    bus = lab.lab / ".bus"
    (bus / "workers").mkdir(parents=True)
    (bus / "workers" / "x.jsonl").write_text(json.dumps({"ts": "2099-01-01T00:00:00", "run_id": "r9", "event": "action",
                                                         "tool": "Bash", "summary": "Bash: git push origin main"}) + "\n",
                                            encoding="utf-8")
    m = {"run_id": "r9", "subject": "w", "started": "2026-01-01T00:00:00", "denials": 3, "usage": {"cost_usd": 0.12}}
    dg = K.watch.digest(lab.root, m, snap, [bus], pdir)
    assert any(f.endswith("configs/base.yaml") for f in dg["files"]["written"]) and dg["cost_usd"] == 0.12
    rules_hit = {f["rule"] for f in dg["flags"]}
    assert {"eval-protocol-edited", "refused", "pushed"} <= rules_hit and dg["notable"] == ["git push origin main"]
    said = "\n".join(K.watch.render(dg))                                          # `newts run <id>` shows it
    assert "configs/base.yaml" in said and "$ git push origin main" in said and "3 denied" in said
    seen = load("dashboard/sources").workers.compact_run({**m, "digest": dg})["digest"]   # …and the run sheet
    assert seen["written"] == len(dg["files"]["written"]) and seen["denials"] == 3 and seen["flags"]
    open_ = {f["rule"] for f in K.watch.flags(lab.root, "w")}
    assert "eval-protocol-edited" in open_ and "pushed" not in open_                 # info lives on the digest only
    fid = next(f["id"] for f in K.watch.flags(lab.root, "w") if f["rule"] == "eval-protocol-edited")
    K.watch.ack(lab.root, fid, note="intended")
    assert "eval-protocol-edited" not in {f["rule"] for f in K.watch.flags(lab.root, "w")}


def test_a_hold_flag_stops_the_studys_launches_until_acknowledged(lab):
    sys.path.insert(0, str(REPO / "tools"))
    import lab_profile
    from executor.lab import Lab
    lab.add_registry_row("h", state="active")
    f = K.watch.flag(lab.root, "block", "a ledger was rewritten", study="h", hold=True, rule="ledger-rewritten")
    with pytest.raises(ValueError, match="held by a flag"):
        lab_profile.check_launch(Lab(lab.root), "experiment", "h")
    K.watch.ack(lab.root, f["id"])
    lab_profile.check_launch(Lab(lab.root), "experiment", "h")


def test_frozen_watch_applies_to_controlled_projects_even_if_control_is_deleted(lab):
    pdir = lab.root / "existing"
    pdir.mkdir()
    lab.add_registry_row("attached", state="active", project=str(pdir))
    m = {"run_id": "r-control", "subject": "attached"}
    snap = K.watch.snapshot([pdir], lab.root)
    dg = K.watch.digest(lab.root, m, snap, [], pdir)
    assert "frozen-broken" not in {f["rule"] for f in dg["flags"]}
    control = pdir / "control.yaml"
    control.write_text("eval_frozen: false\n", encoding="utf-8")
    dg = K.watch.digest(lab.root, m, snap, [], pdir)
    assert any(f["rule"] == "frozen-broken" and f["hold"] for f in dg["flags"])
    snap = K.watch.snapshot([pdir], lab.root)
    control.unlink()
    dg = K.watch.digest(lab.root, m, snap, [], pdir)
    assert any(f["rule"] == "frozen-broken" and f["hold"] for f in dg["flags"])


def test_a_journal_rewritten_during_a_run_is_flagged(lab):
    lab.add_registry_row("j", state="active")
    snap = K.watch.snapshot([], lab.root)
    p = journal.path(lab.root)
    p.write_text(p.read_text(encoding="utf-8").replace('"active"', '"final"'), encoding="utf-8")
    dg = K.watch.digest(lab.root, {"run_id": "r1", "subject": "j", "started": "2026-01-01T00:00:00"}, snap, [])
    assert any(f["rule"] == "journal-rewritten" and f["level"] == "block" for f in dg["flags"])


def test_a_step_procedure_runs_only_where_the_study_stands(lab):
    sys.path.insert(0, str(REPO / "tools"))
    import lab_profile
    from executor.lab import Lab
    lab.add_registry_row("s", state="proposal")
    with pytest.raises(ValueError, match="spawn-project is the work of Project set-up; s is at Proposal"):
        lab_profile.check_launch(Lab(lab.root), "spawn-project", "s")
    lab_profile.check_launch(Lab(lab.root), "propose", "s")          # its own step's work
    lab_profile.check_launch(Lab(lab.root), "discuss", "s")          # a utility runs anywhere
    lab.add_registry_row("p", state="parked")
    with pytest.raises(ValueError, match="parked"):
        lab_profile.check_launch(Lab(lab.root), "lit-review", "p")


def test_an_agent_files_a_study_at_the_start_never_past_a_checkpoint(lab, monkeypatch):
    """Only the PI places a new study past a `before` checkpoint; an agent may still file it at a later step that
    no checkpoint guards (a quick study straight at its proposal)."""
    monkeypatch.setenv("NEWTS_RUN_ID", "hub-2")
    with pytest.raises(studies.StudyError, match="only the PI"):
        studies.new(lab.root, "late", "Late", at="active")
    assert studies.new(lab.root, "early", "Early", at="proposal")["step"] == "proposal"
    monkeypatch.delenv("NEWTS_RUN_ID")
    assert studies.new(lab.root, "placed", "Placed", at="active")["step"] == "active"


def test_a_procedure_offered_at_a_step_is_told_to_leave_the_outcome_to_its_own(lab):
    studies.new(lab.root, "h", "H", at="analysis")
    own, _ = K.brief.brief(lab.root, "analyze", study="h")
    helper, _ = K.brief.brief(lab.root, "make-figures", study="h")
    assert "When your work on this step is done" in own and "move h <outcome>" in own
    assert "alongside its own procedure, /analyze" in helper and "move h <outcome>" not in helper


def test_skills_report_outcomes_and_never_name_steps_or_checkpoints():
    """A skill is portable across workflows: it reports what happened (`newts move <study> <outcome>`) and reads
    its checkpoints from the brief. So no skill names a step or a checkpoint of the shipped definition, moves a
    study by hand, or calls the old lifecycle tools — and only the procedures that do a step's work are told, in
    their generated contract, to report an outcome."""
    import re
    sys.path.insert(0, str(REPO / "tools"))
    import lab_docs
    m = model.load(REPO)
    procs = set(m["procedures"])
    named = {s for s in m["steps"] if s not in procs} | {c["id"] for w in m["workflows"] for c in w["checkpoints"]}
    old = re.compile(r"guard\.py\s+(state|spawn|finalization|approved)\b|METHOD\.md|tools/workflow\.py|approvals\.jsonl|"
                     r"state\s*(→|->)|stages\.yaml|update (the )?(lab/)?REGISTRY|registry row|next-table|replaceable:", re.I)
    generated = re.compile(r"<!-- newts:[\w-]+.*?<!-- /newts:[\w-]+ -->", re.S)
    bad = []
    for f in sorted((REPO / ".claude" / "skills").glob("*/SKILL.md")):
        text = f.read_text(encoding="utf-8")
        body = generated.sub("", text)
        bad += [f"{f.parent.name}: {x.group(0)}" for x in old.finditer(body)]
        bad += [f"{f.parent.name}: `{x}`" for x in re.findall(r"`([a-z][a-z0-9-]*)`", body) if x in named]
        told = "Finish by reporting one outcome" in text
        if told != lab_docs.does_a_step(f.parent.name, m["procedures"][f.parent.name], REPO):
            bad.append(f"{f.parent.name}: its contract {'tells' if told else 'does not tell'} it to report an outcome")
    assert not bad, bad
    assert not list((REPO / ".claude" / "skills").glob("*/METHOD.md"))


def test_a_removed_or_moved_checkpoint_no_longer_holds_its_waiting_studies(lab):
    """Publishing a definition without the checkpoint a study waits at decides that study again (studies.reconcile):
    it moves on, or waits where the definition now says — never approved for it, and no stale wait left behind."""
    studies.new(lab.root, "alpha", "Alpha")
    for _ in range(3):
        _done(lab, "alpha")
    assert _done(lab, "alpha")["waiting"] == "approve-proposal"
    assert studies.reconcile(lab.root) == []                               # nothing changed: it still waits
    _edit_workflow(lab, "research", lambda d: d.update(checkpoints=[c for c in d["checkpoints"] if c["id"] != "approve-proposal"]))
    out = studies.reconcile(lab.root)
    assert out[0]["study"] == "alpha" and out[0]["result"]["moved"] and out[0]["result"]["step"] == "setup"
    s = studies.study(lab.root, "alpha")
    assert s["step"] == "setup" and not s["waiting"] and not journal.approved(lab.root, "alpha", "approve-proposal")
    assert "waits for you" not in studies.next_for(lab.root, "alpha")["label"]


def test_a_waiting_study_names_its_own_workflows_checkpoint(lab):
    studies.new(lab.root, "beta", "Beta")
    for _ in range(4):
        _done(lab, "beta")
    row = next(r for r in studies.rows(lab.root) if r["id"] == "beta")
    assert row["next"] == "waits for you: Approve the proposal"


def _at_proposal_waiting(lab, slug):
    studies.new(lab.root, slug, slug.capitalize())
    for _ in range(3):
        _done(lab, slug)
    assert _done(lab, slug)["waiting"] == "approve-proposal"


def test_an_approval_stands_only_under_the_terms_it_was_given(lab):
    """Approving records the checkpoint's terms (where it stands, what it covers, what it checks): change them and
    the approval reads `outdated` — a study that hasn't passed it waits for the PI again. Wording doesn't count."""
    studies.new(lab.root, "gamma", "Gamma")
    checkpoints.decide(lab.root, "gamma", "approve-full-runs", via="cli")       # approved ahead of time
    assert studies.approved(lab.root, "gamma", "approve-full-runs")
    rec = journal.latest(lab.root, "gamma", "approve-full-runs")
    assert rec["terms"] == model.terms(model.checkpoint("approve-full-runs", "research", lab.root))

    def retitle(d):
        c = next(c for c in d["checkpoints"] if c["id"] == "approve-full-runs")
        c["title"], c["tell"] = "Approve the full-scale runs", "Ask first."
    _edit_workflow(lab, "research", retitle)
    assert studies.approved(lab.root, "gamma", "approve-full-runs")              # wording: still stands

    def widen(d):
        next(c for c in d["checkpoints"] if c["id"] == "approve-full-runs")["means"] = "the runs AND a new budget"
    _edit_workflow(lab, "research", widen)
    assert not studies.approved(lab.root, "gamma", "approve-full-runs")
    assert studies.decisions(lab.root, "gamma")["approve-full-runs"]["decision"] == "outdated"
    assert "changed since the PI approved it" in K.brief.checkpoint_block(lab.root, "gamma")
    checkpoints.decide(lab.root, "gamma", "approve-full-runs", via="cli")       # approved again, as it is now
    assert studies.approved(lab.root, "gamma", "approve-full-runs")


def test_a_campaigns_approval_lapses_when_the_checkpoint_becomes_the_pis_alone(lab):
    _at_proposal_waiting(lab, "delta")
    checkpoints.decide(lab.root, "delta", "approve-proposal", by="campaign:spring", via="keeper")
    assert studies.study(lab.root, "delta")["step"] == "setup"
    _edit_workflow(lab, "research", lambda d: next(c for c in d["checkpoints"] if c["id"] == "approve-proposal")
                   .update(approver="me"))
    assert studies.decisions(lab.root, "delta")["approve-proposal"]["decision"] == "outdated"
    studies.move_to(lab.root, "delta", "proposal")                               # the PI sends it back
    assert _done(lab, "delta")["waiting"] == "approve-proposal"                  # and it asks the PI now


def test_review_says_which_studies_a_change_affects(lab, tmp_path):
    """Before publishing, the PI sees what a change does to the studies: a wait it ends, an approval it outdates."""
    diff = K.diff
    _at_proposal_waiting(lab, "eps")
    studies.new(lab.root, "zeta", "Zeta")
    checkpoints.decide(lab.root, "zeta", "approve-full-runs", via="cli")
    after = tmp_path / "after"
    diff.copy(lab.root, after)
    assert diff.affected(lab.root, after) == []

    def change(d):
        d["checkpoints"] = [c for c in d["checkpoints"] if c["id"] != "approve-proposal"]
        next(c for c in d["checkpoints"] if c["id"] == "approve-full-runs")["checks"] = ["trial-runs-met-criteria"]
    _edit_workflow(type("H", (), {"root": after}), "research", change)
    said = diff.affected(lab.root, after)
    assert any(x.startswith("Eps stops waiting at approve-proposal: it moves on to setup") for x in said), said
    assert any("Zeta: your approval of “Approve full runs” no longer stands" in x for x in said), said
    assert studies.study(lab.root, "eps")["waiting"]                             # read-only: nothing moved yet
