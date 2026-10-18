/* One workspace conversation, with explicit focus and session choices. */
(function () {
  const N=window.NL,{html,useState,useEffect,useRef}=N;
  N.AssistantPanel=({onClose,initialText='',initialStudy='',initialRun='',initialDocument=null,initialReference=null,initialScope=false})=>{
    const lab=N.useLab(),[data,setData]=useState(null),[text,setText]=useState(initialText),[busy,setBusy]=useState(false),[error,setError]=useState('');
    const [study,setStudy]=useState(initialStudy),[run,setRun]=useState(initialRun),[document,setDocument]=useState(initialDocument),[reference,setReference]=useState(initialReference),[backend,setBackend]=useState(''),[preset,setPreset]=useState(''),[model,setModel]=useState(''),[fresh,setFresh]=useState(false),initialized=useRef(false);
    const load=async()=>{const r=await N.get('/api/assistant');if(!r.ok){setError(r.error||'Could not load the assistant.');return}
      setData(r);if(!initialized.current){initialized.current=true;const c=r.selection||{},explicitFocus=initialScope||initialDocument||initialReference;setStudy(explicitFocus?(initialStudy||''):initialStudy||(initialRun?'':c.study)||'');setRun(initialRun||(initialStudy||explicitFocus?'':c.run)||'');setBackend(c.backend||'');setPreset(c.preset||'');setModel(c.model||'')}};
    useEffect(()=>{load();const timer=setInterval(load,5000);return()=>clearInterval(timer)},[]);
    const send=async()=>{if(!text.trim()||busy)return;setBusy(true);setError('');
      try{const r=await N.api('/api/assistant/message',{text,study,run,backend,model,preset,fresh,document,reference});if(r.error)setError(r.error);else{setText('');setFresh(false);await load()}}
      finally{setBusy(false)}};
    const projects=data?.facts?.projects||[],runs=(data?.facts?.runs||[]).filter(r=>!study||r.project===study);
    const runOptions=[{value:'',label:'No specific run'},...runs.map(r=>({value:r.id,label:r.task||r.id}))];
    if(run&&!runs.some(r=>r.id===run))runOptions.push({value:run,label:'Selected run · '+run});
    return html`<${N.Sheet} title="Workspace assistant" onClose=${onClose} wide>
      <div class="workspace-assistant"><nav class="assistant-shortcuts" aria-label="Workspace shortcuts">
        <button type="button" onClick=${()=>{onClose();N.open(N.InboxSheet,{}, {key:'inbox'})}}>Needs attention ↗</button>
        <a href="#/runs" onClick=${onClose}>Working agents ↗</a><a href="#/library" onClick=${onClose}>Library ↗</a><a href="#/workflow" onClick=${onClose}>Workflow ↗</a></nav>
      ${!data&&!error?html`<${N.Spinner}/>`:null}
      ${data?html`<div class="assistant-scope">
        <${N.Field} label="Focus"><${N.Select} value=${study} onChange=${v=>{setStudy(v);setRun('');setDocument(null);setReference(null)}} options=${[{value:'',label:'Whole lab'},...projects.map(p=>({value:p.id,label:p.title}))]}/></${N.Field}>
        <${N.Field} label="Agent’s work"><${N.Select} value=${run} onChange=${v=>{setRun(v);setDocument(null);setReference(null)}} options=${runOptions}/></${N.Field}>
      </div><div class="assistant-conversation" aria-live="polite">
        ${(data.messages||[]).slice(-3).map(m=>html`<p class="assistant-question">${m.text}</p>`)}
        ${data.answer?html`<div class="assistant-answer"><${N.Markdown} text=${data.answer}/></div>`:html`<p class="assistant-welcome">What would you like to look into?</p>`}
        ${data.status?html`<p class="muted small">${N.RUN_WORD[data.status]||data.status}${data.run_id?html` · <button class="link" onClick=${()=>N.openRun(data.run_id)}>Open conversation</button>`:null}</p>`:null}</div>
      <div class="assistant-suggestions" aria-label="Suggested questions">${['What needs my decision?','What changed since I last checked?','Help me adapt this workflow.'].map(t=>html`<button class="chip-btn" type="button" onClick=${()=>setText(t)}>${t}</button>`)}</div>
      ${document?html`<p class="muted small">About ${document.rel}. Answer saved separately. <button class="link" onClick=${()=>setDocument(null)}>Remove focus</button></p>`:null}
      ${reference?html`<p class="muted small">About ${reference.artifact?'the published output':reference.run?'the source run':'the selected record'}. Answer saved separately. <button class="link" onClick=${()=>setReference(null)}>Remove focus</button></p>`:null}
      ${data.question?html`<a class="link small" href=${'#/library?'+N.qs({view:'records',study:data.question.study||'',record:data.question.id})} onClick=${onClose}>Saved question & answer ↗</a>`:null}
      <${N.Field} label="Question"><${N.Textarea} rows=${3} value=${text} onInput=${setText} onSubmit=${send} placeholder="Ask about the work…"/></${N.Field}>
      <details class="assistant-options"><summary>Conversation options</summary><div class="assistant-scope">
        <${N.AgentChoice} study=${study||null} role="assistant" value=${preset?'preset:'+preset:backend?'backend:'+backend:''} onChange=${v=>{setPreset(v.startsWith('preset:')?v.slice(7):'');setBackend(v.startsWith('backend:')?v.slice(8):'');setModel('')}}/>
        <${N.Field} label="Model (optional)"><${N.Input} value=${model} onInput=${setModel} placeholder="Agent default"/></${N.Field}>
      </div><label><input type="checkbox" checked=${fresh} onChange=${e=>setFresh(e.target.checked)}/> New conversation</label>
      <p class="muted small">Changing agent or model starts a new conversation when you send.</p></details>
      <div class="row end">${run?html`<${N.Btn} disabled=${busy} onClick=${()=>{onClose();N.explain(run,null,{backend,model,preset})}}>Visual summary</${N.Btn}>`:null}<${N.Btn} kind="primary" busy=${busy} disabled=${!text.trim()||busy} onClick=${send}>Send</${N.Btn}></div>
      <label class="assistant-auto"><input type="checkbox" checked=${!!data.automatic} onChange=${async e=>{const r=await N.api('/api/assistant/update',{automatic:e.target.checked});if(r.error)setError(r.error);else load()}}/> Automatic briefings <small class="muted">Uses your assistant while the dashboard is open, at most once every 5 minutes.</small></label>`:null}
      ${data?.warnings?.length?html`<p role="status" class="note note-warn">Answer delivery needs attention. ${data.warnings[0]}</p>`:null}${error?html`<p role="alert" class="note note-warn">${error}</p>`:null}</div></${N.Sheet}>`;
  };
  N.openAssistant=(options={})=>N.open(N.AssistantPanel,options,{key:'workspace-assistant'});
  N.AssistantButton=()=>{
    useEffect(()=>{const timer=setInterval(()=>N.api('/api/assistant/update',{}).catch(()=>{}),30000);return()=>clearInterval(timer)},[]);
    return html`<button type="button" class="assistant-launch" onClick=${()=>N.openAssistant()} aria-label="Workspace assistant"><span aria-hidden="true">n.</span> Assistant</button>`;
  };
})();
