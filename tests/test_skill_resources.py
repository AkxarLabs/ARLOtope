"""Reusable methods stay ordinary files; managed runs retain the exact project version."""
import json

import pytest

from conftest import kernel

K = kernel()
import skill_resources as S


def skill(root, name='custom-method'):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: Inspect the evidence.\n---\n\nRead references/example.txt.\n', encoding='utf-8')
    (folder / 'references').mkdir()
    (folder / 'references/example.txt').write_text('Original reference', encoding='utf-8')
    (folder / 'asset.bin').write_bytes(bytes(range(256)))
    return folder


def test_import_inspection_requires_a_skill_and_preserves_resources(tmp_path):
    for folder in ('', str(tmp_path)):
        with pytest.raises(ValueError, match='containing SKILL.md'):
            S.inspect(folder)
    source = skill(tmp_path)
    info = S.inspect(source)
    assert info['name'] == 'custom-method' and len(info['files']) == 3
    destination = tmp_path / 'imported'
    S.copy(source, destination)
    assert S.files(source) == S.files(destination)
    with pytest.raises(ValueError, match='already exists'):
        S.copy(source, destination)


def test_project_versions_win_and_snapshot_remains_unchanged(hub, tmp_path):
    source = skill(hub.root / '.claude/skills')
    assert 'experiment' in S.folders(hub.root)
    workflow = {'id':'custom', 'title':'Custom', 'path':['inspect'], 'nodes':{
        'inspect':{'procedure':'custom-method','next':None}}, 'checkpoints':[], 'routes':{}, 'use':{}}
    project = tmp_path / 'project'
    first = S.snapshot(hub.root, project, workflow, 'sample', tmp_path/'run-one')
    target = project / first['custom-method']['path']
    (target/'references/example.txt').write_text('Project edit', encoding='utf-8')
    (source/'references/example.txt').write_text('Later Lab edit', encoding='utf-8')
    second = S.snapshot(hub.root, project, workflow, 'sample', tmp_path/'run-two')
    assert second['custom-method']['source'] == 'project'
    assert (target/'references/example.txt').read_text() == 'Project edit'
    assert (tmp_path/'run-one/custom-method/references/example.txt').read_text() == 'Original reference'
    assert (tmp_path/'run-two/custom-method/asset.bin').read_bytes() == bytes(range(256))
    assert json.loads((project/'.arlotope/workflows/sample.json').read_text()) == workflow
    rewritten = S.rewrite(str(source/'SKILL.md'), hub.root, project, tmp_path/'run-two', second)
    assert rewritten == (tmp_path/'run-two/custom-method/SKILL.md').as_posix()


def test_existing_native_skill_is_not_overwritten(tmp_path):
    folder = skill(tmp_path/'.claude/skills')
    records = S.install(tmp_path, {'custom-method':{'SKILL.md':b'Lab replacement'}})
    assert records['custom-method']['source'] == 'project'
    assert records['custom-method']['path'] == '.claude/skills/custom-method'
    assert 'Read references' in (folder/'SKILL.md').read_text()
    assert not (tmp_path/'.agents/skills/custom-method').exists()


def test_invalid_resources_rejected_before_writing(tmp_path):
    with pytest.raises(ValueError, match='resource path'):
        S.install(tmp_path, {'custom-method':{'SKILL.md':b'valid','../escape':b'bad'}})
    assert not (tmp_path/'.agents').exists()


def test_exclusions_can_be_reversed_without_removing_defaults(hub):
    S.exclude(hub.root, 'experiment')
    assert 'experiment' not in S.folders(hub.root)
    assert 'scope' in S.folders(hub.root)
    S.exclude(hub.root, 'experiment', False)
    assert 'experiment' in S.folders(hub.root)


def test_external_links_are_not_imported(tmp_path):
    folder = skill(tmp_path)
    outside = tmp_path/'outside.txt'
    outside.write_text('outside')
    try:
        (folder/'linked.txt').symlink_to(outside)
    except OSError:
        pytest.skip('File links require OS permission.')
    with pytest.raises(ValueError, match='outside its folder'):
        S.files(folder)
