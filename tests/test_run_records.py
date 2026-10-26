"""Conversation archives outlive compact manifests and capped provider streams."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from executor import records, supervise
from test_live import conv, ask, StubState


def collect(folder):
    rows=[];offset=0
    while True:
        result=records.page(folder,offset)
        rows.extend(result['rows'])
        if result['next'] is None:return rows
        assert result['offset']>offset
        offset=result['next']


def test_full_responses_survive_manifest_preview_and_attempts(tmp_path):
    state=StubState({'run_id':'sample','attempt':1})
    rec=supervise._Recorder(SimpleNamespace(source_of=lambda w:'hub'),state,tmp_path,None,None,rd=tmp_path)
    text='Evidence and explanation. '*600
    rec.on_event({'event':'result','last_message':text})
    state.m['attempt']=2
    rec.on_event({'event':'result','last_message':'Quota reached','is_error':True})
    rows=collect(tmp_path)
    assert rows[0]['text']==text and len(state.m['last_message'])<=2000
    assert [r['attempt'] for r in rows]==[1,2] and rows[1]['error']
    assert records.page(tmp_path/'missing')['available'] is False


def test_questions_answers_permissions_and_messages_survive_recent_window(tmp_path):
    c,s,st,_=conv(tmp_path)
    st.m['attempt']=1
    for i in range(26):
        ask(c,str(i))
        c._deliver({'kind':'answer','request_id':str(i),'answers':{'Which dataset?':'A'}})
    ask(c,'permission','permission',{'command':'run smoke'})
    c._deliver({'kind':'permission','request_id':'permission','allow':False})
    c._deliver({'kind':'message','text':'Read this new evidence.'})
    rows=collect(tmp_path)
    assert len(st.m['qa'])==20 and len(rows)==55
    assert rows[0]['request_id']=='0' and rows[1]['answers']=={'Which dataset?':'A'}
    assert rows[-2]['kind']=='permission' and rows[-2]['allow'] is False
    assert rows[-1]['text']=='Read this new evidence.'


def test_partial_mirrors_clipping_and_concurrent_writers(tmp_path):
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda n:records.record(tmp_path,{},'message',text=str(n)),range(45)))
    assert len({r['id'] for r in collect(tmp_path)})==45
    records.record(tmp_path,{},'response',text='é'*500_000)
    rows=collect(tmp_path)
    assert rows[-1]['clipped'] and len(rows[-1]['text'])==records.MAX_TEXT
    offset=(tmp_path/records.FILE).stat().st_size
    with (tmp_path/records.FILE).open('ab') as out:out.write(b'{"kind":"response","text":"partial"')
    result=records.page(tmp_path,offset)
    assert result['rows']==[] and result['offset']==offset and result['next'] is None and result['incomplete']
    with (tmp_path/records.FILE).open('ab') as out:out.write(b'}\n')
    assert records.page(tmp_path,offset)['rows'][0]['text']=='partial'



def test_capture_failure_is_visible_without_stopping_work(tmp_path,monkeypatch):
    state={}
    monkeypatch.setattr(records.os,'write',lambda *a: (_ for _ in ()).throw(OSError('disk full')))
    records.record(tmp_path,state,'response',text='Never pretend this was saved.')
    assert state['record_error']=='disk full' and not state.get('record_count')

def test_remote_log_wrapper_writes_existing_project_knowledge(tmp_path,monkeypatch,capsys):
    import knowledge,project_control
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('ARLOTOPE_RUN_ID','remote-run')
    monkeypatch.setenv('ARLOTOPE_RUN_SUBJECT','study')
    monkeypatch.setenv('ARLOTOPE_ATTEMPT','3')
    assert project_control.control(['log','Remote finding','--ref','runs/evidence.json'])==0
    result=knowledge.listing(knowledge.project_folder(tmp_path))['rows'][0]
    assert result['run']=='remote-run' and result['attempt']==3 and result['studies']==['study']
    assert result['refs']==['runs/evidence.json']
    assert not (tmp_path/'lab').exists()


def test_attempt_input_is_retained_before_running(tmp_path,monkeypatch):
    state=StubState({'run_id':'run','attempt':1,'attempts':[], 'resume':{'mode':'reply'}})
    command=SimpleNamespace(notes=None,fires_hooks=True,argv=['fake'],stdin_text=None)
    attempt=SimpleNamespace(prog={},command=command,prompt='Read the new evidence, then continue.',workdir=tmp_path,env={},cli=['fake'])
    monkeypatch.setattr(supervise,'run_process',lambda *a,**kw:supervise.ProcResult(rc=0,started=True))
    monkeypatch.setattr(supervise,'_finish',lambda *a:0)
    assert supervise._run_attempt(SimpleNamespace(source_of=lambda w:'hub'),SimpleNamespace(name='claude'),state,tmp_path,tmp_path,tmp_path,False,attempt)==0
    row=collect(tmp_path)[0]
    assert row['kind']=='input' and row['attempt']==2 and row['source']=='reply'
    assert row['text']==attempt.prompt and row['delivery']=='attempt-start'


def test_run_record_reader_uses_recorded_run_location(hub,monkeypatch):
    from conftest import load,REPO
    from test_run_evidence import configured
    from executor import enqueue,RunSpec,manifest
    lab=configured(hub);run=enqueue(lab,RunSpec('',prompt='Inspect'))
    rd=manifest.run_dir(lab.agents_dir(lab.hub),run['run_id'])
    records.record(rd,run,'response',text='Only this run.')
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    api=load('dashboard/runops');monkeypatch.setattr(api.ctx,'HUB',hub.root)
    result,code=api.run_records({'run_id':run['run_id']})
    assert code==200 and result['rows'][0]['text']=='Only this run.'
    assert api.run_records({'run_id':'missing'})[1]==404
