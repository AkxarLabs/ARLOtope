/* Lab3D.model — what the world shows, worked out from the lab's snapshot with no drawing at all (so it is
 * testable on its own, tests/test_world.py): the defined rooms, their placement, and where each task runs.
 * world.js draws what this decides. */
(function () {
  'use strict';
  const L = (window.Lab3D = window.Lab3D || {});
  const M = {};
  // Machine boundaries affect presentation only. Execution records and IDs stay unchanged.
  M.machineOf = (s, value, seen=new Set()) => {
    if(seen.has(value))return 'local';seen.add(value);
    const run=value.run_id&&(s.runs||[]).find(r=>r.run_id===value.run_id);
    if(run&&run!==value)return M.machineOf(s,run,seen);
    if(value.remote?.machine)return value.remote.machine;
    if(value.machine)return value.machine;
    if(value.level==='hub')return 'local';
    if(value.parent){const parent=(s.agents||[]).find(a=>a.id===value.parent);if(parent)return M.machineOf(s,parent,seen)}
    const it=(s.items||[]).find(i=>i.id===(value.subject||value.project||value.target));
    return it?.machine||'local';
  };
  M.machineGroups = s => {
    if(s.world_view!=='full')return [{id:'local',name:'The lab'}];
    const known=new Map((s.machines||[]).map(m=>[m.id,m]));
    const used=new Set([...(s.items||[]).map(i=>i.machine||'local'),...(s.agents||[]).map(a=>M.machineOf(s,a))]);
    return [{id:'local',name:'This computer'},...[...new Set([...known.keys(),...used])].filter(id=>id!=='local'&&(used.has(id)||known.get(id)?.state==='connected')).sort().map(id=>known.get(id)||{id,name:id})];
  };
  const roomKey = (s,id,machine='local') => s.world_view==='full'&&machine!=='local'?'machine/'+encodeURIComponent(machine)+'/'+id:id;
  const pickRoom = (s,rooms,id,machine) => {const key=roomKey(s,id,machine);return rooms[key]?key:null};

  /** the lab's definition the snapshot carries (else the dashboard's, else the shipped default): its steps (each
   *  with the procedure that does it and the room it stands in), workflows, rooms and procedures */
  M.wfOf = s => (s && s.workflow && Array.isArray(s.workflow.rooms) ? s.workflow
    : (window.NL && window.NL.WF && window.NL.WF.rooms ? window.NL.WF : window.__WORKFLOW_DEFAULT__)) || { rooms: [], steps: [] };
  const stepsIn = r => r.steps || r.states || [];
  /** the procedures that do (or are offered at) these steps */
  M.procsOf = (wf, ids, room) => [...new Set([
    ...(wf.steps || []).filter(x => ids.includes(x.id)).flatMap(x => [x.do, ...(x.also || [])]),
    ...(wf.workflows || []).flatMap(w => Object.entries(w.nodes || {}).filter(([id,n]) => room?n.room===room:ids.includes(id)).map(([id,n]) => n.procedure || (n.instructions?'task:'+id:null)))
  ].filter(Boolean))];
  // how a procedure's run shows in the world is the procedure's own say (its `world:` key), never its name
  M.worldRole = (s, skill) => ((M.wfOf(s).procedures || {})[skill] || {}).world || null;
  /** Defined rooms are shared by studies. By-machine view repeats the same definitions per machine. */
  M.roomList = function roomList(s) {
    if(s.world_view==='full'){
      const shared=M.roomList({...s,world_view:'unified'});
      return M.machineGroups(s).flatMap(m=>{
        const list=shared.map(r=>({...r,id:roomKey(s,r.id,m.id),sourceId:r.id,machine:m.id,machineName:m.name||m.id}));
        if(m.id!=='local')list.push({id:roomKey(s,'hub',m.id),sourceId:'hub',machine:m.id,machineName:m.name||m.id,title:'Desk',states:[],base:{id:'machine-desk',label:'Desk'},lobby:true});
        return list;
      });
    }
    const wf = M.wfOf(s), out = [];
    for (const original of wf.rooms || []) {
      const grouped=(wf.workflows||[]).flatMap(w=>Object.entries(w.nodes||{}).filter(([,n])=>n.room===original.id).map(([id])=>id));
      const r={...original,steps:[...new Set([...stepsIn(original),...grouped])]};
      out.push({ id: r.id, base: r, title: r.title || r.label || r.id, kicker: r.title && r.label && r.label !== r.title ? r.label : null, states: stepsIn(r), place: r.place, facing: r.facing });
    }
    return out;
  };

  /** Deterministic room layout, repeated with an offset for each machine. */
  M.placeRooms = function placeRooms(list, wf) {
    if(list.some(r=>r.machine)){
      const plan={},ids=[...new Set(list.map(r=>r.machine))];let end;
      for(const id of ids){
        const rows=list.filter(r=>r.machine===id),local=rows.filter(r=>!r.lobby).map(r=>({...r,id:r.sourceId,machine:null}));
        const p=M.placeRooms(local,wf),cells=[...Object.values(p).map(p=>p.cell),[0,0]],min=Math.min(...cells.map(c=>c[0])),max=Math.max(...cells.map(c=>c[0]));
        const offset=end===undefined?0:end+3-min;end=max+offset;
        rows.forEach(r=>{const q=r.lobby?{cell:[0,0],facing:'s'}:p[r.sourceId];plan[r.id]={...q,cell:[q.cell[0]+offset,q.cell[1]]}});
      }
      return plan;
    }
    const side = (wf.steps || []).filter(x => x.shelf).map(x => x.id);
    return L.plan(list.map(r => ({ id: r.id, place: r.place, facing: r.facing, states: r.states })), side);
  };

  // Task assignments select rooms; study/project identity never creates a room.
  M.item = (s, id) => ((s && s.items) || []).find(i => i.id === id);
  M.roomForStep = function roomForStep(s, id, rooms, machine='local', workflow) {
    const wf=M.wfOf(s),w=(wf.workflows||[]).find(w=>w.id===workflow);
    const rid=w?.nodes?.[id]?.room||(wf.steps||[]).find(t=>t.id===id)?.room
      ||wf.rooms.find(r=>stepsIn(r).includes(id))?.id;
    return rid?pickRoom(s,rooms,rid,machine):null;
  };
  M.roomOfItem = (s,it,rooms,machine=it.machine||'local') => M.roomForStep(s,it.state,rooms,machine,it.workflow);
  M.roomForProc = function roomForProc(s, proc, rooms, machine='local') {
    const wf = M.wfOf(s), st = (wf.steps || []).find(x => x.do === proc) || (wf.steps || []).find(x => (x.also || []).includes(proc));
    return st?M.roomForStep(s,st.id,rooms,machine):null;
  };
  /** A bound task uses its assigned room; other work uses its procedure, study step, or the desk. */
  M.placeOfRun = function placeOfRun(s, r, rooms) {
    const subj = r.subject || (r.target && r.target !== 'hub' ? r.target : null), it = subj && M.item(s, subj);
    const role = M.worldRole(s, r.skill);
    const machine=M.machineOf(s,r),hub=roomKey(s,'hub',machine);
    const task=r.workflow_node||r.assigned_step;
    if(task){const key=M.roomForStep(s,task,rooms,machine,it?.workflow);if(key)return key}
    if (role === 'designs-room') { const rid = String(r.args || '').split(/\s+/)[0],key=pickRoom(s,rooms,rid,machine); if(key)return key; }
    return M.roomForProc(s,r.skill,rooms,machine)||(it&&M.roomOfItem(s,it,rooms,machine))||hub;
  };

  /** where agents work in a room, by what they are doing: every piece of furniture that serves an activity (its
   *  component's `uses`) offers the spots in front of it (`stands`: [x, z, facing?] in its own frame) →
   *  {kind: [[x, z, facing], …]} in the room's frame */
  M.standsOf = function standsOf(props) {
    const out = {};
    for (const p of props || []) {
      const c = (L.components || {})[p.c];
      if (!c || !Array.isArray(c.uses)) continue;
      const st = typeof c.stands === 'function' ? c.stands(p.props || {}) : (c.stands || [[0, 0.7]]);
      const r = p.rot || 0, cs = Math.cos(r), sn = Math.sin(r);
      for (const [sx, sz, f] of st) {              // (facing the piece square on, unless the spot says otherwise)
        const x = p.at[0] + sx * cs + sz * sn, z = p.at[1] - sx * sn + sz * cs, facing = r + (f ?? Math.PI);
        for (const k of c.uses) (out[k] = out[k] || []).push([x, z, facing]);
      }
    }
    return out;
  };

  /** the activities an agent can be at (the tracer's vocabulary), as the world names them */
  M.ACTS = { read: ['▤', 'reading'], search: ['⌕', 'searching'], edit: ['✎', 'editing'], run: ['⚗', 'running an experiment'],
    bash: ['›', 'at the terminal'], git: ['⑂', 'committing'], spawn: ['⇢', 'briefing a subagent'], ask: ['?', 'asking you'],
    plan: ['☰', 'planning'], skill: ['✦', 'following a procedure'], mcp: ['⚙', 'using a tool'], tool: ['•', 'working'] };

  /** where an agent works and how it stands, from its row in the snapshot's `agents`: room — its run's room (see
   *  placeOfRun) or, for a session no run accounts for, its study's; desk — it is at your desk instead (asking you,
   *  queued, or work with no room); kind — what it is doing now (the activity of the call it is in, else null);
   *  pose — work · wait (asking you) · idle (queued, or between calls in a session) · sleep (gone quiet) */
  M.placeAgent = function placeAgent(s, a, rooms) {
    const run = a.run_id ? (s.runs || []).find(r => r.run_id === a.run_id) : null;
    let room;
    if (run) room = M.placeOfRun(s, run, rooms);
    else { const it = a.subject && M.item(s, a.subject),machine=M.machineOf(s,a); room = it ? M.roomOfItem(s, it, rooms,machine) : null; }
    room = room && rooms[room] ? room : 'hub';
    const kind = (a.doing && a.doing.kind) || null;
    const pose = a.status === 'asking' || kind === 'ask' ? 'wait' : a.status === 'queued' ? 'idle' : a.status === 'stalled' ? 'sleep'
      : a.status === 'idle' && !kind ? 'idle' : 'work';
    const machine=M.machineOf(s,a),desk=room==='hub'||pose==='wait'||a.status==='queued',localHub=roomKey(s,'hub',machine);
    if(s.world_view==='full'&&machine!=='local'&&desk&&rooms[localHub])return {room:localHub,desk:false,kind,pose,run};
    return { room, desk, kind, pose, run };
  };


  /** Coarse local routing around furniture; bounded by room size, independent of backend/workflow. */
  M.pathInRoom = (spec, start, end) => {
    const step = 0.5, [w, d] = spec.size, cols = Math.ceil(w / step), rows = Math.ceil(d / step);
    const cell = p => [Math.max(0, Math.min(cols - 1, Math.round((p[0] + w / 2) / step))), Math.max(0, Math.min(rows - 1, Math.round((p[1] + d / 2) / step)))];
    const point = ([x, z]) => [x * step - w / 2, z * step - d / 2];
    const blocks = (spec.props || []).flatMap(p => {
      const c = L.components[p.c]; if (!c || !c.bounds || ['rug', 'flowers', 'rock', 'document'].includes(p.c)) return [];
      const b = typeof c.bounds === 'function' ? c.bounds(p.props) : c.bounds;
      return [{ at: p.at, rot: p.rot || 0, b }];
    });
    const blocked = c => { const [x, z] = point(c); return blocks.some(p => { const dx = x - p.at[0], dz = z - p.at[1], cs = Math.cos(p.rot), sn = Math.sin(p.rot);
      return Math.abs(dx * cs - dz * sn) < p.b[0] / 2 + 0.15 && Math.abs(dx * sn + dz * cs) < p.b[1] / 2 + 0.15; }); };
    const a = cell(start), b = cell(end), key = p => p.join(','), queue = [a], prev = new Map([[key(a), null]]);
    for (let i = 0; i < queue.length && i < 4096; i++) {
      const c = queue[i]; if (key(c) === key(b)) { const path = []; let k = key(b);
        while (k) { path.push(k.split(',').map(Number)); k = prev.get(k); }
        path.reverse(); const turns = path.filter((p, j) => j > 0 && j < path.length - 1 &&
          (p[0] - path[j - 1][0] !== path[j + 1][0] - p[0] || p[1] - path[j - 1][1] !== path[j + 1][1] - p[1]));
        return [...turns.map(point), end]; }
      for (const [dx, dz] of [[1, 0], [0, 1], [-1, 0], [0, -1]]) { const n = [c[0] + dx, c[1] + dz], k = key(n);
        if (n[0] < 0 || n[0] >= cols || n[1] < 0 || n[1] >= rows || prev.has(k) || (k !== key(b) && blocked(n))) continue;
        prev.set(k, key(c)); queue.push(n); }
    }
    return [end]; // An old room without usable clearances keeps its existing direct route.
  };

  L.model = M;
})();
