"""GitHub sign-in stays in gh; only account/repository metadata reaches the dashboard."""
import json
from types import SimpleNamespace

import pytest

from conftest import REPO, load


@pytest.fixture
def github(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'tools'))
    import github_access
    monkeypatch.setattr(github_access.shutil, 'which', lambda name: '/tools/gh' if name == 'gh' else '/tools/git')
    return github_access


def test_connection_reads_status_not_tokens_and_does_not_trust_json_exit_code(github, monkeypatch):
    calls = []
    def run(argv, **kw):
        calls.append((argv, kw))
        return SimpleNamespace(returncode=0, stdout=json.dumps({'hosts': {'github.com': [
            {'active': True, 'state': 'error', 'login': 'not-connected', 'token': 'must-not-leak'}]}}))
    monkeypatch.setattr(github.subprocess, 'run', run)
    value = github.status()
    assert not value['connected'] and 'token' not in json.dumps(value)
    assert '--show-token' not in calls[0][0] and calls[0][1]['env']['GH_PROMPT_DISABLED'] == '1'
    monkeypatch.setattr(github.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0,
        stdout=json.dumps({'hosts': {'github.com': [{'active': True, 'state': 'success', 'login': 'scientist'}]}})))
    assert github.status()['login'] == 'scientist'


def test_missing_cli_keeps_public_path_available(github, monkeypatch):
    monkeypatch.setattr(github.shutil, 'which', lambda _: None)
    assert github.status() == {'ok': True, 'installed': False, 'connected': False}
    assert github.login_argv() is None


def test_repository_listing_is_bounded_and_returns_only_display_metadata(github, monkeypatch):
    calls = []
    monkeypatch.setattr(github, '_run', lambda argv: calls.append(argv) or [
        {'full_name': 'org/private-study', 'private': True, 'other': 'not-needed'}])
    assert github.repositories()['repositories'] == [{'name': 'org/private-study', 'private': True}]
    assert calls == [['api', '--hostname', 'github.com', 'user/repos?sort=pushed&per_page=50']]


def test_private_lookup_uses_existing_sign_in(github, monkeypatch):
    start = load('research_start')
    calls = []
    monkeypatch.setattr(github, '_run', lambda argv: calls.append(argv) or {
        'full_name': 'org/private-study', 'private': True, 'description': 'Research'})
    assert start.github('org/private-study', authenticated=True)['private']
    assert calls == [['api', '--hostname', 'github.com', 'repos/org/private-study']]
    for name in ('--help', '../private', 'org/../private', 'https://elsewhere.example/study'):
        with pytest.raises(ValueError): start.github(name, authenticated=True)
    assert len(calls) == 1


def test_login_uses_fixed_browser_flow(github, hub, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    term = load('dashboard/term')
    argv, error = term.command_for('login', 'github')
    assert not error and argv == ['/tools/gh', 'auth', 'login', '--hostname', 'github.com', '--web']


def test_private_clone_uses_gh_without_install_or_login(github, hub, monkeypatch):
    from pathlib import Path
    start = load('research_start')
    calls = []
    def clone(argv, **kwargs):
        calls.append((argv, kwargs));Path(argv[-1]).mkdir()
        (Path(argv[-1])/'README.md').write_text('Existing private research')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(start.subprocess, 'run', clone)
    result = start.create(hub.root, title='Private project', question='Inspect the existing research.',
                          repo='org/private-study', github_auth=True)
    assert calls[0][0][:4] == ['/tools/gh', 'repo', 'clone', 'https://github.com/org/private-study.git']
    assert calls[0][1]['env']['GH_PROMPT_DISABLED'] == '1'
    assert (Path(result['project'])/'README.md').read_text() == 'Existing private research'
    assert len(calls) == 1
