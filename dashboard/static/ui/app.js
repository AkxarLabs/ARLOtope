/* Visual research workspace with ordinary navigation and focused editing views. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, render, useState, useEffect, useLayoutEffect, useRef } = NL;
  const NAV = [['', 'Lab'], ['studies', 'Studies'], ['library', 'Library'], ['workflow', 'Workflow']];
  const PAGES = { home: () => LabView, overview: () => NL.Home, studies: () => NL.StudiesPage, study: () => NL.StudyPage,
    runs: () => NL.RunsPage, run: () => NL.RunsPage, library: () => NL.LibraryPage,
    artifacts: () => NL.LibraryPage, history: () => NL.HistoryPage,
    workflow: () => NL.ComposePage,
    settings: () => NL.SettingsPage, labs: () => NL.LabsPage, setup: () => NL.SetupPage,
    start: () => NL.StarterPage, world: () => LabView, 'not-found': () => NotFound };
  const GROUP = { home: '', world: '', overview: '', runs: '', run: '', study: 'studies', artifacts: 'library', history: 'library' };
  NL.followAgent=id=>{NL.pendingFollow=id;NL.go('');document.querySelector('.stage')?.scrollTo(0,0);window.dispatchEvent(new CustomEvent('lab-follow',{detail:id}))};

  const Search = ({ onClose }) => {
    const s = NL.useLab(), [q, setQ] = useState(''), [selected, setSelected] = useState(0), results = useRef();
    const all = [...NAV.map(([path, title]) => ({ title, sub: 'Page', run: () => NL.go(path) })),
      ...(s.items || []).map(i => ({ title: i.title || i.id, sub: 'Study', run: () => NL.go('study/' + i.id) })),
      ...NL.intents().map(i => ({ title: i.title, sub: 'Procedure', run: () => NL.startIntent(i) })),
      { title: 'All agents', sub: 'Lab', run: () => NL.go('runs') },
      { title: 'Machines', sub: 'Page', run: () => NL.go('labs') },
      { title: 'History', sub: 'Page', run: () => NL.go('history') },
      { title: 'New study', sub: 'Page', run: () => NL.go('start') },
      { title: 'Documents', sub: 'Library', run: () => NL.go('library?view=documents') },
      { title: 'Settings', sub: 'Page', run: () => NL.go('settings') }];
    const list = all.filter(x => (x.title + ' ' + x.sub).toLowerCase().includes(q.trim().toLowerCase())).slice(0, 12);
    const at = Math.min(selected, list.length - 1);
    const pick = action => { onClose(); action(); };
    useEffect(() => { results.current?.children[at]?.scrollIntoView({ block: 'nearest' }); }, [at, q]);
    const key = e => {
      if (e.isComposing) return;
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onClose(); }
      else if (list.length && ['ArrowDown', 'ArrowUp'].includes(e.key)) {
        e.preventDefault(); setSelected((at + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length);
      } else if (e.key === 'Enter' && list[at]) { e.preventDefault(); pick(list[at].run); }
    };
    return html`<div class="dialog dialog-wide"><h2>Search the lab</h2>
      <${NL.Field} label="Find a study, page or procedure"><input class="input" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="lab-search-results" aria-activedescendant=${at >= 0 ? 'lab-search-' + at : null}
        value=${q} onInput=${e => { setQ(e.target.value); setSelected(0); }} onKeyDown=${key} placeholder="Search…" /></${NL.Field}>
      <div class="search-results" id="lab-search-results" role="listbox" aria-label="Search results" ref=${results}>${list.map((x, i) => html`<button type="button" role="option" id=${'lab-search-' + i} aria-selected=${i === at} tabindex="-1" class="search-result" onMouseDown=${e => e.preventDefault()} onMouseMove=${() => setSelected(i)} onClick=${() => pick(x.run)}><b>${x.title}</b><small>${x.sub}</small></button>`)}</div>
      ${!list.length ? html`<p class="muted" role="status">No matches.</p>` : null}
      ${q.trim() ? html`<${NL.Btn} onClick=${() => pick(() => NL.openAssistant({initialText:q}))}>Ask about “${NL.clip(q, 50)}”</${NL.Btn}>` : null}
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Close</${NL.Btn}></div></div>`;
  };
  NL.openPalette = () => NL.open(Search, {}, { key: 'palette', kind: 'dialog' });
  NL.startIntent = intent => NL.openStart({ intent: intent.id });
  NL.openStartOrb = () => NL.go('start');
  NL.pauseLab = async on => {
    if (on && !await NL.confirm({ title: 'Pause the lab?', ok: 'Pause', danger: true,
      body: 'Running agents stop and remain resumable. New work waits until you resume.' })) return;
    return NL.act('/api/lab/pause', { paused: !!on, confirm: true }, on ? 'Lab paused' : 'Lab resumed');
  };
  NL.PausedBar = () => {
    const s = NL.useLab();
    return s.lab_paused ? html`<div class="research-paused" role="status"><b>Lab paused.</b>
      <${NL.Btn} small onClick=${() => NL.pauseLab(false)}>Resume</${NL.Btn}></div>` : null;
  };

  const LabView = ({ active }) => {
    const ref = useRef(), p = NL.usePrefs();
    const firstTheme = useRef(NL.themeNow()).current, theme = NL.themeNow();
    const [view,setView]=useState(()=>NL.ls.get('nl-world-view','full')==='unified'?'unified':'full');
    const changeView=value=>{NL.ls.set('nl-world-view',value);setView(value)};
    const [inspected,setInspected]=useState(null),peek=useRef(),point=useRef();
    const dismiss=()=>{setInspected(null);ref.current?.contentWindow?.postMessage({labView:1,command:'dismiss-agent'},'*')};
    const place=()=>NL.placeAgentPeek(peek.current,point.current);
    useEffect(()=>{place();const observer=new ResizeObserver(place);if(peek.current)observer.observe(peek.current);return()=>observer.disconnect()},[inspected]);
    useEffect(()=>{const outside=e=>{if(!peek.current?.contains(e.target)&&e.target!==ref.current)dismiss()};const key=e=>{if(e.key==='Escape')dismiss()};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',key);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',key)}},[]);
    useEffect(() => {
      const receive = e => {
        if (e.source !== ref.current?.contentWindow || e.data?.labView !== 1) return;
        const { kind, id, checkpoint, sub, target, anchor } = e.data;
        if(kind==='inspect-agent'){point.current=anchor;setInspected(target)}
        else if(kind==='agent-anchor'){point.current=anchor;place()}
        else if(kind==='dismiss-agent')setInspected(null);
        else if(kind==='start')NL.go('start');
        else if (kind === 'study' && NL.item(NL.getState(), id)) NL.go('study/' + id);
        else if (kind === 'run') NL.openRun(id, sub);
        else if (kind === 'worker' && id) NL.openWorker(id);
        else if (kind === 'artifact' && id) NL.openArtifact(id);
        else if (kind === 'inbox') NL.open(NL.InboxSheet, {}, {key:'inbox'});
        else if (kind === 'assistant') NL.openAssistant();
        else if (kind === 'following' && NL.pendingFollow === id) NL.pendingFollow = null;
        else if (kind === 'checkpoint' && NL.item(NL.getState(), id)) NL.openCheckpoint(id, checkpoint);
      };
      window.addEventListener('message', receive);
      const follow=e=>ref.current?.contentWindow?.postMessage({labView:1,command:'follow',id:e.detail},'*');
      window.addEventListener('lab-follow',follow);
      return () => {window.removeEventListener('message', receive);window.removeEventListener('lab-follow',follow)};
    }, []);
    const send = () => {const state=NL.getState()||{};ref.current?.contentWindow?.postMessage({ labView: 1, active,
      ...(active ? {state: {...state,world_view:view,agents:NL.displayAgents(state)},
        theme: NL.themeNow(), cast: p.cast, motion: p.motion, labels: p.labels} : {}) }, '*');
      if(active&&NL.pendingFollow)ref.current?.contentWindow?.postMessage({labView:1,command:'follow',id:NL.pendingFollow},'*')};
    const s = NL.useLab();
    useLayoutEffect(send, [active, s, view, theme, p.motion, p.labels, JSON.stringify(p.cast)]);
    useEffect(()=>{if(!active)dismiss()},[active]);
    return html`<div class="lab-view"><header aria-label="Lab overview"><h1>The lab</h1>
      <div class="row"><${NL.Seg} ariaLabel="Lab layout" value=${view} onChange=${changeView} options=${[{value:'full',label:'By machine'},{value:'unified',label:'Unified'}]}/>
      <button class="link small" type="button" onClick=${()=>NL.openAddMachine()}>+ Machine</button>
      <a class="link small" href="#/labs">Machines</a></div>
      ${(s.machines||[]).filter(m=>['auth','error'].includes(m.state)).map(m=>html`<button class="link small" type="button" onClick=${()=>NL.openMachineSetup(m.id,{autoConnect:false})}>${m.name||m.id} · ${m.state==='auth'?'Sign in again':'Reconnect'}</button>`)}
      <div class="world-status"><a class="link" href="#/studies">${NL.plural((s.items||[]).filter(i=>!i.finished&&!NL.isShelved(i.state)).length,'active study','active studies')}</a><a class="link" href="#/runs">${NL.plural((s.agents||[]).filter(a=>a.status!=='queued').length,'agent')} present</a><button type="button" class="link" onClick=${()=>{document.getElementById('lab-desk')?.scrollIntoView({behavior:NL.prefs.motion?'smooth':'instant'});document.getElementById('lab-desk-heading')?.focus({preventScroll:true})}}>Lab notes ↓</button></div></header>
      <${NL.LabFrame} frameRef=${ref} onLoad=${send} onRetry=${dismiss} src=${'static/lab-view.html?lamp='+firstTheme} title="3D research lab"
        fallback=${html`<button type="button" class="link small" onClick=${()=>{document.getElementById('lab-desk')?.scrollIntoView();document.getElementById('lab-desk-heading')?.focus({preventScroll:true})}}>View work below ↓</button>`}/>
      ${inspected?html`<${NL.AgentPeek} key=${inspected.agent_id} target=${inspected} nodeRef=${peek} onClose=${dismiss} onFollow=${()=>ref.current?.contentWindow?.postMessage({labView:1,command:'follow',id:inspected.agent_id},'*')}/>`:null}</div>`;
  };
  const NotFound = ({ error }) => html`<div class="page"><h1>Page not found</h1><p>${error || 'This address does not match a Lab page.'}</p>
    <div class="row"><a class="btn" href="#/">Return to the Lab</a><${NL.Btn} onClick=${NL.openPalette}>Search</${NL.Btn}></div></div>`;
  const App = () => {
    const route = NL.useRoute(), s = NL.useLab();
    const page = Object.hasOwn(PAGES, route.page) ? route.page : 'not-found';
    const showLab = page === 'home' || page === 'world', labSeen = useRef(showLab);
    if (showLab) labSeen.current = true;
    const previous = useRef(page), Component = PAGES[page]();
    const main = useRef(), path = page + '/' + route.args.join('/'), focusedPath = useRef(path);
    const needs = NL.needsYou(s).length, connection = NL.useConn();
    NL.usePrefs();
    useEffect(() => {
      if (previous.current !== page) { NL.closeSheets(); previous.current = page; }
      document.body.dataset.page = page;
      if (page === 'run' && route.args[0]) NL.openRun(route.args[0]);
      const q = route.query || {};
      if (page === 'study' && q.checkpoint) NL.openCheckpoint(route.args[0], q.checkpoint);
      if ('start' in q) NL.openStart(q.start ? { intent: q.start } : {});
      if (q.run) NL.openRun(q.run);
      if (q.panel) NL.openPanel(q.panel, q.study);
      document.querySelector('.stage')?.scrollTo(0, 0);
    }, [page, route.args.join('/'), JSON.stringify(route.query)]);
    useEffect(() => {
      if (focusedPath.current === path) return;
      focusedPath.current = path;
      const frame = requestAnimationFrame(() => {
        // A route may open a dialog or a form with its own autofocus.
        if (document.querySelector('.layer') || main.current?.contains(document.activeElement) && document.activeElement.matches('input,textarea,select,[contenteditable="true"],[role="tab"]')) return;
        const heading = [...(main.current?.querySelectorAll('h1') || [])].find(el => el.getClientRects().length);
        if (heading) heading.tabIndex = -1;
        (heading || main.current)?.focus({ preventScroll: true });
      });
      return () => cancelAnimationFrame(frame);
    }, [path]);
    return html`<a class="skip-link" href="#main-content" onClick=${e=>{e.preventDefault();document.getElementById('main-content').focus();}}>Skip to content</a>
      <header class="lab-header"><a class="lab-brand" href="#/" aria-label="ARLOtope"><img class="arlotope-mark" src="static/brand/arlotope-mark.png" alt=""/>
        <span>ARLOtope</span></a>
        <button type="button" class="theme-switch" aria-label=${NL.themeNow()==='day'?'Switch to dark mode':'Switch to light mode'} title=${NL.themeNow()==='day'?'Switch to dark mode':'Switch to light mode'} onClick=${()=>NL.setPref('theme',NL.themeNow()==='day'?'night':'day')}>${NL.themeNow()==='day'?'◑ Dark':'◐ Light'}</button>
        <nav class="lab-nav" aria-label="Main navigation">${NAV.map(([path, title]) => html`<a href=${'#/' + path}
          aria-current=${(GROUP[page] ?? page) === path ? 'page' : null}>${title}</a>`)}</nav>
        <div class="lab-tools"><button type="button" class="iconbtn" onClick=${NL.openPalette} aria-label="Search" title="Search (Ctrl+K)"><${NL.Glyph} name="lens" size=${18} /></button>
          <button type="button" class="needs-button" onClick=${() => NL.open(NL.InboxSheet, {}, { key: 'inbox' })}>Inbox${needs ? html`<span class="count">${needs}</span>` : null}</button>
          <a class="iconbtn" href="#/settings" aria-label="Settings" title="Settings"><${NL.Glyph} name="gear" size=${18} /></a>
          <${NL.Btn} kind="primary" onClick=${() => NL.go('start')}>New study</${NL.Btn}></div></header>
      <main ref=${main} id="main-content" class="stage" tabIndex="-1"><${NL.PausedBar} />
        ${connection === 'offline' || connection === 'reconnecting' ? html`<div class="connection-note" role="status">Reconnecting. Showing the last known state.</div>` : null}
        ${labSeen.current ? html`<div class="lab-mount" hidden=${!showLab}><${LabView} active=${showLab} /><${NL.LabDesk}/></div>` : null}
        ${!showLab ? html`<${Component} args=${route.args} query=${route.query} error=${route.error} />` : null}
        <footer class="lab-footer"><nav aria-label="Resources"><a href="#/runs">All agents</a><a href="#/history">History</a><a href="#/labs">Machines</a></nav></footer>
      </main><${NL.AssistantButton}/><${NL.OverlayHost} /><${NL.Toasts} />`;
  };
  let seen = null;
  NL.onSnapshot = (_previous, next) => {
    const attention = next?.attention || [], needs = attention.filter(a => a.sev !== 'info');
    document.title = (needs.length ? `(${needs.length}) ` : '') + 'ARLOtope' + (next?.lab_info?.name && next.lab_info.name !== 'ARLOtope' ? ` · ${next.lab_info.name}` : '');
    const fresh = seen === null ? [] : attention.filter(a => !seen.has(a.id));
    const notices = fresh.length > 3 ? [...fresh.slice(0, 2), {
      id: 'attention-burst:' + fresh.slice(2).map(a => a.id).join('|'),
      title: `${fresh.length - 2} more updates in the Inbox`,
      body: fresh.slice(2, 5).map(a => NL.attSubject(a,next)+': '+a.title).join(' · '),
      sev: fresh.slice(2).some(a => a.sev === 'block') ? 'block' : 'info', grouped: true,
    }] : fresh;
    for (const a of notices) {
      const title = a.grouped ? a.title : NL.attSubject(a,next) + ' · ' + a.title;
      NL.toast(title, a.sev === 'block' ? 'warn' : a.kind === 'report' ? 'ok' : 'info');
      if (NL.prefs.notify && window.Notification?.permission === 'granted' && document.hidden) {
        try {
          const notice = new Notification(title, { body: a.body || '', tag: a.id });
          notice.onclick = () => { window.focus(); a.grouped ? NL.open(NL.InboxSheet, {}, {key:'inbox'}) : NL.attOpen(a); };
        } catch (_) { /* The Inbox still holds the update if desktop delivery is unavailable. */ }
      }
    }
    seen = new Set(attention.map(a => a.id));
  };
  window.addEventListener('keydown', e => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(e.target?.tagName) || e.target?.isContentEditable;
    if ((e.key === 'k' && (e.ctrlKey || e.metaKey)) || (e.key === '/' && !typing)) {
      e.preventDefault(); if (!NL.isOpen('palette')) NL.openPalette();
    }
  });
  NL.boot = () => {
    NL.applyTheme(); render(html`<${App} />`, document.getElementById('app'));
    if (NL.DEMO && NL.startDemo) NL.startDemo();
    else { if (NL.store.state) NL.onSnapshot(null, NL.store.state); else NL.refresh(); NL.connect(); }
    const q = new URLSearchParams(location.search);
    if (q.get('open')) NL.go('study/' + q.get('open'));
    if (q.get('read')) { const [scope, slug, ...rel] = q.get('read').split(':'); NL.openDoc(scope, slug || null, rel.join(':')); }
    if (q.get('roomdraft')) NL.get('/api/room-draft?id='+encodeURIComponent(q.get('roomdraft')))
      .then(d=>d.ok?NL.openRoomDesign(d.room,d.id):NL.toast(d.error||'Room draft not found','bad'));
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', NL.boot); else NL.boot();
})();
