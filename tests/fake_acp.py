"""Deterministic ACP peer for protocol tests. No model or external service."""
import json
import os
import sys


def send(obj):
    print(json.dumps({'jsonrpc': '2.0', **obj}), flush=True)


for line in sys.stdin:
    obj = json.loads(line)
    if os.environ.get('FAKE_ACP_LOG'):
        with open(os.environ['FAKE_ACP_LOG'], 'a', encoding='utf-8') as f:
            f.write(line)
    method, rid = obj.get('method'), obj.get('id')
    p = obj.get('params', {})
    if method == 'initialize':
        send({'id': rid, 'result': {'protocolVersion': int(os.environ.get('FAKE_ACP_VERSION', '1')),
             'agentCapabilities': {'loadSession': os.environ.get('FAKE_ACP_LOAD') != 'no'}, 'authMethods': []}})
    elif method in ('session/new', 'session/load'):
        sid = p.get('sessionId', 'fixture-session')
        send({'id': rid, 'result': {'sessionId': sid}})
    elif method == 'session/prompt':
        text = '\n'.join(b.get('text', '') for b in p['prompt'])
        if 'ASK_PERMISSION' in text:
            prompt_id = rid
            send({'id': 700, 'method': 'session/request_permission', 'params': {'sessionId': sid,
                'toolCall': {'toolCallId': 'read', 'title': 'Read evidence'},
                'options': [{'optionId': 'yes', 'name': 'Allow once', 'kind': 'allow_once'},
                            {'optionId': 'no', 'name': 'Reject', 'kind': 'reject_once'}]}})
        else:
            if 'WRITE_RESULT' in text:
                from pathlib import Path
                Path('result.txt').write_text('evidence', encoding='utf-8')
            if 'PUBLISH_SUMMARY' in text or 'one visual page' in text:
                import subprocess
                from pathlib import Path
                page = Path('summary.html')
                page.write_text('<!doctype html><title>Visual summary</title><h1>Recorded work</h1>'
                    '<p>Deterministic test fixture; no research measurements.</p>'
                    '<button onclick="document.querySelector(\'output\').textContent=\'Details opened\'">Show details</button>'
                    '<output>Overview</output>', encoding='utf-8')
                result = subprocess.run([sys.executable, os.environ['ARLOTOPE_WORKER_RUNTIME'], 'artifact',
                    'publish', '--title', 'Visual summary', '--file', str(page),
                    '--about', os.environ['ARLOTOPE_RUN_ID']], capture_output=True, text=True, timeout=25)
                if result.returncode:
                    send({'method': 'session/update', 'params': {'sessionId': sid, 'update': {
                        'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': result.stdout+result.stderr}}}})
                    send({'id': rid, 'result': {'stopReason': 'refusal'}})
                    continue
            if 'REPORT_DONE' in text:
                import subprocess
                result = subprocess.run([sys.executable, os.environ['ARLOTOPE_WORKER_RUNTIME'], 'control',
                    'move', os.environ['ARLOTOPE_RUN_SUBJECT'], 'done'], capture_output=True, text=True, timeout=25)
                if result.returncode:
                    send({'method': 'session/update', 'params': {'sessionId': sid, 'update': {
                        'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': result.stdout+result.stderr}}}})
                    send({'id': rid, 'result': {'stopReason': 'refusal'}})
                    continue
            send({'method': 'session/update', 'params': {'sessionId': sid, 'update': {
                'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': 'Task complete'}}}})
            send({'id': rid, 'result': {'stopReason': 'end_turn'}})
    elif rid == 700 and not method:
        send({'method': 'session/update', 'params': {'sessionId': sid, 'update': {
            'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': 'Decision received'}}}})
        send({'id': prompt_id, 'result': {'stopReason': 'end_turn'}})
    elif method == 'session/cancel':
        pass
