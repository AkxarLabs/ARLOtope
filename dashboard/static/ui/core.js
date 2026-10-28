/* ARLOtope — UI core: the live lab store, the API client, the router, preferences, toasts, layers.
   No build step: Preact + hooks + htm are vendored UMD globals (static/vendor/preact/). Every UI file
   registers into window.NL. Components use `html\`...\`` (htm) instead of JSX. */
(function () {
  'use strict';
  const { h, render, Fragment } = window.preact;
  const H = window.preactHooks;
  const html = window.htm.bind(h);
  const NL = (window.NL = window.NL || {});
  Object.assign(NL, { h, render, Fragment, html, ...H });

  /* ── small helpers ─────────────────────────────────────────────────────── */
  NL.cls = (...xs) => xs.filter(Boolean).join(' ');
  NL.hhmm = ts => (ts || '').slice(11, 16);
  NL.plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
  NL.mins = s => s == null ? '' : s < 60 ? `${Math.round(s)}s` : s < 3600 ? `${Math.round(s / 60)}m` : `${(s / 3600).toFixed(1)}h`;
  /** one way to write a moment everywhere: "Sun 4 Oct, 13:47" (the year only when it isn't this one) */
  NL.when = ts => {
    const d = ts ? new Date(ts) : null;
    if (!d || isNaN(d)) return '';
    const p = n => String(n).padStart(2, '0'), now = new Date();
    return `${d.toLocaleDateString('en-GB', { weekday: 'short' })} ${d.getDate()} ${d.toLocaleDateString('en-GB', { month: 'short' })}${d.getFullYear() !== now.getFullYear() ? ' ' + d.getFullYear() : ''}, ${p(d.getHours())}:${p(d.getMinutes())}`;
  };
  NL.ago = ts => {
    if (!ts) return '';
    const t = Date.parse(ts); if (isNaN(t)) return '';
    const d = (Date.now() - t) / 1000;
    if (d < 60) return 'just now';
    if (d < 3600) return `${Math.round(d / 60)} min ago`;
    if (d < 86400) return `${Math.round(d / 3600)} h ago`;
    return `${Math.round(d / 86400)} d ago`;
  };
  NL.clip = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  NL.qs = o => Object.entries(o).filter(([, v]) => v != null && v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');
  const ls = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  NL.ls = ls;

  /* ── the lab's definition: its steps, workflows (each a path of steps, where outcomes lead, its checkpoints),
     rooms and procedures — from workflow/ (the live snapshot's `workflow`; the generated workflow-default.js
     serves demo/static pages). applyWorkflow() refills these in place whenever the definition changes.
     A study stands at one step (item.state) of its workflow (item.workflow). */
  NL.LIFECYCLE = []; NL.STATE_LABEL = {}; NL.ROOMS = []; NL.PROC = {};
  NL.NEXT_FOR_STATE = {}; NL.WORKFLOWS = []; NL.STEPS = {}; NL.WF = {};
  let wfSig = '';
  // the subagent roles: labels from agent-roles/<role>.yaml (via the workflow), colours from the theme
  const ROLE_COLOR = { orchestrator: 'var(--r-orch)', 'experiment-runner': 'var(--r-run)', 'fresh-context-reviewer': 'var(--r-rev)',
    overseer: 'var(--r-over)', 'ideation-critic': 'var(--r-crit)', 'scoping-advocate': 'var(--r-scope)' };
  NL.ROLE = { orchestrator: { label: 'Orchestrator', color: ROLE_COLOR.orchestrator } };
  const refill = (o, v) => { for (const k of Object.keys(o)) delete o[k]; Object.assign(o, v); };
  NL.applyWorkflow = wf => {
    if (!wf || wf.error || !Array.isArray(wf.steps)) return false;
    const sig = JSON.stringify([wf.steps, wf.rooms, wf.workflows, wf.procedures, wf.roles, wf.role_labels]);
    NL.WF = wf;
    if (sig === wfSig) return false;
    wfSig = sig;
    refill(NL.STEPS, Object.fromEntries(wf.steps.map(s => [s.id, s])));
    NL.LIFECYCLE.splice(0, NL.LIFECYCLE.length, ...wf.steps.filter(s => !s.shelf).map(s => s.id));
    refill(NL.STATE_LABEL, Object.fromEntries(wf.steps.map(s => [s.id, s.label || s.id])));
    NL.ROOMS.splice(0, NL.ROOMS.length, ...(wf.rooms || []).map(r => ({ key: r.id, label: r.label, title: r.title, states: r.steps || [] })));
    NL.WORKFLOWS.splice(0, NL.WORKFLOWS.length, ...(wf.workflows || []).map(w => ({ ...w, steps: w.path || [] })));
    refill(NL.PROC, wf.procedures || {});
    refill(NL.NEXT_FOR_STATE, Object.fromEntries(wf.steps.filter(s => s.do).map(s => [s.id, s.do])));
    for (const k of Object.keys(NL.ROLE)) if (k !== 'orchestrator') delete NL.ROLE[k];
    (wf.roles || []).forEach(r => { NL.ROLE[r] = { label: (wf.role_labels || {})[r] || r, color: ROLE_COLOR[r] || 'var(--ink-soft)' }; });
    return true;
  };
  NL.applyWorkflow(window.__WORKFLOW_DEFAULT__);
  NL.isShelved = st => !!(NL.STEPS[st] || {}).shelf;                 // parked or killed: the PI can bring it back
  // the end of the line: a shelf, or a step that ends every workflow it is on
  NL.isTerminal = st => NL.isShelved(st) || (NL.WORKFLOWS.some(w => w.steps.includes(st)) && NL.WORKFLOWS.every(w => !w.steps.includes(st) || w.steps[w.steps.length - 1] === st));
  NL.isDone = st => NL.isTerminal(st) && !NL.isShelved(st);         // at the end of its workflow, not parked/killed
  NL.stateTone = st => st === 'killed' ? 'bad' : NL.isShelved(st) ? 'muted' : NL.isDone(st) ? 'ok' : 'state';   // a step pill's colour
  /* ── workflows and checkpoints ──────────────────────────────────────────────────────────────────
     A study follows one workflow (item.workflow); a checkpoint is the PI's approval, `before` a step or `during`
     one (at a named point). item.checkpoints holds the latest decision on each; item.waiting the one it waits
     at now; item.asks an outcome the workflow left to the PI; item.flags what the lab's watches saw. */
  NL.workflowOf = it => NL.WORKFLOWS.find(w => w.id === (it && it.workflow)) || NL.WORKFLOWS.find(w => w.default) || NL.WORKFLOWS[0] || { id: 'research', steps: NL.LIFECYCLE, checkpoints: [], routes: {} };
  NL.taskLabel = (it, id=it.state) => NL.workflowOf(it).nodes?.[id]?.label || NL.STATE_LABEL[id] || id;
  NL.stepsOf = it => (NL.workflowOf(it).steps || NL.LIFECYCLE);
  NL.checkpointsOf = it => (NL.workflowOf(it).checkpoints || []);
  NL.checkpoint = (id, it) => (it ? NL.checkpointsOf(it) : NL.WORKFLOWS.flatMap(w => w.checkpoints || [])).find(c => c.id === id);
  NL.approvedCp = (it, id) => (((it && it.checkpoints) || {})[id] || {}).decision === 'approved';
  NL.cpWhere = c => c ? (c.before ? `before ${NL.STATE_LABEL[c.before] || c.before}` : `during ${NL.STATE_LABEL[c.during] || c.during}${c.at ? ', at ' + c.at : ''}`) : '';
  // a checkpoint's check (or watch): a name, or {name: {param: value}}
  NL.checkName = c => (c && typeof c === 'object') ? Object.keys(c)[0] : String(c);
  NL.checkLabel = c => { const n = NL.checkName(c), p = (c && typeof c === 'object') ? c[n] || {} : {};
    const ps = Object.entries(p).map(([k, v]) => `${k}=${v}`).join(', '); return ps ? `${n} (${ps})` : n; };
  // the procedure that does a step's work for this study: its own swap, its workflow's, else the step's
  NL.doesFor = (it, st) => {
    const node=NL.workflowOf(it).nodes?.[st];
    const p = node&&'procedure' in node?node.procedure:(NL.STEPS[st] || {}).do;
    if (!p) return null;
    return ((it && it.use) || {})[p] || (NL.workflowOf(it).use || {})[p] || p;
  };
  NL.proceduresFor = it => {
    const swaps=p=>it.use?.[p]||NL.workflowOf(it).use?.[p]||p;
    return [...new Set([NL.doesFor(it,it.state),...(NL.STEPS[it.state]?.also||[]).map(swaps)].filter(Boolean))];
  };
  // what a study should run next: its step's procedure — unless it waits for you, is shelved or finished
  NL.nextSkill = it => {
    if (typeof it === 'string') return NL.NEXT_FOR_STATE[it] || null;
    if (!it || it.finished || (it.waiting || []).length || it.asks || NL.isShelved(it.state)) return null;
    return NL.doesFor(it, it.state);
  };
  // run status → what the PI reads (one vocabulary everywhere)
  NL.RUN_WORD = {
    queued: 'Queued', starting: 'Starting', running: 'Running', resuming: 'Resuming', waiting_input: 'Waiting for you',
    completed: 'Finished', failed: 'Failed', timeout: 'Timed out', killed: 'Stopped',
  };
  NL.RUN_TONE = { queued: 'muted', starting: 'live', running: 'live', resuming: 'live', waiting_input: 'ask',
    completed: 'ok', failed: 'bad', timeout: 'bad', killed: 'muted' };
  NL.RUN_ACTIVE = new Set(['starting', 'running', 'resuming']);
  NL.RUN_DONE = new Set(['completed', 'failed', 'timeout', 'killed']);
  NL.runWaiting = r => r.status === 'waiting_input' || NL.RUN_ACTIVE.has(r.status) && !!(r.pending_question || r.pending_questions?.length || r.pending_permissions?.length);
  NL.runTitle = (r, s = NL.getState() || {}) => {
    if (!r) return '';
    const subject = r.subject || r.explains?.study, it = subject && (s.items || []).find(i => i.id === subject);
    const what = r.kind === 'ask' || r.skill === 'ask' ? r.label || r.prompt_summary || 'Instruction'
      : NL.PROC[r.skill]?.title || r.label || r.command || r.prompt_summary;
    return what ? what + (it ? ' · ' + (it.title || it.id) : subject ? ' · ' + subject : '') : r.run_id;
  };

  NL.roleOf = r => NL.ROLE[r] || { label: r || 'Agent', color: 'var(--ink-soft)' };

  NL.procTitle = s => (NL.PROC[s] && NL.PROC[s].title) || ('/' + s);

  /* ── the live lab store ────────────────────────────────────────────────── */
  const store = { state: window.__STATE__ || null, live: true, listeners: new Set(), conn: 'connecting' };
  NL.store = store;
  if (store.state && store.state.workflow) NL.applyWorkflow(store.state.workflow);
  NL.getState = () => store.state;
  function emit() { for (const f of store.listeners) { try { f(store.state); } catch (e) { console.error(e); } } }
  NL.setState = s => { const prev = store.state; store.state = s; if (s && s.workflow) NL.applyWorkflow(s.workflow); NL.onSnapshot && NL.onSnapshot(prev, s); emit(); };
  /** Re-render the calling component whenever a listener set fires (the one subscription pattern). */
  const useSub = set => {
    const [, force] = H.useReducer(x => x + 1, 0);
    H.useEffect(() => { set.add(force); return () => set.delete(force); }, []);
  };
  /** Subscribe a component to the lab snapshot (re-renders on every change). */
  NL.useLab = () => { useSub(store.listeners); return store.state || {}; };
  NL.useConn = () => { useSub(store.listeners); return store.conn; };

  const flags = new URLSearchParams(location.search);
  NL.DEMO = flags.has('demo') && (window.__ARLOTOPE_DEMO__ === true || location.protocol === 'file:');
  NL.STATIC = flags.has('static');

  let es = null, pollT = null, backoff = 15000;
  NL.connect = function connect() {
    if (NL.DEMO || NL.STATIC) return;
    try { es && es.close(); } catch (e) { /* closed */ }
    es = new EventSource('/api/events');
    es.onopen = () => { store.conn = 'live'; backoff = 15000; if (pollT) { clearInterval(pollT); pollT = null; } emit(); };
    es.onmessage = ev => { try { const s = JSON.parse(ev.data); if (!s.error) { store.conn = 'live'; NL.setState(s); } } catch (e) { /* partial */ } };
    es.addEventListener('tick', ev => { try { const t = JSON.parse(ev.data); if (store.state && t.now) { store.state.now = t.now; } } catch (e) { /* ignore */ } });
    es.onerror = () => {
      store.conn = 'reconnecting'; emit();
      try { es.close(); } catch (e) { /* closed */ }
      if (!pollT) pollT = setInterval(NL.refresh, 5000);
      setTimeout(connect, backoff); backoff = Math.min(90000, backoff * 1.5);
    };
  };
  NL.refresh = async () => {
    if (NL.DEMO) return;   // the demo is its own lab; nothing real is fetched
    try { const r = await fetch('/api/state', { credentials: 'same-origin' }); if (r.ok) { NL.setState(await r.json()); store.conn = 'live'; }
      else if(r.status===403)checkSession(r,await r.json().catch(()=>({}))); }
    catch (e) { store.conn = 'offline'; emit(); }
  };

  /* ── API ───────────────────────────────────────────────────────────────── */
  const DEMO_READS = new Set(['/api/read', '/api/libdoc']);   // POSTs that only read: the demo answers them itself
  let sessionReload = false;
  const checkSession = (r,j) => {
    if(r.status!==403 || !/session/.test(j.error||'') || sessionReload)return;
    sessionReload=true;
    NL.toast('Reconnecting to the lab…','warn');
    setTimeout(()=>location.reload(),1200);
  };
  NL.api = async function api(path, body) {
    if (NL.DEMO && DEMO_READS.has(path)) return NL.demoRead ? NL.demoRead(path, body || {}) : { error: 'not in the demo' };
    if (NL.DEMO) return { error: 'Demo mode: nothing is written.', demo: true };
    try {
      const r = await fetch(path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
      const j = await r.json().catch(() => ({ error: `server said ${r.status}` }));
      checkSession(r,j);
      return j;
    } catch (e) { return { error: 'Could not reach the lab server. Is it still running?' }; }
  };
  NL.get = async function get(path) {
    if (NL.DEMO) { const x = NL.demoGet && NL.demoGet(path); return x || { error: 'not in the demo', demo: true }; }   // the demo's own lab, never the server's
    try {
      const r = await fetch(path, { credentials: 'same-origin' });
      const j = await r.json().catch(() => ({ error: `server said ${r.status}` }));
      checkSession(r,j);
      return !r.ok ? { error: (j && j.error) || `server said ${r.status}` } : j || { error: 'The server returned an empty response.' };
    } catch (e) { return { error: 'Could not reach the lab server.' }; }
  };
  /** Reads belong to a path/revision/retry. Null waits; previous holds successful data for this path only. */
  NL.useGet = (path, revision) => {
    const [attempt, reload] = H.useReducer(n => n + 1, 0);
    const key = H.useMemo(() => ({}), [path, revision, attempt]);
    const [result, setResult] = H.useState({});
    const previous = H.useRef(null);
    H.useEffect(() => {
      if (!path) return;
      let active = true;
      NL.get(path).then(data => {
        const error = data.error || (data.ok === false ? 'Could not load this item.' : null);
        if (active) {
          if (!error) previous.current = { path, data };
          setResult({ key, data: error ? null : data, error });
        }
      });
      return () => { active = false; };
    }, [key]);
    return { ...(result.key === key ? result : { data: null, error: null }), previous: previous.current?.path === path ? previous.current.data : null, reload };
  };
  // Poll after the previous read settles; cleanup and stale-data scope stay with useGet.
  NL.usePoll = (path, interval) => {
    const read = NL.useGet(path);
    H.useEffect(() => {
      if (!path || !read.data && !read.error) return;
      const timer = setTimeout(read.reload, interval);
      return () => clearTimeout(timer);
    }, [path, read.key, interval]);
    return read;
  };
  /** Run an API call with a toast for the outcome; returns the result. */
  NL.act = async (path, body, okMsg) => {
    const r = await NL.api(path, body);
    if (r && r.ok) { NL.toast(okMsg || r.note || 'Done', 'ok'); (r.warnings || []).forEach(w => NL.toast(w, 'warn')); setTimeout(NL.refresh, 300); }
    else NL.toast((r && r.error) || 'That did not work. Check the lab server is running, then try again.', 'bad');
    return r || {};
  };

  /* ── router: #/page/arg/arg ────────────────────────────────────────────── */
  NL.parseRoute = () => {
    const raw = (location.hash || '').replace(/^#\/?/, '');
    const [path, q] = raw.split('?');
    let parts;
    try { parts = path.split('/').filter(Boolean).map(decodeURIComponent); }
    catch (_) { return { page: 'not-found', args: [], query: {}, error: 'This address has an invalid character escape. Check the link or return to the Lab.' }; }
    const query = Object.fromEntries(new URLSearchParams(q || ''));
    return { page: parts[0] || 'home', args: parts.slice(1), query };
  };
  NL.go = (path) => { const target = '#/' + String(path || '').replace(/^#?\/?/, ''); if (location.hash !== target) location.hash = target; else window.dispatchEvent(new HashChangeEvent('hashchange')); };
  NL.useRoute = () => {
    const [r, setR] = H.useState(NL.parseRoute());
    // resync once listening: a redirect that fired before this effect ran (the first-run wizard) must not be missed
    H.useEffect(() => { const f = () => setR(NL.parseRoute()); window.addEventListener('hashchange', f); f(); return () => window.removeEventListener('hashchange', f); }, []);
    return r;
  };

  // Shared protection for forms whose edits have not been saved.
  const dirtyForms = new Map();
  const hasUnsavedChanges = () => [...dirtyForms.values()].some(Boolean);
  NL.useDirty = flag => {
    const id = H.useRef(Symbol());
    H.useLayoutEffect(() => { dirtyForms.set(id.current, !!flag); }, [!!flag]);
    H.useEffect(() => () => { dirtyForms.delete(id.current); }, []);
    return (value = false) => dirtyForms.set(id.current, !!value);
  };
  NL.confirmLeave = () => {
    if (hasUnsavedChanges() && !window.confirm('You have unsaved changes. Leave without saving?')) return false;
    dirtyForms.clear();
    return true;
  };
  let savedRoute = location.hash;
  window.addEventListener('hashchange', e => {
    if (location.hash === savedRoute) return;
    if (NL.confirmLeave()) { savedRoute = location.hash; return; }
    e.stopImmediatePropagation();
    history.replaceState(history.state, '', savedRoute || '#/');
  }, true);
  window.addEventListener('beforeunload', e => {
    if (hasUnsavedChanges()) { e.preventDefault(); e.returnValue = ''; }
  });

  /* ── preferences ───────────────────────────────────────────────────────── */
  const PREF_DEFAULTS = { theme: 'auto', motion: true, labels: false, notify: false, density: 'comfortable',
    cast: { mode: 'backend', one: 'newt', claude: 'newt', codex: 'human', opencode: 'robot' } };   // who plays the agents in the world
  const prefs = Object.assign({}, PREF_DEFAULTS, ls.get('nl-prefs', {}));
  // carry over the old dashboard's choices once
  (() => { const old = ls.get('viv-prefs', null); if (old && !ls.get('nl-prefs', null)) { if (old.ambient === false) prefs.motion = false; }
    try { const lamp = localStorage.getItem('lamp'); if (lamp && !ls.get('nl-prefs', null)) prefs.theme = lamp === 'light' ? 'day' : lamp === 'dark' ? 'night' : 'auto'; } catch (e) { /* ignore */ } })();
  NL.prefs = prefs;
  const prefListeners = new Set();
  NL.setPref = (k, v) => { prefs[k] = v; ls.set('nl-prefs', prefs); NL.applyTheme(); for (const f of prefListeners) f(prefs); };
  NL.usePrefs = () => { useSub(prefListeners); return prefs; };
  NL.themeNow = () => {
    const q = new URLSearchParams(location.search).get('lamp');
    if (q === 'day' || q === 'light') return 'day';
    if (q === 'night' || q === 'dark') return 'night';
    if (prefs.theme === 'day' || prefs.theme === 'night') return prefs.theme;
    return window.matchMedia && matchMedia('(prefers-color-scheme: light)').matches ? 'day' : 'night';
  };
  NL.applyTheme = () => {
    document.documentElement.dataset.lamp = NL.themeNow();
    document.documentElement.dataset.density = prefs.density;
  };
  if (window.matchMedia) matchMedia('(prefers-color-scheme: light)').addEventListener?.('change', () => {
    if(prefs.theme==='auto'){NL.applyTheme();for(const f of prefListeners)f(prefs)}
  });

  /* ── toasts ────────────────────────────────────────────────────────────── */
  const toasts = { list: [], listeners: new Set(), n: 0 };
  NL.toast = (msg, tone) => {
    if (!msg) return;
    const t = { id: ++toasts.n, msg: String(msg), tone: tone || 'info' };
    toasts.list = [...toasts.list.slice(-3), t];
    toasts.listeners.forEach(f => f());
    setTimeout(() => { toasts.list = toasts.list.filter(x => x !== t); toasts.listeners.forEach(f => f()); }, tone === 'bad' ? 7000 : 4200);
  };
  NL.useToasts = () => { useSub(toasts.listeners); return toasts.list; };

  /* ── layers: sheets and dialogs, stacked; Escape closes the top one ──────
     NL.open(Component, props) → id · NL.close(id) · NL.confirm({...}) → Promise<boolean|string>
     A dialog opened from a sheet sits ABOVE it and never closes it. */
  const layers = { list: [], listeners: new Set(), n: 0 };
  const bump = () => layers.listeners.forEach(f => f());
  NL.open = (Comp, props, opts) => {
    const key = opts && opts.key;
    const hit=layers.list.find(l=>key&&l.key===key||opts?.slot&&l.slot===opts.slot);
    if(hit){hit.Comp=Comp;hit.key=key;hit.props=props||{};bump();return hit.id}
    const id = ++layers.n;
    layers.list = [...layers.list, { id, Comp, props: props || {}, key, slot:opts?.slot,opener: document.activeElement, kind: (opts && opts.kind) || 'sheet' }];
    bump();
    return id;
  };
  NL.close = id => { const l = layers.list.find(x => x.id === id); layers.list = layers.list.filter(x => x.id !== id); if (l && l.props && l.props.onClose) l.props.onClose(); bump(); };
  NL.closeTop = () => { const top = layers.list[layers.list.length - 1]; if (top) { NL.close(top.id); return true; } return false; };
  NL.isOpen = key => layers.list.some(l => l.key === key);
  // going to another page closes its side sheets (a dialog waiting for an answer stays)
  NL.closeSheets = () => { layers.list.filter(l => l.kind === 'sheet').forEach(l => NL.close(l.id)); };
  NL.useLayers = () => { useSub(layers.listeners); return layers.list; };
  NL.confirm = (o) => new Promise(resolve => {
    let done = false;
    const id = NL.open(NL.ConfirmDialog, { ...o, resolve: v => { if (done) return; done = true; NL.close(id); resolve(v); }, onClose: () => { if (!done) { done = true; resolve(false); } } }, { kind: 'dialog' });
  });
  window.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const t = e.target && e.target.tagName;
    if ((t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT') && e.target.value && !e.target.dataset.escClose) { e.target.blur(); return; }
    if (NL.closeTop()) e.preventDefault();
  });

  /* ── lab accessors ─────────────────────────────────────────────────────── */
  NL.item = (s, id) => ((s && s.items) || []).find(i => i.id === id);
  NL.exec = s => (s && s.executor) || {};
  NL.execOn = s => { const x = NL.exec(s); return !!(x.available !== false && x.enabled); };
  NL.runs = (s, pred) => ((s && s.runs) || []).filter(pred || (() => true));
  NL.run = (s, id) => ((s && s.runs) || []).find(r => r.run_id === id);
  NL.agentTitle = (a, s = NL.getState() || {}) => {
    if (a.parent || a.is_subagent) return a.label || a.description || NL.roleOf(a.role).label;
    const r = NL.run(s, a.run_id);
    return r ? NL.runTitle(r, s) : NL.PROC[a.skill || a.role]?.title || a.label || NL.roleOf(a.role).label;
  };
  NL.displayAgents = s => (s.agents || []).map(a => ({ ...a, display_label: NL.agentTitle(a,s) }));
  NL.attSubject = (a, s = NL.getState() || {}) => {
    const r = NL.run(s, a.run_id), id = a.idea || a.detail?.study || r?.subject || r?.explains?.study;
    return id && id !== 'hub' ? NL.item(s, id)?.title || id : 'Lab';
  };
  NL.workRuns = s => {
    const waiting = new Set(NL.needsYou(s).map(a => a.run_id).filter(Boolean));
    return NL.runs(s, r => (NL.RUN_ACTIVE.has(r.status) || r.status === 'queued' || r.status === 'waiting_input') && !(NL.runWaiting(r) && waiting.has(r.run_id)));
  };
  NL.runsOf = (s, slug) => NL.runs(s, r => r.target === slug || r.subject === slug || r.explains?.study === slug);
  /** an activity of the tracer's vocabulary → [sign, words] (the world's, so the two read alike) */
  NL.activity = kind => ArloAgents.activities[kind] || ['•','working'];
  NL.workersOf = (s, slug) => ((s && s.workers) || []).filter(w => w.project === slug || w.idea === slug);
  NL.needsYou = s => ((s && s.attention) || []).filter(a => a.sev !== 'info');
  NL.agentReady = s => NL.backends(s).some(b => b.found && b.logged_in !== false);
  NL.backends = s => { const c = (NL.exec(s).clis) || {}; return ['claude', 'codex', 'opencode', 'acp'].map(b => ({ id: b, ...(c[b] || {}) })); };

  /* ── launching (every "start" button ends here) ────────────────────────── */
  NL.launch = async (body, opts) => {
    const s = NL.getState();
    if (s?.holds?.[body.target]) { NL.toast('This study is on hold. Release it from its study page to start new agents.', 'warn'); return null; }
    if (!NL.execOn(s)) {
      const on = await NL.confirm({ title: 'Let this dashboard start agents?', ok: 'Allow',
        body: 'Agents will run on this computer using your own login. You can turn this off in Settings, under Limits & permissions.' });
      if (!on) return null;
      const r = await NL.api('/api/executor/enable', { enabled: true, confirm: true });
      if (!r.ok) { NL.toast(r.error || 'Could not turn launching on. Check the lab server, then try again.', 'bad'); return null; }
    }
    // a study can have several agents at once — but say who is already at work on it, before another starts
    const busy = body.target && body.target !== 'hub' ? (s.runs || []).filter(x => x.subject === body.target
      && (NL.RUN_ACTIVE.has(x.status) || x.status === 'queued' || x.status === 'waiting_input')) : [];
    if (busy.length && !(opts && opts.quiet)) {
      const it = NL.item(s, body.target);
      const go = await NL.confirm({ title: `Already at work on ${NL.clip((it && it.title) || body.target, 50)}`, ok: 'Start another',
        body: html`<p>${busy.length === 1 ? 'This agent is' : 'These agents are'} working on it now. Another would work on the same files.</p>
          <ul class="busy-list">${busy.map(x => html`<li><button type="button" class="link" onClick=${() => NL.openRun(x.run_id)}>${NL.runTitle(x)}</button>
            <span class="muted small"> · ${x.status === 'waiting_input' ? 'waiting for you' : x.status}${x.started ? ' since ' + NL.hhmm(x.started) : ''}</span></li>`)}</ul>` });
      if (!go) return null;
    }
    const r = await NL.api('/api/run', { confirm: true, ...body });
    if (r && r.ok) {
      NL.toast(`${r.label ? NL.clip(r.label, 50) : 'Run'} queued. It starts in a moment.`, 'ok');
      setTimeout(NL.refresh, 300);
      if (!opts || opts.open !== false) NL.openRun(r.run_id);
      return r;
    }
    NL.toast((r && r.error) || 'Could not start the run. Check the lab server, then try again.', 'bad');
    return null;
  };
  NL.launchCommand = (cmd, fallbackTarget) => {
    const toks = String(cmd || '').trim().split(/\s+/);
    const skill = (toks[0] || '').replace(/^\//, '');
    const s = NL.getState();
    const cfg = ((s && s.skills) || {})[skill];
    if (!cfg) { NL.toast(`"${cmd}" isn't something the dashboard can start`, 'warn'); return; }
    const rest = toks.slice(1);
    if ((NL.PROC[skill] || {}).args === 'campaign') return NL.launch({ skill, args: rest[rest[0] === 'continue' ? 1 : 0] || '' });
    if (cfg.args.startsWith('slug') && rest.length) return NL.launch({ skill, target: rest[0], args: rest.slice(1).join(' ') });
    return NL.launch({ skill, target: cfg.level === 'project' ? (fallbackTarget || 'hub') : 'hub', args: rest.join(' ') });
  };
})();
