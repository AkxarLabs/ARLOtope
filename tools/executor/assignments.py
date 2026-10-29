"""Resolve task/role presets once; keep launcher identity separate from workflow and conversation."""
from __future__ import annotations

import copy
import hashlib
import json
import re

from .lab import load_yaml
from .spec import SpecError

ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$')
OPTIONS = ('command', 'model', 'effort', 'reasoning_effort', 'agent', 'variant', 'extra_args',
           'prompt_via', 'auth_method', 'mode', 'api_provider')


def validate(value):
    if not isinstance(value, dict):
        raise SpecError('Agent settings must be a mapping.')
    presets = value.get('presets') or {}
    if not isinstance(presets, dict):
        raise SpecError('Presets must be named settings.')
    for key, preset in presets.items():
        if not isinstance(key, str) or not ID.fullmatch(key) or not isinstance(preset, dict):
            raise SpecError('Use a short stable ID for each agent preset.')
        if preset.get('backend') not in ('claude', 'codex', 'opencode', 'acp'):
            raise SpecError(f'{key}: choose a supported harness.')
        if preset.get('api_provider') is not None and (preset.get('backend'),preset['api_provider']) not in (('codex','openai'),('claude','anthropic')):
            raise SpecError(f'{key}: choose an API provider supported by this harness.')
        for field in ('label', 'model', 'effort', 'auth_method', 'mode', 'agent', 'variant', 'prompt_via'):
            if preset.get(field) is not None and (not isinstance(preset[field], str) or len(preset[field]) > 180):
                raise SpecError(f'{key}: {field} must be short text.')
        command = preset.get('command')
        if command is not None and (not isinstance(command, list) or not command or any(
                not isinstance(arg, str) or not arg.strip() or '\0' in arg for arg in command)):
            raise SpecError(f'{key}: command must be an argument list.')
        if preset.get('effort') and preset['backend'] not in ('claude', 'codex'):
            raise SpecError(f'{key}: this adapter does not expose effort. Use its native settings.')
        from .spec import MODEL_RE, EFFORTS
        if preset.get('model') and not MODEL_RE.fullmatch(preset['model']):
            raise SpecError(f'{key}: use a model identifier or leave it blank.')
        if preset.get('effort') and preset['effort'] not in EFFORTS:
            raise SpecError(f'{key}: choose a supported effort.')
    if value.get('default_preset') is not None and (not isinstance(value['default_preset'], str) or value['default_preset'] and value['default_preset'] not in presets):
        raise SpecError('Choose an existing default agent preset.')
    bindings(value.get('role_presets') or {}, presets)
    return value


def bindings(value, presets):
    if not isinstance(value, dict):
        raise SpecError('Role assignments must be a mapping.')
    for role, preset in value.items():
        if not isinstance(role, str) or not ID.fullmatch(role) or preset is not None and (not isinstance(preset,str) or preset not in presets):
            raise SpecError(f'{role}: choose an existing preset, or use the general default.')


def study_path(lab, study):
    if not isinstance(study, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,79}', study):
        raise SpecError('Choose an existing study.')
    return lab.hub/'studies'/study/'workflow/agents.yaml'


def settings(lab, study=None):
    prog = lab.prog()
    result = {key: copy.deepcopy(prog.get(key)) for key in ('presets', 'default_preset', 'role_presets')}
    result = validate(result)
    own = load_yaml(study_path(lab, study)) if study else {}
    if own.get('default_preset') and own['default_preset'] not in (result['presets'] or {}):
        raise SpecError('The study uses a missing agent preset. Reassign it in Agents.')
    bindings(own.get('role_presets') or {}, result['presets'] or {})
    return result, own


def resolve(lab, spec, subject=None, remote=None):
    from . import backends
    study = spec.assignment_study or subject
    task = spec.extra.get('agent') or {}
    explicit = bool(spec.preset or spec.backend or spec.model is not None or spec.effort is not None or
                    task.get('preset') or task.get('backend') or 'model' in task or 'effort' in task)
    context = spec.extra.get('context') or {}
    if context.get('mode') in ('continue', 'native-fork') and context.get('run_id') and not explicit:
        from .manifest import find_run
        hit = find_run(lab, context['run_id'])
        if hit and hit[3].get('assignment'):
            return {**copy.deepcopy(hit[3]['assignment']), 'source':'Source conversation', 'study':study}
    cfg, own = settings(lab, study)
    role = spec.role if spec.role != 'orchestrator' else 'general'
    role = role or 'general'
    preset = spec.preset or (task.get('preset') if not spec.backend else None)
    source = 'This launch' if spec.preset or spec.backend else 'Task'
    if not preset and not (spec.backend or task.get('backend')):
        for scope, values in (('Study role', own), ('Lab role', cfg)):
            if role in (values.get('role_presets') or {}):
                preset, source = values['role_presets'][role], scope
                break
        if not preset:
            preset = own.get('default_preset') or cfg.get('default_preset')
            source = 'Study default' if own.get('default_preset') else 'Lab default'
    chosen = (cfg['presets'] or {}).get(preset) if preset else {}
    if preset and chosen is None:
        raise SpecError(f'Agent preset {preset!r} is missing. Choose another agent.')
    chosen = chosen or {}
    machine = {}
    if remote:
        import remote_projects
        machine = remote_projects.machine(remote['machine'])
    # Pick one selector. A higher-priority backend never inherits a lower preset's model.
    if spec.preset:
        selected, backend = True, chosen['backend']
    elif spec.backend:
        selected, backend = False, spec.backend
    elif task.get('preset'):
        selected, backend = True, chosen['backend']
    elif task.get('backend'):
        selected, backend = False, task['backend']
    else:
        selected, backend = bool(chosen), chosen.get('backend') or machine.get('default_agent') or lab.prog().get('backend') or backends.DEFAULT
    if backend not in backends.REGISTRY:
        raise SpecError(f'Unknown harness {backend!r}.')
    base = ((lab.prog().get('backends') or {}).get(backend) or {}).copy()
    if remote:
        base.pop('command', None)
        base.update((machine.get('agent_config') or {}).get(backend) or {})
    backend_model = base.get('model') or None
    if selected:
        base.update({key: copy.deepcopy(chosen[key]) for key in OPTIONS if key in chosen and key != 'command'})
    command = chosen.get('command') if selected else None
    if remote and command:
        command = ((machine.get('agent_presets') or {}).get(preset) or {}).get('command') or command
        if any(re.match(r'^(?:[A-Za-z]:[/\\]|/)', arg) for arg in command):
            override = ((machine.get('agent_presets') or {}).get(preset) or {}).get('command')
            if not override:
                raise SpecError('Set this preset’s command on the execution machine; local paths are not portable.')
    if command:
        base['command'] = command
    model = (chosen.get('model') or backend_model) if selected else backend_model
    if not selected and not (spec.backend or task.get('backend')):
        model = lab.prog().get('model') or model
    if not cfg['presets'] and not own and spec.model is None and 'model' not in task:
        model = lab.prog().get('model') or model
    if not (spec.preset or spec.backend) and 'model' in task:
        model = task['model'] or backend_model
    if spec.model is not None:
        model = spec.model or backend_model
    if model == 'inherit':
        model = backend_model
    effort = base.get('effort') or base.get('reasoning_effort')
    if not (spec.preset or spec.backend) and 'effort' in task:
        effort = task['effort']
    if spec.effort is not None:
        effort = spec.effort or None
    if effort and backend not in ('claude', 'codex'):
        raise SpecError(f'{backend} does not expose an effort selector. Use its native settings.')
    options = {key: copy.deepcopy(base.get(key)) for key in OPTIONS}
    options.update(model=model, effort=effort, reasoning_effort=effort)
    identity = {'backend': backend, 'options': {k: options[k] for k in ('command', 'agent', 'variant', 'auth_method', 'mode', 'api_provider')},
                'machine': remote['machine'] if remote else None}
    result = {'preset': preset if selected else None, 'label': (chosen.get('label') or preset) if selected else backend,
              'source': 'This launch' if spec.backend or spec.model else source, 'study': study,
              'backend': backend, 'model': model, 'effort': effort, 'options': options,
              'identity': hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()}
    from .spec import MODEL_RE
    if model and not MODEL_RE.fullmatch(model):
        raise SpecError('Use a model identifier or leave it blank.')
    # Continue/fork owns its original configuration; default changes cannot replace it.
    context = spec.extra.get('context') or {}
    if context.get('mode') in ('continue', 'native-fork') and context.get('run_id'):
        from .manifest import find_run
        hit = find_run(lab, context['run_id'])
        previous = (hit[3].get('assignment') if hit else None)
        if previous:
            if explicit and any(result.get(k) != previous.get(k) for k in ('identity', 'model', 'effort')):
                raise SpecError('This conversation uses another agent configuration. Use its source agent or start new with handoff.')
            result = {**copy.deepcopy(previous), 'source': 'Source conversation', 'study': study}
    return result
