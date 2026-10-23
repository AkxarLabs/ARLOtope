/* Agent identities and a contextual card over the visual Lab. */
(function () {
  const NL = window.NL;
  const { html, useState, useEffect } = NL;

  const agentCache=new Map();
  NL.useAgentSettings=study=>{
    const key=study||'', [revision,setRevision]=useState(0);
    useEffect(()=>{const reload=()=>setRevision(v=>v+1);window.addEventListener('nl-agent-settings',reload);return()=>window.removeEventListener('nl-agent-settings',reload)},[]);
    const read=NL.useGet('/api/agent-settings'+(study?'?study='+encodeURIComponent(study):''),revision);
    useEffect(()=>{if(read.data?.ok)agentCache.set(key,read.data)},[read.data]);
    const data=read.data||read.previous||agentCache.get(key);
    return data||read.error?{...data,error:read.error,reload:read.reload}:null;
  };
  NL.AgentChoice=({value='',onChange,study,role='general',label='Agent',custom=true})=>{
    const data=NL.useAgentSettings(study),lab=NL.useLab(),resolved=data?.resolved?.[role];
    const options=[{value:'',label:'Use role defaults'+(resolved?' · '+(resolved.label||resolved.backend):'')},
      ...(data?.presets||[]).map(p=>({value:'preset:'+p.id,label:(p.label||p.id)+' · '+p.backend})),
      ...(custom?NL.backends(lab).map(b=>({value:'backend:'+b.id,label:b.id+' · custom settings'})):[])];
    return html`<${NL.Field} label=${label}><${NL.Select} value=${value} onChange=${onChange} options=${options}/>
      ${!value&&resolved?html`<small class="muted">${resolved.backend}${resolved.model?' · '+resolved.model:''} · ${resolved.source}</small>`:null}
      ${data?.error?html`<${NL.LoadState} error=${data.error} reload=${data.reload} stale=${!!data.presets} />`:null}</${NL.Field}>`;
  };
  NL.AgentAssignments=({study,onDraft,value})=>{
    const data=NL.useAgentSettings(study),[draft,setDraft]=useState(value||null),[editing,setEditing]=useState(''),[preset,setPreset]=useState({}),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
    useEffect(()=>{if(data?.ok&&!draft)setDraft(study?data.study:data.defaults)},[data,study]);
    if(data?.error&&!data.presets)return html`<${NL.LoadState} error=${data.error} reload=${data.reload} />`;
    if(!data||!draft)return html`<${NL.Spinner}/>`;
    const all=Object.fromEntries(data.presets.map(p=>[p.id,Object.fromEntries(Object.entries(p).filter(([k])=>!['id','found'].includes(k)))])),current=draft.presets||all;
    const choices=Object.entries(current).map(([id,p])=>({value:id,label:(p.label||id)+' · '+p.backend}));
    const change=v=>{setDraft(v);setMessage('');onDraft?.(v)};
    const setRole=(role,v)=>{const roles={...(draft.role_presets||{})};if(v==='@inherit')delete roles[role];else roles[role]=v==='@default'?null:v;change({...draft,role_presets:roles})};
    const save=async()=>{setBusy(true);setError('');const body={settings:study?draft:{...draft,presets:current},...(study?{study}:{})};const r=await NL.api('/api/agent-settings',body);setBusy(false);if(r.error)setError(r.error);else{agentCache.clear();const {presets,...saved}=draft;setDraft(saved);window.dispatchEvent(new Event('nl-agent-settings'));setMessage('Saved. Applies to new tasks.');NL.refresh()}};
    const commitPreset=()=>{try{const next={...preset};if(typeof next.command==='string'){if(next.command.trim())next.command=JSON.parse(next.command);else delete next.command}if(!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/.test(editing))throw Error('Use a short ID with letters, numbers, dashes or underscores.');if(!next.label?.trim())throw Error('Name this preset.');change({...draft,presets:{...current,[editing]:next}});setEditing('');setError('')}catch(e){setError(e.message)}};
    return html`<div class="agent-assignments">
      ${data.error?html`<${NL.LoadState} error=${data.error} reload=${data.reload} stale />`:null}
      <${NL.Field} label=${study||onDraft?'Default agent':'Lab default agent'}><${NL.Select} value=${draft.default_preset||''} onChange=${v=>change({...draft,default_preset:v||null})} options=${[{value:'',label:'Use existing '+(study||onDraft?'Lab':'harness')+' settings'},...choices]}/></${NL.Field}>
      <details><summary>Agents by role <span class="muted small">${Object.keys(draft.role_presets||{}).length?'· '+NL.plural(Object.keys(draft.role_presets).length,'custom choice'):''}</span></summary><p class="muted small">Override the default for specific roles. Child agents use their harness settings.</p>
        <div class="agent-role-rows">${Object.entries(data.roles).map(([id,label])=>html`<${NL.Field} key=${id} label=${label}><${NL.Select} value=${Object.hasOwn(draft.role_presets||{},id)?draft.role_presets[id]??'@default':'@inherit'} onChange=${v=>setRole(id,v)} options=${[{value:'@inherit',label:study||onDraft?'Use Lab role setting':'Use general default'},...(study||onDraft?[{value:'@default',label:'Use study default'}]:[]),...choices]}/></${NL.Field}>`)}</div>
      </details>
      ${!study&&!onDraft?html`<section class="preset-list"><header class="row"><h3 class="grow">Agent presets</h3><${NL.Btn} small onClick=${()=>{let id='new-agent',i=2;while(current[id])id='new-agent-'+i++;setEditing(id);setPreset({label:'',backend:'codex'});setError('')}}>Add preset</${NL.Btn}></header>
        ${draft.presets?html`<p class="muted small">Save your changes to test a preset.</p>`:null}
        ${Object.entries(current).map(([id,p])=>html`<div class="preset-row"><div class="grow"><b>${p.label||id}</b><small class="muted">${p.backend}${p.model?' · '+p.model:''}</small></div><button class="link" onClick=${()=>{setEditing(id);setPreset({...p,command:p.command?JSON.stringify(p.command):''});setError('')}}>Edit</button><button class="link" onClick=${async()=>{setBusy(true);const r=await NL.api('/api/agent-settings/check',{preset:id});setBusy(false);setMessage(r.message||'');setError(r.error||'')}} disabled=${busy||!!draft.presets}>Test</button><button class="link" aria-label=${'Remove '+(p.label||id)} onClick=${()=>{const next={...current};delete next[id];change({...draft,presets:next})}}>Remove</button></div>`)}
        ${editing?html`<fieldset><legend>Preset</legend><div class="grid2"><${NL.Field} label="Preset ID"><${NL.Input} value=${editing} disabled=${!!current[editing]} onInput=${setEditing}/></${NL.Field}><${NL.Field} label="Name"><${NL.Input} value=${preset.label||''} onInput=${v=>setPreset({...preset,label:v})}/></${NL.Field}></div>
        <${NL.Field} label="Harness"><${NL.Select} value=${preset.backend} onChange=${v=>setPreset({...preset,backend:v,model:'',effort:''})} options=${['claude','codex','opencode','acp']}/></${NL.Field}>
        <div class="grid2"><${NL.Field} label="Model (optional)"><${NL.Input} value=${preset.model||''} onInput=${v=>setPreset({...preset,model:v})} placeholder="Harness default"/></${NL.Field}>${['claude','codex'].includes(preset.backend)?html`<${NL.Field} label="Effort"><${NL.Select} value=${preset.effort||''} onChange=${v=>setPreset({...preset,effort:v})} options=${[{value:'',label:'Harness default'},'low','medium','high','xhigh','max']}/></${NL.Field}>`:null}</div>
        <details open=${preset.backend==='acp'}><summary>Command</summary><${NL.Field} label="Command arguments (JSON)"><${NL.Input} value=${preset.command||''} onInput=${v=>setPreset({...preset,command:v})} placeholder='["my-agent", "--acp"]'/></${NL.Field}>${preset.backend==='acp'?html`<${NL.Field} label="Authentication method (optional)"><${NL.Input} value=${preset.auth_method||''} onInput=${v=>setPreset({...preset,auth_method:v})} placeholder="Agent default"/></${NL.Field}>`:null}<p class="muted small">Use the documented ACP command. Sign in through that agent. Test checks the protocol without sending a prompt.</p></details>
        <div class="row end"><${NL.Btn} small onClick=${()=>setEditing('')}>Cancel</${NL.Btn}><${NL.Btn} small onClick=${commitPreset}>Keep preset</${NL.Btn}></div></fieldset>`:null}</section>`:null}
      ${error?html`<p role="alert" class="note note-warn">${error}</p>`:null}${message?html`<p role="status" class="muted small">${message}</p>`:null}
      ${!onDraft?html`<div class="row end">${editing?html`<small class="muted">Keep or cancel the preset edit first.</small>`:null}<${NL.Btn} kind="primary" busy=${busy} disabled=${!!editing} onClick=${save}>Save agent choices</${NL.Btn}></div>`:null}
    </div>`;
  };
  NL.placeAgentPeek=(panel,anchor)=>{
    if(!panel||!anchor)return;
    if(panel.style.visibility==='visible'&&panel.matches(':hover,:focus-within'))return;
    const {x,y,width,height,visible}=anchor,w=panel.offsetWidth,h=panel.offsetHeight;
    const side=x+24+w<=width-12?'right':'left';
    const left=Math.max(12,Math.min(width-w-12,side==='right'?x+24:x-w-24));
    const top=Math.max(12,Math.min(height-h-72,y-h/2));
    panel.style.transform=`translate(${Math.round(left)}px,${Math.round(top)}px)`;
    panel.style.visibility=visible&&x>=0&&x<=width&&y>=0&&y<=height?'visible':'hidden';
  };
  NL.AgentPeek=({target,nodeRef,onClose,onFollow})=>{
    const s=NL.useLab(),[text,setText]=useState(''),[busy,setBusy]=useState(false);
    const assistant=target.kind==='assistant',agent=(s.agents||[]).find(a=>a.id===target.agent_id)||target.agent||{};
    const run=target.kind==='run'&&NL.run(s,target.id),sub=target.sub&&(run?.subagents||[]).find(a=>a.id===target.sub);
    const study=NL.item(s,agent.subject||agent.project||agent.idea||run?.subject);
    const title=assistant?'Workspace assistant':NL.agentTitle({...agent,run_id:run?.run_id||agent.run_id,parent:target.sub||agent.parent,label:agent.label||sub?.description},s);
    const role=agent.role||sub?.type||run?.role||'general',status=agent.status||sub?.status||run?.status||'idle';
    const doing=agent.doing?.summary||sub?.last_message||run?.external_activity?.current?.label||run?.last_action?.summary||agent.last||'';
    const outputs=ArloAgents.outputs(s,{...agent,run_id:run?.run_id||agent.run_id,sub:target.sub}),peers=assistant?[]:ArloAgents.peers(s,agent);
    const signal=ArloAgents.attention(s,agent);
    const live=run?.transport==='live'&&run.pid&&(NL.RUN_ACTIVE.has(run.status)||run.status==='waiting_input');
    const canMessage=run?.session_id&&!run.pending_question&&(live||run.status==='waiting_input'||NL.RUN_DONE.has(run.status));
    const details=()=>{onClose();if(assistant)NL.openAssistant();else if(target.kind==='run')NL.openRun(target.id,target.sub);else NL.openWorker(target.id)};
    const send=async()=>{
      if(!text.trim()||busy)return;setBusy(true);
      try{const message=(target.sub?'For subagent '+target.sub+' ('+role+'), via its parent: ':'')+text.trim();
        const result=await NL.act('/api/run/reply',{run_id:target.id,text:message},'Message sent');if(result.ok)setText('')}
      finally{setBusy(false)}
    };
    return html`<aside ref=${nodeRef} class="agent-peek" role="dialog" aria-modal="false" aria-label="Agent preview">
      <header><${NL.AgentAvatar} backend=${agent.backend||run?.backend} size=${26}/><div class="grow"><b>${NL.clip(title,70)}</b><small>${assistant?'Lab overview':NL.roleOf(role).label+' · '+(signal?.label||(run && !target.sub ? NL.runStateLabel(run) : NL.RUN_WORD[status]||status.replaceAll('_',' ')))}</small></div><button type="button" class="iconbtn sm" aria-label="Close agent preview" onClick=${onClose}>×</button></header>
      ${assistant?html`<p>Studies: ${(s.items||[]).length} · Inbox: ${(s.attention||[]).length}</p>`:html`${study?html`<a class="link small" href=${'#/study/'+study.id}>${study.title||study.id}</a>`:null}${doing?html`<p>${NL.clip(doing,180)}</p>`:null}`}
      ${study&&run?.workflow_node?html`<small class="muted">${NL.taskLabel(study,run.workflow_node)}${run.workflow_visit>1?' · pass '+run.workflow_visit:''}</small>`:null}
      ${outputs.slice(0,3).map(output=>html`<p><a class="link small" href=${'#/artifacts/'+output.id}>${output.title} ↗</a></p>`)}
      ${peers.length?html`<details class="agent-team"><summary>${peers.length} other${peers.length===1?'':'s'} on this task</summary>${peers.map(p=>html`<button type="button" class="link small" onClick=${()=>{onClose();NL.followAgent(p.id)}}>${NL.agentTitle(p,s)}</button>`)}</details>`:null}
      ${run?.pending_question?html`<button type="button" class="link small" onClick=${details}>Answer the agent’s question →</button>`:run?.pending_permissions?.length?html`<button type="button" class="link small" onClick=${details}>Review permission request →</button>`:null}
      ${run?.needs_followup?html`<button type="button" class="link small" onClick=${details}>Continue task →</button>`:null}
      ${canMessage?html`<label class="agent-peek-message">${target.sub?'Message via parent':'Message'}<textarea class="input" rows="2" aria-label="Message this agent" value=${text} onInput=${e=>setText(e.target.value)} onKeyDown=${e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();send()}}}/></label><div class="row end"><${NL.Btn} small disabled=${!text.trim()||busy} onClick=${send}>${busy?'Sending…':'Send'}</${NL.Btn}></div>`:target.kind==='worker'?html`<p class="muted small">Messages and questions stay in its terminal.</p>`:null}
      <footer>${!assistant?html`<${NL.Btn} small onClick=${onFollow}>Follow</${NL.Btn}>`:null}<${NL.Btn} small onClick=${details}>${assistant?'Open assistant':'Conversation'}</${NL.Btn}>${study?html`<a class="link small" href=${'#/study/'+study.id+'/history'}>History</a>`:null}</footer>
    </aside>`;
  };
  NL.AGENT_CHARACTERS = [{ id: 'newt', label: 'Newt' }, { id: 'human', label: 'Scientist' }, { id: 'robot', label: 'Robot' }];
  NL.AgentAvatar = ({ backend, size = 24 }) => {
    const cast = NL.prefs.cast || {}, choice = cast.mode === 'one' ? cast.one : cast[backend];
    const id = NL.AGENT_CHARACTERS.some(c => c.id === choice) ? choice : 'newt';
    return html`<svg class=${'agent-avatar avatar-' + id} width=${size} height=${size} viewBox="0 0 32 32" aria-hidden="true">
      ${id === 'robot' ? html`<path d="M16 3v4M12 3h8" /><rect x="6" y="8" width="20" height="19" rx="4" /><path d="M11 21h10M2 14v8m28-8v8" /><circle cx="12" cy="15" r="1.5" /><circle cx="20" cy="15" r="1.5" />`
        : id === 'human' ? html`<circle cx="16" cy="11" r="6" /><path d="M5 29v-5c0-5 5-7 11-7s11 2 11 7v5M13 19l3 6 3-6M5 12h22" />`
        : html`<path d="M7 14 2 10m5 9-5 3M25 14l5-4m-5 9 5 3" /><path d="M6 17c0-7 4-11 10-11s10 4 10 11-4 10-10 10S6 24 6 17Z" /><circle cx="12" cy="16" r="1" /><circle cx="20" cy="16" r="1" /><path d="M12 21q4 3 8 0" />`}</svg>`;
  };
})();
