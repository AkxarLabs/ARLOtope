"""Compose (dashboard/compose.py): the lab's definition edited as a draft — steps, routes, workflows, checkpoints,
procedures, rooms, rules, files, copies, deletes — checked, then published as one change (and undone). The lab
and its runs never see a half-made edit; a designer's draft is laid over it, checked the same way, and said in
plain lines with every loosened checkpoint first."""

from __future__ import annotations

import json
import shutil

import pytest
import yaml

from conftest import REPO, kernel, load

K = kernel()


@pytest.fixture
def m(hub, monkeypatch, tmp_path):
    for rel in ("workflow", ".claude/skills", "agent-roles", "checks", "templates/project-types"):
        shutil.copytree(REPO / rel, hub.root / rel, dirs_exist_ok=True)
    (hub.root / "tools").mkdir(exist_ok=True)
    shutil.copy(REPO / "tools" / "role_sync.py", hub.root / "tools")
    shutil.copy(REPO / "tools" / "labfiles.py", hub.root / "tools")
    monkeypatch.setenv("NEWTS_HOME", str(tmp_path / "home"))
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    mod = load("dashboard/serve")
    monkeypatch.setattr(mod.ctx, "HUB", hub.root)
    monkeypatch.setattr(mod.ctx, "LAB", hub.lab)
    return mod


def _op(m, **body):
    out, code = m.compose.op(body)
    assert code == 200, out
    return out


def _draft(m):
    return K.model.load(m.compose._draft())


def _wf(m, wid):
    return next(w for w in _draft(m)["workflows"] if w["id"] == wid)


def test_extension_additions_stay_in_a_reviewable_draft(m, hub):
    extension = hub.root / 'extensions/review-study'
    files = extension / 'workflow/workflows'
    files.mkdir(parents=True)
    (extension / 'extension.yaml').write_text('title: Review study\nblurb: A reusable workflow\n', encoding='utf-8')
    definition = yaml.safe_load((hub.root / 'workflow/workflows/quick.yaml').read_text(encoding='utf-8'))
    definition.update(id='review-study', title='Review study', default=False)
    (files / 'review-study.yaml').write_text(yaml.safe_dump(definition), encoding='utf-8')
    view, code = m.compose.view()
    assert code == 200 and any(e['name'] == 'review-study' and not e['added'] for e in view['extensions'])
    assert 'prereg' in view['audits'] and isinstance(view['watch'], list)
    _op(m, op='extension-use', name='review-study')
    view, code = m.compose.view()
    assert code == 200 and not view['draft']['problems']
    assert _wf(m, 'review-study')['title'] == 'Review study'
    assert not (hub.root / 'workflow/workflows/review-study.yaml').exists()
    out, code = m.compose.op({'op': 'publish', 'note': 'Install reviewed workflow'})
    assert code == 200, out
    assert K.model.workflow('review-study', hub.root)['title'] == 'Review study'


def test_edits_go_to_a_draft_until_published_and_can_be_undone(m, hub):
    before = (hub.root / ".claude/skills/scope/SKILL.md").read_text(encoding="utf-8")
    assert not m.compose.view()[0]["draft"]["active"]
    _op(m, op="procedure", name="scope", fields={"title": "Scope it", "does": "Weighs the options.",
                                                 "outcomes": ["done", "not-worth-it"]})
    _op(m, op="step", id="proposal", fields={"also": ["scope"]})
    v = m.compose.view()[0]
    assert v["draft"]["active"] and v["procedures"]["scope"]["title"] == "Scope it"
    assert {c["path"] for c in v["draft"]["changes"]} == {".claude/skills/scope/SKILL.md", "workflow/steps.yaml"}
    assert v["draft"]["problems"] == []
    assert (hub.root / ".claude/skills/scope/SKILL.md").read_text(encoding="utf-8") == before   # the lab: untouched
    out, code = m.compose.op({"op": "publish", "note": "rename scope"})
    assert code == 200, out
    skill = (hub.root / ".claude/skills/scope/SKILL.md").read_text(encoding="utf-8")
    assert "title: Scope it" in skill and "<!-- newts:contract" in skill and "`not-worth-it`" in skill
    assert "scope" in K.model.step("proposal", hub.root)["also"]
    v = m.compose.view()[0]
    assert not v["draft"]["active"] and v["history"][0]["note"] == "rename scope"
    out, code = m.compose.op({"op": "undo", "id": v["history"][0]["id"]})
    assert code == 200, out
    assert (hub.root / ".claude/skills/scope/SKILL.md").read_text(encoding="utf-8") == before
    assert "compose.publish" in (hub.lab / ".bus" / "pi-actions.jsonl").read_text(encoding="utf-8")


def test_steps_are_added_routed_and_removed_without_yaml(m, hub):
    _op(m, op="step", id="replication", new=True, after="analysis", **{"in": "research"},
        fields={"label": "Replication", "do": "experiment", "room": "lab"})
    path = _wf(m, "research")["path"]
    assert path[path.index("analysis") + 1] == "replication"
    _op(m, op="route", workflow="research", step="replication", outcome="failed-to-replicate", to="active")
    assert _wf(m, "research")["routes"]["replication"] == {"failed-to-replicate": "active"}
    assert m.compose.op({"op": "route", "workflow": "research", "step": "replication", "outcome": "done", "to": "final"})[1] == 400
    assert m.compose.op({"op": "route", "workflow": "research", "step": "replication", "outcome": "x", "to": "nowhere"})[1] == 400
    assert m.compose.problems() == []
    said = m.compose.view()[0]["draft"]["summary"]
    assert any("adds the step Replication" in x for x in said)
    _op(m, op="route", workflow="research", step="replication", outcome="failed-to-replicate", to=None)
    _op(m, op="delete", kind="step", name="replication")
    assert "replication" not in _draft(m)["steps"] and "replication" not in _wf(m, "research")["path"]
    assert m.compose.problems() == []
    text = (m.compose._draft() / "workflow" / "steps.yaml").read_text(encoding="utf-8")
    assert text.startswith("# The places a study can be")                         # the header is the file's own


def test_workflows_and_checkpoints_are_composed_without_yaml(m, hub):
    """A workflow is copied (its checkpoints get ids of their own — approvals are per id), a checkpoint is added,
    moved and removed, a workflow made default and removed; the view shows the audits checkpoints may run."""
    v = m.compose.view()[0]
    assert v['workflows'][0]['id'] == 'research'
    assert {w['id'] for w in v['workflows']} == {'research', 'quick', 'target', 'sakana'} and 'prereg' in v['audits']
    _op(m, op="workflow", id="lean", new=True, like="research", fields={"title": "Lean paper"})
    assert [c["id"] for c in _wf(m, "lean")["checkpoints"]] == ["approve-proposal-lean", "approve-full-runs-lean",
                                                                "approve-loop-lean", "finalize-paper-lean"]
    assert m.compose.problems() == []
    _op(m, op="checkpoint", workflow="lean", id="approve-full-runs-lean", remove=True)
    _op(m, op="checkpoint", workflow="lean", id="look-at-analysis", new=True,
        fields={"title": "Look at the analysis", "before": "writing", "approver": "me"})
    _op(m, op="checkpoint", workflow="lean", id="look-at-analysis", fields={"during": "analysis", "at": "the first figure"})
    cp = next(c for c in _wf(m, "lean")["checkpoints"] if c["id"] == "look-at-analysis")
    assert cp["during"] == "analysis" and "before" not in cp                   # setting one placement clears the other
    assert m.compose.problems() == []
    assert m.compose.op({"op": "checkpoint", "workflow": "lean", "id": "approve-proposal", "new": True})[1] == 400  # ids are unique
    _op(m, op="workflow", id="lean", fields={"path": ["seed", "proposal", "setup", "active", "analysis", "final"],
                                             "use": {"triage": "discuss"}})
    lean = _wf(m, "lean")
    assert lean["use"] == {"triage": "discuss"} and all((c.get("before") or c.get("during")) in lean["path"]
                                                         for c in lean["checkpoints"])
    _op(m, op="workflow", id="quick", default=True)
    assert _draft(m)["workflows"][0]["id"] == "quick"
    _op(m, op="workflow-delete", id="lean")
    assert "lean" not in [w["id"] for w in _draft(m)["workflows"]]
    assert m.compose.op({"op": "workflow-delete", "id": "nope"})[1] == 400


def test_the_last_workflow_stays_and_a_study_is_never_stranded(m, hub):
    for wid in [w['id'] for w in m.compose.view()[0]['workflows'] if w['id'] != 'research']:
        _op(m, op="workflow-delete", id=wid)
    assert m.compose.op({"op": "workflow-delete", "id": "research"})[1] == 400
    _op(m, op="discard")
    hub.add_registry_row("s1", state="writing")
    _op(m, op="step", id="writing", remove=True)
    assert any("Studies stand at `writing`" in p for p in m.compose.problems())
    assert m.compose.op({"op": "publish"})[1] == 409


def test_copy_then_delete_a_procedure_and_discard(m, hub):
    _op(m, op="copy", kind="procedure", like="lit-review", name="quick-scan", title="A quick scan", step="lit-review")
    p = m.compose.view()[0]["procedures"]["quick-scan"]
    assert p["like"] == "lit-review" and p["title"] == "A quick scan" and "lit-review" in p["steps"]
    assert "quick-scan" in m.compose.view()[0]["procedures"]["lit-review"]["variants"]
    _op(m, op="instructions", kind="add", name="quick-scan", text="Skim the ten most-cited papers.")
    assert (m.compose._draft() / "lab/workflow/quick-scan.add.md").is_file()
    _op(m, op="delete", kind="procedure", name="quick-scan")
    v = m.compose.view()[0]
    assert "quick-scan" not in v["procedures"] and v["draft"]["problems"] == []
    assert m.compose.op({"op": "delete", "kind": "procedure", "name": "lit-review"})[1] == 400   # a step's own work
    _op(m, op="discard")
    assert not m.compose.active() and not (hub.root / ".claude/skills/quick-scan").exists()


def test_the_locks_and_the_problems_block_a_publish(m, hub):
    text = (hub.root / "workflow/workflows/research.yaml").read_text(encoding="utf-8").replace("before: setup", "before: nowhere", 1)
    _op(m, op="write", path="workflow/workflows/research.yaml", text=text)
    probs = m.compose.view()[0]["draft"]["problems"]
    assert any("approve-proposal" in p and "not a step of research" in p for p in probs), probs
    assert m.compose.op({"op": "publish"})[1] == 409
    _op(m, op="discard")
    rules = (hub.root / "workflow/rules.yaml").read_text(encoding="utf-8").replace("  - '^templates/'\n", "", 1)
    _op(m, op="write", path="workflow/rules.yaml", text=rules)
    assert any("protected_paths" in p for p in m.compose.problems())     # a safety table: locked
    _op(m, op="discard")
    _op(m, op="rule", id="seeds", remove=True)
    assert any("cited by number" in p for p in m.compose.problems())


def test_a_lab_change_after_the_draft_began_is_a_conflict(m, hub):
    _op(m, op="role", name="overseer", fields={"label": "The overseer"})
    (hub.root / "agent-roles" / "overseer.yaml").write_text("name: overseer\nlabel: Changed meanwhile\n", encoding="utf-8")
    out, code = m.compose.op({"op": "publish"})
    assert code == 409 and out["conflicts"] == ["agent-roles/overseer.yaml"]


def test_rooms_without_yaml(m, hub):
    _op(m, op="copy", kind="room", like="lab", name="replication", plain=True, steps=["analysis"])
    rooms = {r["id"]: r for r in K.model.rooms(m.compose._draft())}
    assert rooms["replication"]["steps"] == ["analysis"] and "analysis" not in rooms["bench"]["steps"]
    _op(m, op="room", id="replication", fields={"title": "The Replication Bench"})
    assert next(r for r in _draft(m)["rooms"] if r["id"] == "replication")["title"] == "The Replication Bench"
    assert 'per_project' not in K.define.dump_rooms([{'id': 'old', 'per_project': True}])
    assert m.compose.problems() == []
    assert m.compose.op({"op": "delete", "kind": "room", "name": "replication"})[1] == 400   # say where its steps go
    _op(m, op="delete", kind="room", name="replication", move_to="bench")
    assert K.model.step("analysis", m.compose._draft())["room"] == "bench" and m.compose.problems() == []


def test_rules_and_files(m, hub):
    _op(m, op="copy", kind="rule", name="no-tabs", text="**No tabs.** Indent with spaces.", list="project")
    _op(m, op="rule", id="no-tabs", text="**No tabs.** Indent with four spaces.", checks=[])
    rl = yaml.safe_load((m.compose._draft() / "workflow/rules.yaml").read_text(encoding="utf-8"))
    assert rl["project_rules"][-1] == {"id": "no-tabs", "text": "**No tabs.** Indent with four spaces."}
    _op(m, op="rule", id="no-tabs", remove=True)
    _op(m, op="rule", id="seeds", text="**Seeds.** Three of them.")
    assert m.compose.problems() == []
    for bad in ("../lab/config.yaml", "tools/guard.py", "workflow/../tools/x.md", "checks/x.exe"):
        assert m.compose.op({"op": "write", "path": bad, "text": "x"})[1] == 400, bad
    f, code = m.compose.file_get({"path": "agent-roles/overseer.md"})
    assert code == 200 and f["text"] == f["published"]


def _design(hub, did, wf_edit=None, steps_edit=None, variant=None):
    d = hub.lab / ".bus" / "designs" / "workflow" / did
    (d / "workflow" / "workflows").mkdir(parents=True)
    if wf_edit:
        wf = yaml.safe_load((hub.root / "workflow/workflows/research.yaml").read_text(encoding="utf-8"))
        wf_edit(wf)
        (d / "workflow" / "workflows" / "research.yaml").write_text(yaml.safe_dump(wf, sort_keys=False), encoding="utf-8")
    if steps_edit:
        st = yaml.safe_load((hub.root / "workflow/steps.yaml").read_text(encoding="utf-8"))
        steps_edit(st)
        (d / "workflow" / "steps.yaml").write_text(yaml.safe_dump(st, sort_keys=False), encoding="utf-8")
    if variant:
        (d / ".claude" / "skills" / variant).mkdir(parents=True)
        (d / ".claude" / "skills" / variant / "SKILL.md").write_text(
            f"---\nname: {variant}\ndescription: A variant.\nnewts:\n  like: lit-review\n---\n# {variant}\n", encoding="utf-8")
    (d / "request.md").write_text("make it leaner", encoding="utf-8")
    (d / "notes.md").write_text("drops a checkpoint", encoding="utf-8")
    return d


def test_a_designed_change_is_checked_said_and_taken_into_the_draft(m, hub):
    def leaner(wf):
        wf["checkpoints"] = [c for c in wf["checkpoints"] if c["id"] != "approve-full-runs"]
        wf["use"] = {"lit-review": "lit-review-lite"}
    _design(hub, "20261010-120000", wf_edit=leaner, variant="lit-review-lite")
    _design(hub, "20261010-130000", wf_edit=lambda wf: wf["path"].append("nowhere"))
    designs = {x["id"]: x for x in m.compose.view()[0]["workflow_designs"]}
    good, bad = designs["20261010-120000"], designs["20261010-130000"]
    assert good["problems"] == [] and bad["problems"] and good["request"] == "make it leaner"
    assert good["changes"][0] == "Research paper: removes the checkpoint “Approve full runs”"   # loosening first
    assert any("adds the procedure /lit-review-lite" in x for x in good["changes"])
    assert m.compose.op({"op": "workflow-design-use", "id": "20261010-130000"})[1] == 400
    _op(m, op="workflow-design-use", id="20261010-120000")
    assert _wf(m, "research")["use"] == {"lit-review": "lit-review-lite"} and "lit-review-lite" in _draft(m)["procedures"]
    assert m.compose.problems() == []
    assert K.model.workflow("research", hub.root)["use"] == {}                # only the draft






def test_a_project_type_can_start_blank(m, hub):
    _op(m, op="copy", kind="type", like="", name="field-notes", title="Fieldwork and interviews.")
    card = m.compose._draft() / "lab/templates/project-types/field-notes/TYPE.md"
    assert card.is_file() and "`field-notes`" in card.read_text(encoding="utf-8")
    assert not (hub.root / "lab/templates/project-types/field-notes").exists()   # the lab: untouched
    out, code = m.compose.op({"op": "copy", "kind": "type", "like": "", "name": "field-notes"})
    assert code != 200 and "already" in out["error"]


def test_checks_and_types_read_as_plain_text(m, hub):
    v = m.compose.view()[0]
    for c in v["checks"]:
        assert c["doc"] and "`" not in c["doc"] and "uv run" not in c["doc"] and not c["doc"].startswith("guard.py")
        assert all("uv run" in u for u in c["usage"])
    for t in v["types"]:
        assert "`" not in t["title"] and "#" not in t["title"] and t["description"] and "`" not in t["description"]


def test_single_agent_preset_and_saved_procedure_export(m, hub):
    import base64
    import io
    import zipfile
    _op(m, op='workflow', id='one-lead', new=True, preset='single-agent', fields={'title':'One lead'})
    view=m.compose.view()[0]
    w=next(w for w in view['workflows'] if w['id']=='one-lead')
    assert len(w['path'])==1 and w['nodes'][w['path'][0]]['context']=={'mode':'fresh'}
    assert not w['checkpoints']
    exported,code=m.compose.export_procedure({'workflow':'one-lead'})
    assert code==200 and exported['requires_lab']
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as z:
        assert 'SKILL.md' in z.namelist() and 'workflow.json' in z.namelist()
    assert not (hub.root/'workflow/workflows/one-lead.yaml').exists()
