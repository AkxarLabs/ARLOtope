"""A study's workflow history, projected from existing records. No second journal."""
from __future__ import annotations

import json
from pathlib import Path
import uuid


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
    visits={};execution=0;workflow=study['workflow']
    def visit(node,number):
        key=(execution,node,number)
        return visits.setdefault(key,{'workflow':workflow,'execution':execution,'node':node,'visit':number,'events':[],'runs':[]})
    for event in events:
        if event['kind'] in ('new','workflow'):
            execution+=1;workflow=event.get('workflow') or workflow
        if event.get('node') and event.get('visit'):
            visit(event['node'],event['visit'])['events'].append(event)
    runs=[]
    keys=('run_id','label','workflow_node','workflow_visit','status','backend','model','model_used','role',
          'created','updated','attempt','attempts','session_id','parent','context','report','reason',
          'resume','remote','explains','judge','assistant')
    for _,_,path,raw in all_runs(lab):
        if (raw.get('subject') or raw.get('target'))!=slug and (raw.get('explains') or {}).get('study')!=slug:
            continue
        run={key:raw[key] for key in keys if key in raw}
        run.update(manifest=str(path),transcript=str(path.parent/(raw.get('stream') or path.stem+'.stream.jsonl')))
        runs.append(run)
        if raw.get('workflow_node') and raw.get('workflow_visit'):
            bound=next((v for v in visits.values() if any(e.get('run_id')==raw['run_id'] for e in v['events'])),None)
            (bound if bound is not None else visit(raw['workflow_node'],raw['workflow_visit']))['runs'].append(raw['run_id'])
    ids={r['run_id'] for r in runs}
    transitions=[e for e in ledger(lab,tail=None) if e.get('run_id') in ids]
    outputs=[{k:a[k] for k in ('id','title','created','run_id','about','kind') if k in a}
             for a in all_artifacts(hub,limit=None,study=slug)]
    for token in study.get('active_steps',[]):
        visit(token['id'],token['visit'])['active']=True
    for item in visits.values():
        outcomes=[e for e in item['events'] if e['kind'] in ('task-completed','task-routed','task-reused','task-omitted')]
        item['outcome']=outcomes[-1] if outcomes else None
    return {'schema':1,'study':slug,'workflow':study['workflow'],'generated_at':journal.now(),
            'finished':study['finished'],'events':events,'visits':list(visits.values()),
            'runs':sorted(runs,key=lambda r:r.get('created','')),'run_transitions':transitions,'outputs':outputs,
            'sources':{'journal':str(journal.path(hub)),'runs':str(lab.runs_ledger)},
            'definition_at_export':model.workflow(study['workflow'],hub),
            'coverage':'Local and mirrored run records; transcripts may be capped and offline remote records may be stale. The workflow definition is current, not a historical reconstruction.'}


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
        state=outcome['kind'].removeprefix('task-') if outcome else 'active' if item.get('active') else 'no outcome recorded'
        text.extend([f'### {item["workflow"]} · {item["node"]} · pass {item["visit"]}',f'State: {state}',
                     'Runs: '+(', '.join('`'+r+'`' for r in item['runs']) or 'none recorded'),''])
    text.extend(['## Agent sessions',''])
    for run in data['runs']:
        text.extend([f'- `{run["run_id"]}` · {run.get("backend","")} · {run.get("status","")}',
                     f'  - Manifest: `{run["manifest"]}`',f'  - Transcript: `{run["transcript"]}`'])
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
        temp=target.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_text(content,encoding='utf-8');temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
    return {'ok':True,'path':str(folder/'workflow.md'),'rel':'history/workflow.md'}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study');parser.add_argument('--hub',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--save',action='store_true');args=parser.parse_args()
    print(json.dumps(save(args.hub,args.study) if args.save else read(args.hub,args.study),indent=2))
