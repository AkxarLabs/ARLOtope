"""Connection recovery and worker-version admission, without a real SSH account."""
import importlib
import json
import os
import subprocess
import time
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from conftest import REPO


@pytest.fixture
def connection(hub, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    monkeypatch.syspath_prepend(str(REPO / 'tools'))
    machines = importlib.import_module('machines')
    setup = importlib.import_module('project_machines')
    monkeypatch.setenv('ARLOTOPE_HOME', str(tmp_path / 'home'))
    monkeypatch.setattr(machines.ctx, 'HUB', hub.root)
    monkeypatch.setattr(machines.ctx, 'LAB', hub.lab)
    monkeypatch.setattr(setup, 'CONNS', {})
    machine = {'id': 'box', 'host': 'box', 'name': 'Compute', 'labs': []}
    machines._put(machine)
    return machines, setup, machine


def test_adding_a_host_reuses_it_and_connect_does_not_probe_twice(connection, monkeypatch):
    machines, _, _ = connection
    monkeypatch.setattr(machines, 'probe', lambda _: pytest.fail('Unexpected SSH probe'))
    first, code = machines.add_machine({'host': 'new-host', 'probe': False})
    assert code == 200
    second, code = machines.add_machine({'host': 'new-host', 'name': 'A different display name'})
    assert code == 200 and second['machine']['id'] == first['machine']['id']
    assert len(machines._load()) == 2


def test_authentication_handoff_and_current_status(connection, monkeypatch):
    machines, setup, machine = connection
    conn = setup.ProjectConn(machine)
    monkeypatch.setattr(conn, 'alive', lambda **_: False)
    monkeypatch.setattr(machines, '_run', lambda *_, **__: subprocess.CompletedProcess([], 255, b'', b'Permission denied (publickey,password)'))
    setup.CONNS['box'] = conn
    assert conn.connect()['needs_interactive'] is True
    assert setup.view()[0]['machines'][0]['state'] == 'auth'
    conn.state, conn.want = 'waiting', True
    assert conn.connect(True)['state'] == 'waiting'
    conn.state, conn.error = 'error', 'SSH window closed'
    assert machines.list_machines()[0]['machines'][0]['worker']['state'] == 'error'
    assert setup.view()[0]['machines'][0]['error'] == 'SSH window closed'


def test_closed_auth_window_and_cancel_stop_waiting(connection, monkeypatch):
    _, setup, machine = connection
    conn = setup.ProjectConn(machine)
    conn.pidfile.parent.mkdir(parents=True, exist_ok=True)
    conn.pidfile.write_text('12345')
    conn.want, conn.window, conn.state = True, True, 'waiting'
    monkeypatch.setattr('executor.procs.pid_alive', lambda _: False)
    assert not conn._wait(1)
    assert conn.state == 'error' and 'closed' in conn.error
    conn.want = False
    assert not conn._wait(1)


def test_missed_signin_expires_and_closes_its_old_ssh_process(connection, monkeypatch):
    machines,setup,machine=connection
    conn=setup.ProjectConn(machine)
    conn.want,conn.window,conn.state=True,True,'waiting'
    conn.pidfile.parent.mkdir(parents=True,exist_ok=True);conn.pidfile.write_text('12345')
    conn.sessionfile.write_text('{}');conn.login_deadline=time.time()+1
    monkeypatch.setattr(conn,'_wait',lambda _:False)
    killed=[];monkeypatch.setattr('executor.procs.kill_tree',lambda pid:killed.append(pid))
    conn._await_window()
    assert killed==[12345] and not conn.pidfile.exists() and not conn.sessionfile.exists()
    assert conn.state=='auth' and 'timed out' in conn.error and conn.login_deadline is None
    assert machines._get('box')['host']=='box'


def test_network_bootstrap_retries_but_authentication_does_not(connection, monkeypatch):
    machines,setup,machine=connection
    conn=setup.ProjectConn(machine)
    monkeypatch.setattr(conn,'alive',lambda **_:False)
    monkeypatch.setattr(machines.Conn,'connect',lambda *args:{'ok':True,'state':'connected'})
    packet={'arlotope_worker_session':True,'build':conn.build,'uid':'1001','pid':123,'cookie':'worker=test','port':conn.rport}
    calls=[];delays=[]
    responses=[subprocess.CompletedProcess([],255,b'',b'Connection timed out'),subprocess.CompletedProcess([],0,json.dumps(packet).encode(),b'')]
    def run(*_,**__):calls.append(1);return responses.pop(0)
    monkeypatch.setattr(machines,'_run',run);monkeypatch.setattr(setup.time,'sleep',delays.append)
    assert conn.connect()['state']=='connected' and len(calls)==2 and delays==[1]
    calls.clear();responses[:]=[subprocess.CompletedProcess([],255,b'',b'Permission denied (password)')]
    assert conn.connect()['needs_interactive'] and len(calls)==1


def test_transient_retry_is_bounded(connection,monkeypatch):
    machines,setup,machine=connection
    conn=setup.ProjectConn(machine);calls=[]
    monkeypatch.setattr(conn,'alive',lambda **_:False)
    def run(*_,**__):calls.append(1);raise subprocess.TimeoutExpired('ssh',60)
    monkeypatch.setattr(machines,'_run',run);monkeypatch.setattr(setup.time,'sleep',lambda _:None)
    assert conn.connect()['error'] and len(calls)==3


def test_initial_project_list_has_the_same_ownership_as_discovery(connection, monkeypatch, hub):
    _, setup, _ = connection
    from project_identity import lab_identity
    owner = lab_identity(hub.root)['execution_owner']
    rows = [{'owner':owner,'registered':True,'path':'/our/project'},
            {'owner':'other','registered':True,'path':'/other/project'}]
    monkeypatch.setattr(setup.R, 'rpc', lambda _, method, *args: {'projects':rows} if method == 'info' else rows)
    inspected, _ = setup.inspect({'id':'box'})
    discovered, _ = setup.projects({'machine':'box'})
    assert inspected['projects'] == discovered['projects']
    assert [r['ours'] for r in inspected['projects']] == [True, False]


def test_worker_build_has_its_own_port_and_old_build_is_refused(connection, monkeypatch):
    _, setup, machine = connection
    first = setup.ProjectConn(machine)
    monkeypatch.setattr(setup.R, 'bundle', lambda: ('new-build', b'package'))
    second = setup.ProjectConn(machine)
    assert first.rport != second.rport
    class HTTP:
        def __init__(self, *_, **__): pass
        def request(self, *_): pass
        def getresponse(self): return self
        def read(self): return json.dumps({'app':'arlotope-worker','protocol':1,'build':first.build}).encode()
        def close(self): pass
    monkeypatch.setattr('http.client.HTTPConnection', HTTP)
    assert second.alive() is False


def test_session_only_comes_from_bootstrap_and_matches_account(connection, monkeypatch):
    _, setup, machine = connection
    conn=setup.ProjectConn(machine)
    packet={'arlotope_worker_session':True,'build':conn.build,'uid':'1001','pid':123,
            'cookie':'worker=test-only','port':conn.rport}
    assert conn._session(json.dumps(packet).encode())
    assert conn.remote_uid == '1001'
    class HTTP:
        def __init__(self,*_,**__): pass
        def request(self,*_): pass
        def getresponse(self): return self
        def read(self): return json.dumps({'app':'arlotope-worker','protocol':1,'build':conn.build,'uid':'1002'}).encode()
        def close(self): pass
    monkeypatch.setattr('http.client.HTTPConnection',HTTP)
    assert not conn.alive()
    assert not conn._session(json.dumps({**packet,'build':'old-build'}).encode())


def test_restarted_worker_rotates_session_and_reauthenticates(connection, monkeypatch):
    machines, setup, machine = connection
    conn=setup.ProjectConn(machine)
    packet={'arlotope_worker_session':True,'build':conn.build,'uid':'1001','pid':123,
            'cookie':'worker=old','port':conn.rport}
    conn._session(json.dumps(packet).encode())
    replacement={**packet,'pid':456,'cookie':'worker=new'}
    class HTTP:
        def __init__(self,*_,**__): pass
        def request(self,*_): pass
        def getresponse(self): return self
        def read(self): return json.dumps({'app':'arlotope-worker','protocol':1,**replacement}).encode()
        def close(self): pass
    monkeypatch.setattr('http.client.HTTPConnection',HTTP)
    assert not conn.alive()
    monkeypatch.setattr(machines,'_run',lambda *_,**__:subprocess.CompletedProcess([],0,json.dumps(replacement).encode(),b''))
    monkeypatch.setattr(conn,'_wait',lambda _:conn.cookie=='worker=new' and conn.remote_pid==456)
    assert conn._restart_remote()


def test_retry_closes_the_old_tunnel_even_after_its_window_state_was_lost(connection, monkeypatch):
    _, setup, machine = connection
    conn=setup.ProjectConn(machine)
    conn.state,conn.window='auth',False
    conn.pidfile.parent.mkdir(parents=True,exist_ok=True);conn.pidfile.write_text('12345')
    killed=[];monkeypatch.setattr('executor.procs.kill_tree',lambda pid:killed.append(pid))
    setup.CONNS['box']=conn
    monkeypatch.setattr(setup.ProjectConn,'connect',lambda self,interactive=False:{'ok':True,'state':'waiting'})
    setup.connect({'id':'box','confirm':True,'interactive':True})
    assert killed==[12345]
    assert setup.CONNS['box'] is not conn and not conn.want


def test_background_worker_refuses_a_foreign_account(connection, monkeypatch):
    import project_worker
    monkeypatch.setattr(sys,'argv',['worker.py','serve','--background','--port','43210'])
    monkeypatch.setattr(project_worker,'user_id',lambda:'1001')
    class HTTP:
        def __init__(self,*_,**__): pass
        def request(self,*_): pass
        def getresponse(self): return self
        def read(self): return json.dumps({'app':'arlotope-worker','protocol':1,'build':'worker','uid':'1002'}).encode()
    monkeypatch.setattr('http.client.HTTPConnection',HTTP)
    with pytest.raises(ValueError,match='another account'):
        project_worker.main()


def test_interactive_helper_hides_cookie_but_records_readiness(tmp_path):
    packet={'arlotope_worker_session':True,'cookie':'worker=fixture-secret','uid':'1001'}
    spec={'argv':[sys.executable,'-u','-c','import json;print('+repr(json.dumps(packet))+');print("Connected")'],
          'pidfile':str(tmp_path/'ssh.pid'),'sessionfile':str(tmp_path/'session.json')}
    path=tmp_path/'setup.json';path.write_text(json.dumps(spec))
    result=subprocess.run([sys.executable,str(REPO/'tools/ssh_worker_install.py'),str(path)],capture_output=True,timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    assert b'fixture-secret' not in result.stdout and b'Connected' in result.stdout
    assert json.loads((tmp_path/'session.json').read_text()) == packet


def test_worker_versions_share_dispatch_receipt_lock(tmp_path, monkeypatch, connection):
    from project_worker import Worker
    root = tmp_path / 'project'; root.mkdir()
    data = {'path':str(root),'owner':'lab','study':'study','run_id':'run',
            'manifest':{'run_id':'run','status':'starting','attempt':0},
            'prompt':'Task','preamble':'Protocol','instructions':{},'config':{}}
    workers = [Worker('old.pyz'), Worker('new.pyz')]
    workers[0].root(data, claim=True)
    launches = []
    def spawn(*args, **kwargs):
        launches.append(args)
        time.sleep(.1)
        return SimpleNamespace(pid=os.getpid())
    monkeypatch.setattr(subprocess, 'Popen', spawn)
    monkeypatch.setattr('executor.procs.pid_alive', lambda _: True)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda w: w.call('dispatch', data), workers))
    assert len(launches) == 1
    assert results[0] == results[1]
