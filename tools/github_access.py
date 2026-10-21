"""Reuse GitHub CLI authentication. The Lab never requests or stores its token."""
import json
import os
import shutil
import subprocess


def _run(args):
    cli = shutil.which('gh')
    if not cli:
        raise ValueError('Install GitHub CLI, or attach an existing checkout. Public repository URLs work without signing in.')
    try:
        result = subprocess.run([cli, *args], capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=15, env={**os.environ, 'GH_PROMPT_DISABLED': '1'})
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('GitHub did not respond. Retry, or attach a local checkout.') from None
    if result.returncode:
        raise ValueError('GitHub could not read that resource. Check your sign-in and repository access, then retry.')
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise ValueError('GitHub CLI returned an unreadable response. Update it or attach a local checkout.') from None


def status():
    if not shutil.which('gh'):
        return {'ok': True, 'installed': False, 'connected': False}
    try:
        data = _run(['auth', 'status', '--active', '--hostname', 'github.com', '--json', 'hosts'])
        accounts = (data.get('hosts') or {}).get('github.com', [])
        account = next((a for a in accounts if a.get('active') and a.get('state') == 'success'), None)
        return {'ok': True, 'installed': True, 'connected': bool(account), 'login': account.get('login') if account else None}
    except ValueError:
        return {'ok': True, 'installed': True, 'connected': False,
                'notice': 'Sign in or check your GitHub connection, then retry.'}


def repositories():
    data = _run(['api', '--hostname', 'github.com', 'user/repos?sort=pushed&per_page=50'])
    if not isinstance(data, list):
        raise ValueError('Could not list repositories.')
    return {'ok': True, 'repositories': [{'name': r['full_name'], 'private': bool(r.get('private'))}
                                       for r in data if isinstance(r, dict) and r.get('full_name')],
            'more': len(data) == 50}


def repository(name):
    # Callers validate owner/repository before constructing this fixed-host resource path.
    return _run(['api', '--hostname', 'github.com', 'repos/' + name])


def login_argv():
    cli = shutil.which('gh')
    return [cli, 'auth', 'login', '--hostname', 'github.com', '--web'] if cli else None


def clone_argv(repo, destination):
    cli = shutil.which('gh')
    if not cli:
        raise ValueError('GitHub CLI is unavailable. Reconnect GitHub or attach a local checkout.')
    return [cli, 'repo', 'clone', 'https://github.com/' + repo + '.git', str(destination)]
