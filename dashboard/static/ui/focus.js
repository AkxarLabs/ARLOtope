/* Viewing context only. IDs in the URL; no second task store or execution state. */
(function () {
  const N=window.NL,{html,useState,useEffect}=N;
  const fields={study:'study',task:'task',run:'agent',sub:'child',worker:'worker'};
  let value={},owner='',listeners=new Set();
  N.resolveFocus=(s,ref={})=>{
    const r=(s.runs||[]).find(r=>r.run_id===ref.run),a=(s.agents||[]).find(a=>ref.worker&&a.worker_id===ref.worker);
    const study=ref.study||r?.subject||a?.subject||'';
    if(study&&study!=='hub'&&!(s.items||[]).some(i=>i.id===study))return {};
    const out={...ref,study:study==='hub'?'':study};
    if(r?.subject&&r.subject!==study){delete out.run;delete out.sub;delete out.task}
    else if(r){out.task=ref.task||r.workflow_node||r.assigned_step||''}
    return Object.fromEntries(Object.keys(fields).filter(k=>out[k]).map(k=>[k,String(out[k])]));
  };
  N.getFocus=()=>{
    const s=N.getState()||{},key=s.lab_info?.path||location.origin;
    if(owner&&owner!==key)value={};owner=key;return N.resolveFocus(s,value);
  };
  N.setFocus=(next,{url=true}={})=>{
    const focus=N.resolveFocus(N.getState()||{},next);
    if(JSON.stringify(focus)===JSON.stringify(value))return;
    value=focus;
    if(url){
      const route=N.parseRoute(),query={...route.query};
      for(const [key,param] of Object.entries(fields)){
        if(focus[key])query[param]=focus[key];else delete query[param];
      }
      const q=N.qs(query);history.replaceState(null,'',location.hash.split('?')[0]+(q?'?'+q:''));
    }
    for(const notify of listeners)notify();
  };
  N.syncFocus=(route,s)=>{
    const previous=N.getFocus(),q=route.query||{},ref=Object.fromEntries(Object.entries(fields).filter(([,param])=>q[param]).map(([key,param])=>[key,q[param]]));
    if(route.page==='workflow'&&q.workflow&&!ref.study&&N.item(s,previous.study)?.workflow!==q.workflow){N.setFocus({},{url:false});return}
    if(route.page==='study'){
      const study=route.args[0];N.setFocus({...(previous.study===study?previous:{}),...ref,study},{url:false});
    }else if(['library','artifacts'].includes(route.page)){
      const study=q.study==='@lab'?'':q.study||'';
      N.setFocus({...(previous.study===study?previous:{}),...ref,study},{url:false});
    }else if(Object.keys(ref).length)N.setFocus(ref,{url:false});
    else N.setFocus(previous,{url:false});
  };
  N.useFocus=()=>{
    const [,refresh]=useState(0);
    useEffect(()=>{const notify=()=>refresh(n=>n+1);listeners.add(notify);return()=>listeners.delete(notify)},[]);
    return N.getFocus();
  };
  N.focusAgent=(id,provided)=>{
    const s=N.getState()||{},a=provided||(s.agents||[]).find(a=>a.id===id||a.worker_id===id||a.run_id===id&&!a.parent);
    if(!a)return;
    N.setFocus({study:a.subject||a.project||a.idea,run:a.run_id,sub:a.sub,worker:a.run_id?null:a.worker_id});
  };
  N.focusRun=(run,sub)=>N.setFocus({study:run.subject,task:run.workflow_node||run.assigned_step,run:run.run_id,sub});
  N.focusHref=(path,focus=N.getFocus())=>{
    const [base,search='']=String(path).replace(/^#\//,'').split('?'),query=Object.fromEntries(new URLSearchParams(search));
    for(const [key,param] of Object.entries(fields))if(focus[key]&&!Object.hasOwn(query,param))query[param]=focus[key];
    if(base.startsWith('workflow')&&focus.study&&!Object.hasOwn(query,'workflow')){const it=N.item(N.getState(),focus.study);if(it)query.workflow=it.workflow}
    const q=N.qs(query);return '#/'+base+(q?'?'+q:'');
  };
  N.clearFocus=()=>{
    N.setFocus({},{url:false});const route=N.parseRoute(),q={...route.query};
    Object.values(fields).forEach(key=>delete q[key]);
    if(route.page==='study'){N.go('#/');return}
    N.go('#/'+[route.page==='home'?'':route.page,...route.args].filter(Boolean).map(encodeURIComponent).join('/')+(N.qs(q)?'?'+N.qs(q):''));
  };
  N.WorkContext=()=>{
    const f=N.useFocus(),s=N.useLab(),study=N.item(s,f.study),run=(s.runs||[]).find(r=>r.run_id===f.run);
    const a=(s.agents||[]).find(a=>f.run?a.run_id===f.run&&(f.sub?a.sub===f.sub:!a.parent):f.worker&&a.worker_id===f.worker);
    if(!Object.keys(f).length)return null;
    const who=a?.label||run?.assignment?.label||((run?.backend||a?.backend||'Agent')+' · '+N.roleOf(a?.role||run?.role||'general').label);
    return html`<nav class="work-context" aria-label="Selected work">
      ${study?html`<a href=${'#/study/'+encodeURIComponent(study.id)} onClick=${()=>N.setFocus({study:study.id})}>${study.title||study.id}</a>`:html`<span>Lab</span>`}
      ${f.task?html`<span aria-hidden="true">/</span><a href=${N.focusHref('workflow/map')} title="Open this task in Workflow">${study?N.taskLabel(study,f.task):f.task}</a>`:null}
      ${f.run||f.worker?html`<span aria-hidden="true">/</span><button type="button" class="link" title=${who} onClick=${()=>f.run?N.openRun(f.run,f.sub):N.openWorker(f.worker)}>${N.clip(who,48)}</button>`:null}
      <button type="button" class="iconbtn sm" aria-label="Clear work focus" title="Show the whole lab" onClick=${N.clearFocus}>×</button>
    </nav>`;
  };
})();
