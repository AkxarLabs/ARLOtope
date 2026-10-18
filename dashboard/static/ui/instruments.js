/* Newts' Lab — shared research controls: line-art glyphs, choice tiles, pickers, the hold-to-approve
   button and its seal, dials, and the metro strip a study's path is drawn as. Shared by every lens. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useRef, cls } = NL;

  /* ── glyphs: one stroke weight, drawn on a 24-grid ─────────────────────────────────────────────── */
  const G = {
    me: 'M12 11.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM5.5 20c.8-3.6 3.4-5.6 6.5-5.6s5.7 2 6.5 5.6',
    campaign: 'M9.5 11.6a2.9 2.9 0 1 0 0-5.8 2.9 2.9 0 0 0 0 5.8zM3.5 20c.7-3.2 3-5 6-5 2.3 0 4.1 1 5.1 2.7M18.2 4.2a3.8 3.8 0 1 0 2.6 6.6 4.3 4.3 0 0 1-2.6-6.6z',
    auto: 'M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6zM12 3.5v2.2M12 18.3v2.2M3.5 12h2.2M18.3 12h2.2M6 6l1.6 1.6M16.4 16.4 18 18M6 18l1.6-1.6M16.4 7.6 18 6M10.4 12.1l1.2 1.2 2.1-2.3',
    diamond: 'M12 3.2 20.3 12 12 20.8 3.7 12z',
    seed: 'M12 20v-7M12 13c0-4 2.7-6.5 7-6.5 0 4-2.8 6.5-7 6.5zM12 15.5c0-3.2-2.2-5.2-5.5-5.2 0 3.2 2.2 5.2 5.5 5.2z',
    book: 'M4.5 5.5c2.6-1.2 5.1-1 7.5.7 2.4-1.7 4.9-1.9 7.5-.7v13c-2.6-1.2-5.1-1-7.5.7-2.4-1.7-4.9-1.9-7.5-.7zM12 6.2v13',
    compass: 'M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM15.5 8.5l-2 5-5 2 2-5z',
    flask: 'M9.5 3.5h5M10.5 3.5v5.5L5 18.4A1.4 1.4 0 0 0 6.2 20.5h11.6a1.4 1.4 0 0 0 1.2-2.1L13.5 9V3.5M7.6 14.5h8.8',
    lens: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM15.3 15.3 20 20',
    pen: 'M15.5 4.5l4 4L9 19H5v-4zM13 7l4 4',
    review: 'M4 5.5h16v10H9l-5 4zM8.5 10.5h7',
    archive: 'M4 6.5h16v3.5H4zM5.5 10v9h13v-9M10 13.5h4',
    margin: 'M5 5h14v14H5zM9 9l6 6M15 9l-6 6',
    target: 'M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12.6a.6.6 0 1 0 0-1.2.6.6 0 0 0 0 1.2z',
    loop: 'M17.5 8.5A6.5 6.5 0 0 0 5.6 10M6.5 15.5A6.5 6.5 0 0 0 18.4 14M18 4.5v4h-4M6 19.5v-4h4',
    moon: 'M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10z',
    spark: 'M12 3.5l1.8 5.2 5.2 1.8-5.2 1.8L12 17.5l-1.8-5.2L5 10.5l5.2-1.8z',
    chat: 'M5 6h14v9H10l-5 4z',
    plus: 'M12 5v14M5 12h14',
    gear: 'M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.8 1.8M16.7 16.7l1.8 1.8M5.5 18.5l1.8-1.8M16.7 7.3l1.8-1.8',
    world: 'M3.5 15.5 12 20l8.5-4.5L12 11zM3.5 11 12 6.5l8.5 4.5M12 2.5v4',
    studies: 'M4 5h4.5v14H4zM10 5h4.5v14H10zM16 5h4v14h-4',
    agents: 'M8 10.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM16.5 10.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM3.5 18.5c.6-2.8 2.3-4.3 4.5-4.3s3.9 1.5 4.5 4.3M12 18.5c.6-2.8 2.3-4.3 4.5-4.3s3.9 1.5 4.5 4.3',
    library: 'M5 4.5h4v15H5zM10.5 4.5h4v15h-4zM16 5.5l3.6.9-3 13.4-3.6-.9',
    metro: 'M3.5 12h17M6.5 12a2 2 0 1 0 0-.01M12 9.5l2.5 2.5-2.5 2.5-2.5-2.5zM17.5 12a2 2 0 1 0 0-.01',
    cabinet: 'M5 3.5h14v17H5zM5 9.5h14M5 15h14M10 6.5h4M10 12.2h4M10 17.8h4',
    hold: 'M12 3.5v4M12 16.5v4M3.5 12h4M16.5 12h4',
    bolt: 'M13 3.5 5.5 13.5H12l-1 7 7.5-10H12z',
    dollar: 'M12 3.5v17M16 7.5c-.8-1.3-2.2-2-4-2-2.3 0-4 1.2-4 3.1 0 4.4 8 2.6 8 6.8 0 1.9-1.7 3.1-4 3.1-1.9 0-3.4-.8-4.2-2.2',
    ring: 'M12 20.5a8.5 8.5 0 1 1 8.2-10.7',
    check: 'M5 12.5l4.5 4.5L19 7.5',
    x: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
    play: 'M8 5.5v13l10.5-6.5z',
    pause: 'M8 5.5v13M16 5.5v13',
  };
  NL.GLYPHS = G;
  NL.Glyph = ({ name, size, className, title }) => html`<svg class=${cls('glyph', className)} viewBox="0 0 24 24" width=${size || 20} height=${size || 20} fill="none" stroke="currentColor"
    stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden=${title ? null : 'true'} role=${title ? 'img' : null}>${title ? html`<title>${title}</title>` : null}<path d=${G[name] || G.spark} /></svg>`;
  // a step's glyph, from its room (rooms are the lab's own; a few have a known face)
  const ROOM_GLYPH = { incubator: 'seed', study: 'book', lab: 'flask', bench: 'lens', writing: 'pen', archive: 'archive', margins: 'margin' };
  NL.stepGlyph = st => { const x = NL.STEPS[st]; return ROOM_GLYPH[x && x.room] || 'spark'; };
  // a room's hue, so a study's path is coloured by where it goes
  const ROOM_HUE = { incubator: 145, study: 205, lab: 172, bench: 260, writing: 32, archive: 48, margins: 0 };
  NL.roomHue = room => ROOM_HUE[room] != null ? ROOM_HUE[room] : (String(room || '').split('').reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7));
  NL.stepHue = st => { const x = NL.STEPS[st]; return NL.roomHue(x && x.room); };

  /* ── choice tiles: the choices that matter, drawn ──────────────────────────────────────────────── */
  NL.ChoiceTiles = ({ value, onChange, options, multi, columns }) => {
    const on = v => multi ? (value || []).includes(v) : value === v;
    const pick = v => multi ? onChange(on(v) ? value.filter(x => x !== v) : [...(value || []), v]) : onChange(v);
    return html`<div class="tiles" role=${multi ? 'group' : 'radiogroup'} style=${columns ? { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` } : null}>
      ${options.map(o => html`<button type="button" role=${multi ? 'checkbox' : 'radio'} aria-checked=${on(o.value)} disabled=${o.disabled}
        class=${cls('tile', on(o.value) && 'on', o.disabled && 'off')} onClick=${() => !o.disabled && pick(o.value)} title=${o.disabled && o.why ? o.why : null}>
        ${o.glyph ? html`<span class="tile-glyph"><${NL.Glyph} name=${o.glyph} size=${26} /></span>` : null}
        <span class="tile-t">${o.title}</span>${o.desc ? html`<span class="tile-d">${o.desc}</span>` : null}
        ${o.badge ? html`<span class="tile-badge">${o.badge}</span>` : null}
        <span class="tile-check" aria-hidden="true"><${NL.Glyph} name="check" size=${12} /></span></button>`)}</div>`;
  };

  /* ── picker: a pill that opens a glass list (replaces a select where the options deserve words) ── */
  NL.Picker = ({ value, onChange, options, placeholder, label, small }) => {
    const [open, setOpen] = useState(false);
    const [q, setQ] = useState('');
    const ref = useRef();
    const cur = options.find(o => o.value === value);
    useEffect(() => { if (!open) return; const f = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
      setTimeout(() => document.addEventListener('mousedown', f), 0); return () => document.removeEventListener('mousedown', f); }, [open]);
    const list = options.filter(o => !q || (o.label + ' ' + (o.hint || '')).toLowerCase().includes(q.toLowerCase()));
    return html`<span class=${cls('picker', small && 'small', open && 'open')} ref=${ref}>
      <button type="button" class="picker-btn" aria-haspopup="listbox" aria-expanded=${open} aria-label=${label} onClick=${() => setOpen(!open)}>
        ${cur && cur.glyph ? html`<${NL.Glyph} name=${cur.glyph} size=${16} />` : null}<span class="clip">${cur ? cur.label : (placeholder || 'Choose…')}</span><${NL.Icon} name="caret" /></button>
      ${open ? html`<div class="picker-pop" role="listbox">${options.length > 7 ? html`<input class="picker-q" autofocus placeholder="Find…" value=${q} onInput=${e => setQ(e.target.value)} ref=${el => el && setTimeout(() => el.focus(), 0)} />` : null}
        ${list.map(o => html`<button type="button" role="option" aria-selected=${o.value === value} disabled=${o.disabled} class=${cls('picker-opt', o.value === value && 'on')}
          onClick=${() => { onChange(o.value); setOpen(false); setQ(''); }}>${o.glyph ? html`<${NL.Glyph} name=${o.glyph} size=${18} />` : html`<span class="picker-dot"></span>`}
          <span class="picker-ot"><b>${o.label}</b>${o.hint ? html`<small>${o.hint}</small>` : null}</span>${o.value === value ? html`<${NL.Glyph} name="check" size=${14} />` : null}</button>`)}
        ${!list.length ? html`<div class="muted small pad">Nothing matches.</div>` : null}</div>` : null}</span>`;
  };

  /* ── hold to approve: deliberate without being a chore (Space / Enter hold too) ─────────────────── */
  NL.HoldButton = ({ onHold, children, ms, kind, disabled, sub }) => {
    const dur = ms || 850;
    const [p, setP] = useState(0);
    const [done, setDone] = useState(false);
    const t = useRef(null);       // the ring's animation frame
    const timer = useRef(null);   // the hold itself: a timer, so it completes even when frames are throttled
    const finish = () => {
      timer.current = null; if (t.current) { cancelAnimationFrame(t.current); t.current = null; }
      setP(1); setDone(true); Promise.resolve(onHold()).finally(() => setTimeout(() => { setDone(false); setP(0); }, 900));
    };
    const start = () => {
      if (disabled || done || timer.current) return;
      const t0 = performance.now();
      const step = now => { setP(Math.min(1, (now - t0) / dur)); if (timer.current) t.current = requestAnimationFrame(step); };
      timer.current = setTimeout(finish, dur);
      t.current = requestAnimationFrame(step);
    };
    const stop = () => {
      if (t.current) { cancelAnimationFrame(t.current); t.current = null; }
      if (timer.current) { clearTimeout(timer.current); timer.current = null; setP(0); }
    };
    useEffect(() => () => { if (timer.current) clearTimeout(timer.current); if (t.current) cancelAnimationFrame(t.current); }, []);
    const key = e => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); start(); } };
    const C = 2 * Math.PI * 15;
    return html`<button type="button" class=${cls('hold', kind && 'hold-' + kind, done && 'done', p > 0 && 'holding')} disabled=${disabled}
      onPointerDown=${start} onPointerUp=${stop} onPointerLeave=${stop} onKeyDown=${key} onKeyUp=${e => (e.key === ' ' || e.key === 'Enter') && stop()}>
      <svg class="hold-ring" viewBox="0 0 36 36" aria-hidden="true"><circle cx="18" cy="18" r="15" class="hold-track" />
        <circle cx="18" cy="18" r="15" class="hold-fill" style=${{ strokeDasharray: `${C * p} ${C}` }} /></svg>
      <span class="hold-t"><b>${done ? '✓ ' : ''}${children}</b><small>${done ? 'recorded' : p > 0 ? 'keep holding…' : (sub || 'press and hold')}</small></span></button>`;
  };

  /* ── the seal: a checkpoint's state, stamped ─────────────────────────────────────────────────────── */
  NL.Seal = ({ state, size }) => {
    const z = size || 64;
    return html`<span class=${cls('seal', 'seal-' + (state || 'waiting'))} style=${{ width: z + 'px', height: z + 'px' }} aria-hidden="true">
      <svg viewBox="0 0 64 64"><path class="seal-o" d="M32 3 61 32 32 61 3 32z" /><path class="seal-i" d="M32 12 52 32 32 52 12 32z" />
        ${state === 'approved' ? html`<path class="seal-k" d="M24 32.5l5.5 5.5L41 26.5" />` : state === 'revoked' ? html`<path class="seal-k" d="M25 25l14 14M39 25 25 39" />` : html`<circle class="seal-k" cx="32" cy="32" r="3.2" />`}</svg></span>`;
  };

  /* ── a dial: a panel's main value as a ring (the instrument rail) ────────────────────────────────── */
  NL.Dial = ({ value, max, glyph, tone, label, title, alert, onClick, size }) => {
    const z = size || 46, r = z / 2 - 4, C = 2 * Math.PI * r;
    const frac = max ? Math.max(0.02, Math.min(1, (value || 0) / max)) : value ? 0.72 : 0.06;
    const tn = tone || (max && value > max ? 'bad' : max && value > 0.85 * max ? 'warm' : '');
    return html`<button type="button" class=${cls('dial', tn && 'dial-' + tn, alert && 'alert')} onClick=${onClick} title=${title} aria-label=${title}>
      <svg viewBox=${`0 0 ${z} ${z}`} width=${z} height=${z} aria-hidden="true"><circle cx=${z / 2} cy=${z / 2} r=${r} class="dial-track" />
        <circle cx=${z / 2} cy=${z / 2} r=${r} class="dial-fill" style=${{ strokeDasharray: `${C * frac} ${C}` }} transform=${`rotate(-90 ${z / 2} ${z / 2})`} /></svg>
      <span class="dial-g">${glyph && glyph.length > 2 ? html`<${NL.Glyph} name=${glyph} size=${17} />` : glyph || '◔'}</span>
      ${label ? html`<span class="dial-l">${label}</span>` : null}</button>`;
  };

  /* ── the metro strip: a study's path through its workflow ────────────────────────────────────────
     stations = steps (filled = passed, pulsing ring = here, hollow = ahead), segments coloured by room,
     diamonds = checkpoints (amber = waiting for you, green = approved, red = went past without it) */
  NL.Metro = ({ it, compact, onStation, onGate }) => {
    const steps = NL.stepsOf(it);
    const idx = steps.indexOf(it.state);
    const off = NL.isShelved(it.state);
    const cps = NL.checkpointsOf(it);
    const slipped = new Set((it.slipped || []).map(x => x.id));
    const waiting = new Set(it.waiting || []);
    const gateState = c => NL.approvedCp(it, c.id) ? 'ok' : slipped.has(c.id) ? 'bad' : waiting.has(c.id) ? 'wait' : 'ahead';
    const Gate = c => html`<button type="button" class=${cls('m-gate', 'g-' + gateState(c))} title=${`${c.title}: ${{ ok: 'approved', bad: 'went past without your approval', wait: 'waiting for you', ahead: 'still ahead' }[gateState(c)]}`}
      onClick=${e => { e.stopPropagation(); onGate ? onGate(c) : NL.openCheckpoint(it.id, c.id); }}><i></i></button>`;
    return html`<ol class=${cls('metro', compact && 'compact', off && 'off')}>${steps.map((st, i) => {
      const done = !off && i < idx, cur = !off && i === idx;
      const before = cps.filter(c => c.before === st), during = cps.filter(c => c.during === st);
      return html`${i ? html`<li class=${cls('m-seg', done || cur ? 'lit' : '')} style=${{ '--h': NL.stepHue(st) }}>${before.map(Gate)}</li>` : null}
        <li class=${cls('m-st', done && 'done', cur && 'cur')} style=${{ '--h': NL.stepHue(st) }}>
          <button type="button" class="m-dot" title=${NL.STATE_LABEL[st]} onClick=${() => onStation && onStation(st)}><i></i></button>
          ${during.length ? html`<span class="m-during">${during.map(Gate)}</span>` : null}
          ${compact ? null : html`<span class="m-l">${NL.STATE_LABEL[st]}</span>`}</li>`;
    })}${off ? html`<li class="m-off">${NL.STATE_LABEL[it.state]}</li>` : null}</ol>`;
  };
})();
