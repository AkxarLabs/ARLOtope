/* Newts' Lab — shared UI pieces: buttons, pills, cards, sheets, dialogs, fields, tabs, markdown. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useLayoutEffect, useRef, useMemo, cls } = NL;

  NL.Btn = ({ children, onClick, kind, small, disabled, title, type, busy, icon }) => {
    const [working, setWorking] = useState(false);
    const click = async e => {
      if (!onClick || working) return;
      const r = onClick(e);
      if (r && typeof r.then === 'function') { setWorking(true); try { await r; } finally { setWorking(false); } }
    };
    return html`<button type=${type || 'button'} class=${cls('btn', kind && 'btn-' + kind, small && 'btn-sm', (busy || working) && 'is-busy')}
      disabled=${disabled || busy || working} title=${title} onClick=${click}>${icon ? html`<span class="btn-ico" aria-hidden="true">${icon}</span>` : null}${children}</button>`;
  };

  /* line icons (stroke = the text colour): NL.Icon name="search" */
  const ICONS = {
    search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM15.3 15.3 20 20',
    bell: 'M18 15.5V11a6 6 0 1 0-12 0v4.5L4.5 17h15zM10 20a2 2 0 0 0 4 0',
    sliders: 'M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1M15 5v4M9 10v4M17 15v4',
    plus: 'M12 5v14M5 12h14',
    x: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
    lock: 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
    copy: 'M9 9h10v11H9zM15 9V5H5v11h4',
    trash: 'M4.5 7h15M10 11v6M14 11v6M6.5 7l1 13h9l1-13M9.5 7V4.5h5V7',
    undo: 'M9 14 4.5 9.5 9 5M4.5 9.5H14a5.5 5.5 0 0 1 0 11h-3',
    check: 'M5 12.5l4.5 4.5L19 7.5',
    alert: 'M12 4 2.8 20h18.4zM12 10v4.5M12 17.2v.3',
    up: 'M12 19V5M6.5 10.5 12 5l5.5 5.5',
    down: 'M12 5v14M6.5 13.5 12 19l5.5-5.5',
    chevron: 'M9.5 6l6 6-6 6',
    caret: 'M7 10l5 5 5-5',
    file: 'M6 3.5h8l4 4V20.5H6zM14 3.5v4h4',
    layers: 'M12 4 3.5 8.5 12 13l8.5-4.5zM3.5 12.5 12 17l8.5-4.5M3.5 16.5 12 21l8.5-4.5',
    spark: 'M12 3.5l1.8 5.2 5.2 1.8-5.2 1.8L12 17.5l-1.8-5.2L5 10.5l5.2-1.8z',
    arrow: 'M5 12h14M13 6l6 6-6 6',
    sound: 'M4 9.5h3.5L12 6v12l-4.5-3.5H4zM15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11',
    mute: 'M4 9.5h3.5L12 6v12l-4.5-3.5H4zM16 9.5l5 5M21 9.5l-5 5',
    sun: 'M12 7.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9zM12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4',
    moon: 'M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10z',
    theme: 'M12 3.5a8.5 8.5 0 1 0 0 17zM12 3.5a8.5 8.5 0 0 1 0 17',
  };
  NL.Icon = ({ name, size, title }) => html`<svg class="ico" viewBox="0 0 24 24" width=${size || null} height=${size || null} fill="none" stroke="currentColor"
    stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden=${title ? null : 'true'} role=${title ? 'img' : null}>${title ? html`<title>${title}</title>` : null}<path d=${ICONS[name] || ''} /></svg>`;

  NL.Pill = ({ tone, children, title }) => html`<span class=${cls('pill', tone && 'pill-' + tone)} title=${title}>${children}</span>`;
  NL.runStateLabel = r => {
    if (r.needs_followup) return 'Task unfinished';
    if (NL.runWaiting(r)) return r.pending_permissions?.length ? 'Permission needed' : 'Waiting for you';
    if (r.status === 'completed' && r.kind === 'ask' && !r.workflow_node && !r.assigned_step) return 'Your turn';
    return NL.RUN_WORD[r.status] || r.status;
  };
  NL.RunPill = ({ r }) => r ? html`<${NL.Pill} tone=${r.needs_followup?'ask':NL.RUN_TONE[r.status] || 'muted'}>${NL.RUN_TONE[r.status] === 'live' ? html`<i class="dot-live"></i>` : null}${NL.runStateLabel(r)}</${NL.Pill}>` : null;
  NL.StatePill = ({ state }) => html`<${NL.Pill} tone=${NL.stateTone(state)}>${NL.STATE_LABEL[state] || state || '—'}</${NL.Pill}>`;
  NL.RoleDot = ({ role }) => html`<i class="role-dot" style=${{ background: NL.roleOf(role).color }} title=${NL.roleOf(role).label}></i>`;

  NL.Section = ({ title, children, action, count, className }) => html`<section class=${cls('section', className)}>
    ${title ? html`<header class="section-head"><h3>${title}${count != null ? html` <span class="count">${count}</span>` : null}</h3>${action || null}</header>` : null}
    ${children}</section>`;
  NL.Empty = ({ icon, title, children }) => html`<div class="empty">${icon ? html`<div class="empty-ico" aria-hidden="true">${icon}</div>` : null}
    ${title ? html`<div class="empty-title">${title}</div>` : null}<div class="empty-body">${children}</div></div>`;
  NL.Spinner = () => html`<span class="spinner" aria-label="loading"></span>`;
  NL.LoadState = ({ error, reload, stale }) => error ? html`<div role="alert"><${NL.Empty} title="Could not load">
    <p>${error}</p>${stale ? html`<p>Last loaded data is shown.</p>` : null}<${NL.Btn} onClick=${reload}>Retry</${NL.Btn}></${NL.Empty}></div>` : html`<${NL.Spinner} />`;
  /** Browsers hide iframe HTTP failures. Check headers first; keep original URLs and sandboxing. */
  const FilePreview = ({ url, kind, title, className, srcdoc }) => {
    const [attempt, retry] = NL.useReducer(n => n + 1, 0);
    const [checked, setChecked] = useState(kind === 'image' || srcdoc != null), [error, setError] = useState('');
    useEffect(() => {
      if (kind === 'image' || srcdoc != null) return;
      let active = true;
      const controller = new AbortController();
      setChecked(false);
      fetch(url, { method: 'HEAD', credentials: 'same-origin', signal: controller.signal }).then(r => {
        if (active) { setError(r.ok ? '' : `Could not open this file (${r.status}).`); setChecked(r.ok); }
      }).catch(() => { if (active) setError('Could not reach the lab server.'); });
      return () => { active = false; controller.abort(); };
    }, [attempt]);
    if (error) return html`<${NL.LoadState} error=${error} reload=${() => { setError(''); retry(); }} />`;
    if (!checked) return html`<${NL.Spinner} />`;
    const failed = () => setError('The preview could not load. Try again or open the original file.');
    return kind === 'image' ? html`<img key=${attempt} class=${className} src=${url} alt=${title} onError=${failed} />`
      : html`<iframe key=${attempt} class=${className} src=${srcdoc != null ? undefined : url} srcdoc=${srcdoc} sandbox=${kind === 'html' ? 'allow-scripts' : undefined} title=${title} onError=${failed}></iframe>`;
  };
  NL.FilePreview = props => html`<${FilePreview} key=${props.kind + ':' + props.url} ...${props} />`;
  /** The shared opaque renderer shell: loading and failure are distinct; retry replaces only this frame. */
  NL.LabFrame = ({ frameRef, src, title, onLoad, onRetry, fallback }) => {
    const [status, setStatus] = useState('loading'), [error, setError] = useState(''), [revision, setRevision] = useState(0);
    useLayoutEffect(() => {
      const receive = e => {
        if (e.source !== frameRef.current?.contentWindow || e.data?.labView !== 1) return;
        if (e.data.error) { setError(String(e.data.error)); setStatus('failed'); }
        else if (e.data.kind === 'ready') { setError(''); setStatus('ready'); }
        else if (e.data.kind === 'labels' && typeof e.data.value === 'boolean') NL.setPref('labels',e.data.value);
      };
      window.addEventListener('message', receive);
      return () => window.removeEventListener('message', receive);
    }, [frameRef]);
    const retry = () => { onRetry?.(); setError(''); setStatus('loading'); setRevision(n => n + 1); };
    return html`<div class=${cls('lab-frame', 'is-' + status)} aria-busy=${status === 'loading'}>
      <iframe ref=${frameRef} key=${revision} sandbox="allow-scripts" src=${src} title=${title} hidden=${status === 'failed'} onLoad=${onLoad}
        onError=${() => { setError('The renderer page could not load.'); setStatus('failed'); }} />
      ${status !== 'ready' ? html`<div class="lab-frame-status" role=${status === 'failed' ? 'alert' : 'status'}>
        ${status === 'loading' ? html`<p><${NL.Spinner}/> Loading 3D view…</p>` : html`<p><b>The 3D view is unavailable.</b></p>`}
        <div class="row"><${NL.Btn} small onClick=${retry}>Retry 3D view</${NL.Btn}>${fallback}</div>
        ${error ? html`<details><summary>Details</summary><p class="mono small">${error}</p></details>` : null}</div>` : null}
    </div>`;
  };
  NL.Bar = ({ value, max, tone }) => { const p = max ? Math.max(0, Math.min(1, value / max)) : 0; return html`<span class=${cls('bar', tone && 'bar-' + tone)}><i style=${{ width: (p * 100).toFixed(1) + '%' }}></i></span>`; };

  /* ── fields ─────────────────────────────────────────────────────────────── */
  NL.Field = ({ label, hint, children, error }) => {
    const name = child => child && [NL.Input, NL.Textarea, NL.Select, NL.Seg].includes(child.type) && typeof label === 'string'
      ? window.preact.cloneElement(child, { ariaLabel: label, ariaDescription: hint }) : child;
    const content = Array.isArray(children) ? children.map(name) : name(children);
    const Tag = [].concat(children || []).some(child => child?.type === NL.Seg) ? 'div' : 'label';
    return html`<${Tag} class=${cls('field', error && 'field-error')}><span class="field-label">${label}</span>${content}${hint ? html`<span class="field-hint">${hint}</span>` : null}${error ? html`<span class="field-err">${error}</span>` : null}</${Tag}>`;
  };
  NL.Input = ({ value, onInput, placeholder, type, autofocus, onEnter, mono, min, max, disabled, ariaLabel, ariaDescription }) => {
    const ref = useRef();
    useEffect(() => { if (autofocus && ref.current) ref.current.focus(); }, []);
    return html`<input ref=${ref} aria-label=${ariaLabel} aria-description=${ariaDescription} class=${cls('input', mono && 'mono')} type=${type || 'text'} value=${value ?? ''} placeholder=${placeholder} min=${min} max=${max} disabled=${disabled}
      onInput=${e => onInput && onInput(e.target.value)} onKeyDown=${e => { if (e.key === 'Enter' && onEnter) { e.preventDefault(); onEnter(); } }} />`;
  };
  NL.Textarea = ({ value, onInput, placeholder, rows, autofocus, onSubmit, mono, ariaLabel, ariaDescription }) => {
    const ref = useRef();
    useEffect(() => { if (autofocus && ref.current) ref.current.focus(); }, []);
    return html`<textarea ref=${ref} aria-label=${ariaLabel} aria-description=${ariaDescription} class=${cls('input', 'textarea', mono && 'mono')} rows=${rows || 4} value=${value ?? ''} placeholder=${placeholder}
      onInput=${e => onInput && onInput(e.target.value)} onKeyDown=${e => { if (onSubmit && e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); onSubmit(); } }}></textarea>`;
  };
  NL.Select = ({ value, onChange, options, disabled, ariaLabel, ariaDescription }) => html`<select aria-label=${ariaLabel} aria-description=${ariaDescription} class="input select" value=${value} disabled=${disabled} onChange=${e => onChange(e.target.value)}>
    ${options.map(o => typeof o === 'string' ? html`<option value=${o}>${o}</option>` : html`<option value=${o.value} disabled=${o.disabled}>${o.label}</option>`)}</select>`;
  NL.Seg = ({ value, onChange, options, ariaLabel }) => {
    const enabled = options.filter(o => !o.disabled), tab = enabled.find(o => o.value === value) || enabled[0];
    const key = (e, current) => {
      if (e.altKey || e.ctrlKey || e.metaKey || !enabled.length) return;
      const direction = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (!direction && e.key !== 'Home' && e.key !== 'End') return;
      e.preventDefault();
      const index = e.key === 'Home' ? 0 : e.key === 'End' ? enabled.length - 1 : (enabled.findIndex(o => o.value === current) + direction + enabled.length) % enabled.length;
      e.currentTarget.parentElement.querySelectorAll('button:not(:disabled)')[index]?.focus();
      onChange(enabled[index].value);
    };
    return html`<div class="seg" role="radiogroup" aria-label=${ariaLabel}>${options.map(o => html`<button type="button" role="radio" disabled=${o.disabled} aria-checked=${value === o.value} tabindex=${o === tab ? 0 : -1}
      class=${cls('seg-btn', value === o.value && 'on')} onKeyDown=${e => key(e,o.value)} onClick=${() => onChange(o.value)}>${o.label}</button>`)}</div>`;
  };
  NL.Toggle = ({ on, onChange, label, sub }) => html`<button type="button" class=${cls('toggle-row')} role="switch" aria-checked=${!!on} onClick=${() => onChange(!on)}>
    <span class="toggle-text"><b>${label}</b>${sub ? html`<small>${sub}</small>` : null}</span><span class=${cls('toggle', on && 'on')}><i></i></span></button>`;

  NL.Tabs = ({ tabs, value, onChange }) => {
    const ref=useRef();
    useEffect(()=>{const nav=ref.current,selected=nav?.querySelector('[aria-selected="true"]');if(!selected)return;
      const box=nav.getBoundingClientRect(),tab=selected.getBoundingClientRect();
      if(tab.right>box.right)nav.scrollLeft+=tab.right-box.right;else if(tab.left<box.left)nav.scrollLeft+=tab.left-box.left;
    },[value]);
    return html`<nav ref=${ref} class="tabs" role="tablist" onKeyDown=${e=>{
      if(!e.target.matches('[role="tab"]')||e.altKey||e.ctrlKey||e.metaKey)return;
      const direction={ArrowRight:1,ArrowLeft:-1}[e.key];if(!direction&&e.key!=='Home'&&e.key!=='End')return;
      e.preventDefault();const i=e.key==='Home'?0:e.key==='End'?tabs.length-1:(tabs.findIndex(t=>t.id===value)+direction+tabs.length)%tabs.length;
      ref.current.children[i]?.focus();onChange(tabs[i].id);
    }}>${tabs.map(t => html`<button type="button" role="tab" aria-selected=${value === t.id} tabindex=${value===t.id?0:-1}
    class=${cls('tab', value === t.id && 'on')} onClick=${() => onChange(t.id)}>${t.label}${t.count ? html` <span class="count">${t.count}</span>` : null}</button>`)}</nav>`;
  };

  /* ── layers ─────────────────────────────────────────────────────────────── */
  /** A side sheet (right) — or a centered dialog. Rendered by the OverlayHost from NL.open(). */
  // title null: the sheet draws its own head (the Permit, the checkpoint editor) and keeps only the close button
  NL.Sheet = ({ title, sub, onClose, children, wide, footer, kicker, className }) => html`<aside class=${cls('sheet', wide && 'sheet-wide', className)} role="dialog" aria-modal="true" aria-label=${typeof title === 'string' ? title : null}>
    ${title == null ? html`<button class="x sheet-x" aria-label="close" onClick=${onClose}><${NL.Icon} name="x" /></button>`
      : html`<header class="sheet-head"><div class="sheet-titles">${kicker ? html`<div class="kicker">${kicker}</div>` : null}<h2>${title}</h2>${sub ? html`<div class="sheet-sub">${sub}</div>` : null}</div>
      <button class="x" aria-label="close" onClick=${onClose}><${NL.Icon} name="x" /></button></header>`}
    <div class="sheet-body">${children}</div>${footer ? html`<footer class="sheet-foot">${footer}</footer>` : null}</aside>`;

  NL.ConfirmDialog = ({ title, body, ok, cancel, danger, typed, resolve, input, placeholder, detail }) => {
    const [txt, setTxt] = useState('');
    const good = typed ? txt.trim() === typed : input ? !!txt.trim() : true;
    const done = () => good && resolve(input ? txt.trim() : true);
    return html`<div class="dialog" role="alertdialog" aria-modal="true" aria-label=${title}>
      <h3>${title}</h3>
      ${body ? html`<div class="dialog-body">${typeof body === 'string' ? html`<p>${body}</p>` : body}</div>` : null}
      ${detail ? html`<div class="dialog-detail">${detail}</div>` : null}
      ${typed ? html`<${NL.Field} label=${html`Type <b class="mono">${typed}</b> to confirm`}><${NL.Input} value=${txt} onInput=${setTxt} autofocus mono onEnter=${done} /></${NL.Field}>` : null}
      ${input ? html`<${NL.Field} label=${input}><${NL.Input} value=${txt} onInput=${setTxt} autofocus placeholder=${placeholder} onEnter=${done} /></${NL.Field}>` : null}
      <div class="dialog-actions"><${NL.Btn} onClick=${() => resolve(false)}>${cancel || 'Cancel'}</${NL.Btn}>
        <${NL.Btn} kind=${danger ? 'danger' : 'primary'} disabled=${!good} onClick=${done}>${ok || 'Confirm'}</${NL.Btn}></div></div>`;
  };

  NL.OverlayHost = () => {
    const list = NL.useLayers(), top = list[list.length - 1];
    useLayoutEffect(() => {
      if (!top) return;
      const host = document.querySelector('[data-layer-id="' + top.id + '"]');
      const dialog = host.querySelector('.sheet,.dialog') || host;
      if (!dialog.hasAttribute('role')) dialog.setAttribute('role', 'dialog');
      dialog.setAttribute('aria-modal', 'true');
      dialog.tabIndex = -1;
      const heading = dialog.querySelector('h1,h2,h3');
      if (heading && !dialog.hasAttribute('aria-label') && !dialog.hasAttribute('aria-labelledby')) {
        heading.id ||= 'layer-title-' + top.id;
        dialog.setAttribute('aria-labelledby', heading.id);
      }
      const background = [...host.parentElement.children].filter(el => el !== host && !el.classList.contains('toasts'));
      const previous = background.map(el => [el, el.inert]);
      background.forEach(el => { el.inert = true; });
      const controls = () => [...host.querySelectorAll('button,input,textarea,select,a[href],iframe,[tabindex]')]
        .filter(el => el.tabIndex >= 0 && !el.disabled && !el.closest('[inert]') && el.getClientRects().length);
      const focusInside = () => (controls()[0] || dialog).focus({ preventScroll: true });
      const contain = e => { if (!host.contains(e.target)) focusInside(); };
      const tab = e => {
        if (e.key !== 'Tab') return;
        const items = controls(), at = items.indexOf(document.activeElement);
        if (!items.length || e.shiftKey && at <= 0 || !e.shiftKey && (at < 0 || at === items.length - 1)) {
          e.preventDefault();
          (items.length ? items[e.shiftKey ? items.length - 1 : 0] : dialog).focus();
        }
      };
      document.addEventListener('focusin', contain);
      host.addEventListener('keydown', tab);
      if (!host.contains(document.activeElement)) focusInside();
      return () => {
        document.removeEventListener('focusin', contain);
        host.removeEventListener('keydown', tab);
        previous.forEach(([el, inert]) => { el.inert = inert; });
        if (host.contains(document.activeElement) || document.activeElement === document.body) {
          const opener = top.opener;
          const restore = () => {
            const remaining = document.querySelectorAll('.layer'), front = remaining[remaining.length - 1];
            if (opener?.isConnected && !opener.closest('[inert]') && (!front || front.contains(opener))) opener.focus({ preventScroll: true });
          };
          restore();
          // Async buttons become enabled when their confirmation promise settles.
          if (document.activeElement !== opener) requestAnimationFrame(restore);
        }
      };
    }, [top?.id]);
    if (!list.length) return null;
    return html`${list.map((layer, i) => html`<div data-layer-id=${layer.id} key=${layer.id} class=${cls('layer', 'layer-' + layer.kind)} style=${{ zIndex: 100 + i * 2 }}>
      <div class="scrim" onClick=${() => NL.close(layer.id)}></div>
      <${layer.Comp} ...${layer.props} onClose=${() => NL.close(layer.id)} layerId=${layer.id} /></div>`)}`;
  };

  NL.Toasts = () => {
    const list=NL.useToasts();
    return html`<div class="toasts" role="status" aria-live="polite">${list.map(t=>html`<div class=${cls('toast','toast-'+t.tone)} key=${t.id}>${t.msg}</div>`)}</div>`;
  };

  /* ── markdown (marked + DOMPurify + KaTeX; offline) ─────────────────────── */
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function mathHtml(src) {
    if (!window.katex) return esc(src);
    let body = src, display = false;
    if (/^\$\$/.test(src)) { body = src.slice(2, -2); display = true; }
    else if (/^\\\[/.test(src)) { body = src.slice(2, -2); display = true; }
    else if (/^\\\(/.test(src)) { body = src.slice(2, -2); }
    else if (/^\$/.test(src)) { body = src.slice(1, -1); }
    try { return window.katex.renderToString(body, { displayMode: display, throwOnError: false }); } catch (e) { return esc(src); }
  }
  function assetUrl(sel, src) {
    if (!sel || sel.rel == null || /^(https?:|data:|\/)/i.test(src)) return null;
    const dir = sel.rel.split('/').slice(0, -1);
    for (const seg of src.split('/')) { if (seg === '' || seg === '.') continue; if (seg === '..') dir.pop(); else dir.push(seg); }
    return `/api/libfile?${NL.qs({ scope: sel.scope, slug: sel.slug || '', rel: dir.join('/') })}`;
  }
  /** markdown → sanitized HTML (with unparsed document metadata). Math is stashed before marked so `$a_i$` survives. */
  NL.mdToHtml = (mdText, sel) => {
    let text = String(mdText || '').replace(/^﻿/, '');
    let front = '';
    const fm = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
    if (fm) {
      text = text.slice(fm[0].length);
      if (fm[1].trim()) front = `<details class="md-frontmatter"><summary>Document details</summary><pre>${esc(fm[1])}</pre></details>`;
    }
    if (!(window.marked && window.DOMPurify)) return front + `<pre class="plain">${esc(text)}</pre>`;
    const stash = [];
    const put = m => { stash.push(m); return `${stash.length - 1}`; };
    text = text.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~)/).map((seg, i) => i % 2 ? seg : seg
      .replace(/\$\$[\s\S]+?\$\$/g, put).replace(/\\\[[\s\S]+?\\\]/g, put).replace(/\\\([\s\S]+?\\\)/g, put)
      .replace(/\$(?!\s)((?:\\.|[^$\\\n])+?)(?<![\s\\])\$(?!\d)/g, put)).join('');
    let out;
    try { out = window.marked.parse(text, { gfm: true, breaks: false, async: false }); } catch (e) { return front + `<pre class="plain">${esc(mdText)}</pre>`; }
    out = window.DOMPurify.sanitize(out).replace(/(\d+)/g, (m, i) => mathHtml(stash[+i]));
    if (sel) out = out.replace(/<img([^>]*?)src="([^"]+)"/g, (m, a, src) => { const u = assetUrl(sel, src.replace(/&amp;/g, '&')); return `<img${a}loading="lazy" src="${u ? esc(u) : src}"`; });
    return front + out;
  };
  NL.Markdown = ({ text, sel, className }) => {
    const ref = useRef();
    const markup = useMemo(() => NL.mdToHtml(text, sel), [text, sel && sel.rel, sel && sel.slug]);
    useEffect(() => {
      const host = ref.current; if (!host) return;
      host.querySelectorAll('a[href]').forEach(a => {
        const href = a.getAttribute('href') || '';
        if (sel?.knowledgeId&&href===sel.attachment){a.href='/api/knowledge/attachment?'+NL.qs({study:sel.study||'',id:sel.knowledgeId});a.target='_blank';a.rel='noopener'}
        else if (/^https?:/i.test(href)) { a.target = '_blank'; a.rel = 'noopener'; }
        else if (!href.startsWith('#')) a.onclick = ev => {
          ev.preventDefault();
          const url=assetUrl(sel,href);
          if(url&&sel){const rel=new URL(url,location.origin).searchParams.get('rel');NL.openDoc(sel.scope,sel.slug,rel)}
          else NL.toast('That links to another file. Open it from the Library.');
        };
      });
    }, [markup]);
    return html`<div ref=${ref} class=${cls('md', className)} dangerouslySetInnerHTML=${{ __html: markup }}></div>`;
  };

  /* ── editor deep links (the dashboard is local: vscode://file/… etc.) ───── */
  NL.editorUri = (abs, line, machine) => {
    const s = NL.getState(); const ed = (s && s.editor) || 'vscode';
    if (!abs || ed === 'none') return null;
    const scheme = /^[a-z][a-z0-9+.-]*$/.test(ed) ? ed : 'vscode';
    let p = String(abs).replace(/\\/g, '/'); if (!p.startsWith('/')) p = '/' + p;
    // a lab on another machine: VS Code (and its forks) open it through Remote-SSH
    const host = machine ? (s?.machines || []).find(m=>m.id===machine)?.host : s?.remote?.host;
    if (host) return `${scheme}://vscode-remote/ssh-remote+${encodeURIComponent(host)}${p}${line ? ':' + line : ''}`;
    return `${scheme}://file${p}${line ? ':' + line : ''}`;
  };
  NL.EditorLink = ({ path, machine, children }) => { const u = NL.editorUri(path, null, machine); return u ? html`<a class="link small" href=${u}>${children || 'open in editor ↗'}</a>` : null; };
})();
