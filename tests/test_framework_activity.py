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


def test_remote_activity_uses_existing_worker_rpc(monkeypatch,tmp_path):
    import remote_projects
    seen=[]
    monkeypatch.setattr(A,'request',lambda *_:{'definition':{'id':'tool'},'project':'/project','study':'demo','phase':'work','machine':'box'})
    monkeypatch.setattr(remote_projects,'rpc',lambda *args:seen.append(args) or {'events':[]})
    assert A.view(tmp_path,{},refresh=True)=={'events':[],'machine':'box'}
    assert seen[0][:2]==('box','framework-activity') and 'machine' not in seen[0][2]
    assert A.view(tmp_path,{'external_activity':{'events':['saved']}})=={'events':['saved']}


def test_activity_drives_existing_actor_without_creating_workers(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    workers=load('dashboard/workers')
    run={'run_id':'r','status':'running','external_activity':{'current':{'state':'running','kind':'plan','label':'Generate idea','time':'now'}}}
    actors=workers.agents([run],[])
    assert len(actors)==1 and actors[0]['doing']['kind']=='plan' and actors[0]['doing']['summary']=='Generate idea'
    run['status']='waiting_input'
    assert workers.agents([run],[])[0]['doing'] is None
