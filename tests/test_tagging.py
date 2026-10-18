"""Labels round-trip through existing study and workflow files without changing research state."""
import json
import pytest
from conftest import kernel, load, REPO


def test_tags_preserve_question_metadata_and_research_state(hub):
    tags=load('tagging');k=kernel()
    k.studies.new(hub.root,'study','Study')
    path=hub.root/'studies/study/IDEA.md';path.parent.mkdir(parents=True,exist_ok=True)
    body='\n# Question\n\nKeep this text.\n'
    path.write_text('---\ntitle: Original\nproject_mode: attached\n---\n'+body,encoding='utf-8')
    before=(hub.root/'lab/journal.jsonl').read_bytes()
    assert tags.set_study_tags(hub.root,'study',[' Replication ','new topic','replication'])==['replication','new-topic']
    assert tags.study_tags(hub.root,'study')==['replication','new-topic']
    assert path.read_text(encoding='utf-8').endswith(body)
    assert 'project_mode: attached' in path.read_text(encoding='utf-8')
    assert (hub.root/'lab/journal.jsonl').read_bytes()==before
    assert k.studies.rows(hub.root)[0]['tags']==['replication','new-topic']
    with pytest.raises(ValueError):tags.set_study_tags(hub.root,'../other',['x'])
    assert tags.set_study_tags(hub.root,'study',[])==[]


@pytest.mark.parametrize('value',[42,{},['valid',3],['x'*65]])
def test_invalid_tags_fail_without_writing(value):
    with pytest.raises(ValueError):load('tagging').normalize(value)


def test_task_and_procedure_tags_survive_definition_roundtrip(hub):
    k=kernel();d=k.define.read(hub.root)
    d['steps']['seed']['tags']=['Replication']
    d['workflows'][0]['tags']=['Methods']
    d['workflows'][0]['nodes']={'seed':{'tags':['Important topic']}}
    k.define.write(hub.root,d)
    after=k.define.read(hub.root)
    assert after['steps']['seed']['tags']==['replication']
    assert after['workflows'][0]['tags']==['methods']
    assert after['workflows'][0]['nodes']['seed']['tags']==['important-topic']
    assert k.model.view(hub.root)['workflows'][0]['tags']==['methods']
    assert {'replication','methods','important-topic'}<=set(load('tagging').catalog(hub.root))


def test_starter_and_cli_accept_user_labels(hub,monkeypatch,capsys):
    starter=load('research_start');tags=load('tagging')
    result=starter.create(hub.root,title='Tagged study',question='Replication?',tags='Replication, Own label')
    assert tags.study_tags(hub.root,result['study'])==['replication','own-label']
    cli=load('newts_cli')
    assert cli.main(['--hub',str(hub.root),'tags',result['study'],'--set','changed'])==0
    assert json.loads(capsys.readouterr().out)==['changed']


def test_invalid_starter_tags_and_bad_metadata_return_errors(hub,monkeypatch):
    monkeypatch.syspath_prepend(str(REPO/'dashboard'))
    adapter=load('dashboard/starter');monkeypatch.setattr(adapter.ctx,'HUB',hub.root)
    result,code=adapter.create({'confirm':True,'title':'Test','question':'Why?','tags':[3]})
    assert code==400 and 'text labels' in result['error']
    kernel().studies.new(hub.root,'study','Study')
    path=hub.root/'studies/study/IDEA.md';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('---\ntags: [broken\n---\nQuestion',encoding='utf-8')
    before=path.read_bytes()
    result,code=adapter.tags({'study':'study','tags':['valid']})
    assert code==400 and 'frontmatter' in result['error']
    assert path.read_bytes()==before


def test_tags_reach_briefs_and_procedure_metadata(hub):
    k=kernel();tags=load('tagging');k.studies.new(hub.root,'study','Study')
    tags.set_study_tags(hub.root,'study',['Replication'])
    procedure=hub.root/'.claude/skills/tagged/SKILL.md';procedure.parent.mkdir(parents=True,exist_ok=True)
    procedure.write_text('---\nname: tagged\nnewts:\n  tags: [Reading]\n---\nRead carefully.',encoding='utf-8')
    text,_=k.brief.brief(hub.root,'tagged','study')
    assert 'Study: replication' in text and 'Procedure: reading' in text
    assert 'reading' in tags.catalog(hub.root)
    assert k.model.view(hub.root)['procedures']['tagged']['tags']==['reading']
