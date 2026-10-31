/* ARLOtope — Labs & machines (#/labs): every lab you can open, on this computer and on the machines
   you reach over SSH. Opening a lab elsewhere starts that lab's own dashboard there and tunnels to it;
   the whole UI then works on it unchanged (agents, files and the terminal all run on that machine). */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useRef, cls } = NL;

  const reach = m => !m.reach ? { tone: 'muted', text: 'not checked' } : m.reach.ok ? { tone: 'ok', text: 'reachable' }
    : m.reach.kind === 'auth' ? { tone: 'warn', text: 'needs sign-in' } : m.reach.kind === 'hostkey' ? { tone: 'warn', text: 'host key not trusted' }
    : { tone: 'bad', text: 'unreachable' };
  const STATE = { idle: ['muted', 'not connected'], starting: ['live', 'starting…'], waiting: ['ask', 'waiting for your sign-in'],
    connected: ['ok', 'connected'], reconnecting: ['warn', 'reconnecting…'], error: ['bad', 'error'], auth: ['warn', 'needs sign-in'] };

  /* ── every lab at once: GET /api/fleet, polled while a page shows it (shared by the top bar) ─────── */
  const fleet = { data: null, t: null, subs: new Set(), at: 0, pending: null };
  const pull = () => { if (NL.DEMO) return; if (fleet.pending) return fleet.pending;
    fleet.pending = NL.get('/api/fleet').then(x => { if (x.ok) { fleet.data = x; fleet.at = Date.now(); }
      else fleet.data = { ...fleet.data, error: x.error || 'Could not read machine summaries.' };
      fleet.subs.forEach(f => f(fleet.data)); }).finally(() => { fleet.pending = null; }); return fleet.pending; };
  /* demo mode: the synthetic fleet (NL.demoFleet, demo.js) in /api/fleet's shape — never the real labs */
  const slug = x => String(x || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  let demoFl = null;
  const demoFleet = () => {
    if (demoFl) return demoFl;
    const src = NL.demoFleet || { labs: [] };
    const labs = (src.labs || []).map(l => ({ ...l, path: l.path || (l.kind === 'remote' ? '~/labs/' : 'C:/demo/labs/') + slug(l.name),
      machine_id: l.machine_id || (l.kind === 'remote' ? slug(l.machine) : null),
      keep_connected: l.keep_connected != null ? l.keep_connected : l.kind === 'remote' && l.state === 'connected' }));
    const sum = (xs, k) => xs.reduce((a, l) => a + (+((l.summary || {})[k]) || 0), 0);
    demoFl = { ...src, labs, needs_elsewhere: sum(labs.filter(l => !l.current), 'needs'), needs_total: sum(labs, 'needs'), running_total: sum(labs, 'running') };
    return demoFl;
  };
  // what GET /api/labs and /api/machines would say, built from the demo fleet
  const demoLabs = () => { const fl = demoFleet(), here = fl.labs.find(l => l.current) || {};
    return { current: here.path, labs: fl.labs.filter(l => l.kind === 'local').map((l, i) => ({ name: l.name, path: l.path, current: !!l.current, exists: true,
      ideas: l.current ? (NL.getState()?.items || []).length : 4, opened: new Date(Date.now() - (i + 1) * 26 * 3600e3).toISOString() })) }; };
  const demoMachines = () => { const by = {};
    demoFleet().labs.filter(l => l.kind === 'remote').forEach(l => {
      const m = by[l.machine_id] = by[l.machine_id] || { id: l.machine_id, name: l.machine, host: `you@${l.machine}.example.org`, reach: { ok: true }, labs: [],
        facts: { os: 'Linux', arch: 'x86_64', cpus: l.machine === 'gpu-cluster' ? 64 : 16, gpus: l.machine === 'gpu-cluster' ? ['GPU 0: NVIDIA A100 80GB', 'GPU 1: NVIDIA A100 80GB', 'GPU 2: NVIDIA A100 80GB', 'GPU 3: NVIDIA A100 80GB'] : [],
          scheduler: l.machine === 'gpu-cluster' ? 'slurm' : null, partitions: l.machine === 'gpu-cluster' ? [{ name: 'gpu' }, { name: 'cpu' }] : [], tools: { uv: true, git: true, claude: true, codex: l.machine !== 'lab-pc', opencode: false } } };
      m.labs.push({ path: l.path, lab_name: l.name, state: l.state, exists: true, keep_connected: !!l.keep_connected });
    });
    return { machines: Object.values(by), suggestions: [] }; };

  NL.useFleet = () => {
    const [d, setD] = useState(NL.DEMO ? null : fleet.data);
    useEffect(() => {
      if (NL.DEMO) return undefined;
      fleet.subs.add(setD);
      if (!fleet.t) { pull(); fleet.t = setInterval(() => { if (!document.hidden) pull(); }, 15000); }
      else if (Date.now() - fleet.at > 15000) pull();
      return () => { fleet.subs.delete(setD); if (!fleet.subs.size && fleet.t) { clearInterval(fleet.t); fleet.t = null; } };
    }, []);
    return NL.DEMO ? demoFleet() : d;
  };
  NL.refreshFleet = () => NL.DEMO ? null : pull();

  /* go to a lab (and optionally straight to one thing in it) */
  NL.goToLab = async (l, then) => {
    if (l.current) { if (then) location.hash = then; else NL.go(''); return; }
    const r = l.kind === 'local' ? await NL.act('/api/labs/open', { path: l.path }, 'Opened')
      : await NL.api('/api/machines/open', { id: l.machine_id, path: l.path });
    if (l.kind === 'remote' && !(r.ok && r.state === 'connected')) { NL.toast(r.error || r.note || 'Could not connect. Open it from its machine below.', r.ok ? 'info' : 'bad'); return; }
    if (r.ok) { location.hash = then || '#/'; setTimeout(() => location.reload(), 250); }
  };
  const itemHash = it => it.kind === 'checkpoint' && it.idea ? `#/study/${it.idea}?checkpoint=${(it.detail || {}).checkpoint}` : it.run_id ? `#/runs?run=${it.run_id}`
    : (it.detail || {}).campaign ? `#/studies?campaign=${encodeURIComponent(it.detail.campaign)}` : it.idea ? `#/study/${it.idea}` : '#/';

  /* what a lab needs and runs, from the fleet summary — shown on that lab's own row */
  const fleetLab = (fl, kind, path, machine) => ((fl && fl.labs) || []).find(l => l.kind === kind && l.path === path && (kind === 'local' || l.machine_id === machine));
  function LabStatus({ l }) {
    if (!l || !l.summary) return null;
    const sm = l.summary;
    return html`<div class="small row gap wrap">${sm.needs ? html`<span class="warn"><b>${sm.needs}</b> need you</span>` : null}
        ${sm.running || sm.queued || sm.waiting ? html`<span>${sm.running || 0} running${sm.queued ? ` · ${sm.queued} queued` : ''}${sm.waiting ? ` · ${sm.waiting} waiting` : ''}</span>` : null}
        ${(sm.campaigns || []).map(c => html`<span class="chip">⟳ ${NL.clip(c.name.replace(/^\d{4}-\d{2}-\d{2}-/, ''), 22)} · ${c.status}</span>`)}
        ${l.kind === 'remote' && l.summary_age > 60 ? html`<span class="muted">as of ${Math.round(l.summary_age / 60)} min ago</span>` : null}</div>
      ${(sm.top || []).length ? html`<div class="fleet-items">${sm.top.slice(0, 3).map(it => html`<button type="button" class="link small" onClick=${() => NL.goToLab(l, itemHash(it))}>› ${NL.clip(it.title || it.kind, 80)}</button>`)}</div>` : null}`;
  }

  function Facts({ f }) {
    if (!f) return null;
    const t = f.tools || {};
    const tool = k => html`<span class=${cls('fact-tool', t[k] ? 'on' : 'off')}>${t[k] ? '✓' : '–'} ${k}</span>`;
    const gpus = (f.gpus || []).length;
    return html`<div class="facts-line">
      <span>${f.os || '?'} ${f.arch || ''}</span>${f.cpus ? html`<span>${f.cpus} CPUs</span>` : null}
      <span>${gpus ? `${gpus} GPU${gpus > 1 ? 's' : ''}${f.gpus[0] ? ' · ' + NL.clip(f.gpus[0].replace(/^GPU \d+: /, '').replace(/\s*\(UUID.*$/, ''), 34) : ''}` : 'no GPU found'}</span>
      <span>${f.scheduler ? `${f.scheduler.toUpperCase()}${(f.partitions || []).length ? ' · ' + f.partitions.slice(0, 4).map(p => p.name).join(', ') : ''}` : 'no scheduler'}</span>
      <span class="row-wrap">${['uv', 'git', 'claude', 'codex', 'opencode'].map(tool)}</span></div>`;
  }

  function RemoteLab({ m, lab, reload, fl }) {
    const [busy, setBusy] = useState(false);
    const [pollError, setPollError] = useState('');
    const [pollAttempt, setPollAttempt] = useState(0);
    const waitingRead = useRef(0);
    const st = STATE[lab.state] || STATE.idle;
    const open = async (interactive) => {
      setBusy(true);
      const r = await NL.api('/api/machines/open', { id: m.id, path: lab.path, interactive });
      setBusy(false);
      if (r.ok && r.state === 'connected') { NL.toast(`Opened ${r.name || lab.path} on ${m.name}`, 'ok'); NL.go(''); setTimeout(() => location.reload(), 250); return; }
      if (r.ok && r.state === 'waiting') { NL.toast(r.note, 'info'); reload(); return; }
      if (r.needs_interactive) {
        if (await NL.confirm({ title: `${m.name} needs you to sign in`, ok: 'Open a terminal to sign in',
          body: html`<p>It needs you at the keyboard (a password, a verification code, or a new host key to accept), so the connection runs in a terminal window on this computer. Sign in there and leave the window open; this page connects by itself.</p>` }))
          return open(true);
        return;
      }
      NL.toast(r.error || 'Could not connect.', 'bad'); reload();
    };
    // an interactive connect: poll until it's up, then switch to it
    useEffect(() => {
      setPollError('');
      if (lab.state !== 'waiting') return undefined;
      let active = true, timer;
      const token = ++waitingRead.current;
      const current = () => active && token === waitingRead.current;
      const poll = async () => {
        const x = await NL.get('/api/machines');
        if (!current()) return;
        if (x.error) { setPollError(x.error + ' Connection checks retry automatically.'); timer = setTimeout(poll, 2500); return; }
        setPollError('');
        const l2 = ((x.machines || []).find(y => y.id === m.id) || { labs: [] }).labs.find(y => y.path === lab.path);
        if (l2 && l2.state === 'connected') {
          const u = await NL.api('/api/machines/use', { id: m.id, path: lab.path });
          if (!current()) return;
          if (u.ok) { NL.go(''); location.reload(); }
          else { NL.toast(u.error || 'Could not open this lab.', 'bad'); reload(); }
        } else if (l2 && l2.state !== 'waiting') reload();
        else timer = setTimeout(poll, 2500);
      };
      timer = setTimeout(poll, 2500);
      return () => { active = false; clearTimeout(timer); };
    }, [lab.state, lab.path, m.id, pollAttempt]);
    return html`<div class="labrow">
      <div class="grow"><b>${lab.lab_name || lab.name || lab.path.split('/').filter(Boolean).pop()}</b> <${NL.Pill} tone=${st[0]}>${st[1]}</${NL.Pill}>
        ${lab.exists === false ? html` <${NL.Pill} tone="warn">no lab there yet</${NL.Pill}>` : null}
        <div class="mono small muted">${lab.path}</div>${lab.error ? html`<div class="small warn">${lab.error}</div>` : null}
        ${pollError ? html`<div class="small warn" role="alert">${pollError} ${lab.state === 'waiting' ? html`<button class="link small" onClick=${()=>setPollAttempt(n=>n+1)}>Retry</button>` : null}</div>` : null}
        <${LabStatus} l=${fleetLab(fl, 'remote', lab.path, m.id)} />
        <div class="small muted keep-why">${lab.keep_connected ? 'Kept connected: activity and requests refresh on this page every 15 s.'
          : 'Keep connected to refresh this lab’s activity here while another lab is open.'}</div></div>
      <div class="row">${lab.state === 'waiting' ? html`<${NL.Spinner} /><span class="small muted">sign in in the terminal window…</span>` : html`<${NL.Btn} small kind="primary" busy=${busy} onClick=${() => open(false)}>Switch to this lab</${NL.Btn}>`}
        ${['connected', 'reconnecting', 'waiting', 'error'].includes(lab.state) ? html`<button class="link small" disabled=${busy} onClick=${async () => { setBusy(true); ++waitingRead.current; const r = await NL.api('/api/machines/disconnect', { id: m.id, path: lab.path }); setBusy(false); if (!r.ok) { setPollError(r.error || 'Could not disconnect.'); return; } if (r.was_current) { NL.go('labs'); location.reload(); } else reload(); }}>Disconnect</button>` : null}
        <label class="small keep keep-vis" title="Keep this lab’s activity and requests updated on this page"><input type="checkbox" checked=${!!lab.keep_connected}
          onChange=${async e => { await NL.act('/api/fleet/keep', { id: m.id, path: lab.path, keep: e.target.checked }); reload(); NL.refreshFleet(); }} /> keep connected</label></div></div>`;
  }

  function MachineCard({ m, reload, fl }) {
    const [path, setPath] = useState('');
    const [newName, setNewName] = useState('');
    const [newPath, setNewPath] = useState('~/labs/');
    const [mode, setMode] = useState(null);
    const status=STATE[m.worker?.state],r=status?{tone:status[0],text:status[1]}:reach(m);
    const probe = async () => { const x = await NL.api('/api/machines/probe', { id: m.id }); NL.toast(x.ok ? 'Checked' : (x.error || 'unreachable'), x.ok ? 'ok' : 'warn'); reload(); };
    const addLab = NL.useSubmit(async () => { const x = await NL.act('/api/machines/add-lab', { id: m.id, path: path.trim() }); if (x.ok) { setPath(''); setMode(null); reload(); } });
    const create = async () => {
      if (!newName.trim() || !newPath.trim()) return NL.toast('A name and a folder', 'warn');
      if (!await NL.confirm({ title: `Create “${newName.trim()}” on ${m.name}?`, ok: 'Create it', body: html`<p>Copies this template's committed files to <span class="mono">${newPath.trim()}</span> on ${m.name} over SSH, then sets it up as an empty lab (it needs <span class="mono">python3</span> and <span class="mono">git</span> there).</p>` })) return;
      const x = await NL.act('/api/machines/create-lab', { id: m.id, path: newPath.trim(), name: newName.trim(), confirm: true });
      if (x.ok) { setMode(null); reload(); }
    };
    return html`<section class="machine">
      <header class="machine-head"><div class="grow"><h3>${m.name}</h3>${m.name!==m.host?html`<span class="mono small muted">${m.host}</span>`:null} <${NL.Pill} tone=${r.tone}>${r.text}</${NL.Pill}>
        ${m.reach && !m.reach.ok ? html`<div class="small muted">${m.reach.error}</div>` : null}</div>
      <div class="row"><${NL.Btn} small onClick=${()=>NL.openMachineSetup(m.id,{autoConnect:true})}>${m.worker?.state==='connected'?'Projects':'Connect'}</${NL.Btn}><button class="link small" onClick=${probe}>Check again</button>
          ${m.facts && !(m.facts.tools || {}).uv ? html`<${NL.Btn} small onClick=${() => NL.act('/api/machines/install-uv', { id: m.id }, 'Installing uv in a terminal window')}>Install uv…</${NL.Btn}>` : null}
          <button class="link small danger" onClick=${async () => { if (await NL.confirm({ title: `Forget ${m.name}?`, body: 'Removes it from this list. Nothing on that machine changes.', ok: 'Forget', danger: true })) { await NL.api('/api/machines/remove', { id: m.id }); reload(); } }}>Forget</button></div></header>
      <${Facts} f=${m.facts} />
      ${(m.labs || []).map(l => html`<${RemoteLab} key=${l.path} m=${m} lab=${l} reload=${reload} fl=${fl} />`)}
      <details><summary>Separate Labs</summary><div class="row">${mode === 'add' ? html`<${NL.Input} value=${path} onInput=${setPath} placeholder="the lab's folder on that machine, e.g. ~/my-lab" mono onEnter=${addLab} /><${NL.Btn} small onClick=${addLab}>Add</${NL.Btn}><button class="link small" onClick=${() => setMode(null)}>cancel</button>`
        : mode === 'create' ? html`<${NL.Input} value=${newName} onInput=${setNewName} placeholder="lab name" /><${NL.Input} value=${newPath} onInput=${setNewPath} mono /><${NL.Btn} small kind="primary" onClick=${create}>Create</${NL.Btn}><button class="link small" onClick=${() => setMode(null)}>cancel</button>`
        : html`<${NL.Btn} small onClick=${() => setMode('add')}>Add a lab folder</${NL.Btn}><${NL.Btn} small onClick=${() => setMode('create')}>Create a lab here</${NL.Btn}>`}</div></details>
    </section>`;
  }

  function AddMachine({ suggestions, reload, onAdded }) {
    const listId=useRef('nl-ssh-'+Math.random().toString(36).slice(2)).current;
    const [host, setHost] = useState('');
    const [name, setName] = useState('');
    const [busy, setBusy] = useState(false);
    const add = NL.useSubmit(async () => {
      if (!host.trim()) return;
      const x = await NL.api('/api/machines/add', { host: host.trim(), name: name.trim() || host.trim(), probe:false });
      if (!x.ok) return NL.toast(x.error, 'bad');
      setHost(''); setName(''); reload?.();
      if(onAdded)onAdded(x.machine);else NL.openMachineSetup(x.machine.id,{autoConnect:true});
    }, setBusy);
    return html`<${NL.Section} title="Add a machine"><div class="form">
      <${NL.Field} label="SSH host"><input class="input mono" list=${listId} value=${host} onInput=${e => setHost(e.target.value)} onKeyDown=${e=>e.key==='Enter'&&add()} placeholder="SSH alias or user@host" />
          <datalist id=${listId}>${(suggestions || []).map(h => html`<option value=${h} />`)}</datalist></${NL.Field}>
      <details><summary>Display name</summary><${NL.Field} label="Name"><${NL.Input} value=${name} onInput=${setName} placeholder=${host || 'GPU box'} onEnter=${add} /></${NL.Field}></details>
      <p class="muted small">Uses your SSH settings. Adds a small runner in ~/.arlotope.</p>
      <div class="row end"><${NL.Btn} kind="primary" busy=${busy} disabled=${!host.trim()} onClick=${add}>Connect</${NL.Btn}></div></div></${NL.Section}>`;
  }

  /* this computer's labs (open / create / switch) */
  function LocalLabs({ d, reload, fl }) {
    const [path, setPath] = useState('');
    const [nm, setNm] = useState('');
    const [where, setWhere] = useState('');
    useEffect(() => { if (d && d.current && !where) setWhere(d.current.replace(/[\\/][^\\/]+$/, '')); }, [d]);
    const s = NL.getState() || {};
    const slug = (nm || 'my-lab').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'my-lab';
    const sep = (where || '').includes('\\') ? '\\' : '/';
    const dest = where ? where.replace(/[\\/]$/, '') + sep + slug : '';
    const open = async p => { const r = await NL.act('/api/labs/open', { path: p }, 'Opened'); if (r.ok) { NL.go(''); setTimeout(() => location.reload(), 300); } };
    const create = async () => {
      if (!nm.trim() || !dest) return NL.toast('Give the lab a name and a place', 'warn');
      if (!await NL.confirm({ title: `Create “${nm.trim()}”?`, ok: 'Create the lab', body: html`<p>A new, empty lab at <span class="mono">${dest}</span>: this template's procedures and tools, an empty registry and knowledge base, its own git repository. Its projects will live next to it in <span class="mono">${slug}-projects</span>.</p>` })) return;
      const r = await NL.act('/api/labs/create', { confirm: true, name: nm.trim(), path: dest, open: true }, 'Lab created');
      if (r.ok) { NL.go('setup'); setTimeout(() => location.reload(), 300); }
    };
    const row=l=>html`<div class=${cls('labrow', l.current && !s.remote && 'on', !l.exists && 'gone')}>
        <div class="grow"><b>${l.name}</b>${l.current && !s.remote ? html` <${NL.Pill} tone="ok">open</${NL.Pill}>` : null}<div class="mono small muted">${l.path}</div>
          ${l.exists ? html`<div class="small muted">${l.ideas ? NL.plural(l.ideas, 'study', 'studies') : 'no studies yet'}${l.opened ? ' · opened ' + NL.when(l.opened) : ''}</div>` : html`<div class="small warn">folder not found</div>`}
          <${LabStatus} l=${fleetLab(fl, 'local', l.path)} /></div>
        <div class="row">${l.current && !s.remote ? html`<span class="muted small">You are in this lab</span>` : l.exists ? html`<${NL.Btn} small kind="primary" onClick=${() => open(l.path)}>Switch to this lab</${NL.Btn}>` : null}
          ${!l.current ? html`<button class="link small" onClick=${async () => { await NL.api('/api/labs/forget', { path: l.path }); reload(); }}>Forget</button>` : null}</div></div>`;
    return html`<section class="machine machine-local">
      <header class="machine-head"><div class="grow"><h3>This computer</h3></div></header>
      ${!d?html`<${NL.Spinner}/>`:(d.labs||[]).filter(l=>l.current).map(row)}
      ${d?.labs?.some(l=>!l.current)?html`<details><summary>Other Labs</summary>${d.labs.filter(l=>!l.current).map(row)}</details>`:null}
      <details class="more"><summary>Create or open another lab on this computer</summary><div class="form">
        <div class="grid2"><${NL.Field} label="New lab name"><${NL.Input} value=${nm} onInput=${setNm} placeholder="e.g. Sparse models lab" /></${NL.Field}>
          <${NL.Field} label="Inside this folder"><${NL.Input} value=${where} onInput=${setWhere} mono /></${NL.Field}></div>
        ${dest ? html`<div class="muted small">It will be created at <span class="mono">${dest}</span></div>` : null}
        <div class="row end"><${NL.Btn} kind="primary" onClick=${create}>Create the lab</${NL.Btn}></div>
        <div class="row"><${NL.Input} value=${path} onInput=${setPath} placeholder="or open an existing lab folder (it contains lab/config.yaml)" mono onEnter=${() => open(path)} />
          <${NL.Btn} onClick=${() => open(path)} disabled=${!path.trim()}>Open</${NL.Btn}></div></div></details></section>`;
  }

  NL.LabsPage = () => {
    const localRead=NL.usePoll(NL.DEMO?null:'/api/labs',8000);
    const machineRead=NL.usePoll(NL.DEMO?null:'/api/machines',8000);
    const local=NL.DEMO?demoLabs():localRead.data||localRead.previous;
    const mach=NL.DEMO?demoMachines():machineRead.data||machineRead.previous;
    const error=[localRead.error,machineRead.error].filter(Boolean).join(' · ');
    const s = NL.useLab();
    const load=()=>{localRead.reload();machineRead.reload()};
    const cur = s.remote;
    const fl = NL.useFleet();
    return html`<div class="page page-narrow">
      <header class="page-head"><div><h1>Machines</h1></div></header>
      ${error ? html`<p class="note note-warn" role="alert">${error} <button type="button" class="link" onClick=${load}>Retry</button></p>` : null}
      ${fl?.error ? html`<${NL.LoadState} error=${fl.error} reload=${NL.refreshFleet} stale=${!!fl.labs} />` : null}
      ${cur ? html`<div class="note">Showing <b>${cur.lab_name || cur.lab}</b> on <b>${cur.name}</b> (${cur.host}). <button class="link" onClick=${async () => { await NL.api('/api/machines/local', {}); NL.go(''); location.reload(); }}>Back to this computer</button></div>` : null}
      ${fl && (fl.labs || []).length > 1 ? (() => {
        const sum = (xs, k) => xs.reduce((a, l) => a + (+((l.summary || {})[k]) || 0), 0);
        const here = fl.labs.filter(l => l.current && Object.keys(l.summary || {}).length), others = fl.labs.filter(l => !l.current);
        const line = xs => { const n = sum(xs, 'needs'), r = sum(xs, 'running');
          return html`${n ? html`<b class="warn">${n} ${n === 1 ? 'thing needs' : 'things need'} you</b>` : 'nothing needs you'} · ${NL.plural(r, 'run')} working`; };
        return html`<div class="muted labs-summary">${here.length ? html`<p>This lab: ${line(here)}</p>` : null}
          <p>Other labs: ${line(others)}</p></div>`;
      })() : null}
      ${NL.DEMO ? html`<div class="note small">Demo: these labs and machines are made up. Nothing connects.</div>` : null}
      <${LocalLabs} d=${local} reload=${load} fl=${fl} />
      ${mach ? (mach.machines || []).map(m => html`<${MachineCard} key=${m.id} m=${m} reload=${load} fl=${fl} />`) : html`<${NL.Spinner} />`}
      <${AddMachine} suggestions=${mach && mach.suggestions} reload=${load} />
    </div>`;
  };
  NL.FolderPicker=({machine='',initial,onPick,onClose,title='Choose a folder'})=>{
    const [data,setData]=useState(null),[path,setPath]=useState(initial||'~'),[error,setError]=useState(''),[busy,setBusy]=useState(false),[hidden,setHidden]=useState(false);
    const request=useRef(0),mounted=useRef(true);
    useEffect(()=>()=>{mounted.current=false},[]);
    const load=async (next,show=hidden)=>{const version=++request.current;setBusy(true);setError('');
      try{const r=await NL.api('/api/project-machines/browse',{machine,path:next,hidden:show});if(!mounted.current||version!==request.current)return;
        if(r.error)setError(r.error);else{setData(r);setPath(r.path)}}finally{if(mounted.current&&version===request.current)setBusy(false)}};
    useEffect(()=>{load(initial||'~')},[machine]);
    return html`<${NL.Sheet} title=${title} onClose=${onClose} footer=${html`<div class="row end"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!data||busy||!!error||path!==data.path} onClick=${()=>{onPick(data.path);onClose()}}>Use this folder</${NL.Btn}></div>`}>
      <div class="folder-tools row"><${NL.Btn} small disabled=${busy} onClick=${()=>load('~')}>Home</${NL.Btn}><${NL.Btn} small disabled=${busy||!data?.parent} onClick=${()=>load(data.parent)}>Up</${NL.Btn}>
        ${(data?.drives||[]).map(d=>html`<${NL.Btn} small disabled=${busy} onClick=${()=>load(d)}>${d}</${NL.Btn}>`)}</div>
      <div class="row folder-path"><${NL.Input} ariaLabel="Folder path" value=${path} onInput=${setPath} disabled=${busy} mono onEnter=${()=>load(path)}/><${NL.Btn} small busy=${busy} onClick=${()=>load(path)}>Go</${NL.Btn}></div>
      ${error?html`<p class="note note-warn" role="alert">${error}${machine?html` <button type="button" class="link" onClick=${()=>NL.openMachineSetup(machine,{onConnected:()=>load(path)})}>Connect</button>`:null}</p>`:null}
      <div class="folder-list" aria-busy=${busy}>${data?.folders.map(f=>html`<button type="button" class="folder-entry" disabled=${busy} onClick=${()=>load(f.path)}><span>${f.name}</span><span aria-hidden="true">→</span></button>`)}${data&&!data.folders.length?html`<p class="muted small">No subfolders.</p>`:null}</div>
      ${data?.truncated?html`<p class="muted small">Showing the first 1,000 folders. Use the path field to open another.</p>`:null}
      <label class="small"><input type="checkbox" checked=${hidden} onChange=${e=>{setHidden(e.target.checked);load(data?.path||path,e.target.checked)}}/> Show hidden folders</label>
    </${NL.Sheet}>`;
  };
  NL.pickFolder=options=>NL.open(NL.FolderPicker,options,{key:'folder-picker'});
  const ProjectBrowser=({machine='',onClose,initial,onProject})=>{
    const s=NL.useLab(),[root,setRoot]=useState('~'),[rows,setRows]=useState(initial||[]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
    const load=async folder=>{setBusy(true);try{const x=await NL.api('/api/project-machines/projects',{machine,root:folder||undefined});if(x.error)setError(x.error);else{setRows(x.projects||[]);setError('')}}finally{setBusy(false)}};
    useEffect(()=>{if(!initial)load()},[machine]);
    const pick=p=>{const existing=(s.items||[]).find(i=>i.id===p.study&&p.ours);if(existing){onClose();NL.go('study/'+existing.id);return}
      if(onProject){onProject({...p,machine});onClose();return}
      const key='nl-study-draft:'+(s.lab_info?.path||location.origin),draft=NL.ls.get(key,{})||{};
      NL.ls.set(key,{...draft,kind:'local',local:p.path,machine:machine==='local'?'':machine,title:draft.title||p.title||'',id:p.ours?p.study||'':''});onClose();NL.go('start')};
    return html`<section class="project-browser"><h3>Projects</h3>${rows.length?rows.map(p=>html`<div class="row between"><div class="grow path-wrap"><b>${p.title||p.path}</b><small class="mono">${p.path}</small>${!p.exists?html`<small>Folder missing</small>`:p.duplicate?html`<small>Duplicate project identity · inspect the copies</small>`:p.registered&&!p.ours?html`<small>Attached to another Lab</small>`:null}</div>
      <${NL.Btn} small disabled=${!p.exists||p.duplicate||p.identity_matches===false||p.registered&&!p.ours} onClick=${()=>pick(p)}>${p.ours&&(s.items||[]).some(i=>i.id===p.study)?'Open study':'Use project'}</${NL.Btn}></div>`):html`<p class="muted small">No registered projects. Browse a folder to find repositories.</p>`}
      <div class="row"><${NL.Input} ariaLabel="Find projects in folder" value=${root} onInput=${setRoot} placeholder="~/research or /project/my-group"/><${NL.Btn} small onClick=${()=>NL.pickFolder({machine,initial:root,title:'Find projects in a folder',onPick:p=>{setRoot(p);load(p)}})}>Browse…</${NL.Btn}><${NL.Btn} small busy=${busy} onClick=${()=>load(root)}>Find projects</${NL.Btn}></div>
      ${error?html`<p role="alert">${error}</p>`:null}</section>`;
  };
  NL.AddMachineSheet=({onClose,onConnected,onProject})=>{
    const [data,setData]=useState(null),[selected,setSelected]=useState(null),[error,setError]=useState('');
    const load=async()=>{const r=await NL.get('/api/machines');if(r.error)setError(r.error);else{setData(r);setError('')}};
    useEffect(()=>{load()},[]);
    if(selected)return html`<${NL.ProjectMachineSetup} id=${selected.id} autoConnect onConnected=${onConnected} onProject=${onProject} onClose=${onClose}/>`;
    return html`<${NL.Sheet} title="Connect a machine" onClose=${onClose}>
      ${error?html`<p class="note note-warn" role="alert">${error} <button type="button" class="link" onClick=${load}>Retry</button></p>`:!data?html`<${NL.Spinner}/>`:null}
      ${(data?.machines||[]).map(m=>html`<button class="search-result" type="button" onClick=${()=>setSelected({id:m.id})}><b>${m.name||m.host}</b><small>${m.host} · ${m.worker?.state==='connected'?'Connected':'Connect'}</small></button>`)}
      <${AddMachine} suggestions=${data?.suggestions} onAdded=${m=>setSelected({id:m.id,auto:true})}/></${NL.Sheet}>`;
  };
  NL.openAddMachine=(onConnected,options={})=>NL.open(NL.AddMachineSheet,{...options,onConnected:typeof onConnected==='function'?onConnected:undefined}, {key:'add-machine'});

  NL.ProjectMachineSetup = ({id,onClose,autoConnect=true,onConnected,onProject}) => {
    const mounted=useRef(true),epoch=useRef(0);
    const current=token=>mounted.current&&token===epoch.current;
    useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;epoch.current++}},[id]);
    const [info,setInfo]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[waiting,setWaiting]=useState(false),
      [agent,setAgent]=useState('claude'),[command,setCommand]=useState(''),[config,setConfig]=useState({}),[remaining,setRemaining]=useState(null);
    const inspect=async(token=epoch.current)=>{setBusy('Checking…');try{
      const r=await NL.api('/api/project-machines/inspect',{id});if(!current(token))return;
      if(r.error)setError(r.error);else{setInfo(r);setConfig(r.agent_config||{});setAgent(r.default_agent||'claude');setError('');onConnected?.(id)}
    }finally{if(current(token))setBusy(false)}};
    useEffect(()=>{const token=epoch.current;if(autoConnect)connect(false);else NL.get('/api/project-machines').then(r=>{
      if(!current(token))return;const m=r?.machines?.find(m=>m.id===id);
      if(r.error)setError(r.error);else if(['auth','error'].includes(m?.state))setError(m.error||'Reconnect when you are ready.');
      else if(['waiting','starting','reconnecting'].includes(m?.state))setWaiting(true);else if(m?.state==='connected')inspect(token);
    })},[id]);
    useEffect(()=>{setCommand(JSON.stringify(config[agent]?.command||[]))},[agent,config]);
    useEffect(()=>{if(!waiting)return;let active=true,t;const token=epoch.current,poll=async()=>{
      const r=await NL.get('/api/project-machines');if(!active||!current(token))return;
      if(r.error){setError(r.error);t=setTimeout(poll,2000);return}
      setError('');const m=r.machines?.find(m=>m.id===id);
      setRemaining(m?.login_deadline?Math.max(0,Math.ceil((m.login_deadline*1000-Date.now())/60000)):null);
      if(m?.state==='connected'){setWaiting(false);await inspect(token);return}
      if(!m||!['waiting','starting','reconnecting'].includes(m.state)){setWaiting(false);setError(m?.error||r?.error||'Connection closed. Try again.');return}
      t=setTimeout(poll,2000)};poll();return()=>{active=false;clearTimeout(t)}},[waiting,id]);
    const connect=async interactive=>{if(!mounted.current)return;const token=++epoch.current;
      setWaiting(false);setInfo(null);setBusy('Connecting…');setError('');try{
        const r=await NL.api('/api/project-machines/connect',{id,confirm:true,interactive});if(!current(token))return;
        if(r.needs_interactive&&!interactive)return await connect(true);
        if(r.error||r.needs_interactive)setError(r.error||'Could not open sign-in. Try again.');
        else if(['waiting','starting','reconnecting'].includes(r.state))setWaiting(true);else await inspect(token);
      }finally{if(current(token))setBusy(false)}};
    const cancel=async()=>{const token=++epoch.current;setWaiting(false);setBusy('Disconnecting…');try{
      const r=await NL.api('/api/project-machines/disconnect',{id});if(!current(token))return false;
      if(r.error){setError(r.error);return false}setError('');setInfo(null);setRemaining(null);NL.refresh();return true;
    }finally{if(current(token))setBusy(false)}};
    const retry=async()=>{if(await cancel())await connect(true)};
    const saveConfig=async next=>{const r=await NL.api('/api/project-machines/inspect',{id,agent_config:next,default_agent:agent});if(r.error)setError(r.error);else{setConfig(next);setInfo(r);setError('')}};
    const save=async()=>{let parsed;try{parsed=JSON.parse(command);if(!Array.isArray(parsed)||!parsed.length)throw Error('Use a JSON argument array.')}catch(e){setError(e.message);return}
      return saveConfig({...config,[agent]:{command:parsed}})};
    return html`<${NL.Sheet} title=${id} onClose=${onClose}>
      ${waiting?html`<p role="status">Finish signing in in the SSH window. Keep it open.</p>${remaining!==null?html`<p class="muted small">Up to ${remaining} min left. Missed the prompt? Open a new one.</p>`:null}<div class="row"><${NL.Btn} busy=${busy} onClick=${retry}>Restart sign-in</${NL.Btn}><${NL.Btn} busy=${busy} onClick=${cancel}>Cancel connection</${NL.Btn}></div>`:!info?html`<p class="muted small" role="status">${busy|| (error?'Your machine is saved. You can retry whenever you are ready.':'Connect over SSH to browse projects.')}</p><${NL.Btn} kind="primary" busy=${busy} onClick=${()=>connect(false)}>${error?'Try again':'Connect'}</${NL.Btn}>`:html`
      <div class="row between"><p class="muted small" role="status">Connected · ${info.platform}</p><${NL.Btn} small busy=${busy} onClick=${cancel}>Disconnect</${NL.Btn}></div>
      <${ProjectBrowser} machine=${id} initial=${info.projects} onClose=${onClose} onProject=${onProject}/>
      <details class="more"><summary>Agents & commands</summary><${NL.Field} label="Agent"><${NL.Select} value=${agent} onChange=${async value=>{setAgent(value);const r=await NL.api('/api/project-machines/inspect',{id,default_agent:value});if(r.error)setError(r.error)}} options=${['claude','codex','opencode','acp']}/></${NL.Field}>
      <div class="row">${info.clis?.[agent]?.found?html`<span>Installed${info.clis[agent].logged_in===true?' · Signed in':''}</span>${agent!=='acp'&&info.clis[agent].logged_in!==true?html`<${NL.Btn} onClick=${()=>NL.open(NL.TerminalSheet,{purpose:'login',backend:agent,machine:id})}>Sign in</${NL.Btn}>`:null}`:agent!=='acp'?html`<${NL.Btn} onClick=${()=>NL.open(NL.TerminalSheet,{purpose:'install',backend:agent,machine:id})}>Install ${agent}</${NL.Btn}>`:null}<${NL.Btn} busy=${busy} onClick=${()=>inspect()}>Check again</${NL.Btn}></div>
      ${agent==='acp'?html`<p class="muted small">Use this agent’s own login command on the machine.</p>`:null}
      <details><summary>Custom command</summary><${NL.Field} label="Command arguments" hint="JSON array. Use an existing executable or wrapper for a specific environment."><${NL.Input} value=${command} onInput=${setCommand} mono placeholder='["/path/to/agent", "--acp"]'/></${NL.Field}><div class="row"><${NL.Btn} onClick=${save}>Save command</${NL.Btn}>${config[agent]?.command?html`<${NL.Btn} onClick=${()=>{const next={...config};delete next[agent];return saveConfig(next)}}>Use default command</${NL.Btn}>`:null}</div></details></details>
      ${info.labs?.length?html`<p><a href="#/labs" onClick=${onClose}>Open connected labs →</a></p>`:null}`}
      ${error?html`<p role="alert" class="note">${error}</p>${info?html`<${NL.Btn} busy=${busy} onClick=${()=>{setInfo(null);connect(false)}}>Reconnect</${NL.Btn}>`:null}`:null}<div class="row end"><${NL.Btn} onClick=${onClose}>Done</${NL.Btn}></div></${NL.Sheet}>`;
  };
  NL.openMachineSetup=(id,options={})=>NL.open(NL.ProjectMachineSetup,{id,...options},{key:'machine-setup:'+id});
  NL.MachinePicker=({value,onChange,onProject})=>{
    const read=NL.usePoll('/api/project-machines',4000),data=read.data||read.previous,error=read.error,load=read.reload;
    return html`<div><${NL.Field} label="Project machine"><${NL.Select} value=${value} onChange=${onChange} options=${[{value:'',label:'This computer'},...(data?.machines||[]).map(m=>({value:m.id,label:m.name})),...(value&&!(data?.machines||[]).some(m=>m.id===value)?[{value,label:value+' · unavailable'}]:[])]}/></${NL.Field}>
      ${error?html`<p class="note note-warn" role="alert">${error} <button type="button" class="link" onClick=${load}>Retry</button></p>`:null}
      <div class="row">${value?html`<button type="button" class="link" onClick=${()=>NL.openMachineSetup(value,{onProject})}>Browse projects</button>`:null}
      <button type="button" class="link" onClick=${()=>NL.openAddMachine(async id=>{await load();onChange(id)},{onProject})}>Connect a machine…</button></div></div>`;
  };
})();
