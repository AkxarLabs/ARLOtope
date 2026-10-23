"""Attach-first studies. No project scaffolding, dependency installation or agent launch."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import uuid
from contextlib import contextmanager
import urllib.error
import urllib.request
from pathlib import Path

import yaml

import labfiles
from kernel import model, studies


class StartError(ValueError):
    pass


@contextmanager
def _clone_staging(parent):
    # This becomes a real workspace. tempfile's owner-only Windows DACL would
    # survive the checkout's rename and exclude the agent's sandbox identity.
    parent = Path(parent).resolve()
    folder = parent / ('.arlotope-clone-' + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        if folder.is_symlink() or folder.resolve().parent != parent:
            raise StartError('Clone staging folder changed unexpectedly; left it in place.')
        shutil.rmtree(folder)


def repository(value: str) -> str:
    """Accept an exact owner/repository or its ordinary GitHub HTTPS URL."""
    if not isinstance(value, str):
        raise StartError('Use owner/repository or a GitHub repository URL.')
    value = re.sub(r'^https://github\.com/', '', value.strip(), flags=re.I).rstrip('/')
    value = value.removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}', value):
        raise StartError('Use owner/repository, for example numpy/numpy.')
    if value.split('/')[1] in ('.', '..'):
        raise StartError('A repository name is required.')
    return value


def github(value: str, authenticated=False) -> dict:
    name = repository(value)
    request = urllib.request.Request('https://api.github.com/repos/' + name,
        headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'ARLOtope-Lab'})
    try:
        if authenticated:
            import github_access
            data = github_access.repository(name)
        else:
            with urllib.request.urlopen(request, timeout=12) as response:
                data = json.loads(response.read(1_000_001))
    except urllib.error.HTTPError as error:
        message = {404: 'Repository not found. Use an exact public owner/repository, or attach a local checkout.',
                   403: 'GitHub is limiting requests. Try later, or attach a local checkout.',
                   429: 'GitHub is limiting requests. Try later, or attach a local checkout.'}
        raise StartError(message.get(error.code, 'GitHub could not read that repository.')) from None
    except (OSError, ValueError) as error:
        raise StartError('Could not reach GitHub. You can attach a local checkout instead.') from error
    if not isinstance(data, dict) or data.get('private') and not authenticated or not data.get('full_name'):
        raise StartError('Choose a public GitHub repository, or attach a local checkout.')
    canonical = repository(data['full_name'])
    return {'name': canonical, 'url': 'https://github.com/' + canonical,
            'description': str(data.get('description') or '')[:500],
            'language': data.get('language'), 'archived': bool(data.get('archived')), 'private': bool(data.get('private'))}


def projects_root(hub: Path) -> Path:
    configured = labfiles.config(hub).get('lab') or {}
    path = Path(configured.get('projects_root') or '../arlotope-projects').expanduser()
    return (path if path.is_absolute() else hub / path).resolve()


def context(hub: Path) -> dict:
    from kernel import branches, entry
    from frameworks import requirements
    topics = hub / 'lab/RESEARCH.md'
    return {'topics': topics.read_text(encoding='utf-8') if topics.is_file() else '',
            'projects_root': str(projects_root(hub)),
            'workflows': [{'id': w['id'], 'title': w['title'], 'blurb': w.get('blurb', ''),
                           'requires': requirements(w),
                           'steps': w['path'], 'default': bool(w.get('default')),
                           'tasks': [dict(n, outcomes={**w.get('routes', {}).get(n['id'], {}), **n.get('outcomes', {})}) for n in branches.nodes(w, model.steps(hub))], 'entry_revision': entry.revision(hub, w),
                           'checkpoints': w['checkpoints']}
                          for w in model.workflows(hub)]}


def create(hub: Path, *, title: str, question: str, slug: str = '', workflow: str = '',
           local: str = '', repo: str = '', machine: str = '', agents=None, tags=None, draft: str = '', entry=None, github_auth=False) -> dict:
    """Create only a hub study record and an optional project pointer or new clone."""
    if studies.in_agent_run():
        raise StartError('The researcher creates and attaches studies; agents can propose them.')
    hub = Path(hub).resolve()
    if draft:
        import study_materials
        material_path, material_meta = study_materials.load(hub, draft)
        for item in material_meta['files']:
            study_materials.file_path(material_path, item)
    import tagging
    try:
        tags = tagging.normalize(tags)
    except ValueError as exc:
        raise StartError(str(exc)) from exc
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise StartError('Give the study a title (up to 200 characters).')
    if not isinstance(question, str) or not question.strip() or len(question) > 6000:
        raise StartError('Describe the question or the first task (up to 6000 characters).')
    if not all(isinstance(x, str) for x in (slug, workflow, local, repo)):
        raise StartError('Study, workflow and repository fields must be text.')
    slug = slug.strip() or re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]
    if not model.SLUG.fullmatch(slug) or len(slug) > 80:
        raise StartError('Use a short study ID with lowercase letters, digits and dashes.')
    if slug in studies.all_studies(hub):
        raise StartError('That study ID already exists. Choose another.')
    if agents:
        if not isinstance(agents, dict) or any(key not in ('default_preset','role_presets') for key in agents):
            raise StartError('Study agent choices must contain a default and optional role choices.')
        from executor import assignments, Lab
        cfg, _ = assignments.settings(Lab(hub))
        assignments.bindings(agents.get('role_presets') or {}, cfg['presets'] or {})
        if agents.get('default_preset') and agents['default_preset'] not in (cfg['presets'] or {}):
            raise StartError('Choose an existing agent preset.')
    flow = model.workflow(workflow or None, hub)
    if workflow and flow['id'] != workflow:
        raise StartError('Choose one of this lab\'s workflows.')
    from kernel import entry as entry_plan
    entry = entry_plan.prepare(hub, flow, entry)
    if entry:
        entry_plan.preview(hub, flow, entry)
    if local and repo and not machine:
        raise StartError('Choose a local folder or a GitHub repository.')
    project = None
    if machine:
        import remote_projects as remote
        remote.machine(machine)
        remote.uri(machine, local)
        if not local:
            raise StartError('Choose a folder on the remote machine.')
    if local and not machine:
        project = Path(local).expanduser()
        if not project.is_absolute():
            raise StartError('Use an absolute path to your project folder.')
        project = project.resolve()
        if not project.is_dir() or project == hub or project in hub.parents:
            raise StartError('Choose an existing project folder, separate from the lab itself.')
    canonical = repository(repo) if repo else None
    destination = projects_root(hub) / slug if canonical and not machine else None
    if destination and (destination.exists() or destination == hub or destination in hub.parents):
        raise StartError('The clone destination already exists. Attach that folder or choose another study ID.')
    folder = hub / 'studies' / slug
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise StartError('That study folder already exists. Choose another study ID.') from None
    try:
        if machine:
            import remote_projects as remote
            if canonical:
                remote.rpc(machine, 'clone', {'path': local, 'repository': canonical, 'github_auth': github_auth is True})
            from project_identity import lab_identity
            attached = remote.rpc(machine, 'attach', {'path': local, 'owner': remote.owner(hub), 'study': slug,
                                                     'lab_id':lab_identity(hub)['lab_id'],'title':title.strip()})
            project = remote.uri(machine, attached['path'])
        if canonical and not machine:
            if not shutil.which('git'):
                raise StartError('Git is not installed. Install Git, or attach an existing local folder.')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with _clone_staging(destination.parent) as temporary:
                checkout = Path(temporary) / 'checkout'
                env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'Never'}
                if github_auth is True:
                    from github_access import clone_argv
                    argv = clone_argv(canonical, checkout)
                    env['GH_PROMPT_DISABLED'] = '1'
                else:
                    argv = ['git', 'clone', '--', 'https://github.com/' + canonical + '.git', str(checkout)]
                try:
                    result = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8',
                                            errors='replace', env=env, timeout=180)
                except (OSError, subprocess.TimeoutExpired) as error:
                    raise StartError('Cloning did not finish. Retry, or attach a local checkout.') from error
                if result.returncode:
                    raise StartError('Git could not clone that repository. Check the name and network, or attach a local checkout.')
                # Rename cannot replace a populated directory; the destination must still be unused.
                if destination.exists():
                    raise StartError('The clone destination was created by another process. Choose another study ID.')
                checkout.rename(destination)
            project = destination
        if project and not machine:
            from project_identity import register, lab_identity
            ident = lab_identity(hub)
            register(project,ident['execution_owner'],slug,ident['lab_id'],title.strip())
        metadata = yaml.safe_dump({'title': title.strip(), 'workflow': flow['id'], 'tags': tags,
            'project_mode': 'attached' if project else 'new',
            **({'repository': 'https://github.com/' + canonical} if canonical else {})},
            sort_keys=False, allow_unicode=True).strip()
        text = '---\n' + metadata + '\n---\n\n# Research question\n\n' + question.strip() + '\n'
        if project:
            text += ('\n## Existing project\n\nInspect the existing code and environment before proposing changes. '
                     'Add research scaffolding only when the researcher requests it.\n')
        (folder / 'IDEA.md').write_text(text, encoding='utf-8')
        if draft:
            count = study_materials.attach(hub, draft, folder, meta=material_meta)
            if count:
                with (folder / 'IDEA.md').open('a', encoding='utf-8') as record:
                    record.write('\n## Supporting materials\n\nRead [MATERIALS.md](MATERIALS.md) for the supplied project brief and files.\n')
        if agents:
            target = folder/'workflow/agents.yaml';target.parent.mkdir(exist_ok=True)
            target.write_text(yaml.safe_dump(agents, sort_keys=False), encoding='utf-8')
        studies.new(hub, slug, title.strip(), workflow=flow['id'], by='pi', entry=entry)
        if project:
            studies.set_project(hub, slug, str(project), by='pi')
        if entry:
            entry_plan.apply(hub, slug)
        return {'ok': True, 'study': slug, 'project': str(project) if project else None,
                'workflow': flow['id'], 'cloned': bool(canonical)}
    except Exception:
        # Only our newly reserved study folder is eligible; never remove an attached project or clone.
        if slug not in studies.all_studies(hub):
            # This exact folder was reserved above; only our study record is rolled back.
            if folder.resolve().parent == (hub / 'studies').resolve() and not folder.is_symlink():
                shutil.rmtree(folder)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hub', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--title', required=True)
    parser.add_argument('--question', required=True)
    parser.add_argument('--slug', default='')
    parser.add_argument('--workflow', default='')
    parser.add_argument('--local', default='')
    parser.add_argument('--repo', default='')
    parser.add_argument('--machine', default='')
    parser.add_argument('--tags', default='', help='comma-separated labels')
    args = vars(parser.parse_args())
    try:
        print(json.dumps(create(**args), indent=2))
    except (ValueError, studies.StudyError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
