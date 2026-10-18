"""Proof by scenario: what a lab can make of the kernel without touching its code.

    1  a step of its own        a replication step between analysis and writing, with its own skill — on the
                                map, in the brief, `newts next`, the launcher; done at analysis can't skip it
    2  a lab with no papers     its own steps, skills and checks, and none of the research ones
    3  a renamed step           the studies standing there move with it; the journal says so
    4  a variant, where wanted  a quick literature pass in one workflow, and for one study only
    5  a check with parameters  `budget-under: {usd: 50}` — approving itself under budget, flagging work past it
    6  reads and outputs        a step works from a file an earlier step produces; check() catches the gap
                                when the producing step goes
"""

from __future__ import annotations

import json
import shutil
import types

import pytest
import yaml

from conftest import REPO, kernel, load

K = kernel()
model, studies, checkpoints, journal, define = K.model, K.studies, K.checkpoints, K.journal, K.define


@pytest.fixture(autouse=True)
def _not_in_a_run(monkeypatch):
    monkeypatch.delenv("NEWTS_RUN_ID", raising=False)


@pytest.fixture
def lab(hub):
    """A hub with its own copy of this repo's definition and skills."""
    shutil.copytree(REPO / "workflow", hub.root / "workflow")
    shutil.copytree(REPO / ".claude" / "skills", hub.root / ".claude" / "skills")
    shutil.copytree(REPO / "agent-roles", hub.root / "agent-roles")
    return hub


def _skill(root, name, **newts):
    """A minimal skill: a folder with a SKILL.md whose `newts:` block is its definition."""
    d = root / ".claude" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    block = yaml.safe_dump({"kind": "stage", "args": "slug", **newts}, sort_keys=False)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name}\nnewts:\n"
                                + "".join(f"  {ln}\n" for ln in block.splitlines()) + f"---\n\n# {name}\n\nDo the work.\n",
                                encoding="utf-8")


def _launch(root, skill, slug):
    profile = load("lab_profile")
    profile.check_launch(types.SimpleNamespace(hub=root), skill, slug)


def _problems(root):
    return model.check(root, K.rules.check_names(root)) + K.rules.check(root)


# ── 1 ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_step_of_its_own_between_analysis_and_writing(lab):
    new = load("new")
    new.new_skill(lab.root, "replicate", "experiment", title="Replicate the headline result")
    new.new_step(lab.root, "replication", "analysis", do="replicate", label="Replication", workflow="research",
                 after="analysis")
    assert _problems(lab.root) == []
    w = model.workflow("research", lab.root)
    assert w["path"][w["path"].index("analysis") + 1] == "replication"
    view = model.view(lab.root)                                            # the map, the board and the world
    assert any(s["id"] == "replication" and s["do"] == "replicate" for s in view["steps"])
    assert any("replication" in r["steps"] for r in view["rooms"])

    studies.new(lab.root, "r1", "R1", at="analysis")
    assert studies.move(lab.root, "r1", "done")["step"] == "replication"     # done can't skip it
    assert studies.next_for(lab.root, "r1")["procedure"] == "replicate"
    text, _ = K.brief.brief(lab.root, "replicate", study="r1")
    assert "**Replication**" in text and "`done` → Writing" in text
    with pytest.raises(ValueError, match="where the study stands|stands at|is at"):
        _launch(lab.root, "write-paper", "r1")                              # the next step's work waits
    _launch(lab.root, "replicate", "r1")


# ── 2 ────────────────────────────────────────────────────────────────────────────────────────────
def _product_lab(root):
    """A lab that builds software: its own steps, skills, a check — and no research skills at all."""
    (root / "workflow" / "workflows").mkdir(parents=True)
    (root / "workflow" / "steps.yaml").write_text(
        "spec:  {label: Spec, do: write-spec}\nbuild: {label: Build, do: build}\n"
        "evaluate: {label: Evaluate, do: evaluate}\nshipped: {label: Shipped}\n"
        "parked: {label: Parked}\nkilled: {label: Killed}\n", encoding="utf-8")
    (root / "workflow" / "workflows" / "product.yaml").write_text(yaml.safe_dump({
        "title": "Product build", "default": True, "path": ["spec", "build", "evaluate", "shipped"],
        "routes": {"evaluate": {"regressed": "build"}},
        "checkpoints": [{"id": "ship-it", "title": "Ship it", "before": "shipped", "approver": "auto",
                         "checks": ["tests-green"]}]}, sort_keys=False), encoding="utf-8")
    (root / "workflow" / "rooms.yaml").write_text("[]\n", encoding="utf-8")
    for name in ("write-spec", "build"):
        _skill(root, name)
    _skill(root, "evaluate", outcomes={"regressed": "a metric got worse than the last release"})
    (root / "checks").mkdir(exist_ok=True)
    (root / "checks" / "tests_green.py").write_text(
        'NAME = "tests-green"\n\n\ndef add_args(p):\n    p.add_argument("slug")\n\n\n'
        'def run(a, g):\n    import os, pathlib\n'
        '    ok = (pathlib.Path(os.environ["NEWTS_HUB"]) / "studies" / a.slug / "GREEN").exists()\n'
        '    return g._verdict(0 if ok else 1, "tests green" if ok else "tests red")\n', encoding="utf-8")


def test_a_lab_with_no_papers_runs_on_the_same_kernel(hub):
    _product_lab(hub.root)
    assert _problems(hub.root) == []
    assert set(model.load(hub.root)["procedures"]) == {"write-spec", "build", "evaluate"}
    studies.new(hub.root, "app", "The app")
    assert studies.move(hub.root, "app", "done")["step"] == "build"
    assert studies.move(hub.root, "app", "done")["step"] == "evaluate"
    assert studies.move(hub.root, "app", "regressed")["step"] == "build"       # its own route
    studies.move(hub.root, "app", "done")
    res = studies.move(hub.root, "app", "done")                                # tests red: the auto checkpoint waits
    assert res.get("waiting") == "ship-it"
    (hub.root / "studies" / "app").mkdir(parents=True, exist_ok=True)
    (hub.root / "studies" / "app" / "GREEN").write_text("", encoding="utf-8")
    res = studies.move(hub.root, "app", "done")                                # reported again: green, it approves itself
    assert res["step"] == "shipped" and res["finished"]                       # an end with no work: it finishes there
    assert journal.latest(hub.root, "app", "ship-it")["by"] == "auto" and studies.study(hub.root, "app")["finished"]


# ── 3 ────────────────────────────────────────────────────────────────────────────────────────────
def test_renaming_a_step_carries_its_studies_checkpoints_and_instructions(lab):
    studies.new(lab.root, "s", "S", at="active")
    K.instructions.write("step", "active", "Log GPU memory.", lab.root)
    studies.rename_step(lab.root, "active", "running")
    assert _problems(lab.root) == []
    assert studies.study(lab.root, "s")["step"] == "running"
    research = model.workflow("research", lab.root)
    assert "running" in research["path"] and "active" not in research["path"]
    assert model.checkpoint("approve-full-runs", "research", lab.root)["during"] == "running"
    assert research["routes"]["analysis"]["more-experiments"] == "running"
    assert K.instructions.read("step", "running", lab.root) == "Log GPU memory."
    assert any(e["kind"] == "remap" and e["map"] == {"active": "running"} for e in journal.events(lab.root))
    with pytest.raises(ValueError):
        studies.rename_step(lab.root, "running", "analysis")                    # an id already taken


def test_renaming_a_step_is_the_pis(lab, monkeypatch):
    monkeypatch.setenv("NEWTS_RUN_ID", "r-1")
    with pytest.raises(studies.StudyError, match="the PI's"):
        studies.rename_step(lab.root, "active", "running")


# ── 4 ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_variant_in_one_workflow_and_for_one_study(lab):
    load("new").new_skill(lab.root, "lit-review-quick", "lit-review", title="A quick scan")
    studies.new(lab.root, "a", "A", at="lit-review")
    studies.new(lab.root, "b", "B", at="lit-review")
    studies.set_use(lab.root, "b", {"lit-review": "lit-review-quick"})
    assert studies.next_for(lab.root, "a")["procedure"] == "lit-review"
    assert studies.next_for(lab.root, "b")["procedure"] == "lit-review-quick"
    _launch(lab.root, "lit-review-quick", "b")
    p = model.procedure("lit-review-quick", lab.root)
    assert p["outcomes"] == model.procedure("lit-review", lab.root)["outcomes"]   # it inherits what it reports
    text, _ = K.brief.brief(lab.root, "lit-review-quick", study="b")
    assert "When your work on this step is done" in text                       # it is the step's work, for b


# ── 5 ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_check_with_parameters_and_a_watch_of_its_own(lab):
    (lab.root / "checks").mkdir(exist_ok=True)
    (lab.root / "checks" / "budget_under.py").write_text(
        'NAME = "budget-under"\n\n\ndef add_args(p):\n    p.add_argument("slug")\n    p.add_argument("--usd", type=float, required=True)\n\n\n'
        'def run(a, g):\n    import json, os, pathlib\n'
        '    f = pathlib.Path(os.environ["NEWTS_HUB"]) / "studies" / a.slug / "spend.json"\n'
        '    spent = json.loads(f.read_text())["usd"] if f.exists() else 0\n'
        '    return g._verdict(0 if spent <= a.usd else 1, f"spent {spent} of {a.usd}")\n', encoding="utf-8")
    p = lab.root / "workflow" / "workflows" / "quick.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["checkpoints"] = [{"id": "within-budget", "title": "Within budget", "before": "analysis", "approver": "auto",
                           "checks": [{"budget-under": {"usd": 50}}], "watch": [{"budget-under": {"usd": 50}}]}]
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    assert _problems(lab.root) == []
    studies.new(lab.root, "q", "Q", workflow="quick", at="active")
    (lab.root / "studies" / "q").mkdir(parents=True)
    (lab.root / "studies" / "q" / "spend.json").write_text(json.dumps({"usd": 80}), encoding="utf-8")
    assert studies.move(lab.root, "q", "done").get("waiting") == "within-budget"   # over: it waits for the PI
    ws = K.watch.checkpoint_watches(lab.root, "q", "quick")
    raised = K.watch.evaluate(lab.root, ws, {"written": [], "deleted": []}, [], 0, None, "q", "r-1")
    assert raised and "spent 80" in raised[0]["detail"]
    (lab.root / "studies" / "q" / "spend.json").write_text(json.dumps({"usd": 20}), encoding="utf-8")
    assert studies.move(lab.root, "q", "done")["step"] == "analysis"          # under budget now: it approves itself
    doc["checkpoints"][0]["checks"] = [{"budget-under": {"usd": 500}}]          # loosening it shows first in a draft
    draft = lab.root / "draft"
    shutil.copytree(lab.root / "workflow", draft / "workflow")
    (draft / "workflow" / "workflows" / "quick.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    said = K.diff.summary(lab.root, draft)
    assert said and "no longer runs budget-under (usd=50)" in said[0]


def test_a_malformed_parameterised_check_is_caught(lab):
    p = lab.root / "workflow" / "workflows" / "quick.yaml"
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    doc["checkpoints"] = [{"id": "x", "title": "X", "before": "analysis", "approver": "me",
                           "checks": [{"budget-under": 50}]}]
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    assert any("{name: {param: value}}" in x for x in _problems(lab.root))


# ── 6 ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_step_reads_what_an_earlier_step_produces(hub):
    _product_lab(hub.root)
    _skill(hub.root, "write-spec", outputs=["studies/<slug>/SPEC.md: what to build and how it is judged"])
    _skill(hub.root, "build", reads=["studies/<slug>/SPEC.md"])
    assert _problems(hub.root) == []
    studies.new(hub.root, "app", "The app", at="build")
    text, _ = K.brief.brief(hub.root, "build", study="app")
    assert "## What it works from" in text and "studies/<slug>/SPEC.md" in text
    d = define.read(hub.root)                                                 # drop the step that writes the spec
    d["workflows"][0]["path"].remove("spec")
    define.write(hub.root, d)
    assert any("/build reads studies/<slug>/SPEC.md" in x for x in _problems(hub.root))


# ── an extension ─────────────────────────────────────────────────────────────────────────────────
def test_a_research_extension_adds_a_workflow_without_changing_the_shipped_ones(lab):
    extension = lab.root / "extensions" / "replication"
    folder = extension / "workflow" / "workflows"
    folder.mkdir(parents=True)
    (extension / "extension.yaml").write_text("title: Replication\n", encoding="utf-8")
    doc = yaml.safe_load((lab.root / "workflow/workflows/quick.yaml").read_text(encoding="utf-8"))
    doc.update(title="Replication", default=False, checkpoints=[{
        "id": "review-replication", "title": "Review replication", "before": "analysis", "approver": "me"}])
    (folder / "replication.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    before = {w["id"] for w in model.workflows(lab.root)}
    x = next(e for e in K.diff.extensions(lab.root) if e["name"] == "replication")
    probs, said = K.diff.check_overlay(lab.root, x["path"], merge=True)
    assert probs == [] and any("Replication" in change for change in said)
    K.diff.lay(x["path"], lab.root, merge=True)
    assert _problems(lab.root) == []
    assert {w["id"] for w in model.workflows(lab.root)} == before | {"replication"}
    studies.new(lab.root, "replica", "Replication study", workflow="replication", at="active")
    lab.produce("replica")
    assert studies.move(lab.root, "replica", "done")["waiting"] == "review-replication"
