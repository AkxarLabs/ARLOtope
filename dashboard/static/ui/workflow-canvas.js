/* One task definition, three views. No graph library or second editor data model. */
(function(){
  'use strict';
  const N=window.NL,{html,useState,useEffect,useRef}=N;
  const modes=[{value:'fresh',label:'New conversation'},{value:'continue',label:'Continue conversation'},{value:'native-fork',label:'Fork conversation'}];
  const list=v=>v==null?[]:Array.isArray(v)?v:[v];
  const destinations=n=>[...list(n.next),...Object.values(n.outcomes||{}).flatMap(list)];
  const TaskRoutes=({node,nodes,onChange})=>{
    const [name,setName]=useState('');
    return html`<fieldset><legend>Named outcomes</legend>${Object.entries(node.outcomes||{}).map(([key,to])=>html`<div class="row"><b>${key}</b><${N.Select} ariaLabel=${'Destination for '+key} value=${list(to)[0]||'end'} options=${[{value:'end',label:'End branch'},...nodes.map(n=>({value:n.id,label:n.label})),{value:'parked',label:'Park study'}]} onChange=${v=>onChange({...node.outcomes,[key]:v==='end'?[]:[v]})}/><button type="button" class="link" aria-label=${'Remove outcome '+key} onClick=${()=>onChange(Object.fromEntries(Object.entries(node.outcomes).filter(([k])=>k!==key)))}>×</button></div>`)}
    <div class="row"><${N.Input} value=${name} onInput=${setName} ariaLabel="New outcome name" placeholder="e.g. revise"/><${N.Btn} small disabled=${!name.trim()||['done','park','kill'].includes(name.trim())} onClick=${()=>{const key=name.toLowerCase().replace(/[^a-z0-9._-]+/g,'-').replace(/^-+|-+$/g,'');if(key){onChange({...node.outcomes,[key]:[]});setName('')}}}>Add</${N.Btn}></div></fieldset>`;
  };
  const defaults=[{value:'general',label:'General'},{value:'analyst',label:'Analyst'},{value:'reviewer',label:'Reviewer'},{value:'writer',label:'Writer'},{value:'designer',label:'Designer'}];
  function layout(nodes){
    const ranks=Object.fromEntries(nodes.map(n=>[n.id,0])),known=new Set(nodes.map(n=>n.id));
    const counts=Object.fromEntries(nodes.map(n=>[n.id,0])),seen=new Set();
    nodes.forEach(n=>destinations(n).forEach(t=>{if(known.has(t))counts[t]++}));
    const queue=nodes.filter(n=>!counts[n.id]).map(n=>n.id);
    while(seen.size<nodes.length){
      if(!queue.length)queue.push(nodes.find(n=>!seen.has(n.id)).id);
      const id=queue.shift();if(seen.has(id))continue;seen.add(id);
      destinations(nodes.find(n=>n.id===id)).forEach(t=>{if(known.has(t)&&!seen.has(t)){ranks[t]=Math.max(ranks[t],ranks[id]+1);if(!--counts[t])queue.push(t)}});
    }
    const rows={},places={},countsByRank={};
    nodes.forEach(n=>{const rank=ranks[n.id];countsByRank[rank]=(countsByRank[rank]||0)+1});
    const bands=Math.floor(Math.max(...Object.values(ranks))/3)+1,offsets=[22];
    for(let band=0;band<bands;band++)offsets[band+1]=offsets[band]+Math.max(1,...[0,1,2].map(col=>countsByRank[band*3+col]||0))*142+28;
    nodes.forEach(n=>{const rank=ranks[n.id],band=Math.floor(rank/3),col=band%2?2-rank%3:rank%3;
      places[n.id]={x:22+col*260,y:offsets[band]+(rows[rank]||0)*142};rows[rank]=(rows[rank]||0)+1});
    return {places,width:Math.max(480,...Object.values(places).map(p=>p.x+234)),height:Math.max(240,offsets[bands])};
  }
  N.WorkflowCanvas=({nodes,rooms=[],roles=[],skills=[],onChange,onCreateRoom,onDesignRoom,onCheckpoint,onEditSkill,onSave,onExport,dirty,tags=[],checkpoints=[]})=>{
    const [selected,setSelected]=useState(null),[view,setView]=useState(()=>matchMedia('(max-width:640px)').matches?'list':'flow'),[picked,setPicked]=useState([]),[room,setRoom]=useState(''),[roomName,setRoomName]=useState(''),[parallelFrom,setParallelFrom]=useState('');
    const node=nodes.find(n=>n.id===selected),{places,width,height}=layout(nodes);
    const branched=nodes.some((n,i)=>list(n.next).length>1||list(n.next).some(t=>nodes.findIndex(x=>x.id===t)<=i)||Object.keys(n.outcomes||{}).length);
    const scroll=useRef(),inspector=useRef(),[available,setAvailable]=useState(800),[zoom,setZoom]=useState(1),[query,setQuery]=useState('');
    const scale=zoom??Math.max(.15,Math.min(1,(available-24)/width,540/height));
    useEffect(()=>{const host=scroll.current;if(!host)return;const observer=new ResizeObserver(()=>setAvailable(host.clientWidth));observer.observe(host);return()=>observer.disconnect()},[view,!!node]);
    useEffect(()=>{if(!node||zoom===null)return;const host=scroll.current,p=places[node.id];if(host&&p)host.scrollTo({left:Math.max(0,p.x*scale-(host.clientWidth-212*scale)/2),top:Math.max(0,p.y*scale-40)})},[selected,view]);
    useEffect(()=>{if(node&&matchMedia('(max-width:760px)').matches)inspector.current?.scrollIntoView({block:'start',behavior:'instant'})},[selected]);
    const inspect=sid=>{setSelected(sid);if(zoom!==null&&zoom<.85)setZoom(1)};
    const closeInspector=()=>{setSelected(null);scroll.current?.querySelector(`[data-task="${selected}"] .wf-node-open`)?.focus()};

    const patch=(sid,fields)=>onChange(nodes.map(n=>n.id===sid?{...n,...fields}:n));
    const incoming=sid=>nodes.filter(n=>destinations(n).includes(sid));
    const connections=sid=>nodes.flatMap(n=>[
      ...(list(n.next).includes(sid)?[{value:n.id+':',source:n.id,outcome:'',label:n.label+' · done'}]:[]),
      ...Object.entries(n.outcomes||{}).filter(([,to])=>list(to).includes(sid)).map(([outcome])=>({value:n.id+':'+outcome,source:n.id,outcome,label:n.label+' · '+outcome}))]);
    const earlier=sid=>{const found=new Set(),pending=incoming(sid);while(pending.length){const n=pending.pop();if(found.has(n.id))continue;found.add(n.id);pending.push(...incoming(n.id))}return nodes.filter(n=>found.has(n.id)||n.id===sid)};
    const add=(parallel=false,anchor=node||nodes[nodes.length-1])=>{
      const base='task',taken=new Set(nodes.map(n=>n.id));let i=1;while(taken.has(base+'-'+i))i++;
      const edges=parallel?connections(anchor.id):[],connection=edges.length===1?edges[0]:edges.find(e=>e.value===parallelFrom);
      const sid=base+'-'+i,source=parallel?nodes.find(n=>n.id===connection?.source):anchor;
      if(parallel&&!source)return;
      const fresh={id:sid,label:'New task',procedure:'',instructions:'',outputs:[],tags:[],room:anchor?.room||rooms[0]?.id,
        agent:{role:'general'},context:{mode:'fresh',...(source?{handoff:true,from:source.id}:{})},next:parallel?list(anchor.next):list(source?.next)};
      const updated=nodes.map(n=>n.id===source?.id?(parallel&&connection.outcome?
        {...n,outcomes:{...n.outcomes,[connection.outcome]:[...new Set([...list(n.outcomes[connection.outcome]),sid])]}}:
        {...n,next:parallel?[...new Set([...list(n.next),sid])]:[sid]}):
        parallel&&list(anchor.next).includes(n.id)?{...n,join:true}:
        !parallel&&list(source?.next).includes(n.id)&&n.context?.from===source?.id?{...n,context:{...n.context,from:sid}}:n);
      onChange([...updated,fresh]);setSelected(sid);
    };
    const matches=n=>!query||[n.label,n.procedure,n.agent?.role,...(n.tags||[])].join(' ').toLowerCase().includes(query.toLowerCase());
    const card=n=>html`<article data-task=${n.id} class=${'wf-node '+(selected===n.id?'selected':'')+(matches(n)?'':' dimmed')} key=${n.id} style=${view==='flow'?{left:places[n.id].x+'px',top:places[n.id].y+'px'}:{}}>
      <label class="wf-pick"><input type="checkbox" aria-label=${'Group '+n.label} checked=${picked.includes(n.id)} onChange=${e=>setPicked(e.target.checked?[...picked,n.id]:picked.filter(x=>x!==n.id))}/></label>
      <button type="button" class="wf-node-open" title=${n.label} aria-label=${'Edit task: '+n.label} onClick=${()=>inspect(n.id)}><span class="wf-node-title">${n.label}</span><small>${skills.find(s=>s.value===n.procedure)?.label||n.procedure||'Own instructions'}</small>
      <span class="wf-agent"><i aria-hidden="true">${(n.agent?.role||'general').slice(0,1).toUpperCase()}</i>${n.agent?.role||'general'} · ${modes.find(m=>m.value===(n.context?.mode||'fresh'))?.label}</span>
      </button>
      <div class="wf-node-foot"><span>${rooms.find(r=>r.id===n.room)?.label||n.room||'Ungrouped'}${n.join?' · join':''}${n.tags?.length?' · '+n.tags.length+' tags':''}</span>
      ${checkpoints.filter(c=>c.before===n.id||c.during===n.id).map(c=>html`<button type="button" class="wf-gate" title=${(c.before?'Before: ':'During: ')+(c.title||c.id)} aria-label=${'Edit checkpoint: '+(c.title||c.id)} onClick=${()=>onCheckpoint?.(n.id,c)}>${c.before?'◇':'◈'}</button>`)}
      <button type="button" title="Add next task" aria-label=${'Add task after '+n.label} onClick=${()=>add(false,n)}}>+</button></div></article>`;
    const edge=(a,b,index,outcome,checkpoint)=>{
      if(!places[b])return null;const p=places[a],q=places[b],mode=nodes.find(n=>n.id===b)?.context?.mode||'fresh',same=list(nodes.find(n=>n.id===b)?.context?.from).includes(a);
      const kind=same&&mode==='continue'?'Continue':same&&mode==='native-fork'?'Fork':same&&(mode==='fork'||nodes.find(n=>n.id===b)?.context?.handoff)?'Handoff':mode!=='fresh'?'Wait':'New';
      const label=outcome?outcome.replaceAll('-',' ')+(checkpoint?'':' · '+kind):kind;
      const vertical=Math.abs(q.x-p.x)<30&&q.y>p.y,reverse=q.x<p.x;
      const x=vertical?p.x+106:reverse?p.x:p.x+212,y=vertical?p.y+116:p.y+50;
      const x2=vertical?q.x+106:reverse?q.x+212:q.x,y2=vertical?q.y:q.y+50,middle=(x+x2)/2;
      const path=a===b?`M${p.x+166},${p.y} C${p.x+212},${p.y-28} ${p.x+18},${p.y-28} ${p.x+46},${p.y}`:vertical?`M${x},${y} C${x},${(y+y2)/2} ${x2},${(y+y2)/2} ${x2},${y2}`:`M${x},${y} C${middle},${y} ${middle},${y2} ${x2},${y2}`;
      const activate=()=>checkpoint?onCheckpoint?.(a,checkpoint):inspect(a);
      return html`<g key=${a+'-'+b+'-'+(outcome||'done')} class=${'wf-edge '+(checkpoint?'gate':outcome?'outcome':kind==='Handoff'?'handoff':same?mode:'fresh')} role="button" tabindex="0" aria-label=${`${label}: ${nodes.find(n=>n.id===a)?.label} to ${nodes.find(n=>n.id===b)?.label}. Edit connection.`} onClick=${activate} onKeyDown=${e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}}}>
        <path d=${path} marker-end="url(#wf-arrow)"/><text x=${middle} y=${a===b?p.y-12:(y+y2)/2-9-index*14} text-anchor="middle">${label}</text></g>`;
    };
    return html`<section class=${'wf-canvas'+(scale<.85?' is-overview':'')} aria-label="Workflow designer"><header class="wf-toolbar"><div class="wf-map-tools"><${N.Input} ariaLabel="Find a task" value=${query} onInput=${setQuery} placeholder="Find a task or tag…"/><button type="button" class="btn btn-sm" onClick=${()=>{setSelected(null);setZoom(null)}}>Fit overview</button><button type="button" class="iconbtn sm" aria-label="Zoom out" onClick=${()=>setZoom(Math.max(.2,scale-.15))}>−</button><button type="button" class="wf-zoom" aria-label="Actual size" title="Actual size" onClick=${()=>setZoom(1)}>${Math.round(scale*100)}%</button><button type="button" class="iconbtn sm" aria-label="Zoom in" onClick=${()=>setZoom(Math.min(1.6,scale+.15))}>+</button></div><${N.Seg} value=${view} onChange=${setView} options=${[{value:'flow',label:'Flow'},{value:'rooms',label:'By room'},{value:'list',label:'Sequence'}]}/></header>
      ${picked.length?html`<div class="wf-group-bar"><b>${picked.length} selected</b><${N.Select} value=${room} onChange=${setRoom} options=${[{value:'',label:'Choose a room'},...rooms.map(r=>({value:r.id,label:r.label||r.id}))]}/><${N.Btn} small disabled=${!room} onClick=${()=>{onChange(nodes.map(n=>picked.includes(n.id)?{...n,room}:n));setPicked([])}}>Group in room</${N.Btn}>
      ${onCreateRoom?html`<${N.Input} value=${roomName} onInput=${setRoomName} placeholder="New room name"/><${N.Btn} small disabled=${!roomName.trim()} onClick=${async()=>{const id=await onCreateRoom(roomName,picked);if(id){onChange(nodes.map(n=>picked.includes(n.id)?{...n,room:typeof id==='string'?id:id.id}:n),typeof id==='object'?id:null);setPicked([]);setRoomName('')}}}>Create room & group</${N.Btn}>`:null}</div>`:null}
      <div class=${'wf-workbench'+(node?' has-inspector':'')}><div class="wf-map-scroll" ref=${scroll}>
      ${view==='flow'?html`<div class="wf-map-space" style=${{width:width*scale+'px',height:height*scale+'px'}}><div class="wf-map" style=${{width:width+'px',height:height+'px',transform:'scale('+scale+')'}}><svg class="wf-connectors" width=${width} height=${height} aria-label="Task connections"><defs><marker id="wf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="currentColor"/></marker></defs>${nodes.flatMap(n=>[...list(n.next).map((t,i)=>edge(n.id,t,i)),...Object.entries(n.outcomes||{}).flatMap(([name,to],i)=>list(to).map(t=>edge(n.id,t,i+1,name)))])}${checkpoints.flatMap(c=>Object.entries(c.decisions||{}).filter(([,to])=>to!=='continue').map(([name,to],i)=>edge(c.before||c.during,to,i+1,name,c)))}</svg>${nodes.map(card)}</div></div>`:
      view==='rooms'?html`<div class="wf-room-groups">${[...rooms,...(nodes.some(n=>!rooms.some(r=>r.id===n.room))?[{id:'',label:'Ungrouped'}]:[])].map(r=>{const grouped=nodes.filter(n=>r.id?n.room===r.id:!rooms.some(x=>x.id===n.room));return grouped.length?html`<section><header><h3>${r.label||r.id}</h3>${onDesignRoom&&r.id?html`<button type="button" class="link small" onClick=${()=>onDesignRoom(r.id)}>Design room</button>`:null}</header>${grouped.map(card)}</section>`:null})}</div>`:html`<div class="wf-list">${branched?html`<div class="note"><b>Branches</b><p>This workflow has parallel paths or loops.</p><button class="link" type="button" onClick=${()=>setView('flow')}>Edit in Flow</button></div>`:nodes.map(card)}</div>`}
      </div>${node?html`<aside ref=${inspector} class="wf-inspector" aria-label="Task inspector"><div class="wf-inspector-head"><b>${node.label}</b><button type="button" class="iconbtn sm" aria-label="Close task inspector" onClick=${closeInspector}>×</button></div>
      <${N.Field} label="Task name"><${N.Input} value=${node.label} onInput=${v=>patch(node.id,{label:v})}/></${N.Field}>
      <${N.Field} label="Skill / procedure"><${N.Select} value=${node.procedure||''} onChange=${v=>patch(node.id,{procedure:v})} options=${[{value:'',label:'Own instructions'},...skills]}/></${N.Field}>
      ${onEditSkill&&node.procedure?html`<button class="link small" onClick=${()=>onEditSkill(node.procedure)}>Edit reusable skill</button>`:null}
      <details open=${!!node.skills?.length}><summary>Skill sequence</summary>${(node.skills||[]).map((p,i)=>html`<div class="row"><span class="grow">${skills.find(s=>s.value===p)?.label||p}</span><button class="link" type="button" disabled=${i===0} aria-label=${'Move '+p+' up'} onClick=${()=>{const seq=[...node.skills];[seq[i-1],seq[i]]=[seq[i],seq[i-1]];patch(node.id,{skills:seq})}}>↑</button><button class="link" type="button" aria-label=${'Remove skill '+p} onClick=${()=>patch(node.id,{skills:node.skills.filter((_,j)=>i!==j)})}>×</button></div>`)}
      <${N.Select} value="" ariaLabel="Add skill to sequence" options=${[{value:'',label:'Add a skill…'},...skills]} onChange=${v=>{if(v)patch(node.id,{skills:[...(node.skills||[]),v]})}}/></details>
      <${N.Field} label="Task instructions"><${N.Textarea} rows=${4} value=${node.instructions||''} onInput=${v=>patch(node.id,{instructions:v})}/></${N.Field}>
      <${N.Field} label="Run this task as"><${N.Select} value=${node.agent?.role||'general'} options=${[...new Map([...defaults,...roles].map(r=>[r.value,r])).values()]} onChange=${v=>patch(node.id,{agent:{...node.agent,role:v},...(v==='reviewer'?{context:{mode:'fresh'}}:{})})}/></${N.Field}>
      <${N.AgentChoice} role=${node.agent?.role||'general'} value=${node.agent?.preset?'preset:'+node.agent.preset:node.agent?.backend?'backend:'+node.agent.backend:''} onChange=${v=>{const {model,effort,...agent}=node.agent||{};patch(node.id,{agent:{...agent,preset:v.startsWith('preset:')?v.slice(7):'',backend:v.startsWith('backend:')?v.slice(8):''}})}}/>
      <${N.Field} label="Agent context"><${N.Select} value=${node.context?.mode||'fresh'} options=${modes} onChange=${v=>patch(node.id,{context:{mode:v,...(v==='fresh'?{handoff:node.agent?.role!=='reviewer'&&!!incoming(node.id).length}:{ }),from:incoming(node.id)[0]?.id||''}})}/></${N.Field}>
      ${node.context?.mode==='fresh'&&incoming(node.id).length?html`<label class="wf-check"><input type="checkbox" checked=${!!node.context.handoff} onChange=${e=>patch(node.id,{context:{...node.context,handoff:e.target.checked,from:node.context.from||incoming(node.id)[0]?.id}})}/>Include a summary of prior work</label>`:null}
      ${(node.context?.mode||'fresh')!=='fresh'||node.context?.handoff?html`${node.context.mode==='fresh'?html`<fieldset><legend>Evidence from</legend>${earlier(node.id).filter(n=>n.id!==node.id).map(n=>html`<label class="wf-check"><input type="checkbox" checked=${list(node.context.from).includes(n.id)} onChange=${e=>patch(node.id,{context:{...node.context,from:e.target.checked?[...list(node.context.from),n.id]:list(node.context.from).filter(id=>id!==n.id)}})}/>${n.label}</label>`)}</fieldset>`:html`<${N.Field} label="Context from"><${N.Select} value=${node.context?.from||''} options=${[{value:'',label:'Select a source task'},...earlier(node.id).map(n=>({value:n.id,label:n.label+(n.id===node.id?' · previous visit':'')}))]} onChange=${v=>patch(node.id,{context:{...node.context,from:v,...(v===node.id?{initial:'fresh'}:{initial:undefined})}})}/></${N.Field}>`}
      <p class="wf-explainer">${node.context.mode==='continue'?'Next message in the source session. Only one branch can continue it.':node.context.mode==='native-fork'?'Copy the source conversation into a new agent. Requires native fork support.':'New session with a summary and evidence links. The full conversation is not cloned.'}</p>`:html`<p class="wf-explainer">New session with the role, instructions and required evidence. No prior conversation.</p>`}
      ${node.agent?.role==='reviewer'&&((node.context?.mode||'fresh')!=='fresh'||node.context?.handoff)?html`<p class="wf-explainer">This reviewer inherits prior work. Choose New conversation and turn off the summary for an independent review.</p>`:null}
      <${N.Field} label="Expected output files"><${N.Input} value=${(node.outputs||[]).join(', ')} placeholder="report.md, results.json" onInput=${v=>patch(node.id,{outputs:v.split(',').map(s=>s.trim()).filter(Boolean)})}/></${N.Field}>
      <${N.Field} label="Room"><${N.Select} value=${node.room||''} options=${rooms.map(r=>({value:r.id,label:r.label||r.id}))} onChange=${v=>patch(node.id,{room:v})}/></${N.Field}>
      <details class="wf-more"><summary>Connections & execution</summary><${N.Field} label="Task tags"><${N.TagInput} ariaLabel="Task tags" value=${node.tags||[]} onChange=${v=>patch(node.id,{tags:v})} suggestions=${tags}/></${N.Field}><fieldset><legend>Tasks after this one</legend>${nodes.map(n=>html`<label class="wf-check"><input type="checkbox" checked=${list(node.next).includes(n.id)} onChange=${e=>patch(node.id,{next:e.target.checked?[...list(node.next),n.id]:list(node.next).filter(x=>x!==n.id)})}/>${n.label}</label>`)}</fieldset>
      <label class="wf-check"><input type="checkbox" checked=${!!node.join} onChange=${e=>patch(node.id,{join:e.target.checked})}/>Wait for all incoming branches</label>
      <p class="wf-explainer">Use this for parallel work. Leave it off when alternative paths merge.</p>
      <${TaskRoutes} key=${node.id} node=${node} nodes=${nodes} onChange=${v=>patch(node.id,{outcomes:v})}/>
      <${N.Field} label="Maximum task visits"><${N.Input} type="number" value=${node.max_visits||''} onInput=${v=>patch(node.id,{max_visits:v?Number(v):undefined})} placeholder="Optional repetition limit"/></${N.Field}>
      <${N.Field} label="Model (optional)" hint="inherit uses the harness default"><${N.Input} value=${node.agent?.model===null?'inherit':node.agent?.model||''} placeholder="Agent preset" onInput=${v=>{const agent={...node.agent};if(v)agent.model=v==='inherit'?null:v;else delete agent.model;patch(node.id,{agent})}}/></${N.Field}>
      <${N.Field} label="Extra role instructions"><${N.Textarea} rows=${2} value=${node.agent?.instructions||''} onInput=${v=>patch(node.id,{agent:{...node.agent,instructions:v}})}/></${N.Field}></details>
      <details class="wf-templates"><summary>Task starting points</summary><div class="row">${[{label:'Literature',role:'analyst',skill:'lit-review'},{label:'Experiment',role:'general',skill:'experiment'},{label:'Analyze',role:'analyst',skill:'analyze'},{label:'Independent review',role:'reviewer',skill:'critique-paper'},{label:'Write',role:'writer',skill:'write-paper'}].map(t=>html`<${N.Btn} small onClick=${()=>patch(node.id,{label:t.label,agent:{...node.agent,role:t.role},...(node.procedure||node.instructions||node.skills?.length?{}:{procedure:t.skill}),...(t.role==='reviewer'?{context:{mode:'fresh'}}:{})})}>${t.label}</${N.Btn}>`)}<${N.Btn} small onClick=${()=>{const id=node.id+'-copy-'+Date.now().toString(36);onChange([...nodes,{...JSON.parse(JSON.stringify(node)),id,label:node.label+' copy',next:[],context:{mode:'fresh'}}]);setSelected(id)}}>Duplicate task</${N.Btn}></div><p class="muted small">Starting points fill a role and an empty skill; your instructions stay editable.</p></details>
      <div class="wf-add">${connections(node.id).length>1?html`<${N.Select} ariaLabel="Parallel source connection" value=${parallelFrom} onChange=${setParallelFrom} options=${[{value:'',label:'Choose a connection…'},...connections(node.id)]}/>`:null}<${N.Btn} small onClick=${()=>add()}>+ Next task</${N.Btn}><${N.Btn} small disabled=${!connections(node.id).length||connections(node.id).length>1&&!connections(node.id).some(e=>e.value===parallelFrom)} onClick=${()=>add(true)}>+ Parallel task</${N.Btn}>
      ${onCheckpoint?html`<${N.Btn} small onClick=${()=>onCheckpoint(node.id)}>+ Checkpoint</${N.Btn}>`:null}</div>
      <button type="button" class="link small wf-remove" disabled=${nodes.length<2} onClick=${()=>{onChange(nodes.filter(n=>n.id!==node.id).map(n=>({...n,next:list(n.next).filter(t=>t!==node.id),outcomes:Object.fromEntries(Object.entries(n.outcomes||{}).map(([k,v])=>[k,list(v).filter(t=>t!==node.id)])),context:list(n.context?.from).includes(node.id)?{mode:'fresh'}:n.context})));setSelected(nodes.find(n=>n.id!==node.id)?.id)}}>Remove task</button>
      </aside>`:null}</div>
      <footer class="wf-editor-foot"><span class="muted small">Continue · New agent · Fork · Handoff</span>${onExport?html`<${N.Btn} small disabled=${dirty} onClick=${onExport}>Download procedure</${N.Btn}>`:null}${onSave?html`<${N.Btn} kind="primary" disabled=${!dirty} onClick=${onSave}>Save composition to draft</${N.Btn}>`:null}</footer>
    </section>`;
  };
})();
