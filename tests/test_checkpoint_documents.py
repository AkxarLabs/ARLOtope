"""Checkpoint exhibits use the full document reader without changing approval state."""
import json
import shutil
import subprocess

import pytest

from conftest import REPO


NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(not NODE, reason='node is needed for the UI actions')

# Real htm produces inert VNodes; fake hooks supply the already-loaded checkpoint.
# Tests click actual rendered event handlers, with no browser or real Lab state.
_SETUP = r"""
const fs=require('fs'), root=process.argv[1], config=JSON.parse(process.argv[2]);
global.window=global;
const htm=require(root+'/dashboard/static/vendor/preact/htm.umd.js');
const html=htm.bind((type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}));
const filenames=['proposal.md','lit-review.md','decisions.md'];
const evidence=config.evidence||filenames.map(name=>({name,path:'studies/study-one/'+name,exists:true,dir:false}));
const sections=config.sections||filenames.map(name=>({title:'studies/study-one/'+name,
  path:'/tmp/My Lab/studies/study-one/'+name,text:'# Clipped preview only\n\n… (clipped)'}));
const study={id:'study-one',title:'One study',checkpoints:{},...(config.study||{})};
const lab={lab_info:{path:config.labPath||'/tmp/My Lab'},items:[study]};
const view={checkpoint:{id:'approve-proposal',title:'Approve proposal',before:'setup',approver:'me'},
  record:null,evidence,waiting:false};
const opened=[],requests=[];
window.NL={html,cls:(...xs)=>xs.filter(Boolean).join(' '),
  useState:x=>[typeof x==='function'?x():x,()=>{}],useEffect:()=>{},
  useDraft:(_key,initial)=>[typeof initial==='function'?initial():initial,()=>{}],
  useLab:()=>lab,item:(s,id)=>s.items.find(x=>x.id===id),
  useGet:()=>({data:view,reload:()=>{}}),qs:x=>new URLSearchParams(x).toString(),
  STATE_LABEL:{setup:'Project setup'},workflowOf:()=>({title:'Research'}),
  DocReader:function DocReader(){},Markdown:function Markdown(){},
  Section:function Section(){},Sheet:function Sheet(){},
  open:(component,props)=>{opened.push({component,props});},
  api:async(path,body)=>{requests.push({path,body});
    if(path!=='/api/read')throw Error('Unexpected API mutation: '+path);
    return {ok:true,sections};},
  act:()=>{throw Error('A reader must not approve or launch work');}};
const useState=NL.useState,cls=NL.cls;
const components=fs.readFileSync(root+'/dashboard/static/ui/components.js','utf8');
eval(components.slice(components.indexOf('NL.isMarkdownDoc ='),components.indexOf('/* ── editor deep links')));
eval(fs.readFileSync(root+'/dashboard/static/ui/studies.js','utf8'));
eval(fs.readFileSync(root+'/dashboard/static/ui/checkpoint.js','utf8'));
function all(value,predicate){
  if(Array.isArray(value))return value.flatMap(x=>all(x,predicate));
  if(!value||typeof value!=='object')return [];
  if(value.type===NL.DocumentText)return all(NL.DocumentText(value.props),predicate);
  return [...(predicate(value)?[value]:[]),...all(value.children||[],predicate)];
}
function text(value){
  if(Array.isArray(value))return value.map(text).join('');
  return value&&typeof value==='object'?text(value.children||[]):String(value??'');
}
function checkpoint(){return NL.CheckpointSheet({study:'study-one',id:'approve-proposal',onClose:()=>{}});}
function exhibits(tree){return all(tree,x=>x.type==='button'&&String(x.props.class||'').split(' ').includes('exhibit'));}
function readers(tree){return all(tree,x=>x.type===NL.DocReader).map(x=>x.props);}
function last(){const x=opened[opened.length-1];if(!x||x.component!==NL.SectionsSheet)throw Error('Expected evidence sheet');return x.props;}
"""


def _node(body, config=None):
    script = _SETUP + '\n(async()=>{' + body + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
    result = subprocess.run([NODE, '-e', script, str(REPO), json.dumps(config or {})],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_an_exhibit_opens_only_its_full_document_not_the_clipped_bundle():
    got = _node("""
      const buttons=exhibits(checkpoint());
      await buttons[0].props.onClick();
      const sheet=last(),tree=NL.SectionsSheet(sheet);
      console.log(JSON.stringify({sections:sheet.data.sections,readers:readers(tree),
        plain:all(tree,x=>x.type==='pre').map(text),requests}));
    """)
    assert len(got['sections']) == 1
    assert got['readers'] == [{'scope': 'study', 'slug': 'study-one', 'rel': 'proposal.md', 'bare': True}]
    assert not got['plain']
    assert not any('clipped' in section.get('text', '') for section in got['sections'])
    assert not got['requests'], 'Recognized exhibits should use DocReader, not fetch a clipped bundle first'


def test_read_all_fetches_three_full_documents_in_exhibit_order():
    got = _node("""
      const button=all(checkpoint(),x=>x.type==='button'&&text(x)==='read them all')[0];
      await button.props.onClick();
      const sheet=last(),tree=NL.SectionsSheet(sheet);
      console.log(JSON.stringify({readers:readers(tree),plain:all(tree,x=>x.type==='pre').map(text),requests}));
    """)
    assert [x['rel'] for x in got['readers']] == ['proposal.md', 'lit-review.md', 'decisions.md']
    assert all(x['scope'] == 'study' and x['slug'] == 'study-one' and x['bare'] for x in got['readers'])
    assert not got['plain'], 'Clipped previews must not be substituted for full readers'
    assert got['requests'] == [{'path': '/api/read', 'body': {
        'what': 'checkpoint', 'idea': 'study-one', 'checkpoint': 'approve-proposal'}}]


@pytest.mark.parametrize(('path', 'study', 'scope', 'rel'), [
    ('studies/study-one/proposal.md', {}, 'study', 'proposal.md'),
    ('/tmp/My Lab/studies/study-one/notes/report.MARKDOWN', {}, 'study', 'notes/report.MARKDOWN'),
    ('/tmp/Research Code/PLAN.md', {'project_dir': '/tmp/Research Code'}, 'project', 'PLAN.md'),
    ('arlotope+ssh://box/home/user/project/notes/report.md',
     {'machine': 'box', 'remote_project': {'machine': 'box', 'path': '/home/user/project'}},
     'project', 'notes/report.md'),
])
def test_exhibit_maps_only_the_current_study_and_project_roots(path, study, scope, rel):
    got = _node("""
      await exhibits(checkpoint())[0].props.onClick();
      console.log(JSON.stringify(readers(NL.SectionsSheet(last()))));
    """, {'evidence': [{'name': 'Evidence', 'path': path, 'exists': True, 'dir': False}], 'study': study})
    assert got == [{'scope': scope, 'slug': 'study-one', 'rel': rel, 'bare': True}]


@pytest.mark.parametrize(('path', 'study', 'lab_path', 'scope', 'rel'), [
    ('C:\\ARLOtope Lab\\studies\\study-one\\proposal.md', {}, 'C:\\ARLOtope Lab', 'study', 'proposal.md'),
    ('D:\\Research Code\\notes\\report.md', {'project_dir': 'D:\\Research Code'}, 'C:\\ARLOtope Lab',
     'project', 'notes/report.md'),
])
def test_windows_document_paths_keep_the_same_exact_root_mapping(path, study, lab_path, scope, rel):
    got = _node("""
      await exhibits(checkpoint())[0].props.onClick();
      console.log(JSON.stringify(readers(NL.SectionsSheet(last()))));
    """, {'evidence': [{'name': 'Evidence', 'path': path, 'exists': True, 'dir': False}],
          'study': study, 'labPath': lab_path})
    assert got == [{'scope': scope, 'slug': 'study-one', 'rel': rel, 'bare': True}]


@pytest.mark.parametrize(('path', 'study'), [
    ('studies/study-one-other/proposal.md', {}),
    ('studies/study-one/../other/proposal.md', {}),
    ('/tmp/My Lab-copy/studies/study-one/proposal.md', {}),
    ('/tmp/My Lab/studies/study-one/../../other/proposal.md', {}),
    ('/etc/proposal.md', {}),
    ('/tmp/Research Code-other/PLAN.md', {'project_dir': '/tmp/Research Code'}),
    ('arlotope+ssh://other/home/user/project/PLAN.md',
     {'machine': 'box', 'remote_project': {'machine': 'box', 'path': '/home/user/project'}}),
    ('arlotope+ssh://box/home/user/project/../project/PLAN.md',
     {'machine': 'box', 'remote_project': {'machine': 'box', 'path': '/home/user/project'}}),
])
def test_unrelated_paths_and_traversal_do_not_become_full_reader_requests(path, study):
    got = _node("""
      await exhibits(checkpoint())[0].props.onClick();
      console.log(JSON.stringify({readers:readers(NL.SectionsSheet(last())),requests}));
    """, {'evidence': [{'name': 'Evidence', 'path': path, 'exists': True, 'dir': False}],
          'sections': [{'title': path, 'path': path, 'text': 'Existing authorized preview'}], 'study': study})
    assert got['readers'] == []
    assert got['requests'][0]['path'] == '/api/read', 'Unknown paths retain the bounded evidence-bundle fallback'


@pytest.mark.parametrize('section', [
    {'title': 'Report', 'path': '/other/REPORT.MD', 'text': '# Report\n\n**Evidence**'},
    {'title': 'notes/report.markdown', 'text': '# Report\n\n**Evidence**'},
    {'title': 'Report without a suffix', 'format': 'markdown', 'text': '# Report\n\n**Evidence**'},
])
def test_markdown_bundle_fallback_uses_the_shared_renderer(section):
    got = _node("""
      const tree=NL.SectionsSheet({title:'Evidence',data:{ok:true,sections:config.sections}});
      console.log(JSON.stringify({markdown:all(tree,x=>x.type===NL.Markdown).map(x=>x.props),
        plain:all(tree,x=>x.type==='pre').map(text)}));
    """, {'sections': [section]})
    assert got['markdown'][0]['text'] == section['text']
    assert not got['plain']


@pytest.mark.parametrize(('name', 'content'), [
    ('metrics.json', '{"note": "# Keep this literal", "loss": 0.25}'),
    ('instructions.txt', '# This is plain text, not a document heading'),
])
def test_non_markdown_bundle_fallback_preserves_literal_source(name, content):
    got = _node("""
      const tree=NL.SectionsSheet({title:'Evidence',data:{ok:true,sections:config.sections}});
      console.log(JSON.stringify({markdown:all(tree,x=>x.type===NL.Markdown).length,
        plain:all(tree,x=>x.type==='pre').map(text)}));
    """, {'sections': [{'title': name, 'path': '/other/' + name, 'text': content}]})
    assert got['plain'] == [content]
    assert got['markdown'] == 0
