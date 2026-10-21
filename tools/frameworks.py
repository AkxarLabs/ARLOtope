"""Optional research tools: declarative commands, phase receipts and ordinary workflow tasks.

No framework imports, automatic installs, shell interpolation or second scheduler. The agent
assigned to a task invokes this CLI; the existing executor owns that agent and its controls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

import yaml

ID = re.compile(r'^[a-z0-9][a-z0-9._-]{0,79}$')


def read(path):
    value = yaml.safe_load(Path(path).read_text(encoding='utf-8-sig')) or {}
    if not isinstance(value, dict):
        raise ValueError(f'{path}: expected a mapping.')
    return value


def definitions(hub):
    from kernel import model
    paths = {}
    for base in dict.fromkeys((model.CODE, model.root_of(hub))):
        paths.update({p.stem: p for p in (base / 'workflow/frameworks').glob('*.yaml')})
    return {key: dict(read(path), id=key, file=str(path)) for key, path in paths.items()}


def validate(value):
    if not isinstance(value, dict) or set(value) != {'framework', 'phase'} or any(
            not isinstance(v, str) or not ID.fullmatch(v) for v in value.values()):
        raise ValueError('External tasks need a framework ID and a phase ID.')


def requirements(workflow):
    return sorted({n['external']['framework'] for n in (workflow.get('nodes') or {}).values()
                   if isinstance(n, dict) and isinstance(n.get('external'), dict)})


def settings(project, fid):
    path = Path(project) / '.newts/frameworks.yaml' if project else None
    value = (read(path).get(fid) or {}) if path and path.is_file() else {}
    if not isinstance(value, dict) or not isinstance(value.get('inputs') or {}, dict):
        raise ValueError('Framework settings and inputs must be mappings.')
    return value


def installed(defs, project=None):
    """Read-only detection on this host. No configured executable is run by a dashboard GET."""
    out = []
    for fid, definition in defs.items():
        try:
            config = settings(project, fid)
            command = argv(config.get('command', definition.get('command')))
            cwd = Path(config.get('cwd') or project or Path.cwd()).expanduser()
            executable = command[0]
            found = shutil.which(executable) or (str((cwd / executable).resolve())
                if (cwd / executable).is_file() and os.access(cwd / executable, os.X_OK) else None)
            missing = [key for key in definition.get('inputs', []) if not (config.get('inputs') or {}).get(key)]
            supported = sys.platform in definition.get('platforms', [sys.platform])
            out.append({'id': fid, 'title': definition.get('title', fid), 'installed': bool(found), 'available': bool(found) and supported,
                        'configured': not missing, 'reason': 'Not installed' if not found else
                        'Use a supported execution machine' if not supported else
                        'Set up project inputs' if missing else 'Installed · check before running',
                        'setup': definition.get('setup', ''), 'phases': list(definition.get('phases') or {})})
        except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
            out.append({'id': fid, 'title': definition.get('title', fid), 'installed': False, 'available': False,
                        'reason': str(error), 'setup': definition.get('setup', ''), 'phases': []})
    return out


def availability(hub, *, machine='', project=''):
    defs = definitions(hub)
    if machine:
        import remote_projects
        return remote_projects.rpc(machine, 'frameworks', {'definitions': defs, 'project': project})
    return {'frameworks': installed(defs, project), 'machine': 'local'}


def check_launch(hub, study, external):
    import remote_projects
    from kernel import checkpoints
    if not study.get('project'):
        raise ValueError('Attach a project before running external research phases.')
    remote = remote_projects.location(study['project'])
    data = availability(hub, machine=remote['machine'] if remote else '',
                        project=remote['path'] if remote else str(checkpoints.project_dir(hub, study['id'])))
    found = next((f for f in data['frameworks'] if f['id'] == external['framework']), {})
    if not found.get('available') or not found.get('configured'):
        raise ValueError(f'{external["framework"]}: {found.get("reason", "tool unavailable")}. See Optional research tools.')


def completion(definition, project, study, phase):
    value = plan(definition, project, study, phase)
    path = Path(value['receipt'])
    receipt = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    signature = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    if receipt.get('status') != 'completed' or receipt.get('signature') != signature or outputs(value) != receipt.get('evidence'):
        raise ValueError('This external phase has no current, completed evidence receipt. Inspect its log before continuing.')
    return receipt


def check_task(hub, study, external):
    import remote_projects
    from kernel import checkpoints
    definition = definitions(hub)[external['framework']]
    remote = remote_projects.location(study.get('project'))
    if remote:
        return remote_projects.rpc(remote['machine'], 'framework-receipt', {'definition': definition,
            'project': remote['path'], 'study': study['id'], 'phase': external['phase']})
    return completion(definition, checkpoints.project_dir(hub, study['id']) or Path(hub) / 'studies' / study['id'],
                      study['id'], external['phase'])


def argv(value):
    if not isinstance(value, list) or not value or any(not isinstance(v, str) or not v or '\0' in v for v in value):
        raise ValueError('Commands and arguments must be nonempty arrays of text; no shell command strings.')
    return value


def expand(parts, values, extra):
    result = []
    for part in argv(parts):
        if part == '{args}':
            result.extend(extra)
        else:
            try:
                result.append(part.format_map(values))
            except (KeyError, ValueError) as error:
                raise ValueError(f'Unknown or malformed command placeholder: {part}') from error
    return result


def plan(definition, project, study, phase):
    if not ID.fullmatch(study) or not ID.fullmatch(definition['id']) or not ID.fullmatch(phase):
        raise ValueError('Use a study slug and framework ID.')
    project = Path(project).resolve()
    config = settings(project, definition['id'])
    selected = (definition.get('phases') or {}).get(phase)
    if not isinstance(selected, dict):
        raise ValueError('Choose a declared framework phase.')
    if sys.platform not in definition.get('platforms', [sys.platform]):
        raise ValueError('This framework needs a supported execution machine; see its setup guide.')
    missing = [key for key in definition.get('inputs', []) if not (config.get('inputs') or {}).get(key)]
    if missing:
        raise ValueError('Set .newts/frameworks.yaml inputs: ' + ', '.join(missing))
    extra = config.get('args') or []
    if extra:
        argv(extra)
    if any(arg.lstrip('+').split('=', 1)[0] in definition.get('reserved_args', []) or arg.startswith('--') for arg in extra):
        raise ValueError('Extra arguments cannot replace the phase, run directory or execution mode.')
    root = project / '.newts/framework-runs' / study / definition['id']
    if not root.resolve().is_relative_to(project):
        raise ValueError('Framework records must remain inside the project.')
    evidence = selected.get('outputs')
    if not isinstance(evidence, list) or not evidence or any(not isinstance(p, str) or not p or
            p.startswith(('/', '\\')) or ':' in p or '..' in p.replace('\\', '/').split('/') for p in evidence):
        raise ValueError('Declare phase outputs as relative file paths before execution.')
    accept = selected.get('accept', {})
    if not isinstance(accept, dict) or any(p not in evidence or not isinstance(checks, dict) or
            any(not isinstance(allowed, list) or not allowed for allowed in checks.values()) for p, checks in accept.items()):
        raise ValueError('Acceptance checks must name declared outputs and lists of allowed JSON field values.')
    values = dict(config.get('inputs') or {}, project=str(project), study=study, phase=phase,
                  run_dir=str(root / 'run'))
    if any(not isinstance(v, str) for v in values.values()):
        raise ValueError('Framework inputs must be text.')
    command = argv(config.get('command', definition.get('command')))
    cwd = Path(config.get('cwd') or project).expanduser()
    if not cwd.is_absolute():
        cwd = project / cwd
    if not cwd.is_dir():
        raise ValueError('The framework working directory does not exist.')
    result = {'framework': definition['id'], 'phase': phase, 'project': str(project), 'study': study,
              'cwd': str(cwd.resolve()), 'run_dir': values['run_dir'], 'receipt': str(root / (phase + '.json')),
              'commands': [command + expand(parts, values, extra) for parts in
                           [definition['check'], selected.get('command', definition['run'])]],
              'outputs': selected.get('outputs', []), 'accept': selected.get('accept', {}),
              'timeout_seconds': config.get('timeout_seconds')}
    timeout = result['timeout_seconds']
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout < float('inf'):
        raise ValueError('Set a positive timeout_seconds in .newts/frameworks.yaml; no budget is assumed.')
    return result


def outputs(plan):
    root, evidence = Path(plan['run_dir']).resolve(), {}
    for relative in plan['outputs']:
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError('Required framework output is missing or unsafe: ' + relative)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Receipt evidence must be at most 32 MiB; reference larger artifacts from a manifest.')
        data = path.read_bytes()
        checks = plan['accept'].get(relative, {})
        document = json.loads(data) if checks else {}
        if not isinstance(document, dict):
            raise ValueError(relative + ': expected a JSON object.')
        for key, allowed in checks.items():
            if document.get(key) not in allowed:
                raise ValueError(f'{relative}: {key} does not satisfy the phase contract.')
        evidence[relative] = hashlib.sha256(data).hexdigest()
    if not evidence:
        raise ValueError('Declare at least one phase output before execution.')
    return evidence


def execute(value, retry=False):
    from executor.procs import RunLock, NO_WINDOW, graceful_stop
    receipt = Path(value['receipt'])
    receipt.parent.mkdir(parents=True, exist_ok=True)
    lock = RunLock(receipt.parent / 'execution.lock')
    if not lock.try_acquire():
        raise ValueError('Another phase of this campaign is running.')
    try:
        signature = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        old = json.loads(receipt.read_text()) if receipt.exists() else None
        if old:
            if not isinstance(old, dict) or old.get('signature') != signature:
                raise ValueError('The saved phase configuration changed. Review it before starting a new campaign.')
            if old['status'] == 'completed':
                if outputs(value) != old['evidence']:
                    raise ValueError('Saved evidence changed; do not reuse this completion.')
                return old
            if not retry:
                raise ValueError('An earlier attempt did not complete. Inspect its log and use --retry explicitly.')
        state = dict(value, signature=signature, status='running', started=time.time())
        def save():
            temp = receipt.with_suffix('.tmp')
            temp.write_text(json.dumps(state, indent=2), encoding='utf-8')
            os.replace(temp, receipt)
        save()
        previous = signal.getsignal(signal.SIGTERM)
        def interrupted(_signum, _frame):
            raise KeyboardInterrupt('The framework phase was interrupted.')
        signal.signal(signal.SIGTERM, interrupted)
        try:
            with receipt.with_suffix('.log').open('ab') as log:
                deadline = time.monotonic() + value['timeout_seconds']
                for command in value['commands']:
                    with subprocess.Popen(command, cwd=value['cwd'], stdin=subprocess.DEVNULL,
                                          stdout=log, stderr=subprocess.STDOUT, **NO_WINDOW) as child:
                        try:
                            code = child.wait(timeout=max(.01, deadline-time.monotonic()))
                        except BaseException:
                            graceful_stop(child, grace=3)
                            child.wait()
                            raise
                    if code:
                        raise ValueError(f'Framework command exited {code}. Inspect {receipt.with_suffix(".log")}')
            state.update(status='completed', evidence=outputs(value))
        except (Exception, KeyboardInterrupt) as error:
            state.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error=str(error))
            raise
        finally:
            signal.signal(signal.SIGTERM, previous)
            state['finished'] = time.time()
            save()
        return state
    finally:
        lock.release()


def task_prompt(hub, project, slug, external):
    from lab_profile import runtime_file
    validate(external)
    fid, phase = external['framework'], external['phase']
    definition = definitions(hub).get(fid)
    if not definition or phase not in definition.get('phases', {}):
        raise ValueError('Unknown external framework or phase.')
    command = [runtime_file(hub, 'tools/frameworks.py').as_posix(), '--definition', Path(definition['file']).as_posix(),
               '--project', str(project).replace('\\', '/'), '--study', slug, '--phase', phase]
    return (f'\nRead {runtime_file(hub, ".claude/skills/external-framework/SKILL.md").as_posix()}.\n'
            f'Framework argv (prepend this host\'s Python interpreter with PyYAML): {json.dumps(command)}\n'
            'Use a subprocess argument array, not a shell command assembled from paths. '
            'First add --plan to inspect the command. Then run without --plan. '
            'A prior failure requires inspection and explicit --retry, never an automatic restart. '
            'Read the receipt and original evidence. Report done only after a completed receipt and evidence review; '
            'a negative result is not an infrastructure failure. Publish a concise evidence-linked summary. '
            'Do not launch other phases or approve gates.\n')


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--definition', required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--study', required=True)
    parser.add_argument('--phase', required=True)
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--retry', action='store_true')
    args = parser.parse_args(args)
    try:
        definition = dict(read(args.definition), id=Path(args.definition).stem)
        value = plan(definition, args.project, args.study, args.phase)
        print(json.dumps(value if args.plan else execute(value, args.retry), indent=2))
        return 0
    except (ValueError, OSError, TimeoutError, subprocess.TimeoutExpired, yaml.YAMLError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
