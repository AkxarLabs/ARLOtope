/* panelkit — a small kit every panel view may use (inlined into its sandboxed iframe: no network, no access to
   the dashboard). The dashboard posts {type:'data', data, theme, context}; a view registers PK.on(render) and
   draws with plain DOM, SVG, canvas — or these helpers, which give the lab's look for free:

     PK.on(fn(data, context))        render (called on every update)
     PK.h(tag, attrs, ...children)   make an element (attrs: class, style, onclick, any attribute)
     PK.mount(...nodes)              replace the body and report the height
     PK.hero({value, unit, label, delta, tone})   PK.stat({k, n, s, tone})   PK.bar(value, max, {mark, tone})
     PK.ring(value, max, {label, tone, size})     PK.trace(series, {key, x, budget, height, tone, area})
     PK.ledger(rows, [{key, label, num, bar, max, fmt}], {onclick})          PK.pill(text, tone)
     PK.alerts(list)   PK.section(text)   PK.empty(title, line)   PK.fmt(n, d)   PK.ago(iso)
     PK.open(kind, id)               ask the dashboard to open a study / run / doc (it checks)
     PK.summary(text)                the one line the dashboard shows for this panel
*/
(function () {
  const listeners = [];
  let last = null;
  const PK = window.PK = {};
  PK.context = {};
  PK.on = fn => { listeners.push(fn); if (last) fn(last.data, last.context || {}); };
  const post = msg => { try { parent.postMessage(Object.assign({ pk: 1 }, msg), '*'); } catch (_) { /* sandbox */ } };
  PK.open = (kind, id) => post({ type: 'open', kind: String(kind), id: String(id) });
  PK.summary = text => post({ type: 'summary', text: String(text || '').slice(0, 200) });
  let lastH = 0;
  const report = () => { const h = Math.ceil(document.documentElement.scrollHeight); if (Math.abs(h - lastH) > 1) { lastH = h; post({ type: 'height', h }); } };
  try { new ResizeObserver(report).observe(document.documentElement); } catch (_) { setInterval(report, 500); }
  window.addEventListener('message', e => {
    const m = e.data;
    if (!m || m.pk !== 1) return;
    if (m.type === 'data') {
      if (m.theme && m.theme.vars) for (const [k, v] of Object.entries(m.theme.vars)) document.documentElement.style.setProperty(k, v);
      if (m.theme) document.documentElement.dataset.mode = m.theme.mode || 'night';
      last = m; PK.context = m.context || {};
      for (const fn of listeners) { try { fn(m.data || {}, PK.context); } catch (err) { PK.mount(PK.empty('This panel could not draw', String(err && err.message || err))); } }
      report();
    }
  });
  post({ type: 'ready' });

  const NS = 'http://www.w3.org/2000/svg';
  const SVG_TAGS = new Set(['svg', 'path', 'circle', 'line', 'rect', 'g', 'text', 'defs', 'linearGradient', 'stop', 'filter', 'feGaussianBlur', 'polyline', 'polygon', 'title']);
  PK.h = (tag, attrs, ...kids) => {
    const el = SVG_TAGS.has(tag) ? document.createElementNS(NS, tag) : document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else el.setAttribute(k === 'className' ? 'class' : k, v === true ? '' : v);
    }
    for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c)));
    return el;
  };
  const h = PK.h;
  PK.mount = (...nodes) => { document.body.replaceChildren(...nodes.flat().filter(Boolean)); report(); };
  PK.fmt = (n, d) => n == null || isNaN(n) ? '—' : Number(n).toLocaleString(undefined, { maximumFractionDigits: d == null ? (Math.abs(n) < 10 ? 1 : 0) : d });
  PK.ago = iso => { const t = Date.parse(iso); if (!t) return ''; const s = (Date.now() - t) / 1000;
    return s < 90 ? 'just now' : s < 5400 ? Math.round(s / 60) + ' min ago' : s < 129600 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' d ago'; };
  const tone = (v, max) => max && v > max ? 'bad' : max && v > 0.8 * max ? 'warm' : '';
  PK.section = t => h('div', { class: 'pk-sec' }, t);
  PK.pill = (t, tn) => h('span', { class: 'pk-pill ' + (tn || '') }, tn ? h('span', { class: 'pk-dot' }) : null, t);
  PK.empty = (t, l) => h('div', { class: 'pk-empty' }, h('b', {}, t), l || '');
  PK.hero = o => h('div', { class: 'pk-hero' },
    h('div', {}, h('div', {}, h('span', { class: 'v' }, typeof o.value === 'number' ? PK.fmt(o.value) : o.value), o.unit ? h('span', { class: 'u' }, o.unit) : null),
      o.label ? h('div', { class: 'l' }, o.label) : null),
    o.delta ? h('span', { class: 'pk-delta ' + (o.tone || '') }, o.delta) : null);
  PK.stat = o => h('div', { class: 'pk-stat ' + (o.tone || '') }, h('div', { class: 'k' }, o.k), h('div', { class: 'n' }, o.n), o.s ? h('div', { class: 's' }, o.s) : null);
  PK.bar = (v, max, o) => { o = o || {}; const m = max || Math.max(v, 1); const pct = Math.max(0, Math.min(100, (v / m) * 100));
    return h('div', { class: 'pk-bar ' + (o.tone != null ? o.tone : tone(v, max)) }, h('i', { style: { width: pct + '%' } }),
      o.mark != null ? h('b', { style: { left: Math.min(100, (o.mark / m) * 100) + '%' } }) : null); };
  PK.ring = (v, max, o) => { o = o || {}; const size = o.size || 92, r = size / 2 - 7, C = 2 * Math.PI * r;
    const frac = max ? Math.max(0, Math.min(1, v / max)) : 0.66, tn = o.tone != null ? o.tone : tone(v, max);
    const col = tn === 'bad' ? 'var(--bad)' : tn === 'warm' ? 'var(--warm)' : 'var(--accent)';
    return h('div', { class: 'pk-ring', style: { width: size + 'px', height: size + 'px' } },
      h('svg', { width: size, height: size, viewBox: `0 0 ${size} ${size}` },
        h('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', stroke: 'var(--edge-2)', 'stroke-width': 5 }),
        h('circle', { class: 'v', cx: size / 2, cy: size / 2, r, fill: 'none', stroke: col, 'stroke-width': 5, 'stroke-linecap': 'round',
          'stroke-dasharray': `${C * frac} ${C}`, transform: `rotate(-90 ${size / 2} ${size / 2})`,
          style: { filter: `drop-shadow(0 0 calc(5px * var(--glow)) ${col})` } })),
      h('div', { class: 'c' }, h('div', {}, h('b', {}, o.center != null ? o.center : PK.fmt(v)), h('span', {}, o.label || ''))));
  };
  let gid = 0;
  PK.trace = (series, o) => {
    o = o || {}; const key = o.key || 'value', H = o.height || 96, W = 320, pad = 4;
    const pts = (series || []).map((p, i) => ({ x: i, y: Number(typeof p === 'number' ? p : p[key]) || 0, lab: p && p[o.x || 'day'] }));
    if (!pts.length) return PK.empty('No data yet', '');
    const ymax = Math.max(...pts.map(p => p.y), o.budget || 0, 1e-9) * 1.08, n = Math.max(pts.length - 1, 1);
    const X = i => pad + (i / n) * (W - 2 * pad), Y = y => H - pad - (y / ymax) * (H - 2 * pad - 10);
    const d = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' ');
    const col = o.tone === 'warm' ? 'var(--warm)' : o.tone === 'bad' ? 'var(--bad)' : 'var(--accent)', id = 'pkg' + (++gid);
    return h('svg', { class: 'pk-trace', viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none', style: { height: H + 'px' } },
      h('defs', {}, h('linearGradient', { id, x1: 0, x2: 0, y1: 0, y2: 1 }, h('stop', { offset: '0%', 'stop-color': col, 'stop-opacity': .32 }), h('stop', { offset: '100%', 'stop-color': col, 'stop-opacity': 0 }))),
      o.area !== false ? h('path', { d: `${d} L${X(pts[pts.length - 1].x)},${H} L${X(0)},${H} Z`, fill: `url(#${id})` }) : null,
      o.budget ? h('line', { x1: 0, x2: W, y1: Y(o.budget), y2: Y(o.budget), stroke: 'var(--bad)', 'stroke-dasharray': '4 4', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke' }) : null,
      h('path', { d, fill: 'none', stroke: col, 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke', 'stroke-linejoin': 'round',
        style: { filter: `drop-shadow(0 0 calc(4px * var(--glow)) ${col})` } }),
      h('circle', { cx: X(pts[pts.length - 1].x), cy: Y(pts[pts.length - 1].y), r: 3, fill: col }));
  };
  PK.ledger = (rows, cols, o) => { o = o || {};
    return h('table', { class: 'pk-ledger' },
      h('tr', {}, cols.map(c => h('th', { style: c.num || c.bar ? { textAlign: 'right' } : null }, c.label || ''))),
      (rows || []).map(r => h('tr', { class: o.onclick ? 'click' : '', onclick: o.onclick ? () => o.onclick(r) : null },
        cols.map(c => c.bar ? h('td', { style: { width: '34%' } }, PK.bar(Number(r[c.key]) || 0, c.max ? (typeof c.max === 'function' ? c.max(r) : c.max) : null))
          : h('td', { class: c.num ? 'num' : '' }, c.fmt ? c.fmt(r[c.key], r) : (c.num ? PK.fmt(r[c.key]) : (r[c.key] ?? '—')))))));
  };
  PK.alerts = list => (list || []).map(a => h('div', { class: 'pk-alert ' + (a.level === 'block' ? 'block' : '') }, h('span', { class: 'g' }, '▲'),
    h('div', {}, a.say, a.study ? h('div', { class: 'pk-muted' }, a.study + (a.hold ? ' · launches on hold' : '')) : null)));
})();
