"""Native billing selection stays separate from CLI sign-in and from saved run records."""
import io
from contextlib import contextmanager
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from conftest import REPO, load
import native_providers as N
import provider_access as P
from executor import assignments, RunSpec, Lab
from executor.backends import Attempt
from executor.backends.codex import Codex, CodexSession
from executor.backends.claude import Claude


def test_private_connection_file_does_not_change_native_logins(tmp_path,monkeypatch):
    monkeypatch.setenv('ARLOTOPE_HOME',str(tmp_path/'private'))
    monkeypatch.delenv('OPENAI_API_KEY',raising=False);monkeypatch.delenv('CODEX_API_KEY',raising=False)
    monkeypatch.delenv('ANTHROPIC_API_KEY',raising=False)
    normal=tmp_path/'native-auth.json';normal.write_text('{"type":"subscription"}')
    assert not N.credential('openai')
    assert N.key('connect','openai',' fixture-key ')['configured']
    N.key('connect','anthropic','anthropic-fixture')
    assert N.credential('openai')=='fixture-key' and N.credential('anthropic')=='anthropic-fixture'
    assert normal.read_text()=='{"type":"subscription"}'
    if os.name!='nt':assert stat.S_IMODE(N._path().stat().st_mode)==0o600
    assert 'fixture-key' not in json.dumps(N.key('disconnect','openai'))
    assert not N.credential('openai') and N.credential('anthropic')
    with pytest.raises(ValueError):N.key('connect','openai','line\nbreak')


def test_provider_defaults_use_native_harnesses_without_opencode(monkeypatch):
    seen=[]
    monkeypatch.setattr(N,'catalog',lambda provider:seen.append(provider) or {'ok':True})
    monkeypatch.setattr(P,'catalog',lambda refresh:pytest.fail('OpenCode is not needed for native providers'))
    assert P.view('openai')['ok'] and P.view('anthropic')['ok']
    assert seen==['openai','anthropic']
    assert next(p for p in P.choices() if p['id']=='openai')['backends']==['codex','opencode']
    with pytest.raises(ValueError):P.view('anthropic','codex')


@pytest.mark.parametrize('provider',['openai','anthropic'])
def test_model_discovery_uses_native_protocol_and_returns_only_public_fields(provider,monkeypatch):
    calls=[]
    monkeypatch.setattr(N,'credential',lambda _: 'fixture-key')
    @contextmanager
    def probe(backend,secret):
        assert secret=='fixture-key'
        def call(message):
            calls.append(message)
            if message.get('method')=='model/list':
                cursor=message['params']['cursor']
                return {'data':[{'model':'second' if cursor else 'current','displayName':'Model','private':'fixture-key'}],
                        'nextCursor':None if cursor else 'next'}
            return {'models':[{'value':'default','displayName':'Current Claude','private':'fixture-key'}]}
        yield call,lambda message:calls.append(message)
    monkeypatch.setattr(N,'_probe',probe)
    result=N.catalog(provider)
    assert 'fixture-key' not in json.dumps(result)
    assert result['providers'][0]['configured']
    models=result['providers'][0]['models']
    assert [m['id'] for m in models]==(['current','second'] if provider=='openai' else ['default'])
    if provider=='openai':
        assert [c['method'] for c in calls]==['initialize','initialized','account/login/start','model/list','model/list']
    else:assert calls[0]['request']['subtype']=='initialize'


def test_api_billing_is_an_explicit_assignment_and_conversation_identity(hub):
    from test_agent_assignments import configure
    lab,cfg=configure(hub)
    cfg['agents']['programmatic']['presets']['api']={'backend':'codex','api_provider':'openai'}
    import yaml
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(cfg))
    api=assignments.resolve(lab,RunSpec('',preset='api'))
    normal=assignments.resolve(lab,RunSpec('',backend='codex'))
    assert api['options']['api_provider']=='openai' and normal['options']['api_provider'] is None
    assert api['identity']!=normal['identity'] and 'fixture-key' not in json.dumps(api)
    with pytest.raises(ValueError):assignments.validate({'presets':{'wrong':{'backend':'claude','api_provider':'openai'}}})


def test_api_agent_check_reports_missing_key_without_using_subscription_sign_in(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/agent_settings')
    monkeypatch.setattr(api.ctx,'HUB',hub.root)
    monkeypatch.setattr(api.backends,'resolve_cli',lambda *args:[sys.executable])
    body={'agent':{'backend':'codex','api_provider':'openai'}}
    monkeypatch.setattr(N,'credential',lambda _:None)
    assert api.check(body)[1]==400
    monkeypatch.setattr(N,'credential',lambda _:'fixture-key')
    result,code=api.check(body)
    assert code==200 and 'API key found' in result['message'] and 'billing' in result['message']
    assert 'fixture-key' not in json.dumps(result)


def test_codex_api_login_precedes_thread_creation_and_does_not_log_the_key():
    session=CodexSession('go',api_key='fixture-key',thread={'cwd':'/workspace'})
    calls=[];session._write=lambda obj:calls.append(obj) or True
    session.open(SimpleNamespace(stdin=io.StringIO()))
    session.handle({'id':1,'result':{}})
    login=calls[-1]
    assert login['method']=='account/login/start' and login['params']=={'type':'apiKey','apiKey':'fixture-key'}
    assert not any(c.get('method')=='thread/start' for c in calls)
    lines,events=session.handle({'id':login['id'],'result':{'type':'apiKey'}})
    assert calls[-1]['method']=='thread/start' and not lines and not events
    assert 'api_key' not in session.ctx


def test_native_adapters_only_inject_selected_connections(hub,tmp_path,monkeypatch):
    monkeypatch.setattr(N,'credential',lambda provider:provider+'-fixture')
    def attempt(backend,selected):
        cfg={'api_provider':selected} if selected else {}
        lab=Lab(hub.root)
        return Attempt(lab,{'level':'hub'},hub.root,tmp_path,{},['agent'],'go','',False,True,{},sys.executable,
            guard=None,tracer=None),cfg
    a,cfg=attempt('codex','openai');a.m['assignment']={'options':cfg}
    Codex().prepare(a)
    assert a.env['CODEX_API_KEY']=='openai-fixture'
    command=Codex().command(a).argv
    assert 'cli_auth_credentials_store="ephemeral"' in command and not any('openai-fixture' in v for v in command)
    normal,_=attempt('codex',None);Codex().prepare(normal)
    assert 'CODEX_API_KEY' not in normal.env
    a,cfg=attempt('claude','anthropic');a.m['assignment']={'options':cfg}
    a.env.update(ANTHROPIC_AUTH_TOKEN='other',CLAUDE_CODE_USE_BEDROCK='1')
    Claude().prepare(a)
    assert a.env['ANTHROPIC_API_KEY']=='anthropic-fixture' and 'ANTHROPIC_AUTH_TOKEN' not in a.env
    assert 'CLAUDE_CODE_USE_BEDROCK' not in a.env
    assert 'anthropic-fixture' not in json.dumps(a.m)
