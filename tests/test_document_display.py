"""Markdown readers default to rendered content, with a reversible source view."""
import json
import shutil
import subprocess

import pytest
from conftest import REPO

NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(not NODE, reason='node is needed for document readers')

_SETUP = r"""
const fs=require('fs'),root=process.argv[1];
global.window=global;
const htm=require(root+'/dashboard/static/vendor/preact/htm.umd.js');
const html=htm.bind((type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}));
const cls=(...xs)=>xs.filter(Boolean).join(' ');
let state;
const useState=initial=>[state===undefined?initial:state,next=>{state=next}];
const NL=window.NL={html,cls,Markdown:function Markdown(){}};
const readerSource=fs.readFileSync(root+'/dashboard/static/ui/components.js','utf8');
eval(readerSource.slice(readerSource.indexOf('NL.isMarkdownDoc ='),readerSource.indexOf('/* ── editor deep links')));
function all(value,predicate){
  if(Array.isArray(value))return value.flatMap(x=>all(x,predicate));
  if(!value||typeof value!=='object')return [];
  return [...(predicate(value)?[value]:[]),...all(value.children||[],predicate)];
}
function text(value){
  if(Array.isArray(value))return value.map(text).join('');
  return value&&typeof value==='object'?text(value.children||[]):String(value??'');
}
"""


def _node(body):
    result = subprocess.run([NODE, '-e', _SETUP + body, str(REPO)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('metadata', [
    {'name': 'proposal.md'}, {'path': 'notes/REVIEW.MARKDOWN'},
    {'format': 'markdown'}, {'format': 'text/markdown'}, {'kind': 'md'},
    {'kind': 'text', 'name': '/tmp/Results.MD'},
])
def test_markdown_opens_rendered_and_preserves_scoped_links(metadata):
    props = {**metadata, 'text': '# Report\n\n**Evidence**', 'sel': {'scope': 'study', 'slug': 'one', 'rel': 'report.md'}}
    got = _node('const props=' + json.dumps(props) + r""";
      const tree=NL.DocumentText(props);
      console.log(JSON.stringify({markdown:all(tree,x=>x.type===NL.Markdown).map(x=>x.props),
        pre:all(tree,x=>x.type==='pre').length,
        controls:all(tree,x=>x.type==='button').map(x=>[text(x),x.props['aria-pressed']])}));
    """)
    assert got['markdown'][0]['text'] == props['text']
    assert got['markdown'][0]['sel'] == props['sel']
    assert got['pre'] == 0
    assert got['controls'] == [['Rendered', True], ['Markdown source', False]]


def test_source_toggle_is_reversible_and_does_not_write_or_change_document():
    got = _node(r"""
      const props={name:'proposal.md',text:'# Proposal\n\n<script>alert(1)</script>'};
      let tree=NL.DocumentText(props);
      all(tree,x=>x.type==='button'&&text(x)==='Markdown source')[0].props.onClick();
      const source=NL.DocumentText(props),literal=all(source,x=>x.type==='pre').map(text);
      all(source,x=>x.type==='button'&&text(x)==='Rendered')[0].props.onClick();
      const rendered=NL.DocumentText(props);
      console.log(JSON.stringify({literal,sourceMd:all(source,x=>x.type===NL.Markdown).length,
        renderedMd:all(rendered,x=>x.type===NL.Markdown).map(x=>x.props.text),unchanged:props.text}));
    """)
    assert got['literal'] == [got['unchanged']]
    assert got['sourceMd'] == 0
    assert got['renderedMd'] == [got['unchanged']]


def test_a_different_document_opens_rendered_after_viewing_source():
    got = _node(r"""
      let tree=NL.DocumentText({name:'one.md',text:'# One'});
      all(tree,x=>x.type==='button'&&text(x)==='Markdown source')[0].props.onClick();
      tree=NL.DocumentText({name:'two.md',text:'# Two'});
      console.log(JSON.stringify(all(tree,x=>x.type===NL.Markdown).map(x=>x.props.text)));
    """)
    assert got == ['# Two']


@pytest.mark.parametrize('name', ['technical.log', 'config.yaml', 'metrics.json', 'instructions.txt', 'script.py'])
def test_logs_config_and_code_remain_literal_even_when_text_looks_like_markdown(name):
    got = _node('const tree=NL.DocumentText('+json.dumps({'name': name, 'text': '# Literal\n\n**Still literal**'})+');'+r"""
      console.log(JSON.stringify({pre:all(tree,x=>x.type==='pre').map(text),
        md:all(tree,x=>x.type===NL.Markdown).length,buttons:all(tree,x=>x.type==='button').length}));
    """)
    assert got == {'pre': ['# Literal\n\n**Still literal**'], 'md': 0, 'buttons': 0}
