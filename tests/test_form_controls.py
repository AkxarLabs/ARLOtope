"""Editing preserves text; only submitted commands discard blank argument lines."""
import json
import shutil
import subprocess

import pytest

from conftest import REPO

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(not NODE, reason='node is needed')


def run(script):
    result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_command_editing_retains_newlines_until_submission():
    source = (REPO / 'dashboard/static/ui/agents.js').read_text(encoding='utf-8')
    controls = source[source.index('  const CommandFields='):source.index('  NL.AgentAssignments=')]
    result = run("""
      const NL={Field:'field',Input:'input',Textarea:'textarea'};
      const html=(strings,...values)=>({values});
    """ + controls + """
      let command=['agent','acp'];
      const type=text=>CommandFields({value:command,onChange:value=>command=value})
        .values.filter(value=>typeof value==='function')[1](text);
      type('acp\\n');
      const first=command.slice();
      type('acp\\nargument with spaces\\n\\n');
      console.log(JSON.stringify({first,edited:command,sent:cleanAgent({command}).command}));
    """)
    assert result == {
        'first': ['agent', 'acp', ''],
        'edited': ['agent', 'acp', 'argument with spaces', '', ''],
        'sent': ['agent', 'acp', 'argument with spaces'],
    }


def test_unsaved_form_guard_retains_cancelled_edits_and_releases_clean_forms():
    source = (REPO / 'dashboard/static/ui/core.js').read_text(encoding='utf-8')
    guard = source[source.index('  // Shared protection for forms'):source.index('  /* ── preferences')]
    result = run("""
      const NL={},events={},location={hash:'#/settings/agents'};
      let consent=false,restored=null,prompts=0,cleanup;
      const window={addEventListener:(name,fn)=>events[name]=fn,
        confirm:()=>{prompts++;return consent}};
      const history={replaceState:(_state,_title,path)=>{restored=path;location.hash=path}};
      const H={useRef:value=>({current:value}),useLayoutEffect:fn=>fn(),useEffect:fn=>cleanup=fn()};
    """ + guard + """
      const markClean=NL.useDirty(true);
      location.hash='#/workflow';let blocked=false;
      events.hashchange({stopImmediatePropagation:()=>blocked=true});
      let unloadBlocked=false;events.beforeunload({preventDefault:()=>unloadBlocked=true});
      const protectedUnload=unloadBlocked;
      markClean();location.hash='#/workflow';
      events.hashchange({stopImmediatePropagation:()=>{throw Error('Clean form blocked')}});
      NL.useDirty(true);consent=true;location.hash='#/library';
      events.hashchange({stopImmediatePropagation:()=>{throw Error('Accepted discard blocked')}});
      unloadBlocked=false;events.beforeunload({preventDefault:()=>unloadBlocked=true});
      cleanup();
      console.log(JSON.stringify({blocked,restored,prompts,protectedUnload,unloadBlocked}));
    """)
    assert result == {'blocked': True, 'restored': '#/settings/agents', 'prompts': 2,
                      'protectedUnload': True, 'unloadBlocked': False}
