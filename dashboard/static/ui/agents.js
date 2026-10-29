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
  const CommandFields=({value=[],onChange})=>html`<${NL.Field} label="Program"><${NL.Input} value=${value[0]||''} onInput=${v=>onChange([v,...value.slice(1)])} placeholder="Executable name or path"/></${NL.Field}>
    <${NL.Field} label="Arguments" hint="One argument per line; keep spaces within an argument."><${NL.Textarea} rows=${2} value=${value.slice(1).join('\n')} onInput=${v=>onChange([value[0]||'',...v.split('\n')])} placeholder="e.g. acp"/></${NL.Field}>`;
  const cleanAgent=agent=>({...agent,...(agent.command?{command:[agent.command[0],...agent.command.slice(1).filter(x=>x.trim())]}:{})});
  const ApiProviderForm=({onSave,onCancel})=>{
    const [machine,setMachine]=useState(''),[provider,setProvider]=useState('openrouter'),[key,setKey]=useState(''),[model,setModel]=useState(''),[name,setName]=useState(''),[makeDefault,setDefault]=useState(false),[revision,setRevision]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState('');
    const machines=NL.useGet('/api/project-machines'),read=NL.useGet('/api/providers?'+NL.qs({machine}),revision),data=read.data||read.previous;
    const selected=data?.providers.find(p=>p.id===provider),models=(selected?.models||[]).filter(m=>m.tools!==false);
    const markClean=NL.useDirty(!!key||!!model||!!name);
    useEffect(()=>{setKey('');setModel('');setError('')},[provider,machine]);
    const refresh=async()=>{setBusy(true);setError('');const r=await NL.get('/api/providers?'+NL.qs({machine,refresh:'1'}));setBusy(false);if(r.error)setError(r.error);else setRevision(v=>v+1)};
    const save=async()=>{
      if(!model.trim()||!selected)return;setBusy(true);setError('');
      try{
        if(key.trim()){const r=await NL.api('/api/providers',{action:'connect',machine,provider,key:key.trim()});if(r.error)throw Error(r.error);setKey('');setRevision(v=>v+1)}
        else if(!selected.configured)throw Error('Enter a key or connect this provider in OpenCode.');
        const label=name.trim()||selected.name+' · '+model.trim();
        if(await onSave({label,backend:'opencode',model:provider+'/'+model.trim()},makeDefault))markClean();
      }catch(e){setError(e.message)}finally{setBusy(false)}
    };
    const disconnect=async()=>{if(!await NL.confirm({title:'Remove this provider connection?',body:'This removes OpenCode’s connection on the selected machine. Saved agents keep their model settings.',ok:'Remove connection',danger:true}))return;
      setBusy(true);const r=await NL.api('/api/providers',{action:'disconnect',provider,machine});setBusy(false);if(r.error)setError(r.error);else setRevision(v=>v+1)};
    return html`<fieldset class="agent-connect"><legend>API provider</legend><p class="muted small">API-backed agents use OpenCode. Keys stay in its credential store on the selected machine.</p>
      <${NL.Field} label="Machine"><${NL.Select} value=${machine} disabled=${busy} onChange=${setMachine} options=${[{value:'',label:'Lab machine'},...(machines.data?.machines||[]).map(m=>({value:m.id,label:m.name}))]}/></${NL.Field}>
      ${!data||read.error?html`<${NL.LoadState} ...${read} stale=${!!data}/>`:null}
      ${data?html`<${NL.Field} label="Provider"><${NL.Select} value=${provider} disabled=${busy} onChange=${setProvider} options=${data.providers.map(p=>({value:p.id,label:p.name+(p.configured?' · configured':'')}))}/></${NL.Field}>
      <${NL.Field} label="API key" hint=${selected?.configured?'Leave blank to keep the existing connection. A new key replaces it.':'Create a key with this provider.'}><input class="input" type="password" autocomplete="new-password" aria-label="API key" value=${key} disabled=${busy} onInput=${e=>setKey(e.target.value)}/></${NL.Field}>
      <${NL.Field} label="Model" hint="Choose a current catalog entry, or enter a model configured in OpenCode."><input class="input" list="api-provider-models" aria-label="Model" value=${model} disabled=${busy} onInput=${e=>setModel(e.target.value)} placeholder="Search models…"/><datalist id="api-provider-models">${models.map(m=>html`<option value=${m.id}>${m.name}</option>`)}</datalist></${NL.Field}>
      <div class="row wrap"><button type="button" class="link small" disabled=${busy} onClick=${refresh}>Refresh models</button><small class="muted">${data.source} · ${models.length} models</small></div>
      <${NL.Field} label="Agent name"><${NL.Input} value=${name} disabled=${busy} onInput=${setName} placeholder=${(selected?.name||provider)+' · '+(model||'model')}/></${NL.Field}>
      <label><input type="checkbox" checked=${makeDefault} disabled=${busy} onChange=${e=>setDefault(e.target.checked)}/> Make this the Lab default</label>
      ${selected?.configured?html`<button type="button" class="link small" disabled=${busy} onClick=${disconnect}>Remove provider connection</button>`:null}`:null}
      ${error?html`<p role="alert" class="note note-warn">${error}</p>`:null}
      <div class="row end"><${NL.Btn} disabled=${busy} onClick=${()=>{markClean();onCancel()}}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" busy=${busy} disabled=${!selected||!model.trim()||!key.trim()&&!selected.configured} onClick=${save}>Save agent</${NL.Btn}></div>
    </fieldset>`;
  };
  NL.AgentAssignments=({study,onDraft,value,connect})=>{
    const data=NL.useAgentSettings(study),[draft,setDraft]=useState(value||null),[editing,setEditing]=useState(''),[preset,setPreset]=useState({}),[error,setError]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[connection,setConnection]=useState(null);
    const checkSeq=NL.useRef(0);
    const [api,setApi]=useState(false);
    const savedDraft=NL.useRef(''),editBaseline=NL.useRef('');
    const draftDirty=!!draft&&JSON.stringify(draft)!==savedDraft.current;
    const markClean=NL.useDirty(!onDraft&&(draftDirty||!!editing&&JSON.stringify([editing,preset])!==editBaseline.current));
    const openPreset=(id,agent)=>{editBaseline.current=JSON.stringify([id,agent]);setEditing(id);setPreset(agent);setError('');setMessage('');setConnection(null)};
    useEffect(()=>{checkSeq.current++;setConnection(null);if(editing)setMessage('');setBusy(false)},[editing,preset.backend,JSON.stringify(preset.command)]);
    useEffect(()=>()=>{checkSeq.current++},[]);
    useEffect(()=>{if(data?.ok&&!draft){const initial=study?data.study:data.defaults;savedDraft.current=JSON.stringify(initial);setDraft(initial)}},[data,study]);
    useEffect(()=>{if(connect==='acp'&&data?.ok&&!study&&!onDraft){let id='acp-agent',i=2;while(data.presets.some(p=>p.id===id))id='acp-agent-'+i++;openPreset(id,{label:'',backend:'acp'})}},[connect,!!data?.ok]);
    if(data?.error&&!data.presets)return html`<${NL.LoadState} error=${data.error} reload=${data.reload} />`;
    if(!data||!draft)return html`<${NL.Spinner}/>`;
    const all=Object.fromEntries(data.presets.map(p=>[p.id,Object.fromEntries(Object.entries(p).filter(([k])=>!['id','found'].includes(k)))])),current=draft.presets||all;
    const choices=Object.entries(current).map(([id,p])=>({value:id,label:(p.label||id)+' · '+p.backend}));
    const change=v=>{setDraft(v);setMessage('');onDraft?.(v)};
    const setRole=(role,v)=>{const roles={...(draft.role_presets||{})};if(v==='@inherit')delete roles[role];else roles[role]=v==='@default'?null:v;change({...draft,role_presets:roles})};
    const save=async(next=draft)=>{setBusy(true);setError('');const body={settings:study?next:{...next,presets:next.presets||current},...(study?{study}:{})};const r=await NL.api('/api/agent-settings',body);setBusy(false);if(r.error)setError(r.error);else{agentCache.clear();const {presets,...saved}=next;savedDraft.current=JSON.stringify(saved);markClean();setDraft(saved);window.dispatchEvent(new Event('nl-agent-settings'));setMessage('Saved. Applies to new tasks.');NL.refresh()}return !r.error};
    const presetValue=()=>{const next=cleanAgent(preset);if(!next.command?.length||next.command.length===1&&!next.command[0].trim())delete next.command;if(!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/.test(editing))throw Error('Use a short ID with letters, numbers, dashes or underscores.');if(!next.label?.trim())throw Error('Name this agent.');return next};
    const begin=backend=>{let id=backend==='acp'?'acp-agent':'new-agent',i=2;while(current[id])id=(backend==='acp'?'acp-agent':'new-agent')+'-'+i++;openPreset(id,{label:'',backend})};
    const test=async agent=>{const request=++checkSeq.current;setBusy(true);setError('');setMessage('');setConnection(null);const r=await NL.api('/api/agent-settings/check',{agent:cleanAgent(agent)});if(request!==checkSeq.current)return;setBusy(false);setMessage(r.message||'');setError(r.error||'');if(r.connection)setConnection(r.connection)};
    return html`<div class="agent-assignments">
      ${data.error?html`<${NL.LoadState} error=${data.error} reload=${data.reload} stale />`:null}
      <${NL.Field} label=${study||onDraft?'Default agent':'Lab default agent'}><${NL.Select} value=${draft.default_preset||''} onChange=${v=>change({...draft,default_preset:v||null})} options=${[{value:'',label:'Use existing '+(study||onDraft?'Lab':'harness')+' settings'},...choices]}/></${NL.Field}>
      ${data.resolved?.general?html`<p class="muted small">Saved default: ${data.resolved.general.label||data.resolved.general.backend} · ${data.resolved.general.model||'tool’s model default'}</p>`:null}
      <details><summary>Task agent assignments <span class="muted small">${Object.keys(draft.role_presets||{}).length?'· '+NL.plural(Object.keys(draft.role_presets).length,'custom choice'):''}</span></summary><p class="muted small">Choose agents for task roles. Specialist child agents use the tool’s subagent settings.</p>
        <div class="agent-role-rows">${Object.entries(data.roles).map(([id,label])=>html`<${NL.Field} key=${id} label=${label}><${NL.Select} value=${Object.hasOwn(draft.role_presets||{},id)?draft.role_presets[id]??'@default':'@inherit'} onChange=${v=>setRole(id,v)} options=${[{value:'@inherit',label:study||onDraft?'Use Lab role setting':'Use general default'},...(study||onDraft?[{value:'@default',label:'Use study default'}]:[]),...choices]}/></${NL.Field}>`)}</div>
      </details>
      ${!study&&!onDraft?html`<section class="preset-list"><header class="row wrap"><h3 class="grow">Saved agents</h3><${NL.Btn} small disabled=${!!editing||api} onClick=${()=>setApi(true)}>Connect API provider</${NL.Btn}><${NL.Btn} small disabled=${!!editing||api} onClick=${()=>begin('acp')}>Connect ACP agent</${NL.Btn}><${NL.Btn} small kind="ghost" disabled=${!!editing||api} onClick=${()=>begin('codex')}>Add agent preset</${NL.Btn}></header>
        ${api?html`<${ApiProviderForm} onCancel=${()=>setApi(false)} onSave=${async(p,makeDefault)=>{let id='api-'+p.model.replace(/[^a-zA-Z0-9_-]/g,'-').slice(0,65),n=2,base=id;while(current[id])id=base+'-'+n++;const ok=await save({...draft,presets:{...current,[id]:p},...(makeDefault?{default_preset:id}:{})});if(ok)setApi(false);return ok;}}/>`:null}
        ${Object.entries(current).map(([id,p])=>html`<div class="preset-row"><div class="grow"><b>${p.label||id}</b><small class="muted">${p.backend}${p.model?' · '+p.model:''}</small></div><button class="link" disabled=${!!editing||busy||api} onClick=${()=>openPreset(id,{...p})}>Edit</button><button class="link" onClick=${()=>test(p)} disabled=${busy||!!editing||api}>Test</button><button class="link" disabled=${!!editing||busy||api} aria-label=${'Remove '+(p.label||id)} onClick=${()=>{const next={...current};delete next[id];change({...draft,presets:next})}}>Remove</button></div>`)}
        ${editing?html`<fieldset class="agent-connect"><legend>${preset.backend==='acp'?'Connect an ACP agent':'Agent preset'}</legend>
        <${NL.Field} label="Name"><${NL.Input} value=${preset.label||''} onInput=${v=>setPreset({...preset,label:v})} placeholder="e.g. My research agent" autofocus/></${NL.Field}>
        <${NL.Field} label="Agent type"><${NL.Select} value=${preset.backend} onChange=${v=>{setPreset({...preset,backend:v,model:'',effort:'',auth_method:''});setConnection(null)}} options=${[{value:'claude',label:'Claude'},{value:'codex',label:'Codex'},{value:'opencode',label:'opencode'},{value:'acp',label:'Other agent (ACP)'}]}/></${NL.Field}>
        ${preset.backend==='acp'?html`<${CommandFields} value=${preset.command} onChange=${v=>{setPreset({...preset,command:v});setConnection(null)}}/><p class="muted small">Use the agent’s ACP program. For <code>opencode acp</code>, enter <code>opencode</code> as the program and <code>acp</code> as its argument. Sign in through the agent’s own login.</p>`:null}
        <details><summary>Model & advanced settings</summary>
          <${NL.Field} label="Model" hint="Leave blank to use the agent’s default."><${NL.Input} value=${preset.model||''} onInput=${v=>setPreset({...preset,model:v})} placeholder="Agent default"/></${NL.Field}>
          ${['claude','codex'].includes(preset.backend)?html`<${NL.Field} label="Effort"><${NL.Select} value=${preset.effort||''} onChange=${v=>setPreset({...preset,effort:v})} options=${[{value:'',label:'Agent default'},'low','medium','high','xhigh','max']}/></${NL.Field}>`:null}
          ${preset.backend==='acp'?html`<${NL.Field} label="Sign-in method" hint="Check the connection to discover available methods. Leave blank if already signed in.">${connection?.authMethods?.length?html`<${NL.Select} value=${preset.auth_method||''} onChange=${v=>setPreset({...preset,auth_method:v})} options=${[{value:'',label:'Use existing sign-in'},...connection.authMethods.filter(m=>!m.type||m.type==='agent').map(m=>({value:m.id,label:m.name||m.id}))]}/>`:html`<${NL.Input} value=${preset.auth_method||''} onInput=${v=>setPreset({...preset,auth_method:v})} placeholder="Use existing sign-in"/>`}</${NL.Field}>`:
            html`<${CommandFields} value=${preset.command} onChange=${v=>setPreset({...preset,command:v})}/>`}
          <${NL.Field} label="Preset ID"><${NL.Input} value=${editing} disabled=${!!current[editing]} onInput=${setEditing}/></${NL.Field}>
        </details>
        ${connection?.agentInfo?html`<p class="muted small" role="status">Connected to ${connection.agentInfo.title||connection.agentInfo.name}${connection.agentInfo.version?' · '+connection.agentInfo.version:''}</p>`:null}
        <div class="row end wrap"><${NL.Btn} small onClick=${()=>{markClean(draftDirty);setEditing('');setMessage('');setError('');if(connect)NL.go('settings/agents')}}>Cancel</${NL.Btn}><${NL.Btn} small busy=${busy} onClick=${()=>test({...preset})}>Check connection</${NL.Btn}><${NL.Btn} small kind="primary" busy=${busy} onClick=${async()=>{try{const next={...draft,presets:{...current,[editing]:presetValue()}};if(await save(next)){setEditing('');if(connect)NL.go('settings/agents')}}catch(e){setError(e.message)}}}>Save agent</${NL.Btn}></div></fieldset>`:null}</section>`:null}
      ${error?html`<p role="alert" class="note note-warn">${error}</p>`:null}${message?html`<p role="status" class="muted small">${message}</p>`:null}
      ${!onDraft&&!editing&&!api?html`<div class="row end"><${NL.Btn} kind="primary" busy=${busy} onClick=${()=>save()}>Save agent choices</${NL.Btn}></div>`:null}
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
      try{const message=ArloAgents.message(text,target.sub,role);
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
      ${canMessage?html`<label class="agent-peek-message">${target.sub?'Message via parent':'Message'}<textarea class="input" rows="2" aria-label="Message this agent" value=${text} onInput=${e=>setText(e.target.value)} onKeyDown=${e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();send()}}}/></label><div class="row end"><${NL.Btn} small disabled=${!text.trim()||busy} onClick=${send}>${busy?'Sending…':'Send'}</${NL.Btn}></div>`:target.kind==='worker'?html`<p class="muted small">Direct messages stay in its terminal.</p>`:null}
      <footer>${!assistant?html`<${NL.Btn} small onClick=${()=>{onClose();if(run)NL.askAboutRun(run,target.sub||'');else NL.openAssistant({initialStudy:study?.id||'',initialText:'Help me understand terminal agent '+(agent.worker_id||target.id)+'.',initialScope:true})}}>Ask assistant</${NL.Btn}>`:null}${!assistant?html`<${NL.Btn} small onClick=${onFollow}>Follow</${NL.Btn}>`:null}<${NL.Btn} small onClick=${details}>${assistant?'Open assistant':'Conversation'}</${NL.Btn}>${study?html`<a class="link small" href=${'#/study/'+study.id+'/history'}>History</a>`:null}</footer>
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
