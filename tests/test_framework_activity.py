"""External events remain observations, separate from execution and completion receipts."""
import json
from pathlib import Path

import pytest

from conftest import REPO, kernel, load

kernel()
import framework_activity as A
import frameworks as F


def fixture(tmp_path):
    definition = dict(F.read(REPO/'workflow/frameworks/sakana.yaml'),id='sakana')
    root = tmp_path/'.arlotope/framework-runs/demo/sakana/run'
    (root/'investigation').mkdir(parents=True)
    return definition,root


def test_real_event_shape_filters_configuration_and_keeps_negative_results(tmp_path):
    definition,root=fixture(tmp_path)
    rows=[{'event':'run_config','fields':{'secret':'private'}},
          {'event':'step_start','phase':'idea','timestamp':'2026-10-20T10:00:00Z','fields':{'step':'idea_generation','cycle':1},'worker_index':0},
          {'event':'attempt_summary','timestamp':'2026-10-20T10:00:01Z','fields':{'attempt_status':'fail'}},
          {'event':'phase_end','timestamp':'2026-10-20T10:00:02Z','fields':{'phase_name':'paper','label':'Paper'}},
          {'event':'finished','timestamp':'2026-10-20T10:00:03Z'}]
    (root/'investigation/events.jsonl').write_text('\n'.join(map(json.dumps,rows))+'\n{"torn":')
    result=A.read(definition,tmp_path,'demo','investigation')
    assert len(result['events'])==3 and result['malformed']==1
    assert result['events'][0]['kind']=='plan' and result['events'][0]['cycle']==1
    assert result['events'][1]['state']=='failed' and result['current']['state']=='completed'
    assert 'private' not in json.dumps(result)
    assert not (root.parent/'investigation.json').exists()  # Observations never create completion.


def test_selection_and_degraded_events_are_shown(tmp_path):
    definition,root=fixture(tmp_path)
    rows=[{'event':'downstream_selection','timestamp':'1','fields':{'selection_kind':'retained_baseline'}},
          {'event':'optional_input_degraded','timestamp':'2'},
          {'event':'cost_summary','timestamp':'3'}]
    (root/'pipeline_events.jsonl').write_text(json.dumps(rows[0])+chr(10)+json.dumps(rows[1])+chr(10)+json.dumps(rows[2]))
    events=A.read(definition,tmp_path,'demo','investigation')['events']
    assert [(e['label'],e['state']) for e in events]==[('retained baseline','completed'),
        ('Optional input degraded','degraded'),('Cost summary recorded','completed')]


def test_generic_fields_mapping_empty_and_bounded_tail(tmp_path):
    definition,root=fixture(tmp_path)
    definition['activity']={'files':['events.jsonl'],'fields':{'time':'when','event':'type','label':'text'},
                            'events':{'working':{'state':'running','kind':'edit'}}}
    assert A.read(definition,tmp_path,'demo','investigation')['events']==[]
    path=root/'events.jsonl'
    path.write_text('\n'.join(json.dumps({'type':'working','when':str(i).zfill(6),'text':str(i)}) for i in range(6000)))
    result=A.read(definition,tmp_path,'demo','investigation')
    assert result['clipped'] and len(result['events'])==160 and result['current']['label']=='5999'
    assert result['current']['kind']=='edit'
    definition['activity']['files']=['../../../../outside.jsonl']
    with pytest.raises(ValueError,match='escapes'):
        A.read(definition,tmp_path,'demo','investigation')


def test_remote_activity_is_data_and_this_lab_decides_where_it_points(monkeypatch,tmp_path):
    """A machine's activity reaches the page as text and numbers. Its root, machine and sources are this Lab's, so
    the Source link opens that machine's run folder, never a local file or a network share the machine named."""
    import remote_projects
    seen=[]
    definition={'id':'tool','activity':{'files':['{phase}/events.jsonl']}}
    monkeypatch.setattr(A,'request',lambda *_:{'definition':definition,'project':'/project','study':'demo','phase':'work','machine':'box'})
    hostile={'root':'//attacker.invalid/share','machine':'','malformed':'many','events':['junk',
             {'time':'t','label':'Reading','state':'running','kind':'read','source':'../../etc/passwd','worker':{'x':1}},
             {'time':'u','label':'Writing','state':'completed','kind':'edit','source':'work/events.jsonl','cycle':2}]}
    monkeypatch.setattr(remote_projects,'rpc',lambda *args:seen.append(args) or hostile)
    got=A.view(tmp_path,{},refresh=True)
    assert seen[0][:2]==('box','framework-activity') and 'machine' not in seen[0][2]
    assert got['machine']=='box' and got['root']=='/project/.arlotope/framework-runs/demo/tool/run' and got['malformed']==0
    assert [(e['label'],e['source'],e['worker'],e['cycle']) for e in got['events']]==[
        ('Reading','',None,None),('Writing','work/events.jsonl',None,2)]
    for junk in ('x',['y'],None):
        monkeypatch.setattr(remote_projects,'rpc',lambda *args,junk=junk:junk)
        assert A.view(tmp_path,{},refresh=True)=={'error':'The machine reported unreadable activity.','machine':'box'}
    stored={'events':[],'machine':'box'}
    assert A.view(tmp_path,{'external_activity':stored}) is stored     # what sync kept, already taken as data


def test_activity_drives_existing_actor_without_creating_workers(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    workers=load('dashboard/workers')
    run={'run_id':'r','status':'running','external_activity':{'current':{'state':'running','kind':'plan','label':'Generate idea','time':'now'}}}
    actors=workers.agents([run],[])
    assert len(actors)==1 and actors[0]['doing']['kind']=='plan' and actors[0]['doing']['summary']=='Generate idea'
    run['status']='waiting_input'
    assert workers.agents([run],[])[0]['doing'] is None
