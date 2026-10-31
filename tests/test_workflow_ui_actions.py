"""Dashboard workflow controls preserve graph semantics without starting agents."""
import json
import shutil
import subprocess

import labfiles
import pytest

from conftest import REPO, kernel, load


def test_human_approval_dispatches_all_ready_nodes_with_their_context(hub, monkeypatch):
    kernel()
    import executor
    import lab_profile
    from test_agent_assignments import configure
    from test_agent_workspaces import graph

    k = graph(hub)
    lab, _ = configure(hub)
    definition = k.define.read(hub.root)
    flow = definition['workflows'][0]
    flow['checkpoints'] = [{'id': 'human-review', 'title': 'Review', 'before': 'writing', 'approver': 'me'}]
    flow['nodes']['analysis']['context'] = {'mode': 'continue', 'from': 'seed'}
    flow['nodes']['writing']['context'] = {'mode': 'fresh'}
    k.define.write(hub.root, definition)
    first = lab_profile.start_graph(lab, 'study', executor.enqueue, executor.RunSpec)[0]
    _, _, path, source = executor.find_run(lab, first)
    source.update(status='completed', session_id='source-session')
    labfiles.write_json(path, source)
    k.studies.move(hub.root, 'study', 'done')
    assert k.studies.study(hub.root, 'study')['runnable'] == ['analysis']

    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    api = load('dashboard/decisions')
    monkeypatch.setattr(api.ctx, 'HUB', hub.root)
    monkeypatch.setattr(api.ctx, 'LAB', hub.lab)
    result, code = api.decide({'study': 'study', 'checkpoint': 'human-review',
                               'decision': 'approved', 'confirm': True, 'start': True})
    assert code == 200 and result['launch']['ok'], result
    runs = [executor.find_run(lab, rid)[3] for rid in result['launch']['runs']]
    assert {r['workflow_node'] for r in runs} == {'analysis', 'writing'}
    continuing = next(r for r in runs if r['workflow_node'] == 'analysis')
    reviewing = next(r for r in runs if r['workflow_node'] == 'writing')
    assert continuing['session_id'] == 'source-session'
    assert continuing['context']['mode'] == 'continue'
    assert reviewing['role'] == 'reviewer' and reviewing['backend'] == 'codex'
    assert reviewing['context']['mode'] == 'fresh' and not reviewing.get('session_id')
    assert all(r['status'] == 'queued' and r['workflow_visit'] == 1 for r in runs)


def test_presets_referenced_by_gate_cannot_be_deleted(hub, monkeypatch):
    from test_agent_assignments import configure
    from test_agent_workspaces import graph

    k = graph(hub)
    lab, _ = configure(hub)
    definition = k.define.read(hub.root)
    definition['workflows'][0]['checkpoints'] = [{
        'id': 'independent-review', 'title': 'Review', 'before': 'writing', 'approver': 'agent',
        'evidence': ['studies/{study}/IDEA.md'],
        'judge': {'skill': 'gate-review', 'preset': 'external'}, 'decisions': {'proceed': 'continue'}}]
    k.define.write(hub.root, definition)
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    api = load('dashboard/agent_settings')
    monkeypatch.setattr(api.ctx, 'HUB', hub.root)
    monkeypatch.setattr(api.ctx, 'LAB', hub.lab)
    before = (hub.lab / 'config.yaml').read_text()
    settings = {key: lab.prog()[key] for key in ('presets', 'default_preset', 'role_presets')}
    settings['presets'].pop('external')
    result, code = api.save({'settings': settings})
    assert code == 400 and 'independent-review' in result['error']
    assert (hub.lab / 'config.yaml').read_text() == before


@pytest.mark.skipif(not shutil.which('node'), reason='node is needed')
@pytest.mark.parametrize('connection', ['', 'source:approve'])
def test_parallel_task_preserves_the_selected_conditional_connection(connection):
    """Exercise the rendered action; neither a DOM nor a graph-library test double is needed."""
    nodes = [{'id': 'source', 'label': 'Source', 'next': [],
              'outcomes': {'approve': ['review'], 'revise': ['retry']}},
             {'id': 'review', 'label': 'Review', 'next': ['finish']},
             {'id': 'retry', 'label': 'Retry', 'next': []},
             {'id': 'finish', 'label': 'Finish', 'next': []}]
    if connection:
        nodes[0]['next'] = ['review']  # The same source has two distinct incoming connections.
    script = r"""
      global.window=global; global.matchMedia=()=>({matches:false});
      let hook=0,updated;
      const html=(strings,...values)=>({strings:[...strings],values});
      window.NL={html,useEffect:()=>{},useRef:()=>({current:null}),
        useState:initial=>{const index=++hook;return [index===1?'review':index===6?CONNECTION:
          typeof initial==='function'?initial():initial,()=>{}]}};
      eval(require('fs').readFileSync(FILE,'utf8'));
      const tree=NL.WorkflowCanvas({nodes:NODES,rooms:[],onChange:value=>updated=value});
      function find(value){
        if(Array.isArray(value))return value.map(find).find(Boolean);
        if(value&&value.strings){
          if(value.strings.some(s=>s.includes('+ Parallel task')))return value;
          return value.values.map(find).find(Boolean);
        }
      }
      const button=find(tree);
      const index=button.strings.findIndex(s=>s.includes('>+ Parallel task'));
      button.values[index-1]();
      console.log(JSON.stringify(updated));
    """.replace('CONNECTION', json.dumps(connection)).replace('FILE', json.dumps(str(REPO / 'dashboard/static/ui/workflow-canvas.js'))).replace('NODES', json.dumps(nodes))
    result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    updated = json.loads(result.stdout)
    source = next(n for n in updated if n['id'] == 'source')
    added = next(n for n in updated if n['id'].startswith('task-'))
    assert source['outcomes']['approve'] == ['review', added['id']]
    assert source['outcomes']['revise'] == ['retry']
    assert source['next'] == nodes[0]['next']
    assert added['next'] == ['finish']
    assert next(n for n in updated if n['id'] == 'finish')['join']


@pytest.mark.skipif(not shutil.which('node'), reason='node is needed')
@pytest.mark.parametrize('action', ['delete', 'add'])
def test_map_actions_preserve_valid_context_and_the_workflow_entry(action):
    nodes = [{'id': 'a', 'label': 'A', 'next': ['b'], 'outcomes': {'revise': ['c']}},
             {'id': 'b', 'label': 'B', 'next': ['c'], 'context': {'mode': 'continue', 'from': 'a'}},
             {'id': 'c', 'label': 'C', 'next': [], 'context': {'mode': 'fresh', 'handoff': True, 'from': ['a', 'd']}},
             {'id': 'd', 'label': 'D', 'next': ['a', 'c']}]
    script = r"""
      global.window=global;global.matchMedia=()=>({matches:false});
      let hook=0,updated;
      window.NL={html:(strings,...values)=>({strings:[...strings],values}),useEffect:()=>{},useRef:()=>({current:null}),
        useState:initial=>[++hook===1?'a':typeof initial==='function'?initial():initial,()=>{}]};
      eval(require('fs').readFileSync(FILE,'utf8'));
      const tree=NL.WorkflowCanvas({nodes:NODES,rooms:[{id:'study'}],onChange:value=>updated=value});
      function find(value){
        if(Array.isArray(value))return value.map(find).find(Boolean);
        if(value&&value.strings){
          const index=value.strings.findIndex(s=>s.includes(LABEL));
          if(index>=0)return ()=>value.values[index-1]();
          return value.values.map(find).find(Boolean);
        }
      }
      find(tree)();console.log(JSON.stringify(updated));
    """.replace('FILE', json.dumps(str(REPO/'dashboard/static/ui/workflow-canvas.js'))).replace('NODES', json.dumps(nodes)).replace('LABEL', json.dumps('>Delete task' if action == 'delete' else '>+ Task'))
    result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    updated = json.loads(result.stdout)
    if action == 'add':
        assert updated[:len(nodes)] == nodes
        assert updated[-1]['next'] == [] and updated[-1]['id'].startswith('task-')
    else:
        by_id = {n['id']: n for n in updated}
        assert set(by_id) == {'b', 'c', 'd'}
        assert by_id['b']['context'] == {'mode': 'fresh'}
        assert by_id['c']['context']['from'] == ['d']
        assert by_id['d']['next'] == ['c']
        from workflow_graph import validate
        assert not validate(updated)
