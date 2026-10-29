"""Public provider metadata, opaque native credentials and execution-host routing."""
from contextlib import contextmanager
import json
import pytest
from conftest import load, kernel, REPO

kernel()
import provider_access as P


def test_catalog_keeps_only_public_metadata_and_refreshes_on_request(monkeypatch):
    calls=[]
    @contextmanager
    def server():
        def request(method,path,body=None):
            calls.append((method,path,body))
            if path=='/config/providers':
                return {'providers':[{'id':'openrouter','options':{'apiKey':'private'},'models':{
                    'new/model:free':{'name':'Current model','capabilities':{'toolcall':True}}}}]}
            return {'connected':['openrouter'],'all':[{'id':'openrouter','name':'OpenRouter',
                'options':{'apiKey':'never-export-this'},'models':{'stale/model':{
                    'name':'Unavailable model','apiKey':'also-private'}}}]}
        yield request
    monkeypatch.setattr(P,'_server',server)
    monkeypatch.setattr(P,'_cache',None)
    first=P.catalog()
    assert first['providers'][0]['models'][0]['id']=='new/model:free'
    assert first['providers'][0]['configured']
    assert 'private' not in json.dumps(first) and 'apiKey' not in json.dumps(first)
    assert P.catalog() is first and len(calls)==2
    refresh=[]
    monkeypatch.setattr(P.shutil,'which',lambda _: '/opencode')
    monkeypatch.setattr(P.subprocess,'Popen',lambda args,**kw: refresh.append(args) or type('R',(),{'wait':lambda self,timeout:0,'poll':lambda self:0})())
    P.catalog(refresh=True)
    assert refresh==[['/opencode','models','--refresh']] and len(calls)==4


def test_refresh_timeout_reaps_the_native_process_tree(monkeypatch):
    killed=[]
    class Process:
        pid=12345
        def poll(self):return None
        def wait(self,timeout):
            if timeout==60:raise P.subprocess.TimeoutExpired('opencode',timeout)
            return 0
    monkeypatch.setattr(P.shutil,'which',lambda _: '/opencode')
    monkeypatch.setattr(P.subprocess,'Popen',lambda *a,**kw:Process())
    from executor import procs
    monkeypatch.setattr(procs,'kill_tree',lambda pid:killed.append(pid))
    with pytest.raises(ValueError,match='refresh did not finish'):P.catalog(refresh=True)
    assert killed==[12345]


def test_keys_are_sent_only_to_native_auth_and_never_returned(monkeypatch):
    calls=[]
    @contextmanager
    def server():
        yield lambda *args: calls.append(args) or True
    monkeypatch.setattr(P,'_server',server)
    value=P.key('connect','openrouter',' fixture-secret ')
    assert calls==[('PUT','/auth/openrouter',{'type':'api','key':'fixture-secret'})]
    assert 'secret' not in json.dumps(value)
    P.key('disconnect','openrouter')
    assert calls[-1]==('DELETE','/auth/openrouter',None)
    for provider,key in [('../openai','secret'),('openai',''),('openai','line\nbreak')]:
        with pytest.raises(ValueError): P.key('connect',provider,key)
    assert len(calls)==2


def test_dashboard_and_worker_reuse_the_provider_adapter_without_logging_keys(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/providers')
    monkeypatch.setattr(api.ctx,'HUB',hub.root)
    monkeypatch.setattr(api.ctx,'LAB',hub.lab)
    seen=[]
    monkeypatch.setattr(api.provider_access,'key',lambda *a: seen.append(a) or {'ok':True})
    value,code=api.save({'action':'connect','provider':'openrouter','key':'private-fixture'})
    assert code==200 and value['ok'] and seen[0][2]=='private-fixture'
    assert 'private-fixture' not in (hub.lab/'.bus/pi-actions.jsonl').read_text()
    remote=[]
    monkeypatch.setattr(api.remote_projects,'rpc',lambda *a: remote.append(a) or {'ok':True,'providers':[]})
    assert api.view({'machine':'compute','refresh':'1'})[1]==200
    assert remote==[('compute','providers',{'action':'catalog','refresh':True,'provider':None,'backend':None})]
    from project_worker import Worker
    Worker().call('providers',{'action':'connect','provider':'openrouter','key':'remote-fixture'})
    assert seen[-1]==('connect','openrouter','remote-fixture')
