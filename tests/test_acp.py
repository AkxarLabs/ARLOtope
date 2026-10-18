"""ACP contract, real stdio process and client filesystem/terminal capabilities."""
import io
import json
import os
import subprocess
import sys
import time
import threading
from pathlib import Path

import pytest

from conftest import REPO
sys.path.insert(0, str(REPO/'tools'))
from executor.backends.acp import AcpSession
from executor.backends.acp_tools import ClientTools
from executor.supervise import run_process


def session(tmp_path, sid=None):
    s = AcpSession('work', sid, workdir=tmp_path, env=os.environ.copy(), config={})
    s.proc = type('Proc', (), {'stdin': io.StringIO()})()
    return s


def reply(s, method, result):
    rid = s.rpc(method, {})
    return s.handle({'jsonrpc': '2.0', 'id': rid, 'result': result})


def test_capabilities_and_resume_fail_closed(tmp_path):
    s = session(tmp_path, 'old')
    reply(s, 'initialize', {'protocolVersion': 1, 'agentCapabilities': {}})
    assert s.error and 'cannot load' in s.error and s.closed
    s = session(tmp_path)
    reply(s, 'initialize', {'protocolVersion': 9})
    assert 'version 1' in s.error


def test_elicitation_typed_response_and_invalid_submission(tmp_path):
    s = session(tmp_path, 'sid')
    form = {'sessionId':'sid','mode':'form','message':'Configure the review', 'requestedSchema':{
        'type':'object','properties':{'seeds':{'type':'integer','minimum':1},'blind':{'type':'boolean'},
        'method':{'type':'string','enum':['a','b']}},'required':['seeds','blind']}}
    _, events = s.handle({'jsonrpc':'2.0','id':70,'method':'elicitation/create','params':form})
    assert events[0]['kind'] == 'question'
    with pytest.raises(ValueError, match='integer'):
        s.respond(events[0], {'action':'accept','content':{'seeds':True,'blind':False}})
    assert 70 in s.requests
    assert s.respond(events[0], {'content':{'seeds':3,'blind':False,'method':'a'}})
    result = json.loads(s.proc.stdin.getvalue().splitlines()[-1])['result']
    assert result == {'action':'accept','content':{'seeds':3,'blind':False,'method':'a'}}


@pytest.mark.parametrize('action',['decline','cancel'])
def test_elicitation_can_be_declined_or_cancelled(tmp_path, action):
    s=session(tmp_path,'sid')
    _, events=s.handle({'jsonrpc':'2.0','id':4,'method':'elicitation/create','params':{
        'sessionId':'sid','mode':'url','message':'Sign in','url':'https://example.org/login','elicitationId':'external'}})
    assert s.respond(events[0],{'action':action})
    assert json.loads(s.proc.stdin.getvalue().splitlines()[-1])['result']=={'action':action}


def test_elicitation_scope_and_native_fork_capability(tmp_path):
    s=session(tmp_path,'sid')
    assert s.handle({'jsonrpc':'2.0','id':8,'method':'elicitation/create','params':{
        'sessionId':'other','mode':'form','requestedSchema':{'type':'object'}}}) == ([],[])
    assert json.loads(s.proc.stdin.getvalue().splitlines()[-1])['error']['code']==-32602
    s=session(tmp_path)
    s.ctx['fork_from']='source'
    reply(s,'initialize',{'protocolVersion':1,'agentCapabilities':{'sessionCapabilities':{'fork':{}}}})
    assert json.loads(s.proc.stdin.getvalue().splitlines()[-1])['method']=='session/fork'
    reply(s,'session/fork',{'sessionId':'child'})
    assert s.session_id=='child' and s.turn


def test_url_completion_is_scoped_and_only_applied_once(tmp_path):
    s=session(tmp_path,'sid')
    _,ev=s.handle({'jsonrpc':'2.0','id':1,'method':'elicitation/create','params':{
        'sessionId':'sid','mode':'url','url':'https://example.org/login','message':'Connect','elicitationId':'opaque'}})
    complete=lambda eid:s.handle({'jsonrpc':'2.0','method':'elicitation/complete','params':{'elicitationId':eid}})
    assert complete('unknown')==([],[])
    assert s.respond(ev[0],{'action':'accept'})
    assert complete('opaque')[1]==[{'event':'elicitation_complete','elicitation_id':'opaque'}]
    assert complete('opaque')==([],[])


def test_titled_multiple_choices_and_invalid_nested_schema():
    from executor.backends.acp_forms import validate_content, schema_fields
    schema={'type':'object','properties':{'datasets':{'type':'array','minItems':1,'items':{'anyOf':[
        {'const':'a','title':'Dataset A'},{'const':'b','title':'Dataset B'}]}}},'required':['datasets']}
    assert validate_content(schema,{'datasets':['b']})=={'datasets':['b']}
    with pytest.raises(ValueError):validate_content(schema,{'datasets':[]})
    with pytest.raises(ValueError):validate_content(schema,{'datasets':['a','a']})
    with pytest.raises(ValueError):schema_fields({'properties':{'nested':{'type':'object'}}})


def test_acp_fork_without_capability_fails_without_prompting(tmp_path):
    s=session(tmp_path);s.ctx['fork_from']='source'
    reply(s,'initialize',{'protocolVersion':1,'agentCapabilities':{}})
    assert s.error and s.closed and 'native forks' in s.error


def test_permission_uses_once_and_cancellation(tmp_path):
    s = session(tmp_path, 'sid')
    _, events = s.handle({'jsonrpc': '2.0', 'id': 7, 'method': 'session/request_permission', 'params': {
        'sessionId': 'sid', 'toolCall': {'title': 'Write'}, 'options': [{'kind': 'allow_always', 'optionId': 'forever'}]}})
    s.respond(events[0], {'allow': True})
    assert json.loads(s.proc.stdin.getvalue().splitlines()[-1])['result']['outcome']['outcome'] == 'cancelled'
    s.turn = 'turn'
    s.handle({'jsonrpc': '2.0', 'id': 8, 'method': 'session/request_permission', 'params': {'sessionId': 'sid'}})
    s.interrupt()
    assert not s.requests
    assert 'session/cancel' in s.proc.stdin.getvalue()


def test_streamed_text_is_delta_and_tool_failures_keep_their_evidence(tmp_path):
    s = session(tmp_path, 'sid')
    def update(value):
        lines, _ = s.handle({'jsonrpc': '2.0', 'method': 'session/update',
                            'params': {'sessionId': 'sid', 'update': value}})
        return lines[0]['events']
    text = [update({'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': chunk}})[0]
            for chunk in ('Hello', ' world')]
    assert ''.join(event['text'] for event in text) == s.answer == 'Hello world'
    assert all(event['delta'] for event in text)
    started = update({'sessionUpdate': 'tool_call', 'toolCallId': 'edit', 'title': 'Update notes',
                      'kind': 'edit', 'rawInput': False, 'locations': [{'path': str(tmp_path / 'notes.md')}]})
    assert started[0]['input']['input'] is False and started[0]['kind'] == 'edit'
    failed = update({'sessionUpdate': 'tool_call_update', 'toolCallId': 'edit', 'status': 'failed',
                     'rawOutput': 'Permission denied'})
    assert failed[0]['is_error'] and 'Permission denied' in failed[0]['text']
    instant = update({'sessionUpdate': 'tool_call', 'toolCallId': 'instant', 'title': 'Read file', 'status': 'completed'})
    assert [event['event'] for event in instant] == ['action', 'tool_result']


def test_permission_uses_metadata_from_prior_tool_update(tmp_path):
    s = session(tmp_path, 'sid')
    s.handle({'jsonrpc': '2.0', 'method': 'session/update', 'params': {'sessionId': 'sid',
        'update': {'sessionUpdate': 'tool_call', 'toolCallId': 'read', 'title': 'Read evidence', 'rawInput': False}}})
    _, events = s.handle({'jsonrpc': '2.0', 'id': 10, 'method': 'session/request_permission',
        'params': {'sessionId': 'sid', 'toolCall': {'toolCallId': 'read'}, 'options': []}})
    assert events[0]['tool'] == 'Read evidence' and events[0]['input'] is False


def test_terminal_output_is_live_bounded_and_valid_utf8(tmp_path):
    tools = ClientTools(tmp_path, os.environ.copy())
    try:
        terminal = tools.call('terminal/create', {'command': sys.executable, 'args': [
            '-c', 'import sys,time;sys.stdout.buffer.write("ééé".encode());sys.stdout.flush();time.sleep(1)'],
            'outputByteLimit': 3})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            output = tools.call('terminal/output', terminal)
            if output['output']:
                break
            time.sleep(.02)
        assert output['truncated'] and output['output'] == 'é'
        assert '\ufffd' not in output['output']
        with pytest.raises(ValueError, match='absolute'):
            tools.call('terminal/create', {'command': sys.executable, 'cwd': 'relative'})
    finally:
        tools.close()


@pytest.mark.parametrize('reason', ['refusal', 'max_tokens', 'max_turn_requests'])
def test_incomplete_acp_turn_is_a_failure(tmp_path, reason):
    s = session(tmp_path, 'sid')
    lines, events = reply(s, 'session/prompt', {'stopReason': reason})
    assert s.error and lines[0]['events'][0]['is_error']
    assert events == [{'event': 'turn_end'}]


def test_model_selected_only_from_negotiated_options(tmp_path):
    s = session(tmp_path)
    s.ctx['model'] = 'offered'
    reply(s, 'session/new', {'sessionId': 'sid', 'configOptions': [
        {'id': 'model-id', 'category': 'model', 'options': [{'value': 'offered', 'name': 'Offered'}]}]})
    request = json.loads(s.proc.stdin.getvalue().splitlines()[-1])
    assert request['method'] == 'session/set_config_option' and request['params']['value'] == 'offered'
    s = session(tmp_path)
    s.ctx['model'] = 'not-offered'
    reply(s, 'session/new', {'sessionId': 'sid'})
    assert 'default or native' in s.error and not s.turn


@pytest.mark.parametrize('kind, expected', [('fetch', 'search'), ('think', 'plan'),
    ('switch_mode', 'plan'), ('move', 'edit'), ('delete', 'edit'), ('execute', 'bash'), ('other', 'tool')])
def test_protocol_tool_kinds_use_dashboard_activities(tmp_path, kind, expected):
    s = session(tmp_path, 'sid')
    lines, _ = s.handle({'jsonrpc': '2.0', 'method': 'session/update', 'params': {
        'sessionId': 'sid', 'update': {'sessionUpdate': 'tool_call', 'toolCallId': 't',
                                      'title': 'Vendor tool', 'kind': kind}}})
    assert lines[0]['events'][0]['kind'] == expected


def test_terminal_exit_waits_for_final_output_drain(tmp_path):
    tools = ClientTools(tmp_path, os.environ.copy())
    done = threading.Event()
    record = {'proc': type('Proc', (), {'poll': lambda self: 0})(),
              'output': bytearray(b'first'), 'truncated': False, 'done': done}
    tools.terminals['t'] = record
    assert 'exitStatus' not in tools.call('terminal/output', {'terminalId': 't'})
    record['output'].extend(b' last')
    done.set()
    output = tools.call('terminal/output', {'terminalId': 't'})
    assert output['exitStatus']['exitCode'] == 0 and output['output'] == 'first last'


def test_files_and_terminals(tmp_path):
    tools = ClientTools(tmp_path, os.environ.copy())
    file = tmp_path / 'notes.txt'
    tools.call('fs/write_text_file', {'path': str(file), 'content': 'one\ntwo\nthree'})
    assert tools.call('fs/read_text_file', {'path': str(file), 'line': 2, 'limit': 1}) == {'content': 'two\n'}
    with pytest.raises(ValueError):
        tools.call('fs/read_text_file', {'path': 'relative'})
    term = tools.call('terminal/create', {'command': sys.executable, 'args': ['-c', 'print("hello")']})
    assert tools.call('terminal/wait_for_exit', term)['exitCode'] == 0
    assert 'hello' in tools.call('terminal/output', term)['output']
    tools.close()
    assert not tools.terminals


@pytest.mark.parametrize('previous', [None, 'previous-session'])
def test_real_acp_stdio(tmp_path, previous):
    log = tmp_path / 'rpc.jsonl'
    env = {**os.environ, 'FAKE_ACP_LOG': str(log)}
    s = AcpSession('work', previous, workdir=tmp_path, env=env, config={})
    class Conversation:
        def tick(self):
            return False
        def waiting(self):
            return False
    def event(ev):
        if ev.get('event') == 'turn_end':
            s.close()
    result = run_process([sys.executable, str(REPO/'tests/fake_acp.py')], cwd=tmp_path,
        env=env, stream_path=tmp_path/'stream.jsonl', backend='acp', max_seconds=15,
        live=s, conv=Conversation(), on_event=event)
    assert result.rc == 0 and result.session_id == (previous or 'fixture-session')
    assert result.last_message == 'Task complete'
    calls = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    methods = [call.get('method') for call in calls]
    assert ('session/load' in methods) == bool(previous)
    assert ('session/new' in methods) == (not previous)
    assert methods.index('session/load' if previous else 'session/new') < methods.index('session/prompt')
    prompt = next(call['params'] for call in calls if call.get('method') == 'session/prompt')
    assert prompt['sessionId'] == (previous or 'fixture-session')
