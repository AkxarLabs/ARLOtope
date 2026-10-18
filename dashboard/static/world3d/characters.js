/* Lab3D — the cast: other little characters an agent can be drawn as, besides the newt. Each one is a soft,
 * toy-like figure built from primitives with the same interface as Lab3D.makeNewt (world3d/newt.js):
 *
 *   Lab3D.CHARACTERS                       — [{ id, label, blurb, line }] in display order (line: a personality, never a job)
 *   const c = Lab3D.makeCharacter(K, 'human', { color: '#5ccfbc', hue: 40, scale: 1 });
 *     color: the role badge on its chest · hue: turns its FAMILY colour round the wheel (a main agent and its
 *     subagents share it: the scientist's scarf, the frog's spots and toes, the owl's tufts and wing tips, the
 *     fox's scarf, the robot's antenna and chest light; the penguin's bow tie, the hedgehog's cardigan, the bee's
 *     satchel and antenna tips, the capybara's towel, the snail's antenna tips and bookmark, the dragon's wings and
 *     spikes) · scale: its size. An unknown id gives the newt. world3d/cast.html shows them all, in every pose.
 *   c.group                       — add it to the scene (stands on y = 0, faces +z)
 *   c.update(t, { pose, moving, act, poke }) — as the newt's: one shared animator (Lab3D.animator, newt.js), and
 *     each character's own fidgets while it stands idle
 *   c.head                        — the head's group
 *
 * Loaded after kit.js and newt.js. At night the family colour glows a little, as the newt's gills do.
 */
(function () {
  'use strict';
  const L = (window.Lab3D = window.Lab3D || {});

  L.CHARACTERS = [
    { id: 'newt', label: 'Newt' }, { id: 'human', label: 'Scientist' }, { id: 'robot', label: 'Robot' }
  ];
  L.LIBRARY_CHARACTERS = L.CHARACTERS;

  // the family colour at hue 0 (the newt's pink), turned like the newt's gills
  const FAM = '#f58cc4';
  const turn = (THREE, c, deg) => (deg ? '#' + new THREE.Color(c).offsetHSL(deg / 360, 0, 0).getHexString() : c);

  // geometries are shared by every instance (they don't depend on the theme)
  const GEO = new Map();
  const geo = (key, make) => L.resources.cached(GEO, key, make);

  /** the per-character toolbox: shared geometry, materials, a mesh-adder */
  function tools(K, o) {
    const { THREE } = K, fam = turn(THREE, FAM, o.hue || 0);
    const T = {
      THREE, fam,
      // smooth, round, high-poly: a toy you could pick up (the segment counts asked for are a floor, doubled)
      sph: (r, w, h) => geo(`s${r}|${w || 14}|${h || 10}`, () => K.geometry('SphereGeometry', r, Math.max(28, (w || 14) * 2), Math.max(20, (h || 10) * 2))),
      cap: (r, l) => geo(`c${r}|${l}`, () => K.geometry('CapsuleGeometry', r, l, 8, 20)),
      cone: (r, h, s) => geo(`k${r}|${h}|${s || 8}`, () => K.geometry('ConeGeometry', r, h, Math.max(20, (s || 8) * 2))),
      cyl: (rt, rb, h, s) => geo(`y${rt}|${rb}|${h}|${s || 12}`, () => K.geometry('CylinderGeometry', rt, rb, h, Math.max(24, (s || 12) * 2))),
      box: (w, h, d) => geo(`b${w}|${h}|${d}`, () => K.geometry('BoxGeometry', w, h, d)),   // crisp: the robot is a machine
      torus: (r, t, arc) => geo(`t${r}|${t}|${arc || 0}`, () => K.geometry('TorusGeometry', r, t, 12, 36, arc || Math.PI * 2)),
      lathe: (name, prof) => geo('l' + name, () => K.geometry('LatheGeometry', prof.map(([r, y]) => new THREE.Vector2(r, y)), 40)),
      mat: (c, extra) => K.mat(c, Object.assign({ smooth: true, rough: 0.7 }, extra)),
      // the family colour: soft by day, glowing a little at night (like the newt's gills)
      famMat: (gid, gn) => K.mat(fam, { smooth: true, rough: 0.6, glow: fam, gi: {day:gid ?? 0.12,night:gn ?? 0.55} }),
      dark: K.mat('#151517', { smooth: true, rough: 0.3 }),
      hl: K.mat('#ffffff', { smooth: true, glow: '#ffffff', gi: 0.6 }),
      blush: K.mat('#f4a3a8', { smooth: true, rough: 0.9 }),
      /** add a mesh to parent; returns it */
      add(parent, g, m, x, y, z, sx, sy, sz) {
        const me = K.mesh(g, m, x, y, z);
        if (sx != null) me.scale.set(sx, sy ?? sx, sz ?? sx);
        parent.add(me); return me;
      },
      /** the role badge on the chest, like the newt's */
      badge(parent, x, y, z) {
        if (!o.color) return null;
        const b = K.mesh(T.sph(0.045, 14, 10), K.mat(o.color, { glow: o.color, gi: {day:0.25,night:0.9}, smooth: true }), x, y, z);
        b.scale.z = 0.5; parent.add(b); return b;
      },
      /** a pair of dark bead eyes with a highlight each */
      eyes(parent, dx, y, z, r) {
        return [-1, 1].map(s => {
          const e = T.add(parent, T.sph(r, 12, 10), T.dark, s * dx, y, z);
          T.add(e, T.sph(r * 0.28, 6, 6), T.hl, r * 0.3, r * 0.35, r * 0.85);
          return e;
        });
      },
      /** big, shiny eyes: a little taller than round, a big catchlight up top and a small one below */
      cuteEyes(parent, dx, y, z, r, iris) {
        return [-1, 1].map(s => {
          const e = T.add(parent, T.sph(r, 16, 12), iris ? T.mat(iris, { rough: 0.35 }) : T.dark, s * dx, y, z, 1, 1.12, 0.75);
          const p = iris ? T.add(e, T.sph(r * 0.62, 14, 10), T.dark, 0, -r * 0.04, r * 0.5) : e;
          T.add(p, T.sph(r * (iris ? 0.42 : 0.34), 8, 6), T.hl, r * 0.3, r * 0.34, r * 0.72);
          T.add(p, T.sph(r * (iris ? 0.2 : 0.15), 6, 6), T.hl, -r * 0.28, -r * 0.3, r * 0.78);
          return e;
        });
      },
      /** an arm: a group pivoting at the shoulder, the limb hanging down (-y) */
      arm(parent, s, x, y, z) { const a = new THREE.Group(); a.position.set(s * x, y, z); parent.add(a); return a; },
    };
    return T;
  }

  /** wrap up: shadows, scale, first frame */
  function finish(root, o, R) {
    if (o.scale) root.scale.setScalar(o.scale);
    const update = L.animator(Object.assign({ seed: o.seed ?? o.hue ?? 0 }, R)); update(0, {});
    return { group: root, update, rig:R, head:R.head, slots: { left: R.arms[0], right: R.arms[1], head: R.head } };
  }

  function legsPair(T, body, g, m, dx, y) {
    return [-1, 1].map(s => T.add(body, g, m, s * dx, y, 0.02));
  }
  /** a lathe profile's radius at height y (to set things on a body's surface) */
  function profR(prof, y) {
    for (let i = 1; i < prof.length; i++) {
      const [r0, y0] = prof[i - 1], [r1, y1] = prof[i];
      if (y <= y1) return r0 + (r1 - r0) * Math.max(0, (y - y0) / ((y1 - y0) || 1));
    }
    return 0;
  }
  const ease = u => u * u * (3 - 2 * u);

  // ── the mini human: a little scientist in a lab coat, round glasses and a scarf in the family colour ──
  function human(K, o) {
    const T = tools(K, o), { THREE } = T, root = new THREE.Group(), body = new THREE.Group(), head = new THREE.Group();
    root.add(body);
    const skin = T.mat('#f2c6a2'), coat = T.mat('white', { rough: 0.8 }), trousers = T.mat('#3d4a63'), shoe = T.mat('#5a3a2a'), hairM = T.mat('#5b3b26', { rough: 0.9 }), fam = T.famMat();
    // legs in trousers, with round shoes
    const legs = legsPair(T, body, T.cap(0.055, 0.1), trousers, 0.085, 0.11);
    legs.forEach(l => T.add(l, T.sph(0.066, 12, 8), shoe, 0, -0.085, 0.035, 1, 0.55, 1.45));
    // the lab coat: a flared lathe, two buttons
    T.add(body, T.lathe('coat', [[0.001, 0.1], [0.19, 0.1], [0.205, 0.18], [0.185, 0.38], [0.16, 0.55], [0.12, 0.67], [0.001, 0.72]]), coat);
    [0.3, 0.2].forEach(y => T.add(body, T.sph(0.014, 6, 6), T.mat('#9aa7ad'), 0.0, y, 0.195));
    // the scarf: a ring round the neck and one end hanging down the front
    const ring = T.add(body, T.torus(0.11, 0.042), fam, 0, 0.665, 0); ring.rotation.x = Math.PI / 2;
    const end = T.add(body, T.box(0.075, 0.2, 0.04), fam, 0.07, 0.54, 0.16); end.rotation.set(-0.2, 0, 0.12);
    // the role badge, clipped on the coat
    T.badge(body, -0.085, 0.43, 0.165);
    // arms: white sleeves, hands
    const arms = [-1, 1].map(s => {
      const a = T.arm(body, s, 0.155, 0.58, 0.05);
      T.add(a, T.cap(0.046, 0.14), coat, 0, -0.08, 0); T.add(a, T.sph(0.048, 10, 8), skin, 0, -0.19, 0);
      return a;
    });
    // the round head: hair cap tilted back, a side fringe and a cowlick
    head.position.set(0, 0.95, 0); body.add(head);
    T.add(head, T.sph(0.22, 20, 14), skin, 0, 0, 0, 1.06, 0.98, 1);
    const cap = T.add(head, geo('hairCap', () => K.geometry('SphereGeometry', 0.236, 20, 10, 0, Math.PI * 2, 0, Math.PI * 0.56)), hairM, 0, 0.0, -0.005, 1.07, 1, 1.06);
    cap.rotation.x = -0.55;
    const fringe = T.add(head, T.sph(0.1, 12, 8), hairM, -0.06, 0.15, 0.145, 1.5, 0.5, 0.8); fringe.rotation.set(0.5, 0, 0.3);
    const lick = T.add(head, T.cone(0.035, 0.12, 6), hairM, 0.03, 0.25, -0.02); lick.rotation.set(-0.3, 0, -0.5);
    [-1, 1].forEach(s => T.add(head, T.sph(0.045, 8, 6), skin, s * 0.23, -0.01, 0, 0.6, 1, 1));   // ears
    const eyes = T.eyes(head, 0.078, 0.0, 0.2, 0.03);
    // round glasses
    const rim = T.mat('#2d2a26', { rough: 0.4 });
    [-1, 1].forEach(s => T.add(head, T.torus(0.052, 0.009), rim, s * 0.078, 0.0, 0.222));
    T.add(head, T.box(0.05, 0.01, 0.01), rim, 0, 0.012, 0.228);
    [-1, 1].forEach(s => T.add(head, T.sph(0.035, 8, 6), T.blush, s * 0.135, -0.075, 0.165, 1, 0.6, 0.4));   // rosy cheeks
    const smile = T.add(head, T.torus(0.035, 0.007, Math.PI), T.dark, 0, -0.085, 0.205); smile.rotation.z = Math.PI;
    const brows = L.brows(K, eyes, null).map(b => { b.position.y += 0.012; b.userData.y = b.position.y; return b; });   // above the glasses
    return finish(root, o, { body, head, legs, arms, eyes, brows, mouth: smile, legY: 0.11,
      fidgets: [
        (o, k) => { o.armR = -0.55 - 1.75 * k; o.raiseR = -0.6 * k; o.tilt = 0.06 * k; },                       // pushes its glasses up
        (o, k) => { o.armL = -0.55 - 0.85 * k; o.raiseL = -0.25 * k; o.tilt = 0.32 * k; o.turn = -0.2 * k; },   // checks its watch
        (o, k, tt) => { o.armR = -0.35; o.raiseR = (2.45 + Math.sin(tt * 16) * 0.12) * k; o.roll = -0.08 * k; },  // scratches its head
      ] });
  }

  // ── the frog: a round little frog — a big head, eyes like marbles on top, rosy cheeks, family-coloured toes ──
  function robot(K, o) {
    const T = tools(K, o), { THREE } = T, root = new THREE.Group(), body = new THREE.Group(), head = new THREE.Group();
    root.add(body);
    const shell = T.mat('#d3dcdf', { rough: 0.45, metal: 0.15 }), joint = T.mat('#8e9ba2', { rough: 0.5, metal: 0.2 }), screen = T.mat('#26353c', { rough: 0.3 });
    const famLight = T.famMat(0.45, 0.9), eyeM = K.mat('#bff6ff', { smooth: true, glow: '#8fefff', gi: {day:0.6,night:1.0} });
    const legs = legsPair(T, body, T.cyl(0.05, 0.05, 0.14, 10), joint, 0.095, 0.12);
    legs.forEach(l => T.add(l, T.box(0.12, 0.06, 0.17), shell, 0, -0.08, 0.025));
    T.add(body, T.box(0.38, 0.4, 0.3), shell, 0, 0.4, 0);
    T.add(body, T.box(0.2, 0.075, 0.02), famLight, 0, 0.29, 0.155);   // the chest light
    T.badge(body, 0, 0.47, 0.158);
    T.add(body, T.cyl(0.055, 0.065, 0.1, 10), joint, 0, 0.64, 0);    // neck
    const arms = [-1, 1].map(s => {
      const a = T.arm(body, s, 0.215, 0.56, 0.0);
      T.add(a, T.sph(0.05, 10, 8), joint, 0, 0, 0);
      T.add(a, T.cyl(0.035, 0.035, 0.2, 8), joint, 0, -0.11, 0); T.add(a, T.sph(0.055, 10, 8), shell, 0, -0.23, 0);
      return a;
    });
    head.position.set(0, 0.87, 0); body.add(head);
    T.add(head, T.box(0.46, 0.33, 0.34), shell, 0, 0, 0);
    T.add(head, T.box(0.37, 0.22, 0.02), screen, 0, -0.005, 0.17);
    const eyes = [-1, 1].map(s => T.add(head, T.sph(0.038, 10, 8), eyeM, s * 0.085, 0.02, 0.18, 1, 1.35, 0.6));
    const smile = T.add(head, T.torus(0.04, 0.008, Math.PI), eyeM, 0, -0.045, 0.182); smile.rotation.z = Math.PI;
    [-1, 1].forEach(s => { const b = T.add(head, T.cyl(0.055, 0.055, 0.04, 10), joint, s * 0.245, 0, 0); b.rotation.z = Math.PI / 2; });
    T.add(head, T.cyl(0.012, 0.012, 0.14, 6), joint, 0, 0.235, 0);
    const bulb = T.add(head, T.sph(0.045, 12, 10), famLight, 0, 0.33, 0);
    const brows = L.brows(K, eyes, '#8fefff');
    return finish(root, o, { body, head, legs, arms, eyes, brows, mouth: smile, legY: 0.12,
      fidgets: [
        (o, k, tt, u) => { o.turn = u * Math.PI * 2; },                                                      // its head, right round
        (o, k, tt) => { o.look = Math.sign(Math.sin(tt * 3)) * k * 1.4; o.tilt = -0.06 * k; },               // an eye scan
        (o, k) => { o.face = 'happy'; o.raiseL = 0.4 * k; o.raiseR = 0.4 * k; },                              // a pleased beep
      ],
      extra(tt, pose, moving, f) {
        const k = pose === 'wait' ? 1 + Math.abs(Math.sin(tt * 6)) * 0.5 : pose === 'work' ? 1 + Math.max(0, Math.sin(tt * 12)) * 0.3
          : f && f.i === 2 ? 1 + Math.max(0, Math.sin(tt * 20)) * 0.6 : pose === 'sleep' || pose === 'fail' ? 0.75 : 1 + Math.sin(tt * 2.5) * 0.08;
        bulb.scale.setScalar(k);
      } });
  }

  // ── the penguin: a round little intern — a navy coat, a heart-shaped white face, a bow tie in the family colour,
  //    a clipboard tucked under one flipper (crisp: it's stationery) ──
  const BUILDERS = { human, robot };

  L.attachAccessory = (K, character, id, side = 'right') => {
    if (!['document', 'clipboard', 'mug'].includes(id) || !character.slots || !character.slots[side]) return null;
    const prop = K.build(id); prop.position.set(0, -0.17, 0.06); prop.rotation.x = Math.PI / 2;
    character.slots[side].add(prop); return prop;
  };

  /** any character by id (an unknown id gives the newt); the same interface as Lab3D.makeNewt */
  L.makeCharacter = function makeCharacter(K, id, o) {
    o = o || {};
    const b = BUILDERS[id];
    const character=b?b(K,o):L.makeNewt(K,o);character.character=b?id:'newt';return character;
  };
})();
