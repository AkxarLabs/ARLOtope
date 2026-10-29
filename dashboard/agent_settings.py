"""Saved agent choices at Lab and study scope; no second agent manager."""
import shutil
from pathlib import Path
import yaml

import ctx
import settings as config
from executor import Lab, backends, RunSpec
from executor import assignments


def view(q):
    try:
        lab = Lab(ctx.HUB)
        cfg, own = assignments.settings(lab, q.get('study'))
        presets = [{'id': key, **p, 'found': bool(backends.resolve_cli(p['backend'], {
            **((lab.prog().get('backends') or {}).get(p['backend']) or {}), **({'command': p['command']} if p.get('command') else {})}))}
            for key, p in (cfg['presets'] or {}).items()]
        roles = {'general': 'General', 'analyst': 'Analyst', 'reviewer': 'Reviewer', 'writer': 'Writer',
                 'designer': 'Designer', 'assistant': 'Workspace assistant', **ctx.tool('kernel').model.roles(ctx.HUB)}
        custom = assignments.load_yaml(lab.hub/'lab/structure.yaml').get('roles') or {}
        roles.update({key: value.get('label') or key for key,value in custom.items()})
        if roles.get('fresh-context-reviewer') == roles.get('reviewer'):
            roles['fresh-context-reviewer'] = 'Paper reviewer'
        resolved = {role: assignments.resolve(lab, RunSpec('', role=role, assignment_study=q.get('study'))) for role in roles}
        return {'ok': True, 'presets': presets, 'defaults': {k: cfg.get(k) for k in ('default_preset', 'role_presets')},
                'study': own, 'roles': roles, 'resolved': {r:{k:v.get(k) for k in ('preset','label','source','backend','model','effort')} for r,v in resolved.items()}}, 200
    except (ValueError, OSError) as error:
        return {'error': str(error)}, 400


def save(body):
    try:
        lab = Lab(ctx.HUB)
        value = body.get('settings')
        if not isinstance(value, dict):
            raise ValueError('Choose agent settings to save.')
        value = {key:value.get(key) for key in ('default_preset','role_presets', *(() if body.get('study') else ('presets',)))}
        if value.get('default_preset') is not None and not isinstance(value['default_preset'],str):
            raise ValueError('Choose a default agent preset.')
        if body.get('study'):
            if not ctx.tool('kernel').studies.study(ctx.HUB, body['study']):
                raise ValueError('Choose an existing study.')
            cfg, _ = assignments.settings(lab)
            assignments.bindings(value.get('role_presets') or {}, cfg['presets'] or {})
            if value.get('default_preset') and value['default_preset'] not in (cfg['presets'] or {}):
                raise ValueError('Choose an existing preset.')
            path = assignments.study_path(lab, body['study'])
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(yaml.safe_dump(value, sort_keys=False), encoding='utf-8')
            temporary.replace(path)
        else:
            assignments.validate(value)
            known = value.get('presets') or {}
            for path in (lab.hub/'studies').glob('*/workflow/agents.yaml'):
                own = assignments.load_yaml(path)
                assignments.bindings(own.get('role_presets') or {}, known)
                if own.get('default_preset') and own['default_preset'] not in known:
                    raise ValueError('A study uses this preset. Reassign it before removing it.')
            for flow in ctx.tool('kernel').model.workflows(ctx.HUB):
                for checkpoint in flow.get('checkpoints') or []:
                    key=(checkpoint.get('judge') or {}).get('preset')
                    if key and key not in known:
                        raise ValueError('Checkpoint '+checkpoint['id']+' uses this preset. Reassign it before removing it.')
                for node in (flow.get('nodes') or {}).values():
                    key = (node.get('agent') or {}).get('preset')
                    if key and key not in known:
                        raise ValueError('A workflow uses this preset. Reassign it before removing it.')
            error = config.write_config({('agents','programmatic',key): value.get(key) for key in ('presets','default_preset','role_presets')})
            if error:
                raise ValueError(error)
        ctx.pi_log({'action':'agents.assign', 'study':body.get('study'), 'presets':list(value.get('presets') or {})})
        ctx.KICK.set()
        return {'ok':True}, 200
    except (ValueError, OSError) as error:
        return {'error': str(error)}, 400


def check(body):
    try:
        lab = Lab(ctx.HUB)
        if 'agent' in body:
            agent = body['agent']
            assignments.validate({'presets': {'preview': agent}})
            backend = agent['backend']
            selected = {'backend': backend, 'options': {
                **((lab.prog().get('backends') or {}).get(backend) or {}), **agent}}
        else:
            selected = assignments.resolve(lab, RunSpec('', preset=body.get('preset')))
        command = backends.resolve_cli(selected['backend'], selected['options'])
        if not command or not (Path(command[0]).is_file() or shutil.which(command[0])):
            raise ValueError('This agent is not installed. Check its command in the preset.')
        if selected['options'].get('api_provider'):
            from native_providers import credential
            if not credential(selected['options']['api_provider']):
                raise ValueError('Connect this API provider on the execution machine first.')
            return {'ok':True, 'message':'Agent and API key found. Model access and billing are checked when starting a task.'}, 200
        if selected['backend'] == 'acp':
            from executor.acp_probe import probe
            return {'ok':True, 'message':'ACP connected. Authentication and model access are checked when starting a task.',
                    'connection':probe(command, lab.hub)}, 200
        return {'ok':True, 'message':'Agent executable found. Use its Sign in control to check your account.'}, 200
    except (ValueError, OSError) as error:
        return {'error':str(error)}, 400
