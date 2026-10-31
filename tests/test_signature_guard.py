"""tools/signature_guard.py — in a headless run, the PI's records and the lab's definition are the PI's.

The guard is an early warning on the tool calls it sees: edits to the journal and the registry written from it,
the check results, the campaigns' state, the usage limits, the PI-action log, the panel collector approvals, the
Compose draft, workflow/, the skills, the roles and the checks (the floor no rules.yaml lowers), the lab's
settings (except in /setup-lab and /configure), the protected paths of workflow/rules.yaml — and `arlo
approve`/`revoke`, --skip-guard and new.py on the shell. Code an agent runs writes past any pattern, so what
holds is checked from outside: signed approvals (test_kernel), and each attempt's fingerprint of what only the PI
changes (here, and test_run_records). Prose in a document approves nothing, so writing it is fine. Covered across
tool shapes (claude Edit/Write/MultiEdit/Bash, codex apply_patch, opencode edit) and the hook contract (exit 2 +
reason on stderr, the denial logged to the run's permissions.jsonl; a guard that fails allows the call and says so).
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from conftest import REPO, load

MARK = "<!-- PI Gate 1 approved via the dashboard 2026-09-01T10:00:00 -->"
REC = json.dumps({"ts": "2026-09-01T10:00:00", "study": "idea-a", "checkpoint": "approve-proposal",
                  "decision": "approved", "by": "pi", "via": "dashboard"})


@pytest.fixture
def g(hub, monkeypatch):
    mod = load("signature_guard")
    monkeypatch.setattr(mod, "HUB", hub.root.resolve())
    monkeypatch.delenv("ARLOTOPE_RUN_SKILL", raising=False)
    (hub.root / "studies" / "idea-a").mkdir(parents=True)
    (hub.root / "studies" / "idea-a" / "proposal.md").write_text("# Proposal\n\n## Gate\n\npending\n", encoding="utf-8")
    return mod


def edit(path, old, new):
    return {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(path.parent),
            "tool_input": {"file_path": str(path), "old_string": old, "new_string": new}}


def write(path, content):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(path.parent),
            "tool_input": {"file_path": str(path), "content": content}}


def bash(cmd, cwd="."):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(cwd), "tool_input": {"command": cmd}}


# ── the PI's records ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("rel", ["lab/journal.jsonl", "lab/REGISTRY.md", "lab/approvals.jsonl",
                                 "lab/.bus/checks/idea-a/finalize-paper.json",
                                 "lab/.bus/campaigns/2026-09-01-x.json", "lab/.bus/limits.json",
                                 "lab/.bus/pi-actions.jsonl", "lab/.bus/panels/approved.json"])
def test_the_pis_records_are_denied(g, hub, rel):
    """No run writes an approval, a check result, a campaign's state, the limits or the PI-action log."""
    p = hub.root / rel
    assert g.decide(write(p, REC + "\n"))
    assert g.decide(edit(p, "x", "y"))


def test_writing_an_approval_phrase_in_a_document_is_harmless_and_allowed(g, hub):
    """Prose means nothing now: an agent may write "Gate 1 approved" in its proposal — it approves nothing."""
    p = hub.root / "studies" / "idea-a" / "proposal.md"
    assert g.decide(edit(p, "pending", MARK)) is None
    assert g.decide(write(p, "# Proposal\n" + MARK)) is None
    paper = hub.root / "studies" / "idea-a" / "paper"
    assert g.decide(write(paper / "gate3-approval.md", "Gate 3 approved")) is None
    pdir = hub.make_project("idea-a", control=False)
    assert g.decide(write(pdir / "control.yaml", "eval_frozen: true\n")) is None
    assert g.decide(write(pdir / "LOOP_BRIEF.md", "- [x] Authorized as scoped above\n")) is None


def test_a_campaign_brief_is_a_work_file_the_registry_is_not(g, hub):
    """A campaign brief is written by procedures (approving it is a record); the registry is the kernel's view
    of the journal — a study moves with `arlo move`, never by an edit."""
    hub.add_registry_row("idea-a", state="internal-review")
    reg = hub.lab / "REGISTRY.md"
    assert "arlo move" in g.decide(edit(reg, "| idea-a | T | internal-review |", "| idea-a | T | final |"))
    d = hub.lab / "campaigns"
    d.mkdir(parents=True)
    assert g.decide(write(d / "2026-09-04-new.md", "# C\n\n## Campaign Log\n")) is None


# ── lab config ────────────────────────────────────────────────────────────────

CFG = "compute:\n  max_concurrent_runs: 1\nideation:\n  candidates: 8\nagents:\n  programmatic:\n    enabled: false\n"


def test_lab_config_is_the_pis_except_in_the_config_procedures(g, hub, monkeypatch):
    """The whole of lab/config.yaml is denied, unless the run is /setup-lab or /configure (with the PI)."""
    c = hub.lab / "config.yaml"
    c.write_text(CFG, encoding="utf-8")
    assert g.decide(edit(c, "enabled: false", "enabled: true"))
    assert g.decide(edit(c, "candidates: 8", "candidates: 12"))
    for skill in ("setup-lab", "configure"):
        monkeypatch.setenv("ARLOTOPE_RUN_SKILL", skill)
        assert g.decide(edit(c, "max_concurrent_runs: 1", "max_concurrent_runs: 8")) is None
        assert g.decide(bash("sed -i 's/candidates: 8/candidates: 12/' lab/config.yaml", hub.root)) is None
    monkeypatch.setenv("ARLOTOPE_RUN_SKILL", "experiment")
    assert g.decide(edit(c, "max_concurrent_runs: 1", "max_concurrent_runs: 8"))
    monkeypatch.setenv("ARLOTOPE_RUN_SKILL", "configure")
    assert g.decide(write(hub.lab / "approvals.jsonl", REC))            # a config run still never approves
    assert g.decide(write(hub.lab / ".bus" / "pi-actions.jsonl", "{}"))


# ── shell ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "arlo approve idea-a approve-proposal --yes",
    "python arlo.py revoke idea-a finalize-paper --yes",
    "uv run --with pyyaml python arlo.py approve idea-a approve-proposal --yes",
    "arlo hold idea-b --reason 'stop it'",
    "uv run --with pyyaml python arlo.py pause",
    "python \"C:/hub/arlo.py\" approve-collector gpu --yes",
    "./arlo approve idea-a approve-proposal --yes",
    '.\\arlo.cmd revoke idea-a finalize-paper --yes',
    '"C:/My Lab/arlo.cmd" pause',
    "python tools/spawn_project.py idea-a --skip-guard",
    "python tools/new.py procedure survey",
])
def test_the_pis_verbs_on_the_shell_are_denied(g, cmd):
    assert g.decide(bash(cmd))


@pytest.mark.parametrize("cmd", [
    "grep -n 'PI Gate 1' studies/idea-a/proposal.md",
    "cat lab/approvals.jsonl",
    "uv run python tools/guard.py frozen idea-a 2>&1",
    "uv run --with pyyaml python arlo.py move idea-a done --note 'proposal written'",
    "arlo approved idea-a approve-full-runs",
    "arlo status",
    "cat lab/journal.jsonl",
    "echo x > ../projects/idea-a/templates/page.html",
    "cat ../projects/idea-a/control.yaml | grep eval_frozen",
    "uv run python scripts/run.py --stage FULL > runs/log.txt 2>&1",
    "echo '<!-- PI Gate 1 approved -->' >> studies/idea-a/proposal.md",
    "ls lab/.bus",
])
def test_shell_reads_and_work_are_fine(g, cmd):
    assert g.decide(bash(cmd)) is None


@pytest.mark.parametrize("cmd", ["arlo checkpoint idea-a approve-proposal", "arlo checks idea-a approve-full-runs"])
def test_reading_a_checkpoint_from_the_cli_is_fine(g, cmd):
    assert g.decide(bash(cmd)) is None


# ── other tool shapes ─────────────────────────────────────────────────────────

def test_codex_apply_patch_opencode_edit_and_multiedit(g, hub):
    a = hub.lab / "approvals.jsonl"
    p = hub.root / "studies" / "idea-a" / "proposal.md"
    patch = f"*** Begin Patch\n*** Add File: {a}\n+{REC}\n*** End Patch\n"
    assert g.decide({"tool_name": "apply_patch", "cwd": str(hub.root), "tool_input": {"command": patch}})
    rel = "*** Begin Patch\n*** Update File: lab/approvals.jsonl\n@@\n+{}\n*** End Patch\n"
    assert g.decide({"tool_name": "apply_patch", "cwd": str(hub.root), "tool_input": {"input": rel}})
    ok_patch = f"*** Begin Patch\n*** Update File: {p}\n@@\n-pending\n+{MARK}\n*** End Patch\n"
    assert g.decide({"tool_name": "apply_patch", "cwd": str(hub.root), "tool_input": {"command": ok_patch}}) is None
    assert g.decide({"tool_name": "edit", "cwd": str(hub.root),
                     "tool_input": {"filePath": str(a), "oldString": "x", "newString": "y"}})
    assert g.decide({"tool_name": "MultiEdit", "cwd": str(hub.root), "tool_input": {
        "file_path": str(a), "edits": [{"old_string": "x", "new_string": "y"}]}})
    assert g.decide({"tool_name": "Read", "cwd": str(hub.root), "tool_input": {"file_path": str(a)}}) is None


def test_hook_contract_exit_2_and_logged(hub, tmp_path):
    (hub.root / "studies" / "idea-a").mkdir(parents=True)
    p = hub.root / "studies" / "idea-a" / "proposal.md"
    p.write_text("pending\n", encoding="utf-8")
    rd = tmp_path / "run.d"
    rd.mkdir()
    env = {**__import__("os").environ, "ARLOTOPE_HUB": str(hub.root), "ARLOTOPE_RUN_DIR": str(rd)}
    env.pop("ARLOTOPE_RUN_SKILL", None)
    r = subprocess.run([sys.executable, str(REPO / "tools" / "signature_guard.py")],
                       input=json.dumps(write(hub.lab / "approvals.jsonl", REC)),
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 2 and "signature guard" in r.stderr
    rec = json.loads((rd / "permissions.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert rec["decision"] == "deny" and rec["by"] == "signature-guard" and "approvals" in rec["summary"]
    ok = subprocess.run([sys.executable, str(REPO / "tools" / "signature_guard.py")], input=json.dumps(edit(p, "pending", MARK)),
                        capture_output=True, text=True, env=env, timeout=60)
    assert ok.returncode == 0
    junk = subprocess.run([sys.executable, str(REPO / "tools" / "signature_guard.py")], input="not json",
                          capture_output=True, text=True, env=env, timeout=60)
    assert junk.returncode == 0
    other = subprocess.run([sys.executable, str(REPO / "tools" / "signature_guard.py")],
                           input=json.dumps({**write(hub.lab / "approvals.jsonl", REC), "hook_event_name": "PostToolUse"}),
                           capture_output=True, text=True, env=env, timeout=60)
    assert other.returncode == 0                        # only PreToolUse is judged


NODE = __import__("shutil").which("node")


def test_opencode_guard_preserves_native_configuration_without_a_new_dependency_directory(tmp_path):
    from types import SimpleNamespace
    from executor.backends import opencode
    directory = tmp_path/'custom-config'
    directory.mkdir()
    existing={'plugin':['my-existing-plugin'], 'model':'openrouter/my-model'}
    attempt=SimpleNamespace(env={'OPENCODE_CONFIG_DIR':str(directory),
        'OPENCODE_CONFIG_CONTENT':json.dumps(existing)}, bcfg={},rd=tmp_path/'run.d',
        guard=REPO/'tools/signature_guard.py',python=sys.executable,workdir=tmp_path)
    opencode.Opencode().prepare(attempt)
    assert attempt.env['OPENCODE_CONFIG_DIR']==str(directory)
    configured=json.loads(attempt.env['OPENCODE_CONFIG_CONTENT'])
    assert configured['model']==existing['model'] and configured['plugin'][0]=='my-existing-plugin'
    assert configured['plugin'][1]==(attempt.rd/'arlotope-guard.mjs').as_uri()
    assert not (attempt.rd/'opencode-config').exists()


@pytest.mark.skipif(not NODE, reason="node is needed to load the opencode plugin")
def test_opencode_guard_plugin_blocks_under_node(hub, tmp_path):
    sys.path.insert(0, str(REPO / "tools"))
    from executor.backends import opencode
    (hub.root / "studies" / "idea-a").mkdir(parents=True)
    p = hub.root / "studies" / "idea-a" / "proposal.md"
    p.write_text("pending\n", encoding="utf-8")
    a = hub.lab / "approvals.jsonl"
    plugin = opencode.guard_plugin(tmp_path / "run.d", REPO / "tools" / "signature_guard.py", sys.executable).as_uri()
    js = f"""
const {{ ARLOtopeGuard }} = await import({json.dumps(plugin)})
const hooks = await ARLOtopeGuard({{ directory: {json.dumps(str(hub.root))} }})
const call = (a) => hooks["tool.execute.before"]({{ tool: "edit", sessionID: "s", callID: "c" }}, {{ args: a }})
let denied = false
try {{ await call({{ filePath: {json.dumps(str(a))}, oldString: "x", newString: "y" }}) }} catch (e) {{ denied = /signature guard/.test(e.message) }}
await call({{ filePath: {json.dumps(str(p))}, oldString: "pending", newString: "later" }})
console.log(JSON.stringify({{ denied }}))
"""
    env = {**__import__("os").environ, "ARLOTOPE_HUB": str(hub.root)}
    env.pop("ARLOTOPE_RUN_SKILL", None)
    r = subprocess.run([NODE, "--input-type=module", "-e", js], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1]) == {"denied": True}


# ── procedures, roles, panels and the PI's stage instructions ─────────────────

@pytest.mark.parametrize("rel", [".claude/skills/experiment/SKILL.md", "agent-roles/overseer.md",
                                 ".claude/agents/overseer.md", "workflow/steps.yaml", "workflow/workflows/research.yaml",
                                 "lab/workflow/experiment.add.md", "studies/idea-a/workflow/propose.add.md",
                                 "lab/rooms3d/lab.json", "lab/panels/gpu/collect.py",
                                 "extensions/mine/workflow/steps.yaml"])
def test_agents_cannot_edit_procedures_or_their_own_instructions(g, hub, rel):
    p = hub.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    why = g.decide(write(p, "be sloppier"))
    assert why and "arlo propose" in why
    assert g.decide(write(hub.lab / ".bus" / "compose" / "draft" / "workflow" / "steps.yaml", "x"))   # nor the PI's draft


def test_proposing_an_instruction_change_is_allowed(g, hub):
    assert g.decide(bash("uv run --with pyyaml python arlo.py propose experiment --file /tmp/draft.md", hub.root)) is None
    assert g.decide(write(hub.root / "studies" / "idea-a" / "notes.md", "fine")) is None
    assert g.decide(write(hub.lab / ".bus" / "designs" / "panels" / "gpu" / "view.html", "<p>")) is None


def test_the_rules_the_manuals_and_the_checks_are_the_pis(g, hub):
    """workflow/rules.yaml's protected_paths: a run can't rewrite the lab's rules, its manuals, its checks or
    its templates (it proposes instead); ordinary work files stay writable."""
    for rel in ("workflow/rules.yaml", "AGENTS.md", "CLAUDE.md", "checks/evolve.py", "templates/idea/proposal.md",
                "lab/templates/idea/proposal.md", ".claude/skills/propose/SKILL.md"):
        assert g.decide(write(hub.root / rel, "x\n")), rel
    assert g.decide(write(hub.root / "studies" / "idea-a" / "notes.md", "fine\n")) is None


def test_a_labs_own_protected_paths_are_honoured(g, hub):
    """A lab can protect more (its rules.yaml protected_paths) — on top of the floor, never instead."""
    (hub.root / "workflow").mkdir(exist_ok=True)
    (hub.root / "workflow" / "rules.yaml").write_text("protected_paths:\n  - '^data/frozen/'\n", encoding="utf-8")
    assert g.decide(write(hub.root / "data" / "frozen" / "test.csv", "a,b\n"))
    assert g.decide(write(hub.root / "data" / "scratch.csv", "a,b\n")) is None
    assert g.decide(write(hub.root / "agent-roles" / "x.md", "y"))          # the floor still holds
    assert g.decide(write(hub.root / "checks" / "x.py", "y")) and g.decide(write(hub.lab / "journal.jsonl", "{}"))


def test_a_guard_that_fails_allows_the_call_and_flags_it(hub, tmp_path):
    """A bug in the guard never wedges a run: the call is allowed, the error logged, and a warn flag raised."""
    rd = tmp_path / "run.d"
    rd.mkdir()
    (hub.root / "workflow").mkdir(exist_ok=True)
    (hub.root / "workflow" / "rules.yaml").write_text("protected_paths:\n  - '('\n", encoding="utf-8")   # a broken regex
    env = {**__import__("os").environ, "ARLOTOPE_HUB": str(hub.root), "ARLOTOPE_RUN_DIR": str(rd), "ARLOTOPE_RUN_ID": "r-1"}
    r = subprocess.run([sys.executable, str(REPO / "tools" / "signature_guard.py")],
                       input=json.dumps(write(hub.root / "studies" / "x" / "notes.md", "x")),
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0
    assert '"decision": "error"' in (rd / "permissions.jsonl").read_text(encoding="utf-8")
    sys.path.insert(0, str(REPO / "tools"))
    from kernel import watch
    assert any(f["source"] == "guard" and f["level"] == "warn" for f in watch.flags(hub.root))


def test_a_run_cannot_switch_its_own_guard_off(g, hub):
    """The guard runs on every call, from the lab's own copy: a run that could rewrite it could switch it off.
    The rest of the lab's code is not the guard's to protect (monitoring.md: an agent can run code)."""
    for rel in ("tools/signature_guard.py", "tools/executor/opencode_guard.js"):
        p = hub.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        assert "switch it off" in (g.decide(write(p, "")) or ""), rel
    assert g.decide(write(hub.root / "tools" / "kernel" / "studies.py", "x")) is None


@pytest.mark.parametrize("code", [
    "open('workflow/rules.yaml','a').write('protected_paths: []')",                        # the forms no pattern saw
    "import shutil; shutil.copy('studies/idea-a/proposal.md', 'checks/always_pass.py')",
    "import base64,pathlib; pathlib.Path('AGENTS.md').write_bytes(base64.b64decode('eA=='))",
    "import os; os.remove('agent-roles/overseer.md')",
    "import pathlib; pathlib.Path('lab/config.yaml').write_text('agents: {}')",
])
def test_what_the_guard_cannot_see_is_seen_after_the_attempt(g, hub, code):
    """No pattern sees every way code writes a file, so each attempt's supervisor fingerprints what only the PI
    changes (the definition, and the settings outside /configure) before and after: a change holds the lab."""
    from executor import Lab
    import lab_profile as profile
    from kernel import watch
    lab = Lab(hub.root)
    (hub.root / "workflow").mkdir(exist_ok=True)
    (hub.root / "workflow" / "rules.yaml").write_bytes((REPO / "workflow" / "rules.yaml").read_bytes())
    for rel in ("AGENTS.md", "agent-roles/overseer.md", "checks/frozen.py"):
        (hub.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (hub.root / rel).write_text("x\n", encoding="utf-8")
    m = {"run_id": "r-1", "skill": "experiment"}
    before = profile.definition(lab, m)
    assert {"workflow/rules.yaml", "AGENTS.md", "agent-roles/overseer.md", "checks/frozen.py", "lab/config.yaml"} <= set(before)
    (hub.root / "studies" / "idea-a" / "notes.md").write_text("ordinary work", encoding="utf-8")
    assert profile.definition_changed(lab, m, before) is None
    subprocess.run([sys.executable, "-c", code], cwd=hub.root, check=True, timeout=60)
    f = profile.definition_changed(lab, m, before)
    assert f["level"] == "block" and f["hold"] and f["run"] == "r-1"
    with pytest.raises(ValueError, match="held by a flag"):
        profile.check_launch(lab, "lab-status", None)
    watch.ack(hub.root, f["id"])
    profile.check_launch(lab, "lab-status", None)                      # the PI has looked: work goes on


def test_a_configure_run_may_change_the_settings_but_nothing_else(g, hub):
    from executor import Lab
    import lab_profile as profile
    lab, m = Lab(hub.root), {"run_id": "r-2", "skill": "configure"}
    (hub.root / ".claude" / "agents").mkdir(parents=True)
    (hub.root / ".claude" / "agents" / "overseer.md").write_text("model: a", encoding="utf-8")
    before = profile.definition(lab, m)
    (hub.lab / "config.yaml").write_text("agents: {}\n", encoding="utf-8")
    (hub.root / ".claude" / "agents" / "overseer.md").write_text("model: b", encoding="utf-8")   # role_sync renders
    assert profile.definition_changed(lab, m, before) is None
    (hub.root / "checks").mkdir(exist_ok=True)
    (hub.root / "checks" / "x.py").write_text("x", encoding="utf-8")
    assert "checks/x.py" in profile.definition_changed(lab, m, before)["detail"]


def fenced_procedure(hub):
    """Explicit fixture scope; shipped /design now prepares a workspace rather than running directly."""
    import shutil
    shutil.copytree(REPO / '.claude/skills', hub.root / '.claude/skills', dirs_exist_ok=True)
    path = hub.root / '.claude/skills/design/SKILL.md'
    path.write_text(path.read_text(encoding='utf-8').replace('writes: ["lab/.bus/designs/workflow/**"]', 'writes: [lab/.bus/designs/**]', 1), encoding='utf-8')


def test_declared_write_scope_applies_to_edits(g, hub, monkeypatch):
    """A procedure that declares `writes:` is confined to it through its edit tools; the system temp folder stays
    usable; other runs are not confined. (What its shell writes elsewhere is flagged after the run, below.)"""
    import tempfile
    monkeypatch.setenv("ARLOTOPE_RUN_SKILL", "design")
    root = hub.root
    fenced_procedure(hub)
    w = lambda p: {"hook_event_name": "PreToolUse", "tool_name": "Write", "cwd": str(root),   # noqa: E731
                   "tool_input": {"file_path": str(p), "content": "x"}}
    sh = lambda c: {"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(root),   # noqa: E731
                    "tool_input": {"command": c}}
    assert g.decide(w(root / "lab" / ".bus" / "designs" / "workflow" / "1" / "workflow" / "steps.yaml")) is None
    assert "writes only lab/.bus/designs/**" in g.decide(w(root / "tools" / "kernel" / "model.py"))
    assert "writes only" in g.decide(w(root / "dashboard" / "static" / "ui" / "app.js"))
    assert g.decide(w(__import__("pathlib").Path.home() / "projects" / "x" / "run.py"))       # outside the lab and temp
    assert g.decide(w(__import__("pathlib").Path(tempfile.gettempdir()) / "scratch.txt")) is None
    assert g.decide(sh("python lab/.bus/designs/panels/p/collect.py 2>&1 | head -5")) is None
    monkeypatch.setenv("ARLOTOPE_RUN_SKILL", "analyze")
    assert g.decide(w(root / "studies" / "idea-a" / "notes.md")) is None


def test_declared_write_scope_violation_is_flagged(hub):
    from conftest import kernel
    watch = kernel().watch
    fenced_procedure(hub)
    m = {"run_id": "r1", "skill": "design", "subject": None}
    ok = {"written": [(hub.root / "lab" / ".bus" / "designs" / "x" / "panel.yaml").as_posix()], "deleted": []}
    assert watch._outside_writes(hub.root, m, ok, None, "r1") == []
    bad = {"written": [(hub.root / "tools" / "panels.py").as_posix()], "deleted": []}
    f = watch._outside_writes(hub.root, m, bad, None, "r1")
    assert f and f[0]["rule"] == "writes-outside" and "tools/panels.py" in f[0]["detail"]
    assert watch._outside_writes(hub.root, dict(m, skill="analyze"), bad, None, "r1") == []
