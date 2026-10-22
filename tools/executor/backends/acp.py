"""Agent Client Protocol v1 over stdio. Native adapters remain independent choices.

Spec: agentclientprotocol.com/protocol/v1/{initialization,session-setup,prompt-turn,tool-calls}.
Only implemented capabilities are advertised. A failed load never silently starts a fresh session.
"""
import json
import subprocess
import threading

from .. import live
from ..procs import kill_tree
from . import Backend, RunCommand, activity, summarize_input, with_preamble
from .acp_tools import ClientTools
from . import acp_forms


class Acp(Backend):
    name = 'acp'
    live_only = True
    sign_in_hint = 'Sign in with the configured ACP agent, then resume this run.'

    def command(self, a):
        if not a.live:
            raise ValueError('ACP requires a live connection. It has no one-shot fallback.')
        return RunCommand(list(a.cli), None, False)

    def session(self, a):
        return AcpSession(with_preamble(a), a.resume_sid, workdir=a.workdir, env=a.env,
                          model=a.model, config=a.bcfg, guard=a.guard, python=a.python,
                          fork_from=a.m.get('fork_session') if not a.resume_sid else None)

    def parse(self, obj):
        return obj.get('events', []) if obj.get('type') == 'arlotope.acp' else []


class AcpSession(live.Session):
    def __init__(self, prompt, session_id=None, **ctx):
        super().__init__(prompt, session_id, **ctx)
        self.sequence, self.calls, self.requests, self.pending = 0, {}, {}, []
        self.turn, self.answer, self.capabilities = None, '', {}
        self.tool_calls = {}
        self.url_elicitations = {}
        self._turn_lock = threading.RLock()
        self.tools = ClientTools(ctx['workdir'], ctx['env'], ctx.get('guard'), ctx.get('python'))

    def rpc(self, method, params):
        with self._wlock:
            self.sequence += 1
            rid = 'client-' + str(self.sequence)
            self.calls[rid] = method
        self._write({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params})
        return rid

    def result(self, rid, result=None, error=None):
        return self._write({'jsonrpc': '2.0', 'id': rid,
                            **({'error': error} if error else {'result': result or {}})})

    def open(self, proc):
        self.proc = proc
        self.rpc('initialize', {'protocolVersion': 1,
            'clientInfo': {'name': 'arlotope', 'version': '2.0'},
            'clientCapabilities': {'fs': {'readTextFile': True, 'writeTextFile': True}, 'terminal': True,
                                   'elicitation': {'form': {}, 'url': {}}}})

    def send(self, text):
        if self.closed:
            return False
        with self._wlock:
            self.pending.append(text)
            self.unread += 1
        self._send_next()
        return True

    def _send_next(self):
        with self._turn_lock:
            if self.turn or not self.session_id or not self.pending or self.closed:
                return
            text = self.pending.pop(0)
            self.answer = ''
            self.turn = self.rpc('session/prompt', {'sessionId': self.session_id,
                                                  'prompt': [{'type': 'text', 'text': text}]})

    def interrupt(self):
        if self.session_id and self.turn:
            self._write({'jsonrpc': '2.0', 'method': 'session/cancel', 'params': {'sessionId': self.session_id}})
        for rid in list(self.requests):
            params = self.requests.pop(rid)
            self.result(rid, {'action': 'cancel'} if params.get('mode') else {'outcome': {'outcome': 'cancelled'}})
            if params.get('mode') == 'url':
                self.url_elicitations.pop(params['elicitationId'], None)
        return True

    def respond(self, req, item):
        rid = req['rpc_id']
        params = self.requests.get(rid)
        if not params:
            return False
        if params.get('mode'):
            result = acp_forms.response(params, item)
            ok = self.result(rid, result)
            if ok:
                self.requests.pop(rid, None)
                if params['mode'] == 'url':
                    if result['action'] == 'accept':
                        self.url_elicitations[params['elicitationId']] = True
                    else:
                        self.url_elicitations.pop(params['elicitationId'], None)
            return ok
        want = 'allow_once' if item.get('allow') else 'reject_once'
        option = next((o for o in params.get('options', []) if o.get('kind') == want), None)
        # Never turn a one-time approval into an allow_always grant.
        result = {'outcome': {'outcome': 'selected', 'optionId': option['optionId']}} if option else {'outcome': {'outcome': 'cancelled'}}
        ok = self.result(rid, result)
        if ok:
            self.requests.pop(rid, None)
        return ok

    def close(self):
        if self.closed:
            return
        self.interrupt()
        self.tools.close()
        super().close()
        self.ended = True
        if self.proc and self.proc.poll() is None:
            kill_tree(self.proc.pid)

    def _client_request(self, method, p, rid):
        try:
            result = self.tools.call(method, p)
            self.result(rid, result)
        except NotImplementedError:
            self.result(rid, error={'code': -32601, 'message': 'Method not supported.'})
        except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
            self.result(rid, error={'code': -32602, 'message': str(error)})

    def handle(self, obj):
        if obj.get('jsonrpc') != '2.0':
            return [], []
        method, p, rid = obj.get('method'), obj.get('params') or {}, obj.get('id')
        events, control = [], []
        if method:
            if method == 'elicitation/create' and rid is not None:
                try:
                    scoped = (p.get('sessionId') == self.session_id and bool(self.session_id)) if 'sessionId' in p else p.get('requestId') in self.calls
                    if not scoped or ('sessionId' in p and 'requestId' in p) or rid in self.requests:
                        raise ValueError('Unknown or duplicate elicitation scope.')
                    value = acp_forms.request(p)
                    if p['mode'] == 'url':
                        if p['elicitationId'] in self.url_elicitations:
                            raise ValueError('Duplicate URL elicitation ID.')
                        self.url_elicitations[p['elicitationId']] = False
                    self.requests[rid] = p
                    return [], [{'event': 'request', 'id': 'acp-' + str(rid), 'rpc_id': rid,
                                 'kind': 'question', 'tool': 'ACP question', 'input': {'elicitation': value}}]
                except (ValueError, TypeError, KeyError) as error:
                    self.result(rid, error={'code': -32602, 'message': str(error)})
                    return [], []
            if method == 'elicitation/complete':
                eid = p.get('elicitationId')
                if isinstance(eid, str) and self.url_elicitations.get(eid):
                    self.url_elicitations.pop(eid, None)
                    return [], [{'event':'elicitation_complete', 'elicitation_id':eid}]
                return [], []
            if p.get('sessionId') != self.session_id or not self.session_id:
                if rid is not None:
                    self.result(rid, error={'code': -32602, 'message': 'Unknown session.'})
                return [], []
            if method == 'session/request_permission' and rid is not None:
                self.requests[rid] = p
                patch = p.get('toolCall') or {}
                call = {**self.tool_calls.get(str(patch.get('toolCallId') or ''), {}),
                        **{k: v for k, v in patch.items() if v is not None}}
                control.append({'event': 'request', 'id': 'acp-' + str(rid), 'rpc_id': rid,
                    'kind': 'permission', 'tool': call.get('name') or call.get('title') or 'Tool',
                    'input': call.get('rawInput') if 'rawInput' in call else call, 'why': call.get('title')})
            elif method == 'session/update':
                u = p.get('update') or {}
                kind = u.get('sessionUpdate')
                if kind == 'agent_message_chunk' and (u.get('content') or {}).get('type') == 'text':
                    chunk = u['content'].get('text', '')
                    self.answer += chunk
                    events.append({'event': 'text', 'text': chunk, 'delta': True})
                elif kind in ('tool_call', 'tool_call_update'):
                    tid = str(u.get('toolCallId') or '')
                    known = tid in self.tool_calls
                    call = self.tool_calls.setdefault(tid, {})
                    call.update({k: v for k, v in u.items() if v is not None})
                    status = call.get('status', 'pending')
                    if not known:
                        tool, value = call.get('name') or call.get('title') or 'Tool', call.get('rawInput')
                        value = value if isinstance(value, dict) else {'input': value} if value is not None else {}
                        locations = call.get('locations') or []
                        if locations and 'file_path' not in value:
                            value = {**value, 'file_path': locations[0].get('path')}
                        events.append({'event': 'action', 'tool': tool, 'input': value, 'tool_use_id': tid,
                                       'kind': {'execute': 'bash', 'fetch': 'search', 'think': 'plan',
                                                'switch_mode': 'plan', 'delete': 'edit', 'move': 'edit',
                                                'other': 'tool'}.get(call.get('kind'), call.get('kind')) or activity(tool, value),
                                       'summary': call.get('title') or summarize_input(tool, value), 'open': True})
                    if status in ('completed', 'failed'):
                        events.append({'event': 'tool_result', 'tool_use_id': tid,
                                       'text': json.dumps(call.get('rawOutput') if call.get('rawOutput') is not None
                                                          else call.get('content') or '')[:4000],
                                       'is_error': status == 'failed'})
                elif kind == 'usage_update':
                    events.append({'event': 'usage', 'usage': u})
            elif rid is not None:
                threading.Thread(target=self._client_request, args=(method, p, rid), daemon=True).start()
        elif rid in self.calls:
            method = self.calls.pop(rid)
            if obj.get('error'):
                self.error = str(obj['error'].get('message') or obj['error'])
                events.append({'event': 'result', 'is_error': True, 'last_message': self.error})
                control.append({'event': 'turn_end'})
                self.turn, self.unread = None, 0
            else:
                result = obj.get('result') or {}
                if method == 'initialize':
                    if result.get('protocolVersion') != 1:
                        self.error = 'The ACP agent did not negotiate protocol version 1.'
                        control.append({'event': 'turn_end'})
                    else:
                        self.capabilities = result.get('agentCapabilities') or {}
                        auth = self.ctx['config'].get('auth_method')
                        if auth:
                            methods = result.get('authMethods') or []
                            match = next((m for m in methods if m.get('id') == auth and m.get('type', 'agent') == 'agent'), None)
                            if not match:
                                self.error = 'The configured ACP authentication method is unavailable. Sign in using the agent CLI.'
                                control.append({'event': 'turn_end'})
                            else:
                                self.rpc('authenticate', {'methodId': auth})
                        else:
                            self._session()
                elif method == 'authenticate':
                    self._session()
                elif method in ('session/new', 'session/load', 'session/fork'):
                    self.session_id = result.get('sessionId') or self.session_id
                    if method == 'session/fork' and self.session_id == self.ctx.get('fork_from'):
                        self.session_id = None
                    if not self.session_id:
                        self.error = 'ACP returned no session ID.'
                        control.append({'event': 'turn_end'})
                    else:
                        events.append({'event': 'start', 'session_id': self.session_id})
                        model = self.ctx.get('model')
                        options = result.get('configOptions') or []
                        match = next((o for o in options if o.get('category') == 'model' or o.get('id') == 'model'), None)
                        if model and match:
                            values = [v for group in match.get('options', []) for v in (group.get('options') or [group])]
                            if any(v.get('value') == model for v in values):
                                self.rpc('session/set_config_option', {'sessionId': self.session_id, 'configId': match['id'], 'value': model})
                            else:
                                self.error = 'The requested model is not offered by this ACP agent.'
                                control.append({'event': 'turn_end'})
                        elif model:
                            self.error = 'This ACP agent does not expose a model selector. Use its default or native adapter.'
                            control.append({'event': 'turn_end'})
                        else:
                            self.send(self.prompt)
                elif method == 'session/set_config_option':
                    self.send(self.prompt)
                elif method == 'session/prompt':
                    with self._turn_lock:
                        self.turn, self.unread = None, max(0, self.unread - 1)
                        reason = result.get('stopReason')
                        if reason in ('refusal', 'max_tokens', 'max_turn_requests'):
                            self.error = 'ACP stopped: ' + reason.replace('_', ' ') + '.'
                        events.append({'event': 'result', 'last_message': self.answer,
                                       'session_id': self.session_id, 'stop_reason': reason,
                                       'is_error': bool(self.error)})
                        if not self.error:
                            self._send_next()
                        if not self.turn:
                            control.append({'event': 'turn_end'})
        return ([{'type': 'arlotope.acp', 'events': events}] if events else []), control

    def _session(self):
        params = {'cwd': str(self.ctx['workdir']), 'mcpServers': self.ctx['config'].get('mcp_servers', [])}
        if self.ctx.get('fork_from'):
            caps = self.capabilities.get('sessionCapabilities') or self.capabilities.get('session') or {}
            if 'fork' not in caps or caps['fork'] is None or caps['fork'] is False:
                self.error = 'This ACP agent does not offer native forks. Choose a new agent with handoff.'
                self.tools.close()
                super().close()
                self.ended = True
                return
            self.rpc('session/fork', {**params, 'sessionId': self.ctx['fork_from']})
            return
        if self.session_id:
            if not self.capabilities.get('loadSession'):
                self.error = 'This ACP agent cannot load the previous session. Start a fresh task or use a handoff.'
                # Closing stdin lets the process exit without executing the task again.
                self.tools.close()
                super().close()
                self.ended = True
                if self.proc and hasattr(self.proc, 'poll') and self.proc.poll() is None:
                    kill_tree(self.proc.pid)
                return
            params['sessionId'] = self.session_id
        self.rpc('session/load' if self.session_id else 'session/new', params)
