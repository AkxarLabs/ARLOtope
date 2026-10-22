"""The dashboard UI (dashboard/static/ui/) — static checks that need no browser.

Every file parses; the page loads Preact/htm before the UI and the UI after the world; every `NL.x` the
UI uses is defined by some UI file (a typo'd helper would otherwise only fail on click); every API path
the UI calls exists on the server; day and night define the same colour tokens; the retired files stay
retired and the vendored libraries carry their licences.
"""

from __future__ import annotations

import re
import shutil
import json
import subprocess
import sys

import pytest

from conftest import REPO, load

STATIC = REPO / "dashboard" / "static"
UI = STATIC / "ui"
NODE = shutil.which("node")
UI_ORDER = ["workflow-default", "core", "components", "tags", "instruments", "runs", "terminal", "composer", "campaign", "checkpoint", "panels", "library", "knowledge", "artifacts", "answers", "studies", "workflow", "compose", "workflow-canvas", "assistant", "room-design", "home", "settings", "setup", "machines", "demo", "starter", "agents", "app"]


def _js():
    return {f.stem: f.read_text(encoding="utf-8") for f in sorted(UI.glob("*.js"))}


@pytest.mark.skipif(not NODE, reason="node is needed to parse the UI")
@pytest.mark.parametrize("name", UI_ORDER + ["../world3d/" + n for n in ("world", "model", "layout", "kit", "newt", "components")])
def test_every_ui_file_parses(name):
    r = subprocess.run([NODE, "--check", str(UI / f"{name}.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_script_order():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    order = ["vendor/preact/preact.umd.js", "vendor/preact/hooks.umd.js", "vendor/preact/htm.umd.js",
             ] + [f"ui/{n}.js" for n in UI_ORDER]
    pos = [html.index(o) for o in order]
    assert pos == sorted(pos), order
    assert set(_js()) == set(UI_ORDER) | {'lab-view'}, "every ui/*.js is loaded, in order"
    assert "ui/ui.css" in html and 'id="app"' in html and 'id="scene"' not in html


def test_every_NL_name_used_is_defined():
    src = _js()
    allsrc = "\n".join(src.values())
    # Shared workspace components use N as a local alias of window.NL.
    defined = set(re.findall(r"\b(?:NL|N)\.([A-Za-z_]\w*)\s*=(?!=)", allsrc))
    # Object.assign(NL, { h, render, … , ...H }) in core.js + the preact hooks spread into NL
    m = re.search(r"Object\.assign\(NL, \{([^}]*)\}\)", src["core"])
    defined |= {x.strip() for x in m.group(1).split(",") if x.strip() and not x.strip().startswith("...")}
    defined |= {"useState", "useEffect", "useRef", "useMemo", "useReducer", "useCallback", "useLayoutEffect", "useContext"}
    used = set(re.findall(r"\bNL\.([A-Za-z_]\w*)", allsrc))
    missing = sorted(used - defined)
    assert not missing, f"used but never defined: {missing}"


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_procedure_menus_use_the_studys_workflow_and_instruction_only_override():
    source = _js()['core']
    logic = source[source.index('NL.doesFor ='):source.index('// what a study should run next:')]
    script = f"""const NL={{STEPS:{{task:{{do:'write-paper',also:['discuss']}}}},workflowOf:it=>it.workflow}};
      {logic}
      const workflow={{nodes:{{task:{{procedure:'collect'}}}},use:{{collect:'collect-carefully'}}}};
      const it={{state:'task',workflow,use:{{discuss:'discuss-data'}}}};
      const replaced=NL.proceduresFor(it);
      workflow.nodes.task.procedure=null;
      console.log(JSON.stringify([replaced,NL.proceduresFor(it)]));"""
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [['collect-carefully', 'discuss-data'], ['discuss-data']]


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_workflow_details_follow_node_replacements_in_the_draft():
    source = _js()['compose']
    logic = source[source.index('const doesIn ='):source.index('const procTitle =')]
    script = f"""const stepOf=()=>({{do:'write-paper',also:['discuss']}});
      {logic}
      const w={{nodes:{{task:{{procedure:'collect'}}}},use:{{collect:'collect-carefully',discuss:'discuss-data'}}}};
      const replaced=offers({{}},'task',w);
      w.nodes.task.procedure=null;
      console.log(JSON.stringify([replaced,offers({{}},'task',w)]));"""
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [['collect-carefully', 'discuss-data'], ['discuss-data']]


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_document_metadata_preserves_structure_and_escapes_markup_without_a_yaml_parser():
    source = _js()['components']
    reader = source[source.index('const esc ='):source.index('NL.Markdown =')]
    metadata = 'tags:\n  - replication\n  - "causal: inference"\nsource:\n  title: A paper\nnotes: |\n  A multiline note.\nempty: []\nquoted: "<img src=x onerror=alert(1)>"'
    cases = ['---\n' + metadata + '\n---\n# Body', '---\n \n---\nBody', 'Body\n---\nnot metadata',
             '\ufeff---\r\ntags:\r\n- a\r\n---\r\nBody']
    script = f"const window={{}},NL={{}};{reader};console.log(JSON.stringify({json.dumps(cases)}.map(text=>NL.mdToHtml(text))));"
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    from html import unescape
    assert unescape(re.search(r'<pre>(.*?)</pre>', rendered[0], re.S).group(1)) == metadata
    assert '<img' not in rendered[0] and '&lt;img' in rendered[0]
    assert 'fm-chip' not in rendered[0] and '<summary>Document details</summary>' in rendered[0]
    assert '</details><pre class="plain"># Body</pre>' in rendered[0]
    assert rendered[1] == '<pre class="plain">Body</pre>'
    assert rendered[2] == '<pre class="plain">Body\n---\nnot metadata</pre>'
    assert '<pre>tags:\r\n- a</pre>' in rendered[3] and rendered[3].endswith('Body</pre>')


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_held_study_launch_does_not_offer_to_enable_execution_or_call_the_server():
    source = _js()['core']
    launch = source[source.index('NL.launch ='):source.index('NL.launchCommand =')]
    script = f"""
      const messages=[],NL={{getState:()=>({{holds:{{held:{{by:'PI'}}}}}}),toast:(...args)=>messages.push(args),
        execOn:()=>{{throw new Error('must check hold first')}},api:()=>{{throw new Error('must not launch')}}}};
      {launch}
      NL.launch({{target:'held',skill:'discuss'}}).then(result=>console.log(JSON.stringify({{result,messages}})));
    """
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out['result'] is None and 'on hold' in out['messages'][0][0]


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_held_study_primary_action_keeps_existing_work_and_checkpoint_access():
    source = _js()['studies']
    next_for = source[source.index('NL.nextFor ='):source.index('/** a study')]
    script = f"""
      const opened=[],NL={{RUN_ACTIVE:new Set(['running']),runsOf:s=>s.runs||[],
        checkpoint:()=>({{title:'Evidence'}}),openCheckpoint:(...a)=>opened.push(a),
        openRun:id=>opened.push(id),followAgent:id=>opened.push('follow:'+id),go:route=>opened.push(route)}};
      {next_for}
      const it={{id:'held',runnable:['analysis']}},s={{holds:{{held:{{}}}}}};
      const results=[NL.nextFor(s,it),NL.nextFor(s,{{...it,waiting:['review']}}),
        NL.nextFor({{...s,runs:[{{run_id:'active',status:'running'}}]}},it)];
      for(const action of results)action.run();console.log(JSON.stringify({{labels:results.map(x=>x.label),opened}}));
    """
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out['labels'] == ['View hold', 'Review: Evidence', 'Show in lab']
    assert out['opened'] == ['study/held/controls', ['held', 'review'], 'follow:active']


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_get_rejects_http_and_empty_responses_without_accepting_them_as_data():
    source = _js()['core']
    get = source[source.index('NL.get ='):source.index('NL.useGet =')]
    script = f"""
      const NL = {{}}; {get}
      (async () => {{
        const out = [];
        for (const [ok, status, value] of [[false,503,{{config:{{name:'misleading'}}}}],
          [false,400,{{error:'Unknown checkpoint'}}],[true,200,null],[true,200,{{config:{{name:'Lab'}}}}]]) {{
          global.fetch = async () => ({{ok,status,json:async () => value}});
          out.push(await NL.get('/test'));
        }}
        global.fetch = async () => {{throw new Error('offline')}};
        out.push(await NL.get('/test'));
        console.log(JSON.stringify(out));
      }})().catch(e => {{console.error(e); process.exitCode=1}});
    """
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert '503' in values[0]['error'] and 'config' not in values[0]
    assert values[1] == {'error': 'Unknown checkpoint'}
    assert values[2].get('error') and values[4].get('error')
    assert values[3] == {'config': {'name': 'Lab'}}


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_routes_handle_bad_escapes_and_preserve_valid_identifiers():
    source = _js()['core']
    parser = source[source.index('NL.parseRoute ='):source.index('NL.go =')]
    cases = ['#/study/%', '#/%E0%A4%A', '#/study/Mixed%20Case?checkpoint=approve-proposal',
             '#/runs', '#/agents', '#/not-a-page', '#/', '#/constructor', '#/__proto__']
    script = f"""const NL={{}},location={{hash:''}}; {parser}
      console.log(JSON.stringify({json.dumps(cases)}.map(hash=>{{location.hash=hash;return NL.parseRoute()}})));"""
    r = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    values = json.loads(r.stdout)
    assert all(v['page'] == 'not-found' and v['error'] for v in values[:2])
    assert values[2] == {'page': 'study', 'args': ['Mixed Case'], 'query': {'checkpoint': 'approve-proposal'}}
    assert [v['page'] for v in values[3:]] == ['runs', 'agents', 'not-a-page', 'home', 'constructor', '__proto__']


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_demo_and_static_require_named_query_flags():
    source = _js()['core']
    flags = source[source.index('const flags ='):source.index('let es =')]
    cases = [('?open=static-analysis', False, 'http:'), ('?read=lab::demo.md', True, 'http:'),
             ('?static', False, 'http:'), ('?static=1', False, 'http:'),
             ('?demo', False, 'http:'), ('?demo', True, 'http:'), ('?demo', False, 'file:')]
    script = f"""const cases={json.dumps(cases)};
      console.log(JSON.stringify(cases.map(([search,allowed,protocol])=>{{
        const NL={{}},location={{search,protocol}},window={{__ARLOTOPE_DEMO__:allowed}};
        {flags}; return [NL.STATIC,NL.DEMO];
      }})));"""
    r = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [[False, False], [False, False], [True, False], [True, False],
                                    [False, False], [False, True], [False, True]]


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_agent_and_attention_labels_use_the_selected_snapshot_and_preserve_children():
    source = _js()['core']
    titles = source[source.index('NL.RUN_WORD ='):source.index('/* ── the live lab store')]
    accessors = source[source.index('NL.item ='):source.index('NL.backends =')]
    script = f"""
      const NL={{PROC:{{review:{{title:'Review evidence'}}}},ROLE:{{critic:{{label:'Independent critic'}}}},getState:()=>({{}})}};
      {titles} {accessors}
      const s={{items:[{{id:'a',title:'Alpha'}},{{id:'b',title:'Beta'}}],runs:[
        {{run_id:'r',skill:'review',subject:'a',command:'/review a'}},
        {{run_id:'ask',kind:'ask',subject:'b',label:'Check results'}},
        {{run_id:'explain',kind:'ask',label:'Explain findings',explains:{{study:'a'}}}}]}};
      console.log(JSON.stringify({{
        agents:[NL.agentTitle({{run_id:'r',label:'/review a'}},s),
          NL.agentTitle({{run_id:'r',parent:'main',label:'Check statistics'}},s),
          NL.agentTitle({{parent:'main',role:'critic'}},s),NL.agentTitle({{label:'My terminal'}},s)],
        runs:s.runs.map(r=>NL.runTitle(r,s)),
        subjects:[{{idea:'a'}},{{detail:{{study:'b'}}}},{{run_id:'r'}},{{run_id:'explain'}},{{idea:'missing'}},{{target:'hub'}}].map(a=>NL.attSubject(a,s))
      }}));
    """
    r = subprocess.run([NODE, '-e', script], capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got['agents'] == ['Review evidence · Alpha', 'Check statistics', 'Independent critic', 'My terminal']
    assert got['runs'] == ['Review evidence · Alpha', 'Check results · Beta', 'Explain findings · Alpha']
    assert got['subjects'] == ['Alpha', 'Beta', 'Alpha', 'Alpha', 'missing', 'Lab']


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_work_list_keeps_queued_and_unrepresented_waits_without_repeating_inbox_waits():
    source = _js()['core']
    accessors = source[source.index('NL.item ='):source.index('NL.backends =')]
    states = source[source.index('NL.RUN_WORD ='):source.index('NL.runTitle =')]
    components = _js()['components']
    labels = components[components.index('NL.runStateLabel ='):components.index('NL.RunPill =')]
    presentation=(STATIC/'agent-view.js').read_text(encoding='utf-8')
    script = f"""global.window=global; {presentation} const NL={{}}; {states} {accessors} {labels}
      const s={{runs:[{{run_id:'working',status:'running'}},{{run_id:'later',status:'queued'}},
        {{run_id:'question',status:'waiting_input'}},{{run_id:'orphan',status:'waiting_input'}},
        {{run_id:'permission',status:'running',pending_permissions:[{{tool:'Read'}}]}},
        {{run_id:'finished',status:'completed'}}],attention:[{{run_id:'question',sev:'block'}},{{run_id:'permission',sev:'block'}},{{run_id:'orphan',sev:'info'}}]}};
      console.log(JSON.stringify({{work:NL.workRuns(s).map(r=>r.run_id),labels:s.runs.map(r=>NL.runStateLabel(r))}}));"""
    r = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got['work'] == ['working', 'later', 'orphan']
    assert got['labels'] == ['Running', 'Queued', 'Waiting for you', 'Waiting for you', 'Permission needed', 'Finished']


def test_every_api_path_the_ui_calls_exists_on_the_server():
    serve = load("dashboard/serve")
    routes = set(serve.GET_ROUTES) | set(serve.POST_ROUTES) | set(serve.FILE_ROUTES) | {"/api/events", "/api/ping"}
    paths = set()
    for text in _js().values():
        paths |= set(re.findall(r"['\"`](/api/[a-z0-9/_-]+)", text))
    # a path the UI builds (`/api/run/${op}`) shows up as its prefix
    missing = sorted(p for p in paths if p not in routes and not (p.endswith("/") and any(r.startswith(p) for r in routes)))
    assert not missing, f"the UI calls endpoints the server doesn't route: {missing}"


def test_day_and_night_define_the_same_tokens():
    css = (UI / "ui.css").read_text(encoding="utf-8")
    night = re.search(r':root, html\[data-lamp="night"\] \{(.*?)\n\}', css, re.S).group(1)
    day = re.search(r'html\[data-lamp="day"\] \{(.*?)\n\}', css, re.S).group(1)
    colour = lambda block: {k for k in re.findall(r"(--[\w-]+):", block) if k not in ("--sans", "--serif", "--mono", "--round", "--r", "--r-l", "--top", "--rail-w")}   # noqa: E731
    assert colour(night) == colour(day), colour(night) ^ colour(day)


def test_retired_files_stay_retired_and_vendored_libs_carry_licences():
    for f in ("app.js", "terrarium.css"):
        assert not (STATIC / f).exists(), f
    for f in ("preact.umd.js", "hooks.umd.js", "htm.umd.js", "LICENSE-preact", "LICENSE-htm"):
        assert (STATIC / "vendor" / "preact" / f).exists(), f
    fonts = STATIC / "vendor" / "fonts"         # the bundled type (SIL OFL), each with its licence
    for fam in ("newsreader", "instrument-sans", "ibm-plex-mono"):
        assert list(fonts.glob(f"{fam}-*.woff2")) and (fonts / f"OFL-{fam}.txt").exists(), fam
    css = (UI / "ui.css").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in css and all(f"'{n}'" in css for n in ("Newsreader", "Instrument Sans", "IBM Plex Mono"))


def test_approvals_and_free_form_are_wired_in_the_ui():
    src = "\n".join(_js().values())
    assert "/api/checkpoint/decide" in src and "NL.HoldButton" in src   # a checkpoint is approved by press-and-hold
    assert "op: 'checkpoint'" in src and "op: 'workflow'" in src        # the Workflow map edits checkpoints and lines
    assert "prompt:" in src and "/api/run" in src       # Ask Newt sends a free-form prompt
    assert "/api/terminal" in src                       # sign-in opens the CLI's own login window


@pytest.mark.skipif(not NODE, reason="node is needed")
def test_questions_the_live_state_answers_never_start_an_agent():
    """Ask Newt: a status question is answered from the snapshot (free, instant); work goes to an agent."""
    cases = {
        "what needs me?": "needs", "anything waiting on me": "needs", "what's running?": "running",
        "what happened overnight?": "overnight", "how much have we spent today?": "cost", "did anything fail?": "failed",
        "which gates are waiting?": "gates", "which checkpoints are waiting?": "gates", "anything for me to look at?": "foryou",
        "how is sparse moe routing doing?": "status", "status of rl?": "status",
        "compare the last three pilots of moe": None, "write the related work section": None,
        "why did exp-019 time out?": None, "run the smoke test": None, "summarise what moved overnight": None,
    }
    items = [{"id": "moe", "title": "Sparse MoE routing"}, {"id": "rl", "title": "RL fine-tuning"}]
    js = (f"global.window = global; eval(require('fs').readFileSync({json.dumps(str(UI / 'answers.js'))}, 'utf8'));"
          f"const items = {json.dumps(items)}, cases = {json.dumps(list(cases))};"
          "console.log(JSON.stringify(cases.map(c => { const m = window.NL.quickIntent(c, items); return m ? m.intent : null; })));")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert dict(zip(cases, json.loads(r.stdout))) == cases




def test_no_ui_helper_is_defined_twice():
    """Two files (or one twice) assigning the same NL.<name> silently replace one helper with another — as when
    an activity-icon lookup once took the name of the helper every button uses to call the server."""
    seen: dict[str, str] = {}
    for name, text in _js().items():
        for m in re.finditer(r"^\s*NL\.([A-Za-z_]\w*)\s*=(?!=)", text, re.M):
            assert m.group(1) not in seen, f"NL.{m.group(1)} is defined in {seen[m.group(1)]} and again in {name}.js"
            seen[m.group(1)] = f"{name}.js"
