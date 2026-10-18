"""Original briefs, optional agent assistance, and safe local folder browsing."""
import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, load, kernel


@pytest.fixture(autouse=True)
def tools_path(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'tools'))


def draft(hub):
    m = load('study_materials')
    meta = m.new(hub.root)
    path, _ = m.load(hub.root, meta['id'])
    return m, path, meta


def test_materials_keep_original_bytes_collisions_and_no_automatic_agent(hub):
    m, path, meta = draft(hub)
    original = b'%PDF-1.7\n\x00\xfforiginal brief'
    for _ in range(2):
        m.upload(path,meta,'../brief.pdf',base64.b64encode(original).decode())
    assert len({f['stored'] for f in meta['files']}) == 2
    result = load('research_start').create(hub.root,title='Brief study',question='Review the mechanism.',draft=meta['id'])
    records = hub.root / 'studies' / result['study']
    assert [p.read_bytes() for p in (records/'materials').iterdir()] == [original,original]
    assert 'MATERIALS.md' in (records/'IDEA.md').read_text()
    assert '../brief.pdf' in (records/'MATERIALS.md').read_text()
    assert not (hub.root/'lab/.bus/agents').exists()
    assert kernel().journal.approvals(hub.root) == []
    assert m.load(hub.root,meta['id'])[1]['files'] == meta['files']


@pytest.mark.parametrize('name,data', [('brief.txt','not base64!'), ('', 'eA=='), ('brief.txt','A'*7_000_000)], ids=['encoding','filename','size'])
def test_invalid_upload_leaves_draft_unchanged(hub,name,data):
    m,path,meta=draft(hub)
    with pytest.raises(ValueError):m.upload(path,meta,name,data)
    assert m.load(hub.root,meta['id'])[1]['files'] == []


def test_material_totals_and_ids_are_bounded(hub,monkeypatch):
    m,path,meta=draft(hub)
    monkeypatch.setattr(m,'TOTAL_LIMIT',3)
    m.upload(path,meta,'first.txt','eHg=')
    with pytest.raises(ValueError,match='20 MB'):m.upload(path,meta,'second.txt','eHg=')
    for value in ('../elsewhere','',None,[], 'a'*32):
        with pytest.raises(ValueError):m.folder(hub.root,value)
    with pytest.raises(ValueError):m.file_path(path,{'stored':'../draft.json'})


def test_remove_frees_unused_uploads_but_keeps_agent_inputs_within_quota(hub,monkeypatch):
    m,path,meta=draft(hub)
    monkeypatch.setattr(m,'TOTAL_LIMIT',3)
    m.upload(path,meta,'first.txt','eHg=')
    original=m.file_path(path,meta['files'][0])
    m.remove(path,meta,meta['files'][0]['stored'])
    assert not original.exists()
    m.upload(path,meta,'replacement.txt','eHg=')
    work=path/'analyses'/('a'*32);work.mkdir(parents=True)
    original=m.file_path(path,meta['files'][0])
    (work/'request.json').write_text(json.dumps({'materials':[{'path':str(original)}]}))
    m.remove(path,meta,meta['files'][0]['stored'])
    assert original.exists() and not meta['files']
    with pytest.raises(ValueError,match='earlier agent inputs'):m.upload(path,meta,'extra.txt','eHg=')


def test_missing_material_does_not_create_partial_study(hub):
    m,path,meta=draft(hub)
    m.upload(path,meta,'brief.md','aGVsbG8=')
    m.file_path(path,meta['files'][0]).unlink()
    with pytest.raises(ValueError):
        load('research_start').create(hub.root,title='Missing brief',question='Why?',draft=meta['id'])
    assert not (hub.root/'studies/missing-brief').exists()


def test_failed_registration_rolls_back_only_new_record(hub,monkeypatch,tmp_path):
    m,path,meta=draft(hub)
    m.upload(path,meta,'brief.md','aGVsbG8=')
    start=load('research_start')
    project=tmp_path/'existing';project.mkdir();(project/'keep.txt').write_text('keep')
    monkeypatch.setattr(start.studies,'new',lambda *a,**k:(_ for _ in ()).throw(ValueError('failed registration')))
    with pytest.raises(ValueError,match='failed registration'):
        start.create(hub.root,title='Rollback',question='Why?',local=str(project),draft=meta['id'])
    assert not (hub.root/'studies/rollback').exists()
    assert (project/'keep.txt').read_text()=='keep'
    assert m.file_path(path,meta['files'][0]).read_bytes()==b'hello'


def adapter(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    module=load('dashboard/starter')
    monkeypatch.setattr(module.ctx,'HUB',hub.root)
    monkeypatch.setattr(module.ctx,'LAB',hub.lab)
    return module


def test_assistance_is_explicit_uses_normal_queue_and_keeps_draft_inputs(hub,monkeypatch):
    api=adapter(hub,monkeypatch)
    created,status=api.draft_op({'action':'create'});assert status==201
    seen=[]
    monkeypatch.setattr(api,'enqueue',lambda lab,spec:seen.append(spec) or {'run_id':'suggestion-run'})
    state={'status':'running'}
    monkeypatch.setattr(api,'find_run',lambda *_:(None,None,None,state))
    upload,status=api.draft_op({'id':created['id'],'action':'upload','name':'brief.txt','data':'aGVsbG8='})
    assert status==200 and not seen
    inputs={'question':'Compare mechanisms','title':'','workflow':'quick','tags':[],'instructions':'List missing assumptions.'}
    data,status=api.draft_op({'id':created['id'],'action':'analyze','backend':'codex','inputs':inputs})
    assert status==200 and len(seen)==1 and seen[0].backend=='codex'
    assert seen[0].skill=='' and seen[0].chain=='off'
    work=api.M.folder(hub.root,created['id'])/'analyses'/data['analysis']
    request=json.loads((work/'request.json').read_text())
    assert request['fields']==inputs and Path(request['materials'][0]['path']).read_text()=='hello'
    assert 'suggestion.json' in (work/'README.md').read_text()
    assert api.draft_op({'id':created['id'],'action':'analyze','inputs':inputs})[1]==400
    (work/'suggestion.json').write_text(json.dumps({'title':'Suggested','question':'Question?','workflow':'quick',
        'tags':['method'],'analysis':'A hypothesis is missing.','machine':'malicious','confirm':True}))
    assert not api.draft_view({'id':created['id']})[0].get('suggestion')
    state['status']='completed'
    view,status=api.draft_view({'id':created['id']})
    assert view['suggestion']['title']=='Suggested' and 'machine' not in view['suggestion']
    assert view['inputs']==inputs and view['analysis_revision']==view['revision']
    updated,_=api.draft_op({'id':created['id'],'action':'remove','file':view['files'][0]['stored']})
    assert updated['analysis_revision']!=updated['revision'] and updated['version']>view['version']
    assert not kernel().studies.rows(hub.root)


def test_materials_appear_and_open_in_library(hub,monkeypatch):
    m,path,meta=draft(hub)
    m.upload(path,meta,'brief.pdf',base64.b64encode(b'%PDF-original').decode())
    m.upload(path,meta,'notes.docx','ZG9jeA==')
    load('research_start').create(hub.root,title='Library study',question='Why?',draft=meta['id'])
    api=adapter(hub,monkeypatch)
    library=load('dashboard/library')
    tree=library.lib_tree()
    group=next(g for g in tree['groups'] if g.get('slug')=='library-study')
    assert any(s['title']=='Materials' and len(s['docs'])==2 for s in group['sections'])
    for item in meta['files']:
        rel='materials/'+item['stored']
        assert library.lib_doc('study','library-study',rel)['format']=='file'
        assert library.lib_file('study','library-study',rel)[0].read_bytes()==m.file_path(path,item).read_bytes()
    assert library.lib_file('study','library-study','materials/../../../../lab/config.yaml') is None


def test_clear_draft_preserves_created_study_and_refuses_active_agent(hub,monkeypatch):
    api=adapter(hub,monkeypatch)
    meta,_=api.draft_op({'action':'create'})
    meta,_=api.draft_op({'id':meta['id'],'action':'upload','name':'brief.md','data':'aGVsbG8='})
    load('research_start').create(hub.root,title='Keep study',question='Why?',draft=meta['id'])
    path,state=api.M.load(hub.root,meta['id']);state['run_id']='draft-agent';api.M.save(path,state)
    monkeypatch.setattr(api,'find_run',lambda *_:(None,None,None,{'status':'running'}))
    assert api.draft_op({'action':'discard','id':meta['id']})[1]==400 and path.exists()
    monkeypatch.setattr(api,'find_run',lambda *_:(None,None,None,{'status':'completed'}))
    assert api.draft_op({'action':'discard','id':meta['id']})[1]==200 and not path.exists()
    records=hub.root/'studies/keep-study'
    assert len(list((records/'materials').iterdir()))==1 and (records/'MATERIALS.md').exists()


def test_browse_is_shallow_no_files_and_resolves_home(tmp_path,monkeypatch):
    browse=load('project_files').browse
    (tmp_path/'Research').mkdir();(tmp_path/'.hidden').mkdir();(tmp_path/'file.txt').write_text('private')
    monkeypatch.setattr(Path,'home',classmethod(lambda _:tmp_path))
    data=browse(str(tmp_path))
    assert [r['name'] for r in data['folders']]==['Research']
    assert {r['name'] for r in browse(str(tmp_path),True)['folders']}=={'.hidden','Research'}
    assert data['parent']==str(tmp_path.parent) and data['home']==str(tmp_path)
    with pytest.raises(ValueError):browse(str(tmp_path/'file.txt'))
    with pytest.raises(ValueError):browse('relative/path')
    with pytest.raises(OSError):browse(str(tmp_path/'missing'))


def test_upload_route_body_limit_does_not_expand_other_routes(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    server=load('dashboard/serve')
    handler=object.__new__(server.Handler)
    handler.headers={'Content-Length':str(7*1024*1024)}
    for path,limit in [('/api/starter/draft',7*1024*1024),('/api/starter',1024*1024)]:
        handler.path=path;handler.rfile=io.BytesIO(b'x'*(7*1024*1024))
        assert len(handler._raw_body())==limit
