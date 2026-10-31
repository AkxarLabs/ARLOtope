"""The CLI uses authenticated dashboard routes, preserving payloads, errors and owner selection."""
import http.client
import json
import threading
import pytest
from conftest import load


@pytest.fixture
def api(hub,monkeypatch):
    from test_serve import _mod
    m=_mod(hub,monkeypatch)
    calls=[]
    reads={**m.GET_ROUTES,'/api/state':lambda q:({'ok':True,'items':[{'id':'example'}]},200)}
    writes={**m.POST_ROUTES,'/api/echo':lambda b:(calls.append(b) or {'ok':True,'received':b},200)}
    monkeypatch.setattr(m,'GET_ROUTES',reads);monkeypatch.setattr(m,'POST_ROUTES',writes)
    monkeypatch.setattr(m.ctx,'REMOTE',object())
    proxy=[]
    monkeypatch.setattr(m.Handler,'_proxy',lambda self,method:proxy.append(method) or self._json({'error':'wrong Lab'},500))
    server=m.LabServer(('127.0.0.1',0),m.Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try: yield m,server.server_address[1],calls,proxy
    finally: server.shutdown();server.server_close();thread.join(timeout=3)


def test_session_bootstrap_obeys_origin_checks_and_client_stays_on_owner(api,hub):
    m,port,calls,proxy=api
    for origin in ('null','https://elsewhere.example'):
        c=http.client.HTTPConnection('127.0.0.1',port)
        c.request('GET','/api/session',headers={'Origin':origin})
        response=c.getresponse()
        assert response.status==403 and response.getheader('Set-Cookie') is None
        response.read();c.close()
    from api_client import Client
    client=Client(hub.root,port)
    status,_headers,body=client.request('GET','/api/state')
    assert status==200 and json.loads(body)['items'][0]['id']=='example'
    assert client.cookie.startswith('arlotope_'+str(port)+'=') and not proxy
    status,_headers,body=client.request('POST','/api/echo',{'instructions':'Unicode → research','nested':{'n':7}})
    assert status==200 and calls==[json.loads(body)['received']]
    status,_headers,body=client.request('GET','/api/schema')
    schema=json.loads(body)
    assert status==200 and set(m.POST_ROUTES)<={p for p,d in schema['paths'].items() if 'post' in d}
    assert schema['components']['securitySchemes']['localSession']['name']=='arlotope_'+str(port)
    assert not schema['paths']['/api/session']['get']['security']
    assert schema['paths']['/api/providers']['post']['requestBody']['content']['application/json']['schema']['properties']['key']['writeOnly']


def test_cli_accepts_yaml_files_queries_and_raw_file_output(api,hub,tmp_path,capsys):
    _m,port,calls,_proxy=api
    cli=load('arlo_cli')
    request=tmp_path/'request.yaml';request.write_text('instructions: Read the sources\noutputs:\n- evidence.json\n')
    assert cli.main(['api','POST','/api/echo','--hub',str(hub.root),'--port',str(port),'--data','@'+str(request)])==0
    assert json.loads(capsys.readouterr().out)['received']['outputs']==['evidence.json']
    output=tmp_path/'response.json'
    assert cli.main(['api','GET','/api/state','--port',str(port),'--query','study=example','--output',str(output)])==0
    assert json.loads(output.read_text())['items'][0]['id']=='example'
    assert cli.main(['open','example','--port',str(port),'--print'])==0
    assert '#/study/example' in capsys.readouterr().out
    assert cli.main(['api','POST','/api/echo','--port',str(port),'--data','[not,an,object]'])==2
    assert len(calls)==1


def test_managed_client_cannot_claim_pi_decisions_and_keeps_parent(monkeypatch):
    from api_client import protect
    monkeypatch.setenv('ARLOTOPE_RUN_ID','parent-run')
    for route,body in [('/api/checkpoint/decide',{'decision':'approved'}),('/api/checkpoint/gate',{'choice':'accept'}),
        ('/api/run/permission',{'action':'allow'}),('/api/workflow/proposal',{'accept':True}),
        ('/api/providers',{'action':'connect'}),('/api/compose',{'op':'publish'})]:
        with pytest.raises(ValueError,match='PI-owned'): protect('POST',route,body)
    assert protect('POST','/api/compose',{'op':'graph'})=={'op':'graph'}
    result=protect('POST','/api/run',{'parent':'invented','prompt':'Read evidence'})
    assert result['parent']=='parent-run' and result['created_by']=='run:parent-run'
    assert protect('GET','/api/providers',None) is None
    import signature_guard
    monkeypatch.setattr(signature_guard,'_config_run',lambda:True)
    assert protect('POST','/api/providers',{'action':'connect'})=={'action':'connect'}
    with pytest.raises(ValueError,match='PI-owned'):
        protect('POST','/api/checkpoint/decide',{'decision':'approved'})


def test_secret_prompt_is_not_printed_and_failed_writes_are_not_replayed(api,hub,monkeypatch,capsys):
    _m,port,calls,_proxy=api
    import getpass, sys
    monkeypatch.setattr(sys.stdin,'isatty',lambda:True)
    monkeypatch.setattr(getpass,'getpass',lambda _: 'private-fixture-key')
    # Real provider route returns public metadata only; the echo fixture would echo its input.
    monkeypatch.setitem(_m.POST_ROUTES,'/api/private',lambda b:(calls.append(b) or {'ok':True},200))
    cli=load('arlo_cli')
    assert cli.main(['api','POST','/api/private','--port',str(port),'--secret','key'])==0
    assert calls[-1]['key']=='private-fixture-key'
    assert 'private-fixture-key' not in capsys.readouterr().out
    from api_client import Client
    client=Client(hub.root,port);client.cookie='existing=session'
    attempts=[]
    def lost(*args,**kwargs):
        attempts.append(args)
        raise http.client.RemoteDisconnected('lost response')
    monkeypatch.setattr(client,'_request',lost)
    with pytest.raises(http.client.RemoteDisconnected):client.request('POST','/api/private',{'x':1})
    assert len(attempts)==1
