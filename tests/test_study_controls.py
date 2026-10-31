"""Control requests are durable instructions, not hidden scheduler/state transitions."""
import json
import pytest
from conftest import REPO, kernel, load

@pytest.mark.parametrize('action',['prioritize','park','kill'])
def test_study_requests_only_append_an_instruction(hub,monkeypatch,action):
    hub.add_registry_row('pending',state='seed')
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    module=load('dashboard/runops')
    monkeypatch.setattr(module.ctx,'HUB',hub.root)
    monkeypatch.setattr(module.ctx,'LAB',hub.lab)
    before=kernel().studies.study(hub.root,'pending')
    called=[]
    monkeypatch.setattr(module,'launch_run',lambda *a,**kw:called.append(a))
    response,code=module.command_post({'target':'pending','action':action,'launch':True})
    assert code==200 and response['ok'] and response['launch'] is None
    assert not called and kernel().studies.study(hub.root,'pending')==before
    rows=[json.loads(line) for line in (hub.lab/'.bus/directives.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['kind']=='command' and rows[0]['action']==action
    assert rows[0]['target']=='pending'
