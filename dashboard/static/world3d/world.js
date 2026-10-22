/* ARLOtope — the world: the lab as an open-plan tabletop (three.js), drawn from the live lab.
 *
 * The rooms are the workflow's, on plots round the PI's desk (world3d/layout.js), each in its own look
 * (a built-in world3d/rooms/<id>.js, the lab's lab/rooms3d/<id>.json, or plain).
 * Rooms come from the workflow definition and are shared by studies. By-machine view repeats them
 * in connected spaces; agents use their task's room assignment.
 * Every agent at work (the snapshot's `agents`: a run's main agent, every subagent it spawned, and any session
 * no run accounts for) is a newt in its room, in its run's family colour, a subagent smaller. Each stands at the
 * furniture for the call it is in right now (a shelf to read, a bench to run an experiment, a whiteboard to brief
 * a subagent; model.standsOf), else at its station. A subagent walks out of its parent and back to it when it's
 * done. One asking the PI walks to the desk and raises a hand; a stalled one dozes. Studies are cards on their room's shelf; when a study
 * moves on, a newt carries its card along the streets to the next room (and waits at a checkpoint's lantern for the
 * signature). Nothing on the table is written out: a name shows on hover, and in the tour (setLabels, tour).
 *
 * Lab3D.createWorld(canvas, {lamp, reduced}) → the world contract scene.js wraps (sync, setPose, setLamp,
 * setView, goRoom, focusProject, back, viewInfo, highlight, layout, setAmbient, followWorker/stopFollow/
 * following, setLabels, tour, on* callbacks). Nothing in here writes anything: clicks call back into the dashboard.
 */
(function () {
'use strict';
const L = window.Lab3D;
const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const hash01 = s => { let h = 2166136261; for (let i = 0; i < (s || '').length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 100000) / 100000; };
const ROLE_BADGE = { 'experiment-runner': '#3fb8a6', overseer: '#6f9be6', 'fresh-context-reviewer': '#9b84ea', 'ideation-critic': '#e57ab5',
  'scoping-advocate': '#e0a346', 'general-purpose': '#9aa7ad', orchestrator: '#e0b44e' };
const ACTIVE = new Set(['starting', 'running', 'resuming']);
const WALK = 3.0, STREET = 3.4, PLAZA = 13, ROOMSCALE = 1.15, SUB_SCALE = 0.62;
function three() { return window.THREE ? Promise.resolve(window.THREE) : new Promise(r => addEventListener('three:ready', () => r(window.THREE), { once: true })); }
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

L.createWorld = async function createWorld(canvas, opts) {
  opts = opts || {};
  const THREE = await Promise.race([three(), new Promise(r => setTimeout(() => r(null), 8000))]);
  if (!THREE) throw new Error('three.js did not load');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });     // throws without WebGL
  renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1)); renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(30, 1, 0.5, 900);
  const overlay = document.createElement('div'); overlay.className = 'world-labels'; overlay.setAttribute('aria-hidden', 'true'); canvas.after(overlay);
  const tip = document.createElement('div'); tip.className = 'world-tip'; overlay.after(tip);

  let theme = opts.lamp === 'day' ? 'day' : 'night', K = null, TH = null, reduced = !!opts.reduced, ambient = true;
  let destroyed = false, active = true; const listeners = [];
  const listen = (target, event, fn, options) => { target.addEventListener(event, fn, options); listeners.push(() => target.removeEventListener(event, fn, options)); };
  const motion = () => reduced ? 'reduced' : ambient ? 'full' : 'still';
  let snap = null, labels = false, glowAll = false, touring = null, pose = 'idle', highlightRole = null, followKey = null, view = { level: 'WORLD', room: null, label: '' };
  let onCheckpoint = null, onLab = null, onArtifact = null, onItem = null, onInbox = null, onWorker = null, onRun = null, onNewt = null, onView = null, onFollow = null;
  let staticSig = '', W = null;                 // the built table: rooms, streets, lanterns, hub
  const actors = new Map(), cards = new Map(), pickables = new Set();
  let settled = false;
  const knownRooms = new Set();

  // ── what the table holds: the workflow's shared rooms ─────────────────────────────────────────
  const M = L.model, wfOf = M.wfOf, procsOf = M.procsOf, roomList = M.roomList;
  function plainSpec(id, procs) {
    const n = Math.max(1, procs.length), w = Math.max(7, 2.4 * n + 2), stations = {}, props = [];
    procs.forEach((p, i) => { const x = -w / 2 + 1.6 + i * 2.4; props.push({ c: 'workstation', at: [x, -1.6], props: { monitors: 1 + (i % 2) } }); stations[p] = [x, -0.95, Math.PI]; });
    props.push({ c: 'plant', at: [w / 2 - 0.8, 1.8], props: { kind: 'tall' } }, { c: 'cabinet', at: [-w / 2 + 0.6, 1.2], rot: Math.PI / 2 });
    return { key: id, size: [w, 6], floor: 'tiles', accent: 'blue', props, stations, roleStation: {} };
  }
  function scaled(sp, k) {
    const pt = a => a && [a[0] * k, a[1] * k, a[2]];
    return Object.assign({}, sp, { sceneScale:k, size: [sp.size[0] * k, sp.size[1] * k], shell:sp.shell?.map(s=>({...s,at:[s.at[0]*k,s.at[1],s.at[2]*k],size:[s.size[0]*k,s.size[1],s.size[2]*k]})), props: (sp.props || []).map(p => Object.assign({}, p, { at: [p.at[0] * k, p.at[1] * k] })),
      stations: Object.fromEntries(Object.entries(sp.stations || {}).map(([n, a]) => [n, pt(a)])), roleStation: Object.fromEntries(Object.entries(sp.roleStation || {}).map(([n, a]) => [n, pt(a)])) });
  }

  // ── building the table (again whenever its rooms or their definitions change) ───────────────────
  function buildStatic(s) {
    const wf = wfOf(s), list = roomList(s);
    const sig = JSON.stringify([s.world_view,s.room_designs, list.map(r => [r.id,r.machine,r.machineName,r.sourceId,r.lobby,r.place,r.facing,r.title,r.kicker]), (wf.workflows || []).map(w => [w.id, w.path || w.steps, w.nodes, (w.checkpoints || []).map(c => [c.id, c.before, c.during])])]);
    if (sig === staticSig && W) return false;
    staticSig = sig;
    const previousRooms=W?W.rooms:{};
    for(const o of Object.values(previousRooms))if(o.g.parent)o.g.parent.remove(o.g);
    if (W) { L.resources.release(W.group); W.rooms && Object.values(W.rooms).forEach(o => o.g && pickables.delete(o.floor)); pickables.clear(); }
    K = L.kit(THREE, theme); TH = K.th;
    // the agents stay where they are while the table changes round them (a new lab rising, a room moved):
    // each walks on from where it stands; only couriers (their cards are rebuilt) and a theme change start over
    for (const [key, a] of actors) {
      if (a.courier) { L.resources.release(a.n.group); actors.delete(key); continue; }
      // Rigs belong to actors, not to room layouts. Recolor them without restarting their animation.
      recolor(a.n.group);
      a.room = 'street'; a.dest = null; a.path = []; pickables.add(a.n.hit || a.n.group);
    }
    for (const c of cards.values()) L.resources.release(c); cards.clear();
    const group = new THREE.Group(); scene.add(group);
    // lights
    while (scene.children.some(c => c.isLight)) L.resources.release(scene.children.find(c => c.isLight));
    scene.add(new THREE.HemisphereLight(TH.hemiColor, TH.groundColor, TH.hemi));
    const sun = new THREE.DirectionalLight(TH.sunColor, TH.sun); sun.castShadow = true; sun.shadow.mapSize.set(opts.quality === 'high' ? 4096 : 2048, opts.quality === 'high' ? 4096 : 2048); sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.03; sun.shadow.radius = 4; scene.add(sun);
    const fillLight = new THREE.DirectionalLight(TH.fillColor, TH.fill ?? 0.4); fillLight.position.set(30, 18, -20); scene.add(fillLight);   // a soft pink-blue fill: no harsh shadow sides
    renderer.toneMappingExposure = TH.exposure;
    // where every room stands
    const plan = M.placeRooms(list, wf);
    const DIR = { s: [0, 1], n: [0, -1], e: [1, 0], w: [-1, 0] }, RY = { s: 0, n: Math.PI, e: Math.PI / 2, w: -Math.PI / 2 };
    const rooms = {};
    for (const r of list) {
      const look = L.rooms[r.base.id] || plainSpec(r.base.id, procsOf(wf, r.states, r.base.id));
      const sp = scaled(look, ROOMSCALE), p = plan[r.id], turned = p.facing === 'e' || p.facing === 'w';
      rooms[r.id] = { ...r, cell: p.cell, facing: p.facing, spec: sp, ry: RY[p.facing], dir: DIR[p.facing], ex: turned ? sp.size[1] : sp.size[0], ez: turned ? sp.size[0] : sp.size[1], procs: procsOf(wf, r.states, r.base.id) };
    }
    // the grid: columns as wide as their widest room, rows as deep as their deepest, streets between
    const cells = Object.values(rooms).map(o => o.cell).concat([[0, 0]]);
    const C0 = Math.min(...cells.map(c => c[0])), C1 = Math.max(...cells.map(c => c[0])), R0 = Math.min(...cells.map(c => c[1])), R1 = Math.max(...cells.map(c => c[1]));
    const colW = {}, rowH = {};
    for (let c = C0; c <= C1; c++) colW[c] = Math.max(c === 0 ? PLAZA : 8, ...Object.values(rooms).filter(o => o.cell[0] === c).map(o => o.ex + 1.2)) + STREET;
    for (let w = R0; w <= R1; w++) rowH[w] = Math.max(w === 0 ? PLAZA : 8, ...Object.values(rooms).filter(o => o.cell[1] === w).map(o => o.ez + 1.2)) + STREET;
    const XS = [], ZS = [];
    { let x = 0; for (let c = C0; c <= C1; c++) { XS.push(x); x += colW[c]; } XS.push(x); let z = 0; for (let w = R0; w <= R1; w++) { ZS.push(z); z += rowH[w]; } ZS.push(z); }
    const ox = XS[-C0] + colW[0] / 2, oz = ZS[-R0] + rowH[0] / 2;
    XS.forEach((v, i) => { XS[i] = v - ox; }); ZS.forEach((v, i) => { ZS[i] = v - oz; });
    const cx = c => XS[c - C0] + colW[c] / 2, cz = w => ZS[w - R0] + rowH[w] / 2;
    const toWorld = (o, lx, lz) => [o.x + lx * Math.cos(o.ry) + lz * Math.sin(o.ry), o.z - lx * Math.sin(o.ry) + lz * Math.cos(o.ry)];
    for (const o of Object.values(rooms)) {
      o.x = cx(o.cell[0]); o.z = cz(o.cell[1]); o.hx = colW[o.cell[0]] / 2; o.hz = rowH[o.cell[1]] / 2;
      o.door = toWorld(o, 0, o.spec.size[1] / 2 + 0.5); o.street = [o.x + o.dir[0] * o.hx, o.z + o.dir[1] * o.hz];
      // every procedure of the room has a station: the look's, else a desk added by the front
      o.st = Object.assign({}, o.spec.stations); o.extraProps = [];
      o.procs.filter(p => !o.st[p]).forEach((p, i) => { const [w, d] = o.spec.size, x = w / 2 - 1.3 - i * 2.2; o.extraProps.push({ c: 'workstation', at: [x, d / 2 - 1.8] }); o.st[p] = [x, d / 2 - 1.2, Math.PI]; });
      o.uses = M.standsOf((o.spec.props || []).concat(o.extraProps));     // where agents work here, by what they're doing
      const [w, d] = o.spec.size; o.spots = [];                               // somewhere to stand when no station fits
      for (let i = 0; i < 12; i++) o.spots.push([(-0.32 + (i % 4) * 0.2) * w, (0.05 + Math.floor(i / 4) * 0.12) * d, Math.PI]);
      o.toLocal = (x, z) => [(x - o.x) * Math.cos(o.ry) - (z - o.z) * Math.sin(o.ry), (x - o.x) * Math.sin(o.ry) + (z - o.z) * Math.cos(o.ry)];
      o.shelfAt = [-w / 2 + 0.5, d / 2 - 0.55]; o.toWorld = (lx, lz) => toWorld(o, lx, lz);
    }
    const EXT = { x0: XS[0], x1: XS[XS.length - 1], z0: ZS[0], z1: ZS[ZS.length - 1] };
    const districts=[...new Set(list.map(r=>r.machine||'local'))].map(id=>{
      const rows=Object.values(rooms).filter(r=>(r.machine||'local')===id),cells=rows.map(r=>r.cell).concat(id==='local'?[[0,0]]:[]);
      const c0=Math.min(...cells.map(c=>c[0])),c1=Math.max(...cells.map(c=>c[0])),r0=Math.min(...cells.map(c=>c[1])),r1=Math.max(...cells.map(c=>c[1]));
      return {id,name:rows[0]?.machineName||'This computer',c0,c1,r0,r1,x0:XS[c0-C0],x1:XS[c1-C0+1],z0:ZS[r0-R0],z1:ZS[r1-R0+1]};
    });
    if(!districts.length)districts.push({id:'local',name:'This computer',...EXT,c0:C0,c1:C1,r0:R0,r1:R1});
    const SPAN = Math.max(EXT.x1 - EXT.x0, EXT.z1 - EXT.z0) / 2 + 2.5;
    sun.position.set(-SPAN * 0.7, SPAN * 1.3, SPAN * 0.9); Object.assign(sun.shadow.camera, { left: -SPAN - 4, right: SPAN + 4, top: SPAN + 4, bottom: -SPAN - 4, near: 1, far: SPAN * 4 }); sun.shadow.camera.updateProjectionMatrix();
    // the tabletop, its streets, the plaza, a park on any empty plot
    const slab = (x0, z0, x1, z1, r, h, y, c) => {
      const sh = new THREE.Shape(); sh.moveTo(x0 + r, z0); sh.lineTo(x1 - r, z0); sh.quadraticCurveTo(x1, z0, x1, z0 + r); sh.lineTo(x1, z1 - r); sh.quadraticCurveTo(x1, z1, x1 - r, z1);
      sh.lineTo(x0 + r, z1); sh.quadraticCurveTo(x0, z1, x0, z1 - r); sh.lineTo(x0, z0 + r); sh.quadraticCurveTo(x0, z0, x0 + r, z0);
      const g = new THREE.ExtrudeGeometry(sh, { depth: h, bevelEnabled: false, curveSegments: 10 }); g.rotateX(Math.PI / 2);
      const m = new THREE.Mesh(g, c === '@table' && K.floorMap ? K.mat('#ffffff', { map: (() => { const t = K.floorMap('table'); t.repeat.set(0.25, 0.25); return t; })() }) : K.mat(c)); m.position.y = y; m.receiveShadow = true; return m;
    };
    const RIM = 1.6;
    for(const d of districts){
      group.add(slab(d.x0 - RIM, d.z0 - RIM, d.x1 + RIM, d.z1 + RIM, 2.2, 0.35, 0, '@table'));
      group.add(slab(d.x0 - RIM + 0.1, d.z0 - RIM + 0.1, d.x1 + RIM - 0.1, d.z1 + RIM - 0.1, 2.1, 1.3, -0.35, '@tableSide'));
      group.add(slab(d.x0 - RIM + 0.6, d.z0 - RIM + 0.6, d.x1 + RIM - 0.6, d.z1 + RIM - 0.6, 1.8, 1.5, -1.65, '@soil'));
    }
    const bridgeZ=ZS[1-R0];
    for(let i=1;i<districts.length;i++){
      const a=districts[i-1],b=districts[i],length=b.x0-a.x1+0.4,x=(a.x1+b.x0)/2;
      group.add(K.box(length,.18,2.4,'wood',x,-.08,bridgeZ));
      for(const z of [bridgeZ-1.25,bridgeZ+1.25]){group.add(K.box(length,.1,.09,'woodDark',x,.6,z));for(const end of [a.x1,b.x0])group.add(K.box(.12,.7,.12,'woodDark',end,0,z))}
    }
    const flat = (geo, c, y) => { const m = new THREE.Mesh(geo, c === '@path' && K.floorMap ? K.mat('#ffffff', { map: K.floorMap('path', geo.parameters.width || 8, geo.parameters.height || 8) }) : K.mat(c)); m.rotation.x = -Math.PI / 2; m.position.y = y || 0.012; m.receiveShadow = true; return m; };
    for(const d of districts){
      for(const x of XS.filter(x=>x>=d.x0&&x<=d.x1)){const st=flat(new THREE.PlaneGeometry(STREET*.48,d.z1-d.z0+STREET),'@path');st.position.set(x,.012,(d.z0+d.z1)/2);group.add(st)}
      for(const z of ZS.filter(z=>z>=d.z0&&z<=d.z1)){const st=flat(new THREE.PlaneGeometry(d.x1-d.x0+STREET,STREET*.48),'@path');st.position.set((d.x0+d.x1)/2,.013,z);group.add(st)}
    }
    group.add(K.cyl(Math.min(colW[0], rowH[0]) / 2 - 2.0, Math.min(colW[0], rowH[0]) / 2 - 1.9, 0.1, '@path', 0, 0, 0, { seg: 48 }));
    const night = theme === 'night', glowLines = [];
    const nightDecor = new THREE.Group(); nightDecor.userData.labNightOnly = true; nightDecor.visible = night; group.add(nightDecor);
    {
      const e = STREET / 2 - 0.3;
      const rim = K.mat('teal', { glow: 'teal', gi: 0.7 }), R0x = EXT.x0 - RIM + 0.25, R1x = EXT.x1 + RIM - 0.25, R0z = EXT.z0 - RIM + 0.25, R1z = EXT.z1 + RIM - 0.25;
      for (const [w, d, x, z] of [[R1x - R0x, 0.06, (R0x + R1x) / 2, R0z], [R1x - R0x, 0.06, (R0x + R1x) / 2, R1z], [0.06, R1z - R0z, R0x, (R0z + R1z) / 2], [0.06, R1z - R0z, R1x, (R0z + R1z) / 2]]) {
        if(districts.length===1){const m = new THREE.Mesh(new THREE.BoxGeometry(w, 0.03, d), rim); m.position.set(x, 0.36, z); nightDecor.add(m)}
      }
      for (const x of XS) for (const z of ZS) {
        if(!districts.some(d=>x>=d.x0&&x<=d.x1&&z>=d.z0&&z<=d.z1))continue;
        if (Math.hypot(x, z) < Math.min(colW[0], rowH[0]) / 2) continue;      // not on the plaza
        nightDecor.add(K.at(K.build('streetLamp'), x + e + 0.15, 0, z + e + 0.15));
      }
    }
    const taken = new Set(cells.map(c => c.join(',')));
    const flies = [];
    let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    for (let c = C0; c <= C1; c++) for (let w = R0; w <= R1; w++) {
      if(!districts.some(d=>c>=d.c0&&c<=d.c1&&w>=d.r0&&w<=d.r1))continue;
      if (taken.has(c + ',' + w)) continue;
      const pw = colW[c] - STREET, ph = rowH[w] - STREET; group.add(K.box(pw, 0.08, ph, '@grass', cx(c), 0, cz(w)));
      for (let i = 0; i < 5; i++) group.add(K.at(K.build('tree', { size: 0.8 + rnd() * 0.6, v: Math.floor(rnd() * 4) }), cx(c) + (rnd() - 0.5) * (pw - 2), 0.08, cz(w) + (rnd() - 0.5) * (ph - 2)));
      if (L.components.flowers) for (let i = 0; i < 6; i++) group.add(K.at(K.build('flowers', { hue: i, n: 5 + (i % 3) }), cx(c) + (rnd() - 0.5) * (pw - 1.5), 0.08, cz(w) + (rnd() - 0.5) * (ph - 1.5)));
      if (L.components.rock) for (let i = 0; i < 3; i++) group.add(K.at(K.build('rock', { size: 0.7 + rnd() * 0.8 }), cx(c) + (rnd() - 0.5) * (pw - 1.5), 0.08, cz(w) + (rnd() - 0.5) * (ph - 1.5), rnd() * 6));
      for (let i = 0; i < 14; i++) flies.push([cx(c) + (rnd() - 0.5) * (pw - 1), 0.5 + rnd() * 1.6, cz(w) + (rnd() - 0.5) * (ph - 1), rnd() * 6.28]);
    }
    let fireflies = null;
    if (flies.length) {
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(flies.flatMap(f => f.slice(0, 3)), 3));
      fireflies = new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xd8ff9a, size: 0.2, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false }));
      fireflies.userData.seed = flies; nightDecor.add(fireflies);
    }
    for(const edge of districts)for (let i = 0; i < 10; i++) { const sd = i % 4, u = rnd(); const x = sd < 2 ? edge.x0 + u * (edge.x1 - edge.x0) : (sd === 2 ? edge.x0 - RIM * 0.55 : edge.x1 + RIM * 0.55), z = sd < 2 ? (sd ? edge.z1 + RIM * 0.55 : edge.z0 - RIM * 0.55) : edge.z0 + u * (edge.z1 - edge.z0);if(Math.abs(z)<2)continue; group.add(K.at(K.build('tree', { size: 0.6 + rnd() * 0.45, v: Math.floor(rnd() * 4) }), x, 0, z)); }
    // your desk, Newt at it, the inbox tray
    const hub = K.build('hubDesk'); hub.userData.pick = { kind: 'hub' }; group.add(hub); pickables.add(hub);
    const inbox = new THREE.Group(); inbox.position.set(0.55, 0.98, 0.1); group.add(inbox);
    const bigNewt = L.makeNewt(K, { scale: 1.4 }); bigNewt.group.position.set(0, 0.12, -1.0); bigNewt.group.userData.pick = { kind: 'newt' }; group.add(bigNewt.group); pickables.add(bigNewt.group);
    // the rooms
    const reused=new Set();
    for(const o of Object.values(rooms)){
      const old=previousRooms[o.id];
      if(old&&old.renderTheme===theme&&JSON.stringify(old.spec)===JSON.stringify(o.spec)&&JSON.stringify(old.extraProps)===JSON.stringify(o.extraProps)){
        for(const key of ['g','floor','floorMat','floorBase','walls','rising'])o[key]=old[key];o.g.position.set(o.x,0,o.z);o.g.rotation.y=o.ry;group.add(o.g);pickables.add(o.floor);recolor(o.g);reused.add(o.id);
      }else buildRoom(o,group);
      o.renderTheme=theme;
    }
    for(const [id,o]of Object.entries(previousRooms))if(!reused.has(id))L.resources.release(o.g);
    // checkpoints: a diamond lantern at the door of the room a study waits in for each one (on the street for a
    // `before` checkpoint, just inside for a `during` one). Unlit until a study waits; amber while one does.
    const gates = {};
    const lit = {};
    for (const district of districts) for (const w of wf.workflows || []) for (const c of w.checkpoints || []) {
      const key=district.id==='local'?c.id:'machine/'+encodeURIComponent(district.id)+'/'+c.id;
      if (gates[key]) continue;
      const st = w.path || w.steps || [], at = c.during || (w.nodes ? c.before : st[st.indexOf(c.before) - 1]);
      const grouped = w.nodes?.[at]?.room;
      const candidates=Object.values(rooms).filter(o=>(o.machine||'local')===district.id);
      const host = (grouped && candidates.find(o=>o.base.id===grouped)) || candidates.find(o => (o.states || []).includes(at));
      if (!host) continue;
      const k = lit[host.id] = (lit[host.id] || 0) + 1, f = c.during ? 0.9 : 0.35, side = (k - 1) * 0.9 - 0.45;
      const dx = host.door[0] - host.street[0], dz = host.door[1] - host.street[1], len = Math.hypot(dx, dz) || 1;
      const p = [host.street[0] + dx * f + (-dz / len) * side * (k > 1 ? 1 : 0), host.street[1] + dz * f + (dx / len) * side * (k > 1 ? 1 : 0)];
      const lantern = K.build('lantern'); lantern.position.set(p[0], 0, p[1]); lantern.rotation.y = host.ry;
      lantern.userData.pick = { kind: 'checkpoint', id: c.id, machine:district.id }; group.add(lantern); pickables.add(lantern);
      const lamp = lantern.userData.lamp;
      gates[key] = { arch: lantern, lamp, g: c, pos: p, host, machine:district.id };
    }
    group.traverse(m => { if (m.isMesh && m.geometry && m.geometry.type === 'PlaneGeometry') m.castShadow = false; });
    W = { group, rooms, districts, bridgeZ, XS, ZS, colW, rowH, EXT, SPAN, hub, inbox, bigNewt, gates, sun, fireflies, glowLines, hubExits: Object.values(DIR).map(d => [d[0] * colW[0] / 2, d[1] * rowH[0] / 2]) };
    buildNeighbours();
    fitCamera(true);
    return true;
  }

  // ── what agents made for you: a sheet pinned on a little board in the room the work happened in (amber when it
  // asks you something); opened artifacts come down. Click one to read it.
  let sheetGroup = null, sheetSig = '';
  function pinSheets(s) {
    if (!W) return;
    const runs = new Map(((s && s.runs) || []).map(r => [r.run_id, r]));
    const where = a => {
      const r = a.run_id && runs.get(a.run_id);
      if (r) { const rid = placeOfRun(s, r); if (W.rooms[rid]) return rid; }
      const it = a.study && item(s, a.study), rid = it && roomOfItem(s, it);
      return rid && W.rooms[rid] ? rid : null;
    };
    const up = ((s && s.artifacts) || []).filter(a => !a.answered && (!a.seen || a.question)).slice(0, 30).map(a => ({ a, room: where(a) })).filter(x => x.room);
    const sig = JSON.stringify([staticSig, up.map(x => [x.a.id, x.room, !!x.a.question])]);
    if (sig === sheetSig && sheetGroup) return;
    sheetSig = sig;
    if (sheetGroup) { L.resources.release(sheetGroup); sheetGroup.traverse(o => pickables.delete(o)); }
    sheetGroup = new THREE.Group(); scene.add(sheetGroup);
    const byRoom = {};
    up.forEach(x => (byRoom[x.room] = byRoom[x.room] || []).push(x.a));
    for (const [rid, list] of Object.entries(byRoom)) {
      const o = W.rooms[rid], [w, d] = o.spec.size, n = Math.min(list.length, 4);
      const board = K.group(K.cyl(0.04, 0.04, 1.3, 'woodDark', -0.75, 0, 0), K.cyl(0.04, 0.04, 1.3, 'woodDark', 0.75, 0, 0), K.box(1.7, 0.95, 0.06, 'woodLight', 0, 0.75, 0));
      const [bx, bz] = o.toWorld(w / 2 - 1.3, d / 2 - 0.45);
      board.position.set(bx, 0, bz); board.rotation.y = o.ry; sheetGroup.add(board);
      list.slice(0, n).forEach((a, i) => {
        const sh = K.group(K.box(0.34, 0.44, 0.02, a.question ? 'amber' : 'paper', 0, 0, 0, a.question ? { glow: true, gi: {day:0.25,night:0.8} } : null),
          K.sphere(0.045, a.question ? 'red' : 'teal', 0, 0.4, 0.03));
        sh.position.set(-0.55 + i * 0.37, 0.98 + (i % 2) * 0.06, 0.05); sh.rotation.z = (i % 2 ? -1 : 1) * 0.06;
        sh.userData.pick = { kind: 'artifact', id: a.id }; board.add(sh); pickables.add(sh);
      });
      if (list.length > n) board.add(K.sphere(0.1, 'amber', 0.78, 1.32, 0.05, { glow: true }));
    }
  }

  // ── your other labs (this computer's and other machines', all in this one dashboard): small tables beyond the
  // back edge, a bridge to each — its name, what waits on you there, how many agents are at work. Click to go.
  let neighbours = [], nbGroup = null, nbSig = '';
  function buildNeighbours() {
    if (!W) return;
    const sig = JSON.stringify([theme, W.EXT, neighbours.map(n => [n.key, n.needs, n.running, n.state])]);
    if (sig === nbSig && nbGroup) return;
    nbSig = sig;
    if (nbGroup) { L.resources.release(nbGroup); nbGroup.traverse(o => pickables.delete(o)); }
    nbGroup = new THREE.Group(); scene.add(nbGroup);
    const list = neighbours.slice(0, 6), E = W.EXT, wide = E.x1 - E.x0, step = Math.min(22, (wide + 16) / Math.max(1, list.length));
    list.forEach((nb, i) => {
      const x = (E.x0 + E.x1) / 2 + (i - (list.length - 1) / 2) * step, z = E.z0 - 11;   // spread along the back edge
      const g = new THREE.Group(); g.position.set(x, 0, z);
      const off = nb.state !== 'here' && nb.state !== 'connected';
      g.add(K.box(9, 0.3, 6, off ? '@tableSide' : '@table', 0, -0.3, 0), K.box(8.6, 1.0, 5.6, '@tableSide', 0, -1.3, 0));
      [[-2.6, -1.2], [0, -1.4], [2.6, -1.1], [-1.4, 1.2], [1.6, 1.3]].forEach(([a, b], k) => g.add(K.box(2.0, 0.55 + (k % 2) * 0.2, 1.6, off ? 'plasterDark' : 'plaster', a, 0, b)));
      for (let k = 0; k < Math.min(8, nb.running || 0); k++) g.add(K.sphere(0.22, 'teal', -3 + k * 0.85, 1.05, 2.3, { glow: true }));   // agents at work
      if (nb.needs) { const f = K.group(K.cyl(0.05, 0.05, 2.2, 'woodDark', 0, 0, 0), K.box(0.9, 0.55, 0.05, 'amber', 0.47, 1.6, 0, { glow: true })); f.position.set(3.6, 0, -2.2); g.add(f); }
      const bridge = K.box(1.4, 0.18, 11 - 3 - 1.6, '@table', 0, -0.12, 3 + (11 - 3 - 1.6) / 2 - 0.4); g.add(bridge);
      g.userData.pick = { kind: 'otherlab', key: nb.key };
      g.traverse(o => { if (o.isMesh) o.castShadow = false; });
      nbGroup.add(g); pickables.add(g); nb._at = [x, z];
    });
  }

  function buildRoom(o, group) {
    const sp = o.spec, [w, d] = sp.size, g = new THREE.Group();
    g.position.set(o.x, 0, o.z); g.rotation.y = o.ry; group.add(g); o.g = g;
    o.floorMat = K.mat(sp.floor === 'grass' ? '@grass' : sp.floor).clone();
    if (K.floorMap && ['boards', 'tiles', 'grass'].includes(sp.floor)) { o.floorMat.map = K.floorMap(sp.floor === 'grass' ? 'grass' : sp.floor, w, d); o.floorMat.color.set('#ffffff'); o.floorMat.userData.labColor = '#ffffff'; o.floorMat.needsUpdate = true; }
    o.floorBase = o.floorMat.color.clone();
    const fl = new THREE.Mesh(new THREE.BoxGeometry(w, 0.14, d), o.floorMat); fl.position.y = 0.07; fl.receiveShadow = true; fl.userData.pick = { kind: 'room', id: o.id }; g.add(fl); pickables.add(fl); o.floor = fl;
    const trim = { glow: sp.accent, gi: {day:0,night:0.55} };
    g.add(K.box(w, 0.05, 0.22, sp.accent, 0, 0.14, d / 2 - 0.11, trim));
    o.walls = [];
    const wallH = 1.5;
    if(sp.shell)for(const s of sp.shell){const wall=K.box(...s.size,sp.wall||'plaster',s.at[0],.14+s.at[1]-s.size[1]/2,s.at[2]);wall.userData.physicsSolid=true;g.add(wall);}
    if (!sp.shell&&sp.walls !== false) for (const [lx, lz, len, nx, nz] of [[0, -d / 2, w, 0, -1], [-w / 2, 0, d, -1, 0], [w / 2, 0, d, 1, 0]]) {
      const wall = K.box(nz ? len : 0.16, wallH, nz ? 0.16 : len, sp.wall || 'plaster', lx, 0.14, lz); g.add(wall);
      const cap = K.box(nz ? len + 0.02 : 0.2, 0.06, nz ? 0.2 : len + 0.02, sp.accent, lx, 0.14 + wallH + 0.0, lz, trim); g.add(cap);
      o.walls.push({ wall, cap, n: [nx, nz], lx, lz, h: wallH });
    }
    const sign = K.sign(o.title, { h: 0.42 }); sign.position.set(0, 1.25, -d / 2 + 0.1); g.add(sign);
    if (knownRooms.size && !knownRooms.has(o.id) && !reduced) { g.scale.y = 0.02; o.rising = true; }   // a new room rises out of the table
    knownRooms.add(o.id);
    for (const p of (sp.props || []).concat(o.extraProps)) { const m = K.build(p.c, p.props); m.position.set(p.at[0], 0.14, p.at[1]); m.rotation.y = p.rot || 0; g.add(m); }
    g.add(K.box(Math.min(3.4, w * 0.4), 0.42, 0.5, 'woodLight', o.shelfAt[0] + Math.min(3.4, w * 0.4) / 2, 0.14, o.shelfAt[1]));
    const pl = new THREE.PointLight(0xffc98a, 18, 11, 1.5); pl.userData.labNightIntensity=18; pl.visible=theme==='night'; pl.position.set(0, 2.8, 0); g.add(pl);
  }

  // ── streets: a walk between any two places ───────────────────────────────────────────────────────
  const near = (v, arr) => arr.reduce((a, b) => (Math.abs(b - v) < Math.abs(a - v) ? b : a));
  const onX = p => W.XS.some(x => Math.abs(p[0] - x) < 1e-6);
  const corner = p => (onX(p) ? [p[0], near(p[1], W.ZS)] : [near(p[0], W.XS), p[1]]);
  function streetPath(p, q) {
    const a=corner(p),b=corner(q),district=p=>W.districts.find(d=>p[0]>=d.x0-.01&&p[0]<=d.x1+.01);
    const cross=district(p)!==district(q),pts=cross?[p,a,[a[0],W.bridgeZ],[b[0],W.bridgeZ],b,q]:[p,a,[b[0],a[1]],b,q],out=[];
    for(const x of pts)if(!out.length||Math.hypot(x[0]-out[out.length-1][0],x[1]-out[out.length-1][1])>.01)out.push(x);
    return out;
  }
  const hubExit = to => W.hubExits.reduce((a, b) => (Math.hypot(b[0] - to[0], b[1] - to[1]) < Math.hypot(a[0] - to[0], a[1] - to[1]) ? b : a));
  /** from a place to a place — {room: a room id | 'hub' | 'street', at: [x, z]}: out of the door, along the
   *  streets, in at the other door (a newt already on the street goes on from where it is) */
  function route(from, to) {
    const inside = (room, a, b) => M.pathInRoom(room.spec, room.toLocal(...a), room.toLocal(...b)).map(p => room.toWorld(...p));
    if (from.room === to.room && from.room !== 'street') return W.rooms[from.room] ? inside(W.rooms[from.room], from.at, to.at) : [to.at];
    const A = W.rooms[from.room], B = W.rooms[to.room];
    const p1 = A ? A.street : from.room === 'hub' ? hubExit(B ? B.street : [0, 0]) : from.at;
    const p2 = B ? B.street : hubExit(p1);
    const at = (p, room) => Object.assign(p.slice(), { enter: room });     // passing this point, it is in `room`
    const streets = streetPath(p1, p2).map((p, i) => (i ? p.slice() : at(p, 'street')));
    return [...(A ? [at(A.door, 'street')] : []), ...streets, ...(B ? [at(B.door, to.room), ...inside(B, B.door, to.at).map(p => at(p, to.room))] : [at(to.at, to.room)])];
  }

  // ── who should be where, from the snapshot ───────────────────────────────────────────────────────
  const item = M.item, roomOfItem = (s, it) => M.roomOfItem(s, it, W.rooms);
  const placeOfRun = (s, r) => M.placeOfRun(s, r, W.rooms);
  const ACTS = M.ACTS;
  // calls come and go faster than a newt can walk: an agent keeps to what it is at for a moment before it walks off to
  // the next thing, and between two calls it stays where it was
  const DWELL = 8000, LINGER = 20000, shown = new Map();
  function shownKind(id, kind) {
    const now = Date.now();
    let cur = shown.get(id);
    if (!cur) { cur = { kind, at: now, seen: now }; shown.set(id, cur); return kind; }
    if (kind) cur.seen = now;
    const want = kind || (now - cur.seen < LINGER ? cur.kind : null);
    if (want !== cur.kind && now - cur.at >= DWELL) { cur.kind = want; cur.at = now; }
    return cur.kind;
  }
  /** who should be where: every agent in the snapshot's `agents` (a run's main agent and its subagents, and any
   *  session no run accounts for) stands in its room at the furniture for what it is doing right now — a shelf to
   *  read, a bench to run an experiment, a desk to write, a whiteboard to brief a subagent — else at its own
   *  station; a subagent comes out of its parent and goes back to it when it is done */
  function desired(s) {
    const want = new Map(), used = {};
    const spot = (roomId, key, { kind, prefer, role }) => {
      const o = W.rooms[roomId], u = (used[roomId] = used[roomId] || new Set()), off = hash01(key), cands = [];
      const add = (list) => { const n = list.length, k0 = Math.floor(off * n); for (let i = 0; i < n; i++) cands.push(list[(i + k0) % n]); };
      if (kind && o.uses[kind]) add(o.uses[kind]);                      // the furniture for what it is doing
      if (prefer && o.st[prefer]) cands.push(o.st[prefer]);              // its procedure's own station
      if (role && o.spec.roleStation[role]) cands.push(o.spec.roleStation[role]);   // its role's
      add(o.spots);                                                      // somewhere to stand
      const id = p => p[0].toFixed(1) + ',' + p[1].toFixed(1);
      const mine = actors.get(key), here = mine && mine.dest && mine.dest.room === roomId ? mine.dest.spot : null;
      const pick = (here && cands.find(p => id(p) === here && !u.has(here))) || cands.find(p => !u.has(id(p))) || cands[cands.length - 1];
      u.add(id(pick)); const [x, z] = o.toWorld(pick[0], pick[1]);
      return { room: roomId, at: [x, z], ry: o.ry + (pick[2] ?? Math.PI), spot: id(pick) };
    };
    let queue = 0;
    const deskSlot = () => { const k = queue++, th = Math.PI + (k - 3) * 0.42, x = 2.6 * Math.sin(th), z = -2.6 * Math.cos(th); return { room: 'hub', at: [x, z], ry: Math.atan2(-x, -z) }; };
    const list = s.agents || [];
    for (const ag of list) {
      const p = M.placeAgent(s, ag, W.rooms), sub = !!ag.parent, kind = shownKind(ag.id, p.kind);
      const target = p.desk ? deskSlot() : spot(p.room, ag.id, { kind, prefer: sub ? null : p.run?.workflow_node?'task:'+p.run.workflow_node:ag.skill, role: ag.role });
      want.set(ag.id, { key: ag.id, kind: sub ? 'sub' : 'main', hue: Math.floor(hash01(rootOf(list, ag)) * 12) * 30,
        badge: ROLE_BADGE[ag.role] || (sub ? ROLE_BADGE['general-purpose'] : ROLE_BADGE.orchestrator), scale: sub ? SUB_SCALE : 1,
        parent: ag.parent, target, pose: p.pose, act: kind, agent: ag, run: p.run, room: p.room });
    }
    for (const id of [...shown.keys()]) if (!want.has(id)) shown.delete(id);
    return want;
  }
  /** an agent's family: its run, or the session it is part of (a subagent wears its root's colours) */
  function rootOf(list, ag) {
    if (ag.run_id) return ag.run_id;
    let a = ag, seen = 0;
    while (a.parent && seen++ < 8) { const p = list.find(x => x.id === a.parent); if (!p) break; a = p; }
    return a.worker_id || a.id;
  }

  // ── actors: arlo (or the cast you chose) walking to where they should be ────────────────────────
  // the cast: one character for every agent, or one per tool (Claude, Codex, opencode) so you can tell them apart
  let cast = Object.assign({ mode: 'backend', one: 'newt', claude: 'newt', codex: 'human', opencode: 'robot' }, opts.cast || {});
  const characterOf = spec => {
    const be = (spec.agent && spec.agent.backend) || (spec.run && spec.run.backend) || '';
    const id = cast.mode === 'one' ? cast.one : (cast[be] || cast.one || 'newt');
    return (L.LIBRARY_CHARACTERS||L.CHARACTERS).some(c=>c.id===id)?id:'newt';
  };
  const body = (spec, detail) => {
    const previousDetail = K.detail; K.detail = detail || detailFor(null);
    const n = L.makeCharacter ? L.makeCharacter(K, characterOf(spec), { color: spec.badge, hue: spec.hue, scale: spec.scale * 1.25, seed: spec.key })
      : L.makeNewt(K, { color: spec.badge, hue: spec.hue, scale: spec.scale * 1.25, seed: spec.key });
    n.hit = new THREE.Mesh(K.geometry('BoxGeometry', 1.2, 1.8, 0.9), new THREE.MeshBasicMaterial()); n.hit.visible = false;
    n.hit.position.y = 0.85; n.hit.userData.pick = { kind: 'actor', key: spec.key }; n.group.add(n.hit); n.detail = K.detail; K.detail = previousDetail; L.resources.track(n.group); return n;
  };
  function refreshCast() {
    for (const a of actors.values()) {
      const id=characterOf(a.spec);
      if(a.n.character===id)continue;
      const old=a.n,n=body(a.spec);n.character=id;
      if(old.update.snapshot&&n.update.restore)n.update.restore(old.update.snapshot());
      n.group.position.copy(old.group.position);n.group.rotation.copy(old.group.rotation);n.group.scale.copy(old.group.scale);
      n.group.userData.pick=old.group.userData.pick;
      L.resources.release(old.group);pickables.delete(old.hit||old.group);scene.add(n.group);pickables.add(n.hit||n.group);a.n=n;
    }
  }
  function makeActor(spec, from) {
    const n = body(spec); L.resources.track(n.group);
    n.character = characterOf(spec);
    n.group.userData.pick = { kind: 'actor', key: spec.key }; scene.add(n.group); pickables.add(n.hit || n.group);
    const a = { key: spec.key, spec, n, room: from.room, pos: from.at.slice(), ry: from.ry || 0, path: [], fade: 0, leaving: false };
    return a;
  }
  function sendTo(a, target) {
    if (motion() !== 'full') { a.pos = target.at.slice(); a.ry = target.ry || 0; a.room = target.room; a.dest = target; a.path = []; return; }
    a.path = route({ room: a.room, at: a.pos }, target);
    a.dest = target;
  }
  function reconcile(s) {
    const want = desired(s);
    for (const [key, spec] of want) {
      let a = actors.get(key);
      if (!a) {
        const parent = spec.parent && actors.get(spec.parent);
        const from = parent ? { room: parent.room, at: parent.pos.slice() } : { room: 'hub', at: [0, 1.8] };
        a = makeActor(spec, from); actors.set(key, a); sendTo(a, spec.target);
      } else if (a.leaving || !a.dest || a.dest.room !== spec.target.room || Math.hypot(a.dest.at[0] - spec.target.at[0], a.dest.at[1] - spec.target.at[1]) > 0.3) {
        a.leaving = false; sendTo(a, spec.target);
      }
      a.spec = spec;
    }
    for (const [key, a] of actors) if (!want.has(key) && !a.leaving && !a.courier) {
      a.leaving = true;
      const home = a.spec.kind === 'sub' && actors.get(a.spec.parent);
      if (a.spec.kind === 'sub') { if (home && !home.leaving) sendTo(a, { room: home.room, at: home.pos.slice(), ry: 0 }); else a.path = []; }
      else sendTo(a, { room: 'hub', at: [0, 2.2], ry: 0 });
    }
    pinSheets(s);
    // studies: their card on the shelf, at its gate, or carried to its new room
    for (const it of s.items || []) {
      const rid = roomOfItem(s, it); let c = cards.get(it.id);
      if (!c) c = makeCard(it);
      const prev = c.userData.room;
      c.userData.room = rid; c.userData.gate = Object.keys(W.gates).find(key=>(it.waiting||[]).includes(W.gates[key].g.id)&&W.gates[key].g.before&&W.gates[key].machine===(snap.world_view==='full'?it.machine||'local':'local')) || null;
      if (prev && rid && prev !== rid && W.rooms[prev] && W.rooms[rid] && !reduced) carry(it, prev, rid);
    }
    for (const id of [...cards.keys()]) if (!item(s, id)) { L.resources.release(cards.get(id)); cards.delete(id); }
  }
  function makeCard(it) {
    const hue = Math.floor(hash01(it.id + 'hue') * 12) * 30;
    const m = new THREE.MeshStandardMaterial({ color: new THREE.Color(`hsl(${hue}, 55%, 60%)`), roughness: 0.6, emissive: new THREE.Color(`hsl(${hue}, 60%, 40%)`), emissiveIntensity: theme === 'night' ? 0.35 : 0 });
    const c = new THREE.Group(); const b = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.09, 0.4), m); b.castShadow = true; c.add(b);
    const lab = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.012, 0.1), K.mat('paper')); lab.position.set(-0.04, 0.05, -0.08); c.add(lab);
    c.userData = { pick: { kind: 'card', id: it.id }, id: it.id, cardMaterial: m }; scene.add(c); pickables.add(c); cards.set(it.id, c);
    return c;
  }
  function carry(it, fromRoom, toRoom) {
    const A = W.rooms[fromRoom], B = W.rooms[toRoom], key = `carry:${it.id}:${Date.now()}`;
    const spec = { key, kind: 'courier', hue: Math.floor(hash01(it.id + 'hue') * 12) * 30, badge: null, scale: 1, pose: 'carry' };
    const a = makeActor(spec, { room: fromRoom, at: A.door.slice() }); a.courier = it.id; actors.set(key, a);
    sendTo(a, { room: toRoom, at: B.door.slice(), ry: B.ry + Math.PI });
    a.path.pop();                         // stop at the door; the card goes onto the shelf
    cards.get(it.id).userData.carrier = key;
  }

  const detailFor = current => opts.quality === 'high' || opts.quality === 'low' ? opts.quality : cam.r > 65 ? 'low' : cam.r < 25 ? 'high' : cam.r > 35 && cam.r < 55 ? 'medium' : current || 'medium';
  const locomotion = id => ({ frog: 'hop', bee: 'hover', snail: 'glide', penguin: 'waddle' }[id] || 'walk');
  function recolor(root) { if (K) K.setLook(null, root); }
  function applyLights() {
    const lights = scene.children.filter(o => o.isLight);
    const hemi = lights.find(o => o.isHemisphereLight), sun = lights.find(o => o.isDirectionalLight && o.castShadow), fill = lights.find(o => o.isDirectionalLight && !o.castShadow);
    if (hemi) { hemi.intensity = TH.hemi; hemi.color.set(TH.hemiColor); hemi.groundColor.set(TH.groundColor); }
    if (sun) { sun.intensity = TH.sun; sun.color.set(TH.sunColor); } if (fill) { fill.intensity = TH.fill ?? 0.4; fill.color.set(TH.fillColor); }
    renderer.toneMappingExposure = TH.exposure;
  }
  function unsettled() {
    return [...actors.values()].some(a => a.path.length || a.leaving || a.fade > 0)
      || Object.keys(cam).some(k => Math.abs(cam[k] - camT[k]) > 0.002)
      || (W && Object.values(W.rooms).some(o => o.rising));
  }
  // ── the camera: the whole table, or one room; it keeps clear of the rail and the ask bar ──────────
  const cam = { az: 0, el: 0.92, r: 80, tx: 0, tz: 0 }, camT = { ...cam };
  let insets = { right: 0, left: 0, bottom: 0, top: 56, k: 0.5 };
  const nbRoom = () => (neighbours.length ? 14 : 0);   // the back edge's other labs need a little more of the view
  function fitCamera(snapNow) {
    if (!W) return;
    const r = canvas.getBoundingClientRect(), wide = r.width - insets.right - insets.left, aspect = Math.max(0.3, wide / Math.max(1, r.height - insets.top - insets.bottom * insets.k)), base = W.SPAN * 3.5 * Math.max(1, 1.4 / aspect, 1.25 * r.height / Math.max(1, wide));   // (narrow screens: fit the width)
    if (view.level === 'ROOM' && W.rooms[view.room]) { const o = W.rooms[view.room]; Object.assign(camT, { tx: o.x, tz: o.z, r: Math.max(o.spec.size[0], 10) * 2.0, az: Math.atan2(o.dir[0], o.dir[1]), el: 0.95 }); }
    else Object.assign(camT, { tx: (W.EXT.x0 + W.EXT.x1) / 2, tz: (W.EXT.z0 - nbRoom() + W.EXT.z1) / 2 + 1, r: base * (1 + nbRoom() / Math.max(10, W.EXT.z1 - W.EXT.z0) * 0.75), el: 0.92, az: camT.az && view.level === 'WORLD' ? camT.az : 0 });
    if (snapNow || motion() !== 'full') Object.assign(cam, camT);
  }
  // the room the UI leaves the world: a column on the left (a lens), the instrument rail on the right
  // along the bottom. The camera centres the table in what is left.
  function measureInsets() {
    const rail = document.querySelector('[data-world-inset="right"]'), col = document.querySelector('[data-world-inset="left"]');
    const bar = document.querySelector('[data-world-inset="bottom"]');
    const rr = rail ? rail.getBoundingClientRect() : null, lr = col ? col.getBoundingClientRect() : null;   // (fixed: measure it)
    const sheet = lr && lr.width > innerWidth * 0.6;          // on a phone the lens is a sheet along the bottom
    const bh = bar ? Math.max(0, innerHeight - bar.getBoundingClientRect().top) : 0;
    insets = sheet ? { right: 0, left: 0, bottom: Math.min(innerHeight * 0.55, innerHeight - lr.top), top: 100, k: 1, cut: lr.top - 8 }
      : { right: rr && rr.width ? rr.width + 12 : 0, left: lr && lr.width ? lr.right + 12 : 0, bottom: bh, top: 72, k: 0.5, cut: innerHeight - bh };
  }
  function setViewState(level, room) {
    view = { level, room: room || null, label: room && W && W.rooms[room] ? W.rooms[room].title : '' };
    fitCamera(false); if (onView) onView({ level: level === 'ROOM' ? 'REGION' : 'WORLD', room, label: view.label }); kick();
  }

  // ── input: drag to turn, wheel to zoom, hover to read, click to open ──────────────────────────────
  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
  let drag = null, hovered = null;
  function pickAt(x, y) {
    const r = canvas.getBoundingClientRect(); mouse.set((x - r.left) / r.width * 2 - 1, -((y - r.top) / r.height) * 2 + 1); ray.setFromCamera(mouse, camera);
    const hits = ray.intersectObjects([...pickables].filter(p => p.visible !== false || (p.userData.pick && p.userData.pick.kind === 'actor')), true);
    for (const h of hits) { let o = h.object; while (o && !o.userData.pick) o = o.parent; if (o) return o.userData.pick; }
    return null;
  }
  const blocked = e => e.target !== canvas;
  listen(window, 'pointerdown', e => { if (blocked(e) || e.button !== 0) return; drag = { x: e.clientX, y: e.clientY, az: camT.az, el: camT.el, moved: false }; });
  listen(window, 'pointerup', e => { if (drag && !drag.moved && !blocked(e)) click(pickAt(e.clientX, e.clientY)); drag = null; });
  listen(window, 'pointermove', e => {
    if (drag) { const dx = e.clientX - drag.x, dy = e.clientY - drag.y; if (Math.abs(dx) + Math.abs(dy) > 4) drag.moved = true; camT.az = drag.az - dx * 0.006; camT.el = clamp(drag.el + dy * 0.004, 0.35, 1.35); kick(); }
    if (blocked(e)) { tip.style.display = 'none'; canvas.style.cursor = ''; hovered = null; return; }
    const was = hovered && (hovered.key || hovered.kind);
    hovered = pickAt(e.clientX, e.clientY); canvas.style.cursor = hovered ? 'pointer' : '';
    if (hovered && hovered.kind === 'actor' && hovered.key !== was) poke(hovered.key, false);
    if (hovered && hovered.kind === 'newt' && was !== 'newt' && W) { W.bigNewt.poke = performance.now() / 1000; kick(); }
    const html = hovered && describe(hovered);
    if (!html) { tip.style.display = 'none'; return; }
    tip.innerHTML = html; tip.style.display = 'block'; tip.style.left = Math.min(innerWidth - 330, e.clientX + 16) + 'px'; tip.style.top = (e.clientY + 14) + 'px';
  });
  listen(canvas, 'wheel', e => { e.preventDefault(); if (!W) return; camT.r = clamp(camT.r * (1 + Math.sign(e.deltaY) * 0.1), 9, W.SPAN * 4); kick(); }, { passive: false });
  listen(window, 'pointercancel', () => { drag = null; });
  canvas.tabIndex = 0; canvas.setAttribute('aria-label', 'World: use arrow keys to select, Enter to open, Escape for the overview');
  let selected = -1;
  listen(canvas, 'keydown', e => {
    const choices = [...new Set([...pickables].map(o => o.userData.pick).filter(Boolean))];
    if (e.key === 'Escape') { setViewState('WORLD'); tip.style.display = 'none'; kick(); }
    else if (e.key === 'Enter' && choices[selected]) { e.preventDefault(); click(choices[selected]); }
    else if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key) && choices.length) {
      e.preventDefault(); selected = (selected + (e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 1) + choices.length) % choices.length;
      tip.innerHTML = describe(choices[selected]) || ''; tip.style.display = 'block'; tip.style.left = '16px'; tip.style.top = '80px';
    }
  });
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(() => resize()) : null;
  if (observer) { observer.observe(canvas); listeners.push(() => observer.disconnect()); }
  let contextLost = false;
  listen(canvas, 'webglcontextlost', e => { e.preventDefault(); contextLost = true; if (raf) cancelAnimationFrame(raf); raf = 0; });
  listen(canvas, 'webglcontextrestored', () => { contextLost = false; last = performance.now(); kick(); });
  /** someone looked at an agent: it waves (and hops, when clicked) */
  function poke(key, hop) { const a = actors.get(key); if (a && !a.leaving) { a.poke = performance.now() / 1000; a.hop = hop; kick(); } }
  function click(p) {
    if (!p) return;
    if (p.kind === 'actor') poke(p.key, true);
    if (p.kind === 'room') { if (view.level === 'ROOM' && view.room === p.id) return; setViewState('ROOM', p.id); return; }
    if (p.kind === 'card' && onItem) return onItem(p.id);
    if (p.kind === 'hub' && onInbox) return onInbox();
    if (p.kind === 'newt' && onNewt) return onNewt();
    if (p.kind === 'otherlab' && onLab) return onLab(p.key);
    if (p.kind === 'artifact' && onArtifact) return onArtifact(p.id);
    if (p.kind === 'checkpoint') { const it = ((snap && snap.items) || []).find(i => (i.waiting || []).includes(p.id)&&(snap.world_view!=='full'||(i.machine||'local')===p.machine));
      if (it && onCheckpoint) return onCheckpoint(it.id, p.id); if (it && onItem) return onItem(it.id); }
    if (p.kind === 'actor') {
      const a = actors.get(p.key); if (!a) return;
      const ag = a.spec.agent;
      if (ag && ag.run_id && onRun) return onRun(ag.run_id, ag.sub || null);
      if (ag && ag.worker_id && onWorker) return onWorker(ag.worker_id);
      if (a.courier && onItem) return onItem(a.courier);
    }
  }
  /** what an agent is doing, in a line: the call it is in (with its activity's sign), else what it did last */
  function doing(spec) {
    const ag = spec.agent, r = spec.run;
    if (!ag) return '';
    if (r && !ag.parent) {
      if (r.status === 'waiting_input') return '? ' + ((r.pending_question && (r.pending_question.question || r.pending_question.text)) || 'a question for you');
      if (r.status === 'queued') return 'queued · starts when a slot frees';
      if ((r.pending_permissions || []).length) return '✋ asks to ' + ((r.pending_permissions[0].tool) || 'do something') + ' · Needs you';
    }
    const d = ag.doing, act = d && ACTS[d.kind];          // (the sign of the call itself; where it stands may lag a moment)
    if (d) return `${act ? act[0] + ' ' : ''}${d.summary || d.tool || (act && act[1]) || ''}`;
    return ag.last || ag.said || ag.label || ag.role || '';
  }
  function describe(p) {
    const s = snap || {};
    if (p.kind === 'artifact') { const a = ((snap && snap.artifacts) || []).find(x => x.id === p.id); return a ? `<b>${esc(a.title)}</b>${a.question ? `<small>${esc(a.question)}</small>` : ''}` : null; }
    if (p.kind === 'otherlab') { const nb = neighbours.find(n => n.key === p.key); return nb ? `<b>${esc(nb.name)}</b>${nb.needs ? `<small>${nb.needs} need${nb.needs === 1 ? 's' : ''} you</small>` : ''}` : null; }
    if (p.kind === 'actor') {
      const a = actors.get(p.key); if (!a) return null;
      if (a.courier) { const it = item(s, a.courier); return `<b>Carrying “${esc(it ? it.title || it.id : a.courier)}”</b><small>to its next room</small>`; }
      const sp = a.spec, r = sp.run, ag = sp.agent || {};
      const on = r && (r.subject || (r.target !== 'hub' ? r.target : '')), it0 = on && item(s, on);
      const who = ag.display_label ? esc(ag.display_label) : ag.parent ? esc(ag.label || ag.role || 'subagent') : r ? `${esc(((s.workflow?.procedures||{})[r.skill]||{}).title || r.label || r.skill)}${it0 ? ' · ' + esc(it0.title || it0.id) : ''}`
        : `${esc(ag.role || 'agent')}${ag.interactive ? ' · your session' : ''}`;
      const kids = [...actors.values()].filter(x => x.spec.parent === sp.key && !x.leaving).length;
      return `<b>${who}</b><small>${esc(NLclip(doing(sp), 90))}</small>${kids ? `<small>${kids} subagent${kids === 1 ? '' : 's'}</small>` : ''}`;
    }
    if (p.kind === 'card') { const it = item(s, p.id); return it ? `<b>${esc(it.title || it.id)}</b><small>${(it.waiting || []).length ? '◆ waits for you' : esc((window.NL && NL.STATE_LABEL && NL.STATE_LABEL[it.state]) || it.state)}</small>` : null; }
    if (p.kind === 'room') { const o = W.rooms[p.id]; if (!o) return null; const n = [...actors.values()].filter(a => a.room === p.id && !a.leaving).length; return `<b>${esc(o.title)}</b>${n ? `<small>${n} at work</small>` : ''}`; }
    if (p.kind === 'hub') { const n = needs(s).length; return `<b>Your desk</b>${n ? `<small>${n} need${n === 1 ? 's' : ''} you</small>` : ''}`; }
    if (p.kind === 'newt') return '<b>Workspace assistant</b>';
    if (p.kind === 'checkpoint') { const g = Object.values(W.gates).find(g=>g.g.id===p.id&&g.machine===p.machine); if (!g) return null; const w = ((s.items) || []).filter(i => (i.waiting || []).includes(p.id)&&(s.world_view!=='full'||(i.machine||'local')===p.machine));
      return `<b>◆ ${esc(g.g.title)}</b>${w.length ? `<small>${esc(w.map(i => i.title || i.id).join(', '))}</small>` : ''}`; }
    return null;
  }
  const needs = s => ((s && s.attention) || []).filter(a => a.sev !== 'info');
  const NLclip = (t, n) => { t = String(t || ''); return t.length > n ? t.slice(0, n - 1) + '…' : t; };

  // ── lenses and labels ─────────────────────────────────────────────────────────────────────────────
  const tmpV = new THREE.Vector3();
  function toScreen(x, y, z) { tmpV.set(x, y, z).project(camera); const r = canvas.getBoundingClientRect(); return [(tmpV.x + 1) / 2 * r.width + r.left, (1 - tmpV.y) / 2 * r.height + r.top, tmpV.z < 1]; }
  /** what is drawn over the table: a "?" over each agent asking you; the rooms' names only when asked (the tour) */
  function overlays() {
    if (!W || !snap) return;
    const out = [];
    if(snap.world_view==='full')for(const d of W.districts){
      const [x,y,visible]=toScreen((d.x0+d.x1)/2,1.2,d.z1+1);
      const state=(snap.machines||[]).find(m=>m.id===d.id)?.state,offline=d.id!=='local'&&state!=='connected';
      if(visible)out.push(`<div class="wl-room wl-machine" title="${esc(d.name)}" style="left:${x}px;top:${y}px"><b>${esc(d.name)}</b>${offline?'<small>Disconnected</small>':''}</div>`);
    }
    if (labels) for (const o of Object.values(W.rooms)) {
      const [sx, sy, vis] = toScreen(o.x, 1.7, o.z - o.ez / 2 + 0.6);
      if (vis && sy > insets.top + 30 && sy < (insets.cut || innerHeight)) out.push(`<div class="wl-room" style="left:${sx}px;top:${sy}px"><b>${esc(o.title)}</b></div>`);
    }
    for (const a of actors.values()) {
      if (a.leaving || a.courier || a.path.length || (a.spec.pose !== 'wait' && a.spec.pose !== 'sleep')) continue;
      const h = a.n.group.position, [sx, sy, vis] = toScreen(h.x, 1.75 * a.spec.scale * 1.25 + 0.15, h.z);
      if (vis) out.push(a.spec.pose === 'wait' ? `<div class="wl-bub ask icon" style="left:${sx}px;top:${sy}px">?</div>`
        : `<div class="wl-bub zzz" style="left:${sx}px;top:${sy}px">zzz</div>`);
    }
    const html = out.join(''); if (overlay.innerHTML !== html) overlay.innerHTML = html;
  }

  // ── each frame ────────────────────────────────────────────────────────────────────────────────────
  let last = performance.now(), dirty = true, raf = 0;
  function frame(now, quiet) {     // quiet: move the world on without drawing it (fast-forward)
    if (!quiet) raf = 0;
    if (destroyed || contextLost || !active) return;
    const raw = Math.max(0, (now - last) / 1000), dt = Math.min(0.05, raw), dtWalk = Math.min(0.1, raw); last = now;   // walks keep pace on a slow machine
    const t = now / 1000;
    if (W && snap) {
      // actors walk their paths; leavers fade
      for (const [key, a] of actors) {
        const detail = detailFor(a.n.detail);
        if (detail !== a.n.detail) {
          const old = a.n, replacement = body(a.spec, detail); replacement.character = old.character;
          if (old.update.snapshot && replacement.update.restore) replacement.update.restore(old.update.snapshot());
          replacement.group.position.copy(old.group.position); replacement.group.rotation.copy(old.group.rotation); replacement.group.scale.copy(old.group.scale);
          L.resources.release(old.group); pickables.delete(old.hit || old.group); scene.add(replacement.group); pickables.add(replacement.hit || replacement.group); a.n = replacement;
        }
        let moving = false;
        if (a.path.length) {
          const lastPoint = a.path[a.path.length - 1], left = Math.hypot(lastPoint[0] - a.pos[0], lastPoint[1] - a.pos[1]);
          const max = WALK * (a.spec.kind === 'sub' ? 1.15 : 1), desiredSpeed = a.path.length === 1 ? Math.min(max, Math.sqrt(left * 10)) : max;
          a.speed = (a.speed || 0) + (desiredSpeed - (a.speed || 0)) * (1 - Math.exp(-dtWalk * 12));
          let budget = a.speed * dtWalk;
          while (a.path.length && budget > 0) {
            const point = a.path[0], dx = point[0] - a.pos[0], dz = point[1] - a.pos[1], d = Math.hypot(dx, dz), step = Math.min(d, budget);
            if (d > 0.0001) { a.pos[0] += dx / d * step; a.pos[1] += dz / d * step;
              a.ry += Math.atan2(Math.sin(Math.atan2(dx, dz) - a.ry), Math.cos(Math.atan2(dx, dz) - a.ry)) * (1 - Math.exp(-dtWalk * 12)); }
            a.distance = (a.distance || 0) + step; budget -= step; moving = moving || step > 0;
            if (d <= step + 0.002) { a.pos = point.slice(0, 2); a.path.shift(); if (point.enter) a.room = point.enter;
              if (!a.path.length && a.dest) a.room = a.dest.room; } else break;
          }
        } else if (a.dest && a.dest.ry != null) { a.ry += (((a.dest.ry - a.ry + Math.PI * 3) % (Math.PI * 2)) - Math.PI) * Math.min(1, dt * 6); }
        const done = !a.path.length; if (motion() !== 'full' && a.leaving) a.fade = 1;
        if (a.leaving && done) a.fade = Math.min(1, a.fade + dt * 2.5); else if (!a.leaving) a.fade = Math.max(0, a.fade - dt * 4);
        if (a.courier && done) { a.leaving = true; const c = cards.get(a.courier); if (c && c.userData.carrier === key) c.userData.carrier = null; }
        if (a.leaving && a.fade >= 1) { L.resources.release(a.n.group); pickables.delete(a.n.hit || a.n.group); actors.delete(key); continue; }
        const g = a.n.group, sc = a.spec.scale * 1.25 * (1 - a.fade * 0.9);
        g.position.set(a.pos[0], a.y??0.14, a.pos[1]); g.rotation.y = a.ry; g.scale.setScalar(Math.max(0.01, sc));
        const pz = moving ? (a.courier ? 'carry' : 'walk') : a.spec.pose;
        const poked = a.poke != null && t - a.poke < 1.6 ? t - a.poke : null;
        a.n.update(t, { pose: pz, moving, act: a.spec.act, poke: poked, hop: a.hop, contact:a.blocked,motion: motion(), distance: a.distance || 0, locomotion: locomotion(a.n.character) });
      }
      // cards: carried, at a gate, or on their room's shelf
      const shelfN = {};
      for (const [id, c] of cards) {
        const carrier = c.userData.carrier && actors.get(c.userData.carrier);
        if (carrier) { c.position.set(carrier.pos[0], 1.85 * 1.25 + 0.25, carrier.pos[1]); c.rotation.y = carrier.ry; c.visible = true; continue; }
        const o = W.rooms[c.userData.room]; if (!o) { c.visible = false; continue; }
        const g = c.userData.gate && W.gates[c.userData.gate];
        if (g && g.host === o) { const k = (shelfN['gate' + c.userData.gate] = (shelfN['gate' + c.userData.gate] || 0) + 1) - 1; c.position.set(g.pos[0], 0.3 + k * 0.1, g.pos[1]); c.rotation.y = motion() === 'full' ? t * 0.6 : o.ry; c.visible = true; continue; }
        const i = (shelfN[o.id] = (shelfN[o.id] || 0) + 1) - 1, perRow = Math.max(1, Math.floor(Math.min(3.4, o.spec.size[0] * 0.4) / 0.62));
        const [x, z] = o.toWorld(o.shelfAt[0] + 0.34 + (i % perRow) * 0.62, o.shelfAt[1]);
        c.position.set(x, 0.62 + Math.floor(i / perRow) * 0.1 + (touring === 'studies' ? 0.25 + Math.sin(t * 3 + i) * 0.12 : 0), z); c.rotation.y = o.ry; c.visible = true;
        c.scale.setScalar(touring === 'studies' ? 1.7 : 1);
      }
      // the desk: one envelope per thing waiting; Newt poses by the lab's mood; checkpoint lanterns glow when someone waits
      const n = needs(snap).length;
      while (W.inbox.children.length < n) W.inbox.add(K.box(0.4, 0.035, 0.28, 'amber', 0, W.inbox.children.length * 0.045, 0, { glow: 'amber', gi: 0.4 }));
      W.inbox.children.forEach((e, i) => { e.visible = i < n; });
      W.bigNewt.update(t, { motion: motion(), pose: pose === 'gate' || n ? 'wait' : pose === 'sleep' ? 'sleep' : pose === 'failure' ? 'fail' : pose === 'running' ? 'work' : 'idle',
        poke: W.bigNewt.poke != null && t - W.bigNewt.poke < 1.6 ? t - W.bigNewt.poke : null });
      const waitingGates = new Set(((snap.items) || []).flatMap(i => i.waiting || []));
      if (W.fireflies && ambient && !reduced) {
        const P = W.fireflies.geometry.attributes.position, sd = W.fireflies.userData.seed;
        for (let i = 0; i < sd.length; i++) { const f = sd[i]; P.setXYZ(i, f[0] + Math.sin(t * 0.4 + f[3]) * 0.6, f[1] + Math.sin(t * 0.9 + f[3] * 2) * 0.25, f[2] + Math.cos(t * 0.33 + f[3]) * 0.6); }
        P.needsUpdate = true; W.fireflies.material.opacity = 0.6 + Math.sin(t * 1.7) * 0.25;
        if (W.glowLines[0]) W.glowLines[0].material.emissiveIntensity = 0.32 + Math.sin(t * 0.8) * 0.1;
      }
      for (const g of Object.values(W.gates)) {
        const on = (waitingGates.has(g.g.id)&&(snap.world_view!=='full'||(snap.items||[]).some(it=>(it.waiting||[]).includes(g.g.id)&&(it.machine||'local')===g.machine))) || glowAll;
        g.lamp.material.emissiveIntensity = on ? 1.7 + (motion() === 'full' ? Math.sin(t * 4.5) * 0.6 : 0) : 0.12;
        g.lamp.rotation.y = on && motion() === 'full' ? t * 0.8 : 0;
        if (g.arch.userData.sway && motion() === 'full') g.arch.userData.sway.rotation.z = on ? Math.sin(t * 1.6) * 0.06 : 0;
      }
      // the camera: follow, ease, keep clear of the rail
      if (followKey) { const a = actors.get(followKey); if (a) { camT.tx = a.pos[0]; camT.tz = a.pos[1]; } else { followKey = null; if (onFollow) onFollow(null); } }
      const k = motion() === 'full' ? 1 - Math.pow(0.002, dt) : 1;
      for (const key of ['az', 'el', 'r', 'tx', 'tz']) cam[key] += (camT[key] - cam[key]) * k;
      camera.position.set(cam.tx + cam.r * Math.cos(cam.el) * Math.sin(cam.az), cam.r * Math.sin(cam.el), cam.tz + cam.r * Math.cos(cam.el) * Math.cos(cam.az));
      camera.lookAt(cam.tx, 0.6, cam.tz);
      for (const o of Object.values(W.rooms)) if (o.rising) { o.g.scale.y += (1 - o.g.scale.y) * Math.min(1, dt * 1.6); if (o.g.scale.y > 0.995) { o.g.scale.y = 1; o.rising = false; } }
      // walls duck when they stand between you and their room
      for (const o of Object.values(W.rooms)) for (const wl of o.walls) {
        const [wx, wz] = o.toWorld(wl.lx, wl.lz), nn = [wl.n[0] * Math.cos(o.ry) + wl.n[1] * Math.sin(o.ry), -wl.n[0] * Math.sin(o.ry) + wl.n[1] * Math.cos(o.ry)];
        const target = nn[0] * (camera.position.x - wx) + nn[1] * (camera.position.z - wz) > 0 ? 0.12 : 1;
        wl.wall.scale.y += (target - wl.wall.scale.y) * Math.min(1, k * 1.5); wl.wall.position.y = 0.14 + wl.h / 2 * wl.wall.scale.y; wl.cap.position.y = 0.14 + wl.h * wl.wall.scale.y + 0.03;
      }
      if (quiet) return;
      renderer.render(scene, camera);
      overlays();
    }
    if (!document.hidden && (motion() === 'full' || unsettled())) raf = requestAnimationFrame(frame);
  }
  const kick = () => { if (!destroyed && active && !raf) raf = requestAnimationFrame(frame); };
  listen(document, 'visibilitychange', ()=>{last=performance.now();kick();});
  let viewportWidth=0,viewportHeight=0;
  function resize(refit = false) {
    if(!active)return;
    const r = canvas.getBoundingClientRect();
    if(!r.width||!r.height)return;
    const w=r.width,h=r.height,changed=w!==viewportWidth||h!==viewportHeight;
    viewportWidth=w;viewportHeight=h;
    renderer.setSize(w, h, false); camera.aspect = w / h;
    measureInsets();
    camera.setViewOffset(w, h, (insets.right - insets.left) / 2, (insets.bottom - insets.top) / 2 * insets.k, w, h);
    camera.updateProjectionMatrix(); if(refit||changed)fitCamera(false); kick();
  }
  listen(window, 'resize', ()=>resize());

  return {
    kind: '3d',
    setActive(on) {
      if(active===!!on)return;
      active=!!on;last=performance.now();
      if(!active){if(raf)cancelAnimationFrame(raf);raf=0;tip.style.display='none'}
      else resize(false);
    },
    destroy() {
        if (destroyed) return; destroyed = true;
      if (raf) cancelAnimationFrame(raf); raf = 0;
      listeners.splice(0).forEach(off => off());
        L.resources.release(scene); renderer.dispose();
      tip.remove(); overlay.remove();
      actors.clear(); cards.clear(); pickables.clear();
    },
    setMotion(mode) { reduced = mode === 'reduced'; ambient = mode === 'full';
      if (motion() !== 'full') { for (const a of actors.values()) if (a.dest) sendTo(a, a.dest); if (W) for (const o of Object.values(W.rooms)) { o.rising = false; o.g.scale.y = 1; } }
      kick(); },
    _debug: () => ({ W, actors, cards, snap, view, labels, click, pickAt, toScreen, step(sec, fps) { const f = fps || 20; for (let i = 0; i < sec * f; i++) frame(last + 1000 / f, true); } }),
    async boot() { resize(); kick(); },
    async sync(s) {
      if (destroyed) return;const changed=snap&&snap.world_view!==s.world_view; snap = s;
      const rebuilt = buildStatic(s);
      refreshCast();
      reconcile(s); L.resources.track(scene);
      if(changed)for(const a of actors.values())if(a.dest){a.pos=a.dest.at.slice();a.room=a.dest.room;a.path=[];a.ry=a.dest.ry||0}
      if ((!settled || rebuilt) && /[?&]settle\b/.test(location.search)) { settled = true; for (let i = 0; i < 900; i++) frame(last + 50, true); }   // screenshots: everyone in place (again after a rebuild: walks start over)
      kick();
    },
    setPose(p) { pose = p; kick(); },
    setLamp(m) {
      const next=m==='day'?'day':'night';
      if(next===theme)return;
      theme=next;
      // Authored modules may construct different geometry for each theme.
      if(Object.values(snap?.room_designs||{}).some(r=>r.module)){
        staticSig='';buildStatic(snap);refreshCast();reconcile(snap);L.resources.track(scene);kick();return;
      }
      if(K){
        K=L.kit(THREE,theme);TH=K.th;recolor(scene);applyLights();
        for(const o of Object.values(W.rooms)){o.renderTheme=theme;o.floorBase.copy(o.floorMat.color)}
        for(const c of cards.values())c.userData.cardMaterial.emissiveIntensity=theme==='night'?0.35:0;
      }
      kick();
    },
    setView(m) { if (m === 'WORLD') setViewState('WORLD'); },
    goRoom(k) { if (W && W.rooms[k]) setViewState('ROOM', k); },
    focusProject(id) { if (!W) return; const it = item(snap, id), rid = (it && roomOfItem(snap, it)) || null; if (rid) setViewState('ROOM', rid); },
    back() { setViewState('WORLD'); },
    viewInfo() { return { level: view.level === 'ROOM' ? 'REGION' : 'WORLD', label: view.label }; },
    agentAnchor(id) {
      const a = actors.get(id), mascot = id === 'newt' && W?.bigNewt;
      if ((!a || a.leaving) && !mascot) return null;
      const p = (mascot || a.n).group.position;
      const [x,y,visible] = toScreen(p.x, p.y + (mascot ? 1.8 : 1.5 * a.spec.scale), p.z);
      return {x,y,width:canvas.clientWidth,height:canvas.clientHeight,visible};
    },
    highlight(role) { highlightRole = role || null; kick(); },
    roomRect() { return null; }, band() { return null; },
    followWorker(id) {
      const ag = ((snap && snap.agents) || []).find(x => x.id === id || x.worker_id === id || (x.run_id === id && !x.parent));
      const key = ag ? ag.id : [...actors.keys()].find(k => k === 'run:' + id || k === 'w:' + id);
      if (key && actors.has(key)) { followKey = key; camT.r = 22; if (onFollow) onFollow(id); kick(); }
    },
    stopFollow() { followKey = null; if (onFollow) onFollow(null); }, following() { return followKey; },
    layout() {                         // the plan of the table, for the minimap
      if (!W) return null;
      const boxes = Object.values(W.rooms).map((o, i) => ({ key: o.id, x: o.x - o.ex / 2, y: o.z - o.ez / 2, w: o.ex, h: o.ez, label: o.title, n: i + 1 }));
      return { boxes, bbox: { x: W.EXT.x0, y: W.EXT.z0, w: W.EXT.x1 - W.EXT.x0, h: W.EXT.z1 - W.EXT.z0 }, room: view.room, level: view.level };
    },
    setAmbient(on) { ambient = !!on; if (!on) for (const a of actors.values()) if (a.dest) sendTo(a, a.dest); kick(); },
    /** the rooms' names over the table (the tour shows them; otherwise a name is a hover away) */
    setLabels(on) { labels = !!on; kick(); },
    /** the tour: show one of the lab's concepts — 'rooms' · 'studies' · 'agents' · 'checkpoints' · 'desk' — or end (null) */
    tour(what) {
      if (!W) return;
      labels = what === 'rooms'; glowAll = what === 'checkpoints'; touring = what || null;
      const busiest = count => { let best = null, n = 0; for (const o of Object.values(W.rooms)) { const k = count(o); if (k > n) { n = k; best = o.id; } } return best; };
      const room = what === 'studies' ? busiest(o => [...cards.values()].filter(c => c.userData.room === o.id).length)
        : what === 'agents' ? busiest(o => [...actors.values()].filter(a => a.room === o.id && !a.leaving && !a.courier).length)
        : what === 'checkpoints' ? (() => { const waiting = new Set(((snap && snap.items) || []).flatMap(i => i.waiting || [])), gs = Object.values(W.gates);
            const g = gs.find(x => waiting.has(x.g.id)) || gs[0]; return g && g.host ? g.host.id : null; })() : null;
      if (room) setViewState('ROOM', room);
      else { setViewState('WORLD'); if (what === 'desk') Object.assign(camT, { tx: 0, tz: 0, r: Math.max(16, W.SPAN * 1.1), el: 0.9 }); }
      kick();
    },
    /** your other labs: [{key, name, machine, needs, running, state}] — drawn as small tables past the back edge */
    setNeighbours(list) { const had = neighbours.length; neighbours = (list || []).map(n => ({ ...n })); nbSig = ''; buildNeighbours(); if (!had !== !neighbours.length && view.level === 'WORLD') fitCamera(false); kick(); },
    onLab(cb) { onLab = cb; }, onArtifact(cb) { onArtifact = cb; }, onCheckpoint(cb) { onCheckpoint = cb; },
    /** who plays the agents: {mode: 'one'|'backend', one, claude, codex, opencode} — swapped in place, mid-stride */
    setCast(c) {
      cast = Object.assign({}, cast, c || {});
      refreshCast();
      kick();
    },
    insetsChanged() { resize(true); },
    onClick(item, inbox) { onItem = item; onInbox = inbox; }, onWorker(cb) { onWorker = cb; }, onRun(cb) { onRun = cb; }, onNewt(cb) { onNewt = cb; },
    onView(cb) { onView = cb; }, onFollow(cb) { onFollow = cb; },
  };
};
})();
