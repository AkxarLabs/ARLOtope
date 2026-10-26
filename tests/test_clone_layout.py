"""A clone starts empty and keeps local research out of source-control staging."""
import shutil
import subprocess

import pytest

from conftest import REPO


def test_private_config_is_seeded_once_and_preserves_user_values(tmp_path):
    import labfiles
    from executor.lab import Lab

    lab = tmp_path / 'lab'
    lab.mkdir()
    defaults = lab / 'config.defaults.yaml'
    defaults.write_text('lab:\n  name: Starter\nagents:\n  programmatic:\n    enabled: false\n')
    config = labfiles.ensure_config(tmp_path)
    assert config.read_bytes() == defaults.read_bytes()
    config.write_text('lab:\n  name: My research\n')
    defaults.write_text('lab:\n  name: New defaults\n')
    assert Lab(tmp_path).config()['lab']['name'] == 'My research'
    assert config.read_text() == 'lab:\n  name: My research\n'
    assert not labfiles.ensure_config(tmp_path / 'unrelated').exists()


@pytest.mark.skipif(not shutil.which('git'), reason='git is needed')
def test_gitignore_excludes_research_but_keeps_product_sources(tmp_path):
    shutil.copyfile(REPO / '.gitignore', tmp_path / '.gitignore')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    private = ['lab/config.yaml', 'lab/identity.json', 'lab/journal.jsonl', 'lab/REGISTRY.md',
               'lab/.bus/artifacts/report.html', 'lab/knowledge/FINDINGS.md',
               'lab/notebook/2030-01-01.md', 'lab/records/answer.md', 'lab/RESEARCH.md',
               'lab/rooms3d/room.json', 'studies/example/IDEA.md', 'studies/example/materials/brief.pdf',
               '.env', '.env.local', 'local.key', 'output/test/index.html', '.playwright-cli/session.yml']
    shared = ['lab/README.md', 'lab/config.defaults.yaml', 'lab/profiles/codex.yaml',
              'lab/notebook/README.md', 'lab/ideation/README.md', 'workflow/rooms.yaml',
              '.claude/skills/example/SKILL.md', 'dashboard/static/assets/icon.png',
              'docs/assets/current/example.png', 'templates/project/configs/base.yaml', '.env.example']
    paths = private + shared
    result = subprocess.run(['git', 'check-ignore', '--no-index', '-z', '--stdin'], input=('\0'.join(paths)+'\0').encode(),
                            cwd=tmp_path, capture_output=True, check=True)
    assert set(result.stdout.decode().rstrip('\0').split('\0')) == set(private)


def test_shipped_defaults_start_without_agents_or_machine_specific_paths():
    import yaml
    data = yaml.safe_load((REPO / 'lab/config.defaults.yaml').read_text())
    assert data['lab']['projects_root'] == '../arlotope-projects'
    assert data['agents']['programmatic']['enabled'] is False
    assert not data['agents']['programmatic'].get('presets')


def test_optional_local_copy_from_download_never_copies_lab_state(tmp_path):
    import new_lab
    source, destination = tmp_path / 'download', tmp_path / 'copy'
    for rel, text in {'lab/config.defaults.yaml': 'lab: {}\n', 'lab/config.yaml': 'private settings',
                      'lab/records/private.md': 'private answer', 'lab/identity.json': 'private identity',
                      'studies/private/IDEA.md': 'private study', 'output/report.html': 'private output',
                      '.env': 'private secret', 'workflow/steps.yaml': 'steps: {}\n'}.items():
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    destination.mkdir()
    new_lab._export(source, destination)
    assert {p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()} == {
        'lab/config.defaults.yaml', 'workflow/steps.yaml'}
