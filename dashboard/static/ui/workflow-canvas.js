/* One task definition, three views. No graph library or second editor data model. */
(function(){
  'use strict';
  const N=window.NL,{html,useState,useEffect,useRef}=N;
  const modes=[{value:'fresh',label:'New conversation'},{value:'continue',label:'Continue conversation'},{value:'native-fork',label:'Fork conversation'}];
  const list=v=>v==null?[]:Array.isArray(v)?v:[v];
  N.requiredFrameworks=w=>w.requires||[...new Set(Object.values(w.nodes||{}).map(n=>n.external?.framework).filter(Boolean))];
  N.frameworkBlocked=(w,data)=>N.requiredFrameworks(w).some(id=>!data?.frameworks?.find(f=>f.id===id)?.available);
  N.FrameworkTools=({read,machine='',onMachine,onInspect})=>{
    const s=N.useLab(),items=read.data?.frameworks||[];
    return html`<details class="process-agent"><summary>Research tools</summary>
      <p class="muted small">Installed separately on the execution machine. Their phases connect to ordinary tasks and checkpoints.</p>
      ${onMachine?html`<${N.Field} label="Execution machine"><${N.Select} value=${machine} onChange=${onMachine} options=${[{value:'',label:'This machine'},...(s.machines||[]).filter(m=>m.id&&m.id!=='local'&&m.kind!=='local').map(m=>({value:m.id,label:m.label||m.name||m.id}))]}/></${N.Field}>`:null}
      ${!read.data||read.error?html`<${N.LoadState} ...${read}/>`:items.map(f=>html`<div class=${N.cls('framework-tool',!f.available&&'unavailable')} key=${f.id}><b>${f.title}</b><span class="muted small">${f.reason}</span><a class="link small" href=${f.setup} target="_blank" rel="noopener noreferrer">Setup guide ↗</a>${onInspect?html`<button type="button" class="link small" onClick=${()=>onInspect(f.id)}>Inspect workflow</button>`:null}</div>`)}
      <${N.Btn} small onClick=${read.reload}>Check again</${N.Btn}>
    </details>`;
  };
  const destinations=n=>[...list(n.next),...Object.values(n.outcomes||{}).flatMap(list)];
  // Removed dependencies cannot leave a task continuing an unrelated conversation.
  const cleanSources=nodes=>nodes.map(n=>{
    if(!n.context?.from)return n;
    const allowed=new Set(),pending=nodes.filter(s=>destinations(s).includes(n.id));
    while(pending.length){const source=pending.pop();if(allowed.has(source.id))continue;allowed.add(source.id);pending.push(...nodes.filter(s=>destinations(s).includes(source.id)))}
    if(n.context.initial==='fresh')allowed.add(n.id);
    const from=list(n.context.from).filter(id=>allowed.has(id));
    return {...n,context:!from.length?{mode:'fresh'}:{...n.context,from:Array.isArray(n.context.from)?from:from[0]}};
  });
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
    const bands=Math.floor(Math.max(...Object.values(ranks))/3)+1,offsets=[36];
    for(let band=0;band<bands;band++)offsets[band+1]=offsets[band]+Math.max(1,...[0,1,2].map(col=>countsByRank[band*3+col]||0))*142+28;
    nodes.forEach(n=>{const rank=ranks[n.id],band=Math.floor(rank/3),col=band%2?2-rank%3:rank%3;
      places[n.id]={x:22+col*260,y:offsets[band]+(rows[rank]||0)*142};rows[rank]=(rows[rank]||0)+1});
    return {places,width:Math.max(480,...Object.values(places).map(p=>p.x+234)),height:Math.max(240,offsets[bands])};
  }
  N.workflowNodes=w=>w.tasks||(w.path||w.steps||[]).map((id,i,ids)=>({id,label:N.STEPS[id]?.label||id,
    agent:N.STEPS[id]?.agent||{},next:ids.slice(i+1,i+2),outcomes:w.routes?.[id]||{},...w.nodes?.[id]}));
  N.WorkflowPicker=({workflows,value,onChange,blocked=()=>false,label='Workflow'})=>{
    const selected=workflows.find(w=>w.id===value);
    return html`<details class="workflow-picker"><summary><span>${label}</span><b>${selected?.title||selected?.id||'Choose a workflow'}</b><small>${selected?N.plural(N.workflowNodes(selected).length,'task')+' · '+N.plural((selected.checkpoints||[]).length,'checkpoint')+' · ':''}Change workflow</small></summary><fieldset><legend>Choose a workflow</legend>
    <div role="radiogroup" aria-label=${label} onKeyDown=${e=>{
      const buttons=[...e.currentTarget.querySelectorAll('button:not(:disabled)')],index=buttons.indexOf(e.target),direction={ArrowRight:1,ArrowDown:1,ArrowLeft:-1,ArrowUp:-1}[e.key];
      if(index<0||!direction&&e.key!=='Home'&&e.key!=='End')return;
      e.preventDefault();const next=buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(index+direction+buttons.length)%buttons.length];next.focus();next.click();
    }}>${workflows.map(w=>html`<button type="button" role="radio" aria-checked=${w.id===value} tabindex=${w.id===(workflows.find(w=>w.id===value&&!blocked(w))||workflows.find(w=>!blocked(w)))?.id?0:-1} disabled=${blocked(w)} onClick=${()=>onChange(w.id)}>
      <span aria-hidden="true" class="workflow-choice-icon">${N.requiredFrameworks(w).length?'↗':N.workflowNodes(w).some(n=>list(n.next).length>1)?'⑂':'→'}</span>
      <span><b>${w.title||w.id}</b><small>${N.plural(N.workflowNodes(w).length,'task')} · ${N.plural((w.checkpoints||[]).length,'checkpoint')}${blocked(w)?' · setup needed':''}</small></span></button>`)}</div></fieldset></details>`;
  };
  N.WorkflowOverview=({workflow,entry,onSelect,selected,ready=[],completed=[]})=>{
    const [detail,setDetail]=useState(null),nodes=N.workflowNodes(workflow);
    if(!nodes.length)return html`<p class="muted small">No tasks yet.</p>`;
    const {places,width,height}=layout(nodes);
    const choose=id=>{setDetail(detail===id?null:id);onSelect?.(id)};
    const active=selected??detail,node=nodes.find(n=>n.id===active),checkpoints=workflow.checkpoints||[];
    const state=n=>completed.includes(n.id)?'completed':ready.includes(n.id)?'ready':entry?.tasks?.[n.id]?.action||'';
    const caption=n=>({reuse:'Existing work',omit:'Skipped at start',ready:'Ready',completed:'Done'})[state(n)]||(n.agent?.role&&n.agent.role!=='general'?n.agent.role:'agent');
    const edges=nodes.flatMap(n=>destinations(n).filter(t=>places[t]).map(t=>{
      const p=places[n.id],q=places[t],reverse=q.x<p.x,vertical=q.x===p.x;
      const down=q.y>p.y,x=p.x+(vertical?106:reverse?0:212),y=p.y/2+24+(vertical?(down?49:0):24),x2=q.x+(vertical?106:reverse?212:0),y2=q.y/2+24+(vertical?(down?0:49):24);
      const back=nodes.findIndex(x=>x.id===t)<=nodes.indexOf(n),top=Math.min(p.y,q.y)/2;
      const path=back?`M${p.x+146},${p.y/2+24} C${p.x+146},${top-4} ${q.x+66},${top-4} ${q.x+66},${q.y/2+24}`:`M${x},${y} C${(x+x2)/2},${y} ${(x+x2)/2},${y2} ${x2},${y2}`;
      return html`<path key=${n.id+'-'+t} d=${path} marker-end="url(#overview-arrow)"><title>${n.label+' → '+nodes.find(n=>n.id===t)?.label}</title></path>`;
    }));
    const text=n=>html`<b>${n.label}</b><small>${caption(n)}${checkpoints.some(c=>c.before===n.id||c.during===n.id)?' · ◇ checkpoint':''}</small>`;
    return html`<section class="workflow-overview" aria-label=${(workflow.title||'Workflow')+' preview'}>
      <svg class="workflow-mini-map" viewBox=${`0 0 ${width} ${height/2+34}`} role="group" aria-label="Workflow connections">
        <defs><marker id="overview-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z"/></marker></defs>
        <g class="overview-edges">${edges}</g>${nodes.map((n,i)=>html`<g key=${n.id} class=${'overview-task '+state(n)+(active===n.id?' selected':'')} role="button" tabindex="0" aria-label=${'Inspect task: '+n.label}
          transform=${`translate(${places[n.id].x},${places[n.id].y/2+24})`} onClick=${()=>choose(n.id)} onKeyDown=${e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(n.id)}}}>
          <title>${n.label}${checkpoints.filter(c=>c.before===n.id||c.during===n.id).map(c=>' · '+c.title).join('')}</title><rect width="212" height="49" rx="5"/>
          <text x="10" y="20">${String(i+1).padStart(2,'0')} ${n.label.length>23?n.label.slice(0,22)+'…':n.label}</text>
          <text class="overview-meta" x="10" y="38">${caption(n)}${checkpoints.some(c=>c.before===n.id||c.during===n.id)?' · ◇ checkpoint':''}</text></g>`)}
      </svg>
      <ol class="workflow-mini-list">${nodes.map(n=>html`<li><button type="button" aria-label=${'Inspect task: '+n.label} class=${state(n)+(active===n.id?' selected':'')} onClick=${()=>choose(n.id)}>${text(n)}</button>
        <small>${destinations(n).length?'→ '+destinations(n).map(t=>nodes.find(x=>x.id===t)?.label||t).join(' / '):'End'}</small></li>`)}</ol>
      ${node&&!onSelect?html`<div class="workflow-task-note"><b>${node.label}</b><p>${node.instructions||N.PROC[node.procedure]?.description||'Follow the task’s skill and written instructions.'}</p>
        <small>${node.external?'Tool: '+node.external.framework+' · '+node.external.phase.replaceAll('_',' '):modes.find(m=>m.value===(node.context?.mode||'fresh'))?.label||'New conversation'}${node.join?' · Wait for all branches':''}${node.outputs?.length?' · Outputs: '+node.outputs.join(', '):''}</small>
        ${Object.keys(node.outcomes||{}).length?html`<small>${Object.entries(node.outcomes).map(([name,to])=>name+' → '+list(to).map(t=>nodes.find(n=>n.id===t)?.label||t).join(', ')).join(' · ')}</small>`:null}
        ${checkpoints.filter(c=>c.before===node.id||c.during===node.id).map(c=>html`<p>◇ ${c.title}</p>`)}</div>`:null}
    </section>`;
  };
  N.WorkflowCanvas=({nodes,rooms=[],roles=[],skills=[],frameworks=[],onChange:onNodesChange,onCreateRoom,onDesignRoom,onCheckpoint,onEditSkill,onSave,onExport,dirty,tags=[],checkpoints=[]})=>{
    const [selected,setSelected]=useState(null),[view,setView]=useState(()=>matchMedia('(max-width:640px)').matches?'list':'flow'),[picked,setPicked]=useState([]),[room,setRoom]=useState(''),[roomName,setRoomName]=useState(''),[parallelFrom,setParallelFrom]=useState('');
    const node=nodes.find(n=>n.id===selected),{places,width,height}=layout(nodes);
    const branched=nodes.some((n,i)=>list(n.next).length>1||list(n.next).some(t=>nodes.findIndex(x=>x.id===t)<=i)||Object.keys(n.outcomes||{}).length);
    const scroll=useRef(),inspector=useRef(),[available,setAvailable]=useState(800),[zoom,setZoom]=useState(null),[query,setQuery]=useState('');
    const [wire,setWire]=useState(null),[connection,setConnection]=useState(null),[history,setHistory]=useState([]),gesture=useRef(null);
    const onChange=updated=>{if(JSON.stringify(updated)===JSON.stringify(nodes))return;setHistory(h=>[...h.slice(-29),nodes]);onNodesChange(updated)};
    const undo=()=>{if(!history.length)return;onNodesChange(history[history.length-1]);setHistory(history.slice(0,-1));setSelected(null);setConnection(null);setWire(null);scroll.current?.focus({preventScroll:true})};
    const scale=zoom??Math.max(.15,Math.min(1,(available-24)/width,540/height));
    useEffect(()=>{const host=scroll.current;if(!host)return;const observer=new ResizeObserver(()=>setAvailable(host.clientWidth));observer.observe(host);return()=>observer.disconnect()},[view,!!node]);
    useEffect(()=>{if(!node||zoom===null)return;const host=scroll.current,p=places[node.id];if(host&&p)host.scrollTo({left:Math.max(0,p.x*scale-(host.clientWidth-212*scale)/2),top:Math.max(0,p.y*scale-40)})},[selected,view]);
    useEffect(()=>{if(node&&matchMedia('(max-width:760px)').matches)inspector.current?.scrollIntoView({block:'start',behavior:'instant'})},[selected]);
    useEffect(()=>{setWire(null);gesture.current=null},[view]);
    useEffect(()=>{if(connection)scroll.current?.querySelector(`[data-connection="${connection.source}:${connection.outcome}:${connection.target}"]`)?.focus({preventScroll:true})},[connection]);
    const inspect=sid=>{setSelected(sid);setConnection(null);if(zoom!==null&&zoom<.85)setZoom(1)};
    const closeInspector=()=>{setSelected(null);scroll.current?.querySelector(`[data-task="${selected}"] .wf-node-open`)?.focus()};

    const patch=(sid,fields)=>onChange(nodes.map(n=>n.id===sid?{...n,...fields}:n));
    const removeTask=()=>{
      if(!node||nodes.length<2)return;
      onChange(cleanSources(nodes.filter(n=>n.id!==node.id).map(n=>({...n,next:list(n.next).filter(t=>t!==node.id),
        outcomes:Object.fromEntries(Object.entries(n.outcomes||{}).map(([k,v])=>[k,list(v).filter(t=>t!==node.id)]))}))));
      setPicked(picked.filter(id=>id!==node.id));setSelected(null);setWire(null);scroll.current?.focus({preventScroll:true});
    };
    const disconnect=()=>{
      if(!connection)return;
      const {source,target,outcome}=connection,n=nodes.find(n=>n.id===source);
      const fields=outcome?{outcomes:{...n.outcomes,[outcome]:list(n.outcomes[outcome]).filter(id=>id!==target)}}:{next:list(n.next).filter(id=>id!==target)};
      onChange(cleanSources(nodes.map(n=>n.id===source?{...n,...fields}:n)));
      setConnection(null);
      scroll.current?.focus({preventScroll:true});
    };
    const connect=(source,target)=>{
      if(!nodes.some(n=>n.id===source)||!nodes.some(n=>n.id===target))return;
      const n=nodes.find(n=>n.id===source);
      patch(source,{next:[...new Set([...list(n.next),target])]});
      setWire(null);setSelected(null);setConnection({source,target,outcome:''});
    };
    const point=e=>{const rect=scroll.current.querySelector('.wf-map').getBoundingClientRect();return {x:(e.clientX-rect.left)/scale,y:(e.clientY-rect.top)/scale}};
    const startWire=(e,source)=>{
      if(e.button!==0)return;e.preventDefault();e.stopPropagation();
      const p=places[source],start={source,x:p.x+212,y:p.y+50,target:null};
      gesture.current={...start,clientX:e.clientX,clientY:e.clientY,moved:false};setWire(start);
      e.currentTarget.setPointerCapture(e.pointerId);
    };
    const moveWire=e=>{
      const drag=gesture.current;if(!drag)return;
      drag.moved ||= Math.hypot(e.clientX-drag.clientX,e.clientY-drag.clientY)>4;
      drag.target=document.elementFromPoint(e.clientX,e.clientY)?.closest('[data-task]')?.dataset.task||null;
      setWire({source:drag.source,...point(e),target:drag.moved?drag.target:null});
    };
    const endWire=e=>{
      const drag=gesture.current;if(!drag)return;gesture.current=null;
      if(drag.moved){if(drag.target)connect(drag.source,drag.target);else setWire(null)}
      e.currentTarget.releasePointerCapture(e.pointerId);
    };
    const keyDown=e=>{
      if(e.target.closest('input,textarea,select,[contenteditable],[role="combobox"]'))return;
      if(e.key==='Escape'){gesture.current=null;setWire(null);setConnection(null);setSelected(null);return}
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!e.shiftKey){e.preventDefault();undo();return}
      if((e.key==='Delete'||e.key==='Backspace')&&!e.target.closest('.wf-inspector')){e.preventDefault();connection?disconnect():removeTask()}
    };
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
      const position=source?updated.findIndex(n=>n.id===source.id)+1:updated.length;
      onChange([...updated.slice(0,position),fresh,...updated.slice(position)]);setSelected(sid);
    };
    const matches=n=>!query||[n.label,n.procedure,n.external?.framework,n.external?.phase,n.agent?.role,...(n.tags||[])].join(' ').toLowerCase().includes(query.toLowerCase());
    const card=n=>html`<article data-task=${n.id} class=${'wf-node '+(selected===n.id?'selected':'')+(wire?.target===n.id?' drop-target':'')+(matches(n)?'':' dimmed')} key=${n.id} style=${view==='flow'?{left:places[n.id].x+'px',top:places[n.id].y+'px'}:{}}>
      ${view==='flow'?html`<button type="button" class="wf-port wf-port-in" aria-label=${'Connect to '+n.label} title="End a connection here" onClick=${()=>{if(wire)connect(wire.source,n.id)}}>◦</button><button type="button" class="wf-port wf-port-out" aria-label=${'Connect from '+n.label} title="Drag to another task, or click then choose its input" onPointerDown=${e=>startWire(e,n.id)} onPointerMove=${moveWire} onPointerUp=${endWire} onPointerCancel=${()=>{gesture.current=null;setWire(null)}} onKeyDown=${e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setWire({source:n.id,x:places[n.id].x+212,y:places[n.id].y+50})}}}>+</button>`:null}
      <label class="wf-pick"><input type="checkbox" aria-label=${'Group '+n.label} checked=${picked.includes(n.id)} onChange=${e=>setPicked(e.target.checked?[...picked,n.id]:picked.filter(x=>x!==n.id))}/></label>
      <button type="button" class="wf-node-open" title=${n.label} aria-label=${'Edit task: '+n.label} onClick=${()=>inspect(n.id)}><span class="wf-node-title">${n.label}</span><small>${n.external?n.external.framework+' · '+n.external.phase.replaceAll('_',' '):skills.find(s=>s.value===n.procedure)?.label||n.procedure||'Instructions only'}</small>
      <span class="wf-agent"><i aria-hidden="true">${(n.agent?.role||'general').slice(0,1).toUpperCase()}</i>${n.agent?.role||'general'} · ${modes.find(m=>m.value===(n.context?.mode||'fresh'))?.label}</span>
      </button>
      <div class="wf-node-foot"><span>${rooms.find(r=>r.id===n.room)?.label||n.room||'Ungrouped'}${n.join?' · join':''}${n.tags?.length?' · '+n.tags.length+' tags':''}</span>
      ${checkpoints.filter(c=>c.before===n.id||c.during===n.id).map(c=>html`<button type="button" class="wf-gate" title=${(c.before?'Before: ':'During: ')+(c.title||c.id)} aria-label=${'Edit checkpoint: '+(c.title||c.id)} onClick=${()=>onCheckpoint?.(n.id,c)}>${c.before?'◇':'◈'}</button>`)}
      <button type="button" title="Add next task" aria-label=${'Add task after '+n.label} onClick=${()=>add(false,n)}>+</button></div></article>`;
    const edge=(a,b,index,outcome,checkpoint)=>{
      if(!places[a]||!places[b])return null;const p=places[a],q=places[b],mode=nodes.find(n=>n.id===b)?.context?.mode||'fresh',same=list(nodes.find(n=>n.id===b)?.context?.from).includes(a);
      const kind=same&&mode==='continue'?'Continue':same&&mode==='native-fork'?'Fork':same&&nodes.find(n=>n.id===b)?.context?.handoff?'Handoff':mode!=='fresh'?'Wait':'New';
      const label=outcome?outcome.replaceAll('-',' ')+(checkpoint?'':' · '+kind):kind;
      const x=p.x+212,y=p.y+50,x2=q.x,y2=q.y+50,middle=(x+x2)/2;
      const direct=q.y===p.y&&q.x-p.x===260,lane=Math.max(16,p.y-14-index*12);
      const caption=outcome?outcome.replaceAll('-',' '):kind==='New'?'':kind;
      // Travel in the gutters so a long connection cannot disappear behind another task.
      const path=direct?`M${x},${y} L${x2},${y2}`:
        `M${x},${y} L${x+18},${y} L${x+18},${lane} L${x2-18},${lane} L${x2-18},${y2} L${x2},${y2}`;
      const activate=()=>{if(checkpoint){onCheckpoint?.(a,checkpoint);return}setSelected(null);setConnection({source:a,target:b,outcome:outcome||''})};
      const active=connection?.source===a&&connection?.target===b&&connection?.outcome===(outcome||'');
      return html`<g key=${a+'-'+b+'-'+(outcome||'done')} data-connection=${checkpoint?'':`${a}:${outcome||''}:${b}`} class=${'wf-edge '+(active?'selected ':'')+(checkpoint?'gate':outcome?'outcome':kind==='Handoff'?'handoff':same?mode:'fresh')} role="button" tabindex="0" aria-pressed=${active} aria-label=${`${label}: ${nodes.find(n=>n.id===a)?.label} to ${nodes.find(n=>n.id===b)?.label}. Edit connection.`} onClick=${activate} onKeyDown=${e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate()}}}>
        <path class="wf-edge-hit" d=${path}/><path d=${path} marker-end="url(#wf-arrow)"/>${caption?html`<text x=${direct?middle:p.x+106} y=${direct?y-9-index*14:lane-5} text-anchor="middle">${caption}</text>`:null}</g>`;
    };
    return html`<section class=${'wf-canvas'+(scale<.85?' is-overview':'')} aria-label="Workflow designer" onKeyDown=${keyDown}><header class="wf-toolbar"><div class="wf-map-tools"><${N.Input} ariaLabel="Find a task" value=${query} onInput=${setQuery} placeholder="Find a task or tag…"/><button type="button" class="btn btn-sm" onClick=${()=>{setSelected(null);setConnection(null);setZoom(null)}}>Fit overview</button><button type="button" class="iconbtn sm" aria-label="Zoom out" onClick=${()=>setZoom(Math.max(.2,scale-.15))}>−</button><button type="button" class="wf-zoom" aria-label="Actual size" title="Actual size" onClick=${()=>setZoom(1)}>${Math.round(scale*100)}%</button><button type="button" class="iconbtn sm" aria-label="Zoom in" onClick=${()=>setZoom(Math.min(1.6,scale+.15))}>+</button></div><${N.Seg} value=${view} onChange=${setView} options=${[{value:'flow',label:'Flow'},{value:'rooms',label:'By room'},{value:'list',label:'List'}]}/></header>
      <div class="wf-edit-bar"><span role="status">${wire?'Choose a task to connect to. Escape cancels.':connection?`${nodes.find(n=>n.id===connection.source)?.label} → ${nodes.find(n=>n.id===connection.target)?.label} · ${connection.outcome||'done'}`:view==='rooms'?'Rooms are shared spaces. Tasks in the same room can belong to different studies.':'Drag + to another task to connect. Select a task or arrow, then Delete to remove.'}</span><button type="button" class="link small" disabled=${!history.length} onClick=${undo}>Undo</button>${connection?html`<button type="button" class="link small" onClick=${disconnect}>Disconnect</button>`:null}<button type="button" class="btn btn-sm" onClick=${()=>add(false,null)}>+ Task</button></div>
      ${picked.length?html`<div class="wf-group-bar"><b>${picked.length} selected</b><${N.Select} value=${room} onChange=${setRoom} options=${[{value:'',label:'Choose a room'},...rooms.map(r=>({value:r.id,label:r.label||r.id}))]}/><${N.Btn} small disabled=${!room} onClick=${()=>{onChange(nodes.map(n=>picked.includes(n.id)?{...n,room}:n));setPicked([])}}>Group in room</${N.Btn}>
      ${onCreateRoom?html`<${N.Input} value=${roomName} onInput=${setRoomName} placeholder="New room name"/><${N.Btn} small disabled=${!roomName.trim()} onClick=${async()=>{const id=await onCreateRoom(roomName,picked);if(id){onChange(nodes.map(n=>picked.includes(n.id)?{...n,room:typeof id==='string'?id:id.id}:n),typeof id==='object'?id:null);setPicked([]);setRoomName('')}}}>Create room & group</${N.Btn}>`:null}</div>`:null}
      <div class=${'wf-workbench'+(node?' has-inspector':'')}><div class="wf-map-scroll" ref=${scroll} tabindex="-1" aria-label="Workflow map">
      ${view==='flow'?html`<div class="wf-map-space" style=${{width:width*scale+'px',height:height*scale+'px'}}><div class="wf-map" style=${{width:width+'px',height:height+'px',transform:'scale('+scale+')'}}><svg class="wf-connectors" width=${width} height=${height} aria-label="Task connections"><defs><marker id="wf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10z" fill="currentColor"/></marker></defs>${nodes.flatMap(n=>[...list(n.next).map((t,i)=>edge(n.id,t,i)),...Object.entries(n.outcomes||{}).flatMap(([name,to],i)=>list(to).map(t=>edge(n.id,t,i+1,name)))])}${checkpoints.flatMap(c=>Object.entries(c.decisions||{}).filter(([,to])=>to!=='continue').map(([name,to],i)=>edge(c.before||c.during,to,i+1,name,c)))}${wire?html`<path class="wf-wire" d=${`M${places[wire.source]?.x+212},${places[wire.source]?.y+50} C${places[wire.source]?.x+260},${places[wire.source]?.y+50} ${wire.x-48},${wire.y} ${wire.x},${wire.y}`}/>`:null}</svg>${nodes.map(card)}</div></div>`:
      view==='rooms'?html`<div class="wf-room-groups">${[...rooms,...(nodes.some(n=>!rooms.some(r=>r.id===n.room))?[{id:'',label:'Ungrouped'}]:[])].map(r=>{const grouped=nodes.filter(n=>r.id?n.room===r.id:!rooms.some(x=>x.id===n.room));return grouped.length?html`<section><header><h3>${r.label||r.id}</h3>${onDesignRoom&&r.id?html`<button type="button" class="link small" onClick=${()=>onDesignRoom(r.id)}>Design room</button>`:null}</header>${grouped.map(card)}</section>`:null})}</div>`:html`<div class="wf-list">${branched?html`<p class="muted small">Flow shows the branches and loops. <button class="link" type="button" onClick=${()=>setView('flow')}>See connections →</button></p>`:null}${nodes.map(card)}</div>`}
      </div>${node?html`<aside ref=${inspector} class="wf-inspector" aria-label="Task inspector"><div class="wf-inspector-head"><b>${node.label}</b><button type="button" class="iconbtn sm" aria-label="Close task inspector" onClick=${closeInspector}>×</button></div>
      <${N.Field} label="Task name"><${N.Input} value=${node.label} onInput=${v=>patch(node.id,{label:v})}/></${N.Field}>
      <${N.Field} label="Skill"><${N.Select} value=${node.procedure||''} onChange=${v=>patch(node.id,{procedure:v})} options=${[{value:'',label:'Instructions only'},...skills]}/></${N.Field}>
      ${onEditSkill&&node.procedure?html`<button class="link small" onClick=${()=>onEditSkill(node.procedure)}>Edit reusable skill</button>`:null}
      <${N.Field} label="Task instructions"><${N.Textarea} rows=${4} value=${node.instructions||''} onInput=${v=>patch(node.id,{instructions:v})}/></${N.Field}>
      <${N.Field} label="Room" hint="Where the agent appears in the lab. Several tasks and studies can share a room; arrows control the order."><${N.Select} value=${node.room||''} options=${rooms.map(r=>({value:r.id,label:r.label||r.id}))} onChange=${v=>patch(node.id,{room:v})}/></${N.Field}>
      <details class="wf-more" key=${node.id+'-outputs'}><summary>Output files <span class="muted">${node.outputs?.length?'· '+N.plural(node.outputs.length,'file'):''}</span></summary><${N.Field} label="Expected output files" hint="Name files you want this task to produce. Leave blank to use the skill and task instructions."><${N.Input} value=${(node.outputs||[]).join(', ')} placeholder="report.md, results.json" onInput=${v=>patch(node.id,{outputs:v.split(',').map(s=>s.trim()).filter(Boolean)})}/></${N.Field}></details>
      <details class="wf-more" key=${node.id+'-tools'}><summary>More skills & tools <span class="muted">${node.skills?.length?'· '+N.plural(node.skills.length,'extra skill'):''}${node.external?' · '+node.external.framework+' / '+node.external.phase:''}</span></summary>
      <fieldset><legend>Skill sequence</legend>${(node.skills||[]).map((p,i)=>html`<div class="row"><span class="grow">${skills.find(s=>s.value===p)?.label||p}</span><button class="link" type="button" disabled=${i===0} aria-label=${'Move '+p+' up'} onClick=${()=>{const seq=[...node.skills];[seq[i-1],seq[i]]=[seq[i],seq[i-1]];patch(node.id,{skills:seq})}}>↑</button><button class="link" type="button" aria-label=${'Remove skill '+p} onClick=${()=>patch(node.id,{skills:node.skills.filter((_,j)=>i!==j)})}>×</button></div>`)}
      <${N.Select} value="" ariaLabel="Add skill to sequence" options=${[{value:'',label:'Add a skill…'},...skills]} onChange=${v=>{if(v)patch(node.id,{skills:[...(node.skills||[]),v]})}}/></fieldset>
        <${N.Field} label="Research tool"><${N.Select} value=${node.external?.framework||''} options=${[{value:'',label:'None'},...frameworks.map(f=>({value:f.id,label:f.title}))]} onChange=${v=>patch(node.id,{external:v?{framework:v,phase:frameworks.find(f=>f.id===v)?.phases[0]||''}:undefined})}/></${N.Field}>
        ${node.external?html`<${N.Field} label="Tool phase"><${N.Select} value=${node.external.phase} options=${frameworks.find(f=>f.id===node.external.framework)?.phases||[node.external.phase]} onChange=${v=>patch(node.id,{external:{...node.external,phase:v}})}/></${N.Field}><p class="muted small">One phase, then the next connection. Project settings supply inputs and budgets.</p>`:null}
      </details>
      <details class="wf-more" key=${node.id+'-agent'}><summary>Agent & conversation <span class="muted">· ${[...defaults,...roles].find(r=>r.value===(node.agent?.role||'general'))?.label||node.agent?.role} · ${modes.find(m=>m.value===(node.context?.mode||'fresh'))?.label}</span></summary>
      <${N.Field} label="Run this task as"><${N.Select} value=${node.agent?.role||'general'} options=${[...new Map([...defaults,...roles].map(r=>[r.value,r])).values()]} onChange=${v=>patch(node.id,{agent:{...node.agent,role:v},...(v==='reviewer'?{context:{mode:'fresh'}}:{})})}/></${N.Field}>
      <${N.AgentChoice} role=${node.agent?.role||'general'} value=${node.agent?.preset?'preset:'+node.agent.preset:node.agent?.backend?'backend:'+node.agent.backend:''} onChange=${v=>{const {model,effort,...agent}=node.agent||{};patch(node.id,{agent:{...agent,preset:v.startsWith('preset:')?v.slice(7):'',backend:v.startsWith('backend:')?v.slice(8):''}})}}/>
      <${N.Field} label="Conversation"><${N.Select} value=${node.context?.mode||'fresh'} options=${modes} onChange=${v=>patch(node.id,{context:{mode:v,...(v==='fresh'?{handoff:node.agent?.role!=='reviewer'&&!!incoming(node.id).length}:{ }),from:incoming(node.id)[0]?.id||''}})}/></${N.Field}>
      ${node.context?.mode==='fresh'&&incoming(node.id).length?html`<label class="wf-check"><input type="checkbox" checked=${!!node.context.handoff} onChange=${e=>patch(node.id,{context:{...node.context,handoff:e.target.checked,from:node.context.from||incoming(node.id)[0]?.id}})}/>Include a summary of prior work</label>`:null}
      ${(node.context?.mode||'fresh')!=='fresh'||node.context?.handoff?html`${node.context.mode==='fresh'?html`<fieldset><legend>Evidence from</legend>${earlier(node.id).filter(n=>n.id!==node.id).map(n=>html`<label class="wf-check"><input type="checkbox" checked=${list(node.context.from).includes(n.id)} onChange=${e=>patch(node.id,{context:{...node.context,from:e.target.checked?[...list(node.context.from),n.id]:list(node.context.from).filter(id=>id!==n.id)}})}/>${n.label}</label>`)}</fieldset>`:html`<${N.Field} label="Context from"><${N.Select} value=${node.context?.from||''} options=${[{value:'',label:'Select a source task'},...earlier(node.id).map(n=>({value:n.id,label:n.label+(n.id===node.id?' · previous visit':'')}))]} onChange=${v=>patch(node.id,{context:{...node.context,from:v,...(v===node.id?{initial:'fresh'}:{initial:undefined})}})}/></${N.Field}>`}
      <p class="wf-explainer">${node.context.mode==='continue'?'Send the next message in the source conversation. Only one branch can continue it.':node.context.mode==='native-fork'?'Copy the source conversation into a new agent. Requires native fork support.':'Start a new conversation with a summary and evidence links.'}${list(node.context.from).includes(node.id)?' The first pass starts a new conversation. Later passes use this task’s previous conversation.':''}</p>`:html`<p class="wf-explainer">Start a new conversation. Earlier messages are not included.</p>`}
      ${node.agent?.role==='reviewer'&&((node.context?.mode||'fresh')!=='fresh'||node.context?.handoff)?html`<p class="wf-explainer">This reviewer inherits prior work. Choose New conversation and turn off the summary for an independent review.</p>`:null}
      <details><summary>Model & role instructions <span class="muted">${node.agent?.model!==undefined?'· '+(node.agent.model??'harness default'):''}${node.agent?.instructions?' · custom instructions':''}</span></summary><${N.Field} label="Model override" hint="Leave blank to use agent settings. Type inherit to use the harness default."><${N.Input} value=${node.agent?.model===null?'inherit':node.agent?.model||''} placeholder="Use agent settings" onInput=${v=>{const agent={...node.agent};if(v)agent.model=v==='inherit'?null:v;else delete agent.model;patch(node.id,{agent})}}/></${N.Field}>
      <${N.Field} label="Extra role instructions"><${N.Textarea} rows=${2} value=${node.agent?.instructions||''} onInput=${v=>patch(node.id,{agent:{...node.agent,instructions:v}})}/></${N.Field}></details></details>
      <details class="wf-more" key=${node.id+'-routing'}><summary>Connections & loops</summary><${N.Field} label="Task tags"><${N.TagInput} ariaLabel="Task tags" value=${node.tags||[]} onChange=${v=>patch(node.id,{tags:v})} suggestions=${tags}/></${N.Field}><fieldset><legend>Tasks after this one</legend>${nodes.map(n=>html`<label class="wf-check"><input type="checkbox" checked=${list(node.next).includes(n.id)} onChange=${e=>patch(node.id,{next:e.target.checked?[...list(node.next),n.id]:list(node.next).filter(x=>x!==n.id)})}/>${n.label}</label>`)}</fieldset>
      <label class="wf-check"><input type="checkbox" checked=${!!node.join} onChange=${e=>patch(node.id,{join:e.target.checked})}/>Wait for all incoming branches</label>
      <p class="wf-explainer">Use this for parallel work. Leave it off when alternative paths merge.</p>
      <${TaskRoutes} key=${node.id} node=${node} nodes=${nodes} onChange=${v=>patch(node.id,{outcomes:v})}/>
      <${N.Field} label="Maximum passes" hint="Leave blank for no task-specific limit."><${N.Input} type="number" value=${node.max_visits||''} onInput=${v=>patch(node.id,{max_visits:v?Number(v):undefined})} placeholder="No task-specific limit"/></${N.Field}></details>
      <details class="wf-templates"><summary>Task starting points</summary><div class="row">${skills.filter(s=>s.task?.label).map(s=>html`<${N.Btn} small onClick=${()=>patch(node.id,{label:s.task.label,agent:{...node.agent,role:s.task.role||'general'},...(node.procedure||node.instructions||node.skills?.length?{}:{procedure:s.value}),...(s.task.role==='reviewer'?{context:{mode:'fresh'}}:{})})}>${s.task.label}</${N.Btn}>`)}<${N.Btn} small onClick=${()=>{const id=node.id+'-copy-'+Date.now().toString(36);onChange([...nodes,{...JSON.parse(JSON.stringify(node)),id,label:node.label+' copy',next:[],context:{mode:'fresh'}}]);setSelected(id)}}>Duplicate task</${N.Btn}></div><p class="muted small">Starting points fill a role and an empty skill; your instructions stay editable.</p></details>
      <div class="wf-add">${connections(node.id).length>1?html`<${N.Select} ariaLabel="Parallel source connection" value=${parallelFrom} onChange=${setParallelFrom} options=${[{value:'',label:'Choose a connection…'},...connections(node.id)]}/>`:null}<${N.Btn} small onClick=${()=>add()}>+ Next task</${N.Btn}><${N.Btn} small disabled=${!connections(node.id).length||connections(node.id).length>1&&!connections(node.id).some(e=>e.value===parallelFrom)} onClick=${()=>add(true)}>+ Parallel task</${N.Btn}>
      ${onCheckpoint?html`<${N.Btn} small onClick=${()=>onCheckpoint(node.id)}>+ Checkpoint</${N.Btn}>`:null}</div>
      <button type="button" class="link small wf-remove" disabled=${nodes.length<2} onClick=${removeTask}>Delete task</button>
      </aside>`:null}</div>
      <footer class="wf-editor-foot">${onSave?html`<${N.Btn} kind="primary" disabled=${!dirty} onClick=${onSave}>Save workflow draft</${N.Btn}>`:null}${onExport?html`<${N.Btn} small disabled=${dirty} onClick=${onExport}>Download procedure</${N.Btn}>`:null}</footer>
    </section>`;
  };
})();
