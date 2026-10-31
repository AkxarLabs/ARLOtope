"""Plain Markdown records shared by the dashboard, agents and the SSH worker."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid
import yaml

import labfiles

KINDS = ('document','source','note','answer','output','log')
MAX_TEXT = 500_000
MAX_FILE = 4*MAX_TEXT+65536


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def project_folder(root):
    root=Path(root).resolve()
    config=labfiles.read_json(root/'.arlotope/project.json', {})
    if not isinstance(config,dict):raise ValueError('The project configuration must be a mapping.')
    rel=config.get('knowledge_dir','.arlotope/knowledge')
    if not isinstance(rel,str) or Path(rel).is_absolute():
        raise ValueError('Knowledge directory must be relative to the project.')
    folder=(root/rel).resolve()
    if not folder.is_relative_to(root) or folder==root:
        raise ValueError('Knowledge directory must be inside the project.')
    return folder


def location(hub, study=None):
    hub=Path(hub).resolve()
    if not study:
        return {'scope':'lab','slug':None,'base':hub/'lab','folder':hub/'lab/records'}
    from kernel import studies
    s=studies.study(hub,study)
    if not s:
        raise ValueError('Choose an existing study.')
    import remote_projects
    remote=remote_projects.location(s.get('project'))
    if remote:
        return {'scope':'project','slug':study,'remote':remote}
    from kernel.checkpoints import project_dir
    root=project_dir(hub,study)
    if root and Path(root).is_dir():
        root=Path(root).resolve()
        return {'scope':'project','slug':study,'base':root,'folder':project_folder(root)}
    root=hub/'studies'/study
    return {'scope':'study','slug':study,'base':root,'folder':root/'knowledge'}


def _file(folder, identifier):
    if not isinstance(identifier,str) or not identifier or len(identifier)>500 or Path(identifier).is_absolute() or '..' in Path(identifier).parts or '\\' in identifier:
        raise ValueError('Choose a record ID.')
    path=Path(folder)/(identifier if identifier.endswith('.md') else identifier+'.md')
    if not labfiles.inside(folder,path):
        raise ValueError('The record is outside its knowledge folder.')
    if not path.exists() and Path(folder).is_dir():
        matches=[]
        for candidate in Path(folder).rglob('*.md'):
            if not labfiles.inside(folder,candidate):continue
            try:
                if read_file(candidate)[0].get('id')==identifier:matches.append(candidate)
            except (OSError,ValueError,yaml.YAMLError):continue
        if len(matches)>1:raise ValueError('Duplicate record IDs; open the record by its relative file path.')
        if matches:path=matches[0]
    return path


def read_file(path):
    path=Path(path)
    if path.stat().st_size>MAX_FILE:
        raise ValueError('This record is too large to preview.')
    text=path.read_text(encoding='utf-8-sig')
    meta={}
    if text.startswith('---\n'):
        parts=text.split('---\n',2)
        if len(parts)==3:
            try:meta=yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError as error:raise ValueError('Invalid record metadata: '+str(error)) from error
            if not isinstance(meta,dict):
                raise ValueError('Record metadata must be a mapping.')
            text=parts[2].lstrip('\n')
    return meta,text


def _write(path, meta, text):
    content='---\n'+yaml.safe_dump(meta,sort_keys=False,allow_unicode=True)+'---\n\n'+text.rstrip()+'\n'
    if len(content.encode('utf-8'))>MAX_FILE:raise ValueError('This record is too large; start a separate record.')
    labfiles.write_atomic(path,content)


def create(folder, *, kind='note', text='', title='', studies=None, tags=None, about=None,
           acknowledge=False, author='human', source=None, attachment=None, **extra):
    if kind not in KINDS or not isinstance(text,str) or len(text)>MAX_TEXT or not text.strip():
        raise ValueError('Choose a record kind and write some text (up to 500,000 characters).')
    if not isinstance(title,str) or len(title)>200:
        raise ValueError('Use a short title.')
    if type(acknowledge) is not bool or studies is not None and (not isinstance(studies,list) or any(not isinstance(s,str) for s in studies)):
        raise ValueError('Choose study IDs and a valid acknowledgement option.')
    if about is not None and (not isinstance(about,dict) or len(json.dumps(about))>2000):
        raise ValueError('Choose a document or run to reference.')
    from tagging import normalize
    identifier=kind+'-'+uuid.uuid4().hex[:16]
    meta={'id':identifier,'kind':kind,'title':title.strip() or text.strip().splitlines()[0][:100],
          'created':now(),'author':author,'studies':studies or [],'tags':normalize(tags)}
    if about:meta['about']=about
    if acknowledge:meta['acknowledge']=True
    if source:
        if not isinstance(source,dict):raise ValueError('Source metadata must be a mapping.')
        meta['source']=source
    if any(k in extra for k in ('id','kind','created','author','studies','tags')):
        raise ValueError('Record identity and authorship cannot be overridden.')
    meta.update(extra)
    if attachment:
        file=Path(attachment)
        if not file.is_file() or file.stat().st_size>50*1024*1024:
            raise ValueError('Use a local attachment up to 50 MB.')
        name=hashlib.sha256(file.read_bytes()).hexdigest()[:16]+'-'+re.sub(r'[^A-Za-z0-9_.-]','-',file.name)
        target=Path(folder)/'attachments'/name;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copyfile(file,target)
        meta['attachment']='attachments/'+name
        text+='\n\n[Original attachment](attachments/'+name+')'
    _write(_file(folder,identifier),meta,text)
    return meta


def listing(folder, *, query='', kind='', tag='', offset=0, limit=100, **_):
    folder=Path(folder);rows=[]
    for path in sorted(folder.rglob('*.md')) if folder.is_dir() else []:
        meta={}
        if not labfiles.inside(folder,path):continue
        try:
            meta,text=read_file(path)
            entry={**meta,'id':meta.get('id') or path.relative_to(folder).with_suffix('').as_posix(),'kind':meta.get('kind','document'),
                   'title':meta.get('title') or path.stem,'file':path.relative_to(folder).as_posix(),
                   'mtime':path.stat().st_mtime,'text':text}
        except (OSError,ValueError,yaml.YAMLError) as error:
            entry={'id':path.relative_to(folder).with_suffix('').as_posix(),'title':path.stem,'kind':'document','file':path.relative_to(folder).as_posix(),
                   'mtime':path.stat().st_mtime,'text':'','error':str(error)}
        if kind and entry['kind']!=kind or tag and tag not in entry.get('tags',[]):continue
        if query and query.casefold() not in (json.dumps(meta,default=str)+entry['text']).casefold():continue
        rows.append(entry)
    rows.sort(key=lambda r:str(r.get('created') or datetime.fromtimestamp(r['mtime'],timezone.utc).isoformat()),reverse=True)
    offset=max(0,int(offset));limit=len(rows)+1 if limit is None else max(1,min(int(limit),200))
    return {'rows':[{**r,'text':r['text'][:300]} for r in rows[offset:offset+limit]],'total':len(rows),'next':offset+limit if offset+limit<len(rows) else None}


def get(folder, identifier):
    path=_file(folder,identifier)
    meta,text=read_file(path)
    return {**meta,'id':meta.get('id') or path.relative_to(folder).with_suffix('').as_posix(),
            'kind':meta.get('kind','document'),'title':meta.get('title') or path.stem,
            'text':text,'file':path.relative_to(folder).as_posix()}


def attachment(folder, identifier):
    record=get(folder,identifier)
    rel=record.get('attachment')
    if not isinstance(rel,str):raise ValueError('This record has no retained attachment.')
    path=(Path(folder)/rel).resolve()
    if not path.is_relative_to(Path(folder).resolve()) or not path.is_file() or path.stat().st_size>50*1024*1024:
        raise ValueError('Attachment unavailable or outside the knowledge folder.')
    return path


def update(folder, identifier, *, acknowledgement=None, response=None, status=None, binding=None):
    from executor.procs import excl_lock
    path=_file(folder,identifier)
    with excl_lock(path.with_suffix('.lock')):
        meta,text=read_file(path)
        before=(json.dumps(meta,sort_keys=True,default=str),text)
        if acknowledgement:
            if not meta.get('acknowledge'):raise ValueError('Acknowledgement was not requested.')
            if not any(a.get('run')==acknowledgement.get('run') for a in meta.get('acknowledgements',[])):
                meta.setdefault('acknowledgements',[]).append({'at':now(),**acknowledgement})
        if response:
            if response['id'] not in meta.get('responses',[]):
                meta.setdefault('responses',[]).append(response['id'])
                text+='\n\n## Response · '+response['at']+'\n\n'+response['text']
                meta['status']=response.get('status','answered')
        if status:meta['status']=status
        if binding:meta.update(binding)
        if before!=(json.dumps(meta,sort_keys=True,default=str),text):_write(path,meta,text)
    return get(folder,identifier)


def dispatch(hub, study, action='list', **data):
    loc=location(hub,study)
    # Notes created before project attachment remain part of this study's history.
    study_records=Path(hub)/'studies'/str(study)/'knowledge'
    if study and loc['scope']=='project' and study_records.is_dir():
        if action in ('get','update'):
            old=_file(study_records,data['id'])
            if old.is_file():
                result=get(study_records,data['id']) if action=='get' else update(study_records,data.pop('id'),**data)
                return {**result,'scope':'study','slug':study,'rel':old.relative_to(Path(hub)/'studies'/study).as_posix()}
        if action=='list':
            query={**data,'offset':0,'limit':None}
            current=_dispatch(hub,study,action,**query)
            old=listing(study_records,**query)
            for row in old['rows']:row.update(scope='study',slug=study,rel='knowledge/'+row['file'])
            rows=current['rows']+old['rows']
            rows.sort(key=lambda r:str(r.get('created') or datetime.fromtimestamp(r['mtime'],timezone.utc).isoformat()),reverse=True)
            offset=max(0,int(data.get('offset',0)));limit=max(1,min(int(data.get('limit') or 100),200))
            return {'rows':rows[offset:offset+limit],'total':len(rows),'next':offset+limit if offset+limit<len(rows) else None}
    return _dispatch(hub,study,action,**data)


def _dispatch(hub, study, action='list', **data):
    loc=location(hub,study)
    if loc.get('remote'):
        if data.get('attachment'):raise ValueError('Add attachments on the project machine with --project; local paths are not remote files.')
        import remote_projects
        remote_data = data if action in ('list','get') else {'id':data.get('id'),'record':{k:v for k,v in data.items() if k!='id'}}
        result=remote_projects.call(hub,study,'knowledge',action=action,**remote_data)
        if action=='list':
            for row in result['rows']:row.update(scope='project',slug=study)
        return result
    folder=loc['folder']
    if action=='list':
        result=listing(folder,**data)
        for row in result['rows']:
            row.update(scope=loc['scope'],slug=study,rel=(folder/row['file']).relative_to(loc['base']).as_posix())
        return result
    if action=='get':
        result=get(folder,data['id'])
        return {**result,'scope':loc['scope'],'slug':study,'rel':(folder/result['file']).relative_to(loc['base']).as_posix()}
    if action=='add':return create(folder,studies=[study] if study else [],**data)
    if action=='update':return update(folder,data.pop('id'),**data)
    raise ValueError('Unknown knowledge action.')


def save_answer(lab, question, result):
    """Keep a durable delivery receipt before writing to a possibly offline project."""
    pending=lab.hub/'lab/.bus/knowledge-pending'/ (result['id']+'.json')
    labfiles.write_json(pending,{'question':question,'result':result})
    _deliver_answer(lab,pending,question,result)


def _deliver_answer(lab,path,question,result):
    dispatch(lab.hub,question.get('study'),'update',id=question['id'],response={
        'id':result['id'],'at':result['at'],'text':result['text'],
        'status':'failed' if result.get('error') else 'answered'})
    path.unlink(missing_ok=True)


def retry_answers(lab):
    errors=[]
    for path in (lab.hub/'lab/.bus/knowledge-pending').glob('*.json'):
        item=labfiles.read_json(path)
        try:
            if item:_deliver_answer(lab,path,item['question'],item['result'])
        except (OSError,ValueError) as error:errors.append(str(error))
    return errors


def sync_answer(lab, run=None):
    """Materialize a workspace reply once; transcripts remain the execution evidence."""
    record=labfiles.read_json(lab.hub/'lab/.bus/assistant.json',{})
    if run is None:
        if not record.get('run_id'):return
        from executor.manifest import find_run
        try:hit=find_run(lab,record['run_id'])
        except ValueError:return
        run=hit[3] if hit else None
    if not run:return
    question=run.get('knowledge_question') or (record.get('question') if run.get('run_id')==record.get('run_id') else None)
    if not question:return
    result=run.get('last_result')
    if result and result['id']!=question.get('baseline') and result['at']>=question['created']:
        from executor.manifest import find_run,run_dir
        hit=find_run(lab,run['run_id'])
        if not hit:return
        saved=labfiles.read_json(run_dir(hit[2].parent,run['run_id'])/result['file'])
        if saved and saved.get('text'):
            save_answer(lab,saved.get('question') or question,saved)
    elif run.get('status') in ('completed','failed','killed','timeout'):
        dispatch(lab.hub,question.get('study'),'update',id=question['id'],status='unanswered' if run['status']=='completed' else 'interrupted')


def log_arguments(parser):
    parser.add_argument('text')
    parser.add_argument('--study', default=os.environ.get('ARLOTOPE_RUN_SUBJECT'))
    parser.add_argument('--title', default='')
    parser.add_argument('--tag', action='append', default=[])
    parser.add_argument('--ref', action='append', default=[])
    parser.add_argument('--agent', help='Exported child agent ID, when known')


def log_note(hub, args, project=None):
    """A contextual knowledge record; never an outcome, directive or approval."""
    study = args.study if args.study != 'hub' else None
    context = {}
    rid = os.environ.get('ARLOTOPE_RUN_ID')
    if rid and study == (os.environ.get('ARLOTOPE_RUN_SUBJECT') or None):
        context.update(run=rid, attempt=int(os.environ.get('ARLOTOPE_ATTEMPT') or 0))
        context['about'] = {'run': rid}
        if args.agent:context['about']['agent'] = args.agent
    elif args.agent:
        raise ValueError('A child agent reference needs its managed parent run.')
    data = dict(kind='log', text=args.text, title=args.title, tags=args.tag, refs=args.ref,
                author='agent' if rid else 'human', **context)
    if project:
        return create(project_folder(project), studies=[study] if study else [], **data)
    return dispatch(hub, study, 'add', **data)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hub',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--study');parser.add_argument('--project',type=Path)
    parser.add_argument('action',choices=('list','search','show','add','ack'))
    parser.add_argument('value',nargs='?',default='')
    parser.add_argument('--kind',choices=KINDS,default='');parser.add_argument('--tag',default='')
    parser.add_argument('--title',default='');parser.add_argument('--text',default='');parser.add_argument('--file',type=Path)
    parser.add_argument('--url');parser.add_argument('--doi');parser.add_argument('--version');parser.add_argument('--coverage',default='metadata')
    parser.add_argument('--attachment',type=Path);parser.add_argument('--acknowledge',action='store_true')
    parser.add_argument('--offset',type=int,default=0)
    args=parser.parse_args(argv)
    action={'search':'list','show':'get','ack':'update'}.get(args.action,args.action)
    data={'query':args.value if args.action=='search' else '', 'kind':args.kind,'tag':args.tag,'offset':args.offset} if action=='list' else {'id':args.value}
    if action=='add':
        data={'kind':args.kind or 'note','text':args.file.read_text(encoding='utf-8') if args.file else args.text,
              'title':args.title,'tags':[args.tag] if args.tag else [],'author':'agent' if os.environ.get('ARLOTOPE_RUN_ID') else 'human',
              'acknowledge':args.acknowledge,'run':os.environ.get('ARLOTOPE_RUN_ID')}
        if args.kind=='source':data['source']={k:v for k,v in {'url':args.url,'doi':args.doi,'version':args.version,'coverage':args.coverage,'retrieved':now()}.items() if v}
        if args.attachment:data['attachment']=str(args.attachment)
    if args.action=='ack':data['acknowledgement']={'run':os.environ.get('ARLOTOPE_RUN_ID') or 'terminal-agent'}
    if args.project:
        folder=project_folder(args.project)
        result=listing(folder,**data) if action=='list' else get(folder,data['id']) if action=='get' else create(folder,**data) if action=='add' else update(folder,data.pop('id'),**data)
    else:result=dispatch(args.hub,args.study,action,**data)
    print(json.dumps(result,ensure_ascii=False,default=str,indent=2))


if __name__=='__main__':main()
