"""`arlotope <verb>` (tools/arlotope_cli.py): the whole lab from a terminal, through the same kernel the dashboard uses.
The PI's verbs ask for confirmation (or --yes) and refuse inside an agent run; every dashboard action names the
verb that does the same."""

from __future__ import annotations

import io
import json
import sys

import pytest

from conftest import REPO, kernel, load

K = kernel()


@pytest.fixture(autouse=True)
def _not_in_a_run(monkeypatch):
    monkeypatch.delenv("ARLOTOPE_RUN_ID", raising=False)


@pytest.fixture
def cli(hub, monkeypatch):
    (hub.lab / "config.yaml").write_text(
        'lab:\n  projects_root: "../projects"\nagents:\n  programmatic:\n    enabled: true\n    backend: claude\n'
        f"    backends:\n      claude:\n        command: {json.dumps([sys.executable, str(REPO / 'tests' / 'fake_claude.py')])}\n",
        encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))       # no terminal to ask on
    mod = load("arlotope_cli")
    return lambda *argv: mod.main(["--hub", str(hub.root), *argv])


def test_file_move_and_finish_from_the_terminal(hub, cli, capsys):
    assert cli("new", "demo", "--title", "Demo", "--workflow", "quick") == 0
    assert "filed at Idea (quick workflow)" in capsys.readouterr().out
    assert cli("move", "demo", "done") == 1                                 # done means the step's work is there
    assert "studies/demo/IDEA.md is not" in capsys.readouterr().err
    hub.produce("demo")
    assert cli("move", "demo", "done") == 0
    assert "demo → Proposal. Next: /propose demo" in capsys.readouterr().out
    assert cli("move", "demo", "sideways") == 1
    assert "not an outcome of proposal" in capsys.readouterr().err
    assert cli("next", "demo") == 0 and "next: /propose demo" in capsys.readouterr().out
    assert cli("move", "demo", "--to", "analysis") == 1                     # the PI's move: confirm it
    assert cli("move", "demo", "--to", "analysis", "--yes", "--note", "skip ahead") == 0
    capsys.readouterr()
    assert cli("move", "demo", "done") == 0 and cli("move", "demo", "done") == 0
    assert "demo has finished its workflow." in capsys.readouterr().out
    assert cli("studies") == 0 and "finished" in capsys.readouterr().out


def test_approve_revoke_and_changes(hub, cli, capsys):
    hub.add_registry_row("demo", state="proposal")
    K.studies.move(hub.root, "demo", "done")                                # it waits at its checkpoint
    assert cli("approve", "demo", "approve-proposal") == 1                  # no --yes and no terminal: refused
    assert "pass --yes" in capsys.readouterr().err
    assert cli("approve", "demo", "approve-proposal", "--yes", "--note", "keep it small") == 0
    out = capsys.readouterr().out
    assert "demo → Project set-up" in out and "next: arlotope start spawn-project demo" in out
    rec = K.journal.latest(hub.root, "demo", "approve-proposal")
    assert (rec["decision"], rec["by"], rec["via"], rec["note"]) == ("approved", "pi", "cli", "keep it small")
    assert cli("approved", "demo", "approve-proposal") == 0 and "the PI's note: keep it small" in capsys.readouterr().out
    assert cli("revoke", "demo", "approve-proposal", "--yes") == 0
    assert cli("approved", "demo", "approve-proposal") == 1 and "was revoked" in capsys.readouterr().out
    assert cli("changes", "demo", "approve-proposal", "--yes") == 2         # say what should change
    assert cli("changes", "demo", "approve-proposal", "--yes", "--note", "cut exp-3") == 0
    assert cli("approve", "demo", "nope", "--yes") == 2
    assert cli("approve", "lab", "campaign:c1", "--yes") == 0                # a lab-wide approval
    assert K.journal.approved(hub.root, "lab", "campaign:c1")


def test_approve_can_start_the_next_steps_work(hub, cli, capsys):
    hub.add_registry_row("demo", state="internal-review")
    K.studies.move(hub.root, "demo", "done")
    assert cli("approve", "demo", "finalize-paper", "--yes", "--start") == 0
    assert "queued" in capsys.readouterr().out
    import executor
    runs = [m for *_x, m in executor.all_runs(executor.Lab(hub.root))]
    assert [(m["skill"], m["subject"], m["created_by"]) for m in runs] == [("finalize", "demo", "cli")]


def test_the_pis_verbs_refuse_inside_an_agent_run(hub, cli, monkeypatch, capsys):
    hub.add_registry_row("demo", state="proposal")
    monkeypatch.setenv("ARLOTOPE_RUN_ID", "hub-x-1")
    for argv in (("approve", "demo", "approve-proposal", "--yes"), ("revoke", "demo", "approve-proposal", "--yes"),
                 ("move", "demo", "--to", "active", "--yes"), ("workflow", "set", "demo", "quick"),
                 ("workflow", "rename-step", "active", "running", "--yes"), ("hold", "demo"), ("release", "demo"),
                 ("config", "set", "agents.programmatic.permission_mode=bypassPermissions")):
        assert cli(*argv) == 1, argv
    assert "an agent run can't" in capsys.readouterr().err
    assert K.journal.approvals(hub.root) == []
    assert cli("move", "demo", "done") == 0                                   # the agent's own move is fine


def test_status_brief_and_checkpoint(hub, cli, capsys):
    hub.add_registry_row("demo", title="Demo", state="proposal")
    K.studies.move(hub.root, "demo", "done")
    assert cli("status") == 0
    out = capsys.readouterr().out
    assert "1 thing(s) need you." in out and "Approve the proposal" in out and "arlotope checkpoint demo approve-proposal" in out
    assert cli("--json", "status") == 0
    data = json.loads(capsys.readouterr().out)
    assert data["waiting"][0]["study"] == "demo" and data["waiting"][0]["checkpoint"] == "approve-proposal"
    assert cli("checkpoint", "demo", "approve-proposal") == 0
    out = capsys.readouterr().out
    assert "before setup" in out and "it waits for this" in out
    assert cli("brief", "propose", "--study", "demo") == 0
    assert "ARLOTOPE BRIEF /propose · study demo" in capsys.readouterr().out
    assert cli("approve", "demo", "approve-proposal", "--yes") == 0
    capsys.readouterr()
    cli("status")
    assert "Nothing needs you." in capsys.readouterr().out
    assert cli("approvals", "demo") == 0 and "approve-proposal" in capsys.readouterr().out


def test_check_docs_and_propose(hub, cli, capsys, tmp_path):
    assert cli("check") == 0 and "[arlotope] ok" in capsys.readouterr().out
    f = tmp_path / "draft.md"
    f.write_text("Cite the closest three papers.", encoding="utf-8")
    assert cli("propose", "lit-review", "--file", str(f), "--why", "seen twice") == 0
    assert [p["name"] for p in K.instructions.proposals(hub.root)] == ["lit-review"]
    assert cli("propose", "step:analysis", "--file", str(f)) == 0
    assert K.instructions.proposals(hub.root)[-1]["kind"] == "step"


def _routes(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    return load("dashboard/serve").POST_ROUTES, load("arlotope_cli")


def test_every_dashboard_action_has_a_terminal_verb(monkeypatch):
    """ROUTE_VERBS names the CLI verb for every POST route the dashboard serves (or says it is dashboard-only),
    and every verb it names exists."""
    routes, cli = _routes(monkeypatch)
    assert set(routes) - set(cli.ROUTE_VERBS) == set()
    for r in ("/api/checkpoint/decide", "/api/study/move", "/api/study/hold", "/api/study/workflow", "/api/study/use"):
        assert cli.ROUTE_VERBS[r] != "dashboard-only", r
    verbs = {v.split()[0] for v in cli.ROUTE_VERBS.values() if v != "dashboard-only" and not v.startswith("arlotope.py")}
    assert verbs <= cli.VERBS, verbs - cli.VERBS
