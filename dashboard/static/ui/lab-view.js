/* A disposable renderer frame. It receives state; it never reads or writes lab files. */
(async function () {
  let world, latest, following, syncing=false, inspected, anchorFrame, active=true;
  const draftID=new URLSearchParams(location.search).get('roomdraft'), loaded=new Map();
  let draft;
  const report=error=>{send({error:'The Lab view could not load: '+error.message});let note=document.querySelector('.preview-error');if(!note){note=document.createElement('p');note.className='note note-warn preview-error';note.setAttribute('role','alert');document.body.append(note)}note.textContent=error.message};
  const send = data => parent.postMessage({ labView: 1, ...data }, location.origin);
  const followSelect=document.querySelector('.view-follow'),followActivity=document.querySelector('.view-activity'),stopButton=document.querySelector('.view-stop');
  let rosterKey='';
  const followControls=()=>{
    const agents=latest?.state?.agents||[],key=JSON.stringify(agents.map(a=>[a.id,a.label,a.role,a.parent]));
    if(key!==rosterKey){
      rosterKey=key;
      followSelect.replaceChildren(new Option(agents.length?'Follow an agent':'No agents running',''),
        ...agents.map(a=>new Option((a.parent?'↳ ':'')+(a.label||a.role||a.id),a.id)));
    }
    followSelect.disabled=!agents.length;followSelect.value=following||'';stopButton.hidden=!following;
    const agent=agents.find(a=>a.id===following);
    const status=agent?.doing?.summary||Lab3D.model.ACTS[agent?.doing?.kind]?.[1]||({working:'Working',asking:'Waiting for you',queued:'Queued',stalled:'No recent activity',idle:'Idle'}[agent?.status])||'';
    followActivity.textContent=following?status:'';followActivity.title=followActivity.textContent;
  };
  const closeInspection=()=>{inspected=null;cancelAnimationFrame(anchorFrame);send({kind:'dismiss-agent'})};
  const track = () => {
    if(!inspected)return;
    const anchor=world.agentAnchor(inspected.agent_id);
    if(!anchor){inspected=null;send({kind:'dismiss-agent'});return}
    send({kind:'agent-anchor',anchor});anchorFrame=requestAnimationFrame(track);
  };
  const inspect = (kind,id,sub) => {
    cancelAnimationFrame(anchorFrame);
    const agent=(latest?.state?.agents||[]).find(a=>kind==='run'?a.run_id===id&&(sub?a.sub===sub:!a.parent):a.worker_id===id);
    inspected={kind,id,sub,agent_id:kind==='assistant'?'newt':agent?.id,agent};
    if(!inspected.agent_id){send({kind,id,sub});return}
    const tip=document.querySelector('.world-tip');if(tip)tip.style.display='none';
    send({kind:'inspect-agent',target:inspected,anchor:world.agentAnchor(inspected.agent_id)});track();
  };
  const apply = async message => {
    const { state, theme, cast, motion } = message;
    if(!state)return;
    for(const [id,resource] of Object.entries({...state.room_designs,...(draft?{[draft.room]:draft}: {})})){
      if(loaded.get(id)===resource.revision)continue;
      if(resource.module){const module=await import('/api/room-resource?'+(draft&&id===draft.room?'draft='+encodeURIComponent(draftID):'room='+encodeURIComponent(id))+'&revision='+resource.revision);if(typeof module.default!=='function')throw new Error('extra.js must export a registration function');module.default(Lab3D)}
      const data=resource.definition,base=Lab3D.rooms[data.base]||{};
      Lab3D.defineRoom({...base,...data,key:id,resourceRevision:resource.revision});loaded.set(id,resource.revision);
    }
    if(message!==latest)return;
    document.documentElement.dataset.lamp = theme;
    world.setLamp(theme); world.setCast(cast);
    world.setMotion(motion && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'full' : 'reduced');
    if (state) {
      const room={id:draft?.room,label:draft?.room,title:'Room preview',steps:[]};
      const view=draft&&!message.previewWide?{...state,items:[],agents:[],runs:[],workflow:{...state.workflow,rooms:[room],workflows:[]}}:
        draft&&!state.workflow?.rooms?.some(r=>r.id===draft.room)?{...state,workflow:{...state.workflow,rooms:[...(state.workflow?.rooms||[]),room]}}:state;
      await world.sync(view);
      if(following){if((state.agents||[]).some(a=>a.id===following||a.run_id===following||a.worker_id===following)){if(world.following()!==following)world.followWorker(following)}else{following=null;world.stopFollow()}}
      followControls();
      if(message===latest){document.documentElement.dataset.ready = 'true';document.querySelector('.preview-error')?.remove();send({kind:'ready'})}
    }
  };
  const sync = async () => {
    if(!world||!latest||syncing||!active)return;
    syncing=true;
    try{while(latest){const message=latest;await apply(message);if(message===latest)break}}
    finally{syncing=false}
  };
  addEventListener('message', e => {
    if (e.source !== parent || e.origin !== location.origin || e.data?.labView !== 1) return;
    if(typeof e.data.active==='boolean'){
      active=e.data.active;world?.setActive(active);
      if(!active){inspected=null;cancelAnimationFrame(anchorFrame);return}
    }
    if(e.data.command==='dismiss-agent'){inspected=null;cancelAnimationFrame(anchorFrame);return}
    if(e.data.command==='follow'){following=e.data.id;if(world)world.followWorker(following);followControls();return}
    if(!e.data.state)return;
    latest = e.data; sync().catch(report);
  });
  try {
    // Seed the dashboard's normal local session when a designer opens this preview directly.
    if(parent===window)await fetch('/');
    if(draftID){const response=await fetch('/api/room-draft?id='+encodeURIComponent(draftID));draft=await response.json();if(!response.ok||!draft.ok)throw new Error(draft.error||'Unable to read the room draft')}
    world = await Lab3D.createWorld(document.getElementById('scene'), { lamp: latest?.theme||document.documentElement.dataset.lamp, legacyMovement: true });
    world.onClick(id => send({ kind: 'study', id }),()=>send({kind:'inbox'}));
    world.onRun((id,sub) => inspect('run',id,sub));
    world.onWorker(id=>inspect('worker',id));
    world.onArtifact(id=>send({kind:'artifact',id}));
    world.onFollow(id=>{const agent=(latest?.state?.agents||[]).find(a=>a.id===id||a.run_id===id||a.worker_id===id);following=agent?.id||id;followControls();send({kind:'following',id})});
    world.onCheckpoint((id, checkpoint) => send({ kind: 'checkpoint', id, checkpoint }));
    world.onNewt(()=>inspect('assistant'));
    let down;
    addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY]});
    addEventListener('pointerup',e=>{if(inspected&&down&&e.target.id==='scene'&&Math.hypot(e.clientX-down[0],e.clientY-down[1])<4)closeInspection()},true);
    addEventListener('keydown',e=>{if(e.key==='Escape')closeInspection()});
    document.querySelector('.view-back').onclick = () => {following=null;world.stopFollow();world.back()};
    followSelect.onchange=e=>{following=e.target.value;if(following)world.followWorker(following);else world.stopFollow();followControls()};
    stopButton.onclick=()=>{following=null;world.stopFollow();followControls();followSelect.focus()};
    document.querySelector('.view-labels').onclick=e=>{const button=e.currentTarget,on=button.getAttribute('aria-pressed')!=='true';button.setAttribute('aria-pressed',String(on));button.title=on?'Hide room names':'Show room names';world.setLabels(on)};
    await world.boot();
    world.setActive(active);
    if(!latest&&parent===window){const response=await fetch('/api/state');if(response.ok&&!latest)latest={state:await response.json(),theme:document.documentElement.dataset.lamp,motion:true}}
    await sync();
  } catch (error) { report(error); }
  addEventListener('pagehide', () => {cancelAnimationFrame(anchorFrame);world?.destroy()}, { once: true });
})();
