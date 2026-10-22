"""Panels (tools/panels.py) — the lab's instruments — and their sandboxed view (dashboard/panels_api.py).

What is protected: the library's precedence (shipped < yours < the lab's, so a lab's own panel wins); a lab
panel's collector is code and never runs until the PI approved THAT version of it (a record carrying its sha —
a changed script is blocked again); plain-read sources (files, registry) need no approval; every panel has a
summary line; a panel's alert holds a study's launches only when the PI let that panel hold; saving keeps the
old version; a view gets a CSP with no network at all.
"""

from __future__ import annotations

import json
import sys
import time

import pytest
import yaml

from conftest import REPO, approve, kernel, load

K = kernel()

sys.path.insert(0, str(REPO / "tools"))


@pytest.fixture
def pn(hub, monkeypatch, tmp_path):
    monkeypatch.setenv("ARLOTOPE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ARLOTOPE_RUN_ID", raising=False)
    return load("panels")


def _panel(root, pid, definition, view="<p>hi</p>", collector=None):
    d = root / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "panel.yaml").write_text(yaml.safe_dump(definition), encoding="utf-8")
    (d / "view.html").write_text(view, encoding="utf-8")
    if collector:
        (d / collector[0]).write_text(collector[1], encoding="utf-8")
    return d


def _quiet(pn, hub):
    """No pins: the shipped Compute/spend panels (pinned on first use) are not collected by these tests."""
    pn._save_state(hub.root, {})


COLLECT = "import json\nprint(json.dumps({'gpu_hours': 12.5, 'jobs': 3, 'summary': None}))\n"


# ── the library ───────────────────────────────────────────────────────────────────────────────────

def test_the_library_layers_shipped_yours_and_the_labs(pn, hub):
    lib = {p["id"]: p for p in pn.library(hub.root)}
    assert {"compute", "agent-spend", "studies-by-step"} <= set(lib) and lib["compute"]["origin"] == "shipped"
    assert lib["compute"]["pinned"] == ["home", "dock", "studies"]                   # pinned on first use
    _panel(pn.user_dir(), "compute", {"title": "My compute", "source": "registry"})
    assert pn.get(hub.root, "compute")["origin"] == "yours" and pn.get(hub.root, "compute")["title"] == "My compute"
    _panel(pn.lab_dir(hub.root), "compute", {"title": "Lab compute", "source": "registry"})
    p = pn.get(hub.root, "compute")
    assert p["origin"] == "lab" and p["title"] == "Lab compute" and p["sources"] == ["registry"]
    _panel(pn.lab_dir(hub.root), "Bad_Id", {"title": "x"})                          # not a panel id: ignored
    assert pn.get(hub.root, "Bad_Id") is None
    with pytest.raises(ValueError):
        pn.set_state(hub.root, "nope", pinned=["home"])
    assert pn.set_state(hub.root, "compute", pinned=["dock"], may_hold=True) == {"pinned": ["dock"], "may_hold": True}
    assert pn.get(hub.root, "compute")["may_hold"] is True


def test_every_and_sources_are_read_safely(pn):
    assert pn.parse_every("2m") == 120 and pn.parse_every("1h") == 3600 and pn.parse_every("5") == pn.MIN_EVERY
    assert pn.parse_every("soon") == 300 and pn.parse_every(None) == 300


# ── collecting ────────────────────────────────────────────────────────────────────────────────────

def test_files_and_registry_sources_need_no_approval(pn, hub):
    hub.add_registry_row("idea-a", title="A", state="active")
    proj = hub.make_project("idea-a")
    (proj / "runs" / "r1").mkdir(parents=True)
    (proj / "runs" / "r1" / "meta.json").write_text(json.dumps({"stage": "FULL", "minutes": 7}), encoding="utf-8")
    (hub.lab / "budget.csv").write_text("who,hours\nlab,10\n", encoding="utf-8")
    _panel(pn.lab_dir(hub.root), "runs-and-studies",
           {"title": "Runs", "source": ["files", "registry"], "files": ["{projects}/*/runs/*/meta.json", "lab/budget.csv"],
            "summary": "{missing} of it"})
    res = pn.collect(hub.root, "runs-and-studies")
    files = {f["path"].rsplit("/", 1)[-1]: f["data"] for f in res["data"]["files"]}
    assert files["meta.json"] == {"stage": "FULL", "minutes": 7} and files["budget.csv"] == [{"who": "lab", "hours": "10"}]
    assert res["data"]["studies"][0]["id"] == "idea-a" and res["error"] is None
    assert res["summary"] == "? of it"                                              # a missing key reads as ?
    assert pn.cached(hub.root, "runs-and-studies")["data"]["studies"][0]["state"] == "active"
    assert pn.collector_approved(hub.root, pn.get(hub.root, "runs-and-studies"))   # nothing to approve


def test_a_lab_collector_runs_only_once_its_version_is_approved(pn, hub):
    d = _panel(pn.lab_dir(hub.root), "gpu", {"title": "GPU", "source": "collector", "collector": "collect.py",
                                             "summary": "{gpu_hours:.0f} GPU-h over {jobs} jobs"},
               collector=("collect.py", COLLECT))
    p = pn.get(hub.root, "gpu")
    assert not pn.collector_approved(hub.root, p)
    res = pn.collect(hub.root, "gpu")
    assert res["error"] == "its collector is waiting for your approval" and res["data"] == {}
    rec = pn.approve_collector(hub.root, "gpu", via="cli")
    assert rec["study"] == "lab" and rec["checkpoint"] == "panel:gpu" and rec["sha"] == pn.collector_sha(p)
    res = pn.collect(hub.root, "gpu")
    assert res["data"]["gpu_hours"] == 12.5 and res["summary"] == "12 GPU-h over 3 jobs" and res["error"] is None
    (d / "collect.py").write_text(COLLECT.replace("12.5", "99"), encoding="utf-8")   # the script changed
    assert not pn.collector_approved(hub.root, pn.get(hub.root, "gpu"))
    res = pn.collect(hub.root, "gpu")
    assert res["stale"] and res["data"]["gpu_hours"] == 12.5 and "approval" in res["error"]   # last good data, marked
    approve(hub.root, "lab", "panel:gpu", "revoked", via="cli")
    pn.approve_collector(hub.root, "gpu")
    assert pn.collect(hub.root, "gpu")["data"]["gpu_hours"] == 99
    approve(hub.root, "lab", "panel:gpu", "revoked", via="cli")
    assert not pn.collector_approved(hub.root, pn.get(hub.root, "gpu"))


def test_a_shipped_collector_is_the_labs_own_code(pn, hub):
    assert pn.collector_approved(hub.root, pn.get(hub.root, "compute"))
    with pytest.raises(ValueError, match="no collector"):
        _panel(pn.lab_dir(hub.root), "plain", {"title": "Plain", "source": "registry"})
        pn.approve_collector(hub.root, "plain")


def test_collector_approval_can_bind_to_the_reviewed_version(pn, hub):
    folder = _panel(pn.lab_dir(hub.root), 'reviewed', {'title': 'Reviewed', 'collector': 'collect.py'},
                    collector=('collect.py', COLLECT))
    sha = pn.collector_sha(pn.get(hub.root, 'reviewed'))
    (folder/'collect.py').write_text(COLLECT.replace('12.5', '99'), encoding='utf-8')
    before = K.journal.events(hub.root)
    with pytest.raises(ValueError, match='collector changed'):
        pn.approve_collector(hub.root, 'reviewed', expected_sha=sha)
    assert K.journal.events(hub.root) == before
    current = pn.collector_sha(pn.get(hub.root, 'reviewed'))
    result = pn.approve_collector(hub.root, 'reviewed', expected_sha=current)
    assert result['sha'] == current
    assert pn.collect(hub.root, 'reviewed')['data']['gpu_hours'] == 99


def test_collector_api_shows_one_code_version_and_refuses_a_changed_review(pn, hub, monkeypatch):
    import hashlib
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api = load('dashboard/panels_api')
    monkeypatch.setattr(api.ctx, 'HUB', hub.root)
    monkeypatch.setattr(api, '_p', lambda: pn)
    folder = _panel(pn.lab_dir(hub.root), 'reviewed', {'title': 'Reviewed', 'collector': 'collect.py'},
                    collector=('collect.py', COLLECT))
    response, status = api.get_panel({'id': 'reviewed'})
    assert status == 200 and response['collector']['sha'] == hashlib.sha256((folder/'collect.py').read_bytes()).hexdigest()[:16]
    (folder/'collect.py').write_text(COLLECT.replace('12.5', '99'), encoding='utf-8')
    result, status = api.approve_collector({'id': 'reviewed', 'confirm': True, 'sha': response['collector']['sha']})
    assert status == 400 and 'collector changed' in result['error']
    assert not pn.collector_approved(hub.root, pn.get(hub.root, 'reviewed'))
    refreshed, _ = api.get_panel({'id': 'reviewed'})
    result, status = api.approve_collector({'id': 'reviewed', 'confirm': True, 'sha': refreshed['collector']['sha']})
    assert status == 200 and result['data']['data']['gpu_hours'] == 99


def test_collector_review_hash_matches_its_code_even_if_file_changes_during_the_read(pn, hub, monkeypatch):
    import hashlib
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api = load('dashboard/panels_api')
    monkeypatch.setattr(api.ctx, 'HUB', hub.root)
    monkeypatch.setattr(api, '_p', lambda: pn)
    folder = _panel(pn.lab_dir(hub.root), 'reviewed', {'title': 'Reviewed', 'collector': 'collect.py'},
                    collector=('collect.py', COLLECT))
    old = (folder/'collect.py').read_bytes()
    sha = pn.collector_sha
    def changed(panel):
        (folder/'collect.py').write_text(COLLECT.replace('12.5', '99'), encoding='utf-8')
        return sha(panel)
    monkeypatch.setattr(pn, 'collector_sha', changed)
    result, status = api.get_panel({'id': 'reviewed'})
    assert status == 200
    assert result['collector']['code'] == old.decode('utf-8')
    assert result['collector']['sha'] == hashlib.sha256(old).hexdigest()[:16]


def test_an_agent_run_cannot_approve_a_collector(pn, hub, monkeypatch):
    _panel(pn.lab_dir(hub.root), "gpu", {"title": "GPU", "collector": "collect.py"}, collector=("collect.py", COLLECT))
    monkeypatch.setenv("ARLOTOPE_RUN_ID", "hub-design-1")
    with pytest.raises(K.checkpoints.CheckpointError):
        pn.approve_collector(hub.root, "gpu")


def test_collector_edit_before_execution_is_rechecked(pn, hub, monkeypatch):
    folder = _panel(pn.lab_dir(hub.root), 'race', {'title': 'Race', 'collector': 'collect.py'}, collector=('collect.py', COLLECT))
    pn.approve_collector(hub.root, 'race')
    original = pn._run_collector
    def changed(*args):
        (folder/'collect.py').write_text(COLLECT.replace('12.5', '99'), encoding='utf-8')
        return original(*args)
    monkeypatch.setattr(pn, '_run_collector', changed)
    result = pn.collect(hub.root, 'race')
    assert 'waiting for your approval' in result['error'] and result['data'] == {}
    assert not list(folder.glob('.arlotope-collector-*'))


def test_collector_executes_the_checked_bytes_if_source_changes_at_launch(pn, hub, monkeypatch):
    folder = _panel(pn.lab_dir(hub.root), 'race', {'title': 'Race', 'collector': 'collect.py'}, collector=('collect.py', COLLECT))
    pn.approve_collector(hub.root, 'race')
    original = pn.subprocess.run
    seen = []
    def changed(command, **options):
        script = pn.Path(command[-1])
        assert script.parent == folder and script != folder/'collect.py'
        assert script.read_text(encoding='utf-8') == COLLECT
        seen.append(script)
        (folder/'collect.py').write_text(COLLECT.replace('12.5', '99'), encoding='utf-8')
        return original(command, **options)
    monkeypatch.setattr(pn.subprocess, 'run', changed)
    result = pn.collect(hub.root, 'race')
    assert result['data']['gpu_hours'] == 12.5 and result['error'] is None
    assert not pn.collector_approved(hub.root, pn.get(hub.root, 'race'))
    assert seen and not any(path.exists() for path in seen)


@pytest.mark.parametrize('suffix', ['.py', '.js', '.ps1', '.sh', '.bash', '.r'])
def test_collector_snapshot_keeps_language_parent_cwd_environment_and_cleans_up(pn, hub, monkeypatch, suffix):
    from types import SimpleNamespace
    folder = _panel(pn.lab_dir(hub.root), 'paths', {'title': 'Paths', 'collector': 'collect'+suffix}, collector=('collect'+suffix, COLLECT))
    pn.approve_collector(hub.root, 'paths')
    paths = []
    def run(command, **options):
        script = pn.Path(command[-1]);paths.append(script)
        assert script.suffix == suffix and script.parent == folder
        assert script.read_bytes() == (folder/('collect'+suffix)).read_bytes()
        assert options['cwd'] == str(hub.root)
        assert options['env']['ARLOTOPE_COLLECTOR'] == str((folder/('collect'+suffix)).resolve())
        assert options['env']['ARLOTOPE_STUDY'] == 'a-study' and 'ARLOTOPE_RUN_ID' not in options['env']
        return SimpleNamespace(returncode=0, stdout=b'{"ok":true}', stderr=b'')
    monkeypatch.setattr(pn.subprocess, 'run', run)
    assert pn.collect(hub.root, 'paths', 'a-study')['data'] == {'ok': True}
    assert paths and not any(path.exists() for path in paths)


@pytest.mark.parametrize('suffix', ['.py', '.js'])
def test_native_collector_keeps_sibling_resources_and_original_path(pn, hub, monkeypatch, tmp_path, suffix):
    if suffix == '.js' and not pn.shutil.which('node'):
        pytest.skip('Node is not installed')
    monkeypatch.setenv('ARLOTOPE_HOME', str(tmp_path/'user space 研究'))
    code = ('import json, os\nfrom pathlib import Path\nprint(json.dumps({'
            '"resource":Path(__file__).with_name("resource.txt").read_text(),'
            '"cwd":str(Path.cwd()),"original":os.environ["ARLOTOPE_COLLECTOR"]}))\n')
    if suffix == '.js':
        code = 'console.log(JSON.stringify({resource:require("fs").readFileSync(require("path").join(__dirname,"resource.txt"),"utf8"),cwd:process.cwd(),original:process.env.ARLOTOPE_COLLECTOR}));'
    folder = _panel(pn.user_dir(), 'paths', {'title': 'Paths', 'collector': 'collect'+suffix}, collector=('collect'+suffix, code))
    (folder/'resource.txt').write_text('sibling resource')
    pn.approve_collector(hub.root, 'paths')
    result = pn.collect(hub.root, 'paths')
    assert result['data'] == {'resource': 'sibling resource', 'cwd': str(hub.root), 'original': str((folder/('collect'+suffix)).resolve())}
    assert not list(folder.glob('.arlotope-collector-*'))


def test_collector_snapshot_is_removed_after_timeout(pn, hub, monkeypatch):
    folder = _panel(pn.lab_dir(hub.root), 'timeout', {'title': 'Timeout', 'collector': 'collect.py'}, collector=('collect.py', COLLECT))
    pn.approve_collector(hub.root, 'timeout')
    def run(command, **options):
        assert pn.Path(command[-1]).exists()
        raise pn.subprocess.TimeoutExpired(command, options['timeout'])
    monkeypatch.setattr(pn.subprocess, 'run', run)
    assert 'did not finish' in pn.collect(hub.root, 'timeout')['error']
    assert not list(folder.glob('.arlotope-collector-*'))


def test_shipped_collector_needs_no_write_access_to_its_installation(pn, hub, monkeypatch):
    folder = _panel(pn.lab_dir(hub.root), 'shipped', {'title': 'Shipped', 'collector': 'collect.py'}, collector=('collect.py', COLLECT))
    panel = pn.get(hub.root, 'shipped');panel['origin'] = 'shipped'
    def no_copy(**_kwargs):
        pytest.fail('A trusted shipped collector must not write to its installation.')
    monkeypatch.setattr(pn.tempfile, 'NamedTemporaryFile', no_copy)
    assert pn._run_collector(hub.root, panel)['data']['gpu_hours'] == 12.5
    assert not list(folder.glob('.arlotope-collector-*'))


def test_a_broken_collector_is_reported_not_raised(pn, hub):
    _panel(pn.lab_dir(hub.root), "broken", {"title": "Broken", "collector": "collect.py"},
           collector=("collect.py", "print('not json')\n"))
    pn.approve_collector(hub.root, "broken")
    assert "not JSON" in pn.collect(hub.root, "broken")["error"]
    (pn.lab_dir(hub.root) / "broken" / "collect.py").write_text("import sys\nsys.exit(4)\n", encoding="utf-8")
    pn.approve_collector(hub.root, "broken")
    assert "exited 4" in pn.collect(hub.root, "broken")["error"]


# ── summaries, alerts, refresh ────────────────────────────────────────────────────────────────────

def test_summary_of(pn):
    p = {"summary": "{a} and {b:.1f}"}
    assert pn.summary_of(p, {"a": 1, "b": 2.25}) == "1 and 2.2"
    assert pn.summary_of(p, {"summary": "the data's own line", "a": 1}) == "the data's own line"
    assert pn.summary_of(p, {"a": {"nested": 1}, "b": 2}) == "? and 2.0"            # nested values are not shown
    assert pn.summary_of({"summary": "{b:d}"}, {"b": "text"}) == ""                  # a bad format is no summary
    assert pn.summary_of({}, {"a": 1}) == "" and pn.summary_of(p, [1, 2]) == ""
    assert len(pn.summary_of({}, {"summary": "x" * 500})) == 200


def _alerting(pn, hub, pid="budget", study="idea-a"):
    data = {"summary": "over", "alerts": [{"level": "block", "say": "over the GPU budget", "study": study, "hold": True},
                                          {"level": "info"}]}
    _panel(pn.lab_dir(hub.root), pid, {"title": "Budget", "collector": "collect.py", "every": "30s"},
           collector=("collect.py", f"import json\nprint(json.dumps({data!r}))\n"))
    pn.approve_collector(hub.root, pid)


def test_refresh_due_collects_pinned_panels_and_raises_each_alert_once(pn, hub):
    _quiet(pn, hub)
    _alerting(pn, hub)
    seen = []
    assert pn.refresh_due(hub.root, on_alert=lambda p, a: seen.append(a)) == []      # not pinned: not collected
    pn.set_state(hub.root, "budget", pinned=["home"])
    assert pn.refresh_due(hub.root, on_alert=lambda p, a: seen.append(a)) == ["budget"]
    assert [a["say"] for a in seen] == ["over the GPU budget"]                         # an alert needs `say`
    assert "held" not in seen[0]                                                       # may_hold is off
    assert pn.refresh_due(hub.root, on_alert=lambda p, a: seen.append(a)) == []      # not due again yet
    st = json.loads((hub.lab / ".bus" / "panels" / "data" / "budget.json").read_text(encoding="utf-8"))
    st["epoch"] = time.time() - 120
    (hub.lab / ".bus" / "panels" / "data" / "budget.json").write_text(json.dumps(st), encoding="utf-8")
    assert pn.refresh_due(hub.root, on_alert=lambda p, a: seen.append(a)) == ["budget"]
    assert len(seen) == 1                                                              # the same alert: raised once
    items = pn.alert_items(hub.root)
    assert [(i["panel"], i["level"], i["hold"]) for i in items] == [("budget", "block", False)]
    pn.set_state(hub.root, "budget", archived=True)
    assert pn.alert_items(hub.root) == [] and pn.refresh_due(hub.root) == []


def test_an_alert_holds_a_study_only_when_the_pi_let_the_panel(pn, hub):
    _quiet(pn, hub)
    _alerting(pn, hub, study="idea-h")
    pn.set_state(hub.root, "budget", pinned=["dock"], may_hold=True)
    seen = []
    pn.refresh_due(hub.root, on_alert=lambda p, a: seen.append(a))
    assert seen[0]["held"] is True and pn.alert_items(hub.root)[0]["hold"] is True
    import executor
    from executor import pause
    h = pause.held(executor.Lab(hub.root), "idea-h")
    assert h and h["by"] == "panel" and "over the GPU budget" in h["reason"]


def test_snapshot_view_cards_carry_no_data(pn, hub):
    _quiet(pn, hub)
    _panel(pn.lab_dir(hub.root), "gpu", {"title": "GPU", "collector": "collect.py"}, collector=("collect.py", COLLECT))
    cards = {c["id"]: c for c in pn.snapshot_view(hub.root)["panels"]}
    assert cards["gpu"]["needs_approval"] is True and "data" not in cards["gpu"]
    assert cards["compute"]["needs_approval"] is False
    assert pn._gauge({"gauge": {"value": "3", "max": 10, "label": "GPUs"}}) == {"value": 3.0, "max": 10.0,
                                                                                "label": "GPUs", "tone": ""}
    assert pn._gauge({"gauge": {"value": "lots"}}) is None and pn._gauge([1]) is None


# ── saving ────────────────────────────────────────────────────────────────────────────────────────

def test_save_keeps_old_versions_and_validates(pn, hub):
    p = pn.save(hub.root, "notes-panel", {"title": "Notes", "source": "registry", "pinned": ["home"], "id": "x"},
                "<p>v1</p>")
    assert p["origin"] == "lab" and p["title"] == "Notes" and p["pinned"] == []      # its own fields are not taken
    d = pn.lab_dir(hub.root) / "notes-panel"
    assert "pinned" not in yaml.safe_load((d / "panel.yaml").read_text(encoding="utf-8"))
    pn.save(hub.root, "notes-panel", {"title": "Notes 2"}, "<p>v2</p>", collector=("collect.py", COLLECT))
    versions = list((d / "versions").iterdir())
    assert len(versions) == 1 and (versions[0] / "view.html").read_text(encoding="utf-8") == "<p>v1</p>"
    assert pn.view_html(hub.root, "notes-panel") == "<p>v2</p>"
    p = pn.get(hub.root, "notes-panel")
    assert p["collector"] == "collect.py" and p["sources"] == ["collector"] and not pn.collector_approved(hub.root, p)
    for bad in (dict(pid="Bad Id", definition={}), dict(pid="ok", definition=["x"]),
                dict(pid="ok", definition={}, collector=("run.exe", "x")), dict(pid="ok", definition={}, view="x" * 400_001)):
        with pytest.raises(ValueError):
            pn.save(hub.root, bad["pid"], bad["definition"], bad.get("view", ""), bad.get("collector"))
    mine = pn.save(hub.root, "mine", {"title": "Mine"}, "<p/>", where="user")
    assert mine["origin"] == "yours" and (pn.user_dir() / "mine" / "panel.yaml").is_file()


def test_the_panels_cli(pn, hub, capsys):
    _quiet(pn, hub)
    hub.add_registry_row("idea-a", state="seed")
    _panel(pn.lab_dir(hub.root), "studies-count", {"title": "Studies", "source": "registry", "summary": "{summary}"})
    assert pn.main(["--hub", str(hub.root), "list"]) == 0
    assert "studies-count" in capsys.readouterr().out
    assert pn.main(["--hub", str(hub.root), "show", "studies-count", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["studies"][0]["id"] == "idea-a"
    assert pn.main(["--hub", str(hub.root), "show", "nope"]) == 2


# ── the sandboxed view ────────────────────────────────────────────────────────────────────────────

def test_a_panel_view_is_composed_with_a_no_network_csp(hub, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    serve = load("dashboard/serve")
    monkeypatch.setattr(serve.ctx, "HUB", hub.root)
    monkeypatch.setattr(serve.ctx, "LAB", hub.lab)
    api = serve.panels_api
    html = api.compose_view("<div id=x>hello</div>")
    csp = html.split('http-equiv="Content-Security-Policy" content="', 1)[1].split('"', 1)[0]
    rules = {r.strip().split(" ", 1)[0]: r.strip().split(" ", 1)[1] for r in csp.split(";") if r.strip()}
    assert rules["default-src"] == "'none'" and rules["connect-src"] == "'none'" and rules["form-action"] == "'none'"
    assert rules["frame-src"] == "'none'" and rules["base-uri"] == "'none'"
    assert not any("http" in v or "*" in v or "'self'" in v for v in rules.values())   # nowhere to send data
    assert html.index("Content-Security-Policy") < html.index("<script>") and html.endswith("<div id=x>hello</div></body></html>")
    out, code = api.panel_view({"id": "compute"})
    assert code == 200 and "connect-src 'none'" in out["html"]
    assert api.panel_view({"id": "nope"})[1] == 404
    assert api.approve_collector({"id": "compute"})[1] == 400                        # needs confirm
