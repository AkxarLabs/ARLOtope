"""Instruction reads select real sources and never launch or package a project."""
import hashlib

from conftest import kernel
from test_compose import m  # shared isolated dashboard fixture


def read(m, **query):
    body, status = m.instructions.inspect(query)
    assert status == 200, body
    return body


def tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def test_draft_reader_is_read_only_and_uses_draft_skill(m, hub):
    before = tree(hub.root)
    published = read(m, skills='triage')
    assert any('triage' in s['title'] for s in published['sections'])
    assert tree(hub.root) == before
    original = hub.root / '.claude/skills/triage/SKILL.md'
    result, status = m.compose.op({'op': 'write', 'path': '.claude/skills/triage/SKILL.md',
                                   'text': original.read_text() + '\nDraft-only instruction.\n'})
    assert status == 200, result
    before = tree(hub.root)
    assert 'Draft-only instruction.' in read(m, skills='triage', draft='1')['sections'][0]['text']
    assert 'Draft-only instruction.' not in read(m, skills='triage')['sections'][0]['text']
    assert tree(hub.root) == before


def test_study_reader_uses_project_precedence_and_separate_additions(m, hub):
    project = hub.make_project('test-study')
    hub.add_registry_row('test-study', project=str(project))
    folder = project / '.agents/skills/triage'
    folder.mkdir(parents=True)
    (folder / 'SKILL.md').write_text('---\nname: triage\n---\n# Project method\nUse local evidence.')
    k = kernel()
    k.instructions.write('add', 'triage', 'Lab addition.', hub.root)
    k.instructions.write('step', 'seed', 'Study addition.', hub.root, 'test-study')
    before = tree(hub.root), tree(project)
    body = read(m, skills='triage', step='seed', study='test-study', role='reviewer')
    assert body['sections'][0]['text'].startswith('# Project method')
    assert body['sections'][0]['source'] == str(folder / 'SKILL.md')
    assert {'Study additions · seed', 'Lab additions · triage', 'Role · reviewer'} <= {s['title'] for s in body['sections']}
    draft = read(m, skills='triage', study='test-study', draft='1')
    assert '# Project method' not in draft['sections'][0]['text']
    assert draft['notices']
    assert (tree(hub.root), tree(project)) == before


def test_references_stay_inside_selected_skill(m, hub):
    folder = hub.root / '.claude/skills/triage/references'
    folder.mkdir()
    (folder / 'guide.md').write_text('# Supporting instructions\nRead the original evidence.')
    body = read(m, skills='triage')
    assert 'references/guide.md' in body['sections'][0]['files']
    reference = read(m, skills='triage', file='references/guide.md')
    assert reference['sections'][0]['text'].startswith('# Supporting instructions')
    for file in ('../../../AGENTS.md', '../triage-other/SKILL.md'):
        assert m.instructions.inspect({'skills': 'triage', 'file': file})[1] == 400
    assert m.instructions.inspect({'skills': '../triage'})[1] == 400


def test_recorded_reader_never_substitutes_current_skills(m, hub):
    from test_run_evidence import configured
    from executor import RunSpec, enqueue, manifest
    lab = configured(hub)
    prompt = '---\nmode: review\n---\nOriginal task prompt.'
    run = enqueue(lab, RunSpec('', prompt=prompt))
    _, _, path, _ = manifest.find_run(lab, run['run_id'])
    directory = manifest.run_dir(path.parent, run['run_id'])
    folder = directory / 'skills/triage'
    folder.mkdir(parents=True)
    (folder / 'SKILL.md').write_text('# Recorded skill\nOriginal method.')
    before = tree(hub.root)
    body = read(m, run_id=run['run_id'])
    assert body['scope'] == 'Recorded instructions'
    assert body['sections'][0]['text'] == prompt
    assert body['sections'][-1]['text'] == '# Recorded skill\nOriginal method.'
    assert tree(hub.root) == before
    (folder / 'SKILL.md').unlink()
    body = read(m, run_id=run['run_id'])
    assert len(body['sections']) == 2 and body['notices']
    assert m.instructions.inspect({'run_id': '../bad'})[1] == 404


def test_unavailable_inputs_are_explicit(m, hub):
    body = read(m, skills='no-such-skill')
    assert not body['sections'] and 'not available' in body['notices'][0]
    assert m.instructions.inspect({'skills': 'triage', 'study': '../bad'})[1] == 400
    path = hub.root / '.claude/skills/triage/SKILL.md'
    path.write_text('x' * (m.compose.MAX_FILE + 1))
    body = read(m, skills='triage')
    assert not body['sections'] and 'too large' in body['notices'][0]


def test_additions_follow_runtime_order_and_ignore_sequence_only_additions(m, hub):
    k = kernel()
    hub.add_registry_row('test-study')
    for kind, name, scope, text in [('step', 'seed', None, 'Lab step'),
                                    ('add', 'triage', None, 'Lab skill'),
                                    ('step', 'seed', 'test-study', 'Study step'),
                                    ('add', 'triage', 'test-study', 'Study skill'),
                                    ('add', 'analyze', None, 'Sequence-only addition')]:
        k.instructions.write(kind, name, text, hub.root, scope)
    body = read(m, skills='triage,analyze', step='seed', study='test-study')
    additions = [s['text'] for s in body['sections'] if 'additions' in s['title']]
    assert additions == ['Lab step', 'Lab skill', 'Study step', 'Study skill']
    body = read(m, skills='analyze', primary='-', step='seed')
    assert [s['text'] for s in body['sections'] if 'additions' in s['title']] == ['Lab step']
    assert m.instructions._body('---\r\nname: test\r\n---\r\n# Read me\r\nBody') == '# Read me\nBody'
    k.instructions.write('role', 'reviewer', 'Extra review rule.', hub.root)
    body = read(m, role='reviewer')
    assert '\n'.join(s['text'] for s in body['sections']).count('Extra review rule.') == 1


def test_external_task_preview_uses_existing_instruction_builder_without_execution(m, hub):
    before = tree(hub.root)
    body = read(m, framework='sakana', phase='investigation', draft='1')
    assert 'Framework argv' in body['sections'][0]['text']
    assert any(s.get('skill') == 'external-framework' for s in body['sections'])
    assert tree(hub.root) == before
    assert m.instructions.inspect({'framework': 'sakana', 'phase': 'not-a-phase'})[1] == 400
