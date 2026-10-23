"""Checking an unsaved agent never changes assignments or starts a model turn."""
import json
import sys

import pytest

from conftest import REPO, load
from test_agent_assignments import configure


def test_unsaved_acp_check_preserves_defaults_and_only_initializes(hub, monkeypatch, tmp_path):
    lab, _ = configure(hub)
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    api = load('dashboard/agent_settings')
    monkeypatch.setattr(api.ctx, 'HUB', hub.root)
    monkeypatch.setattr(api.ctx, 'LAB', hub.lab)
    log = tmp_path / 'protocol.jsonl'
    monkeypatch.setenv('FAKE_ACP_LOG', str(log))
    before = (hub.lab / 'config.yaml').read_bytes()
    value, code = api.check({'agent': {'backend': 'acp', 'label': 'Not saved',
        'command': [sys.executable, str(REPO / 'tests/fake_acp.py')]}})
    assert code == 200 and value['connection']['protocolVersion'] == 1
    assert (hub.lab / 'config.yaml').read_bytes() == before
    assert [json.loads(line)['method'] for line in log.read_text().splitlines()] == ['initialize']
    for command in ('agent --acp', [''], [], ['missing-acp-connection-test-program']):
        result, status = api.check({'agent': {'backend': 'acp', 'command': command}})
        assert status == 400 and result['error']
    assert (hub.lab / 'config.yaml').read_bytes() == before


@pytest.mark.parametrize('result', [
    {'id': 1, 'result': {'protocolVersion': 1}},
    {'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': 2}},
    {'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': 1, 'authMethods': 'not-a-list'}},
    {'jsonrpc': '2.0', 'id': 1, 'result': {'protocolVersion': 1, 'agentInfo': 'not-an-object'}},
])
def test_connection_rejects_non_acp_and_unsupported_protocol(tmp_path, result):
    from executor.acp_probe import probe
    program = 'import sys;sys.stdin.readline();print(' + repr(json.dumps(result)) + ',flush=True)'
    with pytest.raises(ValueError, match='initialization|negotiate'):
        probe([sys.executable, '-u', '-c', program], tmp_path, timeout=2)


def test_connection_timeout_exits_owned_process(tmp_path):
    from executor.acp_probe import probe
    with pytest.raises(ValueError, match='timed out'):
        probe([sys.executable, '-u', '-c', 'import sys;sys.stdin.readline();sys.stdin.read()'], tmp_path, timeout=.1)


def test_command_prefix_resolves_program_and_preserves_arguments(tmp_path, monkeypatch):
    from executor import backends
    from executor.acp_probe import probe
    monkeypatch.setattr(backends.shutil, 'which', lambda name: sys.executable if name == 'test-acp-launcher' else None)
    arguments = [str(REPO / 'tests/fake_acp.py')]
    command = backends.resolve_cli('acp', {'command': ['test-acp-launcher', *arguments]})
    assert command == [sys.executable, *arguments]
    assert probe(command, tmp_path)['protocolVersion'] == 1
    assert backends.resolve_cli('acp', {'command': ['missing-program', 'argument with spaces']}) == [
        'missing-program', 'argument with spaces']
