/* ARLOtope — checkpoints: the Permit (one sheet for every checkpoint of every workflow: what it covers,
   the exhibits, its checks, the agent's case, a note to agents, and hold-to-approve), the research loop's
   approval, and moving a study back onto its workflow. Every decision is a record (POST /api/checkpoint/decide →
   lab/journal.jsonl); `arlo approve <study> <checkpoint>` does the same from a terminal. Approving a `before`
   checkpoint the study waits at carries its move; "approve and start" also starts the new step's procedure. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, cls } = NL;

  const LETTERS = 'ABCDEFGHIJKL';
  const BY = by => by === 'pi' ? 'you' : by === 'auto' ? 'its checks (automatic)' : String(by||'').startsWith('judge:') ? 'the independent reviewer' : String(by || '').startsWith('campaign:') ? 'the campaign ' + by.slice(9).replace(/^\d{4}-\d{2}-\d{2}-/, '') : by;
  const VIA = { dashboard: 'in the dashboard', cli: 'from a terminal', keeper: 'by the campaign keeper', kernel:'by the workflow engine', migration: 'carried over from the old marks' };

  const sentence = (cp, it) => {
    const who = html`<b>${(it && (it.title || it.id)) || ''}</b>`;
    return cp.before ? html`Before ${who} moves to <b>${NL.STATE_LABEL[cp.before] || cp.before}</b>, ${cp.approver==='agent'?'the independent reviewer decides':cp.approver==='auto'?'its checks must pass':'you approve it'}.`
      : html`During <b>${NL.STATE_LABEL[cp.during] || cp.during}</b> on ${who}: before ${cp.at || 'the point it names'}, the agent stops and asks you.`;
  };

  const Led = ({ code }) => html`<i class=${cls('led', code == null ? 'led-off' : code === 0 ? 'led-ok' : code === 2 ? 'led-warn' : 'led-bad')}></i>`;

  NL.CheckpointSheet = ({ study, id, onClose }) => {
    const s = NL.useLab();
    const it = NL.item(s, study) || { id: study, title: study };
    const { data: r, error, reload: load } = NL.useGet(`/api/checkpoint?${NL.qs({ study, id })}`, JSON.stringify((it.checkpoints || {})[id] || {}));
    const [note, setNote] = NL.useDraft('checkpoint:' + study + ':' + id + ':note', '');
    const [changes, setChanges] = useState(false);
    const [checking, setChecking] = useState(false);
    const [typed, setTyped] = useState('');
    const cp = (r && r.checkpoint) || NL.checkpoint(id, it) || { id, title: id };
    const rec = (r && r.record) || ((it.checkpoints || {})[id]) || null;
    const approved = rec && rec.decision === 'approved';
    const decide = async (decision, start) => {
      const x = await NL.act('/api/checkpoint/decide', { study, checkpoint: id, decision, note: note.trim(), start: !!start, confirm: true, typed });
      if (x.ok) { setNote(''); setChanges(false); load(); if (x.launch && x.launch.run_id) NL.openRun(x.launch.run_id); }
      return x;
    };
    const runChecks = async () => { setChecking(true); const x = await NL.api('/api/checkpoint/checks', { study, checkpoint: id }); setChecking(false);
      if (x.error) NL.toast(x.error, 'bad'); load(); };
    const readAll = async () => NL.open(NL.SectionsSheet, { title: `${cp.title} · the evidence`, data: await NL.api('/api/read', { what: 'checkpoint', idea: study, checkpoint: id }) });
    // a `before` checkpoint the study waits at: approving moves it there, and can start that step's procedure
    const graph=it.active_steps!=null,waiting=cp.before&&r?.waiting;
    const held = !!s.holds?.[study];
    const nextProc = waiting && !held ? (graph?'workflow':NL.doesFor(it, cp.before)) : null;
    const thenTitle = nextProc ? (graph?'continue workflow':NL.procTitle(nextProc)) : null;
    const asking = r && r.asking;
    const state = approved ? 'approved' : rec && rec.decision === 'revoked' ? 'revoked' : 'waiting';
    const needType = cp.confirm === 'type' && !approved;
    if (!r) return html`<${NL.Sheet} title="Checkpoint" onClose=${onClose}><${NL.LoadState} error=${error} reload=${load} /></${NL.Sheet}>`;
    return html`<aside class="sheet sheet-permit" role="dialog" aria-modal="true" aria-label=${cp.title}>
      <header class="permit-head">
        <${NL.Seal} state=${state} size=${68} />
        <div class="grow"><div class="kicker">Checkpoint · ${NL.workflowOf(it).title || 'workflow'}</div>
          <h2>${cp.title}</h2><p class="permit-sentence">${sentence(cp, it)}</p></div>
        <button class="x" aria-label="close" onClick=${onClose}><${NL.Icon} name="x" /></button></header>
      <div class="sheet-body permit-body">
        ${cp.means ? html`<p class="permit-means">It covers ${cp.means}.</p>` : null}
        ${approved ? html`<div class="stamp"><b>Approved</b> by ${BY(rec.by)} ${VIA[rec.via] || ''} · ${NL.when(rec.ts)}${rec.note ? html`<div class="stamp-note">“${rec.note}”</div>` : null}</div>` : null}
        ${rec && rec.decision === 'outdated' ? html`<div class="note note-warn">You approved this ${NL.ago(rec.ts)}, but the checkpoint has changed since. Approve it again as it is now.</div>` : null}
        ${!approved && rec && rec.decision === 'changes-requested' ? html`<div class="note note-warn">Changes requested ${NL.ago(rec.ts)}: “${rec.note}”</div>` : null}
        ${(it.slipped || []).some(x => x.id === id) ? html`<div class="note note-bad">Work went past this checkpoint without your approval: ${(it.slipped.find(x => x.id === id) || {}).why}.</div>` : null}

        <section class="permit-sec"><h4>Exhibits <button type="button" class="link small" onClick=${readAll}>read them all</button></h4>
          <div class="exhibits">${((r && r.evidence) || []).map((e, i) => html`<button type="button" class=${cls('exhibit', !e.exists && 'missing')} onClick=${readAll}>
            <span class="ex-l">${LETTERS[i]}</span><span class="grow clip"><b>${e.name}</b><small class="mono">${e.path}</small></span><span class="muted small">${e.exists ? (e.dir ? 'folder' : 'open') : 'not yet'}</span></button>`)}
            ${r && !(r.evidence || []).length ? html`<div class="muted small">This checkpoint names no evidence. Its workflow can add some (Workflow → the checkpoint).</div>` : null}
            ${!r ? html`<${NL.Spinner} />` : null}</div></section>

        ${(cp.checks || []).length ? html`<section class="permit-sec"><h4>Checks <button type="button" class="link small" disabled=${checking} onClick=${runChecks}>${checking ? 'running…' : 'run them now'}</button></h4>
          ${((r && r.checks) || cp.checks.map(n => ({ name: NL.checkName(n) }))).map(c => html`<div class="check-row"><${Led} code=${c.code} /><b>${c.name}</b>
            <span class="muted small grow clip">${c.code == null ? 'not run yet' : c.code === 0 ? 'passed' : c.code === 2 ? 'needs a look' : `failed (exit ${c.code})`}</span></div>`)}
          ${r && r.checked_at ? html`<div class="muted small">last run ${NL.ago(r.checked_at)}</div>` : null}</section>` : null}

        ${asking ? html`<section class="permit-sec"><h4>The agent's case</h4><blockquote class="voice"><span class="voice-who">${NL.procTitle(asking.skill)} · ${NL.ago(asking.finished)}</span>
          “${asking.summary || 'It stopped here and asked you.'}”<button type="button" class="link small" onClick=${() => NL.openRun(asking.run_id)}>open the run</button></blockquote></section>` : null}

        ${asking && cp.before && !r.waiting ? html`<p class="muted small">Approval does not finish the current task. Continue the agent from its run.</p>` : null}
        ${!approved ? html`<section class="permit-sec"><h4>${changes ? 'What should change' : 'A note to agents'} <span class="muted small">${changes ? 'goes to the agent that asked' : 'optional; goes into every later brief for this study'}</span></h4>
          <${NL.Textarea} rows="3" value=${note} onInput=${setNote} placeholder=${changes ? 'e.g. add a dense baseline at the same compute before the full runs' : 'e.g. keep it under 120 GPU-hours; top-2 routing first'} />
          ${needType ? html`<${NL.Field} label=${html`Type <b class="mono">${study}</b> to approve`}><${NL.Input} value=${typed} onInput=${setTyped} mono /></${NL.Field}>` : null}</section>` : null}
      </div>
      <footer class="permit-foot">
        ${held ? html`<p class="muted small" style=${{flexBasis:'100%',margin:0}}>This study is on hold. Decisions can be recorded; release it to start new agents.</p>` : null}
        ${!approved&&cp.approver==='agent'?html`<${NL.Btn} disabled=${held} onClick=${async()=>{const x=await NL.act('/api/checkpoint/gate',{study,checkpoint:id,review:true,confirm:true},'Review queued');if(x.run_id)NL.openRun(x.run_id);load()}}>Request independent review</${NL.Btn}>`:null}
        ${!approved&&cp.decisions?html`<div class="row wrap">${Object.keys(cp.decisions).map(choice=>html`<${NL.Btn} small disabled=${needType&&typed.trim()!==study} onClick=${async()=>{const x=await NL.act('/api/checkpoint/gate',{study,checkpoint:id,choice,note,typed,confirm:true},'Decision recorded');if(x.ok)load()}}>${(cp.approver==='agent'?'Override: ':'')+choice.replaceAll('-',' ')}</${NL.Btn}>`)}</div>`:null}
        ${approved ? html`<${NL.Btn} kind="ghost" onClick=${async () => { if (await NL.confirm({ title: `Take back “${cp.title}”?`, body: 'The approval stays in the record, marked revoked. Work it started keeps going unless you stop it.', ok: 'Take it back', danger: true })) decide('revoked'); }}>Take the approval back</${NL.Btn}>
          ${graph&&it.runnable?.length?html`<${NL.Btn} kind="primary" disabled=${held} onClick=${()=>NL.act('/api/workflow/run',{study,retry:true},'Ready tasks queued')}>Run ready tasks</${NL.Btn}>`:!graph&&cp.before && it.state === cp.before && NL.nextSkill(it) ? html`<${NL.Btn} kind="primary" disabled=${held} onClick=${() => NL.launch({ skill: NL.nextSkill(it), target: study })}>Start ${NL.procTitle(NL.nextSkill(it))}</${NL.Btn}>` : null}`
        : cp.decisions ? null : changes ? html`<${NL.Btn} onClick=${() => setChanges(false)}>Back</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!note.trim()} onClick=${() => decide('changes-requested')}>Send to the agent</${NL.Btn}>`
        : html`<${NL.Btn} kind="ghost" onClick=${() => setChanges(true)}>Request changes</${NL.Btn}>
          <span class="grow"></span>
          ${nextProc ? html`<${NL.HoldButton} kind="soft" disabled=${needType && typed.trim() !== study} onHold=${() => decide('approved', false)} sub="hold to approve only">Approve</${NL.HoldButton}>
            <${NL.HoldButton} disabled=${needType && typed.trim() !== study} onHold=${() => decide('approved', true)} sub="hold to approve">Approve and ${thenTitle.toLowerCase()}</${NL.HoldButton}>`
          : html`<${NL.HoldButton} disabled=${needType && typed.trim() !== study} onHold=${() => decide('approved')} sub="hold to approve">Approve</${NL.HoldButton}>`}`}
      </footer>
      <div class="permit-cli mono">or in a terminal: arlo approve ${study} ${id}${nextProc ? ' --start' : ''}</div>
    </aside>`;
  };
  NL.openCheckpoint = (study, id) => { if (study && id) NL.open(NL.CheckpointSheet, { study, id }, { key: 'cp' }); };

  /* ── the research loop: approve it (its `approve-loop` checkpoint, with the mode in the note), from the study ── */
  const LOOP = 'approve-loop';
  NL.LoopSheet = ({ slug, onClose }) => {
    const s = NL.useLab();
    const it = NL.item(s, slug) || { id: slug };
    const [doc, setDoc] = useState(null);
    const [mode, setMode] = useState('execute');
    const [note, setNote] = NL.useDraft('loop:' + slug + ':note', '');
    const load = () => NL.api('/api/libdoc', { scope: 'project', slug, rel: 'LOOP_BRIEF.md' }).then(setDoc);
    useEffect(() => { load(); }, [slug]);
    const rec = (it.checkpoints || {})[LOOP];
    const approved = rec && rec.decision === 'approved';
    const go = async launch => {
      const r = await NL.act('/api/checkpoint/decide', { study: slug, checkpoint: LOOP, decision: 'approved', confirm: true,
        note: `mode: ${mode}.${note.trim() ? ' ' + note.trim() : ''}` }, 'Loop approved');
      if (r.ok) setNote('');
      if (r.ok && launch) NL.launch({ skill: 'research-loop', target: slug });
      return r;
    };
    return html`<${NL.Sheet} wide kicker="Run overnight" title=${`The research loop · ${it.title || slug}`} onClose=${onClose}>
      <div class="cols"><div class="col-main">${!doc ? html`<${NL.Spinner} />` : !doc.ok ? html`<${NL.Empty} title="No loop brief yet">The loop drafts its brief the first time it starts; you approve it after.
          <div class="row center"><${NL.Btn} kind="primary" onClick=${() => NL.launch({ skill: 'research-loop', target: slug })}>Start the loop (it drafts the brief)</${NL.Btn}></div></${NL.Empty}>`
        : html`<${NL.Markdown} text=${doc.text} />`}</div>
        <aside class="col-side">${approved ? html`<div class="stamp"><b>Approved</b> ${NL.when(rec.ts)}${rec.note ? html`<div class="stamp-note">${rec.note}</div>` : null}</div>
            <${NL.Btn} kind="primary" onClick=${() => NL.launch({ skill: 'research-loop', target: slug })}>Start the loop</${NL.Btn}>
            <${NL.Btn} kind="ghost" onClick=${() => NL.act('/api/checkpoint/decide', { study: slug, checkpoint: LOOP, decision: 'revoked', confirm: true }, 'Loop approval taken back')}>Take the approval back</${NL.Btn}>`
          : html`<h4>How it works</h4><${NL.ChoiceTiles} value=${mode} onChange=${setMode} columns=${1} options=${[
              { value: 'execute', glyph: 'flask', title: 'Follow the plan', desc: 'Runs the approved plan, then stops.' },
              { value: 'explore', glyph: 'compass', title: 'Explore', desc: 'May widen the plan and reopen supporting decisions, within the study’s checkpoints.' }]} />
            <${NL.Field} label="A note to the loop (optional)"><${NL.Textarea} rows="2" value=${note} onInput=${setNote} /></${NL.Field}>
            <div class="stack"><${NL.HoldButton} onHold=${() => go(true)} sub="hold to approve">Approve and start</${NL.HoldButton}><${NL.Btn} kind="ghost" onClick=${() => go(false)}>Approve, start later</${NL.Btn}></div>`}</aside></div>
    </${NL.Sheet}>`;
  };
  NL.openLoop = slug => NL.open(NL.LoopSheet, { slug }, { key: 'loop' });

  /* move a study to any step of its workflow (bring a parked one back, send one back, skip ahead) */
  const MoveSheet = ({ it, onClose }) => {
    const steps = [...NL.stepsOf(it), ...Object.keys(NL.STEPS).filter(k => NL.isShelved(k))];
    const [to, setTo] = useState(it.was && steps.includes(it.was) ? it.was : steps.includes(it.state) ? it.state : steps[0]);
    const [note, setNote] = NL.useDraft('move:' + it.id + ':note', '');
    const go = async () => {
      const r = await NL.act('/api/study/move', { study: it.id, to, note: note.trim(), confirm: true });
      if (r.ok) { setNote(''); onClose(); }
    };
    return html`<${NL.Sheet} kicker=${NL.isShelved(it.state) ? 'Bring it back' : 'Move it'} title=${it.title || it.id} onClose=${onClose}
      footer=${html`<${NL.Btn} kind="ghost" onClick=${() => { setNote(''); onClose(); }}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!note.trim() || (to === it.state && !(it.waiting || []).length && !it.asks)} onClick=${go}>Move to ${NL.STATE_LABEL[to] || to}</${NL.Btn}>`}>
      <p class="muted">Now at <b>${NL.taskLabel(it)}</b>${it.was ? html`, left from <b>${NL.STATE_LABEL[it.was] || it.was}</b>` : null}. Your move is the decision: no checkpoint on the way is asked, and the move is recorded with your reason.</p>
      <${NL.Field} label="To"><${NL.Select} value=${to} onChange=${setTo} options=${steps.map(st => ({value:st,label:NL.STATE_LABEL[st]||st}))}/></${NL.Field}>
      <${NL.Field} label="Why (recorded)"><${NL.Textarea} rows="2" value=${note} onInput=${setNote} placeholder="e.g. new evidence from …" /></${NL.Field}>
    </${NL.Sheet}>`;
  };
  NL.moveStudy = it => NL.open(MoveSheet, { it });
  NL.revive = NL.moveStudy;
})();
