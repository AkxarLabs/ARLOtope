"""Authenticated loopback access to the same API the dashboard uses. No proxy or redirect handling."""
import http.client
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlencode, urlsplit


def locate(hub, port=None):
    import importlib.util
    spec=importlib.util.spec_from_file_location('_arlo_launcher',Path(__file__).resolve().parents[1]/'arlo.py')
    launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
    hub=Path(hub).resolve()
    if port is not None:
        ports=[int(port)]
    else:
        try: saved=json.loads(launcher.state_file(hub).read_text(encoding='utf-8'))['port']
        except (OSError,ValueError,KeyError): saved=None
        ports=list(dict.fromkeys([*([saved] if saved else []),*launcher.PORTS]))
    for candidate in ports:
        info=launcher.ping(candidate)
        if info and (port is not None or Path(info.get('lab','')).resolve()==hub):
            return candidate
    raise ValueError('This Lab is not running. Start it with arlo --background --no-browser, or set --port.')


def protect(method,path,body):
    """Keep the PI's CLI actions distinct from a managed agent's ordinary requests."""
    run=os.environ.get('ARLOTOPE_RUN_ID')
    if not run or method!='POST': return body
    route=urlsplit(path).path
    configurable={'/api/lab/config','/api/executor/config','/api/executor/enable',
                  '/api/agent-settings','/api/providers','/api/notify'}
    if route in configurable:
        from signature_guard import _config_run
        if _config_run(): return body
    owned={'/api/checkpoint/decide','/api/study/move','/api/study/hold','/api/study/workflow',
           '/api/checkpoint/gate','/api/workflow/proposal','/api/workflow/save','/api/study/entry/cancel',
           '/api/run/permission','/api/run/answer','/api/directive','/api/artifact/reply',
           '/api/study/use','/api/flag/ack','/api/lab/pause','/api/campaign','/api/campaign/control',
           '/api/panel/approve','/api/lab/config','/api/executor/config','/api/executor/enable',
           '/api/agent-settings','/api/providers','/api/notify','/api/server/stop','/api/starter'}
    if route in owned or route=='/api/compose' and (body or {}).get('op') in ('publish','undo'):
        raise ValueError('This is a PI-owned action. A managed agent can prepare a draft or request a decision.')
    if route in ('/api/run','/api/workflow/run'):
        body={**(body or {}),'parent':run,'created_by':'run:'+run}
    return body


class Client:
    def __init__(self,hub,port=None,timeout=180):
        self.port=locate(hub,port)
        self.timeout=timeout
        self.cookie=None

    def _request(self,method,path,body=None,session=True):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=self.timeout)
        headers={'Content-Type':'application/json','X-Arlotope-Local':'1'}
        if session: headers['Cookie']=self.cookie
        try:
            conn.request(method,path,None if body is None else json.dumps(body,default=str),headers)
            response=conn.getresponse()
            data=response.read()
            return response.status,dict(response.getheaders()),data
        finally: conn.close()

    def request(self,method,path,body=None):
        parsed=urlsplit(path)
        if method not in ('GET','POST','HEAD') or parsed.scheme or parsed.netloc or not path.startswith('/api/') or any(c in path for c in '\r\n#'):
            raise ValueError('Use GET, POST or HEAD with a local /api/ path.')
        body=protect(method,path,body)
        if not self.cookie:
            status,headers,_data=self._request('GET','/api/session',session=False)
            cookie=next((v for k,v in headers.items() if k.lower()=='set-cookie'),None)
            if status!=200 or not cookie:
                raise ValueError('The Lab does not expose API sessions. Restart it with the current code.')
            self.cookie=cookie.split(';',1)[0]
        # A failed write is never replayed: the caller checks its record before retrying.
        return self._request(method,path,body)


def command(args):
    try:
        body=None
        if args.data is not None:
            raw=sys.stdin.read() if args.data=='-' else Path(args.data[1:]).read_text(encoding='utf-8-sig') if args.data.startswith('@') else args.data
            import yaml
            try: body=yaml.safe_load(raw)
            except yaml.YAMLError: raise ValueError('Request data must be a JSON or YAML object.') from None
            if not isinstance(body,dict): raise ValueError('Request data must be an object.')
        path='/api/schema' if args.method=='routes' else args.path
        if not path: raise ValueError('Give an /api/ path, or use arlo api routes.')
        if args.query:
            pairs=[]
            for item in args.query:
                key,sep,value=item.partition('=')
                if not sep or not key: raise ValueError('Use --query name=value.')
                pairs.append((key,value))
            path+=('&' if '?' in path else '?')+urlencode(pairs)
        body=protect('GET' if args.method=='routes' else args.method,path,body)
        if args.secret:
            if args.method!='POST' or not sys.stdin.isatty():
                raise ValueError('--secret requires an interactive POST. For automation, pass a JSON body on stdin.')
            import getpass
            body=dict(body or {})
            for field in args.secret:
                body[field]=getpass.getpass(field+': ')
        hub=Path(args.hub or os.environ.get('ARLOTOPE_HUB') or Path(__file__).resolve().parents[1])
        status,headers,raw=Client(hub,args.port,args.timeout).request('GET' if args.method=='routes' else args.method,path,body)
        if args.output:
            if os.environ.get('ARLOTOPE_RUN_ID'):
                from signature_guard import check_path
                error=check_path(Path(args.output).resolve())
                if error: raise ValueError(error)
            Path(args.output).write_bytes(raw)
        else:
            try: print(json.dumps(json.loads(raw),indent=2,ensure_ascii=False))
            except (ValueError,UnicodeError):
                try: print(raw.decode('utf-8'))
                except UnicodeError: raise ValueError('Use --output FILE to save a binary response.') from None
        return 0 if 200<=status<300 else 1
    except (OSError,ValueError,http.client.HTTPException) as error:
        print('[arlo api] '+str(error),file=sys.stderr)
        return 2
