"""Project records, read receipts and independently persisted workspace answers."""
import json
import sys
from pathlib import Path
import pytest
import yaml
from conftest import REPO, load

sys.path.insert(0,str(REPO/'tools'))
import knowledge as K


def test_durable_project_identity_survives_index_loss(tmp_path,monkeypatch):
    import project_identity as I
    monkeypatch.setenv('NEWTS_HOME',str(tmp_path/'home'))
    root=tmp_path/'project';root.mkdir()
    first=I.register(root,'owner','study','lab-id','Readable name')
    durable=json.loads((root/'.newts/project.json').read_text())
    assert durable['project_id']==first['project_id'] and durable['lab_id']=='lab-id'
    assert durable['knowledge_dir']=='.newts/knowledge'
    assert I.register(root,'owner','study','lab-id')['project_id']==first['project_id']
    (tmp_path/'home/projects.json').unlink();(root/'.bus/newts-owner.json').unlink()
    found=I.discover(tmp_path)
    assert found[0]['title']=='Readable name' and found[0]['project_id']==first['project_id']


def test_identity_conflict_does_not_replace_existing_marker(tmp_path,monkeypatch):
    import project_identity as I
    monkeypatch.setenv('NEWTS_HOME',str(tmp_path/'home'))
    root=tmp_path/'project';root.mkdir()
    I.register(root,'owner','study','lab-id')
    before=(root/'.bus/newts-owner.json').read_bytes()
    with pytest.raises(ValueError):I.register(root,'other','study','other-lab')
    assert (root/'.bus/newts-owner.json').read_bytes()==before


@pytest.mark.parametrize('conflict', ['lab', 'owner', 'study', 'project'])
def test_identity_conflicts_identify_the_selected_project_without_mutation(tmp_path, monkeypatch, conflict):
    import project_identity as I
    monkeypatch.setenv('NEWTS_HOME', str(tmp_path/'home'))
    root = tmp_path/'research with spaces 研究'; root.mkdir()
    original = I.register(root, 'original-owner', 'original-study', 'original-lab')
    args = {'owner': 'original-owner', 'study': 'original-study', 'lab_id': 'original-lab'}
    if conflict == 'project':
        identity = root/'.newts/project.json'
        data = json.loads(identity.read_text(encoding='utf-8'))
        data['project_id'] = 'conflicting-project'
        identity.write_text(json.dumps(data), encoding='utf-8')
    else:
        args[{'lab': 'lab_id', 'owner': 'owner', 'study': 'study'}[conflict]] = 'different'
    paths = [root/'.bus/newts-owner.json', root/'.newts/project.json', I.home()/'projects.json']
    before = {path: path.read_bytes() for path in paths}
    with pytest.raises(ValueError) as error:
        I.register(root, **args)
    message = str(error.value)
    assert str(root.resolve()) in message
    if conflict == 'lab':
        assert 'original-lab' in message and 'owning Lab' in message
    elif conflict == 'project':
        assert original['project_id'] in message and 'conflicting-project' in message
        assert '.bus/newts-owner.json' in message and '.newts/project.json' in message
    else:
        assert 'original-study' in message and 'original-owner' in message
    assert {path: path.read_bytes() for path in paths} == before


def test_new_lab_does_not_copy_owner_identity_or_personal_records(hub):
    from project_identity import lab_identity
    tool=load('new_lab')
    original=lab_identity(hub.root)
    K.dispatch(hub.root,None,'add',text='Private template note')
    tool._reset_state(hub.root)
    assert not (hub.lab/'records').exists()
    assert lab_identity(hub.root)['lab_id']!=original['lab_id']


def test_human_note_does_not_queue_work_or_modify_source(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/knowledge_api');monkeypatch.setattr(api.ctx,'HUB',hub.root)
    monkeypatch.setattr(api.ctx,'pi_log',lambda *_:None)
    hub.add_registry_row('study')
    source=hub.root/'studies/study/IDEA.md';source.write_text('# Unchanged source')
    before=source.read_bytes()
    for ack in (True,False):
        body={'study':'study','text':'Human context','about':{'scope':'study','slug':'study','rel':'IDEA.md'}}
        if not ack:body['acknowledge']=False
        result,code=api.note(body)
        assert code==200 and bool(result['record'].get('acknowledge'))==ack
    assert source.read_bytes()==before
    assert not list(hub.root.rglob('directives.jsonl'))
    assert not list(hub.root.rglob('agents/*.json'))
    rows=K.dispatch(hub.root,'study')['rows'];assert len(rows)==2
    requested=next(r for r in rows if r.get('acknowledge'))
    folder=K.location(hub.root,'study')['folder']
    for _ in range(2):K.update(folder,requested['id'],acknowledgement={'run':'reader-1'})
    saved=K.get(folder,requested['id']);assert len(saved['acknowledgements'])==1


def test_records_search_nested_plain_files_and_pagination(tmp_path):
    folder=tmp_path/'knowledge';(folder/'literature').mkdir(parents=True)
    (folder/'literature/Useful paper.md').write_text('# Read paper\nUnique terminology',encoding='utf-8')
    for i in range(4):K.create(folder,text='Progress '+str(i),tags=['methods'])
    found=K.listing(folder,query='unique');assert found['total']==1
    saved=K.get(folder,found['rows'][0]['id']);assert 'Unique terminology' in saved['text']
    assert K.listing(folder,limit=2)['next']==2
    assert K.listing(folder,offset=2,limit=2)['total']==5
    moved=K.create(folder,text='Moved record')
    (folder/(moved['id']+'.md')).rename(folder/'literature/moved.md')
    assert K.get(folder,moved['id'])['text']=='Moved record\n'
    with pytest.raises(ValueError):K.get(folder,'../outside')


def test_source_metadata_and_attachment_preserve_actual_coverage(tmp_path):
    original=tmp_path/'paper.pdf';original.write_bytes(b'%PDF-1.7\nfixture')
    r=K.create(tmp_path/'knowledge',kind='source',text='Read abstract only.',
               source={'url':'https://arxiv.org/abs/1234.5678','version':'v2','coverage':'abstract'},attachment=original)
    assert r['source']['coverage']=='abstract'
    assert (tmp_path/'knowledge'/r['attachment']).read_bytes()==original.read_bytes()
    assert 'Original attachment' in K.get(tmp_path/'knowledge',r['id'])['text']


def test_project_attachment_keeps_earlier_study_notes_visible(hub,tmp_path):
    from conftest import kernel
    hub.add_registry_row('study')
    old=K.dispatch(hub.root,'study','add',text='Before project.',acknowledge=True)
    root=tmp_path/'existing-project';root.mkdir()
    from kernel import studies
    studies.set_project(hub.root,'study',str(root))
    K.dispatch(hub.root,'study','add',text='After project.')
    assert K.dispatch(hub.root,'study','list')['total']==2
    K.dispatch(hub.root,'study','update',id=old['id'],acknowledgement={'run':'reader'})
    assert K.dispatch(hub.root,'study','get',id=old['id'])['scope']=='study'


def test_unicode_records_remain_readable_and_responses_are_idempotent(tmp_path):
    r=K.create(tmp_path,text='🦎'*150000)
    assert len(K.get(tmp_path,r['id'])['text'])>150000
    reply={'id':'result-1','at':K.now(),'text':'Full reply'}
    K.update(tmp_path,r['id'],response=reply)
    file=tmp_path/(r['id']+'.md');stamp=file.stat().st_mtime_ns
    K.update(tmp_path,r['id'],response=reply)
    assert file.stat().st_mtime_ns==stamp
    assert K.get(tmp_path,r['id'])['text'].count('Full reply')==1


def test_answer_delivery_retries_preserve_original_question(hub,monkeypatch):
    from executor import Lab
    lab=Lab(hub.root)
    a=K.dispatch(hub.root,None,'add',kind='answer',text='Question A')
    b=K.dispatch(hub.root,None,'add',kind='answer',text='Question B')
    original=K.dispatch
    monkeypatch.setattr(K,'dispatch',lambda *_a,**_k:(_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(OSError):K.save_answer(lab,{'id':a['id'],'study':None},{'id':'r1','at':K.now(),'text':'Answer A'})
    monkeypatch.setattr(K,'dispatch',original)
    K.save_answer(lab,{'id':b['id'],'study':None},{'id':'r2','at':K.now(),'text':'Answer B'})
    assert K.retry_answers(lab)==[]
    assert 'Answer A' in K.dispatch(hub.root,None,'get',id=a['id'])['text']
    assert 'Answer B' not in K.dispatch(hub.root,None,'get',id=a['id'])['text']
    assert not list((hub.lab/'.bus/knowledge-pending').glob('*.json'))


def test_workspace_question_is_separate_from_source_and_uses_selected_context(hub,monkeypatch):
    from executor import Lab,find_run
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/assistant');monkeypatch.setattr(api.ctx,'HUB',hub.root)
    hub.add_registry_row('study')
    monkeypatch.setattr(api.sources,'snapshot',lambda:{'items':[{'id':'study','title':'Study'}]})
    (hub.lab/'config.yaml').write_text(yaml.safe_dump({'agents':{'programmatic':{
        'enabled':True,'backend':'claude','live':False,
        'backends':{'claude':{'command':[sys.executable,str(REPO/'tests/fake_claude.py')]}}}}}))
    source=hub.root/'studies/study/IDEA.md';source.write_text('# Evidence\nOriginal file.')
    before=source.read_bytes()
    result,code=api.send({'text':'Explain the evidence','study':'study',
        'document':{'scope':'study','slug':'study','rel':'IDEA.md'}})
    assert code==200,result
    m=find_run(Lab(hub.root),result['run_id'])[3]
    assert m['knowledge_question']['study']=='study'
    q=K.dispatch(hub.root,'study','get',id=m['knowledge_question']['id'])
    assert q['about']['rel']=='IDEA.md' and q['run']==result['run_id']
    assert source.read_bytes()==before
    context=json.loads(next((hub.lab/'.bus/assistant-context').glob('*.json')).read_text())
    assert context['selected_document']['text'].startswith('# Evidence')


def test_codex_full_result_reaches_answer_recorder():
    from executor.backends import codex
    text='Detailed response '*1000
    b=codex.Codex()
    events=b.parse({'type':'item.completed','item':{'id':'answer','type':'agent_message','text':text}})
    assert next(e['last_message'] for e in events if e['event']=='result')==text


def test_download_is_limited_to_retained_attachment(hub,monkeypatch,tmp_path):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/knowledge_api');monkeypatch.setattr(api.ctx,'HUB',hub.root)
    source=tmp_path/'records.zip';source.write_bytes(b'PK\x03\x04fixture')
    record=K.dispatch(hub.root,None,'add',text='Supplementary data',attachment=source)
    file,ctype=api.attachment({'id':record['id']})
    assert file.read_bytes()==source.read_bytes() and ctype=='application/octet-stream'
    assert api.attachment({'id':'../outside'}) is None
    folder=K.location(hub.root,None)['folder']
    K.update(folder,record['id'],binding={'attachment':'../../outside.zip'})
    assert api.attachment({'id':record['id']}) is None


def test_empty_completed_workspace_turn_is_unanswered(hub):
    import executor
    lab=executor.Lab(hub.root)
    q=K.dispatch(hub.root,None,'add',kind='answer',text='Question',status='queued')
    K.sync_answer(lab,{'run_id':'empty','status':'completed','knowledge_question':{**q,'study':None}})
    assert K.dispatch(hub.root,None,'get',id=q['id'])['status']=='unanswered'


def test_workspace_assistant_opens_before_its_first_conversation(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/assistant');monkeypatch.setattr(api.ctx,'HUB',hub.root)
    monkeypatch.setattr(api.sources,'snapshot',lambda:{'items':[]})
    result,code=api.view()
    assert code==200 and result['ok'] and result['run_id'] is None
    assert result['answer']=='' and result['warnings']==[]


@pytest.mark.parametrize('backend',['claude','codex','opencode','acp'])
def test_workspace_answers_are_persisted_through_every_adapter(hub,monkeypatch,backend):
    import shutil,time
    import executor
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/assistant');monkeypatch.setattr(api.ctx,'HUB',hub.root)
    monkeypatch.setattr(api.sources,'snapshot',lambda:{'items':[]})
    if backend=='opencode':
        node=shutil.which('node')
        if not node:pytest.skip('Node.js required for opencode fixture')
        command=[node,str(REPO/'tests/fake_opencode.mjs')]
    else:command=[sys.executable,str(REPO/'tests'/('fake_'+backend+'.py'))]
    cfg={'agents':{'programmatic':{'enabled':True,'backend':backend,
        'live':{'linger_minutes':0} if backend=='acp' else False,'backends':{backend:{'command':command}}}}}
    (hub.lab/'config.yaml').write_text(yaml.safe_dump(cfg),encoding='utf-8')
    monkeypatch.setenv('FAKE_MODE','complete')
    result,code=api.send({'text':'Explain the current work.'});assert code==200,result
    lab=executor.Lab(hub.root);until=time.monotonic()+60
    while time.monotonic()<until:
        executor.tick(lab)
        run=executor.find_run(lab,result['run_id'])[3]
        if run['status'] in ('completed','failed','timeout','killed'):break
        time.sleep(.1)
    assert run['status']=='completed',run
    K.sync_answer(lab,run)
    record=K.dispatch(hub.root,None,'get',id=run['knowledge_question']['id'])
    assert record['status']=='answered' and '## Response' in record['text']
    assert record['run']==run['run_id'] and record['responses']
    state,_=api.view();assert state['answer'] and state['question']['status']=='answered'
