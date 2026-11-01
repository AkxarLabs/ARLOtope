"""The spec-conformance audit (checks/audit_spec_conformance.py): the runs behind a claim used the frozen
data, split, metric and benchmark, and any subsampling, synthetic data or change is disclosed.
Exit convention: 0 clean · 2 needs human review · 1 violation."""

from __future__ import annotations

import pytest
import yaml as _yaml

from conftest import load

PLAN_DATA = {"source": "s3://corpus", "version": "2026-01", "sha256": "abc", "split_seed": 7}
PLAN_EVAL = {"primary_metric": "val_bpb", "benchmark": "wikitext"}


def _setup(hub, monkeypatch, *, run_config="same", claim=None, tex="", plan_data=PLAN_DATA, plan_eval=PLAN_EVAL):
    m = load("audit_spec_conformance")
    monkeypatch.setattr(m, "HUB", hub.root)
    proj = hub.make_project("demo")
    control = _yaml.safe_load((proj / "control.yaml").read_text(encoding="utf-8"))
    (proj / "control.yaml").write_text(_yaml.safe_dump({**control, "data": plan_data}), encoding="utf-8")
    (proj / "configs").mkdir()
    (proj / "configs" / "base.yaml").write_text(_yaml.safe_dump({"eval": plan_eval}), encoding="utf-8")
    hub.add_registry_row("demo", state="writing", project=str(proj))
    if run_config == "same":
        run_config = {"data": plan_data, "eval": plan_eval}
    if run_config is not None:
        (proj / "runs" / "r1").mkdir(parents=True)
        (proj / "runs" / "r1" / "config.resolved.yaml").write_text(_yaml.safe_dump(run_config), encoding="utf-8")
    paper = hub.root / "studies" / "demo" / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    claims = [{"id": "C1", "headline": True, "metric": "val_bpb", "artifacts": ["runs/r1/metrics.json"], **(claim or {})}]
    (paper / "claims.yaml").write_text(_yaml.safe_dump({"claims": claims}), encoding="utf-8")
    (paper / "main.tex").write_text(tex, encoding="utf-8")
    return m, paper


def _config(data=None, eval=None, **extra):
    return {"data": {**PLAN_DATA, **(data or {})}, "eval": {**PLAN_EVAL, **(eval or {})}, **extra}


def test_matching_runs_pass(hub, monkeypatch):
    m, paper = _setup(hub, monkeypatch)
    assert m.audit(paper) == 0


@pytest.mark.parametrize("change", [{"data": {"sha256": "other"}}, {"data": {"split_seed": 8}},
                                    {"eval": {"primary_metric": "acc"}}, {"eval": {"benchmark": "ptb"}}])
def test_undisclosed_change_fails(hub, monkeypatch, change):
    m, paper = _setup(hub, monkeypatch, run_config=_config(**change))
    assert m.audit(paper) == 1


def test_declared_deviation_is_manual(hub, monkeypatch):
    m, paper = _setup(hub, monkeypatch, run_config=_config(data={"version": "2026-03"}),
                      claim={"deviation": "newer snapshot, see Sec 3"})
    assert m.audit(paper) == 2


def test_headline_metric_other_than_planned_fails(hub, monkeypatch):
    m, paper = _setup(hub, monkeypatch, claim={"metric": "acc"})
    assert m.audit(paper) == 1


@pytest.mark.parametrize("extra", [{"synthetic": True}, {"subsample": 0.1}, {"train": {"max_samples": 500}}])
def test_undisclosed_subsampling_or_synthetic_data_fails(hub, monkeypatch, extra):
    m, paper = _setup(hub, monkeypatch, run_config=_config(**extra))
    assert m.audit(paper) == 1


def test_substitution_the_paper_owns_up_to_is_manual(hub, monkeypatch):
    m, paper = _setup(hub, monkeypatch, run_config=_config(subsample=0.1),
                      tex="We train on a 10% subsample of the corpus.")
    assert m.audit(paper) == 2


def test_full_data_flags_are_not_substitution(hub, monkeypatch):
    m, paper = _setup(hub, monkeypatch, run_config=_config(subsample=1.0, synthetic=False))
    assert m.audit(paper) == 0


def test_substitution_the_plan_declares_is_not_a_deviation(hub, monkeypatch):
    plan = {**PLAN_DATA, "source": "synthetic generator v2"}
    m, paper = _setup(hub, monkeypatch, plan_data=plan)
    assert m.audit(paper) == 0


def test_underspecified_plan_is_manual(hub, monkeypatch):
    m, paper = _setup(hub, monkeypatch, plan_data={}, plan_eval={}, run_config=_config())
    assert m.audit(paper) == 2


def test_run_without_resolved_config_is_manual(hub, monkeypatch):
    m, paper = _setup(hub, monkeypatch, run_config=None)
    assert m.audit(paper) == 2
