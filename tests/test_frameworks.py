"""External tools compose through ordinary task graphs, with no live provider or installation."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from conftest import REPO, kernel

kernel()
import frameworks as F


@pytest.fixture
def tool(tmp_path):
    project = tmp_path / 'project with spaces'
    project.mkdir()
    script = tmp_path / 'tool.py'
    script.write_text('''import json,sys,time
from pathlib import Path
if sys.argv[1] == 'check': raise SystemExit(0)
root=Path(sys.argv[2]);root.mkdir(parents=True,exist_ok=True)
count=root/'calls.txt';count.write_text(count.read_text()+'x' if count.exists() else 'x')
if 'sleep' in sys.argv: time.sleep(30)
if 'missing' not in sys.argv:
 (root/'result.json').write_text(json.dumps({'status':'failed' if 'bad' in sys.argv else 'completed'}))
''')
    definition = {'id': 'other-tool', 'title': 'Another framework', 'command': [sys.executable, str(script)],
                  'inputs': ['task'], 'check': ['check'],
                  'run': ['run', '{run_dir}', '{args}'],
                  'phases': {'investigate': {'outputs': ['result.json'],
                                             'accept': {'result.json': {'status': ['completed']}}}}}
    config = {'other-tool': {'inputs': {'task': str(project)}, 'timeout_seconds': 10}}
    config_path = project / '.arlotope/frameworks.yaml'
    config_path.parent.mkdir()
    config_path.write_text(yaml.safe_dump(config))
    return project, definition, config, config_path


def planned(tool):
    project, definition, *_ = tool
    return F.plan(definition, project, 'study-one', 'investigate')


def test_plan_is_read_only_and_arguments_are_literal(tool):
    project, definition, config, path = tool
    config['other-tool']['args'] = ['$(touch bad)', 'two words', '; echo unsafe']
    path.write_text(yaml.safe_dump(config))
    value = planned(tool)
    assert value['commands'][1][-3:] == config['other-tool']['args']
    assert not Path(value['receipt']).exists()
    assert not (project / '.arlotope/framework-runs').exists()


def test_generic_tool_execution_idempotency_and_evidence(tool):
    value = planned(tool)
    result = F.execute(value)
    assert result['status'] == 'completed' and result['evidence']['result.json']
    assert F.execute(value) == result
    assert (Path(value['run_dir']) / 'calls.txt').read_text() == 'x'
    assert F.completion(tool[1], tool[0], 'study-one', 'investigate')['signature'] == result['signature']
    (Path(value['run_dir']) / 'result.json').write_text('{"status":"completed","changed":true}')
    with pytest.raises(ValueError, match='changed'):
        F.execute(value)


def test_receipt_records_the_installed_revision_and_warns_when_it_is_not_the_reviewed_one(tool, monkeypatch, capsys):
    project, definition, *_ = tool
    monkeypatch.setattr(F, 'revision', lambda cwd: 'b' * 40)
    result = F.execute(F.plan(dict(definition, revision='b' * 40), project, 'study-one', 'investigate'))
    assert result['revision'] == 'b' * 40 and 'warning' not in result and not capsys.readouterr().err
    result = F.execute(F.plan(dict(definition, revision='a' * 40), project, 'study-two', 'investigate'))
    assert result['revision'] == 'b' * 40 and 'reviewed ' + 'a' * 40 in result['warning'] and 'warning' in capsys.readouterr().err
    result = F.execute(F.plan(definition, project, 'study-three', 'investigate'))
    assert 'warning' not in result  # a definition with no reviewed revision asserts nothing


def test_revision_reads_a_checkouts_head_and_is_empty_elsewhere(tmp_path):
    repo, plain = tmp_path / 'repo', tmp_path / 'plain'
    repo.mkdir(), plain.mkdir()
    git = ['git', '-C', str(repo), '-c', 'user.name=t', '-c', 'user.email=t@t']
    subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True)
    subprocess.run(git + ['commit', '-q', '--allow-empty', '-m', 'x'], check=True)
    assert F.revision(repo) == subprocess.run(git + ['rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    assert F.revision(tmp_path / 'missing') == ''


@pytest.mark.parametrize('argument', ['missing', 'bad'])
def test_successful_exit_is_not_enough(tool, argument):
    project, definition, config, path = tool
    config['other-tool']['args'] = [argument]
    path.write_text(yaml.safe_dump(config))
    value = planned(tool)
    with pytest.raises(ValueError):
        F.execute(value)
    assert json.loads(Path(value['receipt']).read_text())['status'] == 'failed'
    with pytest.raises(ValueError, match='--retry'):
        F.execute(value)


def test_timeout_is_retained_and_retry_reuses_the_anchor(tool):
    project, definition, config, path = tool
    config['other-tool'].update(args=['sleep'], timeout_seconds=.2)
    path.write_text(yaml.safe_dump(config))
    value = planned(tool)
    with pytest.raises(subprocess.TimeoutExpired):
        F.execute(value)
    saved = json.loads(Path(value['receipt']).read_text())
    assert saved['status'] == 'failed' and saved['run_dir'] == value['run_dir']
    with pytest.raises(ValueError, match='--retry'):
        F.execute(value)
    # Inspect/recover upstream state; a retry must still use the original reviewed configuration.
    value['commands'][1] = value['commands'][1][:-1]
    with pytest.raises(ValueError, match='configuration changed'):
        F.execute(value, retry=True)


def test_lock_does_not_admit_duplicate_or_other_phases(tool):
    from executor.procs import RunLock
    value = planned(tool)
    lock = RunLock(Path(value['receipt']).parent / 'execution.lock')
    assert lock.try_acquire()
    try:
        with pytest.raises(ValueError, match='Another phase'):
            F.execute(value)
    finally:
        lock.release()


def test_detection_never_executes_a_command(tool, monkeypatch):
    monkeypatch.setattr(F.subprocess, 'Popen', lambda *a, **kw: pytest.fail('GET executed software'))
    project, definition, *_ = tool
    assert F.installed({'other-tool': definition}, project)[0]['available']
    assert not F.installed({'missing': {'command': ['arlotope-nonexistent-123']}})[0]['available']


@pytest.mark.parametrize('value', [None, [], {'framework': []}, {'framework': '../x', 'phase': 'x'},
                                  {'framework': 'x', 'phase': 'x', 'command': 'bad'}])
def test_task_contract_rejects_malformed_external_fields(value):
    with pytest.raises(ValueError):
        F.validate(value)


def test_budgets_paths_and_reserved_arguments_are_not_assumed(tool):
    project, definition, config, path = tool
    config['other-tool'].pop('timeout_seconds')
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match='timeout_seconds'):
        planned(tool)
    config['other-tool']['timeout_seconds'] = 10
    config['other-tool']['args'] = ['execution.phases=paper']
    definition['reserved_args'] = ['execution.phases']
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match='cannot replace'):
        planned(tool)


def graph(hub, definition):
    k = kernel()
    folder = hub.root / 'workflow/frameworks'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'other-tool.yaml').write_text(yaml.safe_dump(definition))
    d = k.define.read(hub.root)
    d['workflows'] = [{'id': 'external-test', 'title': 'External + ARLOtope', 'default': True,
                       'path': ['seed', 'analysis'], 'nodes': {
                           'seed': {'procedure': None, 'external': {'framework': 'other-tool', 'phase': 'investigate'}},
                           'analysis': {'procedure': None, 'instructions': 'Review the original result.'}},
                       'checkpoints': [{'id': 'before-review', 'before': 'analysis', 'approver': 'me'}]}]
    k.define.write(hub.root, d)
    return k


def test_external_step_cannot_advance_without_receipt_then_chains_to_normal_task(hub, tool):
    k = graph(hub, tool[1])
    hub.add_registry_row('study-one', project=str(tool[0]))
    with pytest.raises(ValueError, match='receipt'):
        k.studies.move(hub.root, 'study-one', 'done')
    F.execute(planned(tool))
    k.studies.move(hub.root, 'study-one', 'done')
    s = k.studies.study(hub.root, 'study-one')
    assert not s['runnable'] and s['waiting']['checkpoint'] == 'before-review'
    k.checkpoints.decide(hub.root, 'study-one', 'before-review', by='pi')
    assert k.studies.study(hub.root, 'study-one')['runnable'] == ['analysis']
    k.studies.move(hub.root, 'study-one', 'done')
    assert k.studies.study(hub.root, 'study-one')['finished']


def test_external_task_prompt_uses_same_native_graph_dispatch(hub, tool):
    graph(hub, tool[1])
    hub.add_registry_row('study-one', project=str(tool[0]))
    from executor import Lab, RunSpec
    from lab_profile import start_graph
    captured = []
    def enqueue(_lab, spec):
        captured.append(spec)
        return {'run_id': 'fake'}
    assert start_graph(Lab(hub.root), 'study-one', enqueue, RunSpec) == ['fake']
    prompt = captured[0].prompt_override
    command = json.loads(next(line.split(': ', 1)[1] for line in prompt.splitlines() if line.startswith('Framework argv')))
    assert command[-2:] == ['--phase', 'investigate'] and command[0].endswith('/tools/frameworks.py')
    assert captured[0].skill == 'workflow-task' and captured[0].extra['workflow_node'] == 'seed'
    assert 'docs/external-frameworks.md' in prompt and '.arlotope/framework-runs/study-one/other-tool' in prompt


def test_remote_detection_uses_selected_machine_and_project(hub, monkeypatch):
    import remote_projects
    seen = []
    monkeypatch.setattr(remote_projects, 'rpc', lambda machine, method, data:
                        seen.append((machine, method, data)) or {'frameworks': []})
    assert F.availability(hub.root, machine='server', project='/project') == {'frameworks': []}
    assert seen[0][:2] == ('server', 'frameworks') and seen[0][2]['project'] == '/project'


def test_worker_bundle_runs_the_same_generic_tool(tool, tmp_path):
    import remote_projects
    _, blob = remote_projects.bundle()
    runtime = tmp_path / 'worker.pyz'
    runtime.write_bytes(blob)
    project, definition, *_ = tool
    file = tmp_path / 'other-tool.yaml'
    file.write_text(yaml.safe_dump(definition))
    result = subprocess.run([sys.executable, str(runtime), 'framework', '--definition', str(file),
                             '--project', str(project), '--study', 'study-one', '--phase', 'investigate'],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['status'] == 'completed'


def test_sakana_is_only_a_recipe_and_preserves_negative_outcomes():
    recipe = F.read(REPO / 'workflow/frameworks/sakana.yaml')
    assert recipe['command'] == ['agsci']
    assert 'completed_no_winner' in recipe['phases']['investigation']['accept']['.investigation_completion.json']['outcome']
    assert 'win32' not in recipe['platforms'] and 'darwin' not in recipe['platforms']
    assert len(recipe['revision']) == 40
    for command in (recipe['check'], recipe['run']):   # a null result must not fail the paper phase; user args come later and win
        assert command.index('paper.final_outcome_policy=allow_not_qualified') < command.index('{args}')
    assert {'task/evaluate_final.py', 'task/task_contract.json'} <= set(recipe['phases']['task_drafting']['outputs'])
    final = next(c for c in kernel().model.workflow('sakana', REPO)['checkpoints'] if c['id'] == 'sakana-final-evidence')
    assert any(e.endswith(name) for name in ('best_program_manifest.json', 'pipeline_summary.json', 'cost_summary.json')
               for e in final['evidence'])
    assert F.requirements(kernel().model.workflow('sakana', REPO)) == ['sakana']


def test_export_keeps_external_execution_requirements():
    import workflow_export
    import base64
    import io
    import zipfile
    result = workflow_export.export(REPO, 'sakana')
    assert 'External tool: `sakana`, phase `investigation`.' in result['markdown']
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result['data']))) as archive:
        assert 'resources/frameworks/sakana.yaml' in archive.namelist()


def test_missing_installation_blocks_before_agent_dispatch(hub, tool):
    definition = {**tool[1], 'command': ['arlotope-nonexistent-123']}
    graph(hub, definition)
    hub.add_registry_row('study-one', project=str(tool[0]))
    from executor import Lab, RunSpec
    from lab_profile import start_graph
    with pytest.raises(ValueError, match='Not installed'):
        start_graph(Lab(hub.root), 'study-one', lambda *a: pytest.fail('agent launched'), RunSpec)


def test_remote_snapshot_keeps_framework_definitions_and_guide(hub, tmp_path):
    from executor import Lab
    import remote_projects
    folder = tmp_path / 'instructions'
    folder.mkdir()
    remote_projects.capture(Lab(hub.root), {'subject': 'sample'}, folder)
    files = json.loads((folder / 'instructions.json').read_text())
    assert 'workflow/frameworks/sakana.yaml' in files
    assert 'docs/external-frameworks.md' in files
