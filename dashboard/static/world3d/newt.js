/* Lab3D — the newt, in 3D: the lab's axolotl, built from primitives,
 * in its proportions: a wide domed head as tall as the short, stocky pear of a body under it; shiny bead eyes
 * set low and wide, a tiny mouth between them; little arms with their paws held at the belly; three branching
 * gill fronds a side sweeping up from the back of the head and a thick curled tail, both shading pink →
 * lavender → sky blue (they glow a little at night). A role badge on its chest says what kind of agent it is.
 *
 *   const n = Lab3D.makeNewt(K, { color: '#5ccfbc', hue: 40, scale: 1 });
 *     color: the role badge on its chest · hue: turns its gills and tail round the colour wheel (a main agent's
 *     family colour — its subagents are smaller newts in the same colours) · scale: its size
 *   n.group                       — add it to the scene
 *   n.update(t, { pose, moving, act, poke }) — pose: idle | work | walk | wait | sleep | fail | carry · act: the
 *     activity it works at (model.ACTS: read, edit, run, search, plan, spawn, …) · poke: seconds since you
 *     hovered or clicked it (it waves, or hops, with a happy face)
 *
 * Every character shares one animator (L.animator, below): its poses, a work loop per activity, a face that
 * shows how it is doing (brows, eyes, mouth), and — standing idle — its own fidgets now and then.
 */
(function () {
  'use strict';
  const L = (window.Lab3D = window.Lab3D || {});
  const GILL = ['#ff9fd6', '#c9a7ff', '#8fd8ff'];
  const TAIL = ['#f7a6d2', '#c39cf3', '#9fd3ff'];

  const turn = (THREE, c, deg) => (deg ? '#' + new THREE.Color(c).offsetHSL(deg / 360, 0, 0).getHexString() : c);
  function lerpColor(THREE, cs, u) {
    const n = cs.length - 1, i = Math.min(n - 1, Math.floor(u * n)), f = u * n - i;
    return new THREE.Color(cs[i]).lerp(new THREE.Color(cs[i + 1]), f);
  }

  /** a tube along a curve whose radius tapers from r0 to r1, coloured along its length */
  function taperedTube(K, pts, r0, r1, colors) {
    const { THREE } = K, curve = new THREE.CatmullRomCurve3(pts.map(p => new THREE.Vector3(...p)));
    const segs = 48, radial = 14, geo = new THREE.TubeGeometry(curve, segs, 1, radial, false);
    const pos = geo.attributes.position, cols = new Float32Array(pos.count * 3), c = new THREE.Vector3(), v = new THREE.Vector3();
    for (let i = 0; i <= segs; i++) {
      const u = i / segs, r = r0 + (r1 - r0) * Math.pow(u, 0.85), col = lerpColor(THREE, colors, u);
      curve.getPointAt(u, c);
      for (let j = 0; j <= radial; j++) {
        const k = i * (radial + 1) + j;
        v.fromBufferAttribute(pos, k).sub(c).multiplyScalar(r).add(c); pos.setXYZ(k, v.x, v.y, v.z);
        cols[k * 3] = col.r; cols[k * 3 + 1] = col.g; cols[k * 3 + 2] = col.b;
      }
    }
    geo.setAttribute('color', new THREE.BufferAttribute(cols, 3)); geo.computeVertexNormals();
    // cap the thick end with a sphere so it reads as one body
    const m = K.mesh(geo, K.mat('#ffffff', { vc: true, smooth: true, glow: '#ffffff', gi: {day:0,night:0.06} }));
    return m;
  }

  /** one gill frond: a tapered stalk pointing up (+y) with little side twigs */
  function frond(K, len, color) {
    const { THREE } = K, g = new THREE.Group();
    const m = K.mat(color, { smooth: true, glow: color, gi: {day:0,night:0.22} });
    const stalk = K.mesh(K.geometry('CapsuleGeometry', 0.03, len * 0.8, 8, 18), m, 0, len / 2, 0); g.add(stalk);
    for (let i = 0; i < 4; i++) {
      const y = len * (0.22 + i * 0.18), side = i % 2 ? 1 : -1, tw = K.mesh(K.geometry('CapsuleGeometry', 0.017, len * 0.26, 8, 18), m, 0, 0, 0);
      tw.position.set(side * 0.03, y + len * 0.12, 0); tw.rotation.z = -side * 0.95; g.add(tw);
    }
    return g;
  }

  /** a pair of brows above a pair of eyes (each on its eye's parent), for the face to raise, knit or droop */
  L.brows = function brows(K, eyes, color) {
    const { THREE } = K, m = K.mat(color || '#151517', { smooth: true, rough: 0.5, glow: color || null, gi: color ? 0.6 : 0 });
    return eyes.map((e, i) => {
      const r = ((e.geometry.parameters && e.geometry.parameters.radius) || 0.03) * Math.max(e.scale.x, e.scale.y);
      const b = K.mesh(K.geometry('CapsuleGeometry', r * 0.2, r * 1.1, 8, 18), m, e.position.x, e.position.y + r * 1.75, e.position.z + r * 0.25);
      b.rotation.z = Math.PI / 2; b.castShadow = false;
      b.userData = { side: i ? 1 : -1, y: b.position.y, r };
      e.parent.add(b); return b;
    });
  };

  // a face for each mood: eyes open (1) to shut (0), the mouth's width and curve (negative: a frown), the brows'
  // tilt (positive: knitted, inner ends down) and lift
  const FACES = {
    content: { eye: 1, mouth: [1, 1], tilt: 0, lift: 0 },
    happy: { eye: 0.4, mouth: [1.35, 1.35], tilt: -0.1, lift: 0.5 },
    hopeful: { eye: 1.18, mouth: [1.1, 1.15], tilt: -0.28, lift: 0.7 },
    focus: { eye: 0.82, mouth: [0.75, 0.4], tilt: 0.14, lift: -0.1 },
    sad: { eye: 0.85, mouth: [0.9, -0.9], tilt: -0.4, lift: 0.35 },
    asleep: { eye: 0.1, mouth: [0.55, 0.5], tilt: 0, lift: -0.2 },
  };
  const S = Math.sin, PI = Math.PI, wSafe = d => Math.sin(d * 6);
  // working, by what it works at: typing · reading down a page · running (type, then sit back and watch) ·
  // searching (looking round, a hand shading its eyes) · planning (a paw to its chin) · briefing a subagent
  const WORK = {
    type(o, tt) { o.lean = 0.12; o.armL = -1.1 + Math.max(0, S(tt * 11)) * 0.28; o.armR = -1.1 + Math.max(0, S(tt * 11 + 2)) * 0.28; o.tilt = 0.14 + S(tt * 1.3) * 0.05; },
    read(o, tt) { o.lean = 0.08; o.tilt = 0.3; o.turn = S(tt * 0.9) * 0.16; o.look = S(tt * 0.9) * 0.6; o.armL = o.armR = -1.25;
      const u = (tt % 4.5) / 0.6; if (u < 1) { o.raiseR = S(PI * u) * 0.7; o.armR = -1.25 + S(PI * u) * 0.3; } },
    run(o, tt) { if (tt % 6 < 3.4) return WORK.type(o, tt); o.lean = -0.06; o.tilt = -0.1; o.face = 'hopeful'; o.bob += Math.abs(S(tt * 2.5)) * 0.01; },
    search(o, tt) { o.turn = S(tt * 1.4) * 0.5; o.look = S(tt * 3.1); o.armR = -0.9; o.raiseR = 1.75; o.tilt = -0.06; },
    plan(o, tt) { o.armR = -2.2; o.raiseR = -0.6; o.tilt = -0.2 + S(tt * 0.8) * 0.05; o.turn = 0.18; o.look = 0.5; o.face = 'content'; },
    spawn(o, tt) { o.armR = -0.75; o.raiseR = 1.15 + S(tt * 4.2) * 0.35; o.turn = -0.25; o.face = 'happy'; },
  };
  const ACT = { read: 'read', edit: 'type', write: 'type', run: 'run', bash: 'run', git: 'run', search: 'search', plan: 'plan',
    skill: 'plan', spawn: 'spawn', mcp: 'type', tool: 'type' };
  const LOOK_ROUND = (o, k, tt) => { o.turn = S(tt * 1.7) * 0.55 * k; o.look = S(tt * 1.7) * k; };

  /** the shared animation for a rig {body, head, legs, arms, eyes, brows?, mouth?, legY, armRest?, armSpread?,
   *  fidgets?: [(o, k, tt, u) => …], extra?(tt, pose, moving, fidget, o)}. Standing idle it loops through its fidgets,
   *  one after another with a breath between (k: 0 → 1 → 0 over each, u: 0 → 1); `o` is what the frame will set.
   *  → update(t, state) */
  L.animator = function animator(R) {
    let seed = 2166136261; for (const ch of String(R.seed ?? 0)) { seed ^= ch.charCodeAt(0); seed = Math.imul(seed, 16777619); }
    const player=L.motion&&L.motion.player(seed>>>0);
    const phase = (seed >>> 0) / 4294967296 * 10, beat = 3.6 + ((seed >>> 8) % 1000) / 1000 * 1.2, play = 2.6, rest = R.armRest ?? -0.55, spread = R.armSpread ?? 0.18;
    const fidgets = (R.fidgets && R.fidgets.length) ? R.fidgets : [LOOK_ROUND];
    R.eyes.forEach(e => { e.userData.sy = e.scale.y; e.userData.x = e.position.x; e.userData.r = ((e.geometry?.parameters || {}).radius || 0.03) * e.scale.x; });
    const m = R.mouth; if (m) { m.userData.s = m.scale.clone(); m.userData.y = m.position.y; }
    const bodyS = R.body.scale.clone();
    // what is on screen now, eased toward what the pose wants: [key, time constant (s)]
    const EASE = [['bob', 0.07], ['lean', 0.14], ['tilt', 0.11], ['turn', 0.09], ['roll', 0.14], ['armL', 0.06], ['armR', 0.06], ['raiseL', 0.06], ['raiseR', 0.06],
      ['look', 0.08], ['eye', 0.06], ['m0', 0.08], ['m1', 0.08], ['bt', 0.09], ['bl', 0.09], ['leg0', 0.05], ['leg1', 0.05], ['sq', 0.05], ['bodyTurn', 0.2]];
    let cur = null, lastT = null;
    const update = function update(t, st) {
      st = st || {};
      const pose = st.pose || 'idle', moving = !!st.moving, full = !st.motion || st.motion === 'full', tt = (full ? t : 0) + phase;
      const o = { bob: S(tt * 2) * 0.008, lean: 0, tilt: 0, turn: 0, roll: 0, armL: rest, armR: rest, raiseL: 0, raiseR: 0, look: 0, face: 'content', wink: -1,
        blink: S(tt * 0.7) > 0.985 };
      R.legs.forEach((l,i) => { l.position.y = R.legYs?R.legYs[i]:R.legY; });
      o.leg0 = 0; o.leg1 = 0; o.sq = S(tt * 1.7) * 0.012;                // a breath
      if (moving || pose === 'walk' || pose === 'carry') {
        const w = S(st.distance == null ? tt * 9 : st.distance * 6); o.bob = Math.abs(w) * 0.04; o.leg0 = w * 0.5; o.leg1 = -w * 0.5; o.lean = 0.08;
        o.armL = rest + w * 0.35; o.armR = rest - w * 0.35; o.sq = (Math.abs(w) - 0.6) * 0.05;   // a little squash at each footfall
        o.turn = S(tt * 4.5) * 0.06;                                   // the head bobbles along
      }
      if (pose === 'idle') { o.turn = S(tt * 0.45) * 0.35 * Math.max(0, S(tt * 0.21)); o.roll = S(tt * 0.6) * 0.05; }
      if (pose === 'work') { o.face = 'focus'; WORK[ACT[st.act] || 'type'](o, tt, rest); }
      if (pose === 'wait') { o.armR = -0.15; o.raiseR = 2.55 + S(tt * 6) * 0.3; o.bob = Math.abs(S(tt * 3)) * 0.035; o.tilt = -0.15; o.turn = 0.12; o.roll = 0.1; o.face = 'hopeful'; }
      if (pose === 'carry') { o.armL = o.armR = -0.3; o.raiseL = o.raiseR = 2.35; o.face = 'happy'; }
      if (pose === 'sleep') { o.tilt = 0.38; o.face = 'asleep'; o.bob = S(tt * 1.1) * 0.014 - 0.01; o.armL = o.armR = -0.15; o.roll = S(tt * 0.5) * 0.04; }
      if (pose === 'fail') { o.tilt = 0.5; o.lean = 0.2; o.armL = o.armR = -0.05; o.bob = -0.02; o.turn = S(tt * 0.5) * 0.08; o.face = 'sad'; }
      let f = null;                                 // now and then, standing idle: one of its own fidgets
      if (pose === 'idle' && !moving && full) {
        const c = tt / beat, u = (c - Math.floor(c)) * beat / play;   // a fidget, a breath, the next one — round and round
        if (u < 1) { f = { i: Math.floor(c) % fidgets.length, k: S(PI * u), u }; fidgets[f.i](o, f.k, tt, u); }
      }
      if (full && st.poke != null && st.poke < 1.6 && pose !== 'sleep') {   // you looked at it: it waves (and hops, if you clicked)
        const k = S(PI * Math.min(1, st.poke / 1.6)); o.face = 'happy'; o.armR = -0.2; o.raiseR = 2.4 + S(st.poke * 13) * 0.35;
        if (st.hop) { o.bob += k * 0.12; o.sq = S(PI * 2 * Math.min(1, st.poke / 0.9)) * 0.09; }   // stretch going up, squash landing
      }
      if (moving && st.locomotion === 'glide') { o.leg0 = o.leg1 = 0; o.bob = 0; o.lean = 0; }
      if (moving && st.locomotion === 'hover') { o.leg0 = o.leg1 = 0; o.bob = full ? S(tt * 2.6) * 0.02 : 0; }
      if (moving && st.locomotion === 'hop') { o.leg0 = o.leg1 = 0; o.bob = Math.max(0, wSafe(st.distance ?? tt)) * 0.09; }
      if(moving&&st.locomotion==='waddle'){o.roll=S((st.distance??tt)*7)*.12;o.leg0*=.5;o.leg1*=.5;}
      if(player)Object.assign(o,player.update(t,st));
      if (st.o) Object.assign(o, st.o);             // a scene can direct it outright (the film does): face, arms, tilt…
      const F = FACES[o.face] || FACES.content;
      o.eye = F.eye; o.m0 = F.mouth[0]; o.m1 = F.mouth[1]; o.bt = F.tilt; o.bl = F.lift; o.bodyTurn = o.turn * 0.25;   // the body follows the head, a little and late
      // ease what's on screen toward the pose (snap on the first frame, a jump back in time, or a long gap)
      const dt = lastT == null ? -1 : t - lastT; lastT = t;
      if (!cur || !full || !(dt > 0 && dt < 0.3)) cur = Object.assign({}, o);
      else for (const [key, tau] of EASE) {
        let d = o[key] - cur[key];
        if (key === 'turn') d = Math.atan2(Math.sin(d), Math.cos(d));   // a head that went right round comes back the short way
        cur[key] += d * (1 - Math.exp(-dt / tau));
      }
      const c = cur;
      R.body.position.y = c.bob; R.body.rotation.x = c.lean; R.body.rotation.z = c.roll * 0.5; R.body.rotation.y = c.bodyTurn;
      R.body.scale.set(bodyS.x * (1 - c.sq * 0.5), bodyS.y * (1 + c.sq), bodyS.z * (1 - c.sq * 0.5));
      R.head.rotation.x = c.tilt; R.head.rotation.y = c.turn - c.bodyTurn; R.head.rotation.z = c.roll;
      R.legs[0].rotation.x = c.leg0; R.legs[1].rotation.x = c.leg1;
      R.arms[0].rotation.x = c.armL; R.arms[1].rotation.x = c.armR;
      R.arms[0].rotation.z = -spread - c.raiseL; R.arms[1].rotation.z = spread + c.raiseR;   // a raised arm goes up beside the head
      R.eyes.forEach((e, i) => {
        const shut = o.blink || o.wink === i;                         // a blink is quick: never eased
        e.scale.y = e.userData.sy * (shut ? 0.12 : c.eye);
        e.position.x = e.userData.x + c.look * e.userData.r * 0.35;
      });
      (R.brows || []).forEach(b => { b.rotation.z = PI / 2 + b.userData.side * c.bt; b.position.y = b.userData.y + c.bl * b.userData.r * 0.6; });
      if (m) {
        m.scale.set(m.userData.s.x * c.m0, m.userData.s.y * c.m1, m.userData.s.z);
        m.position.y = m.userData.y + (c.m1 < 0 ? 0.6 : 0) * Math.abs(m.userData.s.y) * 0.04;
      }
      if (R.extra) R.extra(tt, pose, moving, f, o);
    };
    update.snapshot = () => ({ cur: cur && Object.assign({}, cur), lastT, clips:player&&player.snapshot() });
    update.restore = state => { if(player)player.restore(state&&state.clips); cur = state && state.cur ? Object.assign({}, state.cur) : null; lastT = state && state.lastT != null ? state.lastT : null; };
    return update;
  };

  L.makeNewt = function makeNewt(K, o) {
    o = o || {};
    const { THREE } = K, root = new THREE.Group(), body = new THREE.Group(), head = new THREE.Group();
    const gill = GILL.map(c => turn(THREE, c, o.hue || 0)), tailC = TAIL.map(c => turn(THREE, c, o.hue || 0));
    // Character identity stays warm; only the surrounding room palette changes at night.
    const skinColor = o.skin || '#fbeee0';
    const skin = K.mat(skinColor, { smooth: true, rough: 0.7, glow: skinColor, gi: {day:0,night:0.45} }), dark = K.mat('#151517', { smooth: true, rough: 0.3 });
    root.add(body);
    // legs + feet
    const legs = [-1, 1].map(s => { const l = K.mesh(K.geometry('CapsuleGeometry', 0.065, 0.05, 8, 18), skin, s * 0.12, 0.08, 0.03); body.add(l);
      const foot = K.mesh(K.geometry('SphereGeometry', 0.07, 28, 20), skin, 0, -0.05, 0.05); foot.scale.set(1.1, 0.45, 1.4); l.add(foot); return l; });
    // the upright, pear-shaped body (a lathe)
    const prof = [[0.001, 0.05], [0.17, 0.07], [0.235, 0.16], [0.245, 0.27], [0.225, 0.39], [0.185, 0.49], [0.14, 0.56], [0.001, 0.58]].map(([r, y]) => new THREE.Vector2(r, y));
    const torso = K.mesh(K.geometry('LatheGeometry', prof, 44), skin); body.add(torso);
    // arms: little paws held in front
    const arms = [-1, 1].map(s => {
      const a = new THREE.Group(); a.position.set(s * 0.15, 0.45, 0.1);
      const limb = K.mesh(K.geometry('CapsuleGeometry', 0.04, 0.12, 8, 18), skin, 0, -0.08, 0); a.add(limb);
      const paw = K.mesh(K.geometry('SphereGeometry', 0.045, 28, 20), skin, 0, -0.16, 0.01); paw.scale.set(1.1, 0.8, 1); a.add(paw);
      a.rotation.x = -0.55; a.rotation.z = s * 0.18; body.add(a); return a;
    });
    // a role badge on the chest
    if (o.color) { const b = K.mesh(K.geometry('SphereGeometry', 0.045, 28, 20), K.mat(o.color, { glow: o.color, gi: {day:0.25,night:0.9}, smooth: true }), 0, 0.2, 0.23); b.scale.z = 0.5; body.add(b); }
    // the big round head
    head.position.set(0, 0.82, 0); body.add(head);
    const skull = K.mesh(K.geometry('SphereGeometry', 0.28, 52, 36), skin); skull.scale.set(1.16, 1.0, 1.06); head.add(skull);
    const hlM = K.mat('#ffffff', { smooth: true, glow: '#ffffff', gi: 0.6 });
    const eyes = [-1, 1].map(s => { const e = K.mesh(K.geometry('SphereGeometry', 0.046, 28, 24), dark, s * 0.17, -0.085, 0.245); e.scale.set(1, 1.08, 0.7); head.add(e); return e; });
    eyes.forEach(e => { const a = K.mesh(K.geometry('SphereGeometry', 0.016, 28, 20), hlM, 0.014, 0.017, 0.035); const b = K.mesh(K.geometry('SphereGeometry', 0.007, 28, 20), hlM, -0.013, -0.014, 0.037); e.add(a, b); });
    [-1, 1].forEach(s => { const c = K.mesh(K.geometry('SphereGeometry', 0.04, 28, 20), K.mat('#f4b3b8', { smooth: true, rough: 0.9, glow: '#f4b3b8', gi: {day:0,night:0.18} }), s * 0.235, -0.14, 0.2); c.scale.set(1, 0.55, 0.4); head.add(c); });
    const mouth = K.mesh(K.geometry('TorusGeometry', 0.022, 0.006, 10, 24, Math.PI), dark, 0, -0.125, 0.268); mouth.rotation.z = Math.PI; head.add(mouth);
    const brows = L.brows(K, eyes, '#c9a59c');   // soft, like the art's bare face
    // gills: three fronds a side, fanned out behind the cheeks
    const gills = [-1, 1].map(s => {
      const g = new THREE.Group(); g.position.set(s * 0.27, 0.04, -0.07); g.scale.setScalar(1.65);
      [[0.33, 0.3, gill[0]], [0.28, 0.85, gill[1]], [0.21, 1.4, gill[2]]].forEach(([len, ang, c]) => { const f = frond(K, len, c); f.rotation.z = -s * ang; f.rotation.x = -0.3; g.add(f); });
      head.add(g); return g;
    });
    // the curled tail
    const tail = new THREE.Group(); tail.position.set(0, 0.13, -0.16); body.add(tail);
    tail.add(taperedTube(K, [[0, 0.02, 0], [0, -0.02, -0.2], [0.04, 0.04, -0.38], [0.08, 0.19, -0.46], [0.07, 0.31, -0.4]], 0.14, 0.035, tailC));
    if (o.scale) root.scale.setScalar(o.scale);

    const update = L.animator({ body, head, legs, arms, eyes, brows, mouth, seed: o.seed ?? o.hue ?? 0, legY: 0.08, armRest: -0.35, armSpread: 0.1,
      fidgets: [
        (o, k) => { o.raiseL = o.raiseR = 2.5 * k; o.armL = o.armR = -0.55 * (1 - k); o.bob += 0.05 * k; if (k > 0.4) o.face = 'happy'; },   // a big stretch
        (o, k, tt) => { o.roll = Math.sin(tt * 11) * 0.13 * k; o.face = 'happy'; },                                                         // a happy wiggle
        (o, k) => { o.turn = 1.15 * k; o.tilt = 0.18 * k; },                                                                                 // a look back at its tail
      ],
      extra(tt, pose, moving, f) {
        const flutter = pose === 'work' ? 5 : f && f.i === 1 ? 9 : 2.2, amp = (f && f.i === 1) || pose === 'wait' ? 0.16 : 0.07;
        gills.forEach((g, i) => { g.rotation.z = (i ? -1 : 1) * Math.sin(tt * flutter) * amp; });
        const swish = moving ? 6 : f && f.i === 2 ? 7 : 1.6;
        tail.rotation.y = Math.sin(tt * swish) * (moving || (f && f.i === 2) ? 0.4 : 0.15);
      } });
    update(0, {});
    return { group: root, update, head, rig:{body,head,legs,arms,eyes,brows,mouth}, slots: { left: arms[0], right: arms[1], head } };
  };
})();
