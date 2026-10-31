/* One workspace conversation, with explicit focus and session choices. */
(function () {
  const N=window.NL,{html,useState,useEffect,useRef}=N;
  N.AssistantPanel=({onClose,initialText='',initialStudy='',initialRun='',initialAgent='',initialDocument=null,initialReference=null,initialScope=false})=>{
    const lab=N.useLab(),read=N.usePoll('/api/assistant',5000),data=read.data||read.previous,load=read.reload,[text,setText]=useState(initialText),[busy,setBusy]=useState(false),[error,setError]=useState('');
    const [study,setStudy]=useState(initialStudy),[run,setRun]=useState(initialRun),[agent,setAgent]=useState(initialAgent),[document,setDocument]=useState(initialDocument),[reference,setReference]=useState(initialReference),[backend,setBackend]=useState(''),[preset,setPreset]=useState(''),[model,setModel]=useState(''),[fresh,setFresh]=useState(false),initialized=useRef(false);
    useEffect(()=>{if(read.data&&!initialized.current){initialized.current=true;const c=read.data.selection||{},explicitFocus=initialScope||initialDocument||initialReference||initialAgent;setStudy(explicitFocus?(initialStudy||''):initialStudy||(initialRun?'':c.study)||'');setRun(initialRun||(initialStudy||explicitFocus?'':c.run)||'');setAgent(initialAgent||(explicitFocus?'':c.agent)||'');setBackend(c.backend||'');setPreset(c.preset||'');setModel(c.model||'')}},[read.data]);
    const send=N.useSubmit(async()=>{if(!text.trim())return;setError('');
      const r=await N.api('/api/assistant/message',{text,study,run,agent,backend,model,preset,fresh,document,reference});if(r.error)setError(r.error);else{setText('');setFresh(false);await load()}},setBusy);
    const projects=data?.facts?.projects||[],runs=(data?.facts?.runs||[]).filter(r=>!study||r.project===study);
    const runOptions=[{value:'',label:'No specific run'},...runs.map(r=>({value:r.id,label:r.task||r.id}))];
    const children=runs.find(r=>r.id===run)?.subagents||[],childOptions=[{value:'',label:'Whole task'},...children.map(a=>({value:a.id,label:a.task||a.role||a.id}))];
    if(agent&&!children.some(a=>a.id===agent))childOptions.push({value:agent,label:'Selected subagent'});
    if(run&&!runs.some(r=>r.id===run))runOptions.push({value:run,label:'Selected run · '+run});
    return html`<${N.Sheet} title="Workspace assistant" onClose=${onClose} wide>
      <div class="workspace-assistant"><nav class="assistant-shortcuts" aria-label="Workspace shortcuts">
        <button type="button" onClick=${()=>{onClose();N.open(N.InboxSheet,{}, {key:'inbox'})}}>Inbox ↗</button>
        <a href="#/runs" onClick=${onClose}>Working agents ↗</a><a href="#/library" onClick=${onClose}>Library ↗</a><a href="#/workflow" onClick=${onClose}>Workflow ↗</a></nav>
      ${!data||read.error?html`<${N.LoadState} ...${read} stale=${!!read.previous}/>`:null}
      ${data?html`<details class="assistant-options"><summary>Focus · ${projects.find(p=>p.id===study)?.title||'Whole lab'}${run?' · '+(runs.find(r=>r.id===run)?.task||'Selected run')+(agent?' · '+(children.find(a=>a.id===agent)?.role||'Subagent'):''):''}</summary><div class="assistant-scope">
        <${N.Field} label="Focus"><${N.Select} value=${study} onChange=${v=>{setStudy(v);setRun('');setAgent('');setDocument(null);setReference(null)}} options=${[{value:'',label:'Whole lab'},...projects.map(p=>({value:p.id,label:p.title}))]}/></${N.Field}>
        <${N.Field} label="Agent’s work"><${N.Select} value=${run} onChange=${v=>{setRun(v);setAgent('');setDocument(null);setReference(null)}} options=${runOptions}/></${N.Field}>
        ${children.length||agent?html`<${N.Field} label="Subagent"><${N.Select} value=${agent} onChange=${setAgent} options=${childOptions}/></${N.Field}>`:null}
      </div></details>${data.answer||data.messages?.length||data.status?html`<div class="assistant-conversation" aria-live="polite">
        ${(data.messages||[]).slice(-3).map(m=>html`<p class="assistant-question">${m.text}</p>`)}
        ${data.answer?html`<div class="assistant-answer"><${N.Markdown} text=${data.answer}/></div>`:null}
        ${data.status?html`<p class="muted small">${N.RUN_WORD[data.status]||data.status}${data.run_id?html` · <button class="link" onClick=${()=>N.openRun(data.run_id)}>Open conversation</button>`:null}</p>`:null}</div>`:null}
      <div class="assistant-suggestions" aria-label="Suggested questions">${['What needs my decision?','What changed since I last checked?','Help me adapt this workflow.'].map(t=>html`<button class="chip-btn" type="button" onClick=${()=>setText(t)}>${t}</button>`)}</div>
      ${document?html`<p class="muted small">About ${document.rel}. Answer saved separately. <button class="link" onClick=${()=>setDocument(null)}>Remove focus</button></p>`:null}
      ${reference?html`<p class="muted small">About ${reference.artifact?'the published output':reference.run?'the source run':'the selected record'}. Answer saved separately. <button class="link" onClick=${()=>setReference(null)}>Remove focus</button></p>`:null}
      ${data.question?html`<a class="link small" href=${'#/library?'+N.qs({view:'records',study:data.question.study||'',record:data.question.id})} onClick=${onClose}>Saved question & answer ↗</a>`:null}
      <${N.Field} label="Question"><${N.Textarea} rows=${3} value=${text} onInput=${setText} onSubmit=${send} placeholder="Ask about the work…"/></${N.Field}>
      <details class="assistant-options"><summary>Agent & settings${data.automatic?' · automatic briefings on':''}</summary><div class="assistant-scope">
        <${N.AgentChoice} study=${study||null} role="assistant" value=${preset?'preset:'+preset:backend?'backend:'+backend:''} onChange=${v=>{setPreset(v.startsWith('preset:')?v.slice(7):'');setBackend(v.startsWith('backend:')?v.slice(8):'');setModel('')}}/>
        <${N.Field} label="Model override"><${N.Input} value=${model} onInput=${setModel} placeholder="Use agent settings"/></${N.Field}>
      </div><label><input type="checkbox" checked=${fresh} onChange=${e=>setFresh(e.target.checked)}/> New conversation</label>
      <p class="muted small">Changing agent or model starts a new conversation when you send.</p>
      <label class="assistant-auto"><input type="checkbox" checked=${!!data.automatic} onChange=${async e=>{const r=await N.api('/api/assistant/update',{automatic:e.target.checked});if(r.error)setError(r.error);else load()}}/> Automatic briefings <small class="muted">Uses your assistant while the dashboard is open, at most once every 5 minutes.</small></label></details>
      <div class="row end">${run?html`<${N.Btn} disabled=${busy} onClick=${()=>{onClose();N.explain(run,agent||null,{backend,model,preset})}}>Visual summary</${N.Btn}>`:null}<${N.Btn} kind="primary" busy=${busy} disabled=${!text.trim()||busy} onClick=${send}>Send</${N.Btn}></div>
      `:null}
      ${data?.warnings?.length?html`<p role="status" class="note note-warn">Answer delivery needs attention. ${data.warnings[0]}</p>`:null}${error?html`<p role="alert" class="note note-warn">${error}</p>`:null}</div></${N.Sheet}>`;
  };
  N.openAssistant=(options={})=>{
    const explicit=['initialStudy','initialRun','initialAgent','initialDocument','initialReference','initialScope'].some(k=>Object.hasOwn(options,k)),f=N.getFocus();
    return N.open(N.AssistantPanel,{...(!explicit?{initialStudy:f.study||'',initialRun:f.run||'',initialAgent:f.sub||'',initialScope:true}:{}),...options},{key:'workspace-assistant'});
  };
  N.askAboutRun=(run,agent='')=>N.openAssistant({initialStudy:run.subject||run.explains?.study||'',initialRun:run.run_id,initialAgent:agent,initialScope:true});
  N.AssistantButton=()=>{
    useEffect(()=>{const timer=setInterval(()=>N.api('/api/assistant/update',{}).catch(()=>{}),30000);return()=>clearInterval(timer)},[]);
    return html`<button type="button" class="assistant-launch" onClick=${()=>N.openAssistant()} aria-label="Workspace assistant"><img class="arlotope-mark" src="static/brand/arlotope-mark.png" alt=""/> Assistant</button>`;
  };
})();
