"""Shared feature contracts through each adapter. CLI peers simulate model output, not providers."""
import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from conftest import REPO, kernel, load


@pytest.mark.parametrize('backend', ['claude','codex','opencode','acp'])
def test_starter_records_roles_and_published_explanations_use_every_adapter(hub,tmp_path,monkeypatch,backend):
    monkeypatch.syspath_prepend(str(REPO/'tools'))
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    import executor
    if backend == 'opencode':
        node=shutil.which('node')
        if not node:pytest.skip('opencode protocol peer requires Node.js')
        command=[node,str(REPO/'tests/fake_opencode.mjs')]
    else:
        command=[sys.executable,str(REPO/'tests'/('fake_'+backend+'.py'))]
    config={'lab':{'projects_root':'../projects'},'agents':{'programmatic':{
        'enabled':True,'backend':backend,'max_depth':1,'live':{'enabled':backend=='acp','linger_minutes':0},
        'backends':{backend:{'command':command}}}}}
    # The executor's documented switch accepts false or a mapping for live settings.
    if backend != 'acp':config['agents']['programmatic']['live']=False
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(config),encoding='utf-8')
    (hub.root/'tools').mkdir(exist_ok=True)
    shutil.copyfile(REPO/'tools/lab_bus.py',hub.root/'tools/lab_bus.py')
    monkeypatch.setenv('FAKE_MODE','complete')
    api=load('dashboard/starter')
    monkeypatch.setattr(api.ctx,'HUB',hub.root);monkeypatch.setattr(api.ctx,'LAB',hub.lab)
    lab=executor.Lab(hub.root)

    def finish(rid):
        until=time.monotonic()+90
        while time.monotonic()<until:
            executor.tick(lab)
            m=executor.find_run(lab,rid)[3]
            if m['status'] in ('completed','failed','killed','timeout'):
                assert m['status']=='completed',m
                return m
            time.sleep(.1)
        executor.stop(lab,rid)
        pytest.fail('Adapter did not complete the fixture turn: '+rid+' ('+m['status']+')')

    draft,status=api.draft_op({'action':'create'});assert status==201
    source=b'# Brief\nCompare the two proposed mechanisms. No results exist yet.\n'
    draft,status=api.draft_op({'id':draft['id'],'action':'upload','name':'brief.md','data':base64.b64encode(source).decode()})
    assert status==200
    # Omitted backend must honor the configured lab default rather than force Claude.
    draft,status=api.draft_op({'id':draft['id'],'action':'analyze','inputs':{'question':'Compare mechanisms.','tags':[]}})
    assert status==200,draft
    suggestion_run=executor.find_run(lab,draft['run_id'])[3]
    assert suggestion_run['backend']==backend and suggestion_run['chain']=='off'
    folder=api.M.folder(hub.root,draft['id'])/'analyses'/draft['analysis']
    request=json.loads((folder/'request.json').read_text())
    assert source==Path(request['materials'][0]['path']).read_bytes()
    # Simulate the structured file authored by a model; parsing is common to all adapters.
    (folder/'suggestion.json').write_text(json.dumps({'title':'Mechanism study','question':'Which mechanism explains the observations?',
        'workflow':'quick','tags':['mechanisms'],'analysis':'A fixture suggestion, not a scientific result.'}),encoding='utf-8')
    assert not api.draft_view({'id':draft['id']})[0].get('suggestion')
    finish(draft['run_id'])
    suggestion=api.draft_view({'id':draft['id']})[0]['suggestion']
    assert suggestion['workflow']=='quick'

    project=tmp_path/'existing-project';project.mkdir();(project/'README.md').write_text('Keep existing work.\n')
    result,status=api.create({'confirm':True,'draft':draft['id'],'local':str(project),
        **{k:suggestion[k] for k in ('title','question','workflow','tags')}})
    assert status==201,result
    slug=result['study'];records=hub.root/'studies'/slug
    assert next((records/'materials').iterdir()).read_bytes()==source
    review=executor.enqueue(lab,executor.RunSpec('',target=slug,prompt='Inspect the supplied study materials.',role='reviewer'))
    assert review['backend']==backend and review['context']['mode']=='fresh'
    rd=executor.run_dir(lab.agents_dir(project),review['run_id'])
    pre=(rd/'preamble.md').read_text(encoding='utf-8')
    assert 'Independently assess' in pre and 'MATERIALS.md' in pre and records.as_posix() in pre
    finish(review['run_id'])

    page=project/'explanation.html';page.write_text('<!doctype html><h1>Mechanism review</h1><p>No measurements claimed.</p>')
    env={**os.environ,'ARLOTOPE_HUB':str(hub.root),'ARLOTOPE_RUN_ID':review['run_id'],'ARLOTOPE_RUN_SUBJECT':slug}
    env['ARLOTOPE_RUN_DIR']=str(rd)
    executor.profile.run_env(review,env)
    footer=subprocess.run([sys.executable,str(executor.profile.bus_script(hub.root,'project',project)),
        'emit','run_report','--data','summary=Reviewed the materials.'],cwd=project,env=env,capture_output=True,text=True,timeout=15)
    assert footer.returncode==0,footer.stderr
    from executor.scheduler import read_report
    assert read_report(lab,project,review['run_id'])['summary']=='Reviewed the materials.'
    assert not (project/'scripts').exists()  # No scaffolding was needed for the footer.
    published=subprocess.run([sys.executable,str(REPO/'tools/artifact.py'),'publish','--title','Mechanism review',
        '--file',str(page),'--about',review['run_id']],cwd=project,env=env,capture_output=True,text=True,timeout=15)
    assert published.returncode==0,published.stderr
    artifacts=load('dashboard/artifacts')
    rows,status=artifacts.list_artifacts({'study':slug,'about':review['run_id']})
    assert status==200 and len(rows['artifacts'])==1
    saved=rows['artifacts'][0]
    assert saved['study']==slug and saved['run_id']==review['run_id'] and saved['kind']=='html'
    assert artifacts.file_route({'id':saved['id']})[0].read_text().startswith('<!doctype html>')
    assert kernel().journal.approvals(hub.root)==[]
    assert (project/'README.md').read_text()=='Keep existing work.\n'
