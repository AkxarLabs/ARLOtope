"""Deterministic Markdown procedure and bundled skills from a workflow definition."""
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

from kernel import model
from kernel.branches import nodes
from workflow_graph import targets


def export(hub, workflow):
    hub = Path(hub)
    w = model.workflow(workflow, hub)
    if w['id'] != workflow:
        raise ValueError('Choose an existing workflow.')
    ns = nodes(w, model.steps(hub))
    from skill_resources import selected, folders, files as skill_files
    skills = selected(hub, w)
    inventory = folders(hub)
    resources, missing = {}, []
    from frameworks import definitions, requirements
    for fid in requirements(w):
        definition = definitions(hub).get(fid)
        if definition:
            resources['resources/frameworks/'+fid+'.yaml'] = Path(definition['file']).read_bytes()
    for skill in dict.fromkeys(skills):
        folder = inventory.get(skill, model.skills_root(hub) / skill)
        if not (folder/'SKILL.md').is_file():
            missing.append(skill)
        else:
            for relative, data in skill_files(folder).items():
                resources['resources/skills/'+skill+'/'+relative] = data
    from kernel import instructions
    from executor import Lab
    from executor.contexts import role_text
    for n in ns:
        role = (n.get('agent') or {}).get('role') or 'general'
        resources['resources/roles/'+role+'.md'] = role_text(Lab(hub), role).encode()
        n['additional_instructions'] = instructions.read('step', n['id'], hub) or ''
        if n.get('procedure'):
            n['additional_instructions'] += '\n' + (instructions.read('add', n['procedure'], hub) or '')
    digest = hashlib.sha256(json.dumps({'workflow':w,'tasks':ns}, sort_keys=True).encode())
    for name, data in sorted(resources.items()):
        digest.update(name.encode()); digest.update(data)
    version = digest.hexdigest()[:16]
    lines = ['---', 'name: '+workflow, 'description: '+json.dumps(w.get('blurb') or w['title']), '---', '',
             '# '+w['title'], '', f'Definition revision: `{version}`.', '',
             '## Execution contract', '',
             'Follow the declared routes. A finished model turn is not task completion. Produce the required evidence, '
             'then report the named outcome. Never treat a question, feedback or silence as checkpoint approval.', '',
             'This portable procedure describes the process. Lab commands, independent agent creation, native forks, '
             'parallel execution and recorded approvals require the corresponding runner/tools. If unavailable, '
             'explain what is unavailable and stop at the affected requirement; do not claim it was enforced.', '',
             'Read the bundled skills under `resources/skills/`. Their references to Lab tools, templates or project '
             'files still require those resources in the execution environment.', '', '## Tasks', '']
    for n in ns:
        lines += [f'### {n["id"]}: {n["label"]}', '', f'Agent: {json.dumps(n.get("agent") or {"role":"general"})}',
                  f'Context: {json.dumps(n.get("context") or {"mode":"fresh"})}', f'Room: {n.get("room") or "unspecified"}', '']
        lines.append('Read role instructions: `resources/roles/'+((n.get('agent') or {}).get('role') or 'general')+'.md`.')
        if n.get('external'):
            external = n['external']
            lines += [f'External tool: `{external["framework"]}`, phase `{external["phase"]}`.',
                      f'Recipe: `resources/frameworks/{external["framework"]}.yaml`. Requires the installed '
                      'ARLOtope framework runner, upstream executable and project `.arlotope/frameworks.yaml`. '
                      'Inspect the phase receipt and original evidence before reporting completion. '
                      'If the tool is unavailable, stop; do not substitute a prose-only result.']
        for p in ([n.get('procedure')] if n.get('procedure') else []) + n.get('skills', []):
            lines.append(f'- Read and follow `resources/skills/{p}/SKILL.md`.')
        lines += ['', n.get('instructions') or '', n['additional_instructions'], '', 'Outputs: '+(', '.join(n.get('outputs') or []) or 'as defined by the skills')+'.',
                  'On done: '+(', '.join(targets(n.get('next'))) or 'end this branch')+'.']
        for outcome, destination in {**w['routes'].get(n['id'],{}),**n.get('outcomes',{})}.items():
            lines.append(f'- On `{outcome}`: {json.dumps(destination)}.')
        if n.get('join'):
            lines.append('Wait for every declared incoming parallel branch before starting.')
        if n.get('max_visits'):
            lines.append(f'Repetition limit: {n["max_visits"]} task visits.')
        lines.append('')
    lines += ['## Gates', '']
    for c in w['checkpoints']:
        lines += [f'### {c["id"]}: {c["title"]}', '',
                  ('Before '+c['before']) if c.get('before') else ('During '+c['during']+' at '+c.get('at','')),
                  'Decision maker: '+c['approver'], 'Rubric: '+(c.get('means') or c.get('tell') or ''),
                  'Evidence: '+json.dumps(c.get('evidence') or []), 'Checks: '+json.dumps(c.get('checks') or []),
                  'Judge: '+json.dumps(c.get('judge') or {}), 'Decisions: '+json.dumps(c.get('decisions') or {'proceed':'continue'}), '']
    text = '\n'.join(lines).rstrip()+'\n'
    files = {**resources, 'SKILL.md':text.encode(), 'workflow.json':json.dumps({'workflow':w,'tasks':ns},indent=2).encode()}
    files['README.md'] = ('# Procedure bundle\n\nRead SKILL.md. Includes skill-local resources, not the complete Lab or project. '
                         'Run inside the appropriate Lab/project for mechanical gates and parallel execution.\n\n'
                         'Missing skill directories: '+(', '.join(missing) or 'none')+'\n').encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    return {'ok':True,'filename':workflow+'-procedure.zip','markdown':text,'revision':version,
            'requires_lab':True,'missing':missing,'data':base64.b64encode(output.getvalue()).decode()}
