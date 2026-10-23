"""Attach-first onboarding preserves existing work and never grants workflow approvals."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from conftest import kernel, load


@pytest.fixture
def start():
    return load('research_start')


def test_attach_preserves_existing_code_environment_and_runner(hub, tmp_path, start):
    project = tmp_path / 'existing-research'
    project.mkdir()
    files = {'analysis.R': 'print(1)\n', 'requirements.txt': 'custom-stack==1\n',
             'notebook.ipynb': '{"cells": []}', 'AGENTS.md': 'My own instructions.\n'}
    for rel, content in files.items():
        (project / rel).write_text(content, encoding='utf-8')
    before = {p.name: p.read_bytes() for p in project.iterdir()}
    result = start.create(hub.root, title='Existing science', question='Understand the existing model.', local=str(project))
    assert result['project'] == str(project.resolve()) and not result['cloned']
    assert {p.name: p.read_bytes() for p in project.iterdir() if p.is_file()} == before
    assert {p.name for p in project.iterdir()} == set(before) | {'.arlotope'}
    identity = json.loads((project / '.arlotope/project.json').read_text(encoding='utf-8'))
    assert identity['project_id'] and identity['knowledge_dir'] == '.arlotope/knowledge'
    study = kernel().studies.study(hub.root, result['study'])
    assert study['step'] == kernel().model.workflow(hub=hub.root)['path'][0]
    assert kernel().journal.approvals(hub.root) == []
    assert not (hub.root / 'lab/.bus/agents').exists()
    text = (hub.root / 'studies/existing-science/IDEA.md').read_text(encoding='utf-8')
    assert 'project_mode: attached' in text and 'Understand the existing model.' in text


def test_topic_creates_only_a_research_record(hub, start):
    result = start.create(hub.root, title='A question', question='Why this mechanism?', workflow='quick')
    assert result['project'] is None and result['workflow'] == 'quick'
    assert not list(hub.projects_root.iterdir())
    assert (hub.root / 'studies/a-question/IDEA.md').is_file()
    with pytest.raises(start.StartError, match='already exists'):
        start.create(hub.root, title='A question', question='A duplicate')
    assert len([e for e in kernel().journal.events(hub.root) if e['kind'] == 'new']) == 1


@pytest.mark.parametrize('fields', [
    {'title': ''}, {'title': 'x'*201}, {'question': ''}, {'question': []}, {'slug': '../escape'},
    {'workflow': 'missing'}, {'local': 'relative/path'}, {'local': '/does/not/exist'},
    {'local': 'a', 'repo': 'owner/name'}, {'repo': 'https://evil.example/owner/repo'},
    {'repo': 'owner/..'}, {'repo': 'owner/repo;calc'}, {'slug': 42},
])
def test_invalid_start_does_not_leave_a_study(hub, start, fields):
    with pytest.raises((start.StartError, kernel().studies.StudyError)):
        start.create(hub.root, **({'title': 'A study', 'question': 'Research this.'} | fields))
    assert kernel().studies.rows(hub.root) == []
    assert not (hub.root / 'studies/a-study').exists()


def test_agent_cannot_use_starter_to_impersonate_the_researcher(hub, start, monkeypatch):
    monkeypatch.setenv('ARLOTOPE_RUN_ID', 'an-agent')
    with pytest.raises(start.StartError, match='researcher'):
        start.create(hub.root, title='A study', question='Research this.')


def test_hub_cannot_be_attached_as_its_own_project(hub, start):
    for path in (hub.root, hub.root.parent):
        with pytest.raises(start.StartError, match='separate'):
            start.create(hub.root, title='A study', question='Research this.', local=str(path))


def test_clone_uses_fixed_github_url_without_installing_or_running_code(hub, start, monkeypatch):
    calls = []
    monkeypatch.setattr(start.shutil, 'which', lambda _name: 'git')
    def clone(args, **options):
        calls.append((args, options))
        checkout = Path(args[-1]); checkout.mkdir()
        (checkout / 'README.md').write_text('Existing project', encoding='utf-8')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(start.subprocess, 'run', clone)
    result = start.create(hub.root, title='My clone', question='Investigate.', repo='https://github.com/numpy/numpy.git')
    assert result['cloned'] and (Path(result['project']) / 'README.md').is_file()
    assert len(calls) == 1 and calls[0][0][:4] == ['git', 'clone', '--', 'https://github.com/numpy/numpy.git']
    assert calls[0][1]['env']['GIT_TERMINAL_PROMPT'] == '0'
    assert not list(hub.projects_root.glob('.arlotope-clone-*'))


@pytest.mark.parametrize('failure', ['exit', 'timeout'])
def test_failed_clone_is_retryable_and_leaves_existing_projects_alone(hub, start, monkeypatch, failure):
    hub.projects_root.mkdir(parents=True, exist_ok=True)
    keeper = hub.projects_root / 'keeper.txt'; keeper.write_text('keep me')
    monkeypatch.setattr(start.shutil, 'which', lambda _name: 'git')
    def clone(args, **_options):
        Path(args[-1]).mkdir()
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(args, 180)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(start.subprocess, 'run', clone)
    with pytest.raises(start.StartError):
        start.create(hub.root, title='Clone study', question='Investigate.', repo='owner/project')
    assert keeper.read_text() == 'keep me'
    assert kernel().studies.rows(hub.root) == []
    assert not (hub.root / 'studies/clone-study').exists()
    assert not list(hub.projects_root.glob('.arlotope-clone-*'))


def test_clone_never_replaces_an_existing_destination(hub, start):
    destination = hub.projects_root / 'clone-study'; destination.mkdir(parents=True)
    (destination / 'important.txt').write_text('existing research')
    with pytest.raises(start.StartError, match='already exists'):
        start.create(hub.root, title='Clone study', question='Investigate.', repo='owner/project')
    assert (destination / 'important.txt').read_text() == 'existing research'


def test_github_lookup_has_bounded_fixed_host_metadata(hub, start, monkeypatch):
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def read(self, limit):
            assert limit == 1_000_001
            return json.dumps({'full_name': 'Owner/Project', 'description': 'A repository', 'language': 'R'}).encode()
    def lookup(request, timeout):
        requests.append(request.full_url); assert timeout == 12
        return Response()
    monkeypatch.setattr(start.urllib.request, 'urlopen', lookup)
    result = start.github('owner/project')
    assert requests == ['https://api.github.com/repos/owner/project']
    assert result['url'] == 'https://github.com/Owner/Project' and result['language'] == 'R'


def test_github_offline_is_a_clear_error_without_state_changes(hub, start, monkeypatch):
    def offline(*_args, **_kwargs): raise OSError('offline')
    monkeypatch.setattr(start.urllib.request, 'urlopen', offline)
    with pytest.raises(start.StartError, match='local checkout'):
        start.github('owner/project')
    assert kernel().studies.rows(hub.root) == []


def test_http_starter_requires_confirmation_and_keeps_workflow_choices(hub, monkeypatch):
    from conftest import REPO
    monkeypatch.syspath_prepend(str(REPO / 'dashboard'))
    server = load('dashboard/serve')
    monkeypatch.setattr(server.ctx, 'HUB', hub.root)
    monkeypatch.setattr(server.ctx, 'LAB', hub.lab)
    assert server.starter.create({'title': 'A study', 'question': 'Why?'})[1] == 400
    context, status = server.starter.view()
    assert status == 200 and any(w['id'] == 'research' for w in context['workflows'])
    result, status = server.starter.create({'confirm': True, 'title': 'A study', 'question': 'Why?'})
    assert status == 201 and result['ok']


def test_attachment_conflict_is_clear_in_http_and_cli_and_can_be_corrected(hub, tmp_path, start, monkeypatch, capsys):
    from conftest import REPO
    import project_identity as I
    project = tmp_path/'registered project'; project.mkdir()
    I.register(project, 'other-owner', 'existing-study', 'other-lab')
    paths = [project/'.arlotope/project.json', I.home()/'projects.json']
    before = {path: path.read_bytes() for path in paths}
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api = load('dashboard/starter')
    monkeypatch.setattr(api.ctx, 'HUB', hub.root)
    body = {'confirm': True, 'title': 'A study', 'question': 'Why?', 'local': str(project)}
    response, status = api.create(body)
    assert status == 400 and 'other-lab' in response['error'] and str(project) in response['error']
    monkeypatch.setattr('sys.argv', ['research_start.py', '--hub', str(hub.root), '--title', 'A study',
                                   '--question', 'Why?', '--local', str(project)])
    with pytest.raises(SystemExit) as error:
        start.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert 'other-lab' in output.err and str(project) in output.err and 'Traceback' not in output.err
    assert {path: path.read_bytes() for path in paths} == before
    assert kernel().studies.rows(hub.root) == [] and not (hub.root/'studies/a-study').exists()
    correct = tmp_path/'unattached project'; correct.mkdir()
    (correct/'.gitignore').write_text('data/\n', encoding='utf-8')
    response, status = api.create({**body, 'local': str(correct)})
    assert status == 201 and response['ok']
    assert (correct/'.gitignore').read_text(encoding='utf-8') == 'data/\n'
