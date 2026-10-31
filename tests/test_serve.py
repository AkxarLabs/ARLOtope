"""Tests for dashboard/serve.py — the local control surface (NO server bind).

serve.py does `import sources` at module load (it inserts dashboard/ on sys.path). We call the
pure functions directly. serve resolves project/control paths through `sources`, so we override
the dashboard's shared state (ctx.HUB / ctx.LAB), which serve and sources both read. No socket is ever bound.
"""

from __future__ import annotations

import pytest

from conftest import REPO, load


def _mod(hub, monkeypatch):
    # Ensure `import sources` inside serve.py resolves to the real dashboard/sources.py.
    monkeypatch.syspath_prepend(str(REPO / "dashboard"))
    m = load("dashboard/serve")
    monkeypatch.setattr(m.ctx, "HUB", hub.root)
    monkeypatch.setattr(m.ctx, "LAB", hub.lab)
    # serve holds a reference to the sources module — patch its globals too.
    monkeypatch.setattr(m.ctx, "HUB", hub.root)
    monkeypatch.setattr(m.ctx, "LAB", hub.lab)
    return m


@pytest.mark.parametrize('raw', [b'{', b'\xff', b'[' * 2000 + b'0' + b']' * 2000,
                               b'{"n":' + b'9' * 5000 + b'}', b'[]', b'null'])
def test_invalid_post_body_is_rejected_before_dispatch(hub, monkeypatch, raw):
    m = _mod(hub, monkeypatch)
    handler = object.__new__(m.Handler)
    handler.path = '/test'
    handler._raw_body = lambda: raw
    sent, calls = [], []
    handler._json = lambda body, code=200: sent.append((body, code))
    monkeypatch.setattr(m, 'POST_ROUTES', {'/test': lambda body: (calls.append(body) or {'ok': True}, 200)})
    handler._dispatch_post()
    assert sent[0][1] == 400 and sent[0][0].get('error')
    assert calls == []


@pytest.mark.parametrize('raw, expected', [(b'', {}), (b'{}', {}), (b'{"note":"Hello"}', {'note': 'Hello'})])
def test_valid_and_empty_post_bodies_keep_their_existing_contract(hub, monkeypatch, raw, expected):
    m = _mod(hub, monkeypatch)
    handler = object.__new__(m.Handler)
    handler.path = '/test'
    handler._raw_body = lambda: raw
    sent, calls = [], []
    handler._json = lambda body, code=200: sent.append((body, code))
    monkeypatch.setattr(m, 'POST_ROUTES', {'/test': lambda body: (calls.append(body) or {'ok': True}, 200)})
    handler._dispatch_post()
    assert calls == [expected] and sent == [({'ok': True}, 200)]


def test_empty_lab_snapshot_includes_machine_choices(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    monkeypatch.setattr(m.sources, 'parse_registry', lambda: [])
    snapshot = m.sources.snapshot()
    assert snapshot['cold'] and snapshot['items'] == []
    assert snapshot['machines'][0]['id'] == 'local'


@pytest.mark.parametrize('dashboard',[False,True])
def test_local_servers_bind_without_dns_and_own_their_port(hub,monkeypatch,dashboard):
    import socket
    from loopback_http import LoopbackHTTPServer
    m=_mod(hub,monkeypatch)
    def unavailable_dns(*args):
        raise AssertionError('Local server startup must not resolve a hostname')
    monkeypatch.setattr(socket,'getfqdn',unavailable_dns)
    assert 'ssh -N -L' in load('arlo.py').tunnel_hint(8787)
    server_type=m.LabServer if dashboard else LoopbackHTTPServer
    server=server_type(('127.0.0.1',0),m.Handler)
    try:
        assert server.server_name=='127.0.0.1' and server.server_port==server.server_address[1]
        with pytest.raises(OSError):
            server_type(server.server_address,m.Handler)
    finally:
        server.server_close()


def test_acp_command_setting_survives_snapshot(hub, monkeypatch):
    import json
    import sys
    m = _mod(hub, monkeypatch)
    command = [sys.executable, str(REPO / 'tests/fake_acp.py')]
    result, code = m.settings.set_executor_config({'confirm': True, 'changes': {
        'backend': 'acp', 'acp_command': json.dumps(command)}})
    assert code == 200 and result['ok'], result
    assert m.settings.attention.executor_status()['config']['acp_command'] == command


def test_snapshot_refreshes_task_slots_without_reprobing_agents(hub, monkeypatch):
    import time
    attention = _mod(hub, monkeypatch).settings.attention
    runs = [{'status': 'running'}, {'status': 'running', 'role': 'reviewer'},
            {'status': 'waiting_input', 'pid': 42}]
    monkeypatch.setattr(attention, '_EXEC_CACHE', {
        'ts': time.time(), 'key': str(hub.root), 'value': {'clis': {}, 'slots_used': 99}})
    monkeypatch.setattr(attention.executor, 'all_runs', lambda _lab: [(None, run) for run in runs])
    monkeypatch.setattr(attention.executor, 'health', lambda _lab: pytest.fail('CLI probe was cached'))
    result = attention.executor_status()
    assert result['active'] == 3 and result['slots_used'] == 2 and result['waiting'] == 1
    runs[0]['status'] = 'completed'
    runs[1]['status'] = 'completed'
    runs[2]['pid'] = None
    result = attention.executor_status()
    assert result['active'] == result['slots_used'] == 0 and result['waiting'] == 1


def test_optional_module_is_served_as_javascript(hub, monkeypatch, tmp_path):
    m=_mod(hub,monkeypatch)
    path=tmp_path/'vendor/example/module.mjs'
    path.parent.mkdir(parents=True)
    path.write_text('export const test = 1;',encoding='utf-8')
    monkeypatch.setattr(m,'STATIC',tmp_path)
    handler=object.__new__(m.Handler)
    sent=[]
    handler._send=lambda *args:sent.append(args)
    handler._serve_static('vendor/example/module.mjs')
    assert sent[0][0]==200 and sent[0][2].startswith('application/javascript')


def test_static_revalidation_keeps_edits_visible_and_preserves_renderer_isolation(hub,monkeypatch,tmp_path):
    m=_mod(hub,monkeypatch)
    asset=tmp_path/'example.js';asset.write_text('version one',encoding='utf-8')
    monkeypatch.setattr(m,'STATIC',tmp_path)
    handler=object.__new__(m.Handler);handler.headers={};sent=[]
    handler._send=lambda *args:sent.append(args)
    handler._serve_static('example.js')
    first=sent[-1];assert first[0]==200 and first[3]['Cache-Control']=='no-cache'
    handler.headers={'If-None-Match':first[3]['ETag']}
    handler._serve_static('example.js')
    assert sent[-1][0]==304 and sent[-1][1]==b''
    assert int(sent[-1][3]['Content-Length'])==len(first[1])
    asset.write_text('version two',encoding='utf-8');handler._serve_static('example.js')
    assert sent[-1][0]==200 and sent[-1][1]==b'version two' and sent[-1][3]['ETag']!=first[3]['ETag']


def test_api_responses_remain_uncached(hub,monkeypatch):
    import io
    m=_mod(hub,monkeypatch);handler=object.__new__(m.Handler);headers={}
    handler.send_response=lambda code:None
    handler.send_header=lambda key,value:headers.update({key:value})
    handler.end_headers=lambda:None
    handler.command='GET';handler.wfile=io.BytesIO()
    handler._json({'private':'study data'})
    assert headers['Cache-Control']=='no-store' and 'ETag' not in headers


def test_renderer_is_opaque_and_static_modules_allow_its_origin(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    handler = object.__new__(m.Handler)
    handler.path = '/static/lab-view.html?embedded=1'
    sent = []
    handler._send = lambda *args: sent.append(args)
    handler._serve_static('lab-view.html')
    csp = sent[-1][3]['Content-Security-Policy']
    assert csp.startswith('sandbox allow-scripts;') and 'allow-same-origin' not in csp
    assert "connect-src 'none'" in csp and "form-action 'none'" in csp and "default-src 'none'" in csp
    handler._serve_static('vendor/three/three.module.min.js')
    assert sent[-1][3]['Access-Control-Allow-Origin'] == '*'


def test_direct_room_preview_opens_the_dashboard_owner(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    handler = object.__new__(m.Handler)
    handler.path = '/static/lab-view.html?roomdraft=study-123'
    handler.headers = {'Host': '127.0.0.1:8787'}
    sent = []
    handler._send = lambda *args: sent.append(args)
    handler._serve_static('lab-view.html')
    assert sent[-1][0] == 302
    assert sent[-1][3]['Location'] == '/?roomdraft=study-123'
    handler.headers['Origin'] = 'null'
    handler._serve_static('lab-view.html')
    assert sent[-1][0] == 403




# ── run_tool whitelist ────────────────────────────────────────────────────────

def test_run_tool_rejects_non_whitelisted(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    res = m.labtools.run_tool("rm_rf")
    assert "error" in res
    assert "whitelist" in res["error"]


def test_safe_tools_set_is_read_only(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    assert "check_lab" in m.labtools.SAFE_TOOLS
    # nothing that trains/writes
    assert "run" not in m.labtools.SAFE_TOOLS and "sweep" not in m.labtools.SAFE_TOOLS


# ── checkpoint decisions (dashboard/decisions.py) ───────────────────────────

def _records(hub):
    from conftest import kernel
    return kernel().journal.approvals(hub.root)


def test_a_decision_is_a_record_and_writes_no_document(hub, monkeypatch):
    """Approving appends one record to the journal (lab/journal.jsonl); the proposal is left exactly as it was."""
    m = _mod(hub, monkeypatch)
    prop = hub.root / "studies" / "demo" / "proposal.md"
    prop.parent.mkdir(parents=True, exist_ok=True)
    prop.write_text("# Proposal\n", encoding="utf-8", newline="")
    hub.add_registry_row("demo", state="proposal")
    out, code = m.decisions.decide({"study": "demo", "checkpoint": "approve-proposal", "confirm": True})
    assert code == 200, out
    assert prop.read_bytes() == b"# Proposal\n"
    recs = _records(hub)
    assert len(recs) == 1 and recs[0]["study"] == "demo" and recs[0]["checkpoint"] == "approve-proposal"
    assert recs[0]["workflow"] == "research" and recs[0]["by"] == "pi" and recs[0]["via"] == "dashboard"


def test_approving_twice_is_two_records_and_the_latest_wins(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    hub.add_registry_row("demo", state="proposal")
    body = {"study": "demo", "checkpoint": "approve-proposal", "confirm": True}
    m.decisions.decide(dict(body))
    m.decisions.decide(dict(body, decision="revoked"))
    assert [r["decision"] for r in _records(hub)] == ["approved", "revoked"]
    assert not m.ctx.tool("kernel").journal.approved(hub.root, "demo", "approve-proposal")


def test_a_checkpoint_that_asks_for_typing_needs_the_studys_name(hub, monkeypatch):
    """A checkpoint with `confirm: type` is approved only when the study's name is typed."""
    import shutil
    import yaml
    m = _mod(hub, monkeypatch)
    shutil.copytree(REPO / "workflow", hub.root / "workflow")
    wf = hub.root / "workflow" / "workflows" / "research.yaml"
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    next(c for c in doc["checkpoints"] if c["id"] == "finalize-paper")["confirm"] = "type"
    wf.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    hub.add_registry_row("demo", state="internal-review")
    body = {"study": "demo", "checkpoint": "finalize-paper", "confirm": True}
    out, code = m.decisions.decide(dict(body, typed="other"))
    assert code == 400 and "type the study's name" in out["error"]
    assert m.decisions.decide(dict(body, typed="demo"))[1] == 200


def test_seed_escape_neutralizes_script_break():
    # H1: the inline-seed escape turns "</script>" into "<\/script>" so a snapshot string can't break
    # out of the <script> element. (Mirrors serve._serve_index's one-line defense.)
    import json
    seed = json.dumps({"detail": "</script><script>alert(1)</script>"}).replace("</", "<\\/")
    assert "</script>" not in seed and "<\\/script>" in seed


# ── paper artifacts (compiled PDF + figures) — read-only binary views ──────────

def _make_paper(hub, slug="demo", figures=None):
    pdir = hub.root / "studies" / slug / "paper"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "main.pdf").write_bytes(b"%PDF-1.5\nbody\n")
    (pdir / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    if figures:
        fdir = pdir / "figures"
        fdir.mkdir(exist_ok=True)
        for name, data in figures.items():
            (fdir / name).write_bytes(data)
    return pdir


def test_paper_pdf_found_and_missing(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    assert m.library.paper_pdf("demo") is None        # nothing compiled yet
    _make_paper(hub)
    f = m.library.paper_pdf("demo")
    assert f is not None and f.name == "main.pdf"


def test_figure_list_filters_by_extension(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _make_paper(hub, figures={"loss.png": b"\x89PNG", "tab.tex": b"x", "diagram.pdf": b"%PDF"})
    figs = m.library.figure_list("demo")
    assert "loss.png" in figs and "diagram.pdf" in figs
    assert "tab.tex" not in figs              # .tex is not a servable figure


def test_figure_file_blocks_path_traversal(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _make_paper(hub, figures={"loss.png": b"\x89PNG"})
    assert m.library.figure_file("demo", "loss.png") is not None
    # any traversal attempt is reduced to a basename that doesn't exist in figures/ -> None
    assert m.library.figure_file("demo", "../../../etc/passwd") is None
    assert m.library.figure_file("demo", "../control.yaml") is None


def test_read_doc_checkpoint_carries_its_evidence(hub, monkeypatch):
    """The checkpoint document: each evidence file of the checkpoint, with an editor path when it exists."""
    m = _mod(hub, monkeypatch)
    prop = hub.root / "studies" / "demo" / "proposal.md"
    prop.parent.mkdir(parents=True, exist_ok=True)
    prop.write_text("# Proposal\n\n## 5. Budget\n\n- 10 GPU-h\n", encoding="utf-8")
    res = m.review.read_doc("checkpoint", "demo", checkpoint="approve-proposal")
    assert res["ok"] and res["title"].startswith("Approve the proposal")
    sec = next(s for s in res["sections"] if s["title"].endswith("proposal.md"))
    assert sec["path"].endswith("proposal.md") and "10 GPU-h" in sec["text"]
    lit = next(s for s in res["sections"] if s["title"].endswith("lit-review.md"))
    assert lit["text"] == "(not written yet)" and "path" not in lit
    assert "error" in m.review.read_doc("checkpoint", "demo", checkpoint="nope")
    assert "error" in m.review.read_doc("checkpoint", "../x", checkpoint="approve-proposal")
    assert "error" in m.review.read_doc("gate", "demo", 1)                  # the gate bundles are gone


def test_read_doc_checkpoint_reads_a_folder_of_reviews(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    paper = hub.root / "studies" / "demo" / "paper"
    (paper / "reviews" / "critique-2026-06-27").mkdir(parents=True, exist_ok=True)
    (paper / "claims.yaml").write_text("claims: []\n", encoding="utf-8")
    (paper / "reviews" / "critique-2026-06-27" / "meta-review.md").write_text("# Meta\n\n## Decision\n\n**accept**\n",
                                                                             encoding="utf-8")
    (paper / "main.pdf").write_bytes(b"%PDF-1.4")
    res = m.review.read_doc("checkpoint", "demo", checkpoint="finalize-paper")
    titles = [s["title"] for s in res["sections"]]
    assert any(t.endswith("meta-review.md") for t in titles)               # found inside the folder
    assert any(t.endswith("claims.yaml") for t in titles)
    pdf = next(s for s in res["sections"] if s["title"].endswith("main.pdf"))
    assert "open it from the Library" in pdf["text"]


def test_read_doc_knowledge_includes_references(hub, monkeypatch):
    # The hub fixture seeds all four knowledge files; the knowledge view must surface REFERENCES
    # (the shared reading index) alongside the three triggered-operator files.
    m = _mod(hub, monkeypatch)
    titles = [s["title"] for s in m.review.read_doc("knowledge")["sections"]]
    assert {"Findings", "Failures", "Open Questions", "References"} <= set(titles)


# ── claims ↔ artifact map ─────────────────────────────────────────────────────

def test_claims_map_resolves_and_marks_linkage(hub, monkeypatch):
    import json
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    hub.add_registry_row("demo", state="writing", project=str(proj))
    art = proj / "runs" / "r0" / "metrics.json"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps({"val_acc": 0.91}), encoding="utf-8")
    paper = hub.root / "studies" / "demo" / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "claims.yaml").write_text(
        "claims:\n"
        "  - id: C001\n    claim: ours hits 0.91\n    numbers: ['0.91']\n    metric: val_acc\n"
        "    location: Table 2\n    project: demo\n    artifacts:\n      - runs/r0/metrics.json\n"
        "  - id: C002\n    claim: missing one\n    numbers: ['1.0']\n    project: demo\n"
        "    artifacts:\n      - runs/ghost/metrics.json\n", encoding="utf-8")
    res = m.review.claims_map("demo")
    assert res["n"] == 2
    c1 = res["claims"][0]
    assert c1["id"] == "C001" and c1["linked"] is True
    a = c1["artifacts"][0]
    assert a["exists"] is True and a["run_id"] == "r0" and a["project"] == "demo" and a["abs"].endswith("metrics.json")
    c2 = res["claims"][1]
    assert c2["linked"] is False and c2["artifacts"][0]["exists"] is False


def test_claims_map_missing_file_errors(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    res = m.review.claims_map("demo")
    assert "error" in res and "claims.yaml" in res["error"]


def test_run_tool_audit_claims_whitelisted_needs_slug(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    assert "audit_claims" in m.labtools.SAFE_TOOLS          # read-only audit is allowed
    res = m.labtools.run_tool("audit_claims", "")
    assert "error" in res and "slug" in res["error"]


# ── claims_map hardening (from the adversarial review) ────────────────────────

def test_claims_map_coerces_scalar_artifacts_and_numbers(hub, monkeypatch):
    import json
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    art = proj / "runs" / "r0" / "metrics.json"
    art.parent.mkdir(parents=True, exist_ok=True)
    art.write_text(json.dumps({"val_acc": 0.91}), encoding="utf-8")
    paper = hub.root / "studies" / "demo" / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "claims.yaml").write_text(
        "claims:\n  - just a bare string\n"            # non-dict list item → skipped
        "  - id: C001\n    numbers: '0.91'\n    artifacts: runs/r0/metrics.json\n    project: demo\n",
        encoding="utf-8")
    res = m.review.claims_map("demo")
    assert res["n"] == 1                               # the bare string is not a claim
    c = res["claims"][0]
    assert c["numbers"] == ["0.91"]                    # scalar coerced — NOT split into characters
    assert len(c["artifacts"]) == 1                    # scalar coerced — NOT 20 single-char rels
    a = c["artifacts"][0]
    assert a["rel"] == "runs/r0/metrics.json" and a["exists"] is True and a["run_id"] == "r0"


def test_claims_map_tolerates_non_dict_toplevel(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    paper = hub.root / "studies" / "demo" / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "claims.yaml").write_text("just a bare scalar\n", encoding="utf-8")
    res = m.review.claims_map("demo")                          # must not raise AttributeError
    assert res["ok"] is True and res["n"] == 0


def test_claims_map_blocks_artifact_traversal(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    proj = hub.make_project("demo")
    (proj.parent / "secret.json").write_text("{}", encoding="utf-8")   # a real file OUTSIDE the project
    paper = hub.root / "studies" / "demo" / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    (paper / "claims.yaml").write_text(
        "claims:\n  - id: C001\n    project: demo\n    artifacts:\n      - ../secret.json\n", encoding="utf-8")
    a = m.review.claims_map("demo")["claims"][0]["artifacts"][0]
    assert a["exists"] is False and "abs" not in a     # escapes the project → never surfaced


# ── the Library (tree + document reader) ──────────────────────────────────────

def _lib_hub(hub):
    """Populate the fake hub with the doc set the Library organizes."""
    (hub.lab / "ideation").mkdir(parents=True, exist_ok=True)
    (hub.lab / "ideation" / "2026-07-01-101010-slm.md").write_text("# worksheet\n", encoding="utf-8")
    hub.notebook_entry("2026-07-01-session.md", "# nb\n")
    sdir = hub.root / "studies" / "demo"
    (sdir / "sessions").mkdir(parents=True, exist_ok=True)
    (sdir / "critiques").mkdir(parents=True, exist_ok=True)
    (sdir / "paper" / "reviews").mkdir(parents=True, exist_ok=True)
    (sdir / "IDEA.md").write_text("# idea\n", encoding="utf-8")
    (sdir / "proposal.md").write_text("# proposal\n\n$E=mc^2$\n", encoding="utf-8")
    (sdir / "sessions" / "2026-07-02-scope.md").write_text("# scope session\n", encoding="utf-8")
    (sdir / "critiques" / "novelty.md").write_text("# critique\n", encoding="utf-8")
    (sdir / "paper" / "claims.yaml").write_text("claims: []\n", encoding="utf-8")
    (sdir / "paper" / "reviews" / "review-1.md").write_text("# review\n", encoding="utf-8")
    return sdir


def test_lib_tree_lab_layer_above_studies(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _lib_hub(hub)
    proj = hub.make_project("demo")
    (proj / "PLAN.md").write_text("# plan\n", encoding="utf-8")
    (proj / "EXPERIMENT_LOG.md").write_text("# log\n", encoding="utf-8")
    hub.add_registry_row("demo", title="Demo study", state="active", project=str(proj))
    tree = m.library.lib_tree()
    assert tree["ok"] is True
    keys = [g["key"] for g in tree["groups"]]
    assert keys[0] == "lab"                              # ideation/knowledge/notebook sit ABOVE projects
    assert "study:demo" in keys
    lab = tree["groups"][0]
    sec_titles = [s["title"] for s in lab["sections"]]
    assert "Ideation (pre-project)" in sec_titles and "Knowledge" in sec_titles and "Notebook" in sec_titles
    ideation = next(s for s in lab["sections"] if s["title"].startswith("Ideation"))
    assert any(d["rel"] == "ideation/2026-07-01-101010-slm.md" for d in ideation["docs"])
    study = next(g for g in tree["groups"] if g["key"] == "study:demo")
    assert study["title"] == "Demo study" and study["state"] == "active"
    stitles = [s["title"] for s in study["sections"]]
    assert stitles[:1] == ["Study"]                      # study docs before the project ledgers
    assert "Sessions" in stitles and "Critiques" in stitles and "Reviews" in stitles
    assert "Project repo" in stitles
    core = next(s for s in study["sections"] if s["title"] == "Study")
    assert [d["rel"] for d in core["docs"]][:2] == ["IDEA.md", "proposal.md"]   # lifecycle order
    prepo = next(s for s in study["sections"] if s["title"] == "Project repo")
    rels = [d["rel"] for d in prepo["docs"]]
    assert rels[:2] == ["PLAN.md", "EXPERIMENT_LOG.md"]  # ledger order, scope=project
    assert all(d["scope"] == "project" for d in prepo["docs"])


def test_lib_tree_includes_unregistered_study_dirs(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _lib_hub(hub)                                        # demo study exists but has NO registry row
    tree = m.library.lib_tree()
    assert any(g["key"] == "study:demo" for g in tree["groups"])


def test_lib_doc_reads_markdown_with_meta(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _lib_hub(hub)
    d = m.library.lib_doc("study", "demo", "proposal.md")
    assert d["ok"] is True and d["format"] == "markdown"
    assert "E=mc^2" in d["text"] and d["title"] == "proposal.md"
    assert d["path"].endswith("proposal.md") and d["mtime"] > 0


def test_lib_doc_blocks_traversal_and_absolute(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    _lib_hub(hub)
    (hub.root / "secret.md").write_text("no\n", encoding="utf-8")
    assert "outside" in m.library.lib_doc("study", "demo", "../../secret.md")["error"]
    assert "outside" in m.library.lib_doc("lab", None, "../secret.md")["error"]
    # an absolute rel is treated as relative-or-refused, never a free read
    res = m.library.lib_doc("study", "demo", str(hub.root / "secret.md"))
    assert "error" in res
    assert m.library.lib_doc("study", "demo", "IDEA.md")["ok"] is True   # sanity: legit reads still work


def test_lib_doc_extension_whitelist(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    sdir = _lib_hub(hub)
    (sdir / "tool.exe").write_bytes(b"MZ")
    res = m.library.lib_doc("study", "demo", "tool.exe")
    assert "error" in res and ".exe" in res["error"]


def test_lib_doc_unknown_scope_or_slug(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    assert "error" in m.library.lib_doc("nope", None, "x.md")
    assert "error" in m.library.lib_doc("study", "no-such", "IDEA.md")
    assert "error" in m.library.lib_doc("study", "../demo", "IDEA.md")   # slug is sanitized, not a path


def test_lib_file_serves_contained_images_only(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    sdir = _lib_hub(hub)
    fig = sdir / "paper" / "figures" / "f1.png"
    fig.parent.mkdir(parents=True, exist_ok=True)
    fig.write_bytes(b"\x89PNG\r\n")
    hit = m.library.lib_file("study", "demo", "paper/figures/f1.png")
    assert hit and hit[0].name == "f1.png" and hit[1] == "image/png"
    assert m.library.lib_file("study", "demo", "../../secret.png") is None      # traversal
    assert m.library.lib_file("study", "demo", "proposal.md") is None           # not an image


# ── write-path hardening: client-supplied ids must never become path traversal ─

def test_decide_rejects_traversal_and_non_string_study(hub, monkeypatch):
    m = _mod(hub, monkeypatch)
    for bad in ("../evil", "..", "a/b", r"a\b", ".hidden", "", "  ", 123, ["x"], {"a": 1}, None):
        out, code = m.decisions.decide({"study": bad, "checkpoint": "approve-proposal", "confirm": True})
        assert code == 400, f"{bad!r} was not rejected"
    for bad in ("../x", "a/b", 5):
        assert m.decisions.decide({"study": "demo", "checkpoint": bad, "confirm": True})[1] == 400
    assert _records(hub) == []
    assert not (hub.root / "evil").exists() and not (hub.root.parent / "evil").exists()


def test_bus_append_rejects_traversal_target(hub, monkeypatch):
    import pytest
    m = _mod(hub, monkeypatch)
    for bad in ("../evil", "a/b", ".hidden"):
        with pytest.raises(ValueError):
            m.bus.append_directive(bad, "hello")
    # a non-string target must also raise ValueError (not AttributeError)
    with pytest.raises(ValueError):
        m.bus.append_directive(123, "hello")
    # the happy paths still work: hub and a bare slug (pre-spawn -> hub-bus fallback)
    assert m.bus.append_directive("hub", "hi")["target"] == "hub"
    assert m.bus.append_directive("demo", "hi")["target"] == "demo"
    assert (hub.lab / ".bus" / "directives.jsonl").exists()


def _read_jsonl(path):
    import json
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]


def test_withdraw_routes_to_the_bus_holding_the_ref(hub, monkeypatch):
    # A directive aimed at a pre-spawn idea lands on the HUB bus (fallback). If the project is
    # spawned before the PI withdraws it, the withdraw must land NEXT TO the record on the hub
    # bus — not on the project bus the target now resolves to (where the ref would never match
    # and the directive would stay pending forever).
    m = _mod(hub, monkeypatch)
    rec = m.bus.append_directive("demo", "do the thing")     # no project dir yet -> hub bus
    hub.make_project("demo")                             # now the project exists
    m.bus.append_withdraw("demo", rec["id"], rec["ts"])
    hub_lines = _read_jsonl(hub.lab / ".bus" / "directives.jsonl")
    assert any(r.get("kind") == "withdraw" and r.get("ref") == rec["id"] for r in hub_lines)
    proj_bus = hub.projects_root / "demo" / ".bus" / "directives.jsonl"
    assert not proj_bus.exists()   # nothing strayed onto the project bus


def test_withdraw_disambiguates_colliding_ids_by_ts(hub, monkeypatch):
    # d-NNN ids are per-bus counters, so the hub and project bus both hold a d-001. A pre-spawn
    # hub record and a post-spawn project record are separated in time (the spawn happens between),
    # so their ts differ — withdrawing the hub record by its ts must mark the HUB d-001, never the
    # unrelated project d-001. Records written directly so the ts are controlled/distinct.
    m = _mod(hub, monkeypatch)
    hub_bus = hub.lab / ".bus"; hub_bus.mkdir(parents=True, exist_ok=True)
    (hub_bus / "directives.jsonl").write_text(
        '{"text": "pre-spawn", "id": "d-001", "ts": "2026-06-01T09:00:00", "target": "demo"}\n',
        encoding="utf-8")
    pbus = hub.make_project("demo") / ".bus"; pbus.mkdir(parents=True, exist_ok=True)
    (pbus / "directives.jsonl").write_text(
        '{"text": "post-spawn", "id": "d-001", "ts": "2026-06-20T14:00:00", "target": "demo"}\n',
        encoding="utf-8")
    m.bus.append_withdraw("demo", "d-001", "2026-06-01T09:00:00")   # the HUB record's ts
    hub_lines = _read_jsonl(hub_bus / "directives.jsonl")
    proj_lines = _read_jsonl(pbus / "directives.jsonl")
    assert any(r.get("kind") == "withdraw" for r in hub_lines)          # landed on the hub bus
    assert not any(r.get("kind") == "withdraw" for r in proj_lines)     # NOT the project's d-001


@pytest.mark.parametrize('scope', ['hub', 'project'])
def test_scoped_withdraw_disambiguates_identical_ids_and_timestamps(hub, monkeypatch, scope):
    import json
    m = _mod(hub, monkeypatch)
    hub.add_registry_row('demo', state='proposal')
    hub_bus = hub.lab / '.bus'
    project_bus = hub.make_project('demo') / '.bus'
    for bus in (hub_bus, project_bus):
        bus.mkdir(parents=True, exist_ok=True)
        (bus / 'directives.jsonl').write_text(json.dumps({'id': 'd-001', 'ts': '2026-10-19T10:00:00',
            'target': 'demo', 'text': str(bus)}) + '\n', encoding='utf-8')
    out, code = m.bus.withdraw_post({'target': 'demo', 'id': 'd-001', 'ts': '2026-10-19T10:00:00', 'scope': scope})
    assert code == 200 and out['ok']
    for name, bus in [('hub', hub_bus), ('project', project_bus)]:
        assert any(r.get('kind') == 'withdraw' for r in _read_jsonl(bus / 'directives.jsonl')) == (name == scope)
    assert m.bus.withdraw_post({'target': 'demo', 'id': 'd-001', 'scope': '../elsewhere'})[1] == 400


def test_withdraw_falls_back_to_target_bus_for_unknown_ref(hub, monkeypatch):
    # an unknown ref (e.g. a synthesized d?xxxx id) keeps the original target routing
    m = _mod(hub, monkeypatch)
    hub.make_project("demo")
    m.bus.append_withdraw("demo", "d?deadbeef")
    proj_lines = _read_jsonl(hub.projects_root / "demo" / ".bus" / "directives.jsonl")
    assert any(r.get("kind") == "withdraw" and r.get("ref") == "d?deadbeef" for r in proj_lines)


def test_withdraw_of_legacy_nonslug_target_does_not_raise(hub, monkeypatch):
    # a hand-written directive with a non-slug target (spaces) must still be withdrawable — the
    # ref is located on the hub bus, so the withdraw routes there without a slug-validation raise.
    m = _mod(hub, monkeypatch)
    bus = hub.lab / ".bus"; bus.mkdir(parents=True, exist_ok=True)
    (bus / "directives.jsonl").write_text(
        '{"text": "legacy", "id": "d-009", "ts": "2026-01-01T00:00:00", "target": "the econ project"}\n',
        encoding="utf-8")
    m.bus.append_withdraw("the econ project", "d-009", "2026-01-01T00:00:00")   # must NOT raise
    hub_lines = _read_jsonl(bus / "directives.jsonl")
    assert any(r.get("kind") == "withdraw" and r.get("ref") == "d-009" for r in hub_lines)
