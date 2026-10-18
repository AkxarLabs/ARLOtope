"""Human notes and separately filed answers; neither edits the referenced file."""
import ctx
from executor import Lab
import knowledge
from pathlib import Path


def list_records(q):
    try:
        warnings=knowledge.retry_answers(Lab(ctx.HUB))
        if q.get('id'):
            return {'ok':True,'record':knowledge.dispatch(ctx.HUB,q.get('study') or None,'get',id=q['id'])},200
        return {'ok':True,'warnings':warnings,**knowledge.dispatch(ctx.HUB,q.get('study') or None,'list',
            **{k:q[k] for k in ('query','kind','tag','offset') if k in q})},200
    except (OSError,ValueError) as error:
        return {'error':str(error)},400


def note(body):
    try:
        study=body.get('study') or None
        about=body.get('about') or None
        if about and (not isinstance(about,dict) or any(k not in ('scope','slug','rel','run','artifact','record') for k in about)):
            raise ValueError('Choose the record this note concerns.')
        result=knowledge.dispatch(ctx.HUB,study,'add',kind='note',text=body.get('text',''),
            title=body.get('title',''),about=about,acknowledge=body.get('acknowledge',True),
            tags=body.get('tags') or [])
        ctx.pi_log({'action':'knowledge.note','study':study,'id':result['id']})
        return {'ok':True,'record':result},200
    except (OSError,ValueError) as error:
        return {'error':str(error)},400


def attachment(q):
    """Download only an attachment explicitly linked by a knowledge record."""
    try:
        study=q.get('study') or None;identifier=q.get('id','')
        record=knowledge.dispatch(ctx.HUB,study,'get',id=identifier)
        loc=knowledge.location(ctx.HUB,study)
        if record.get('scope')=='study':
            path=knowledge.attachment(ctx.HUB/'studies'/study/'knowledge',identifier)
        elif not loc.get('remote'):path=knowledge.attachment(loc['folder'],identifier)
        else:
            import base64,hashlib,uuid
            import remote_projects
            part=remote_projects.call(ctx.HUB,study,'knowledge',action='attachment',id=identifier,offset=0)
            if not 0<=part['size']<=50*1024*1024:raise ValueError('Attachment is too large.')
            key=hashlib.sha256((study+identifier+str(record.get('attachment'))).encode()).hexdigest()
            path=ctx.HUB/'lab/.bus/knowledge-files'/key/Path(part['name']).name
            if not path.is_file() or path.stat().st_size!=part['size']:
                path.parent.mkdir(parents=True,exist_ok=True)
                temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
                try:
                    with temp.open('wb') as stream:
                        offset=0;size=part['size']
                        while True:
                            content=base64.b64decode(part['data'],validate=True)
                            if not content and offset<size:raise ValueError('Attachment transfer stopped. Retry the download.')
                            stream.write(content);offset+=len(content)
                            if offset>=size:break
                            part=remote_projects.call(ctx.HUB,study,'knowledge',action='attachment',id=identifier,offset=offset)
                            if part['size']!=size:raise ValueError('Attachment changed during download. Retry.')
                    if offset!=size:raise ValueError('Incomplete attachment transfer.')
                    temp.replace(path)
                finally:temp.unlink(missing_ok=True)
        import library
        return path,library._FIG_CTYPE.get(path.suffix.lower(),'application/octet-stream')
    except (OSError,ValueError):return None
