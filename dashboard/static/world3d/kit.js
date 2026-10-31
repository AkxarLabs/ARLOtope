/* Lab3D — the tabletop lab's kit. Rooms and furniture are DATA and small builders, so a lab (or its
 * coding agent) can add its own without touching the engine:
 *
 *   Lab3D.defineComponent('bench', {           // one piece of furniture: built from primitives
 *     build(K, props) { return K.group(K.box(2, 0.9, 0.7, 'wood'), …); },   // 1 unit = 1 m, y up,
 *   });                                          //  standing on y = 0, its front facing +z
 *
 *   Lab3D.defineRoom({                           // one room's look (which rooms exist is the workflow's)
 *     key: 'lab', size: [10, 7], floor: 'tiles', wall: 'plaster', accent: 'teal',
 *     props: [{ c: 'bench', at: [x, z], rot: 0, props: {…} }],   // room-local: x across, z toward the
 *     stations: { experiment: [x, z], improve: [x, z] },          //  open front (the hub); back wall at -z
 *     roleStation: { overseer: [x, z] },                           // where a subagent role works here
 *   });
 *
 * A station is where an agent running that procedure stands; a procedure with no station gets a desk of
 * its own, laid out by the engine. A room with no file at all is drawn plain: a floor, low walls and a
 * desk per procedure. Colours are theme names (K.col), so every piece reads right by day and by night.
 */
(function () {
  'use strict';
  const L = (window.Lab3D = window.Lab3D || {});
  L.components = {};
  L.rooms = {};
  L.defineComponent = (name, def) => { L.components[name] = def; return def; };
  L.defineRoom = spec => { L.rooms[spec.key] = Object.assign({ size: [9, 7], floor: 'boards', wall: 'plaster', accent: 'teal', props: [], stations: {}, roleStation: {} }, spec); return L.rooms[spec.key]; };


  // Count actual mesh users, not cache entries. A removed instance releases only its last-used resources.
  const refs = new WeakMap(), tracked = new WeakSet();
  const resourcesOf = m => [m.geometry, ...[].concat(m.material || []).flatMap(a =>
    [a, ...new Set(Object.values(a).filter(v => v && v.isTexture))])].filter(Boolean);
  const retain = r => { const n = refs.get(r) || { count: 0 }; n.count++; refs.set(r, n); };
  const release = r => {
    const n = refs.get(r); if (!n || --n.count > 0) return;
    if (n.cache && n.cache.get(n.key) === r) n.cache.delete(n.key);
    if (r.dispose) r.dispose(); refs.delete(r);
  };
  L.resources = {
    holdMaterial(material) {
      const resources = resourcesOf({ material });resources.forEach(retain);
      return () => resources.forEach(release);
    },
    cached(cache, key, make) {
      if (cache.has(key)) return cache.get(key);
      const r = make();
      if (!refs.has(r)) { cache.set(key, r); refs.set(r, { count: 0, cache, key }); }
      return r;
    },
    track(root) { root.traverse(o => { if ((o.isMesh || o.isPoints || o.isSprite || o.isLine) && !tracked.has(o)) { tracked.add(o); resourcesOf(o).forEach(retain); } }); return root; },
    material(mesh, next) { const previous=resourcesOf(mesh),owned=tracked.has(mesh);mesh.material=next;if(owned){resourcesOf(mesh).forEach(retain);previous.forEach(release)}else L.resources.track(mesh); },
    release(root) {
      if (!root) return;
      root.traverse(o => {
        if ((o.isMesh || o.isPoints || o.isSprite || o.isLine) && tracked.has(o)) {
          resourcesOf(o).forEach(release); tracked.delete(o);
          o.userData.styleState?.releaseOriginals?.();
          for (const material of o.userData.styleState?.defaults || []) material.dispose();
        }
        if (o.isLight && o.shadow) o.shadow.dispose();
      });
      if (root.parent) root.parent.remove(root);
    },
  };
  const SHAPES = new Map();
  L.shape = (THREE, kind, args, detail = 'medium') => {
    const a = args.slice();
    if (detail !== 'high') {
      const slots = { SphereGeometry: [1, 2], CylinderGeometry: [3], ConeGeometry: [2],
        CapsuleGeometry: [2, 3], LatheGeometry: [1], TorusGeometry: [2, 3] }[kind] || [];
      const factor = detail === 'low' ? 0.4 : 0.65;
      slots.forEach(i => { if (typeof a[i] === 'number') a[i] = Math.max(i === 2 && kind === 'CapsuleGeometry' ? 2 : 6, Math.round(a[i] * factor)); });
    }
    return L.resources.cached(SHAPES, kind + '|' + JSON.stringify(a), () => new THREE[kind](...a));
  };

  // palettes: soft, warm, low-saturation by day; the same hues dimmed by night, with what shines lit
  L.THEMES = {
    day: { sky: ['#a9dcf4', '#fff4e2'], table: '#94cf72', tableSide: '#c58b5a', soil: '#8d5f3f', path: '#f2dcac', grass: '#8bd06a',
      sun: 2.5, hemi: 1.35, ambient: 0.3, fog: '#eaf6f4', fill: 0.55,
      colors: { wood: '#dca46b', woodLight: '#f2d19f', woodDark: '#a8714a', plaster: '#fff4e3', plasterDark: '#f3e2c9', boards: '#e7b98a', tiles: '#e6f4ee',
        carpet: '#ee9f8c', rug: '#8cc7ea', paper: '#fffaf0', ink: '#2d2a26', metal: '#bcc9d0', steel: '#90a4ae', glass: '#bfe9f2', screen: '#355f6c',
        plant: '#79cc5f', leaf: '#4fb04f', soil: '#8d5f3f', pot: '#ee8a5f', teal: '#38b9a6', rose: '#f28aa9', ochre: '#f4b740', blue: '#6aa9ea', violet: '#ac8ce8',
        lamp: '#ffe08a', liquid: '#4fe3cf', cream: '#fbeee0', amber: '#f6b640', red: '#ef6a5a', green: '#5fc46e', white: '#ffffff', black: '#2a2b30',
        fruit: '#ff7b6b', flower: '#ffd84f', flower2: '#ff9ccf', flower3: '#ffffff', stone: '#c9c2b6' } },
    night: { sky: ['#0d1a2e', '#14213a'], table: '#2f5a4a', tableSide: '#3c2a22', soil: '#22160f', path: '#5b6b70', grass: '#336b52',
      sun: 1.05, hemi: 0.95, ambient: 0.18, fog: '#0f1a26', neon: '#3fbfae', fill: 0.35,
      colors: { wood: '#8a6446', woodLight: '#a8835e', woodDark: '#5a3d2a', plaster: '#4a4f5c', plasterDark: '#3b404c', boards: '#6e5039', tiles: '#3d5156',
        carpet: '#7e4f52', rug: '#3d5e7a', paper: '#d8dbd6', ink: '#1a1d1f', metal: '#6b7880', steel: '#4f5f66', glass: '#5aa0aa', screen: '#2f7f8a',
        plant: '#4f9a66', leaf: '#3f8a5a', soil: '#2a1f18', pot: '#8f5640', teal: '#5ccfbc', rose: '#e381a3', ochre: '#d8a64b', blue: '#77a0dc', violet: '#a48ee0',
        lamp: '#ffd27a', liquid: '#5ff0d8', cream: '#eadfd3', amber: '#f4c56c', red: '#e8705f', green: '#71d79d', white: '#e9efed', black: '#101216',
        fruit: '#e8705f', flower: '#e8c75a', flower2: '#d987b4', flower3: '#cfd8d4', stone: '#6b6f73' } },
  };

  // Validate the fixed furniture’s parameters.
  const numeric = (v, lo, hi) => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi;
  const validColor = c => typeof c === 'string' && (/^#[0-9a-f]{6}$/i.test(c) || Object.hasOwn(L.THEMES.day.colors, c));
  L.checkProps = (definition, values) => {
    if (!values || typeof values !== 'object' || Array.isArray(values)) throw new Error('Object parameters must be an object');
    for (const [name, v] of Object.entries(values)) {
      if (v == null) continue;
      const s = definition.params && definition.params[name];
      if (definition.params && !s) throw new Error('Unknown object parameter: ' + name);
      if (!s) { if (typeof v === 'number' && !Number.isFinite(v)) throw new Error('Invalid number: ' + name); continue; }
      const ok = s.type === 'boolean' ? typeof v === 'boolean' : s.type === 'color' ? validColor(v)
        : s.type === 'choice' ? s.values.includes(v) : numeric(v, s.min, s.max) && (s.type !== 'integer' || Number.isInteger(v));
      if (!ok) throw new Error('Object parameter outside its catalog: ' + name);
    }
  };
  // ── shared geometry: one of each shape and size, built once ───────────────────────────────────────────
  const GEOS = new Map();
  L.geo = (THREE, kind, a, b, c, d) => {
    const key = [kind, a, b, c, d].map(v => (typeof v === 'number' ? +v.toFixed(3) : v)).join('|');
    return L.resources.cached(GEOS, key, () => {
      const g = kind === 'box' ? new THREE.BoxGeometry(a, b, c) : kind === 'cyl' ? new THREE.CylinderGeometry(a, b, c, d) : kind === 'cone' ? new THREE.ConeGeometry(a, b, c)
        : new THREE.SphereGeometry(a, b, Math.max(12, Math.round(b * 0.7)));
      return g;
    });
  };
  /** a box with soft, rounded edges (three's RoundedBoxGeometry, with smooth normals): the toy look. r: corner
   *  radius (default: a little, scaled to the box); a box too thin to round stays a plain box */
  L.roundBox = (THREE, w, h, d, r) => {
    const m = Math.min(w, h, d);
    r = Math.min(r ?? Math.min(0.07, m * 0.28), m / 2 - 1e-4);
    if (!(r > 0.006)) return L.geo(THREE, 'box', w, h, d);
    const key = ['rbox', w, h, d, r].map(v => (typeof v === 'number' ? +v.toFixed(3) : v)).join('|');
    return L.resources.cached(GEOS, key, () => {
    const segs = (m < 0.12 ? 1 : 3) * 2 + 1, half = 0.5 / segs;
    const g = new THREE.BoxGeometry(1, 1, 1, segs, segs, segs).toNonIndexed();
    const pos = g.attributes.position.array, nor = g.attributes.normal.array, box = new THREE.Vector3(w / 2 - r, h / 2 - r, d / 2 - r);
    const p = new THREE.Vector3(), n = new THREE.Vector3();
    for (let i = 0; i < pos.length; i += 3) {
      p.fromArray(pos, i); n.copy(p);
      n.x -= Math.sign(n.x) * half; n.y -= Math.sign(n.y) * half; n.z -= Math.sign(n.z) * half; n.normalize();
      pos[i] = box.x * Math.sign(p.x) + n.x * r; pos[i + 1] = box.y * Math.sign(p.y) + n.y * r; pos[i + 2] = box.z * Math.sign(p.z) + n.z * r;
      nor[i] = n.x; nor[i + 1] = n.y; nor[i + 2] = n.z;
    }
    g.attributes.position.needsUpdate = g.attributes.normal.needsUpdate = true; g.computeBoundingSphere();
    return g;
    });
  };
  /** floor textures, drawn once per kind and colour: planks, tiles, grass — soft, a little uneven, like a picture book */
  const MAPS = new Map();
  L.floorMap = (THREE, kind, base, w, d) => {
    const key = kind + '|' + base;
    let canvas = MAPS.get(key);
    if (!canvas) {
      const S = 256, c = document.createElement('canvas'); c.width = c.height = S; const x = c.getContext('2d');
      const tone = (hex, k) => { const col = new THREE.Color(hex); col.offsetHSL(0, 0, k); return '#' + col.getHexString(); };
      let seed = 11; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
      x.fillStyle = base; x.fillRect(0, 0, S, S);
      if (kind === 'boards') {                         // planks: four to a tile, staggered, each its own shade
        for (let r = 0; r < 4; r++) { const y = r * S / 4, off = (r % 2) * S / 2;
          for (let k = -1; k < 2; k++) { x.fillStyle = tone(base, (rnd() - 0.5) * 0.06); x.fillRect(off + k * S, y + 2, S - 4, S / 4 - 4); }
          x.fillStyle = tone(base, -0.12); x.fillRect(0, y, S, 2); x.fillRect((off + S - 2) % S, y, 3, S / 4); }
      } else if (kind === 'tiles') {                   // soft square tiles with a darker grout
        for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) { x.fillStyle = tone(base, (i + j) % 2 ? -0.03 : 0.02); x.fillRect(i * S / 4 + 3, j * S / 4 + 3, S / 4 - 6, S / 4 - 6); }
      } else if (kind === 'grass' || kind === 'table') { // grass: little tufts of lighter and darker green
        for (let i = 0; i < 260; i++) { x.fillStyle = tone(base, (rnd() - 0.45) * 0.1); const px = rnd() * S, py = rnd() * S; x.beginPath(); x.ellipse(px, py, 2 + rnd() * 5, 1.5 + rnd() * 3, rnd() * 3, 0, Math.PI * 2); x.fill(); }
      } else if (kind === 'path') {                     // a sandy path: speckles
        for (let i = 0; i < 300; i++) { x.fillStyle = tone(base, (rnd() - 0.5) * 0.08); x.fillRect(rnd() * S, rnd() * S, 2 + rnd() * 3, 2 + rnd() * 3); }
      }
      canvas = c; MAPS.set(key, canvas);
      if (MAPS.size > 32) MAPS.delete(MAPS.keys().next().value);
    }
    // Cache immutable pixels, not Texture Sources: changing one floor must not recolour its siblings.
    const t = new THREE.CanvasTexture(canvas); t.colorSpace = THREE.SRGBColorSpace;
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4;
    t.userData.labFloor = { kind, w, d };
    const tile = kind === 'boards' ? 2.4 : kind === 'tiles' ? 2.0 : 4.0;
    t.repeat.set(Math.max(1, (w || tile) / tile), Math.max(1, (d || tile) / tile));
    return t;
  };

  L.FINISHES = { matte: { rough: 0.72, metal: 0 }, paper: { rough: 1, metal: 0 },
    ceramic: { rough: 0.3, metal: 0 }, glass: { rough: 0.2, metal: 0 }, metal: { rough: 0.4, metal: 0.65 } };
  L.appearance = (theme, look) => {
    const base = L.THEMES[theme], night = theme === 'night', colors = Object.assign({}, base.colors, look && look.colors);
    if (look) for (const [name, source] of Object.entries({ fruit: 'rose', flower: 'ochre', flower2: 'rose', flower3: 'paper', stone: 'steel' }))
      if (!Object.prototype.hasOwnProperty.call(look.colors || {}, name)) colors[name] = colors[source];
    return Object.assign({ finish: 'matte', sunColor: night ? '#a9c8ff' : '#ffeccc', fillColor: night ? '#7f8fd8' : '#ffe1ee',
      hemiColor: night ? '#8fb4dc' : '#d6efff', groundColor: night ? '#2a2a3a' : '#e9d9b8', exposure: night ? 1.3 : 1.05 }, base, look || {}, { colors });
  };

  /** The builder's toolbox for one theme, with optional material overrides. */
  L.kit = function kit(THREE, themeName, look) {
    const base = L.THEMES[themeName], night = themeName === 'night', cache = new Map();
    let th = L.appearance(themeName, look);
    const col = c => typeof c === 'string' && c.startsWith('@') ? th[c.slice(1)] : (typeof c === 'string' && th.colors[c]) || c;
    const glowIntensity = value => (value && typeof value === 'object' ? value[themeName] : value) ?? (night ? 1.3 : 0.25);
    const mat = (c, o) => {
      o = o || {};
      const key = c + '|' + JSON.stringify(o, (n, v) => (n === 'map' ? v && v.uuid : v));   // a texture by its id, not its pixels
      if (!cache.has(key)) L.resources.cached(cache, key, () => new THREE.MeshStandardMaterial({ color: col(c), roughness: o.rough ?? (L.FINISHES[th.finish] || L.FINISHES.matte).rough, metalness: o.metal ?? (L.FINISHES[th.finish] || L.FINISHES.matte).metal, flatShading: !!o.flat,
        map: o.map || null,
        emissive: o.glow ? col(o.glow === true ? c : o.glow) : 0x000000, emissiveIntensity: o.glow ? glowIntensity(o.gi) : 0,
        transparent: o.alpha != null, opacity: o.alpha ?? 1, vertexColors: !!o.vc }));
      const m = cache.get(key); m.userData.labColor = c; m.userData.labGlow = o.glow === true ? c : o.glow; m.userData.labRough = o.rough ?? null; m.userData.labMetal = o.metal ?? null;
      m.userData.labGlowIntensity = o.gi ?? null;
      return cache.get(key);
    };
    const asMat = (c, o) => (c && c.isMaterial ? c : mat(c, o));
    const mesh = (geo, m, x, y, z) => { const me = new THREE.Mesh(geo, m); me.position.set(x || 0, y || 0, z || 0); if (!geo.boundingSphere) geo.computeBoundingSphere(); me.castShadow = geo.boundingSphere.radius >= 0.12; me.receiveShadow = true; return L.resources.track(me); };
    const K = {
      THREE, th, themeName, look: look || null, night, col, mat, mesh, roundBox: L.roundBox, detail: 'medium',
      geometry: (kind, ...args) => L.shape(THREE, kind, args, K.detail),
      setLook(next, root) {
        th = L.appearance(themeName, next);
        K.th = th; K.look = next || null;
        const materials = new Set(cache.values()), textures = new Set();
        if (root) root.traverse(o => {
          if (o.isMesh) [].concat(o.material).forEach(m => materials.add(m));
          if (o.userData.labNightOnly) o.visible = night;
          if (o.isLight && o.userData.labNightIntensity != null) { o.visible = night; o.intensity = o.userData.labNightIntensity; }
        });
        materials.forEach(m => {
          if (m.userData.labColor != null && m.color) m.color.set(col(m.userData.labColor));
          if (m.userData.labGlow && m.emissive) { m.emissive.set(col(m.userData.labGlow)); m.emissiveIntensity = glowIntensity(m.userData.labGlowIntensity); }
          if (m.userData.labColor != null) { const finish = L.FINISHES[th.finish] || L.FINISHES.matte;
            m.roughness = m.userData.labRough ?? finish.rough; m.metalness = m.userData.labMetal ?? finish.metal; }
          if (m.map && m.map.userData.labFloor) textures.add(m.map);
          if (m.map && m.userData.labSign) { const sign = m.userData.labSign, canvas = m.map.image, ctx = canvas.getContext('2d');
            ctx.fillStyle = sign.bg || col('paper'); ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.fillStyle = sign.fg || col('ink');
            ctx.font = sign.font; ctx.textBaseline = 'middle'; ctx.textAlign = 'center'; ctx.fillText(sign.text, canvas.width / 2, canvas.height / 2 + 2); m.map.needsUpdate = true;
            m.emissiveIntensity = night ? 0.35 : 0; }
        });
        textures.forEach(t => { const f = t.userData.labFloor, fresh = K.floorMap(f.kind, f.w, f.d);
          t.image = fresh.image; t.needsUpdate = true; fresh.dispose(); });
      },
      /** a box standing on y (its base at y) — soft-cornered, like a toy, unless {sharp: true} */
      box: (w, h, d, c, x, y, z, o) => mesh(o && o.sharp ? L.geo(THREE, 'box', w, h, d) : L.roundBox(THREE, w, h, d, o && o.r), asMat(c, o), x, (y || 0) + h / 2, z),
      cyl: (rt, rb, h, c, x, y, z, o) => mesh(K.geometry('CylinderGeometry', rt, rb, h, Math.max(24, (o && o.seg) || 0)), asMat(c, o), x, (y || 0) + h / 2, z),
      sphere: (r, c, x, y, z, o) => mesh(K.geometry('SphereGeometry', r, Math.max(28, (o && o.seg) || 0), 20), asMat(c, o), x, y, z),
      cone: (r, h, c, x, y, z, o) => mesh(K.geometry('ConeGeometry', r, h, (o && o.seg) || 24), asMat(c, o), x, (y || 0) + h / 2, z),
      /** a floor's surface: planks, tiles, grass or a plain colour, as a texture tinted by the theme (size in metres) */
      floorMap: (kind, w, d) => L.floorMap(THREE, kind, typeof th[kind] === 'string' ? th[kind] : col(kind), w, d),
      group(...kids) { const g = new THREE.Group(); kids.flat().forEach(k => k && g.add(k)); return g; },
      at(obj, x, y, z, ry) { obj.position.set(x || 0, y || 0, z || 0); if (ry) obj.rotation.y = ry; return obj; },
      /** another component, by name */
      build(name, props) {
        props=Object.assign({},props||{},th.components?.[name]||{});
        const d = L.components[name];
        if (!d) { console.warn(`Lab3D: no component '${name}'`); return new THREE.Group(); }
        L.checkProps(d, props || {});
        const o = d.build(K, props || {}); o.userData.component = name; return L.resources.track(o);
      },
      /** a flat sign with text (a canvas texture), facing +z */
      sign(text, o) {
        o = o || {};
        const c = document.createElement('canvas'), px = 64, font = o.font || '600 40px Newsreader, Georgia, serif';
        const x = c.getContext('2d'); x.font = font; const tw = Math.ceil(x.measureText(text).width) + 40;
        c.width = tw; c.height = px; const y = c.getContext('2d');
        y.fillStyle = o.bg || col('paper'); y.fillRect(0, 0, tw, px); y.fillStyle = o.fg || col('ink'); y.font = font; y.textBaseline = 'middle'; y.textAlign = 'center'; y.fillText(text, tw / 2, px / 2 + 2);
        const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
        const h = o.h || 0.3, w = h * tw / px;
        const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.9, emissive: 0xffffff, emissiveMap: tex, emissiveIntensity: night ? 0.35 : 0 }));
        m.material.userData.labSign = { text, font, bg: o.bg, fg: o.fg };
        return L.resources.track(m);
      },
    };
    return K;
  };
})();
