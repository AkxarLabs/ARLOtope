"""Native API connections. Only the selected harness receives a key; CLI sign-ins stay unchanged."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import threading
import time

NATIVE={'openai':('codex','OpenAI','OPENAI_API_KEY'),'anthropic':('claude','Anthropic','ANTHROPIC_API_KEY')}


def _path():
    return Path(os.environ.get('ARLOTOPE_HOME') or Path.home()/'.arlotope')/'provider-keys.json'


def _read():
    path=_path()
    if not path.exists():return {}
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value,dict) or any(k not in NATIVE or not isinstance(v,str) for k,v in value.items()):raise ValueError()
        return value
    except ValueError:
        raise ValueError('Saved API connections could not be read. Restore provider-keys.json.') from None


def credential(provider):
    if provider not in NATIVE:raise ValueError('Choose a supported native provider.')
    value=_read().get(provider) or os.environ.get(NATIVE[provider][2])
    if not value and provider=='openai':value=os.environ.get('CODEX_API_KEY')
    return value


def inject(provider,env,value=None):
    value=value or credential(provider)
    if not value:raise ValueError('Connect an '+NATIVE[provider][1]+' API key on this machine before starting this agent.')
    if provider=='anthropic':
        for name in ('ANTHROPIC_AUTH_TOKEN','CLAUDE_CODE_OAUTH_TOKEN','CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY'):
            env.pop(name,None)
    else:env.pop('CODEX_ACCESS_TOKEN',None)
    env['CODEX_API_KEY' if provider=='openai' else 'ANTHROPIC_API_KEY']=value


def key(action,provider,value=None):
    if provider not in NATIVE or action not in ('connect','disconnect'):raise ValueError('Choose a supported native connection.')
    if action=='connect' and (not isinstance(value,str) or not value.strip() or len(value)>16384 or any(c in value for c in '\r\n\0')):
        raise ValueError('Enter an API key without line breaks.')
    from executor.procs import excl_lock
    path=_path();path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with excl_lock(path.with_suffix('.lock')):
        saved=_read()
        if action=='connect':saved[provider]=value.strip()
        else:saved.pop(provider,None)
        temp=path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
        try:
            with os.fdopen(os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w',encoding='utf-8') as stream:
                json.dump(saved,stream)
            temp.replace(path)
        finally:temp.unlink(missing_ok=True)
    return {'ok':True,'provider':provider,'backend':NATIVE[provider][0],'configured':bool(credential(provider))}


@contextmanager
def _probe(backend,api_key=None):
    from executor import backends
    from executor.procs import NO_WINDOW,kill_tree
    cli=backends.resolve_cli(backend,{})
    if not cli:raise ValueError('Install '+backend+' on this machine, then retry.')
    args=([*(['-c','cli_auth_credentials_store="ephemeral"'] if api_key else []),'app-server'] if backend=='codex'
          else ['-p','--input-format','stream-json','--output-format','stream-json','--verbose'])
    env=dict(os.environ)
    if backend=='claude' and api_key:inject('anthropic',env,api_key)
    if backend=='codex' and api_key:env.pop('CODEX_ACCESS_TOKEN',None)
    proc=subprocess.Popen([*cli,*args],cwd=Path.home(),env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace',**NO_WINDOW)
    lines=queue.Queue(maxsize=128)
    def drain():
        for line in proc.stdout:
            try:lines.put_nowait(line)
            except queue.Full:pass
    reader=threading.Thread(target=drain,daemon=True);reader.start()
    def send(message):
        proc.stdin.write(json.dumps(message)+'\n');proc.stdin.flush()
    def call(message):
        send(message);until=time.monotonic()+30
        while time.monotonic()<until:
            try:line=lines.get(timeout=.2)
            except queue.Empty:
                if proc.poll() is not None:break
                continue
            try:reply=json.loads(line)
            except ValueError:continue
            response=reply if backend=='codex' else reply.get('response') or {}
            if response.get('id' if backend=='codex' else 'request_id')!=message.get('id' if backend=='codex' else 'request_id'):continue
            if response.get('error') or response.get('subtype')=='error':raise ValueError(backend+' refused model discovery. Check its configuration and sign-in.')
            return response.get('result',{}) if backend=='codex' else response.get('response') or {}
        raise ValueError(backend+' did not finish model discovery. Check its installation and retry.')
    try:yield call,send
    finally:
        try:proc.stdin.close();proc.wait(timeout=3)
        except (OSError,ValueError,subprocess.TimeoutExpired):kill_tree(proc.pid);proc.wait(timeout=5)
        reader.join(timeout=1);proc.stdout.close()


def catalog(provider):
    if provider not in NATIVE:raise ValueError('Choose a supported native provider.')
    backend,name,_env=NATIVE[provider];secret=credential(provider)
    with _probe(backend,secret) as (call,send):
        if backend=='codex':
            call({'id':1,'method':'initialize','params':{'clientInfo':{'name':'arlotope','version':'1'},'capabilities':{'experimentalApi':True}}})
            send({'method':'initialized'})
            if secret:call({'id':2,'method':'account/login/start','params':{'type':'apiKey','apiKey':secret}})
            models=[];cursor=None;sequence=3
            while True:
                page=call({'id':sequence,'method':'model/list','params':{'limit':100,'includeHidden':False,'cursor':cursor}})
                models.extend({'id':m['model'],'name':m.get('displayName') or m['model'],'tools':True} for m in page.get('data',[]))
                cursor=page.get('nextCursor');sequence+=1
                if not cursor:break
        else:
            result=call({'type':'control_request','request_id':'models','request':{'subtype':'initialize','hooks':None}})
            models=[{'id':m['value'],'name':m.get('displayName') or m['value'],'tools':True} for m in result.get('models',[])]
    return {'ok':True,'backend':backend,'source':backend+' model discovery','providers':[
        {'id':provider,'name':name,'configured':bool(secret),'models':models}]}
