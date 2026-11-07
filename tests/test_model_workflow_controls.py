"""Model choice edits preserve native Codex effort and workflow discovery stays read-only."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parents[1] / 'dashboard/static/ui'
NODE = shutil.which('node')


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_model_effort_edit_preserves_native_ultra_and_other_preset_fields():
    source = (UI / 'agents.js').read_text()
    helpers = source[source.index('  // Codex presets'):source.index('  const agentCache=')]
    js = "const NL={};" + helpers + """
      const original={backend:'codex',model:'example-model',command:['codex'],effort:'high',reasoning_effort:'medium'};
      const ultra=NL.setAgentEffort(original,'ultra');
      const xhigh=NL.setAgentEffort(ultra,'xhigh');
      const cleared=NL.setAgentEffort(ultra,'');
      const claude=NL.setAgentEffort({backend:'claude',model:'example-claude-model'},'xhigh');
      console.log(JSON.stringify({original,ultra,xhigh,cleared,claude,
        effort:NL.agentEffort({reasoning_effort:'ultra'}),
        codex:NL.agentEffortOptions('codex'),savedMinimal:NL.agentEffortOptions('codex','minimal'),claudeOptions:NL.agentEffortOptions('claude')}));
    """
    result = subprocess.run([NODE, '-e', js], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['original']['effort'] == 'high'  # edits are immutable
    assert data['ultra']['reasoning_effort'] == 'ultra'
    assert not data['ultra'].get('effort')
    assert data['ultra']['model'] == 'example-model'
    assert data['ultra']['command'] == ['codex']
    assert data['xhigh']['effort'] == 'xhigh'
    assert 'reasoning_effort' not in data['xhigh']
    assert not data['cleared'].get('effort') and 'reasoning_effort' not in data['cleared']
    assert data['claude']['effort'] == 'xhigh'
    assert data['effort'] == 'ultra'
    assert {'value': 'ultra', 'label': 'Ultra'} in data['codex']
    assert {'value': 'max', 'label': 'Max'} in data['codex']
    assert all(x['value'] != 'minimal' for x in data['codex'])
    assert {'value': 'minimal', 'label': 'Minimal'} in data['savedMinimal']
    assert all(x['value'] != 'ultra' for x in data['claudeOptions'])


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_create_workflow_link_only_opens_dialog():
    source = (UI / 'compose.js').read_text()
    effect = source[source.index("useEffect(()=>{if(query.create==='1')"):]
    effect = effect[:effect.index('\n')]
    js = """const opened=[],routes=[],events=[];
      const NL={open:(...args)=>opened.push(args),go:()=>{throw Error('must replace the creation route, not push it')}};
      const history={replaceState:(state,unused,route)=>routes.push(route)},window={dispatchEvent:event=>events.push(event.type)},HashChangeEvent=class{constructor(type){this.type=type}};
      const useEffect=fn=>fn(),query={create:'1'},NewWorkflow='workflow-dialog',choose=()=>{},selected='research';
    """ + effect + "console.log(JSON.stringify({opened,routes,events}));"
    result = subprocess.run([NODE, '-e', js], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['opened'][0][0] == 'workflow-dialog'
    assert data['routes'] == ['#/workflow/map?workflow=research']
    assert data['events'] == ['hashchange']
    # Opening the creation route must not edit or publish a workflow.
    assert 'edit(' not in effect and 'NL.api(' not in effect and 'describeWorkflow(' not in effect


@pytest.mark.skipif(not NODE, reason='node is needed')
def test_launch_options_keep_ultra_in_selected_preset_and_do_not_leak_role_defaults():
    agents = (UI / 'agents.js').read_text()
    helpers = agents[agents.index('  // Codex presets'):agents.index('  const agentCache=')]
    source = (UI / 'composer.js').read_text()
    options = source[source.index('  const DEFAULT_OPTS ='):source.index('  const StudyPicker =')]
    js = """const lab={},settings={presets:[{id:'example-preset',backend:'codex',model:'example-model',reasoning_effort:'ultra'}],resolved:{general:{backend:'claude',model:'role-model',effort:'high'}}};
      const NL={html:(strings,...values)=>({strings:[...strings],values}),useLab:()=>lab,exec:()=>({backend:'claude',config:{}}),backends:()=>[],useAgentSettings:()=>settings};
      const {html}=NL;
    """ + helpers + options + """
      const preset={...DEFAULT_OPTS,preset:'example-preset'},custom={...DEFAULT_OPTS,backend:'codex'},max={...DEFAULT_OPTS,backend:'codex',effort:'max'};
      console.log(JSON.stringify({preset:LaunchOptions({opts:preset,setOpts:()=>{}}),custom:LaunchOptions({opts:custom,setOpts:()=>{}}),body:optBody(preset),maxBody:optBody(max)}));
    """
    result = subprocess.run([NODE, '-e', js], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    rendered = json.dumps(data['preset'])
    assert 'example-model' in rendered and 'Ultra' in rendered
    assert 'Use selected settings (Ultra)' in rendered
    assert '"value": "max"' in rendered
    assert data['maxBody'] == {'backend': 'codex', 'effort': 'max'}
    # Ultra stays in the saved preset; the generic per-launch effort field rejects it.
    assert data['body'] == {'preset': 'example-preset'}
    assert 'role-model' not in json.dumps(data['custom'])
    assert 'minimal' not in rendered
