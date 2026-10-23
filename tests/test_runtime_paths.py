"""A separate Lab uses installed commands without copying the runtime into its workspace."""
import json
import os
import subprocess
import sys
import pytest

from conftest import REPO, kernel


def test_commands_use_installed_runtime_and_keep_the_selected_lab(hub):
    k = kernel()
    import lab_profile
    assert not (hub.root / 'tools/lab_bus.py').exists()
    assert lab_profile.bus_script(hub.root, 'hub', hub.root) == REPO / 'tools/lab_bus.py'
    env = {**os.environ, 'ARLOTOPE_HUB': str(hub.root), 'ARLOTOPE_RUN_ID': 'runtime-test',
           'ARLOTOPE_RUN_BUS': str(hub.lab / '.bus'), 'ARLOTOPE_RUN_SOURCE': 'hub'}
    result = subprocess.run([sys.executable, str(lab_profile.bus_script(hub.root, 'hub', hub.root)),
        'emit', 'run_report', '--data', 'summary=Installed runtime works.'], env=env,
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in (hub.lab / '.bus/events.jsonl').read_text(encoding='utf-8').splitlines()]
    assert events[-1]['run_id'] == 'runtime-test'
    command = k.brief.arlotope_cmd(hub.root)
    assert (REPO / 'tools/arlo_cli.py').as_posix() in command and f'--hub "{hub.root.as_posix()}"' in command
    v = {'level': 'hub', 'workdir': str(hub.root), 'cfg': {'kind': 'ask'}, 'target': 'hub', 'skill': 'ask'}
    text = lab_profile.preamble(__import__('executor').Lab(hub.root), 'runtime-test', v, '')
    for name in ('artifact.py', 'knowledge.py', 'lab_bus.py'):
        assert (REPO / 'tools' / name).as_posix() in text
        assert (hub.root / 'tools' / name).as_posix() not in text


def test_lab_owned_resources_and_project_bus_take_precedence(hub):
    kernel()
    import lab_profile
    local = hub.root / 'tools/lab_bus.py'
    local.parent.mkdir()
    local.write_text('# Local runtime', encoding='utf-8')
    assert lab_profile.bus_script(hub.root, 'hub', hub.root) == local
    project = hub.root / 'existing-project'
    own = project / 'scripts/lab_bus.py'
    own.parent.mkdir(parents=True)
    own.write_text('# Project bus', encoding='utf-8')
    assert lab_profile.bus_script(hub.root, 'project', project) == own


def test_inherited_skills_use_explicit_prompts_and_remote_snapshot_paths(hub, tmp_path, monkeypatch):
    k = kernel()
    import lab_profile
    import remote_projects
    from executor.manifest import run_dir
    lab = __import__('executor').Lab(hub.root)
    v = {'level': 'hub', 'skill': 'triage'}
    prompt = lab_profile.render_prompt(lab, v, '/triage sample', True)
    assert (REPO / '.claude/skills/triage/SKILL.md').as_posix() in prompt
    snapshot = tmp_path / 'capture'
    snapshot.mkdir()
    remote_projects.capture(lab, {'subject': 'sample', 'skill': 'triage'}, snapshot)
    files = json.loads((snapshot / 'instructions.json').read_text(encoding='utf-8'))
    assert files['.claude/skills/triage/SKILL.md']
    local = hub.root / 'remote-mirror'
    monkeypatch.setattr(lab, 'project_workdir', lambda _: local)
    m = {'target': 'sample', 'run_id': 'remote-test', 'remote': {'path': '/scratch/project'}}
    rd = run_dir(lab.agents_dir(local), m['run_id'])
    text = prompt + '\n' + k.brief.arlotope_cmd(hub.root) + '\n' + str(rd)
    for name in ('artifact.py', 'knowledge.py', 'lab_bus.py'):
        text += '\n' + (REPO / 'tools' / name).as_posix()
    rewritten = remote_projects.rewrite(lab, m, text)
    assert REPO.as_posix() not in rewritten and str(hub.root) not in rewritten
    assert '/instructions/tools/arlo_cli.py' in rewritten and '/instructions/.claude/skills/triage/SKILL.md' in rewritten
    assert all('/instructions/tools/' + name in rewritten for name in ('artifact.py', 'knowledge.py', 'lab_bus.py'))


def test_remote_footer_wrapper_accepts_only_its_own_run_id(monkeypatch):
    kernel()
    import project_control
    monkeypatch.setenv('ARLOTOPE_RUN_ID', 'owned-run')
    requests = []
    monkeypatch.setattr(project_control, 'request', lambda payload: requests.append(payload) or {'code': 0})
    assert project_control.control(['emit', 'run_report', '--run-id', 'owned-run', '--data', 'summary=Done']) == 0
    assert requests[0]['verb'] == 'emit' and 'run_id' not in requests[0]
    with pytest.raises(SystemExit) as error:
        project_control.control(['emit', 'run_report', '--run-id', 'different-run'])
    assert error.value.code == 2 and len(requests) == 1


def test_explainer_uses_installed_tools_and_selected_lab(hub, tmp_path, monkeypatch):
    kernel()
    import executor
    from executor import evidence, runs
    monkeypatch.setattr(runs, 'check_enabled', lambda _: None)
    monkeypatch.setattr(evidence, 'snapshot', lambda *_: (tmp_path / 'evidence.json',
        {'agent': None, 'study': 'sample', 'task': 'Recorded work'}))
    specs = []
    monkeypatch.setattr(runs, 'enqueue', lambda _, spec: specs.append(spec) or {'run_id': 'explainer-test'})
    evidence.start(executor.Lab(hub.root), 'source-test')
    prompt = specs[0].prompt
    read = json.loads(next(line for line in prompt.splitlines() if line.startswith('For current records')).split(': ', 1)[1][:-1])
    publish = json.loads(next(line for line in prompt.splitlines() if line.startswith('[')))
    assert read[1] == str(REPO / 'tools/executor_cli.py') and read[3] == str(hub.root)
    assert publish[1] == str(REPO / 'tools/artifact.py')
    assert specs[0].target == 'hub' and specs[0].assignment_study == 'sample'
