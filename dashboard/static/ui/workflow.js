/* ARLOtope — one study's own instructions, and agents' suggestions for the lab's.
   The lab-wide definition (steps, workflows, procedures and their variants, roles, rules, rooms…) is edited in
   Compose (compose.js). Here: the study page's Instructions tab — instructions ADDED to a procedure or to a
   whole step for this study only, saved at once (studies/<slug>/workflow/), and which variant does a procedure
   for it — and an agent's proposal, which the PI accepts or declines. The skill itself is shown read-only. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useMemo, cls } = NL;

  const studyCustom = (s, study) => (((s.workflow || {}).study_custom || {})[study]) || { procedures: {}, steps: {} };

  /* a small line diff (yours vs the default · the draft vs the lab) */
  function lineDiff(a, b) {
    const A = a ? a.split('\n') : [], B = b ? b.split('\n') : [];
    if (A.length * B.length > 250000) return [{ t: '=', s: '(too long to compare line by line)' }];
    const n = A.length, m = B.length, L = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    const out = []; let i = 0, j = 0;
    while (i < n && j < m) { if (A[i] === B[j]) { out.push({ t: '=', s: A[i] }); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) out.push({ t: '-', s: A[i++] }); else out.push({ t: '+', s: B[j++] }); }
    while (i < n) out.push({ t: '-', s: A[i++] }); while (j < m) out.push({ t: '+', s: B[j++] });
    return out;
  }
  /** a line diff; `context` folds long unchanged runs */
  NL.Diff = ({ a, b, context }) => {
    const d = useMemo(() => {
      const all = lineDiff(a, b);
      if (!context) return all;
      const near = i => all.slice(Math.max(0, i - context), i + context + 1).some(y => y.t !== '=');
      const out = []; let gap = 0;
      all.forEach((x, i) => { if (x.t !== '=' || near(i)) { if (gap) out.push({ t: '…', s: `${gap} unchanged line${gap === 1 ? '' : 's'}` }); gap = 0; out.push(x); } else gap++; });
      if (gap) out.push({ t: '…', s: `${gap} unchanged line${gap === 1 ? '' : 's'}` });
      return out;
    }, [a, b, context]);
    return html`<pre class="diff">${d.map(x => html`<div class=${cls('dl', x.t === '+' && 'add', x.t === '-' && 'del', x.t === '…' && 'gap')}><i>${x.t === '=' || x.t === '…' ? ' ' : x.t}</i>${x.s || ' '}</div>`)}</pre>`;
  };

  /* the editor for one of the study's layers (saved at once) */
  const LayerEditor = ({ kind, name, study, value, placeholder, onSaved, rows }) => {
    const key='nl-instruction-draft:'+JSON.stringify([NL.getState()?.lab_info?.path||location.origin,study,kind,name]);
    const [text, setText] = useState(()=>NL.ls.get(key,null)?.text??value??'');
    useEffect(() => setText(NL.ls.get(key,null)?.text??value??''), [value, key]);
    const dirty = text !== (value || '');
    const change=v=>{setText(v);NL.ls.set(key,v===value?null:{text:v})};
    const clear=()=>{NL.ls.set(key,null);setText(value||'')};
    const save = async () => { const r = await NL.act('/api/workflow/save', { kind, name, study, text }, 'Saved for this study'); if(r.ok){NL.ls.set(key,null);if(onSaved)onSaved()} };
    return html`<div class="wf-editor">
      <${NL.Textarea} value=${text} rows=${rows || 7} onInput=${change} placeholder=${placeholder} mono onSubmit=${save} />
      ${dirty?html`<div class="row between small muted"><span>Unsaved draft kept in this browser.</span><button type="button" class="link small" onClick=${clear}>Discard draft</button></div>`:null}
      <div class="row end gap">${value ? html`<${NL.Btn} small kind="ghost" onClick=${async () => { if (await NL.confirm({ title: 'Remove these instructions?', ok: 'Remove', body: 'This study goes back to what the lab does.' })) { const r = await NL.act('/api/workflow/save', { kind, name, study, text: '' }, 'Removed'); if(r.ok){NL.ls.set(key,null);setText('');if(onSaved)onSaved()} } }}>Remove</${NL.Btn}>` : null}
        <${NL.Btn} small kind="primary" disabled=${!dirty} onClick=${save}>Save for this study</${NL.Btn}></div></div>`;
  };

  /* ── one procedure, for one study: added instructions · which variant does it · its skill · what the agent reads ── */
  NL.ProcedureSheet = ({ name, study, onClose }) => {
    const [tab, setTab] = useState('instructions');
    const g = NL.useGet('/api/workflow/item?kind=procedure&name=' + encodeURIComponent(name) + '&study=' + encodeURIComponent(study));
    const d = g.data, reload = g.reload;
    const p = (NL.WF.procedures || {})[name] || {};
    const layer = (d && d.study_layer) || {};
    const tabs = [{ id: 'instructions', label: 'Instructions' }, ...((d && (d.variants || []).length) ? [{ id: 'variant', label: 'Variant' }] : []),
      { id: 'skill', label: 'Its skill' }, { id: 'brief', label: 'What the agent reads' }];
    return html`<${NL.Sheet} wide kicker=${'For this study · /' + name} title=${p.title || '/' + name} sub=${p.does || ''} onClose=${onClose}>
      ${!d ? html`<${NL.LoadState} ...${g} />` : html`
        <${NL.Tabs} tabs=${tabs} value=${tab} onChange=${setTab} />
        ${tab === 'instructions' ? html`
          <p class="muted">Added to <b>${p.title || name}</b> whenever it runs on <b>${study}</b>, on top of its skill. Preferences, datasets or baselines to use, things to avoid.</p>
          <${LayerEditor} kind="add" name=${name} study=${study} value=${layer.add} onSaved=${reload}
            placeholder=${'e.g.\n- The baseline for this study is the 2024 MoE router.\n- Run everything on CPU.'} />
          ${d.lab && d.lab.add ? html`<${NL.Section} title="Also applies: the lab's"><${NL.Markdown} text=${d.lab.add} /></${NL.Section}>` : null}` : null}
        ${tab === 'variant' ? html`<${VariantTab} d=${d} name=${name} study=${study} />` : null}
        ${tab === 'skill' ? html`
          <p class="muted">The procedure's skill, as every study gets it. Its outcomes and outputs bind whatever the instructions say.</p>
          ${(p.outputs || []).length ? html`<${NL.Section} title="It must produce"><ul>${p.outputs.map(o => html`<li>${o}</li>`)}</ul></${NL.Section}>` : null}
          <div class="wf-contract"><${NL.Markdown} text=${d.skill} /></div>` : null}
        ${tab === 'brief' ? html`
          <p class="muted">Exactly what an agent running <span class="mono">/${name}</span> on ${study} reads first (sha <span class="mono">${d.brief_sha}</span>; each run records the version it used).</p>
          <pre class="wf-brief">${d.brief}</pre>` : null}
        <div class="row end"><a class="link small" href=${'#/compose/procedure/' + name} onClick=${onClose}>Change it lab-wide in Workflow →</a></div>`}
    </${NL.Sheet}>`;
  };

  /* which variant of a procedure does it for this study (the study's own swap, over its workflow's) */
  const VariantTab = ({ d, name, study }) => {
    const s = NL.useLab();
    const it = ((s.items || []).find(x => x.id === study)) || {};
    const own = (it.use || {})[name] || '';
    const set = async v => {
      const use = { ...(it.use || {}) };
      if (v) use[name] = v; else delete use[name];
      await NL.act('/api/study/use', { study, use }, v ? `${study} uses /${v} for /${name}` : `${study} uses its workflow's /${name}`);
    };
    return html`<div>
      <p class="muted">A variant is another skill that does this procedure's job its own way. Pick one for <b>${study}</b> only; make new ones under Workflow.</p>
      <${NL.Seg} value=${own} onChange=${set} options=${[{ value: '', label: 'The workflow’s' }, ...d.variants.map(v => ({ value: v, label: NL.procTitle(v) }))]} />
    </div>`;
  };

  /* instructions for one step of a study's workflow, whichever procedure does it */
  const StudyStepSheet = ({ step, study, onClose }) => {
    const g = NL.useGet('/api/workflow/item?kind=step&name=' + encodeURIComponent(step) + '&study=' + encodeURIComponent(study));
    const d = g.data;
    const label = NL.STATE_LABEL[step] || step;
    return html`<${NL.Sheet} kicker="For this study · the whole step" title=${label} onClose=${onClose}>
      ${!d ? html`<${NL.LoadState} ...${g} />` : html`
        <p class="muted">Added to every procedure that runs at <b>${label}</b> on <b>${study}</b>.</p>
        <${LayerEditor} kind="step" name=${step} study=${study} rows=${5} value=${(d.study_layer || {}).add} onSaved=${g.reload}
          placeholder="e.g. Keep every run at this step under 2 GPU-hours." />`}
    </${NL.Sheet}>`;
  };

  /* ── an agent's proposal ─────────────────────────────────────────────── */
  const PROPOSAL_ITEM = { add: 'procedure', step: 'step', role: 'role' };
  NL.ProposalSheet = ({ id, onClose }) => {
    const g = NL.useGet('/api/workflow/proposal?id=' + encodeURIComponent(id)), r = g.data;
    const current = NL.useGet(r ? `/api/workflow/item?kind=${PROPOSAL_ITEM[r.kind] || 'procedure'}&name=${encodeURIComponent(r.name)}${r.study ? '&study=' + encodeURIComponent(r.study) : ''}` : null);
    const cur = current.data;
    const decide = async accept => { const x = await NL.act('/api/workflow/proposal', { id, accept }, accept ? 'Accepted' : 'Declined'); if (x.ok) onClose(); };
    const layer = cur && (r && r.study ? cur.study_layer || {} : cur.lab || {});
    const before = (layer && layer.add) || '';
    const after = !r ? '' : (before ? before + '\n\n' : '') + r.text;
    const what = r && r.ok ? (r.kind === 'step' ? 'the step ' + (NL.STATE_LABEL[r.name] || r.name) : r.kind === 'role' ? 'the role ' + r.name : '/' + r.name) : '';
    return html`<${NL.Sheet} wide kicker="An agent suggests" title=${r && r.ok ? 'Instructions for ' + what : 'A suggested change'}
      sub=${r && r.ok ? (r.study ? 'for ' + r.study : 'for the whole lab') : ''} onClose=${onClose}
      footer=${r && r.ok && r.status === 'pending' ? html`<${NL.Btn} kind="ghost" onClick=${() => decide(false)}>Decline</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!cur} onClick=${() => decide(true)}>Accept</${NL.Btn}>` : null}>
      ${!r ? html`<${NL.LoadState} ...${g} />` : html`
        ${r.why ? html`<blockquote class="quote">${r.why}</blockquote>` : null}
        <div class="muted small">from ${r.by ? html`<a class="link" href=${'#/run/' + r.by}>run ${r.by}</a>` : 'an agent'} · ${NL.ago(r.ts)} · ${r.status}</div>
        ${!cur ? html`<${NL.LoadState} ...${current} />` : html`<${NL.Section} title="What changes"><${NL.Diff} a=${before} b=${after} /></${NL.Section}>`}`}
    </${NL.Sheet}>`;
  };

  /* ── a study's own instructions (the study page's Instructions tab): its workflow's steps, each with the
     procedures that run there ─────────── */
  NL.StudyInstructions = ({ it }) => {
    const s = NL.useLab();
    const mine = studyCustom(s, it.id);
    return html`<div>
      <p class="lede">Instructions for this study only, added on top of the lab's.</p>
      <p class="muted">Useful for “use dataset Y”, “the baseline is Z”, “this study runs on CPU”. To change the whole lab, use <a class="link" href="#/compose">Workflow</a>.</p>
      ${NL.stepsOf(it).map(st => { const here = it.state === st; const procs = [NL.doesFor(it, st), ...((NL.STEPS[st] || {}).also || [])].filter(Boolean);
        return html`<div class=${cls('wf-srow', here && 'cur')} key=${st}>
        <b>${NL.STATE_LABEL[st] || st}</b>${here ? html` <${NL.Pill} tone="live">now</${NL.Pill}>` : null}
        <span class="row gap wrap">${procs.map(p => html`<button type="button" class=${cls('chip', (mine.procedures || {})[p] && 'on')} onClick=${() => NL.open(NL.ProcedureSheet, { name: p, study: it.id })}>${NL.procTitle(p)}${(mine.procedures || {})[p] ? ' · +' : ''}</button>`)}
          <button type="button" class="link small" onClick=${() => NL.open(StudyStepSheet, { step: st, study: it.id })}>whole step${(mine.steps || {})[st] ? ' · +' : ''}…</button></span></div>`; })}
    </div>`;
  };
})();
