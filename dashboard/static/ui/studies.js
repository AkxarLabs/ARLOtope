/* Newts' Lab — studies. The Ledger (every study as a row with its path drawn as a metro strip) and the
   Dossier (one study: its path, what waits for you, the action orb — its step's procedures as buttons — and
   tabs for its overview, documents, agents, instruments, instructions and fate). Both sit in a glass column
   on the left; the world keeps the rest of the screen and flies to the study's room. Also the paper viewer
   and the claims map. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useMemo, cls } = NL;

  /* what the study needs next → its one primary button */
  NL.nextFor = (s, it) => {
    if (!it) return null;
    const live = NL.runsOf(s, it.id).find(r => NL.RUN_ACTIVE.has(r.status) || r.status === 'queued' || r.status === 'waiting_input');
    if (live) return { label: live.status === 'waiting_input' ? 'Answer its question' : 'Watch the agent', glyph: live.status === 'waiting_input' ? 'chat' : 'agents', run: () => NL.openRun(live.run_id), live };
    const w = (it.waiting || [])[0];
    if (w) { const c = NL.checkpoint(w, it) || { title: w }; return { label: `Review: ${c.title}`, glyph: 'diamond', run: () => NL.openCheckpoint(it.id, w), checkpoint: w }; }
    if(it.runnable?.length)return {label:'Run ready tasks',glyph:'play',run:()=>NL.act('/api/workflow/run',{study:it.id,retry:true},'Ready tasks queued')};
    if (it.project_mode === 'attached' && it.state === NL.stepsOf(it)[0] && !it.finished && !NL.isShelved(it.state)) return { label: 'Work on this project', glyph: 'chat', run: () => NL.openAsk('', it.id) };
    const skill = NL.nextSkill(it);
    if (!skill) return NL.isDone(it.state) ? null : NL.isShelved(it.state) ? { label: 'Revive it', glyph: 'loop', run: () => NL.revive(it) } : null;
    if (((s.skills || {})[skill] || {}).level === 'project' && !it.has_project) return null;
    return { label: NL.procTitle(skill), glyph: NL.procGlyph(skill), skill, run: () => NL.launch({ skill, target: it.id }) };
  };

  /** a study's next step, said plainly: a procedure's title in place of its slug ("/experiment …" too) */
  NL.nextLabel = next => {
    const t = String(next || '').trim();
    if (!t || t === '-') return '';
    const m = t.match(/^\/?([\w-]+)(\s[\s\S]*)?$/);
    return m && NL.PROC[m[1]] ? NL.procTitle(m[1]) + (m[2] || '') : t;
  };
  /** when a study last changed: the registry's date, else its latest event or run */
  const lastTouched = (s, it) => [it.updated, ...(it.events || []).map(e => e.ts), ...NL.runsOf(s, it.id).map(r => r.updated || r.created)]
    .filter(Boolean).map(String).sort().pop() || '';
  const statusOf = (s, it) => {
    const runs = NL.runsOf(s, it.id);
    if ((it.slipped || []).length) return ['bad', 'went past a checkpoint'];
    if (((s.holds || {})[it.id])) return ['warm', 'on hold'];
    if ((it.waiting || []).length) return ['warm', 'waiting for you'];
    if (runs.some(r => r.status === 'waiting_input')) return ['warm', 'asking you'];
    const n = runs.filter(r => NL.RUN_ACTIVE.has(r.status)).length;
    if (n) return ['live', NL.plural(n, 'agent') + ' at work'];
    if (runs.some(r=>r.status==='queued')) return ['live','queued'];
    if (NL.isShelved(it.state)) return ['muted', NL.taskLabel(it)];
    if (NL.isDone(it.state)) return ['ok', 'done'];
    return ['', 'idle'];
  };

  const LedgerRow = ({ it }) => {
    const s = NL.useLab();
    const [tone, word] = statusOf(s, it);
    const nx = NL.nextFor(s, it);
    return html`<article class=${cls('lrow', 'st-' + (tone || 'idle'))}>
      <a class="lrow-main" href=${'#/study/' + it.id}>
        <span class="lrow-top"><b class="clip">${it.title || it.id}</b><span class=${cls('lrow-st', tone)}>${tone === 'live' ? html`<i class="dot-live"></i>` : null}${word}</span></span>
        <${NL.Tags} value=${it.tags||[]}/><${NL.Metro} it=${it} compact />
        <span class="lrow-sub muted small">${NL.workflowOf(it).title || ''} · ${NL.taskLabel(it)} · ${(u => u ? NL.ago(u) || NL.when(u) : '')(lastTouched(s, it))}</span></a>
      <div class="lrow-act">${nx ? html`<${NL.Btn} small kind=${nx.checkpoint ? 'primary' : ''} onClick=${nx.run}>${nx.label}</${NL.Btn}>` : null}
</div></article>`;
  };

  NL.StudiesPage = ({ query }) => {
    const s = NL.useLab();
    useEffect(() => { if (query && query.campaign) NL.openCampaign(query.campaign); }, [query && query.campaign]);
    const camps = NL.campaignsOf(s).filter(c => !['done', 'stopped'].includes(c.status) || (Date.now() - new Date(c.created)) < 3 * 86400e3);
    const [f, setF] = useState(NL.ls.get('nl-ledger-f', 'all'));
    const [q, setQ] = useState(''), [tag,setTag]=useState(query?.tag||'');
    const setFilter = v => { setF(v); NL.ls.set('nl-ledger-f', v); };
    const all = (s.items || []).filter(i => (!tag||(i.tags||[]).includes(tag))&&(!q || (i.title+' '+i.id+' '+(i.tags||[]).join(' ')).toLowerCase().includes(q.toLowerCase())));
    const FILTERS = [['all', 'All', () => true], ['you', 'For you', i => statusOf(s, i)[0] === 'warm' || statusOf(s, i)[0] === 'bad'],
      ['work', 'At work', i => statusOf(s, i)[0] === 'live'], ['idle', 'Idle', i => statusOf(s, i)[0] === ''],
      ...NL.WORKFLOWS.length > 1 ? NL.WORKFLOWS.map(w => [w.id, w.title || w.id, i => NL.workflowOf(i).id === w.id]) : [],
      ['done', 'Done & set aside', i => NL.isTerminal(i.state)]];
    const pred = (FILTERS.find(x => x[0] === f) || FILTERS[0])[2];
    const items = all.filter(i => f === 'done' || f === 'all' || !NL.isTerminal(i.state)).filter(pred)
      .sort((a, b) => ['bad', 'warm', 'live', '', 'ok', 'muted'].indexOf(statusOf(s, a)[0]) - ['bad', 'warm', 'live', '', 'ok', 'muted'].indexOf(statusOf(s, b)[0]) || lastTouched(s, b).localeCompare(lastTouched(s, a)));
    return html`<div class="ledger">
      <header class="lens-head"><div class="grow"><div class="kicker">Research workspace</div><h1>Studies</h1></div>
        <${NL.Btn} kind="primary" onClick=${() => NL.openStartOrb()}>＋ New study</${NL.Btn}></header>
      ${camps.length ? html`<div class="camp-row">${camps.map(c => html`<${NL.CampaignCard} key=${c.name} c=${c} compact />`)}</div>` : null}
      <div class="ledger-tools"><div class="chips">${FILTERS.map(([v, l, fn]) => html`<button type="button" aria-pressed=${f === v} class=${cls('chip-btn', f === v && 'on')} onClick=${() => setFilter(v)}>${l} <span class="count">${all.filter(i=>v==='done'||v==='all'||!NL.isTerminal(i.state)).filter(fn).length}</span></button>`)}</div>
        <${NL.Select} ariaLabel="Filter studies by tag" value=${tag} onChange=${setTag} options=${[{value:'',label:'All tags'},...(s.tags||[]).map(t=>({value:t,label:t}))]}/><input class="input search" aria-label="Find a study" placeholder="Find a study…" value=${q} onInput=${e => setQ(e.target.value)} /></div>
      ${!(s.items || []).length ? html`<${NL.Empty} title="No studies yet">Choose New study to start with a question or an existing project.</${NL.Empty}>`
        : html`<div class="ledger-rows">${items.map(it => html`<${LedgerRow} key=${it.id} it=${it} />`)}${!items.length ? html`<div class="muted pad">Nothing here.</div>` : null}</div>`}
    </div>`;
  };

  /* ── the dossier ────────────────────────────────────────────────────────── */
  /* the action orb: the step's procedures as buttons — the first is the big one */
  const ActionOrb = ({ it }) => {
    const s = NL.useLab();
    const nx = NL.nextFor(s, it);
    const [open, setOpen] = useState(false);
    const procs = (NL.PROCS_FOR_STATE[it.state] || []).filter(p => p!=='discuss'&&(s.skills || {})[p] && (!nx || p !== nx.skill));
    const can = p => ((s.skills || {})[p] || {}).level !== 'project' || it.has_project;
    const isLoop = p => (NL.PROC[p] || {}).kind === 'driver' && (NL.PROC[p] || {}).level === 'project';
    const run = p => isLoop(p) ? NL.openLoop(it.id) : NL.launch({ skill: p, target: it.id });
    return html`<div class="action-orb">
      ${nx ? html`<button type="button" class=${cls('pill-act', nx.checkpoint && 'warm')} onClick=${nx.run}><${NL.Glyph} name=${nx.glyph || 'play'} size=${18} /><span>${nx.label}</span></button>` : null}
      ${procs.filter(can).slice(0, 5).map(p => html`<button type="button" class="round-act" title=${`${NL.procTitle(p)}${isLoop(p) ? ' (overnight)' : ''}: ${(NL.PROC[p] || {}).does || ''}`} onClick=${() => run(p)}>
        <${NL.Glyph} name=${isLoop(p) ? 'moon' : NL.procGlyph(p)} size=${17} /><span class="round-l">${isLoop(p) ? 'Run overnight' : NL.procTitle(p)}</span></button>`)}
      <button type="button" class="round-act" title="Think out loud with an agent. It changes nothing." onClick=${() => NL.launch({ skill: 'discuss', target: it.id })}><${NL.Glyph} name="chat" size=${17} /><span class="round-l">Talk it through</span></button>
      <button type="button" class="round-act" title="Give it an instruction in your own words" onClick=${() => NL.openAsk('', it.id)}><${NL.Glyph} name="spark" size=${17} /><span class="round-l">Instruct</span></button>
      <button type="button" class="round-act" title="More" onClick=${() => setOpen(!open)}>⋯</button>
      ${open ? html`<div class="orb-menu glass"><button type="button" onClick=${() => { setOpen(false); NL.openStart({ intent: 'study', target: it.id }); }}>Run something else, with options…</button>
        <button type="button" onClick=${() => { setOpen(false); NL.openNote(it.id); }}>Add note</button>
        <button type="button" onClick=${() => { setOpen(false); NL.go(`study/${it.id}/fate`); }}>Park, kill or hold it…</button>
        <span class="mono small muted">newts start ${nx && nx.skill ? nx.skill : '<procedure>'} ${it.id}</span></div>` : null}</div>`;
  };

  NL.StudyPage = ({ args }) => {
    const s = NL.useLab();
    const slug = args[0], tab = args[1] || 'overview';
    const it = NL.item(s, slug);
    if (!it) return html`<div class="dossier"><${NL.Empty} title="No such study">It may have been renamed. <a class="link" href="#/studies">All studies</a></${NL.Empty}></div>`;
    const runs = NL.runsOf(s, it.id);
    const hold = (s.holds || {})[it.id];
    const setTab = t => NL.go(`study/${it.id}/${t}`);
    const wfs = NL.WORKFLOWS;
    const tabs = [{ id: 'overview', label: 'Overview' }, { id: 'docs', label: 'Documents' }, { id: 'runs', label: 'Agents', count: runs.length || null },
      ...(it.has_project ? [{ id: 'experiments', label: 'Experiments', count: (it.inflight || []).length || null }] : []),
      ...(it.has_paper || it.paper ? [{ id: 'paper', label: 'Paper' }] : []),
      { id: 'panels', label: 'Instruments' },
      { id: 'instructions', label: 'Instructions', count: Object.keys(((((s.workflow || {}).study_custom || {})[it.id]) || {}).procedures || {}).length || null },
      { id: 'fate', label: 'Controls' }];
    return html`<div class="dossier">
      <header class="dossier-head">
        <div class="crumbs"><a class="link" href="#/studies">Studies</a> ›</div>
        <div class="row"><span class="kicker grow">${wfs.length > 1 ? html`<${NL.Picker} small value=${NL.workflowOf(it).id} label="Workflow"
            onChange=${async v => { if (v !== NL.workflowOf(it).id && await NL.confirm({ title: `Move this study to “${(wfs.find(w => w.id === v) || {}).title}”?`, body: 'Its steps and checkpoints change from its next step on. Approvals it already has stay recorded.', ok: 'Move it' })) NL.act('/api/study/workflow', { study: it.id, workflow: v }, 'Workflow changed'); }}
            options=${wfs.map(w => ({ value: w.id, label: w.title || w.id, hint: w.blurb, glyph: 'metro' }))} />` : (NL.workflowOf(it).title || '')}</span></div>
        <h1>${it.title || it.id}</h1>
        ${it.remote_project?html`<p class="muted small">${it.machine} · ${it.remote_project.path} · <button class="link" onClick=${()=>NL.openMachineSetup(it.machine)}>Connection</button></p>`:null}
        <${NL.StudyTags} it=${it}/><${NL.Metro} it=${it} />
        ${(it.slipped || []).map(x => html`<div class="banner banner-bad"><${NL.Glyph} name="diamond" size=${18} /><span class="grow"><b>Went past “${(NL.checkpoint(x.id, it) || {}).title || x.id}” without your approval.</b> <span class="muted">${x.why}</span></span>
          <${NL.Btn} small onClick=${() => NL.openCheckpoint(it.id, x.id)}>Review</${NL.Btn}></div>`)}
        ${(it.waiting || []).map(w => { const c = NL.checkpoint(w, it) || { title: w }; return html`<div class="banner banner-warm"><${NL.Seal} state="waiting" size=${30} /><span class="grow"><b>Waiting for you: ${c.title}</b><span class="muted small">${c.means ? ' · ' + c.means : ''}</span></span>
          <${NL.Btn} small kind="primary" onClick=${() => NL.openCheckpoint(it.id, w)}>Review</${NL.Btn}></div>`; })}
        ${hold ? html`<div class="banner"><${NL.Glyph} name="pause" size=${18} /><span class="grow"><b>On hold</b> <span class="muted small">· nothing new starts for it${hold.reason ? ': ' + hold.reason : ''} (${hold.by})</span></span>
          <${NL.Btn} small onClick=${() => NL.act('/api/study/hold', { study: it.id, hold: false }, 'Released')}>Release</${NL.Btn}></div>` : null}
        <${ActionOrb} key=${it.id} it=${it} /></header>
      <${NL.Tabs} tabs=${tabs} value=${tab} onChange=${setTab} />
      <div class="tabpane">
        ${tab === 'overview' ? html`<${Overview} key=${it.id} it=${it} />` : null}
        ${tab === 'docs' ? html`<${Documents} key=${it.id} it=${it} rel=${args.slice(2).join('/')} />` : null}
        ${tab === 'runs' ? html`<details class="study-agent-settings"><summary>Agent choices for this study</summary><${NL.AgentAssignments} key=${it.id} study=${it.id} compact/></details><div class="runlist">${runs.length ? runs.slice().sort((a, b) => (b.created || '').localeCompare(a.created || '')).map(r => html`<${NL.RunRow} key=${r.run_id} r=${r} />`) : html`<${NL.Empty}>No agents have worked on it yet.</${NL.Empty}>`}</div>` : null}
        ${tab === 'experiments' ? html`<${Experiments} key=${it.id} it=${it} />` : null}
        ${tab === 'paper' ? html`<${PaperPane} key=${it.id} it=${it} />` : null}
        ${tab === 'panels' ? html`<${StudyPanels} key=${it.id} it=${it} />` : null}
        ${tab === 'instructions' ? html`<${NL.StudyInstructions} key=${it.id} it=${it} />` : null}
        ${tab === 'fate' || tab === 'controls' ? html`<${Controls} key=${it.id} it=${it} />` : null}
      </div></div>`;
  };

  /* the instruments pinned "on every study", each drawn for this study */
  const StudyPanels = ({ it }) => {
    const s = NL.useLab();
    const ps = NL.panelsOf(s).filter(p => !p.archived && (p.pinned || []).includes('studies'));
    return html`<div class="study-panels">${ps.map(p => html`<section class="pframe glass-soft" key=${p.id}>
        <header class="pframe-head"><i class=${cls('led', p.alerts ? 'led-warm' : 'led-live')}></i><b>${p.title}</b><span class="grow"></span>
          <button type="button" class="link small" onClick=${() => NL.openPanel(p.id, it.id)}>open</button></header>
        <${NL.PanelFrame} id=${p.id} study=${it.id} minHeight=${160} /></section>`)}
      <div class="row"><span class="muted small grow">${ps.length ? 'Instruments pinned to every study.' : 'No instrument is pinned to studies yet.'}</span><a class="link small" href="#/workflow/instruments">the cabinet →</a></div></div>`;
  };

  /* the study's history, from the journal: every move, wait, approval and flag, newest first */
  const WHO = by => !by ? '' : by === 'pi' ? 'you' : by === 'cli' ? 'a terminal' : by === 'auto' ? 'its checks'
    : by.startsWith('run:') ? 'run ' + by.slice(4) : by.startsWith('campaign:') ? 'the campaign ' + by.slice(9) : by;
  const said = (e, it) => {
    const L = st => NL.STATE_LABEL[st] || st, cp = id => (NL.checkpoint(id, it) || {}).title || id;
    switch (e.kind) {
      case 'new': return `filed at ${L(e.step)}${e.workflow ? ` (${(NL.WORKFLOWS.find(w => w.id === e.workflow) || {}).title || e.workflow})` : ''}`;
      case 'move': return `${L(e.from)} → ${L(e.to)}${e.outcome ? ` · reported ${e.outcome}` : ''}`;
      case 'wait': return e.checkpoint ? `waits for your approval: ${cp(e.checkpoint)}` : `reported ${e.outcome}; waits for you to say where it goes`;
      case 'finish': return 'finished its workflow';
      case 'approval': return `${cp(e.checkpoint)}: ${e.decision === 'changes-requested' ? 'changes requested' : e.decision}`;
      case 'workflow': return `now follows ${(NL.WORKFLOWS.find(w => w.id === e.workflow) || {}).title || e.workflow}`;
      case 'use': return Object.keys(e.use || {}).length ? 'uses ' + Object.entries(e.use).map(([k, v]) => `/${v} for /${k}`).join(', ') : "uses its workflow's procedures";
      case 'project': return `its project: ${e.path}`;
      case 'remap': return 'steps renamed: ' + Object.entries(e.map || {}).map(([a, b]) => `${a} → ${b}`).join(', ');
      case 'flag': return `⚑ ${e.say}${e.acked ? ' (acknowledged)' : ''}`;
      case 'title': return 'renamed';
      default: return e.kind;
    }
  };
  const Timeline = ({ it }) => {
    const [evs, setEvs] = useState(null);
    useEffect(() => { NL.get('/api/study/timeline?study=' + encodeURIComponent(it.id)).then(x => setEvs((x && x.events) || [])); }, [it.id, it.state, it.updated, JSON.stringify(it.waiting || [])]);
    if (!evs) return html`<${NL.Spinner} />`;
    if (!evs.length) return html`<div class="muted small">Nothing recorded yet.</div>`;
    return html`<ol class="timeline">${evs.slice().reverse().slice(0, 40).map(e => html`<li class=${cls('tl-' + e.kind, e.kind === 'flag' && !e.acked && 'tl-open')}>
      <span class="tl-when mono" title=${e.ts}>${NL.ago(e.ts)}</span>
      <span class="tl-what">${said(e, it)}${e.by && e.kind !== 'remap' ? html` <span class="muted small">· ${e.by.startsWith('run:') ? html`<a class="link" href=${'#/run/' + e.by.slice(4)}>${WHO(e.by)}</a>` : WHO(e.by)}</span>` : null}
        ${e.note ? html`<div class="muted small tl-note">“${e.note}”</div>` : null}</span></li>`)}</ol>`;
  };

  const Overview = ({ it }) => {
    const s = NL.useLab();
    const workers = NL.workersOf(s, it.id).filter(w => w.status !== 'done');
    const pending = (it.directives || []).filter(d => d.state === 'pending');
    return html`<div class="cols">
      <div class="col-main"><${NL.DocReader} scope="study" slug=${it.id} rel="IDEA.md" bare fallback=${html`<${NL.Empty} icon="🌱" title="No idea write-up yet">
        This study has no <span class="mono">studies/${it.id}/IDEA.md</span>${it.has_project ? '; its project repo is under Documents' : ''}.</${NL.Empty}>`} /></div>
      <aside class="col-side"><${NL.StudyNotes} study=${it.id}/>
        ${it.active_steps?.length?html`<${NL.Section} title="Workflow tasks" count=${it.active_steps.length}>
          ${it.active_steps.map(t=>{const definition=s.workflow?.workflows?.find(w=>w.id===it.workflow)?.nodes?.[t.id],run=NL.runsOf(s,it.id).find(r=>r.run_id===t.run_id),waits=(it.task_waits||[]).filter(w=>w.at===t.id);return html`<div class="note"><b>${definition?.label||NL.STATE_LABEL[t.id]||t.id}</b><div class="muted small">${definition?.agent?.role||'general'} · visit ${t.visit}${run?' · '+run.status:''}</div>
          ${run?html`<div class="row"><button class="link small" onClick=${()=>NL.openRun(run.run_id)}>Conversation</button><button class="link small" onClick=${()=>NL.followAgent(run.run_id)}>Follow in lab</button></div>`:null}
          ${waits.map(w=>html`<button class="link small" onClick=${()=>NL.openCheckpoint(it.id,w.checkpoint)}>◆ ${w.title}</button>`)}</div>`})}
          ${it.blocked_reason?html`<p class="note note-warn">${it.blocked_reason}</p>`:null}
          ${it.runnable?.length?html`<${NL.Btn} small onClick=${()=>NL.act('/api/workflow/run',{study:it.id,retry:true},'Ready tasks queued')}>Run ready tasks</${NL.Btn}>`:null}
        </${NL.Section}>`:null}
        <${NL.Section} title="Now">
          <div class="facts"><div><span>Step</span><b>${NL.taskLabel(it)}</b></div>
            ${NL.nextLabel(it.next) ? html`<div><span>Next</span><b>${NL.nextLabel(it.next)}</b></div>` : null}
            ${(() => { const u = lastTouched(s, it); return html`<div><span>Updated</span><b title=${u ? NL.when(u) : ''}>${(u && (NL.ago(u) || NL.when(u))) || '—'}</b></div>`; })()}
            ${it.best ? html`<div><span>Best so far</span><b class="mono">${typeof it.best === 'object' ? Object.entries(it.best).filter(([k]) => k !== 'run_id').map(([k, v]) => `${k} ${typeof v === 'number' ? (+v).toPrecision(4) : v}`).join(' · ') : it.best}</b></div>` : null}
            ${NL.checkpointsOf(it).map(c => html`<div><span>◆ ${c.title}</span><b class=${NL.approvedCp(it, c.id) ? 'live' : (it.waiting || []).includes(c.id) ? 'warn' : 'muted'}>${NL.approvedCp(it, c.id) ? 'approved' : (it.waiting || []).includes(c.id) ? 'waiting for you' : 'ahead'}</b></div>`)}
            ${it.loop_active ? html`<div><span>Loop</span><b class="live">running</b></div>` : null}</div></${NL.Section}>
        ${workers.length ? html`<${NL.Section} title="Agents on it" count=${workers.length}>${workers.map(w => html`<button type="button" class="agent-chip wide" onClick=${() => NL.openWorker(w.worker_id)}><${NL.RoleDot} role=${w.role} /><span class="clip grow">${w.label || NL.roleOf(w.role).label}</span><span class="muted small">${w.in_tool ? '▸ ' + w.in_tool.tool : w.status}</span></button>`)}</${NL.Section}>` : null}
        ${pending.length ? html`<${NL.Section} title="Notes waiting for an agent" count=${pending.length}>${pending.map(d => html`<div class="note"><div>${d.text}</div><div class="row"><span class="muted small">${NL.hhmm(d.ts)}</span><span class="grow"></span>
          <button class="link small" onClick=${() => NL.act('/api/withdraw', { target: it.id, id: d.id, ts: d.ts }, 'Withdrawn')}>withdraw</button></div></div>`)}</${NL.Section}>` : null}
        <${NL.Section} title="History"><${Timeline} it=${it} /></${NL.Section}>
      </aside></div>`;
  };

  const Documents = ({ it, rel }) => {
    const tree = NL.useLibTree();
    const g = tree && (tree.groups || []).find(x => x.slug === it.id);
    const docs = g ? g.sections.flatMap(sec => sec.docs.map(d => ({ ...d, sec: sec.title }))) : [];
    const [sel, setSel] = useState(null);
    useEffect(()=>setSel(null),[it.id,rel]);
    const cur = sel || (rel ? docs.find(d => d.rel === rel) : null) || docs[0];
      const records=NL.useArtifactList({study:it.id}),shown=records.rows;
    return html`<div class="page-split inner">
      <aside class="split-left"><a class="link small" href=${'#/library?'+NL.qs({view:'records',study:it.id})}>Notes, answers & sources →</a>${shown.length ? html`<div class="shelf-sec"><div class="shelf-sec-h">❏ Results (${shown.length})</div>${shown.map(a => html`<button type="button" class="shelf-doc" onClick=${() => NL.openArtifact(a.id)}>${a.title}${a.question && !a.answered ? ' · asks you' : ''}</button>`)}</div>` : null}
        ${records.next?html`<${NL.Btn} small busy=${records.loading} onClick=${records.loadMore}>Load older results</${NL.Btn}>`:null}${records.error?html`<p role="alert">${records.error}</p>`:null}
        ${!tree ? html`<${NL.Spinner} />` : !docs.length ? html`<div class="muted small">No documents in the study or its project yet.</div>` :
        g.sections.map(sec => html`<div class="shelf-sec"><div class="shelf-sec-h">${sec.icon || ''} ${sec.title}</div>${sec.docs.map(d => html`<button type="button" class=${cls('shelf-doc', cur && cur.rel === d.rel && cur.scope === d.scope && 'on')} onClick=${() => setSel(d)}><${NL.DocName} d=${d} /></button>`)}</div>`)}</aside>
      <main class="split-right">${cur ? html`<${NL.DocReader} scope=${cur.scope} slug=${cur.slug} rel=${cur.rel} />` : null}</main></div>`;
  };

  const Experiments = ({ it }) => {
    const [out, setOut] = useState(null);
    const tool = async (name) => { setOut({ name, busy: true }); const r = await NL.api('/api/tool', { name, idea: it.id }); setOut({ name, ...r }); };
    const inflight = it.inflight || [];
    return html`<div class="cols"><div class="col-main">
      <${NL.Section} title="Running now" count=${inflight.length || null}>${inflight.length ? inflight.map(r => html`<div class="exp-row">
        <div class="row"><b class="mono">${r.run_id}</b><${NL.Pill} tone=${r.state === 'stalled' ? 'warn' : 'live'}>${r.stage || ''} · ${r.state}</${NL.Pill}><span class="grow"></span>
          <button class="link small" onClick=${async () => { const x = await NL.api('/api/read', { what: 'run', idea: it.id, run: r.run_id }); NL.open(NL.SectionsSheet, { title: r.run_id, data: x }); }}>peek</button></div>
        ${r.budget_min ? html`<${NL.Bar} value=${r.elapsed_s} max=${r.budget_min * 60} tone=${r.elapsed_s > r.budget_min * 51 ? 'warn' : ''} />` : null}
        <div class="muted small">${NL.mins(r.elapsed_s)}${r.budget_min ? ' of ' + r.budget_min + 'm' : ''}${Object.keys(r.last || {}).length ? ' · ' + Object.entries(r.last).slice(0, 4).map(([k, v]) => `${k} ${(+v).toPrecision(4)}`).join(' · ') : ''}</div></div>`)
        : html`<div class="muted">Nothing training right now.${it.n_runs ? ` ${NL.plural(it.n_runs, 'run')} recorded.` : ''}</div>`}</${NL.Section}>
      ${out ? html`<${NL.Section} title=${out.name} action=${html`<button class="link small" onClick=${() => setOut(null)}>close</button>`}>${out.busy ? html`<${NL.Spinner} />` : html`<pre class="plain">${out.output || out.error || '(no output)'}</pre>`}</${NL.Section}>` : null}
    </div><aside class="col-side"><${NL.Section} title="Look closer"><div class="stack">
      <${NL.Btn} onClick=${() => tool('status')}>Project status</${NL.Btn}><${NL.Btn} onClick=${() => tool('compare')}>Compare runs</${NL.Btn}>
      <${NL.Btn} onClick=${() => tool('show_config')}>Settings in force for this study</${NL.Btn}><${NL.Btn} onClick=${() => tool('inbox')}>Notes to its agents</${NL.Btn}></div></${NL.Section}>
      <${NL.Section} title="Start"><div class="stack">${(NL.PROCS_FOR_STATE[it.state] || []).filter(p => (NL.getState().skills || {})[p]).map(p => {
        const brief = (NL.PROC[p] || {}).kind === 'driver' && (NL.PROC[p] || {}).level === 'project';   // a loop needs your approval first
        return html`<${NL.Btn} onClick=${() => brief ? NL.openLoop(it.id) : NL.launch({ skill: p, target: it.id })}>${NL.procTitle(p)}${brief ? '…' : ''}</${NL.Btn}>`; })}
        </div></${NL.Section}></aside></div>`;
  };

  NL.SectionsSheet = ({ title, data, onClose }) => html`<${NL.Sheet} wide title=${title} onClose=${onClose}>${!data || !data.ok ? html`<div class="note note-warn">${(data && data.error) || 'nothing to show'}</div>` :
    (data.sections || []).map(sec => html`<${NL.Section} title=${sec.title}><pre class="plain">${sec.text}</pre></${NL.Section}>`)}</${NL.Sheet}>`;

  /* ── paper ─────────────────────────────────────────────────────────────── */
  const PaperPane = ({ it }) => {
    const [figs, setFigs] = useState([]);
    const mt = (it.paper && it.paper.mtime) || '';
    useEffect(() => { NL.get(`/api/figs?${NL.qs({ idea: it.id })}`).then(x => setFigs((x && x.figures) || [])); }, [it.id, mt]);
    const src = `/api/paper?${NL.qs({ idea: it.id, t: mt })}`;
    return html`<div class="cols"><div class="col-main">${it.paper ? html`<iframe class="pdf" src=${src} title="the paper"></iframe>` : html`<${NL.Empty} icon="📜">No compiled paper yet (studies/${it.id}/paper/main.pdf).</${NL.Empty}>`}</div>
      <aside class="col-side"><${NL.Section} title="Paper"><div class="stack">${it.paper ? html`<a class="btn" href=${src} target="_blank" rel="noopener">Open the PDF ↗</a>` : null}
        <${NL.Btn} onClick=${() => NL.openClaims(it.id)}>Claims ↔ evidence${it.claims ? ` (${it.claims})` : ''}</${NL.Btn}>
        <${NL.Btn} onClick=${() => NL.launch({ skill: 'make-figures', target: it.id })}>Rebuild figures</${NL.Btn}>
        <${NL.Btn} onClick=${() => NL.launch({ skill: 'critique-paper', target: it.id })}>Critique it</${NL.Btn}>
        ${(it.waiting || []).map(w => html`<${NL.Btn} kind="primary" onClick=${() => NL.openCheckpoint(it.id, w)}>◆ ${(NL.checkpoint(w, it) || {}).title || w}…</${NL.Btn}>`)}</div></${NL.Section}>
        ${figs.length ? html`<${NL.Section} title="Figures" count=${figs.length}><div class="figs">${figs.map(f => /\.pdf$/i.test(f) ? html`<a class="link small" href=${`/api/figure?${NL.qs({ idea: it.id, name: f })}`} target="_blank">${f}</a>` :
          html`<a href=${`/api/figure?${NL.qs({ idea: it.id, name: f })}`} target="_blank" rel="noopener"><img src=${`/api/figure?${NL.qs({ idea: it.id, name: f, t: mt })}`} alt=${f} loading="lazy" /></a>`)}</div></${NL.Section}>` : null}</aside></div>`;
  };
  NL.openPaper = slug => NL.go(`study/${slug}/paper`);

  NL.ClaimsSheet = ({ slug, onClose }) => {
    const [r, setR] = useState(null);
    const [audit, setAudit] = useState(null);
    useEffect(() => { NL.api('/api/claims', { idea: slug }).then(setR); }, [slug]);
    const claims = (r && r.claims) || [];
    return html`<${NL.Sheet} wide title="Claims ↔ evidence" sub="Every number in the paper should point at an artifact on disk (hard rule 1)." onClose=${onClose}
      footer=${html`<div class="row"><${NL.Btn} onClick=${async () => { setAudit({ busy: true }); setAudit(await NL.api('/api/tool', { name: 'audit_claims', idea: slug })); }}>Run the claims audit</${NL.Btn}><span class="grow"></span>${r && r.claims_path ? html`<${NL.EditorLink} path=${r.claims_path}>claims.yaml ↗</${NL.EditorLink}>` : null}</div>`}>
      ${!r ? html`<${NL.Spinner} />` : r.error ? html`<div class="note note-warn">${r.error}</div>` : !claims.length ? html`<${NL.Empty}>claims.yaml has no entries yet.</${NL.Empty}>` : html`
        <div class="muted small">${NL.plural(claims.length, 'claim')} · ${claims.filter(c => c.linked).length} fully linked to artifacts on disk</div>
        ${claims.map(c => { const arts = c.artifacts || [], miss = arts.filter(a => !a.exists).length; return html`<div class="claim">
          <div class="row">${c.id ? html`<b class="mono">${c.id}</b>` : null}<${NL.Pill} tone=${c.linked ? 'ok' : 'warn'}>${c.linked ? 'linked' : arts.length ? miss + ' missing' : 'no artifacts'}</${NL.Pill}><span class="grow">${c.claim || ''}</span></div>
          <div class="row-wrap small">${(c.numbers || []).map(n => html`<span class="chip mono">${n}</span>`)}${c.metric ? html`<span class="chip">metric: ${c.metric}</span>` : null}${c.location ? html`<span class="chip">${c.location}</span>` : null}${c.has_hashes ? html`<span class="chip">🔒 hashed</span>` : null}</div>
          ${arts.map(a => html`<div class="art ${a.exists ? '' : 'miss'}"><span class="mono small">${a.exists ? '' : '○ '}${a.rel}</span>${a.exists && a.run_id && a.project ? html`<button class="link small" onClick=${async () => NL.open(NL.SectionsSheet, { title: a.run_id, data: await NL.api('/api/read', { what: 'run', idea: a.project, run: a.run_id }) })}>peek</button>` : null}<${NL.EditorLink} path=${a.exists ? a.abs : null} /></div>`)}</div>`; })}`}
      ${audit ? html`<${NL.Section} title="Audit">${audit.busy ? html`<${NL.Spinner} />` : html`<pre class="plain">${audit.output || audit.error}</pre>`}</${NL.Section}>` : null}
    </${NL.Sheet}>`;
  };
  NL.openClaims = slug => NL.open(NL.ClaimsSheet, { slug }, { key: 'claims' });

  /* ── fate: steering, checkpoints, hold, park/kill/revive ─────────────────── */
  /* where a study set aside by `action` (park / kill) ends up: the shelf for it, and its room */
  const shelfRoom = action => {
    const shelves = Object.values(NL.STEPS).filter(x => x.shelf);
    const st = shelves.find(x => String(x.id).startsWith(action)) || shelves[0];
    const room = st && (NL.ROOMS.find(r => r.key === st.room || (r.states || []).includes(st.id)) || {});
    return (room && (room.title || room.label)) || 'the room for studies set aside';
  };
  const MODES = [{ value: 'execute', label: 'Follow the plan' }, { value: 'explore', label: 'Explore' }];   // as in Settings
  const Controls = ({ it }) => {
    const [labMode, setLabMode] = useState(null);
    const [picked, setPicked] = useState(null);
    useEffect(() => { if (it.has_project) NL.get('/api/lab/config').then(x => setLabMode(((x && x.config) || {}).loop_mode || 'execute')); }, [it.id]);
    // the study's mode: the latest switch you sent it (not withdrawn or refused), else the lab's setting
    const sent = (it.directives || []).filter(x => x.action === 'set_mode' && x.args && x.args.mode && !['withdrawn', 'blocked'].includes(x.state)).slice(-1)[0];
    const mode = picked || (sent && sent.args.mode) || it.loop_mode || labMode || 'execute';
    const cmd = async (action, label, args, confirm) => {
      if (confirm && !await NL.confirm({ ...confirm, ok: confirm.ok || label, danger: true })) return false;
      const launch = ['start_loop', 'stop_loop', 'run_smoke', 'request_run', 'analyze'].includes(action) && NL.execOn(NL.getState());
      const r = await NL.act('/api/command', { target: it.id, action, args: args || {}, launch }, launch ? `${label}: started` : `${label}: its agent picks this up at its next safe point`);
      if (r.launch && r.launch.run_id) NL.openRun(r.launch.run_id);
      return r.ok;
    };
    const setMode = async v => { if (v !== mode && await cmd('set_mode', v === 'explore' ? 'Explore' : 'Follow the plan', { mode: v })) setPicked(v); };
    const off = NL.isShelved(it.state);
    return html`<div class="cols"><div class="col-main">
      ${it.has_project ? html`<${NL.Section} title="Loop and experiments">
        <${NL.Field} label="Its research loop" hint="Follow the plan, or explore: widen the plan and reopen supporting decisions, within its checkpoints. A switch reaches the loop at its next safe point.">
          <${NL.Seg} value=${mode} onChange=${setMode} options=${MODES} /></${NL.Field}>
        <div class="btn-grid">
        <${NL.Btn} onClick=${() => NL.openLoop(it.id)}>Run overnight: the research loop</${NL.Btn}>
        ${it.loop_active ? html`<${NL.Btn} kind="danger" onClick=${() => cmd('stop_loop', 'Stop the loop', {}, { title: 'Stop the loop?', body: 'Its agent stops the loop at its next safe point. You can start it again from here.' })}>Stop the loop</${NL.Btn}>` : null}
        <${NL.Btn} onClick=${() => cmd('run_smoke', 'Run a smoke test')}>Run a smoke test</${NL.Btn}>
        <${NL.Btn} onClick=${() => cmd('request_run', 'Request a run')}>Request a run</${NL.Btn}></div></${NL.Section}>` : null}
      <${NL.Section} title="Priority and fate"><div class="btn-grid">
        <${NL.Btn} onClick=${() => cmd('prioritize', 'Prioritize')}>Prioritize it</${NL.Btn}>
        ${off ? html`<${NL.Btn} kind="primary" onClick=${() => NL.revive(it)}>Revive it</${NL.Btn}>` : html`
          <${NL.Btn} onClick=${() => cmd('park', 'Park it', {}, { title: 'Set this study aside for now?', ok: 'Park it', body: `The agent pauses it at its next safe point and moves it to ${shelfRoom('park')}. You can revive it from there.` })}>Park it</${NL.Btn}>
          <${NL.Btn} kind="danger" onClick=${() => cmd('kill', 'Stop it for good', {}, { title: 'Stop this study for good?', ok: 'Stop it for good', body: `The agent winds it down at its next safe point and moves it to ${shelfRoom('kill')}. You can revive it from there.` })}>Kill it</${NL.Btn}>`}</div></${NL.Section}>
    </div><aside class="col-side">
      <${NL.Section} title="Its checkpoints"><div class="stack">${NL.checkpointsOf(it).map(c => html`<button type="button" class="cp-line" onClick=${() => NL.openCheckpoint(it.id, c.id)}>
          <${NL.Seal} state=${NL.approvedCp(it, c.id) ? 'approved' : 'waiting'} size=${22} /><span class="grow"><b>${c.title}</b><small class="muted">${NL.cpWhere(c)}</small></span></button>`)}
        ${!NL.checkpointsOf(it).length ? html`<span class="muted small">Its workflow has no checkpoints.</span>` : null}</div></${NL.Section}>
      <${NL.Section} title="Hold"><div class="stack">${(NL.getState().holds || {})[it.id]
          ? html`<${NL.Btn} onClick=${() => NL.act('/api/study/hold', { study: it.id, hold: false }, 'Released')}>Release it</${NL.Btn}>`
          : html`<${NL.Btn} onClick=${() => NL.act('/api/study/hold', { study: it.id, hold: true, reason: 'held by the PI' }, 'On hold. Nothing new starts for it.')}>Hold it (nothing new starts)</${NL.Btn}>`}</div></${NL.Section}>
      <${NL.Section} title="Elsewhere"><div class="stack">${it.project_dir ? html`<${NL.EditorLink} path=${it.project_dir} machine=${it.remote_project?it.machine:null}>Open the project repo ↗</${NL.EditorLink}>` : null}
        <button class="link small" onClick=${() => NL.openNote(it.id)}>Add note</button></div></${NL.Section}></aside></div>`;
  };
})();
