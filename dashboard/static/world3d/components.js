/* Lab3D — the furniture kit. Each piece is a few primitives (1 unit = 1 m; it stands on y = 0 and faces
 * +z). A lab adds its own with Lab3D.defineComponent(name, { build(K, props) { … }, uses, stands }) in a file of
 * its own. `uses`: the activities an agent comes to it for (the tracer's vocabulary: read · search · edit · run ·
 * bash · git · spawn · plan · skill · mcp · tool); `stands`: where it stands to use it — [[x, z, facing?], …] in the
 * piece's own frame (it faces +z, so in front is +z; an agent faces it square on unless a spot says), or a function
 * of the piece's props. An agent reading walks to a
 * shelf, one running an experiment to a bench, one briefing a subagent to a whiteboard — whatever the room holds. */
(function () {
  'use strict';
  const L = window.Lab3D, C = L.defineComponent;
  const legs4 = (K, w, d, h, c, r) => [[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([a, b]) => K.box(r || 0.06, h, r || 0.06, c, a * (w / 2 - 0.06), 0, b * (d / 2 - 0.06)));

  C('desk', { build(K, p) {
    const w = p.w || 1.4, d = p.d || 0.7, h = 0.74;
    return K.group(K.box(w, 0.05, d, p.top || 'wood', 0, h, 0), legs4(K, w, d, h, 'woodDark'));
  } });
  C('chair', { build(K, p) {
    return K.group(K.box(0.42, 0.06, 0.42, p.c || 'woodDark', 0, 0.42, 0), K.box(0.42, 0.42, 0.05, p.c || 'woodDark', 0, 0.48, -0.19), legs4(K, 0.42, 0.42, 0.42, 'woodDark', 0.04));
  } });
  C('monitor', { build(K, p) {
    const w = p.w || 0.55;
    return K.group(K.box(0.08, 0.18, 0.08, 'steel', 0, 0, 0, { sharp: true }), K.box(w, w * 0.6, 0.04, 'black', 0, 0.16, 0, { sharp: true }), K.box(w - 0.05, w * 0.6 - 0.05, 0.01, 'screen', 0, 0.185, 0.021, { glow: 'screen', gi: {day:0.5,night:1.6}, sharp: true }));
  } });
  C('deskLamp', { build(K) {
    return K.group(K.cyl(0.07, 0.08, 0.03, 'steel'), K.cyl(0.012, 0.012, 0.32, 'steel', 0, 0.03), K.cone(0.09, 0.1, 'lamp', 0, 0.3, 0.04, { glow: 'lamp', gi: {day:0.4,night:2} }));
  } });
  /** a desk with its screen(s), chair and lamp — the default place an agent works */
  C('workstation', { build(K, p) {
    const g = K.group(K.build('desk', { w: p.w || 1.4, top: p.top }));
    const n = p.monitors ?? 1;
    for (let i = 0; i < n; i++) g.add(K.at(K.build('monitor', {}), (i - (n - 1) / 2) * 0.6, 0.77, -0.15));
    if (p.lamp !== false) g.add(K.at(K.build('deskLamp'), (p.w || 1.4) / 2 - 0.2, 0.77, -0.15));
    if (p.papers !== false) g.add(K.box(0.3, 0.02, 0.22, 'paper', -(p.w || 1.4) / 2 + 0.25, 0.77, 0.1));
    if (p.chair !== false) g.add(K.at(K.build('chair', {}), 0, 0, 0.55, Math.PI));
    return g;
  } });
  C('bookshelf', { build(K, p) {
    const w = p.w || 1.6, h = p.h || 1.9, d = 0.38, g = K.group(K.box(w, h, d, 'woodDark', 0, 0, -0.02), K.box(w - 0.08, h - 0.1, d - 0.04, 'wood', 0, 0.05, 0.01));
    const cols = ['teal', 'rose', 'ochre', 'blue', 'violet', 'paper', 'green'];
    for (let r = 0; r < 4; r++) {
      const y = 0.12 + r * (h - 0.2) / 4; g.add(K.box(w - 0.08, 0.03, d - 0.04, 'woodDark', 0, y - 0.03, 0.02));
      let x = -w / 2 + 0.1; let i = r * 3;
      while (x < w / 2 - 0.15) { const bw = 0.06 + ((i * 37) % 5) * 0.012, bh = (h - 0.2) / 4 * (0.62 + ((i * 13) % 4) * 0.08); g.add(K.box(bw, bh, 0.24, cols[i % cols.length], x + bw / 2, y, 0.04)); x += bw + 0.012; i++; }
    }
    return g;
  } });
  C('flask', { build(K, p) {
    const c = p.liquid || 'liquid';
    return K.group(K.cyl(0.03, 0.09, 0.16, 'glass', 0, 0, 0, { alpha: 0.45, seg: 10 }), K.cyl(0.02, 0.075, 0.09, c, 0, 0.01, 0, { glow: c, gi: {day:0.35,night:1.4}, seg: 10 }), K.cyl(0.02, 0.02, 0.08, 'glass', 0, 0.16, 0, { alpha: 0.45 }));
  } });
  C('microscope', { build(K) {
    return K.group(K.box(0.18, 0.03, 0.22, 'steel'), K.box(0.04, 0.26, 0.04, 'steel', 0, 0.03, -0.06), K.cyl(0.03, 0.03, 0.2, 'black', 0, 0.2, 0.0));
  } });
  C('labBench', { build(K, p) {
    const w = p.w || 2.2, d = 0.8, h = 0.9, g = K.group(K.box(w, h - 0.05, d, 'plasterDark', 0, 0, 0), K.box(w + 0.04, 0.05, d + 0.04, 'paper', 0, h - 0.05, 0));
    const liq = ['liquid', 'green', 'rose', 'violet'];
    for (let i = 0; i < (p.flasks ?? 5); i++) g.add(K.at(K.build('flask', { liquid: liq[i % 4] }), -w / 2 + 0.3 + i * 0.28, h, -0.15 + (i % 2) * 0.12));
    g.add(K.at(K.build('microscope'), w / 2 - 0.35, h, -0.1));
    return g;
  } });
  C('vessel', { build(K, p) {
    const h = p.h || 1.7, c = p.liquid || 'liquid';
    return K.group(K.cyl(0.42, 0.48, 0.25, 'steel'), K.cyl(0.36, 0.36, h - 0.45, 'glass', 0, 0.25, 0, { alpha: 0.35, seg: 18 }), K.cyl(0.32, 0.32, (h - 0.45) * 0.7, c, 0, 0.27, 0, { glow: c, gi: {day:0.4,night:1.6}, seg: 18, alpha: 0.85 }),
      K.cyl(0.42, 0.38, 0.2, 'steel', 0, h - 0.2, 0), K.cyl(0.04, 0.04, 0.4, 'steel', 0.2, h, 0));
  } });
  C('rack', { build(K, p) {
    const h = p.h || 1.9, g = K.group(K.box(0.7, h, 0.6, 'black', 0, 0, 0, { sharp: true }));
    for (let i = 0; i < 8; i++) { g.add(K.box(0.6, 0.12, 0.02, 'steel', 0, 0.15 + i * 0.2, 0.3, { sharp: true })); g.add(K.box(0.05, 0.03, 0.02, i % 3 ? 'green' : 'amber', 0.22, 0.2 + i * 0.2, 0.31, { glow: true, gi: 1.6, sharp: true })); }
    return g;
  } });
  C('whiteboard', { build(K, p) {
    const w = p.w || 1.6, g = K.group(K.box(0.05, 1.7, 0.05, 'steel', -w / 2, 0, 0), K.box(0.05, 1.7, 0.05, 'steel', w / 2, 0, 0), K.box(w, 1.0, 0.04, 'white', 0, 0.65, 0));
    ['teal', 'rose', 'blue', 'ochre'].forEach((c, i) => g.add(K.box(0.3 + (i % 2) * 0.25, 0.03, 0.01, c, -w / 2 + 0.4 + (i % 2) * 0.3, 1.45 - i * 0.18, 0.025)));
    g.add(K.box(0.35, 0.26, 0.01, 'ochre', w / 2 - 0.35, 1.2, 0.025)); g.add(K.box(0.3, 0.22, 0.01, 'rose', w / 2 - 0.45, 0.85, 0.025));
    return g;
  } });
  C('plant', { build(K, p) {
    const s = p.size || 1, g = K.group(K.cyl(0.2 * s, 0.15 * s, 0.3 * s, 'pot'), K.cyl(0.21 * s, 0.21 * s, 0.05 * s, 'pot', 0, 0.28 * s), K.cyl(0.18 * s, 0.18 * s, 0.02, 'soil', 0, 0.31 * s));
    if (p.kind === 'tall') {                          // a little topiary: a stem and three round puffs
      g.add(K.cyl(0.025, 0.03, 1.0 * s, 'woodDark', 0, 0.3 * s)); [0.85, 1.12, 1.34].forEach((y, i) => g.add(K.sphere(0.26 * s - i * 0.05, i % 2 ? 'plant' : 'leaf', 0, y * s, 0)));
    } else if (p.kind === 'fern') {                    // a fan of soft leaves
      for (let i = 0; i < 8; i++) { const l = K.sphere(0.1 * s, i % 2 ? 'plant' : 'leaf', 0, 0, 0); l.scale.set(0.7, 3.2, 0.5); const a = i / 8 * Math.PI * 2;
        const piv = K.group(l); l.position.y = 0.3 * s; piv.position.y = 0.32 * s; piv.rotation.set(Math.sin(a) * 0.65, 0, Math.cos(a) * 0.65); g.add(piv); }
    } else {                                           // a round bush, a few puffs together
      [[0, 0.56, 0, 0.3], [0.16, 0.66, 0.06, 0.2], [-0.15, 0.62, -0.04, 0.2], [0.02, 0.8, -0.02, 0.17]].forEach(([x, y, z, r], i) => g.add(K.sphere(r * s, i % 2 ? 'leaf' : 'plant', x * s, y * s, z * s)));
    }
    return g;
  } });
  /** a few flowers in the grass: little round heads on stems, in two or three colours */
  C('flowers', { build(K, p) {
    const g = K.group(), n = p.n || 7, cols = ['flower', 'flower2', 'flower3'];
    for (let i = 0; i < n; i++) {
      const a = i * 2.4, r = 0.12 + (i % 3) * 0.12, x = Math.cos(a) * r, z = Math.sin(a) * r, h = 0.14 + (i % 4) * 0.04;
      g.add(K.cyl(0.008, 0.01, h, 'leaf', x, 0, z), K.sphere(0.045, cols[(i + (p.hue || 0)) % 3], x, h + 0.02, z), K.sphere(0.02, 'ochre', x, h + 0.04, z + 0.02));
    }
    return g;
  } });
  /** a pebble or two: squashed, soft stones */
  C('rock', { build(K, p) {
    const s = p.size || 1, a = K.sphere(0.22 * s, 'stone', 0, 0.06 * s, 0); a.scale.set(1.2, 0.55, 0.9);
    const b = K.sphere(0.12 * s, 'stone', 0.24 * s, 0.03 * s, 0.1 * s); b.scale.set(1, 0.6, 0.9);
    return K.group(a, b);
  } });
  C('floorLamp', { build(K) {
    const shade = K.sphere(0.2, 'lamp', 0, 1.62, 0, { glow: 'lamp', gi: {day:0.3,night:1.8} }); shade.scale.set(1, 0.75, 1);
    return K.group(K.cyl(0.17, 0.2, 0.06, 'woodDark'), K.cyl(0.025, 0.025, 1.45, 'woodDark', 0, 0.06), shade, K.sphere(0.03, 'woodDark', 0, 1.79, 0));
  } });
  C('crates', { build(K, p) {
    const g = K.group(); const n = p.n || 3;
    for (let i = 0; i < n; i++) g.add(K.box(0.5, 0.4, 0.45, i % 2 ? 'wood' : 'woodLight', (i % 2) * 0.55 - 0.25, Math.floor(i / 2) * 0.4, (i % 3) * 0.05));
    return g;
  } });
  C('easel', { build(K) {
    const g = K.group(); const l1 = K.box(0.05, 1.7, 0.05, 'woodDark', -0.3, 0, 0); l1.rotation.z = 0.12; const l2 = K.box(0.05, 1.7, 0.05, 'woodDark', 0.3, 0, 0); l2.rotation.z = -0.12;
    g.add(l1, l2, K.box(0.9, 0.7, 0.04, 'paper', 0, 0.8, 0.06), K.box(0.5, 0.25, 0.01, 'blue', -0.1, 1.0, 0.085), K.box(0.25, 0.3, 0.01, 'rose', 0.22, 0.9, 0.085));
    return g;
  } });
  C('press', { build(K) {
    const g = K.group(K.box(1.0, 0.9, 0.7, 'steel'), K.box(0.8, 0.08, 0.5, 'paper', 0, 0.9, 0), K.box(0.12, 0.7, 0.12, 'black', 0, 0.9, 0));
    const wheel = K.mesh(new K.THREE.TorusGeometry(0.28, 0.035, 8, 20), K.mat('woodDark'), 0.6, 0.75, 0); wheel.rotation.y = Math.PI / 2; g.add(wheel);
    return g;
  } });
  C('cabinet', { build(K, p) {
    const h = p.h || 1.3, g = K.group(K.box(0.6, h, 0.55, 'metal', 0, 0, 0, { sharp: true }));
    for (let i = 0; i < 4; i++) g.add(K.box(0.18, 0.04, 0.02, 'steel', 0, 0.2 + i * (h - 0.2) / 4, 0.28));
    return g;
  } });
  C('lectern', { build(K) {
    const top = K.box(0.6, 0.05, 0.45, 'wood', 0, 1.05, 0); top.rotation.x = 0.35;
    return K.group(K.box(0.4, 1.0, 0.35, 'woodDark'), top, K.box(0.4, 0.01, 0.3, 'paper', 0, 1.1, 0.02));
  } });
  C('trays', { build(K, p) {
    const w = p.w || 1.8, g = K.group(K.box(w, 0.7, 0.6, 'woodLight'), K.box(w, 0.1, 0.6, 'soil', 0, 0.7, 0));
    for (let i = 0; i < 9; i++) g.add(K.cone(0.05, 0.12 + (i % 3) * 0.06, i % 4 ? 'plant' : 'green', -w / 2 + 0.15 + i * (w - 0.3) / 8, 0.8, (i % 2) * 0.15 - 0.07, { seg: 5, glow: K.night && i % 3 === 0 ? 'green' : null, gi: 0.6 }));
    return g;
  } });
  C('roundTable', { build(K, p) {
    const g = K.group(K.cyl(0.6, 0.6, 0.05, 'wood', 0, 0.72), K.cyl(0.06, 0.06, 0.72, 'woodDark'), K.cyl(0.3, 0.3, 0.03, 'woodDark'));
    for (let i = 0; i < (p.stools ?? 3); i++) { const a = i / (p.stools ?? 3) * Math.PI * 2; g.add(K.cyl(0.18, 0.18, 0.45, 'carpet', Math.cos(a) * 0.95, 0, Math.sin(a) * 0.95)); }
    g.add(K.box(0.25, 0.02, 0.2, 'paper', 0.1, 0.77, 0.05));
    return g;
  } });
  C('armchair', { build(K, p) {
    const c = p.c || 'carpet';
    return K.group(K.box(0.8, 0.4, 0.75, c), K.box(0.8, 0.5, 0.15, c, 0, 0.4, -0.3), K.box(0.12, 0.25, 0.7, c, -0.34, 0.4, 0), K.box(0.12, 0.25, 0.7, c, 0.34, 0.4, 0));
  } });
  C('rug', { build(K, p) {
    const m = K.mesh(new K.THREE.CylinderGeometry(p.r || 1.2, p.r || 1.2, 0.015, 32), K.mat(p.c || 'rug'), 0, 0.008, 0); m.castShadow = false; if (p.sx) m.scale.x = p.sx;
    return K.group(m);
  } });
  C('archiveShelf', { build(K, p) {
    const w = p.w || 1.8, h = 2.0, g = K.group(K.box(w, h, 0.5, 'steel', 0, 0, -0.02));
    for (let r = 0; r < 4; r++) for (let i = 0; i < 5; i++) g.add(K.box(w / 5 - 0.06, 0.32, 0.36, (r + i) % 3 ? 'woodLight' : 'paper', -w / 2 + (i + 0.5) * w / 5, 0.1 + r * 0.48, 0.05));
    return g;
  } });
  C('parkBench', { build(K) {
    return K.group(K.box(1.4, 0.05, 0.45, 'wood', 0, 0.42, 0), K.box(1.4, 0.35, 0.05, 'wood', 0, 0.5, -0.2), K.box(0.05, 0.42, 0.4, 'black', -0.6, 0, 0), K.box(0.05, 0.42, 0.4, 'black', 0.6, 0, 0));
  } });
  C('streetLamp', { build(K) {
    return K.group(K.cyl(0.1, 0.13, 0.12, 'black'), K.cyl(0.045, 0.06, 1.8, 'black', 0, 0.1), K.cyl(0.1, 0.07, 0.06, 'black', 0, 1.88),
      K.sphere(0.15, 'lamp', 0, 2.06, 0, { glow: 'lamp', gi: {day:0.3,night:2.2} }), K.cone(0.09, 0.09, 'black', 0, 2.18, 0));
  } });
  /** a tree: a round, fluffy crown of a few puffs on a short trunk — some with fruit — or now and then a soft pine */
  C('tree', { build(K, p) {
    const s = p.size || 1, v = p.v ?? Math.floor((s * 97) % 4);
    if (v === 3) {                                       // the pine: three soft tiers
      const g = K.group(K.cyl(0.08 * s, 0.11 * s, 0.5 * s, 'woodDark'));
      [[0.45, 0.62, 0.35], [0.85, 0.5, 0.3], [1.2, 0.36, 0.26]].forEach(([y, r, h], i) => { const c = K.cone(r * s, h * 2.2 * s, i % 2 ? 'leaf' : 'plant', 0, y * s, 0); g.add(c); });
      return g;
    }
    const g = K.group(K.cyl(0.08 * s, 0.13 * s, 0.75 * s, 'woodDark'));
    const puffs = [[0, 1.15, 0, 0.52], [0.32, 0.98, 0.1, 0.36], [-0.3, 1.0, -0.06, 0.38], [0.05, 0.98, 0.32, 0.34], [0.02, 1.48, -0.05, 0.34]];
    puffs.forEach(([x, y, z, r], i) => g.add(K.sphere(r * s, i % 3 === 1 ? 'plant' : 'leaf', x * s, y * s, z * s)));
    if (v === 1) [[0.28, 1.0, 0.36], [-0.38, 1.12, 0.22], [0.12, 1.42, 0.38], [0.45, 1.25, 0.05]].forEach(([x, y, z]) => g.add(K.sphere(0.07 * s, 'fruit', x * s, y * s, z * s)));
    return g;
  } });
  C('noticeBoard', { build(K, p) {
    const w = p.w || 1.4, g = K.group(K.box(w, 0.9, 0.05, 'woodLight', 0, 1.0, 0), K.box(0.05, 1.9, 0.05, 'woodDark', -w / 2 + 0.05, 0, -0.03), K.box(0.05, 1.9, 0.05, 'woodDark', w / 2 - 0.05, 0, -0.03));
    ['paper', 'ochre', 'paper', 'rose', 'paper', 'blue'].forEach((c, i) => g.add(K.box(0.28, 0.2, 0.01, c, -w / 2 + 0.25 + (i % 4) * 0.3, 1.6 - Math.floor(i / 4) * 0.3 - (i % 2) * 0.08, 0.03)));
    return g;
  } });
  /** the PI's desk at the middle of the table: where questions queue and gates are signed */
  // what each piece is for (above), and where an agent stands at it
  const along = (w, n) => Array.from({ length: n }, (_, i) => (i - (n - 1) / 2) * (w / n));
  const wide = (w, z) => (w > 1.6 ? [[0, z], [-w / 3, z], [w / 3, z]] : [[0, z]]);     // the middle first, then either end
  const USES = {
    workstation: [['edit', 'bash', 'git', 'tool', 'mcp', 'skill'], [[0, 0.75]]],
    desk: [['edit', 'tool'], [[0, 0.65]]],
    press: [['edit'], [[0, 0.8]]],
    bookshelf: [['read'], p => along(p.w || 1.6, 2).map(x => [x, 0.7])],
    archiveShelf: [['read'], p => along(p.w || 1.8, 2).map(x => [x, 0.75])],
    cabinet: [['read'], [[0, 0.6]]],
    trays: [['read'], p => along(p.w || 1.8, 2).map(x => [x, 0.7])],
    armchair: [['read'], [[0, 0.55]]],
    lectern: [['search', 'read'], [[0, 0.7]]],
    noticeBoard: [['search', 'plan'], [[0, 0.8]]],
    labBench: [['run'], p => wide(p.w || 2.2, 0.8)],
    rack: [['run', 'bash'], [[0, 0.7]]],
    vessel: [['run'], [[0, 0.95]]],
    microscope: [['run'], [[0, 0.5]]],
    whiteboard: [['plan', 'spawn'], p => [[0, 0.8], ...wide(p.w || 1.6, 1.2).slice(1)]],
    easel: [['plan'], [[0, 0.8]]],
    roundTable: [['spawn', 'plan'], p => Array.from({ length: p.stools ?? 3 }, (_, i) => { const a = i / (p.stools ?? 3) * Math.PI * 2; return [Math.cos(a), Math.sin(a), Math.atan2(-Math.cos(a), -Math.sin(a))]; })],   // round it, facing the middle
  };
  for (const [n, [uses, stands]] of Object.entries(USES)) if (L.components[n]) Object.assign(L.components[n], { uses, stands });

  C('hubDesk', { build(K) {
    const g = K.group(K.cyl(1.5, 1.6, 0.12, 'woodLight'), K.cyl(1.0, 1.0, 0.72, 'wood', 0, 0.12), K.cyl(1.15, 1.15, 0.06, 'woodLight', 0, 0.84));
    g.add(K.at(K.build('monitor', { w: 0.7 }), 0, 0.9, -0.5));
    g.add(K.at(K.build('chair', { c: 'teal' }), 0, 0.12, -1.35));
    g.add(K.box(0.5, 0.08, 0.36, 'woodDark', 0.55, 0.9, 0.1));        // the inbox tray
    g.add(K.at(K.build('deskLamp'), -0.6, 0.9, -0.3));
    return g;
  } });
  /** a checkpoint: a slim post with a diamond lantern hanging from its arm. The engine lights it amber (and turns
   *  it slowly) while a study waits at it; userData.lamp is the diamond, userData.sway what swings */
  C('lantern', { build(K) {
    const post = K.group(K.cyl(0.06, 0.08, 2.1, 'woodDark', 0, 0, 0), K.cyl(0.18, 0.22, 0.08, 'woodDark', 0, 0, 0), K.box(0.62, 0.06, 0.06, 'woodDark', 0.28, 2.06, 0));
    const sway = K.group(); sway.position.set(0.52, 2.03, 0);
    const y0 = -0.66, top = K.cone(0.2, 0.26, 'amber', 0, y0, 0, { seg: 4, glow: 'amber', gi: 0.15 });
    const bottom = K.cone(0.2, 0.26, top.material, 0, y0 - 0.26, 0, { seg: 4 });
    bottom.rotation.x = Math.PI;          // one material: the engine dims/lights it
    const lamp = K.group(top, bottom); lamp.material = top.material;
    sway.add(K.box(0.02, 0.4, 0.02, 'black', 0, -0.4, 0), lamp);
    post.add(sway);
    post.userData.lamp = lamp; post.userData.sway = sway;
    return post;
  } });

  C('document', { build(K, p) { return K.group(K.box(0.3, 0.012, 0.22, p.c || 'paper'), K.box(0.2, 0.003, 0.014, 'ink', 0, 0.012, -0.03)); } });
  C('clipboard', { build(K, p) { return K.group(K.box(0.28, 0.025, 0.36, p.c || 'wood'), K.box(0.23, 0.006, 0.28, 'paper', 0, 0.025, 0.015), K.box(0.09, 0.018, 0.035, 'steel', 0, 0.03, -0.13)); } });
  C('mug', { build(K, p) { const handle = K.mesh(K.geometry('TorusGeometry', 0.045, 0.012, 8, 16), K.mat(p.c || 'cream'), 0.09, 0.07, 0); return K.group(K.cyl(0.07, 0.06, 0.12, p.c || 'cream'), handle); } });
  // One catalog supplies creator limits and the renderer's interaction footprints.
  for (const [name, meta] of Object.entries((L.catalog && L.catalog.components) || {})) if (L.components[name]) {
    Object.assign(L.components[name], meta, { bounds(p = {}) {
      const scale = p.size || 1;
      return [(p.w || (p.r ? p.r * 2 * (p.sx || 1) : meta.bounds[0])) * scale, (p.d || (p.r ? p.r * 2 : meta.bounds[1])) * scale];
    } });
  }
})();
