"""Prompt, ordinary designer session, shared 3D preview, reviewed room resource application."""
import json
import shutil
import uuid

import ctx
import room_resources as R
from executor import Lab, RunSpec, enqueue, reply, find_run
from executor.procs import excl_lock


def _draft(value):
    if not isinstance(value, str) or not R.ID.fullmatch(value):
        raise ValueError('Choose a room draft.')
    folder = ctx.HUB / 'lab/.bus/room-drafts' / value
    if not folder.is_dir(): raise ValueError('No such room draft.')
    return folder


def _meta(folder):
    return json.loads((folder / 'draft.json').read_text(encoding='utf-8'))


def drafts(q=None):
    out = []
    for f in sorted((ctx.HUB / 'lab/.bus/room-drafts').glob('*/draft.json'), reverse=True):
        try: out.append(_meta(f.parent))
        except (ValueError, OSError): pass
    out.sort(key=lambda d: (d.get('created', ''), d['id']), reverse=True)
    return {'ok': True, 'drafts': out[:30], 'rooms': R.read(ctx.HUB)}, 200


def get(q):
    try:
        folder = _draft(q.get('id'))
        data = R.validate(json.loads((folder / 'room.json').read_text(encoding='utf-8')))
        module = folder / 'extra.js'
        return {'ok': True, **_meta(folder), 'definition': data,
                'module': module.is_file(), 'revision': str((folder / 'room.json').stat().st_mtime_ns) + (str(module.stat().st_mtime_ns) if module.is_file() else '')}, 200
    except (ValueError, OSError) as error:
        return {'error': str(error)}, 400


def resource(q):
    try:
        if q.get('draft'):
            folder = _draft(q['draft'])
        else:
            rid = q.get('room')
            if not isinstance(rid, str) or not R.ID.fullmatch(rid): return None
            folder = ctx.HUB / 'lab/rooms' / rid
        file = folder / 'extra.js'
        return (file, 'text/javascript') if file.is_file() else None
    except (ValueError, OSError): return None


def op(body):
    try:
        action = body.get('action')
        if action == 'create':
            rid = body.get('room')
            if not isinstance(rid, str) or not R.ID.fullmatch(rid): raise ValueError('Choose a valid room ID.')
            did = rid[:40] + '-' + uuid.uuid4().hex[:8]
            folder = ctx.HUB / 'lab/.bus/room-drafts' / did
            folder.mkdir(parents=True)
            existing = R.read(ctx.HUB).get(rid, {}).get('definition')
            definition = existing or {'base': rid, 'key': rid, 'size': [10,7], 'floor': 'boards', 'accent': 'blue',
                'props': [{'c':'roundTable','at':[0,0]}, {'c':'bookshelf','at':[-3,-2.8]}, {'c':'plant','at':[4,2]}]}
            (folder / 'room.json').write_text(json.dumps(definition, indent=2), encoding='utf-8')
            old_module = ctx.HUB / 'lab/rooms' / rid / 'extra.js'
            if old_module.is_file(): shutil.copyfile(old_module, folder / 'extra.js')
            meta = {'id':did,'room':rid,'request':str(body.get('text') or '')[:3000], 'created':ctx.ts()}
            (folder / 'draft.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
            (folder / 'README.md').write_text('Read docs/room-design.md. Edit room.json and optionally extra.js here. '
                'Preview: /static/lab-view.html?roomdraft='+did+' . Use normal shell/browser tools for feedback. '
                'Do not apply the draft or edit unrelated resources.\nRequest: '+meta['request'],encoding='utf-8')
            return {'ok':True,**meta}, 200
        folder = _draft(body.get('id')); meta = _meta(folder)
        if action == 'save':
            definition = R.validate(body.get('definition'))
            (folder / 'room.json').write_text(json.dumps(definition,indent=2),encoding='utf-8')
        elif action == 'agent':
            text = str(body.get('text') or meta['request']).strip()
            if not text or len(text)>3000: raise ValueError('Describe the room change in up to 3000 characters.')
            prompt = (f"Follow .claude/skills/design-room/SKILL.md. Read {(folder / 'README.md').as_posix()} and docs/room-design.md. "
                f"Design only inside {folder.as_posix()}. Keep the room ID {meta['room']}. "
                'Use the existing kit/components. An optional extra.js module may add room-specific geometry; '
                'do not edit renderer code. Use your normal shell/browser tools and preview for feedback. '
                'Leave a summary of what changed and any preview limitations.\nRequest: '+text)
            if ctx.SERVER:
                prompt += (f"\nLive preview: http://127.0.0.1:{ctx.SERVER.server_address[1]}"
                           f"/static/lab-view.html?roomdraft={meta['id']} . Reload after edits and inspect in your browser.")
            old = None
            if meta.get('run_id'):
                try: old = find_run(Lab(ctx.HUB),meta['run_id'])[3]
                except ValueError: pass
            if old and old.get('session_id'):
                reply(Lab(ctx.HUB),old['run_id'],prompt)
                run = old
            elif old and old.get('status') in ('queued', 'starting', 'running', 'resuming', 'waiting_input'):
                raise ValueError('The designer is starting. Open its conversation to follow or message it.')
            else:
                run = enqueue(Lab(ctx.HUB),RunSpec(skill='',prompt=prompt,role='designer',label='Design room: '+meta['room']))
            meta['run_id']=run['run_id']
            (folder/'draft.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');ctx.KICK.set()
        elif action == 'apply':
            if body.get('confirm') is not True: raise ValueError('Review the preview and confirm application.')
            data = R.validate(json.loads((folder/'room.json').read_text(encoding='utf-8')))
            with excl_lock(ctx.HUB/'lab/.bus/.room-resources.lock'):
                destination = ctx.HUB/'lab/rooms'/meta['room'];destination.mkdir(parents=True,exist_ok=True)
                if (folder/'extra.js').is_file(): shutil.copyfile(folder/'extra.js',destination/'extra.js')
                elif (destination/'extra.js').is_file(): (destination/'extra.js').unlink()
                temp=destination/'room.json.tmp';temp.write_text(json.dumps(data,indent=2),encoding='utf-8');temp.replace(destination/'room.json')
            meta['applied']=ctx.ts();(folder/'draft.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
            ctx.pi_log({'action':'room.apply','room':meta['room'],'draft':meta['id']})
        else: raise ValueError('Choose create, save, agent or apply.')
        return {'ok':True,**meta},200
    except (ValueError,OSError) as error:
        return {'error':str(error)},400
