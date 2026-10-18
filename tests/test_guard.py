"""The lab's checks (checks/*.py, run through tools/guard.py): each returns an exit code — 0 OK · 1 BLOCKED ·
2 WARN. We call them directly with a tiny SimpleNamespace args object and assert the code. (Where a study stands
and whether a checkpoint is approved is the kernel's: tests/test_kernel.py.)
"""

from __future__ import annotations

import sys
import time
import types

from conftest import REPO, load

sys.path.insert(0, str(REPO / "tools"))


def _mod(hub, monkeypatch):
    m = load("guard")
    monkeypatch.setattr(m, "HUB", hub.root)
    monkeypatch.setattr(m, "LAB", hub.lab)
    return m


def _run(m, name, a):
    """Run one check as `tools/guard.py <name> …` would."""
    return m._load_checks()[name].run(a, m)


def test_full_run_commands_are_gone():
    """The Gate-2 envelope accounting is gone: full runs are the approve-full-runs checkpoint."""
    m = load("guard")
    assert not hasattr(m, "c_full_run") and not hasattr(m, "c_release_full_run")


# ── frozen ────────────────────────────────────────────────────────────────────

def test_frozen_ok(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo", eval_frozen=True)
    hub.add_registry_row("demo", state="active", project=str(proj))
    assert _run(m, "frozen", types.SimpleNamespace(slug="demo")) == 0


def test_frozen_blocked_when_unfrozen(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo", eval_frozen=False)
    hub.add_registry_row("demo", state="active", project=str(proj))
    assert _run(m, "frozen", types.SimpleNamespace(slug="demo")) == 1


def test_frozen_blocked_when_block_missing(hub, monkeypatch):
    import yaml
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo", control=False)
    # control.yaml with eval_frozen but no budgets/seeds
    (proj / "control.yaml").write_text(yaml.safe_dump({"eval_frozen": True}), encoding="utf-8")
    hub.add_registry_row("demo", state="active", project=str(proj))
    assert _run(m, "frozen", types.SimpleNamespace(slug="demo")) == 1


# ── append-only ───────────────────────────────────────────────────────────────

def _ledger_project(hub, slug, lines):
    proj = hub.make_project(slug)
    (proj / "EXPERIMENT_LOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    hub.add_registry_row(slug, state="active", project=str(proj))
    return proj


def test_append_only_baseline_then_append_ok(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = _ledger_project(hub, "demo", ["entry 1", "entry 2"])
    a = types.SimpleNamespace(target=str(proj))
    assert _run(m, "append-only", a) == 0  # records baseline
    (proj / "EXPERIMENT_LOG.md").write_text("entry 1\nentry 2\nentry 3\n", encoding="utf-8")
    assert _run(m, "append-only", a) == 0  # pure append -> OK


def test_append_only_rewrite_violation(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = _ledger_project(hub, "demo", ["entry 1", "entry 2"])
    a = types.SimpleNamespace(target=str(proj))
    assert _run(m, "append-only", a) == 0
    # rewrite an earlier line -> violation
    (proj / "EXPERIMENT_LOG.md").write_text("entry 1 TAMPERED\nentry 2\n", encoding="utf-8")
    assert _run(m, "append-only", a) == 1


def test_append_only_removed_line_violation(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = _ledger_project(hub, "demo", ["entry 1", "entry 2", "entry 3"])
    a = types.SimpleNamespace(target=str(proj))
    assert _run(m, "append-only", a) == 0
    (proj / "EXPERIMENT_LOG.md").write_text("entry 1\nentry 2\n", encoding="utf-8")  # shrank
    assert _run(m, "append-only", a) == 1


# ── writeback ─────────────────────────────────────────────────────────────────

def test_writeback_ok_with_dated_notebook_naming_slug(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="active", project="-")
    today = time.strftime("%Y-%m-%d")
    hub.notebook_entry(f"{today}-demo.md", "# Notebook — demo\nworked on demo today\n")
    assert _run(m, "writeback", types.SimpleNamespace(slug="demo")) == 0


def test_writeback_warn_when_nothing(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="active", project="-")
    assert _run(m, "writeback", types.SimpleNamespace(slug="demo")) == 2


# ── evolve (triggered write-back operators) ───────────────────────────────────

_NOTES_TEMPLATE = """\
# NOTES — distilled memory

## Gotchas & fixes (environment / data / infra)

<!-- One line each: the trap -> the fix, with evidence.
     e.g.  - data path stalls -> stage to scratch (exp-004) -->

{gotchas}

## Tried & abandoned (approaches that didn't work — do not re-try blindly)

<!-- approach -> where -> why it failed -> "don't retry unless <cond>".
     e.g.  - label smoothing 0.1: exp-006, no gain, reverted -->

{abandoned}

## What worked / settled here (keepers + key results)

<!-- decisions/results that HOLD, with run-id evidence. -->

{worked}
"""


def _make_notes(pdir, *, abandoned="*(none yet)*", worked="*(none yet)*", gotchas="*(none yet)*"):
    (pdir / "NOTES.md").write_text(
        _NOTES_TEMPLATE.format(gotchas=gotchas, abandoned=abandoned, worked=worked), encoding="utf-8")


def test_evolve_kill_blocked_without_correction(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    _make_notes(proj)  # all placeholders
    hub.add_registry_row("demo", state="killed", project=str(proj))
    assert _run(m, "evolve", types.SimpleNamespace(slug="demo")) == 1


def test_evolve_kill_ok_with_notes_correction(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    _make_notes(proj, abandoned="- curriculum LR: exp-005, diverged, reverted; skip unless data shifts")
    hub.add_registry_row("demo", state="killed", project=str(proj))
    assert _run(m, "evolve", types.SimpleNamespace(slug="demo")) == 0


def test_evolve_kill_ok_with_hub_failure(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    _make_notes(proj)  # placeholders, but the hub FAILURES.md carries the correction
    (hub.lab / "knowledge" / "FAILURES.md").write_text(
        "# Failures\n\n- [2026-06-26] (demo) approach X diverged — wrong scale\n", encoding="utf-8")
    hub.add_registry_row("demo", state="killed", project=str(proj))
    assert _run(m, "evolve", types.SimpleNamespace(slug="demo")) == 0


def test_evolve_triage_kill_without_project_not_blocked(hub, monkeypatch):
    # A kill at triage (no project — non-novel / out of scope) is recorded in IDEA.md/OPEN-QUESTIONS,
    # NOT FAILURES.md; the guard must not demand a correction it would be wrong to file.
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="killed", project="-")  # never spawned a project
    assert _run(m, "evolve", types.SimpleNamespace(slug="demo")) == 0


def test_evolve_a_finished_study_warns_without_recipe(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    _make_notes(proj)
    hub.add_registry_row("demo", state="final", project=str(proj))
    assert _run(m, "evolve", types.SimpleNamespace(slug="demo")) == 2


def test_evolve_a_finished_study_ok_with_recipe(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    _make_notes(proj, worked="- cosine LR is the keeper: +0.6% val (exp-007)")
    hub.add_registry_row("demo", state="final", project=str(proj))
    assert _run(m, "evolve", types.SimpleNamespace(slug="demo")) == 0


def test_evolve_active_state_is_ok_operators_optional(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    _make_notes(proj)  # nothing recorded yet, but mid-flight nothing is forced
    hub.add_registry_row("demo", state="active", project=str(proj))
    assert _run(m, "evolve", types.SimpleNamespace(slug="demo")) == 0


def test_evolve_placeholder_and_comment_dont_count_as_filled(hub, monkeypatch):
    # The example in the HTML comment + the *(none yet)* placeholder must NOT register as a real line.
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    _make_notes(proj)
    assert m._load_checks()["evolve"]._notes_section_filled(proj, "abandoned") is False
    assert m._load_checks()["evolve"]._notes_section_filled(proj, "worked") is False


# ── decisions (Revisit-predicate lint) ────────────────────────────────────────

def _write_decisions(hub, slug, decisions):
    """decisions: list of (D-NNN, status, headline, predicate|None)."""
    idx = ["## Decision index", "", "| ID | Decision | Status | Headline | Choice |",
           "|----|----------|--------|----------|--------|"]
    for d, status, headline, _ in decisions:
        idx.append(f"| {d} | area | {status} | {headline} | choice |")
    blocks = []
    for d, status, headline, pred in decisions:
        b = [f"## {d}: area", "", f"**Headline:** {headline}", "", "**Revisit if:** something"]
        if pred is not None:
            b.append(f"**Revisit predicate:** `{pred}`")
        blocks.append("\n".join(b))
    doc = "\n".join(idx) + "\n\n---\n\n" + "\n\n---\n\n".join(blocks) + "\n"
    f = hub.root / "studies" / slug / "decisions.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(doc, encoding="utf-8")
    return f


def _dec_ns(slug, strict=False):
    return types.SimpleNamespace(slug=slug, strict=strict)


def test_decisions_ok_well_formed_predicate(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _write_decisions(hub, "demo", [("D-001", "settled", "no",
                                    "metric(exp-003, val_acc) within seed_noise of best(baseline)")])
    assert _run(m, "decisions", _dec_ns("demo")) == 0


def test_decisions_warn_missing_predicate(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _write_decisions(hub, "demo", [("D-001", "settled", "no", None)])
    assert _run(m, "decisions", _dec_ns("demo")) == 2


def test_decisions_strict_blocks_missing(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _write_decisions(hub, "demo", [("D-001", "settled", "no", None)])
    assert _run(m, "decisions", _dec_ns("demo", strict=True)) == 1


def test_decisions_blocked_malformed_predicate(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _write_decisions(hub, "demo", [("D-001", "settled", "no", "just some prose, no function call")])
    assert _run(m, "decisions", _dec_ns("demo")) == 1


def test_decisions_headline_yes_exempt(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _write_decisions(hub, "demo", [("D-001", "settled", "yes", None)])
    assert _run(m, "decisions", _dec_ns("demo")) == 0


def test_decisions_open_exempt(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _write_decisions(hub, "demo", [("D-001", "OPEN", "no", None)])
    assert _run(m, "decisions", _dec_ns("demo")) == 0


def test_decisions_target_driven_exempt(hub, monkeypatch):
    import yaml
    # A target-driven project never runs /scope: no decisions.md is expected, so the guard PASSES (0)
    # rather than emitting the "run /scope first" WARN (2).
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("kaggle")
    ctl = yaml.safe_load((proj / "control.yaml").read_text(encoding="utf-8"))
    ctl["target"] = {"active": True}
    (proj / "control.yaml").write_text(yaml.safe_dump(ctl), encoding="utf-8")
    hub.add_registry_row("kaggle", state="active", project=str(proj))
    assert _run(m, "decisions", _dec_ns("kaggle")) == 0


# ── plan-trace (PLAN.md row provenance) ───────────────────────────────────────

def _plan_project(hub, slug, rows, replan_events=None, decisions_text=None):
    """rows: list of (id, question, criterion). Writes PLAN.md (+ optional hub decisions.md)."""
    proj = hub.make_project(slug)
    body = ["# Experiment Plan", "", "## Experiments", "",
            "| ID | Question | Stage | Status | Promotion/success criterion | Result (run ids) |",
            "|----|----------|-------|--------|------------------------------|------------------|"]
    for rid, q, crit in rows:
        body.append(f"| {rid} | {q} | SMOKE | todo | {crit} | |")
    body += ["", "## Re-planning log", "", "| date | event | detail | evidence |", "|---|---|---|---|"]
    for ev in (replan_events or []):
        body.append(f"| 2026-06-20 | {ev} | round 1 | exp-009 |")
    (proj / "PLAN.md").write_text("\n".join(body) + "\n", encoding="utf-8")
    hub.add_registry_row(slug, state="active", project=str(proj))
    if decisions_text is not None:
        f = hub.root / "studies" / slug / "decisions.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(decisions_text, encoding="utf-8")
    return proj


def test_plan_trace_ok_seed_only(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _plan_project(hub, "demo", [("exp-001", "pipeline end-to-end", "runs clean")])
    assert _run(m, "plan-trace", types.SimpleNamespace(slug="demo")) == 0


def test_plan_trace_ok_row_cites_decision(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _plan_project(hub, "demo",
                  [("exp-001", "smoke", "clean"), ("exp-002", "test D-003 dataset choice", "beats base")],
                  decisions_text="## D-003: dataset\n**Headline:** no\n")
    assert _run(m, "plan-trace", types.SimpleNamespace(slug="demo")) == 0


def test_plan_trace_ok_expand_row_with_log(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _plan_project(hub, "demo",
                  [("exp-001", "smoke", "clean"), ("exp-007", "curriculum (expand R1)", "beats base")],
                  replan_events=["frontier_expand"])
    assert _run(m, "plan-trace", types.SimpleNamespace(slug="demo")) == 0


def test_plan_trace_warn_untraceable_row(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _plan_project(hub, "demo",
                  [("exp-001", "smoke", "clean"), ("exp-002", "some new idea", "beats base")])
    assert _run(m, "plan-trace", types.SimpleNamespace(slug="demo")) == 2


def test_plan_trace_blocked_headline_change_row(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _plan_project(hub, "demo",
                  [("exp-001", "smoke", "clean"),
                   ("exp-002", "swap the objective — Headline-change: yes", "beats base")])
    assert _run(m, "plan-trace", types.SimpleNamespace(slug="demo")) == 1


def test_plan_trace_headline_change_not_smuggled_by_decision_cite(hub, monkeypatch):
    # A Headline-change:yes row must be BLOCKED even when it cites a real D-NNN — a decisions.md
    # decision is not a /propose origin, so it cannot smuggle a headline change past the gate.
    m = _mod(hub, monkeypatch)
    _plan_project(hub, "demo",
                  [("exp-001", "smoke", "clean"),
                   ("exp-002", "rework objective per D-003 — Headline-change: yes", "beats base")],
                  decisions_text="## D-003: objective\n**Headline:** no\n")
    assert _run(m, "plan-trace", types.SimpleNamespace(slug="demo")) == 1


def test_plan_trace_blocked_no_plan(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    (proj / "PLAN.md").unlink(missing_ok=True)
    hub.add_registry_row("demo", state="active", project=str(proj))
    assert _run(m, "plan-trace", types.SimpleNamespace(slug="demo")) == 1


def test_the_guard_lists_and_runs_every_check(hub):
    import subprocess
    r = subprocess.run([sys.executable, str(REPO / "tools" / "guard.py"), "--list"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    names = {ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()}
    assert {"frozen", "append-only", "writeback", "evolve", "full-runs-without-approval"} <= names
    assert not {"approved", "spawn", "state", "finalization"} & names        # the kernel's now, not checks
