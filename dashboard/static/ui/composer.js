/* Newts' Lab — starting work. Procedures are buttons where they belong (a procedure's SKILL.md `newts.ui`
   says where: `home` → the Start orb, `step` → a study's action orb, `study` → every study); this file holds
   what they share: the intents (each with its glyph and one line of what it does), the "Start something"
   sheet, a free-form instruction, the options every launch shares, and the campaign form (it records your
   approval of the campaign, with the checkpoints it may approve for you). */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useMemo, cls } = NL;

  /* ── options shared by every launch ────────────────────────────────────── */
  const DEFAULT_OPTS = { preset: '', role: '', backend: '', model: '', effort: '', max_minutes: '', chain: '', repeat_minutes: '', max_repeats: '' };
  const LaunchOptions = ({ opts, setOpts, allowChain, allowRepeat, target }) => {
    const s = NL.useLab();
    const x = NL.exec(s);
    const bs = NL.backends(s);
    const remote = target && NL.item(s, target)?.remote_project;
    const agents=NL.useAgentSettings(target&&target!=='hub'?target:null);
    const chosen=agents?.presets?.find(p=>p.id===opts.preset)||agents?.resolved?.[opts.role||'general'];
    const backend=opts.backend||chosen?.backend||x.backend;
    const set = (k, v) => setOpts(o => ({ ...o, [k]: v }));
    return html`<details class="opts"><summary>Options <span class="muted">· ${opts.backend||chosen?.label||backend||'Agent default'}${opts.model ? ' · ' + opts.model : ''}${opts.max_minutes ? ' · ' + opts.max_minutes + ' min' : ''}${opts.chain === 'off' ? ' · then stop' : opts.chain ? ' · then ' + (opts.chain === 'next' ? 'the next step' : 'keep going') : ''}</span></summary>
      <div class="grid2">
        <${NL.AgentChoice} study=${target&&target!=='hub'?target:null} role=${opts.role||'general'} value=${opts.preset?'preset:'+opts.preset:opts.backend?'backend:'+opts.backend:''} onChange=${v=>setOpts(o=>({...o,preset:v.startsWith('preset:')?v.slice(7):'',backend:v.startsWith('backend:')?v.slice(8):'',model:'',effort:''}))}/>
        <${NL.Field} label="Role"><${NL.Select} value=${opts.role||''} onChange=${v=>set('role',v)} options=${[{value:'',label:'Task default'},...Object.entries(agents?.roles||{}).map(([value,label])=>({value,label}))]}/></${NL.Field}>
        <${NL.Field} label="Model" hint="Use selected agent settings"><${NL.Input} value=${opts.model} onInput=${v => set('model', v)} placeholder=${chosen?.model||'Agent default'} mono /></${NL.Field}>
        ${['claude','codex'].includes(backend)?html`<${NL.Field} label="Effort"><${NL.Select} value=${opts.effort} onChange=${v => set('effort', v)} options=${[{ value: '', label: 'default' }, 'low', 'medium', 'high', 'xhigh', 'max']} /></${NL.Field}>`:null}
        <${NL.Field} label="Time limit (min)" hint=${'default ' + Math.round((x.config || {}).max_minutes || 240)}><${NL.Input} type="number" min="5" value=${opts.max_minutes} onInput=${v => set('max_minutes', v)} /></${NL.Field}>
        ${allowChain ? html`<${NL.Field} label="When it finishes"><${NL.Select} value=${opts.chain} onChange=${v => set('chain', v)}
          options=${[{ value: '', label: 'As the lab is set' }, { value: 'off', label: 'Stop and report' }, { value: 'next', label: 'Run the next step' }, { value: 'loop', label: 'Keep going until a checkpoint' }]} /></${NL.Field}>` : null}
        ${allowRepeat ? html`<${NL.Field} label="Repeat every (min)" hint="blank = once · stops at a checkpoint or a failure"><${NL.Input} type="number" min="5" value=${opts.repeat_minutes} onInput=${v => set('repeat_minutes', v)} /></${NL.Field}>` : null}
        ${allowRepeat && opts.repeat_minutes ? html`<${NL.Field} label="At most (times)"><${NL.Input} type="number" min="1" value=${opts.max_repeats} onInput=${v => set('max_repeats', v)} /></${NL.Field}>` : null}
      </div></details>`;
  };
  const optBody = o => {
    const b = {};
    for (const k of ['preset', 'role', 'backend', 'model', 'effort', 'max_minutes', 'repeat_minutes', 'max_repeats']) if (o[k] !== '' && o[k] != null) b[k] = o[k];
    if (o.chain) b.chain = o.chain;
    return b;
  };

  const StudyPicker = ({ value, onChange, filter, allowLab, label }) => {
    const s = NL.useLab();
    const items = (s.items || []).filter(filter || (() => true));
    return html`<${NL.Field} label=${label || 'Which study'}><${NL.Select} value=${value} onChange=${onChange}
      options=${[...(allowLab ? [{ value: 'hub', label: 'The whole lab' }] : [{ value: '', label: 'Choose a study…' }]),
        ...items.map(i => ({ value: i.id, label: `${i.title || i.id} · ${NL.STATE_LABEL[i.state] || i.state}` }))]} /></${NL.Field}>`;
  };

  /* ── intents: what can be started from the lab (the Start orb) ─────────────────────────────────── */
  const GLYPH = { ideate: 'seed', adopt: 'archive', compete: 'target', 'lab-status': 'compass', discuss: 'chat', configure: 'gear', advance: 'play',
    autopilot: 'moon', design: 'spark', 'research-loop': 'loop', experiment: 'flask', 'lit-review': 'book', scope: 'compass', propose: 'pen',
    analyze: 'lens', 'write-paper': 'pen', 'review-paper': 'review', 'critique-paper': 'review', 'make-figures': 'spark', improve: 'spark', 'spawn-project': 'plus' };
  NL.procGlyph = name => ((NL.PROC[name] || {}).ui || {}).glyph || GLYPH[name] || 'spark';
  const WORDS = {   // the Start orb says these plainly (a procedure's own ui.label/desc win)
    ideate: ['New direction', 'explore a direction; the best ideas become studies'], adopt: ['Bring in what I have', 'an idea, a repo or a draft becomes a study'],
    compete: ['Compete on a target', 'beat a score: a target-driven study'], 'lab-status': ['Brief me', 'a written summary of where everything stands'],
    discuss: ['Talk it through', 'think out loud with an agent; it changes nothing'] };
  const BUILT_IN = [{ id: 'campaign', glyph: 'moon', title: 'Start a campaign', desc: 'the lab works on its own, within limits you set', campaign: true, order: 6, home: true },
    { id: 'study', glyph: 'studies', title: 'Work on a study', desc: 'pick what to do on it', study: true, order: 4 }];
  NL.intents = () => Object.entries(NL.PROC).filter(([, p]) => (p.start || p.ui) && p.launchable !== false).map(([name, p]) => {
    const st = p.start || {}, ui = p.ui || {}, args = p.args || '', w = WORDS[name] || [];
    const where = ui.where || (p.start ? 'home' : 'none');
    return { id: name, glyph: NL.procGlyph(name), title: ui.label || w[0] || st.title || p.title || name, skill: name, order: ui.order ?? st.order ?? 50,
      arg: args.includes('text') && (ui.asks || st.label) ? 'text' : null, argLabel: (ui.asks || {}).label || st.label, placeholder: (ui.asks || {}).placeholder || st.placeholder,
      target: args.startsWith('slug?') ? 'study?' : null, desc: ui.desc || w[1] || p.does, does: p.does, home: where === 'home', where,
      interactive: p.mode === 'interactive' };
  }).filter(i => i.where !== 'none').concat(BUILT_IN).sort((a, b) => a.order - b.order);

  NL.StartSheet = ({ onClose, intent: initial, target: initTarget, skill: initSkill, args: initArgs }) => {
    const s = NL.useLab();
    const [intent, setIntent] = useState(initial || (initSkill ? 'study' : null));
    const [target, setTarget] = useState(initTarget || '');
    const [skill, setSkill] = useState(initSkill || '');
    const [arg, setArg] = useState(initArgs || '');
    const [opts, setOpts] = useState(DEFAULT_OPTS);
    const [ask, setAsk] = useState('');
    const INTENTS = NL.intents();
    const it = INTENTS.find(i => i.id === intent);
    const study = target && target !== 'hub' ? NL.item(s, target) : null;
    // for "work on a study": the procedures that fit its state
    const procs = study ? (NL.PROCS_FOR_STATE[study.state] || []).filter(p => (s.skills || {})[p]) : [];
    useEffect(() => { if (it && it.study && study && (!skill || !procs.includes(skill))) setSkill(procs[0] || ''); }, [intent, target]);
    const theSkill = it ? (it.study ? skill : it.skill) : null;
    const cfg = theSkill ? (s.skills || {})[theSkill] : null;
    const proc = theSkill ? NL.PROC[theSkill] || {} : {};
    const needsProject = cfg && cfg.level === 'project';
    const blocked = needsProject && study && !study.has_project ? 'This study has no project repo yet. It gets one once its proposal is approved.' : null;
    const go = async () => {
      if (!theSkill) return;
      const body = { skill: theSkill, ...optBody(opts) };
      if (it.study || it.target) { if (target && target !== 'hub') body.target = target; else if (it.study) return NL.toast('Choose a study', 'warn'); }
      if (cfg && cfg.args && cfg.args.includes('text') && arg.trim()) body.args = arg.trim();
      if (it.arg === 'text' && arg.trim()) body.args = arg.trim();
      const r = await NL.launch(body);
      if (r) onClose();
    };
    const sendAsk = async () => {
      if (!ask.trim()) return;
      if (NL.quickAnswer && NL.quickAnswer(ask.trim(), NL.getState())) { onClose(); return NL.open(NL.AnswerSheet, { text: ask.trim(), target, onAgent: () => NL.launch({ prompt: ask.trim(), target: target && target !== 'hub' ? target : 'hub', ...optBody({ ...opts, chain: 'off' }) }) }, { key: 'answer' }); }
      const r = await NL.launch({ prompt: ask.trim(), target: target && target !== 'hub' ? target : 'hub', ...optBody({ ...opts, chain: 'off' }) });
      if (r) onClose();
    };
    const sub = it && it.campaign ? 'Agents use the selected project’s machine and account. A campaign may approve only the checkpoints you let it, within the limits you set; everything else waits for you.'
      : 'Agents use the selected project’s machine and account. Checkpoints follow your workflow’s approval settings.';
    return html`<${NL.Sheet} title="Start task" sub=${sub} onClose=${onClose} wide>
      <div class="asknewt-big">
        <label class="field-label">Ask a question or give an instruction</label>
        <${NL.Textarea} rows="3" value=${ask} onInput=${setAsk} onSubmit=${sendAsk} autofocus=${!initial && !initSkill}
          placeholder="e.g. “Compare the last three trial runs of moe and say which setting mattered”. Ctrl+Enter sends." />
        <div class="row"><span class="muted small">Starts a run in ${study ? html`<b>${study.title || study.id}</b>` : 'the lab'}. It can use any procedure; checkpoint decisions follow your workflow.</span><span class="grow"></span>
          <${NL.Btn} kind="primary" disabled=${!ask.trim()} onClick=${sendAsk}>Send</${NL.Btn}></div>
      </div>
      <${LaunchOptions} opts=${opts} setOpts=${setOpts} target=${target} allowChain=${!!theSkill&&cfg?.mode!=='interactive'} allowRepeat=${!!theSkill&&cfg?.mode!=='interactive'}/><div class="or"><span>or start a procedure</span></div>
      <${NL.ChoiceTiles} value=${intent} onChange=${setIntent} options=${INTENTS.map(i => ({ value: i.id, glyph: i.glyph, title: i.title, desc: i.desc }))} />
      ${it && it.campaign ? html`<${CampaignForm} onDone=${onClose} />` : null}
      ${it && !it.campaign ? html`<div class="intent-detail">
        ${(it.study || it.target) ? html`<${StudyPicker} value=${target} onChange=${setTarget} allowLab=${it.target === 'study?'} filter=${i => !NL.isTerminal(i.state)} />` : null}
        ${it.study && study ? html`<${NL.Field} label="What to do"><div class="procs">${procs.length ? procs.map(p => html`<button type="button" class=${cls('proc', skill === p && 'on')} onClick=${() => setSkill(p)}>
          <b>${NL.procTitle(p)}</b><small>${(NL.PROC[p] || {}).does || ''}</small></button>`) : html`<span class="muted">Nothing to start for a study in “${NL.STATE_LABEL[study.state]}”.</span>`}</div></${NL.Field}>` : null}
        ${theSkill && !(it.study && !study) ? html`<div class="explain">
          <div><b>What happens:</b> ${proc.does || NL.procTitle(theSkill)}</div>
          <div><b>Where:</b> ${needsProject ? 'inside the study’s project repo' : study ? 'in the lab, on this study' : 'in the lab'}</div>
          ${proc.stops ? html`<div><b>Stops:</b> ${proc.stops}</div>` : null}
          ${cfg && cfg.mode === 'interactive' ? html`<div><b>Talks with you:</b> one question at a time, answered right here</div>` : null}
          ${blocked ? html`<div class="warn">${blocked}</div>` : null}
          <div class="muted mono small">/${theSkill}${study && cfg && cfg.args.startsWith('slug') ? ' ' + study.id : ''}${arg ? ' ' + arg : ''}</div></div>` : null}
        ${it.arg === 'text' || (cfg && it.study && cfg.args.includes('text')) ? html`<${NL.Field} label=${it.argLabel || 'Notes for the agent (optional)'}>
          <${NL.Input} value=${arg} onInput=${setArg} placeholder=${it.placeholder || ''} onEnter=${go} /></${NL.Field}>` : null}
        <div class="row end"><${NL.Btn} kind="primary" disabled=${!theSkill || !!blocked || (it.study && !study)} onClick=${go}>Start</${NL.Btn}></div>
      </div>` : null}
    </${NL.Sheet}>`;
  };
  NL.openStart = (props) => NL.open(NL.StartSheet, props || {}, { key: 'start' });
  NL.openAsk = (text, target) => NL.open(AskConfirm, { text: text || '', target: target || 'hub' }, { kind: 'dialog', key: 'ask' });

  const AskConfirm = ({ text, target, onSent, onClose }) => {
    const s = NL.useLab();
    const [t, setT] = useState(text);
    const [tgt, setTgt] = useState(target);
    const [opts, setOpts] = useState(DEFAULT_OPTS);
    const go = async () => { const r = await NL.launch({ prompt: t.trim(), target: tgt || 'hub', ...optBody({ ...opts, chain: 'off' }) }); if (r) { onSent && onSent(); onClose(); } };
    return html`<div class="dialog dialog-wide"><h3>New instruction</h3>
      <${NL.Textarea} rows="4" value=${t} onInput=${setT} onSubmit=${go} autofocus />
      <${StudyPicker} label="Where" value=${tgt} onChange=${setTgt} allowLab />
      <${LaunchOptions} opts=${opts} setOpts=${setOpts} target=${tgt} />
      <p class="muted small">A run on your account. It can use any lab procedure but cannot approve checkpoints.</p>
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!t.trim()} onClick=${go}>Send</${NL.Btn}></div></div>`;
  };

  /* ── Plan a campaign (writes and approves lab/campaigns/<date>-<slug>.md) ───── */
  /* what a walk-away start needs, checked live (GET /api/campaign/preflight) */
  NL.Preflight = ({ onReady }) => {
    const read = NL.useGet('/api/campaign/preflight'), p = read.data;
    useEffect(() => { onReady && onReady(!!p?.ready); }, [p]);
    if (!p) return html`<${NL.LoadState} ...${read} />`;
    return html`<div class="preflight">${(p.checks || []).map(c => html`<div class=${cls('pf-row', c.ok ? 'ok' : c.warn_only ? 'warn' : 'bad')} key=${c.id}>
        <span class="pf-ico">${c.ok ? '✓' : c.warn_only ? '!' : '✕'}</span><span class="pf-t"><b>${c.label}</b>${c.detail ? html`<small>${c.detail}</small>` : null}</span>
        ${!c.ok && c.fix ? html`<a class="link small" href=${'#/' + c.fix} onClick=${() => NL.closeTop && NL.closeTop()}>fix →</a>` : null}</div>`)}
      <div class="row end"><button type="button" class="link small" onClick=${read.reload}>check again</button></div></div>`;
  };

  const CampaignForm = ({ onDone }) => {
    const s = NL.useLab();
    const [f, setF] = useState({ direction: '', name: '', ideas: 3, parallel: 1, compute_total: '', full_budget: '',
      max_open_questions: 2, mode: 'execute', explore_rounds: 1, explore_lines: 2, hours: 12, agent_hours: null,
      cycle_minutes: 90, repeat_minutes: 20, delegates: [], spend_cap: '' });
    const [ready, setReady] = useState(false);
    const [more, setMore] = useState(false);
    const set = (k, v) => setF(o => ({ ...o, [k]: v }));
    const autoAgentHours = Math.max(0, (+f.hours || 0) * Math.max(1, +f.parallel || 1));
    const agentHours = f.agent_hours == null ? autoAgentHours : f.agent_hours;
    const until = new Date(Date.now() + (+f.hours || 0) * 3600e3);
    const spendCap = Math.max(0, +f.spend_cap || 0);
    const labName = (s.lab_info || {}).name || 'this lab';
    const machine = s.remote ? s.remote.name : 'this computer';
    // the checkpoints a campaign may be allowed to approve: those whose approver is "me-or-campaign"
    const seen = new Set(), cps = NL.WORKFLOWS.flatMap(w => (w.checkpoints || []).map(c => ({ ...c, wf: w.title || w.id })))
      .filter(c => !seen.has(c.id) && seen.add(c.id));
    const tiles = cps.map(c => ({ value: c.id, glyph: 'diamond', title: c.title, desc: c.approver === 'me-or-campaign' ? `${c.wf} · ${NL.cpWhere(c)}` : 'only you approve this one',
      disabled: c.approver !== 'me-or-campaign', why: 'Only you approve this checkpoint. Change that in Workflow to let a campaign approve it.' }));
    const sign = async (launch) => {
      if (!f.direction.trim()) return NL.toast('Describe the direction first', 'warn');
      const names = f.delegates.map(id => (cps.find(c => c.id === id) || {}).title || id);
      const body = html`<div><p>${names.length ? html`The campaign may approve <b>${names.join(', ')}</b> for its studies only if the evidence fits these bounds and every check passes. Every other checkpoint waits for you.`
          : html`<b>Every checkpoint waits for you.</b> The campaign carries the work up to each one and moves on to other ideas meanwhile.`}</p>
        <p>${spendCap ? html`It stops when its runs have spent <b>$${spendCap.toFixed(2)}</b> (estimated from token use), and writes its final report.` : html`<b>No spending cap.</b> It can spend until its hours run out.`}</p>
        <p class="muted">It runs in ${labName} on ${machine} until ${NL.when(until)}${+agentHours ? ` or ${+agentHours} agent-hours, whichever comes first` : ''}. ${launch ? '' : 'Approving only records it; you start it later. '}Pause, stop or take a checkpoint back any time from its card.</p></div>`;
      const ok = await NL.confirm({ title: 'Approve this campaign?', ok: launch ? 'Approve and start' : 'Approve', body });
      if (!ok) return;
      const fields = { ...f, agent_hours: +agentHours || 0, spend_cap: spendCap };
      const r = await NL.act('/api/campaign', { confirm: true, fields, launch });
      if (r.ok) { onDone && onDone(); if (r.campaign) NL.go('studies?campaign=' + encodeURIComponent(r.campaign)); }
    };
    return html`<div class="intent-detail campaign-form">
      <p class="lede">A campaign carries several ideas toward your checkpoints while you're away. Each <b>pass</b>, it looks at every idea and starts its next step.</p>
      <${NL.Field} label="Research direction"><${NL.Textarea} rows="2" value=${f.direction} onInput=${v => set('direction', v)} placeholder="what the campaign explores" /></${NL.Field}>
      <div class="grid3">
        <${NL.Field} label="Ideas to carry"><${NL.Input} type="number" min="1" value=${f.ideas} onInput=${v => set('ideas', v)} /></${NL.Field}>
        <${NL.Field} label="At once" hint="ideas in flight together"><${NL.Input} type="number" min="1" value=${f.parallel} onInput=${v => set('parallel', v)} /></${NL.Field}>
        <${NL.Field} label="Run for (hours)" hint=${'until ' + NL.when(until)}><${NL.Input} type="number" min="1" value=${f.hours} onInput=${v => set('hours', v)} /></${NL.Field}>
      </div>
      <h4 class="form-h">Which checkpoints it may approve for you</h4>
      <${NL.ChoiceTiles} multi value=${f.delegates} onChange=${v => set('delegates', v)} options=${tiles} />
      <div class="grid2">
        <${NL.Field} label="Budget, for the agents to plan by" hint="in the brief; the Compute instrument tracks it"><${NL.Input} value=${f.compute_total} onInput=${v => set('compute_total', v)} placeholder="e.g. 40 GPU-hours" /></${NL.Field}>
        <${NL.Field} label="Full-scale runs per study" hint="what a study's full runs may use"><${NL.Input} value=${f.full_budget} onInput=${v => set('full_budget', v)} placeholder="e.g. 3 runs × 60 min" /></${NL.Field}>
        <${NL.Field} label="Spending cap ($)" hint=${spendCap ? 'a hard stop, estimated from token use' : 'blank = no cap'}><${NL.Input} type="number" min="0" step="1" value=${f.spend_cap} onInput=${v => set('spend_cap', v)} placeholder="no cap" /></${NL.Field}>
        <${NL.Field} label="Agent-hours" hint=${f.agent_hours == null ? 'hours × at once · 0 = only the clock' : html`0 = only the clock · <button type="button" class="link small" onClick=${() => set('agent_hours', null)}>back to ${autoAgentHours}</button>`}><${NL.Input} type="number" min="0" value=${agentHours} onInput=${v => set('agent_hours', v)} /></${NL.Field}>
      </div>
      <button type="button" class="link small" onClick=${() => setMore(!more)}>${more ? 'Fewer options' : 'More options…'}</button>
      ${more ? html`<div class="grid3">
        <${NL.Field} label="A pass every (min)"><${NL.Input} type="number" min="5" value=${f.repeat_minutes} onInput=${v => set('repeat_minutes', v)} /></${NL.Field}>
        <${NL.Field} label="Longest pass (min)"><${NL.Input} type="number" min="10" value=${f.cycle_minutes} onInput=${v => set('cycle_minutes', v)} /></${NL.Field}>
        <${NL.Field} label="Open questions allowed at scoping"><${NL.Input} type="number" min="0" value=${f.max_open_questions} onInput=${v => set('max_open_questions', v)} /></${NL.Field}>
        <${NL.Field} label="Research loops"><${NL.Seg} value=${f.mode} onChange=${v => set('mode', v)} options=${[{ value: 'execute', label: 'Follow the plan' }, { value: 'explore', label: 'Explore' }]} /></${NL.Field}>
        <${NL.Field} label="Name" hint="optional"><${NL.Input} value=${f.name} onInput=${v => set('name', v)} placeholder="e.g. routing-sprint" /></${NL.Field}>
      </div>` : null}
      <${NL.Section} title="Checks before you start"><${NL.Preflight} onReady=${setReady} /></${NL.Section}>
      <div class="row end"><span class="muted small">${ready ? `${f.ideas} ideas · ${f.hours} h · ${f.delegates.length ? NL.plural(f.delegates.length, 'checkpoint') + ' delegated' : 'nothing delegated'}` : 'Fix the checks above before starting.'}</span>
        <${NL.Btn} onClick=${() => sign(false)}>Approve, start later</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!ready} onClick=${() => sign(true)}>Approve and start</${NL.Btn}></div></div>`;
  };
})();
