"""Viewing context is scoped to studies and never changes execution records."""
import json
import shutil
import subprocess
import pytest
from conftest import REPO

NODE=shutil.which('node')
pytestmark=pytest.mark.skipif(not NODE,reason='node is needed')

def run(body):
    source=(REPO/'dashboard/static/ui/focus.js').read_text(encoding='utf-8')
    script="""
      global.window=global;global.location={hash:'#/study/a',origin:'http://lab'};
      global.history={replaceState:(_a,_b,path)=>location.hash=path};
      const s={lab_info:{path:'/lab'},items:[{id:'a',workflow:'custom'},{id:'b',workflow:'other'}],
        runs:[{run_id:'r',subject:'a',workflow_node:'arbitrary-task'}],agents:[]};
      const N=window.NL={getState:()=>s,item:(s,id)=>s.items.find(i=>i.id===id),
        qs:q=>new URLSearchParams(Object.entries(q).filter(([,v])=>v!=null&&v!=='')).toString(),
        parseRoute:()=>{const [path,q='']=location.hash.slice(2).split('?'),[page,...args]=path.split('/');return {page:page||'home',args,query:Object.fromEntries(new URLSearchParams(q))}},
        go:path=>location.hash=path};
    """+source+'\nconsole.log(JSON.stringify((()=>{'+body+'})()));'
    result=subprocess.run([NODE,'-e',script],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)

def test_focus_round_trip_and_explicit_study_change_do_not_touch_records():
    got=run("""
      const before=JSON.stringify(s);N.focusRun(s.runs[0],'reviewer');
      const focus=N.getFocus(),library=N.focusHref('library?view=records'),workflow=N.focusHref('workflow/map');
      location.hash=library;N.syncFocus(N.parseRoute(),s);const restored=N.getFocus();
      N.syncFocus({page:'study',args:['b'],query:{}},s);
      return {focus,restored,library,workflow,changed:N.getFocus(),untouched:before===JSON.stringify(s)};
    """)
    assert got['focus']==got['restored']=={'study':'a','task':'arbitrary-task','run':'r','sub':'reviewer'}
    assert 'study=a' in got['library'] and 'view=records' in got['library']
    assert 'workflow=custom' in got['workflow']
    assert got['changed']=={'study':'b'} and got['untouched']

def test_focus_clears_and_new_labs_do_not_inherit_another_labs_selection():
    got=run("""
      N.focusRun(s.runs[0]);N.getFocus();s.lab_info.path='/different';const other=N.getFocus();
      N.setFocus({study:'a',task:'anything'});location.hash=N.focusHref('library?view=documents');N.clearFocus();
      return {other,cleared:N.getFocus(),url:location.hash,invalid:N.resolveFocus(s,{study:'missing',task:'task'})};
    """)
    assert got['other']==got['cleared']==got['invalid']=={}
    assert got['url']=='#/library?view=documents'

def test_global_workflow_selection_and_unknown_history_keep_honest_scope():
    got=run("""
      N.focusRun(s.runs[0]);N.syncFocus({page:'workflow',args:['map'],query:{workflow:'other'}},s);
      const global=N.getFocus();N.setFocus({study:'a',run:'old-run',task:'old-task'});
      return {global,historical:N.getFocus(),override:N.focusHref('workflow/map?workflow=explicit')};
    """)
    assert got['global']=={}
    assert got['historical']=={'study':'a','task':'old-task','run':'old-run'}
    assert 'workflow=explicit' in got['override']


def test_inspecting_from_global_library_records_scope_and_clear_from_study_returns_to_lab():
    got=run("""
      location.hash='#/library?view=documents';N.focusRun(s.runs[0]);
      const url=location.hash;N.syncFocus(N.parseRoute(),s);const restored=N.getFocus();
      location.hash='#/study/a';N.clearFocus();return {url,restored,cleared:location.hash};
    """)
    assert 'study=a' in got['url'] and 'agent=r' in got['url']
    assert got['restored']=={'study':'a','task':'arbitrary-task','run':'r'}
    assert got['cleared']=='#/'
