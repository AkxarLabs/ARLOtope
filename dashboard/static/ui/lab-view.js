/* A disposable renderer frame. It receives state; it never reads or writes lab files. */
(async function () {
  let world, latest, displayed, following, syncing=false, inspected, anchorFrame, active=true, graphicsLost=false,focusKey='';
  const loaded=new Map();
  let draft;
  const report=error=>{document.documentElement.dataset.ready='false';send({error:error?.message||String(error)})};
  const send = data => parent.postMessage({ labView: 1, ...data }, '*');
  addEventListener('error', e => { if(e.error)report(e.error);else if(e.target?.tagName==='SCRIPT')report(new Error('A renderer script could not load.')); }, true);
  addEventListener('unhandledrejection', e => report(e.reason));
  document.getElementById('scene').addEventListener('webglcontextlost', () => {graphicsLost=true;report(new Error('The graphics context was lost.'))});
  document.getElementById('scene').addEventListener('webglcontextrestored', () => {graphicsLost=false;sync().catch(report)});
  const followSelect=document.querySelector('.view-follow'),followActivity=document.querySelector('.view-activity'),stopButton=document.querySelector('.view-stop');
  const labelsButton=document.querySelector('.view-labels');
  const showLabels=on=>{labelsButton.setAttribute('aria-pressed',String(on));labelsButton.title=on?'Hide room names':'Show room names';world?.setLabels(on)};
  let rosterKey='';
  const followControls=()=>{
    const agents=displayed?.agents||[],key=JSON.stringify(agents.map(a=>[a.id,a.display_label||a.label,a.role,a.parent]));
    if(key!==rosterKey){
      rosterKey=key;
      followSelect.replaceChildren(new Option(agents.length?'Follow an agent':'No agents running',''),
        ...agents.map(a=>new Option((a.parent?'↳ ':'')+(a.display_label||a.label||a.role||a.id),a.id)));
    }
    followSelect.disabled=!agents.length;followSelect.value=following||'';stopButton.hidden=!following;
    const agent=agents.find(a=>a.id===following);
    const status=agent&&(ArloAgents.attention(displayed,agent)?.label||agent.doing?.summary||Lab3D.model.ACTS[agent.doing?.kind]?.[1]||({working:'Working',idle:'Idle'}[agent.status]))||'';
    followActivity.textContent=following?status:'';followActivity.title=followActivity.textContent;
  };
  const closeInspection=()=>{inspected=null;world?.selectAgent(null);cancelAnimationFrame(anchorFrame);send({kind:'dismiss-agent'})};
  const track = () => {
    if(!inspected)return;
    const anchor=world.agentAnchor(inspected.agent_id);
    if(!anchor){inspected=null;world.selectAgent(null);send({kind:'dismiss-agent'});return}
    send({kind:'agent-anchor',anchor});anchorFrame=requestAnimationFrame(track);
  };
  const inspect = (kind,id,sub) => {
    cancelAnimationFrame(anchorFrame);
    const agent=(displayed?.agents||[]).find(a=>kind==='run'?a.run_id===id&&(sub?a.sub===sub:!a.parent):a.worker_id===id);
    inspected={kind,id,sub,agent_id:kind==='assistant'?'newt':agent?.id,agent};
    if(!inspected.agent_id){send({kind,id,sub});return}
    world.selectAgent(inspected.agent_id);
    const tip=document.querySelector('.world-tip');if(tip)tip.style.display='none';
    send({kind:'inspect-agent',target:inspected,anchor:world.agentAnchor(inspected.agent_id)});track();
  };
  const focusAgent=id=>{
    following=id;
    if(world&&id){world.followWorker(id);const agent=(displayed?.agents||[]).find(a=>a.id===id||a.run_id===id||a.worker_id===id);
      if(agent?.run_id)inspect('run',agent.run_id,agent.sub);else if(agent?.worker_id)inspect('worker',agent.worker_id);
    }else if(world){world.stopFollow();closeInspection()}
    followControls();
  };
  const apply = async message => {
    const { state, theme, cast, motion } = message;
    if(!state)return;
    draft=message.draft;
    for(const [id,resource] of Object.entries({...state.room_designs,...(draft?{[draft.room]:draft}: {})})){
      if(loaded.get(id)===resource.revision)continue;
      if(resource.module){
        const url=URL.createObjectURL(new Blob([resource.module_src],{type:'text/javascript'}));
        try{const module=await import(url);if(typeof module.default!=='function')throw new Error('extra.js must export a registration function');await module.default(Lab3D)}
        finally{URL.revokeObjectURL(url)}
      }
      const data=resource.definition,base=Lab3D.rooms[data.base]||{};
      Lab3D.defineRoom({...base,...data,key:id,resourceRevision:resource.revision});loaded.set(id,resource.revision);
    }
    if(message!==latest)return;
    document.documentElement.dataset.lamp = theme;
    world.setLamp(theme); world.setCast(cast); showLabels(message.labels===true);
    world.setMotion(motion && !matchMedia('(prefers-reduced-motion: reduce)').matches ? 'full' : 'reduced');
    if (state) {
      const room={id:draft?.room,label:draft?.room,title:'Room preview',steps:[]};
      let view=draft&&!message.previewWide?{...state,items:[],agents:[],runs:[],workflow:{...state.workflow,rooms:[room],workflows:[]}}:
        draft&&!state.workflow?.rooms?.some(r=>r.id===draft.room)?{...state,workflow:{...state.workflow,rooms:[...(state.workflow?.rooms||[]),room]}}:state;
      if(draft)view=Lab3D.model.preview(view,draft.room,message.previewActivity,message.previewGuides);
      displayed=view;await world.sync(view);
      if(draft&&!message.previewWide)world.goRoom(draft.room);
      if(!draft&&message.focus){
        const focus=message.focus,key=JSON.stringify(focus);
        if(key!==focusKey){
          focusKey=key;
          const agent=(view.agents||[]).find(a=>focus.run?a.run_id===focus.run&&(focus.sub?a.sub===focus.sub:!a.parent):focus.worker&&a.worker_id===focus.worker);
          if(agent)focusAgent(agent.id);
          else{following=null;world.stopFollow();closeInspection();if(focus.study)world.focusTask(focus.study,focus.task);else world.back()}
        }
      }
      if(following){if((view.agents||[]).some(a=>a.id===following||a.run_id===following||a.worker_id===following)){if(world.following()!==following)world.followWorker(following)}else{following=null;world.stopFollow()}}
      followControls();
      if(message===latest&&!graphicsLost){document.documentElement.dataset.ready = 'true';send({kind:'ready'})}
    }
  };
  const sync = async () => {
    if(!world||!latest||syncing||!active||graphicsLost)return;
    syncing=true;
    try{while(latest){const message=latest;await apply(message);if(message===latest)break}}
    finally{syncing=false}
  };
  addEventListener('message', e => {
    if (e.source !== parent || e.data?.labView !== 1) return;
    if(typeof e.data.active==='boolean'){
      active=e.data.active;world?.setActive(active);
      if(!active){focusKey='';inspected=null;world?.selectAgent(null);cancelAnimationFrame(anchorFrame);return}
    }
    if(e.data.command==='dismiss-agent'){inspected=null;world?.selectAgent(null);cancelAnimationFrame(anchorFrame);return}
    if(e.data.command==='clear-hover'){world?.clearHover();return}
    if(e.data.command==='follow'){
      focusAgent(e.data.id);if(world)send({kind:'following',id:e.data.id});return;
    }
    if(!e.data.state)return;
    latest = e.data; sync().catch(report);
  });
  try {
    world = await Lab3D.createWorld(document.getElementById('scene'), { lamp: latest?.theme||document.documentElement.dataset.lamp });
    world.onClick(id => send({ kind: 'study', id }),()=>send({kind:'inbox'}));
    world.onRun((id,sub) => inspect('run',id,sub));
    world.onWorker(id=>inspect('worker',id));
    world.onArtifact(id=>send({kind:'artifact',id}));
    world.onFollow(id=>{const agent=(displayed?.agents||[]).find(a=>a.id===id||a.run_id===id||a.worker_id===id);following=agent?.id||id;followControls();send({kind:'following',id})});
    world.onCheckpoint((id, checkpoint) => send({ kind: 'checkpoint', id, checkpoint }));
    world.onNewt(()=>inspect('assistant'));
    let down;
    addEventListener('pointerdown',e=>{down=[e.clientX,e.clientY]});
    addEventListener('pointerup',e=>{if(inspected&&down&&e.target.id==='scene'&&Math.hypot(e.clientX-down[0],e.clientY-down[1])<4)closeInspection()},true);
    addEventListener('keydown',e=>{if(e.key==='Escape')closeInspection()});
    document.querySelector('.view-back').onclick = () => {following=null;world.stopFollow();world.back()};
    followSelect.onchange=e=>focusAgent(e.target.value);
    stopButton.onclick=()=>{following=null;world.stopFollow();followControls();followSelect.focus()};
    labelsButton.onclick=()=>{const on=labelsButton.getAttribute('aria-pressed')!=='true';showLabels(on);send({kind:'labels',value:on})};
    await world.boot();
    world.setActive(active);
    await sync();
  } catch (error) { report(error); }
  addEventListener('pagehide', () => {cancelAnimationFrame(anchorFrame);world?.destroy()}, { once: true });
})();
