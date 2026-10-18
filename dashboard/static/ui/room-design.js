/* Lean room drafts reuse the live renderer and the ordinary designer conversation. */
(function(){
  const N=window.NL,{html,useState,useEffect,useRef}=N;
  const RoomDesign=({room,onClose})=>{
    const [draft,setDraft]=useState(null),[text,setText]=useState(''),[source,setSource]=useState(''),[error,setError]=useState(''),[wide,setWide]=useState(false),[revision,setRevision]=useState(0),ref=useRef();
    const load=async id=>{const r=await N.get('/api/room-draft?id='+encodeURIComponent(id));if(r.error)setError(r.error);else{setDraft(r);setSource(JSON.stringify(r.definition,null,2))}};
    useEffect(()=>{N.get('/api/room-drafts').then(async list=>{const old=list.drafts?.find(d=>d.room===room&&!d.applied);if(old)return load(old.id);const r=await N.api('/api/room-draft',{action:'create',room});if(r.ok)load(r.id);else setError(r.error)})},[room]);
    const send=()=>ref.current?.contentWindow?.postMessage({labView:1,state:N.getState(),theme:N.themeNow(),cast:N.prefs.cast,motion:N.prefs.motion,previewWide:wide},location.origin);
    useEffect(send,[wide,revision]);
    const act=async action=>{setError('');let definition;try{if(action==='save')definition=JSON.parse(source)}catch(e){setError(e.message);return}
      const r=await N.api('/api/room-draft',{action,id:draft.id,text,definition,confirm:action==='apply'});if(r.error){setError(r.error);return}
      await load(draft.id);if(action==='save')setRevision(n=>n+1);if(action==='apply'){N.toast('Room applied');N.refresh()}if(action==='agent')N.openRun(r.run_id)};
    return html`<${N.Sheet} title=${'Design room · '+room} sub="Changes stay in draft until applied." wide onClose=${onClose}>
      <div class="room-design"><div class="row between"><label><input type="checkbox" checked=${wide} onChange=${e=>setWide(e.target.checked)}/>Show full lab</label><${N.Btn} small disabled=${!draft} onClick=${async()=>{await load(draft.id);setRevision(n=>n+1)}}>Refresh preview</${N.Btn}></div>
      ${draft?html`<iframe ref=${ref} key=${revision} src=${'static/lab-view.html?roomdraft='+draft.id+'&revision='+revision} title="Room design preview" onLoad=${send}/>`:html`<${N.Spinner}/>`}
      <${N.Field} label="Describe the room"><${N.Textarea} rows=${3} value=${text} onInput=${setText} placeholder="Describe the room or a change…"/></${N.Field}>
      <div class="row end"><${N.Btn} disabled=${!draft||!text.trim()} onClick=${()=>act('agent')}>Design with an agent</${N.Btn}></div>
      ${draft?.run_id?html`<p><button class="link" onClick=${()=>N.openRun(draft.run_id)}>Open conversation</button> · <button class="link" onClick=${async()=>{await load(draft.id);setRevision(n=>n+1)}}>Refresh preview</button></p>`:null}
      <details><summary>Edit the room definition</summary><p class="muted small">Room JSON and optional extra.js for custom geometry.</p><textarea class="input textarea mono" aria-label="Room definition" rows="12" value=${source} onInput=${e=>setSource(e.target.value)}/><${N.Btn} small onClick=${()=>act('save')}>Save & preview</${N.Btn}></details>
      ${error?html`<p role="alert" class="note note-warn">${error}</p>`:null}<div class="row end"><${N.Btn} onClick=${onClose}>Close draft</${N.Btn}><${N.Btn} kind="primary" disabled=${!draft} onClick=${()=>act('apply')}>Apply this room</${N.Btn}></div>
      ${draft?html`<details><summary>Files</summary><p class="muted small mono">lab/.bus/room-drafts/${draft.id}/ → lab/rooms/${room}/</p></details>`:null}</div></${N.Sheet}>`;
  };
  N.openRoomDesign=room=>N.open(RoomDesign,{room},{key:'room-design:'+room});
})();
