/* Research instruments: isolated views, collector approval and the instrument library.
   tools/panels.py stores definitions; dashboard/panels_api.py serves views and data. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useRef, cls } = NL;

  NL.panelsOf = s => (((s && s.panels) || {}).panels) || (NL.DEMO && NL.demoPanels ? NL.demoPanels() : []);

  /* the theme a view gets: the dashboard's own colours, renamed for panelkit */
  const themeVars = () => {
    const cs = getComputedStyle(document.documentElement), v = n => cs.getPropertyValue(n).trim();
    const night = NL.themeNow() !== 'day';
    return { mode: night ? 'night' : 'day', vars: { '--ink': v('--ink'), '--soft': v('--ink-soft'), '--faint': v('--ink-faint'), '--edge': v('--edge'),
      '--edge-2': v('--edge-2'), '--well': night ? 'rgba(255,255,255,.035)' : 'rgba(30,26,20,.035)', '--accent': v('--accent'), '--accent-wash': v('--accent-wash'),
      '--warm': v('--warm'), '--warm-wash': v('--warm-wash'), '--bad': v('--bad'), '--bad-wash': v('--bad-wash'), '--ok': v('--ok'), '--glow': night ? '1' : '0' } };
  };

  /* the demo lab draws its panels from the shipped files directly (it never asks the server) */
  const kit = { css: null, js: null };
  const demoView = async id => {
    if (kit.css == null) { kit.css = await fetch('static/panels/panelkit.css').then(r => r.text()).catch(() => ''); kit.js = await fetch('static/panels/panelkit.js').then(r => r.text()).catch(() => ''); }
    const view = await fetch(`static/panels/shipped/${id}/view.html`).then(r => r.ok ? r.text() : '').catch(() => '');
    return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'">`
      + `<style>${kit.css}</style><script>${kit.js}</script></head><body>${view}</body></html>`;
  };

  /* ── the frame: one sandboxed iframe, fed by postMessage ───────────────────────────────────────── */
  NL.PanelFrame = ({ id, study, design, onSummary, minHeight }) => {
    const ref = useRef();
    const [doc, setDoc] = useState(null);
    const [data, setData] = useState(null);
    const [h, setH] = useState(minHeight || 220);
    const lamp = NL.usePrefs().theme;
    useEffect(() => {
      let off = false;
      (NL.DEMO ? demoView(id).then(html => ({ ok: true, html })) : NL.get(`/api/panel/view?${NL.qs({ id, design: design ? 1 : '' })}`))
        .then(x => { if (!off) setDoc(x && x.ok ? x.html : `<p style="font:13px sans-serif;color:#999">${(x && x.error) || 'no view to show'}</p>`); });
      return () => { off = true; };
    }, [id, design]);
    const pull = () => NL.get(`/api/panel/data?${NL.qs({ id, study })}`).then(setData);
    useEffect(() => { if (design) return undefined; pull(); const t = setInterval(pull, 30000); return () => clearInterval(t); }, [id, study, design]);
    const post = () => { const w = ref.current && ref.current.contentWindow; if (w && data) w.postMessage({ pk: 1, type: 'data', data: data.data || {}, theme: themeVars(), context: { study: study || null } }, '*'); };
    useEffect(post, [data, lamp, doc]);
    useEffect(() => {
      const f = e => {
        if (!ref.current || e.source !== ref.current.contentWindow) return;
        const m = e.data || {};
        if (m.pk !== 1) return;
        if (m.type === 'ready') post();
        else if (m.type === 'height') setH(Math.max(minHeight || 120, Math.min(4000, +m.h || 0)));
        else if (m.type === 'summary' && onSummary) onSummary(String(m.text || '').slice(0, 200));
        else if (m.type === 'open') {   // a view may ask to open a lab object — checked here, never trusted
          const sid = String(m.id || '');
          if (m.kind === 'study' && NL.item(NL.getState(), sid)) NL.go('study/' + sid);
          else if (m.kind === 'run' && NL.run(NL.getState(), sid)) NL.openRun(sid);
        }
      };
      window.addEventListener('message', f);
      return () => window.removeEventListener('message', f);
    }, [data, doc]);
    return html`<div class="pframe-body">${doc == null ? html`<div class="pad"><${NL.Spinner} /></div>`
      : html`<iframe ref=${ref} class="pframe-ifr" sandbox="allow-scripts" srcdoc=${doc} style=${{ height: h + 'px' }} title="panel" onLoad=${post}></iframe>`}
      ${data && data.error ? html`<div class=${cls('pframe-problem', data.stale && 'stale')}>${data.stale ? 'showing the last good data: ' : ''}${data.error}</div>` : null}</div>`;
  };

  const led = p => p.problem ? 'bad' : p.alerts ? 'warm' : p.stale ? 'off' : 'live';
  const PLACES = [{ value: 'home', label: 'Overview', hint: 'a reading in your overview' },
    { value: 'studies', label: 'On every study', hint: 'in each study’s dossier, for that study' }];

  /* ── the panel sheet: an instrument, full size ─────────────────────────────────────────────────── */
  NL.PanelSheet = ({ id, study, onClose }) => {
    const s = NL.useLab();
    const p = NL.panelsOf(s).find(x => x.id === id) || { id, title: id };
    const [sum, setSum] = useState(null);
    const [menu, setMenu] = useState(false);
    const [detail, setDetail] = useState(null);
    useEffect(() => { if (!NL.DEMO) NL.get(`/api/panel?${NL.qs({ id })}`).then(setDetail); }, [id, p.needs_approval]);
    const pin = async places => NL.act('/api/panel/pin', { id, pinned: places }, 'Pinned');
    const pinned = [...new Set((p.pinned || []).map(place => place === 'dock' ? 'home' : place))];
    const it = study && NL.item(s, study);
    return html`<aside class="sheet sheet-instrument" role="dialog" aria-modal="true" aria-label=${p.title}>
      <header class="inst-head"><i class=${cls('led', 'led-' + led(p))}></i>
        <div class="grow"><div class="inst-title">${p.title}${it ? html` · <span class="muted">${it.title || it.id}</span>` : null}</div>
          <div class="inst-sub">${sum || p.summary || p.description || ''}</div></div>
        <span class="inst-live mono">${p.ts ? 'live · ' + NL.ago(p.ts) : p.needs_approval ? 'waiting for you' : ''}</span>
        <button class="x" title="More" aria-label="more" onClick=${() => setMenu(!menu)}>⋯</button>
        <button class="x" aria-label="close" onClick=${onClose}><${NL.Icon} name="x" /></button></header>
      ${menu ? html`<div class="inst-menu">
        <div class="inst-menu-h">Show it</div>
        ${PLACES.map(pl => html`<label class="check"><input type="checkbox" checked=${pinned.includes(pl.value)} onChange=${e => pin(e.target.checked ? [...pinned, pl.value] : pinned.filter(x => x !== pl.value))} /><span><b>${pl.label}</b> <small class="muted">${pl.hint}</small></span></label>`)}
        <label class="check"><input type="checkbox" checked=${!!p.may_hold} onChange=${e => NL.act('/api/panel/pin', { id, may_hold: e.target.checked }, e.target.checked ? 'Its alerts may hold a study' : 'Its alerts only tell you')} /><span><b>Its alerts may hold a study</b> <small class="muted">nothing new starts for that study until you release it</small></span></label>
          <${NL.Btn} small onClick=${() => NL.act('/api/panel/collect', { id, study }, 'Gathered')}>Gather now</${NL.Btn}>
          <${NL.Btn} small kind="ghost" onClick=${async () => { await NL.act('/api/panel/archive', { id, archived: !p.archived }); onClose(); }}>${p.archived ? 'Back to the cabinet' : 'Archive'}</${NL.Btn}></div>
        <div class="muted small mono">newts panel ${id}${study ? ' --study ' + study : ''}</div></div>` : null}
      <div class="sheet-body inst-body">
        ${p.needs_approval ? html`<${CollectorApproval} p=${p} detail=${detail} />` : html`<${NL.PanelFrame} id=${id} study=${study} onSummary=${setSum} />`}
        ${detail && detail.collector && !p.needs_approval ? html`<details class="inst-code"><summary>Its collector · ${detail.collector.name}${detail.panel && detail.panel.origin === 'shipped' ? ' (shipped with the lab)' : ' (approved)'}</summary><pre class="plain">${detail.collector.code}</pre></details>` : null}
      </div></aside>`;
  };
  NL.openPanel = (id, study) => NL.open(NL.PanelSheet, { id, study }, { key: 'panel:' + id + ':' + (study || '') });

  const CollectorApproval = ({ p, detail }) => html`<div class="workbench-approve">
    <p><b>Its collector is code.</b> It runs on this machine, as you, every ${p.every || '5m'}, so it runs only once you approve this version of it.</p>
    ${detail && detail.collector ? html`<pre class="plain codewell">${detail.collector.code}</pre>` : html`<${NL.Spinner} />`}
    <div class="row end"><${NL.HoldButton} onHold=${() => NL.act('/api/panel/approve', { id: p.id, confirm: true }, 'Approved. Gathering now.')} sub="hold to approve the code">Let it run</${NL.HoldButton}></div></div>`;

  /* ── the Cabinet: every panel ever made ─────────────────────────────────────────────────────────── */
  const SRC = { collector: 'code', files: 'files', events: 'events', runs: 'runs', registry: 'studies' };
  NL.Cabinet = () => {
    const s = NL.useLab();
    const [f, setF] = useState('all');
    const all = NL.panelsOf(s);
    const FILTERS = [['all', 'All'], ['pinned', 'Pinned'], ['cabinet', 'In the cabinet'], ['archived', 'Archived'], ['shipped', 'Shipped'], ['lab', 'Made for this lab'], ['yours', 'From your other labs']];
    const pred = v => p => v === 'all' ? !p.archived : v === 'pinned' ? !!(p.pinned || []).length && !p.archived
      : v === 'cabinet' ? !(p.pinned || []).length && !p.archived : v === 'archived' ? !!p.archived : p.origin === v && !p.archived;
    const keep = pred(f);
    const list = all.filter(keep);
    return html`<div class="cabinet">
      <div class="chips">${FILTERS.map(([v, l]) => html`<button type="button" class=${cls('chip-btn', f === v && 'on')} onClick=${() => setF(v)}>${l} <span class="count">${all.filter(pred(v)).length}</span></button>`)}</div>
      <div class="cabinet-grid">${list.map(p => html`<article class="cab-card" key=${p.id}>
          <button type="button" class="cab-face" onClick=${() => NL.openPanel(p.id)}>
            <${NL.Dial} value=${p.gauge ? p.gauge.value : null} max=${p.gauge ? p.gauge.max : null} glyph=${p.icon} size=${58} alert=${!!p.alerts} title=${p.title} />
            <span class="cab-t"><b>${p.title}</b><small>${p.summary || p.description || ''}</small></span></button>
          <div class="cab-meta"><i class=${cls('led', 'led-' + led(p))}></i>${(p.sources || []).map(x => html`<span class="tag">${SRC[x] || x}</span>`)}
            <span class="tag tag-o">${{ shipped: 'shipped', lab: 'this lab', yours: 'yours' }[p.origin] || p.origin}</span>
            ${p.needs_approval ? html`<span class="tag tag-warm">code to approve</span>` : null}<span class="grow"></span>
            ${(p.pinned || []).map(x => html`<span class="pin" title=${'pinned ' + x}>${{ home: '◎', dock: '◔', studies: '▤' }[x]}</span>`)}</div></article>`)}
        ${!list.length ? html`<div class="muted pad">Nothing here.</div>` : null}</div></div>`;
  };

  NL.DescribeBar = ({ what, placeholder, onSend }) => {
    const [text,setText]=useState('');
    const send=async()=>{ if(!text.trim()||!onSend)return; const result=await onSend(text.trim()); if(result&&result.ok!==false)setText(''); };
    return html`<div class="form"><${NL.Field} label="What would you like to change?"><${NL.Textarea} rows=${3} value=${text} onInput=${setText} onSubmit=${send} placeholder=${placeholder} /></${NL.Field}>
      <div class="row end"><${NL.Btn} disabled=${!text.trim()} onClick=${send}>Draft with an agent</${NL.Btn}></div></div>`;
  };
})();
