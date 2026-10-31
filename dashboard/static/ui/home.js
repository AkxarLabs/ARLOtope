/* Research overview, attention inbox and history. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, cls } = NL;

  /* ── the inbox: one list, typed actions ─────────────────────────────────── */
  const ICON = { followup: '↻', flag: '⚑', outcome: '⑂', question: '?', assumed: '≈', needs_pi: '✋', checkpoint: '◆', slipped: '◆', alert: '▲', permission: '🔐', denied: '⊘', crashed: '✕', report: '✓', escalation: '⚠', stalled: '◴', subagent: '◌', brake: '⏸', scheduler: '⚠', proposal: '✎', campaign: '⟳', artifact: '❏' };
  const PRIMARY = new Set(['answer', 'resume', 'checkpoint', 'allow', 'next', 'proposal', 'artifact', 'panel', 'move']);
  /** open what an attention item is about: its checkpoint, its panel, its run, its campaign, its study */
  NL.attOpen = it => {
    const d = it.detail || {};
    if (d.checkpoint && (d.study || it.idea)) return NL.openCheckpoint(d.study || it.idea, d.checkpoint);
    if (it.kind === 'alert' && d.panel) return NL.openPanel(d.panel, d.study || null);
    if (it.kind === 'artifact') return NL.openArtifact(d.artifact);
    if (d.campaign) return NL.openCampaign(d.campaign);
    if (it.kind === 'proposal') return NL.open(NL.ProposalSheet, { id: d.proposal });
    if (it.run_id) return NL.openRun(it.run_id);
    if (it.idea) return NL.go('study/' + it.idea);
    return NL.open(NL.InboxSheet, {}, { key: 'inbox' });
  };
  NL.attAct = async (it, a) => {
    const run = it.run_id, d = it.detail || {};
    switch (a.id) {
      case 'answer': case 'tail': return NL.openRun(run);
      case 'checkpoint': case 'panel': return NL.attOpen(it);
      case 'proposal': return NL.open(NL.ProposalSheet, { id: d.proposal });
      case 'campaign': return NL.openCampaign(d.campaign);
      case 'artifact': return NL.openArtifact(d.artifact);
      case 'reply': return run ? NL.openRun(run) : NL.go(it.idea && it.idea !== 'hub' ? `study/${it.idea}` : '');
      case 'stop': if (await NL.confirm({ title: 'Stop this run?', body: 'It stays resumable.', ok: 'Stop', danger: true })) return NL.act('/api/run/stop', { run_id: run, confirm: true }, 'Stopping'); return;
      case 'resume': return it.kind === 'followup' ? NL.continueTask(run) : NL.act('/api/run/resume', { run_id: run }, 'Resuming');
      case 'handoff': return NL.continueTask(run,true);
      case 'next': return NL.launchCommand(a.command || d.next, (NL.run(NL.getState(), run) || {}).subject);
      case 'allow': case 'deny': return NL.act('/api/run/permission', { run_id: run, n: d.n, allow: a.id === 'allow' }, a.id === 'allow' ? 'Allowed once' : 'Denied');
      case 'resolve': return NL.act('/api/escalation/resolve', { ref: d.id, source: d.source }, 'Marked handled');
      case 'inspect': return NL.openWorker(d.worker_id);
      case 'dismiss': return NL.act('/api/attention/ack', { id: it.id, action: 'dismiss' }, 'Dismissed');
      case 'ack': return NL.act('/api/flag/ack', { flag: d.flag }, 'Acknowledged');
      case 'move': { const st = NL.item(NL.getState(), d.study || it.idea); return st ? NL.moveStudy(st) : NL.go('study/' + (d.study || it.idea)); }
      default: return NL.attOpen(it);
    }
  };
  const InboxRow = ({ it, compact }) => {
    const s = NL.useLab();
    const acts = (it.actions || []).slice(0, compact ? 2 : 4);
    const open = () => NL.attOpen(it);
    return html`<div class=${cls('inrow', 'sev-' + it.sev, 'k-' + it.kind)}>
      <button type="button" class="inrow-main" onClick=${open}><span class="inrow-ico" aria-hidden="true">${ICON[it.kind] || '•'}</span>
        <span class="inrow-t"><small>${NL.attSubject(it, s)}</small><b>${it.title}</b>${it.body ? html`<small>${NL.clip(it.body, compact ? 110 : 260)}</small>` : null}</span></button>
      ${acts.length ? html`<span class="inrow-acts">${acts.map(a => html`<${NL.Btn} small kind=${PRIMARY.has(a.id) ? 'primary' : ''} onClick=${() => NL.attAct(it, a)}>${a.label}</${NL.Btn}>`)}</span>` : null}</div>`;
  };
  const sortInbox = xs => xs.slice().sort((a, b) => ({ block: 0, warn: 1, info: 2 }[a.sev] - { block: 0, warn: 1, info: 2 }[b.sev]) || String(b.ts || '').localeCompare(String(a.ts || '')));
  // Study snapshots also contain their hub instructions; aggregate each bus once.
  const directivesOf = s => [...(s?.directives || []), ...(s?.items || []).flatMap(i => (i.directives || [])
    .filter(d => d.scope !== 'hub').map(d => ({ ...d, target: d.target || i.id })))];
  NL.inboxItems = s => {
    const att = sortInbox(((s && s.attention) || []));
    const pend = directivesOf(s).filter(d => ['pending', 'seen'].includes(d.state));
    return { needs: att.filter(a => a.sev !== 'info'), info: att.filter(a => a.sev === 'info'), notes: pend };
  };

  NL.InboxSheet = ({ onClose }) => {
    const s = NL.useLab();
    const { needs, info, notes } = NL.inboxItems(s);
    return html`<${NL.Sheet} title="Inbox" onClose=${onClose}>
      ${needs.length ? needs.map(it => html`<${InboxRow} key=${it.id} it=${it} />`) : html`<${NL.Empty} icon="✓">No decisions waiting.</${NL.Empty}>`}
      ${info.length ? html`<${NL.Section} title="Finished" count=${info.length}>${info.slice(0, 20).map(it => html`<${InboxRow} key=${it.id} it=${it} compact />`)}</${NL.Section}>` : null}
      ${notes.length ? html`<${NL.Section} title="Pending instructions" count=${notes.length}>${notes.map(d => html`<div class="inrow sev-info"><div class="inrow-main"><span class="inrow-ico">✉</span><span class="inrow-t"><b>${NL.clip(d.text, 120)}</b><small>to ${d.target === 'hub' ? 'the lab' : d.target} · ${d.state === 'seen' ? 'seen; awaiting action' : 'pending'} · ${NL.hhmm(d.ts)}</small></span></div>
        <span class="inrow-acts"><${NL.Btn} small onClick=${() => NL.act('/api/withdraw', { target: d.target || 'hub', id: d.id, ts: d.ts, scope: d.scope }, 'Withdrawn')}>withdraw</${NL.Btn}></span></div>`)}</${NL.Section}>` : null}
      <div class="row end"><a class="link small" href="#/history" onClick=${onClose}>Full history →</a></div>
    </${NL.Sheet}>`;
  };

  const PinnedInstruments = () => {
    const instruments = NL.panelsOf(NL.useLab()).filter(p => !p.archived && (p.pinned || []).some(place => place === 'home' || place === 'dock'));
    return instruments.length ? html`<${NL.Section} title="Instruments" className="desk-instruments" action=${html`<a class="link small" href="#/workflow/instruments">All instruments →</a>`}>
      <div class="grid2">${instruments.map(p => html`<button type="button" key=${p.id} class="desk-entry" onClick=${() => NL.openPanel(p.id)}><b>${p.title}</b><small>${p.summary || (p.needs_approval ? 'Review collector' : 'Open readings')}</small></button>`)}</div></${NL.Section}>` : null;
  };
  const WorkList = ({ work, limit }) => html`${work.length ? work.slice(0,limit).map(r => html`<div class="desk-work" key=${r.run_id}><button type="button" class="desk-entry" onClick=${() => r.status==='queued'?NL.openRun(r.run_id):NL.followAgent(r.run_id)}><b><${NL.AgentAvatar} backend=${r.backend} size=${20}/> ${NL.runTitle(r)}</b><small>${NL.runStateLabel(r)}</small></button><button type="button" class="link small" onClick=${()=>NL.openRun(r.run_id)}>${r.status==='waiting_input'?'Answer':'Conversation'}</button></div>`) : html`<p class="muted">No work in progress.</p>`}
    ${work.length > limit ? html`<a class="link small" href="#/runs">${NL.plural(work.length - limit, 'more task')} →</a>` : null}`;
  NL.LabDesk = () => {
    const s=NL.useLab(),{needs}=NL.inboxItems(s),work=NL.workRuns(s);
    const outputs=NL.artifactsOf(s).slice(0,3);
    return html`<section class="lab-desk" id="lab-desk" aria-label="Lab notes">
      <header class="desk-heading"><div><span class="kicker">Lab notes</span><h2 id="lab-desk-heading" tabIndex="-1">Work in progress</h2></div><a class="link" href="#/studies">Your studies →</a></header>
      <div class="desk-columns"><section><header><h3>Inbox <span class="count">${needs.length}</span></h3><button type="button" class="link small" onClick=${()=>NL.open(NL.InboxSheet,{}, {key:'inbox'})}>Inbox →</button></header>
        ${needs.length?needs.slice(0,3).map(it=>html`<${InboxRow} key=${it.id} it=${it} compact/>`):html`<p class="muted">No pending requests.</p>`}
        ${needs.length>3?html`<button type="button" class="link small" onClick=${()=>NL.open(NL.InboxSheet,{}, {key:'inbox'})}>${NL.plural(needs.length-3,'more request')} →</button>`:null}</section>
      <section><header><h3>Work <span class="count">${work.length}</span></h3><a class="link small" href="#/runs">All agents →</a></header>
        <${WorkList} work=${work} limit=${4}/></section>
      <section><header><h3>Recent outputs</h3><a class="link small" href="#/library">Library →</a></header>
        ${outputs.length?outputs.map(a=>html`<a class="desk-entry" href=${'#/artifacts/'+a.id}><b>${a.title}</b><small>${NL.item(s,a.study)?.title||'Lab'} · ${NL.ago(a.created)}</small></a>`):html`<p class="muted">Published work will appear here.</p>`}</section></div><${PinnedInstruments}/></section>`;
  };

  NL.Home = () => {
    const s = NL.useLab(), needs = NL.needsYou(s);
    const studies = (s.items || []).filter(i => !NL.isTerminal(i.state));
    const running = NL.workRuns(s);
    return html`<div class="page research-home">
      <header class="overview-heading"><h1>Overview</h1>
        <div class="row"><${NL.Btn} kind="primary" onClick=${() => NL.go('start')}>New study</${NL.Btn}>
          <a class="link" href="#/workflow">Workflow</a></div></header>
      ${!NL.agentReady(s) ? html`<div class="setup-note"><div><b>No agent connected</b></div><a class="btn" href="#/setup">Connect an agent</a></div>` : null}
      <div class="overview-grid"><section class="overview-section"><header><h2>Studies</h2><a class="link small" href="#/studies">View all →</a></header>
        ${studies.length ? studies.slice(0, 8).map(it => { const next=NL.nextFor(s,it); return html`<article class="overview-study"><div><a href=${'#/study/'+it.id}><h3>${it.title || it.id}</h3></a>
          <p class="muted small">${NL.taskLabel(it)} · ${NL.workflowOf(it).title}</p></div>${next ? html`<${NL.Btn} small onClick=${next.run}>${next.label}</${NL.Btn}>` : null}</article>`; })
        : html`<div class="overview-empty"><h3>No studies yet.</h3><a class="link" href="#/start">New study →</a></div>`}
        <div class="overview-process"><a class="link small" href="#/workflow">Edit workflow →</a></div></section>
      <aside class="overview-section"><header><h2>Inbox</h2><span class="count">${needs.length}</span></header>
        ${needs.length ? needs.slice(0,5).map(it => html`<${InboxRow} key=${it.id} it=${it} compact />`) : html`<p class="muted overview-quiet">No decisions waiting.</p>`}
        ${needs.length>5?html`<button type="button" class="link small" onClick=${()=>NL.open(NL.InboxSheet,{}, {key:'inbox'})}>${NL.plural(needs.length-5,'more request')} →</button>`:null}
        <header class="overview-subhead"><h2>Current work</h2><span class="count">${running.length}</span></header>
        <${WorkList} work=${running} limit=${5}/>
        <button type="button" class="link small" onClick=${() => NL.openAsk('')}>Ask an agent →</button>
        <${PinnedInstruments}/></aside></div>
    </div>`;
  };

  /* ── History: commands, notes, events ───────────────────────────────────── */
  NL.HistoryPage = ({ query }) => {
    const s = NL.useLab();
    const [q, setQ] = useState('');
    const [tab, setTab] = useState('events');
    const [since, setSince] = useState((query && query.since) || '');
    // opening History counts as catching up
    useEffect(() => { const last = (s.events || []).slice(-1)[0], prev = NL.ls.get('nl-seen-through', ''); if (prev) NL.ls.set('nl-seen-through-prev', prev); if (last) NL.ls.set('nl-seen-through', last.ts); }, []);
    const evs = (s.events || []).slice().reverse().filter(e => (!since || (e.ts || '') > since) && (!q || JSON.stringify(e).toLowerCase().includes(q.toLowerCase())));
    const where = e => { const id = e.idea || (e.source !== 'hub' ? e.source : null), it = id && NL.item(s, id); return id ? html`<a class="link" href=${'#/study/' + id}>${NL.clip(it ? it.title || id : id, 28)}</a>` : 'the lab'; };
    const who = e => /campaign/i.test(`${e.detail || ''} ${(e.data || {}).by || ''}`) ? 'a campaign' : /PI|you\b|dashboard/.test(`${(e.data || {}).by || ''} ${e.source || ''}`) ? 'you' : e.run_id || /run|agent/.test(e.kind || '') ? 'an agent' : '';
    const outcome = e => e.kind === 'run_finished' && e.status ? html` <${NL.Pill} tone=${e.status === 'completed' ? 'ok' : 'bad'}>${e.status === 'completed' ? 'done' : e.status}</${NL.Pill}>` : null;
    const dirs = directivesOf(s)
      .sort((a, b) => (b.ts || '').localeCompare(a.ts || '')).filter(d => !q || (d.text || '').toLowerCase().includes(q.toLowerCase()));
    return html`<div class="page">
      <header class="page-head"><div><h1>History</h1></div>
        <div class="row"><button type="button" class=${cls('lens', since && 'on')} onClick=${() => setSince(since ? '' : (NL.ls.get('nl-seen-through-prev', '') || (s.events || []).slice(-20)[0]?.ts || ''))}>Since my last visit</button>
          <input class="input search" aria-label="Filter history" placeholder="Filter…" value=${q} onInput=${e => setQ(e.target.value)} /></div></header>
      <${NL.Tabs} tabs=${[{ id: 'events', label: 'Events', count: evs.length }, { id: 'commands', label: 'Your commands & notes', count: dirs.length }]} value=${tab} onChange=${setTab} />
      <div class="history-scroll" role="region" aria-label=${tab==='events'?'History events':'Your commands and notes'} tabindex=${(tab==='events'?evs.length:dirs.length)?0:null}>
      ${tab === 'events' ? (!evs.length ? html`<${NL.Empty} icon="◷">${since ? 'All quiet since your last visit.' : q ? 'Nothing matches that filter.' : 'Nothing has happened in this lab yet.'}</${NL.Empty}>`
        : html`<table class="table"><thead><tr><th>When</th><th>Where</th><th>What</th><th>By</th><th>Detail</th></tr></thead><tbody>
        ${evs.slice(0, 300).map(e => html`<tr><td class="mono small">${NL.when ? NL.when(e.ts) : (e.ts || '').replace('T', ' ').slice(5, 16)}</td><td>${where(e)}</td>
          <td><b>${(k => k.charAt(0).toUpperCase() + k.slice(1))((e.kind || '').replace(/_/g, ' '))}</b>${outcome(e)}</td><td class="small muted">${who(e)}</td><td class="small">${NL.clip(e.detail, 160) || html`<span class="muted">—</span>`}${e.run_id ? html` <button type="button" class="link small" onClick=${() => NL.openRun(e.run_id)}>Open run ↗</button>` : null}</td></tr>`)}</tbody></table>`)
      : html`<table class="table"><thead><tr><th>When</th><th>To</th><th>What</th><th>State</th></tr></thead><tbody>
        ${dirs.map(d => html`<tr><td class="mono small">${(d.ts || '').replace('T', ' ').slice(5, 16)}</td><td>${d.target === 'hub' || !d.target ? 'lab' : d.target}</td>
          <td>${d.kind === 'command' ? html`<b>${(d.action || '').replace(/_/g, ' ')}</b> ` : null}${NL.clip(d.text, 160)}</td>
          <td><${NL.Pill} tone=${d.state === 'done' ? 'ok' : d.state === 'blocked' ? 'bad' : d.state === 'withdrawn' ? 'muted' : 'ask'}>${d.state}</${NL.Pill}>${d.state === 'done' && !(d.ack && d.ack.evidence) ? html` <span class="warn small" title="done without evidence">no evidence</span>` : null}</td></tr>`)}</tbody></table>`}
      </div></div>`;
  };
})();
