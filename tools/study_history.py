"""A study's workflow history, projected from existing records. No second journal."""
from __future__ import annotations

import json
from pathlib import Path

import labfiles
from labfiles import write_atomic


def _passes(events, workflow, graph_workflows=(), remaps=None):
    """Task passes and the active ordered pass at each saved journal cursor."""
    remaps = remaps or {}
    visits = {}; cursors = [None]; execution = 0; current = None; counts = {}
    epochs = []; epoch = 0
    for event in events:
        if event['kind'] in ('new', 'workflow'):
            epoch += 1
        epochs.append(epoch)
    graph_epochs = {epoch for epoch, event in zip(epochs, events) if event['kind'] in ('task-bind','task-completed','task-routed')}

    def visit(node, number, mode):
        original = node; node = remaps.get(node,node)
        key = (execution, node, number)
        item = visits.setdefault(key, {'workflow': workflow, 'execution': execution, 'node': node,
                                      'visit': number, 'mode': mode, 'events': [], 'runs': [], 'recorded_nodes': []})
        if original not in item['recorded_nodes']:item['recorded_nodes'].append(original)
        return item

    def enter(node):
        if not node or node in ('parked', 'killed'):
            return None
        node = remaps.get(node,node)
        key = (execution, node)
        counts[key] = counts.get(key, 0)+1
        return visit(node, counts[key], 'ordered')

    for event in events:
        kind = event['kind']
        if kind in ('new', 'workflow'):
            execution += 1; workflow = event.get('workflow') or workflow
            step = event.get('step') or (current or {}).get('node')
            current = enter(step) if execution not in graph_epochs and workflow not in graph_workflows else None
        if event.get('node') and event.get('visit') and (execution in graph_epochs or workflow in graph_workflows):
            visit(event['node'], event['visit'], 'graph')['events'].append(event)
        elif current is not None:
            current['events'].append(event)
            if kind in ('task-reused', 'task-omitted', 'finish') or (kind in ('move', 'wait') and
                    (current.get('outcome') or {}).get('kind') not in ('task-reused','task-omitted')):
                current['outcome'] = event
            if kind == 'move':
                current = enter(event.get('to'))
            elif kind == 'finish':
                current = None
        cursors.append(current)
    for item in visits.values():
        if item['mode'] == 'graph':
            outcomes = [e for e in item['events'] if e['kind'] in
                        ('task-completed', 'task-routed', 'task-reused', 'task-omitted')]
            item['outcome'] = outcomes[-1] if outcomes else None
        item.setdefault('outcome', None)
    return visits, cursors, execution


def read(hub, slug):
    from kernel import journal, model, studies
    from executor import Lab, all_runs
    from executor.manifest import ledger
    from artifact import all_artifacts
    hub=Path(hub).resolve()
    if not isinstance(slug,str) or not journal.ID.fullmatch(slug) or '..' in slug:
        raise ValueError('Choose a study.')
    study=studies.study(hub,slug)
    if not study:
        raise ValueError('Study not found.')
    lab=Lab(hub)
    events=journal.events(hub,slug)
    workflow_ids={e['workflow'] for e in events if e.get('workflow')}
    graph_workflows={wid for wid in workflow_ids if (model.workflow(wid,hub) or {}).get('nodes')}
    remaps={}
    for event in journal.events(hub,'lab',('remap',)):
        mapping=event.get('map') or {}
        remaps={k:mapping.get(v,v) for k,v in remaps.items()} | mapping
    visits,cursors,execution=_passes(events,study['workflow'],graph_workflows,remaps)
    runs=[]
    keys=('run_id','label','workflow_node','workflow_visit','status','backend','model','model_used','role',
          'created','updated','attempt','attempts','session_id','parent','context','report','reason',
          'resume','remote','explains','judge','assistant','assigned_step','assigned_journal_index',
          'last_message','record_count','record_error','remote_records_offset','subagents','needs_followup','task_label')
    for _,_,path,raw in all_runs(lab):
        if (raw.get('subject') or raw.get('target'))!=slug and (raw.get('explains') or {}).get('study')!=slug:
            continue
        run={key:raw[key] for key in keys if key in raw}
        if isinstance(run.get('resume'),dict):run['resume']={'mode':run['resume'].get('mode')}
        run.update(manifest=str(path),transcript=str(path.parent/(raw.get('stream') or path.stem+'.stream.jsonl')))
        runs.append(run)
        bound=None
        if raw.get('workflow_node') and raw.get('workflow_visit'):
            bound=next((v for v in visits.values() if any(e.get('run_id')==raw['run_id'] for e in v['events'])),None)
            if bound is None:
                matches=[v for v in visits.values() if v['node']==remaps.get(raw['workflow_node'],raw['workflow_node']) and v['visit']==raw['workflow_visit']]
                if len(matches)==1:bound=matches[0]
        elif isinstance(raw.get('assigned_journal_index'),int):
            cursor=raw['assigned_journal_index']
            if 0<=cursor<len(cursors) and cursors[cursor] and cursors[cursor]['node']==remaps.get(raw.get('assigned_step'),raw.get('assigned_step')):
                bound=cursors[cursor]
        if bound is not None:
            bound['runs'].append(raw['run_id'])
            run['pass']=[bound['execution'],bound['node'],bound['visit']]
            if raw.get('task_label'):bound['label']=raw['task_label']
            # Snapshots are evidence of the labels this run saw, not today's editable definition.
            snapshot=path.parent/(raw['run_id']+'.d')/'skills/_workflow.json'
            try:
                definition=json.loads(snapshot.read_text(encoding='utf-8'))
                label=(definition.get('nodes',{}).get(raw.get('workflow_node') or raw.get('assigned_step') or bound['node']) or {}).get('label')
                if label:bound['label']=label
            except (OSError,ValueError,TypeError):pass
    ids={r['run_id'] for r in runs}
    transitions=[e for e in ledger(lab,tail=None) if e.get('run_id') in ids]
    outputs=[{k:a[k] for k in ('id','title','created','run_id','about','kind') if k in a}
             for a in all_artifacts(hub,limit=None,study=slug)]
    for token in study.get('active_steps',[]):
        key=(execution,token['id'],token['visit'])
        visits.setdefault(key,{'workflow':study['workflow'],'execution':execution,'node':token['id'],
                              'visit':token['visit'],'mode':'graph','events':[],'runs':[],'outcome':None})['active']=True
    if cursors[-1] is not None and not study['finished']:
        cursors[-1]['active']=not bool(study.get('waiting'))
    for item in visits.values():
        item.setdefault('label',item['node'])
    import knowledge
    try:
        notes=[]; offset=0
        while True:
            page=knowledge.dispatch(hub,slug,'list',offset=offset,limit=200)
            notes.extend({k:r[k] for k in ('id','title','created','kind','tags','about','run','attempt','refs','text','scope','slug','rel') if k in r}
                         for r in page['rows'] if r.get('kind') in ('log','note','answer') or r.get('run') or (r.get('about') or {}).get('run'))
            if page.get('next') is None:break
            offset=page['next']
        notes_error=None
    except (OSError,ValueError,RuntimeError) as error:
        notes=[];notes_error=str(error)
    return {'schema':1,'study':slug,'workflow':study['workflow'],'generated_at':labfiles.now(),
            'finished':study['finished'],'events':events,'visits':list(visits.values()),
            'runs':sorted(runs,key=lambda r:r.get('created','')),'run_transitions':transitions,'outputs':outputs,
            'notes':notes,'notes_error':notes_error,
            'sources':{'journal':str(journal.path(hub)),'runs':str(lab.runs_ledger)},
            'definition_at_export':model.workflow(study['workflow'],hub),
            'coverage':'Local and mirrored run records. Older runs may lack saved responses, exchanges or assignment IDs. Unexported child messages are unavailable. Transcripts may be capped; offline remote records may be stale. Task IDs are retained when no saved label exists. The exported workflow definition is current.'}


def save(hub, slug):
    """Explicitly refresh a generated snapshot; canonical journals and research files stay untouched."""
    data=read(hub,slug)
    base=Path(hub).resolve()/'studies'/slug
    folder=base/'history'
    if not folder.resolve().is_relative_to(base.resolve()) or not base.resolve().is_relative_to(Path(hub).resolve()/'studies'):
        raise ValueError('History must remain in this study.')
    folder.mkdir(parents=True,exist_ok=True)
    text=[f'# Workflow history — {slug}', '',f'Generated: {data["generated_at"]}',
          '',f'Workflow: `{data["workflow"]}`. This snapshot can be refreshed from the study History tab.',
          '',data['coverage'],'','[Structured snapshot](workflow.json)','','## Tasks and repetitions','']
    for item in data['visits']:
        outcome=item['outcome']
        state=(outcome.get('outcome') or outcome['kind'].removeprefix('task-')) if outcome else 'active' if item.get('active') else 'no outcome recorded'
        text.extend([f'### {item["workflow"]} · {item["label"]} · pass {item["visit"]}',f'State: {state}',
                     'Runs: '+(', '.join('`'+r+'`' for r in item['runs']) or 'none recorded'),''])
    text.extend(['## Agent sessions',''])
    for run in data['runs']:
        text.extend([f'- `{run["run_id"]}` · {run.get("backend","")} · {run.get("status","")}',
                     f'  - Manifest: `{run["manifest"]}`',f'  - Transcript: `{run["transcript"]}`',
                     f'  - Saved exchanges: `{Path(run["manifest"]).parent / (run["run_id"]+".d") / "conversation.jsonl"}`'])
        if run.get('last_message'):text.extend(['',run['last_message'],''])
    text.extend(['','## Study logs',''])
    for note in data['notes']:
        text.extend([f'- {note["title"]} · `{note["id"]}` · run `{note.get("run") or "unassigned"}`',
                     '  '+note.get('text','').replace('\n','\n  ')])
    if data['notes_error']:text.append('Logs unavailable: '+data['notes_error'])
    text.extend(['','## Outputs','',*[f'- {a["title"]} · `{a["id"]}`' for a in data['outputs']],
                 '','## Original records','',*[f'- {key}: `{value}`' for key,value in data['sources'].items()]])
    text.extend(['','## Decisions and changes',''])
    for event in data['events']:
        detail=' · '.join(str(event[key]) for key in ('node','checkpoint','decision','outcome','note') if event.get(key))
        text.append(f'- {event.get("ts","")} · {event["kind"]} · {detail}')
    files=[('workflow.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n'),('workflow.md','\n'.join(text)+'\n')]
    if any((folder/name).is_symlink() for name,_ in files):
        raise ValueError('History snapshot must be a regular file.')
    for name,content in files:
        target=folder/name
        write_atomic(target,content)
    return {'ok':True,'path':str(folder/'workflow.md'),'rel':'history/workflow.md'}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study');parser.add_argument('--hub',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--save',action='store_true');args=parser.parse_args()
    print(json.dumps(save(args.hub,args.study) if args.save else read(args.hub,args.study),indent=2))
