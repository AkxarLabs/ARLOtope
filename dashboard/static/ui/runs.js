/* ARLOtope — runs as conversations. A run is one agent session the PI started (a procedure or a
   free-form instruction); the run sheet streams it like a chat: the agent's messages, its tool calls
   folded into groups, subagents inline, its questions as forms you answer in place, and the report
   with its next step as a button. Also: the runs list, and the per-agent inspector. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useRef, useMemo, cls } = NL;
  const needsAttention = r => r.needs_followup || r.status === 'waiting_input' || !!r.pending_permissions?.length
    || !!(r.report?.needs_pi && NL.RUN_DONE.has(r.status));

  // Inbox and run-sheet recovery use the same message, session and handoff behavior.
  NL.continueTask = async (id, fresh = false) => {
    const r = NL.run(NL.getState(), id) || (await NL.get('/api/run?' + NL.qs({run_id:id}))).run;
    if (!r) return NL.toast('This run is unavailable. Refresh and try again.', 'bad');
    const handoff = fresh || !r.session_id;
    const x = await NL.act(handoff ? '/api/run/handoff' : '/api/run/reply', {run_id:id, confirm:true,
      text:'Continue the assigned task. Check its current state and evidence, finish the work and report its workflow outcome.'},
      handoff ? 'New agent queued' : 'Continuing task');
    if (x.run_id && x.run_id !== id) NL.openRun(x.run_id);
    return x;
  };

  /* ── live transcript (polls /api/run/tail while the sheet is open) ──────── */
  function useRun(id) {
    const [detail, setDetail] = useState(null);
    const [lines, setLines] = useState([]);
    const [err, setErr] = useState(null);
    const st = useRef({ offset: 0, status: null, last: 0, alive: true, skipped: 0 });
    useEffect(() => {
      const state = { offset: 0, status: null, last: 0, alive: true, skipped: 0 };
      st.current = state;
      setLines([]); setDetail(null); setErr(null);
      if (NL.DEMO) return undefined;
      let timer = null;
      const loadDetail = async () => {
        const d = await NL.get(`/api/run?${NL.qs({ run_id: id })}`);
        if (!state.alive) return;
        if (d.ok) { setDetail(d.run); state.last = Date.now(); } else setErr(d.error || 'no such run');
      };
      const tick = async () => {
        const t = await NL.get(`/api/run/tail?${NL.qs({ run_id: id, offset: state.offset })}`);
        if (!state.alive) return;
        if (t.ok) {
          setErr(null);
          if (t.skipped && !state.offset) state.skipped = t.skipped;
          state.offset = t.offset;
          if (t.lines && t.lines.length) setLines(prev => { const next = prev.concat(t.lines); return next.length > 2500 ? next.slice(-2000) : next; });
          if (t.status !== state.status || Date.now() - state.last > 5000) { state.status = t.status; await loadDetail(); }
          if (!state.alive) return;
          const done = NL.RUN_DONE.has(t.status) && t.eof;
          timer = setTimeout(tick, done ? 6000 : 1400);
        } else { setErr(t.error || 'no such run'); timer = setTimeout(tick, 5000); }
      };
      tick();
      return () => { state.alive = false; clearTimeout(timer); };
    }, [id]);
    const s = NL.useLab();
    const live = NL.run(s, id);        // the snapshot's compact copy is fresher for status/elapsed
    const run = detail ? { ...detail, ...(live || {}), qa: detail.qa, attempts: detail.attempts, transcript: detail.transcript,
      external_activity:live?.external_activity||detail.external_activity } : live;
    return { run, lines, err, skipped: st.current.skipped, reload: () => { st.current.last = 0; } };
  }

  /* ── transcript → conversation blocks ──────────────────────────────────── */
  const EDITS = new Set(['Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'apply_patch', 'edit', 'write', 'patch']);
  const SPAWNS = new Set(['Agent', 'Task', 'task', 'spawn_agent']);
  function toBlocks(lines) {
    const out = [];
    let group = null;
    const flush = () => { if (group) { out.push(group); group = null; } };
    for (const l of lines) {
      if (l.k === 'tool' && !SPAWNS.has(l.tool)) {
        if (!group || group.who !== (l.who || null)) { flush(); group = { k: 'tools', who: l.who || null, items: [] }; }
        group.items.push(l);
        continue;
      }
      flush();
      if (l.k === 'tool') out.push({ k: 'spawn', who: l.who || null, t: l.t, tool: l.tool });
      else if (l.k === 'text' && out.length && out[out.length - 1].k === 'text' && out[out.length - 1].who === (l.who || null)) out[out.length - 1].t += (l.delta ? '' : '\n\n') + l.t;
      else out.push({ ...l, who: l.who || null });
    }
    flush();
    return out;
  }
  function toolSummary(items) {
    const n = { run: 0, edit: 0, read: 0, other: 0 };
    for (const i of items) {
      if (i.tool === 'Bash' || i.tool === 'bash' || i.tool === 'shell' || i.tool === 'exec_command') n.run++;
      else if (EDITS.has(i.tool)) n.edit++;
      else if (/read|grep|glob|list|search|fetch/i.test(i.tool || '')) n.read++;
      else n.other++;
    }
    const parts = [];
    if (n.run) parts.push(`ran ${NL.plural(n.run, 'command')}`);
    if (n.edit) parts.push(`edited ${NL.plural(n.edit, 'file')}`);
    if (n.read) parts.push(`read ${NL.plural(n.read, 'thing')}`);
    if (n.other) parts.push(NL.plural(n.other, 'other step'));
    return parts.join(' · ');
  }

  const Who = ({ who }) => who ? html`<span class="msg-who">${who}</span>` : null;
  const ToolGroup = ({ b, last }) => {
    const [open, setOpen] = useState(false);
    const show = open ? b.items : [];
    const tail = b.items[b.items.length - 1];
    return html`<div class=${cls('tgroup', open && 'open')}>
      <button type="button" class="tgroup-head" onClick=${() => setOpen(!open)} aria-expanded=${open}>
        <span class="tg-caret">${open ? '▾' : '▸'}</span><${Who} who=${b.who} /><span class="tg-sum">${toolSummary(b.items)}</span>
        ${!open && last ? html`<span class="tg-last"><b>${tail.tool}</b> ${NL.clip(tail.t, 90)}</span>` : null}</button>
      ${show.map(i => html`<div class="tline"><b>${i.tool}</b> <span>${i.t}</span></div>`)}</div>`;
  };
  const Block = ({ b, last }) => {
    switch (b.k) {
      case 'text': return html`<div class="msg"><${Who} who=${b.who} /><${NL.Markdown} text=${b.t} /></div>`;
      case 'you': return html`<div class="msg msg-you"><span class="msg-who">${b.by === 'you' ? (b.kind === 'answer' ? 'you answered' : b.kind === 'permission' ? 'you decided' : 'you') : b.by}</span>${b.t}</div>`;
      case 'tools': return html`<${ToolGroup} b=${b} last=${last} />`;
      case 'spawn': return html`<div class="spawn"><span class="spawn-ico">⤷</span><span>started a subagent</span> <b>${NL.clip(b.t, 120)}</b></div>`;
      case 'sub': return html`<div class="subres"><div class="subres-h">↩ <b>${b.who || 'subagent'}</b> handed back</div><div class="subres-t">${NL.clip(b.t, 1800)}</div></div>`;
      case 'err': return html`<div class="msg-err"><${Who} who=${b.who} />${b.t}</div>`;
      case 'end': return html`<div class="msg-end">${'■ turn ended'}${b.cost != null ? html` <span class="muted">· $${(+b.cost).toFixed(3)}</span>` : null}</div>`;
      case 'attempt': case 'start': return html`<div class="msg-div"><span>${b.t}</span></div>`;
      default: return html`<div class="tline muted">${b.t}</div>`;
    }
  };

  const ElicitationCard = ({r, question}) => {
    const f=question.input.elicitation,fields=f.requestedSchema?.properties||{},required=f.requestedSchema?.required||[];
    const [values,setValues]=NL.useDraft('form:'+r.run_id+':'+question.tool_use_id,()=>Object.fromEntries(Object.entries(fields).filter(([,v])=>'default' in v).map(([k,v])=>[k,v.default]))),[error,setError]=useState(''),[busy,setBusy]=useState(false);
    const update=(k,v)=>setValues(old=>({...old,[k]:v}));
    const send=async action=>{
      setBusy(true);setError('');
      try{const content=Object.fromEntries(Object.entries(values).filter(([k,v])=>v!==undefined&&(v!==''||required.includes(k))));
        required.forEach(k=>{if(!(k in content)&&(fields[k]?.type||'string')==='string'&&!fields[k]?.enum&&!fields[k]?.oneOf)content[k]='';if(!(k in content)&&fields[k]?.type==='array')content[k]=[]});
        const x=await NL.api('/api/run/answer',{run_id:r.run_id,request_id:question.tool_use_id,action,...(f.mode==='form'?{content}:{})});
        if(x.error)setError(x.error);else{NL.toast(action==='accept'?'Response sent':'Request '+(action==='decline'?'declined':'cancelled'));NL.refresh()}}
      finally{setBusy(false)}
    };
    return html`<form class="ask" onSubmit=${e=>{e.preventDefault();send('accept')}}>
      <div class="ask-h"><span class="ask-ico">?</span>${f.message||'The agent needs your input'}</div>
      ${f.mode==='url'?html`<p>Open ${new URL(f.url).hostname} to continue.</p><p class="path-wrap"><code>${f.url}</code></p>`:
        Object.entries(fields).map(([k,v])=>{
          const choices=v.enum?.map(x=>({const:x,title:String(x)}))||v.oneOf,kind=v.type||'string',label=v.title||k;
          return html`<fieldset class="field"><legend class="field-label">${label}${required.includes(k)?' *':''}</legend>${v.description?html`<small>${v.description}</small>`:null}
          ${kind==='array'?html`<span>${(v.items.enum?.map(x=>({const:x,title:x}))||v.items.anyOf||[]).map(option=>html`<label class="row"><input type="checkbox" checked=${(values[k]||[]).includes(option.const)} onChange=${e=>update(k,e.target.checked?[...(values[k]||[]),option.const]:(values[k]||[]).filter(x=>x!==option.const))}/>${option.title||option.const}</label>`)}</span>`:
            choices||kind==='boolean'?html`<select class="input" aria-label=${label} required=${required.includes(k)} value=${values[k]===undefined?'':String(values[k])} onChange=${e=>update(k,kind==='boolean'?(e.target.value===''?undefined:e.target.value==='true'):e.target.value)}>
              <option value="">Choose…</option>${(choices||[{const:true,title:'Yes'},{const:false,title:'No'}]).map(o=>html`<option value=${String(o.const)}>${o.title||String(o.const)}</option>`)}</select>`:
            html`<input class="input" aria-label=${label} type=${['number','integer'].includes(kind)?'number':v.format==='email'?'email':v.format==='date'?'date':'text'} required=${required.includes(k)&&(kind!=='string'||v.minLength>0||!!v.format)} min=${v.minimum} max=${v.maximum} minLength=${v.minLength} maxLength=${v.maxLength} pattern=${v.pattern} step=${kind==='integer'?1:'any'} value=${values[k]??''} onInput=${e=>update(k,['number','integer'].includes(kind)&&e.target.value!==''?Number(e.target.value):e.target.value)}/>`}</fieldset>`;
        })}
      ${error?html`<p role="alert">${error}</p>`:null}<div class="ask-actions row wrap">
        <${NL.Btn} type="button" disabled=${busy} onClick=${()=>send('decline')}>Decline</${NL.Btn}>
        <${NL.Btn} type="button" disabled=${busy} onClick=${()=>send('cancel')}>Cancel request</${NL.Btn}>
        ${f.mode==='url'?html`<${NL.Btn} type="button" kind="primary" disabled=${busy} onClick=${()=>{window.open(f.url,'_blank','noopener,noreferrer');send('accept')}}>Open link</${NL.Btn}>`:
          html`<button class="btn btn-primary" type="submit" disabled=${busy}>Send answers</button>`}
      </div></form>`;
  };

  /* ── the question card (AskUserQuestion) ───────────────────────────────── */
  const AskCard = ({ r }) => {
    const pq = r.pending_question || {};
    // a question that came as plain text (or didn't come through) still gets a box to answer it in
    const plain = pq.question || pq.text || (pq.input && (pq.input.question || pq.input.text)) || '';
    const qs = ((pq.input || {}).questions) || [];
    const key='question:'+r.run_id+':'+(pq.tool_use_id||plain||r.attempt);
    const [free,setFree]=NL.useDraft(key+':free',''),[ans,setAns]=NL.useDraft(key+':answers',{}),
      [other,setOther]=NL.useDraft(key+':other',{}),[skipped,setSkipped]=NL.useDraft(key+':skipped',{});
    const pick = (q, label) => setAns(a => {
      if (!q.multiSelect) return { ...a, [q.question]: label };
      const cur = new Set(a[q.question] || []); cur.has(label) ? cur.delete(label) : cur.add(label);
      return { ...a, [q.question]: [...cur] };
    });
    const answers = () => { const o = { ...ans }; for (const [k, v] of Object.entries(other)) if (v.trim()) o[k] = v.trim();for(const k of Object.keys(skipped))if(skipped[k])o[k]='Skipped by user.'; return o; };
    const complete=qs.every(q=>{const a=answers()[q.question];return Array.isArray(a)?a.length:!!a});
    const send = async () => {
      if (!qs.length) {
        if (!free.trim()) return NL.toast('Type your answer first', 'warn');
        const x = await NL.act('/api/run/answer', { run_id: r.run_id, request_id:pq.tool_use_id, text: free.trim() }, 'Sent. The agent carries on.');
        if (x.ok) setFree('');
        return x;
      }
      const a = answers();
      if (!complete) return NL.toast('Answer or skip each question', 'warn');
      const x = await NL.act('/api/run/answer', { run_id: r.run_id, request_id:pq.tool_use_id, answers: a }, 'Sent. The agent carries on.');
      return x;
    };
    return html`<div class="ask">
      <div class="ask-h"><span class="ask-ico">?</span> ${r.pid ? 'The agent is asking you. It waits for your answer.' : 'The agent asked you. Your answer resumes it.'}</div>
      ${qs.map(q => html`<fieldset class="ask-q"><legend>${q.header ? html`<span class="ask-tag">${q.header}</span>` : null}${q.question}</legend>
        <fieldset disabled=${!!skipped[q.question]} class="ask-choices">
        ${(q.options || []).map(o => {
          const on = q.multiSelect ? (ans[q.question] || []).includes(o.label) : ans[q.question] === o.label;
          return html`<button type="button" class=${cls('ask-opt', on && 'on')} role=${q.multiSelect ? 'checkbox' : 'radio'} aria-checked=${on} onClick=${() => pick(q, o.label)}>
            <span class="ask-mark">${q.multiSelect ? (on ? '☑' : '☐') : (on ? '◉' : '○')}</span><span><b>${o.label}</b>${o.description ? html`<small>${o.description}</small>` : null}</span></button>`;
        })}
        <${NL.Input} value=${other[q.question] || ''} onInput=${v => setOther(o => ({ ...o, [q.question]: v }))} placeholder="…or type your own answer" onEnter=${send} />
        </fieldset><button type="button" class="link small" aria-pressed=${!!skipped[q.question]} onClick=${()=>setSkipped(s=>({...s,[q.question]:!s[q.question]}))}>${skipped[q.question]?'Undo skip':'Skip question'}</button>
      </fieldset>`)}
      ${!qs.length ? html`<div class="ask-q plain">${plain ? html`<b class="ask-text">${plain}</b>` : html`<span class="muted">Its question didn't come through in full; the transcript or the supervisor log below has the context. Whatever you write reaches it as your answer.</span>`}
        <${NL.Textarea} rows="2" value=${free} onInput=${setFree} onSubmit=${send} placeholder="Your answer (Ctrl+Enter)" /></div>` : null}
      <div class="ask-actions"><${NL.Btn} kind="primary" disabled=${qs.length?!complete:!free.trim()} onClick=${send}>Answer and continue</${NL.Btn}></div></div>`;
  };

  const PermissionRows = ({ r }) => {
    const s = NL.useLab();
    const items = ((s.attention) || []).filter(a => a.kind === 'permission' && a.run_id === r.run_id);
    if (!items.length) return null;
    return html`${items.map(a => html`<div class="perm"><div><b>${a.title}</b><div class="mono small">${a.body}</div></div>
      <div class="row"><${NL.Btn} small onClick=${() => NL.act('/api/run/permission', { run_id: r.run_id, n: a.detail.n, allow: false }, 'Denied')}>Deny</${NL.Btn}>
      <${NL.Btn} small kind="primary" onClick=${() => NL.act('/api/run/permission', { run_id: r.run_id, n: a.detail.n, allow: true }, 'Allowed once')}>Allow once</${NL.Btn}></div></div>`)}`;
  };

  const NEEDS = {
    kill_criteria: 'A kill criterion fired', null_result: 'A null result: decide what next', spawn_type: 'Pick the project type', other: 'It needs a decision from you' };
  const Report = ({ r }) => {
    const rep = r.report; if (!rep || !NL.RUN_DONE.has(r.status)) return null;
    return html`<div class=${cls('report', rep.needs_pi && 'report-needs')}>
      <div class="report-h">${rep.needs_pi ? '✋ ' + (NEEDS[rep.needs_pi] || rep.needs_pi) : r.needs_followup ? 'Output' : r.status === 'completed' ? NL.runStateLabel(r) : NL.RUN_WORD[r.status]}</div>
      ${rep.summary ? html`<${NL.Markdown} text=${rep.summary} />` : null}
      <div class="row">
        ${rep.needs_pi && r.subject && NL.checkpoint(rep.needs_pi) ? html`<${NL.Btn} kind="primary" onClick=${() => NL.openCheckpoint(r.subject, rep.needs_pi)}>Review: ${NL.checkpoint(rep.needs_pi).title}</${NL.Btn}>` : null}
        ${rep.next ? html`<${NL.Btn} small=${!!rep.needs_pi} kind=${rep.needs_pi ? '' : 'primary'} onClick=${() => NL.launchCommand(rep.next, r.subject)}
          title=${rep.needs_pi ? 'the step after your decision' : ''}>${rep.needs_pi ? 'then ▸ ' : '▸ '}${rep.next}</${NL.Btn}>` : null}
      </div></div>`;
  };

  /* what the run did, computed by the lab (not the agent's own account): where the study moved, the files it
     wrote, the commands worth a look, what the guard refused, and the flags its watches raised */
  const OUTCOME_WORD = e => e.kind === 'move' ? `moved ${NL.STATE_LABEL[e.from] || e.from} → ${NL.STATE_LABEL[e.to] || e.to}${e.outcome ? ` (${e.outcome})` : ''}`
    : e.kind === 'wait' ? `waits for you${e.checkpoint && NL.checkpoint(e.checkpoint) ? ': ' + NL.checkpoint(e.checkpoint).title : ''}`
    : e.kind === 'finish' ? 'finished its workflow' : 'reported no outcome';
  const Digest = ({ r }) => {
    const [open, setOpen] = useState(false);
    const d = r.digest; if (!d || !NL.RUN_DONE.has(r.status)) return null;
    return html`<div class="digest">
      <div class="row gap wrap">${(d.outcome || []).map(e => html`<${NL.Pill} tone=${e.kind === 'none' ? 'muted' : e.kind === 'wait' ? 'warn' : 'ok'}>${OUTCOME_WORD(e)}</${NL.Pill}>`)}
        <span class="muted small">${NL.plural(d.written || 0,'file written','files written')} · ${NL.plural(d.deleted || 0,'file deleted','files deleted')} · ${NL.plural(d.commits || 0,'commit')} · ${NL.plural(d.commands || 0,'command')}${d.denials ? html` · <b>${d.denials} refused</b>` : ''}</span>
        ${(d.files || []).length || (d.notable || []).length ? html`<button type="button" class="link small" onClick=${() => setOpen(!open)}>${open ? 'hide' : 'details'}</button>` : null}</div>
      ${(d.flags || []).map(f => html`<div class=${cls('note', f.level === 'block' ? 'note-bad' : 'note-warn')}>${f.say}${f.hold ? '; nothing new starts for this study until you acknowledge it' : ''}
        ${f.id && f.level !== 'info' ? html` <button type="button" class="link small" onClick=${() => NL.act('/api/flag/ack', { flag: f.id }, 'Acknowledged')}>acknowledge</button>` : null}</div>`)}
      ${open ? html`<ul class="mono small digest-files">${(d.files || []).map(f => html`<li>+ ${f}</li>`)}${(d.gone || []).map(f => html`<li>− ${f}</li>`)}${(d.notable || []).map(c => html`<li>$ ${c}</li>`)}</ul>` : null}
    </div>`;
  };

  NL.FrameworkActivity=({data,reload})=>!data?null:html`<details class="framework-activity" open>
    <summary>${data.title||'External tool'} <span class="muted small">${data.phase?.replaceAll('_',' ')||'activity'}</span></summary>
    ${data.error?html`<${NL.LoadState} error=${data.error} reload=${reload}/>`:html`
      <p class="muted small">Observed activity · controls stay with the phase.</p>
      ${!data.events?.length?html`<p class="muted small">${data.supported?'No events recorded yet.':'This tool has no activity mapping.'}</p>`:html`
        <ol class="framework-timeline">${data.events.slice().reverse().map((e,i)=>html`<li key=${i} class=${e.state}>
            <span class="framework-event-mark" aria-hidden="true">${e.state==='running'?'◌':e.state==='failed'?'×':e.state==='completed'?'✓':'·'}</span>
          <div><b>${e.label}</b><small>${e.state==='running'?'started':e.state.replaceAll('_',' ')}${e.cycle!=null?' · cycle '+e.cycle:''}${e.worker!=null?' · worker '+(typeof e.worker==='number'?e.worker+1:e.worker):''}
            · <${NL.EditorLink} path=${data.root+'/'+e.source} machine=${data.machine}>Source</${NL.EditorLink}></small></div>
          <time dateTime=${e.time}>${NL.hhmm(e.time)}</time></li>`)}</ol>`}
      ${data.clipped||data.malformed?html`<p class="muted small">${data.clipped?'Showing recent events. ':''}${data.malformed?'Some incomplete records were skipped.':''}</p>`:null}`}
  </details>`;
  /* ── the run sheet ─────────────────────────────────────────────────────── */
  NL.RunSheet = ({ id, focusSub, onClose }) => {
    const { run: r, lines, err, skipped, reload } = useRun(id);
    const s = NL.useLab();
    useEffect(()=>{if(r)NL.focusRun(r,focusSub)},[r?.run_id,focusSub,r?.subject,r?.workflow_node]);
    const blocks = useMemo(() => toBlocks(lines), [lines]);
    const scroller = useRef();
    const [stick, setStick] = useState(true);
    const [reply, setReply] = NL.useDraft('reply:'+id,'');
    useEffect(() => { const el = scroller.current; if (el && stick) el.scrollTop = el.scrollHeight; }, [blocks.length, r && r.status, stick]);
    const onScroll = e => { const el = e.target; setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 80); };
    if (!r) return html`<${NL.Sheet} title="Run" onClose=${onClose} wide>${err ? html`<${NL.Empty}>${err}</${NL.Empty}>` : html`<${NL.Spinner} />`}</${NL.Sheet}>`;
    const it = r.subject && NL.item(s, r.subject);
    const active = NL.RUN_ACTIVE.has(r.status);
    const budget = r.max_minutes ? r.max_minutes * 60 : null;
    const liveNow = r.transport === 'live' && (active || r.status === 'waiting_input') && r.pid;
    const canReply = r.session_id && (r.status === 'waiting_input' || NL.RUN_DONE.has(r.status) || liveNow);
    const sendReply = async () => { if (!reply.trim()) return; const x = await NL.act('/api/run/reply', { run_id: r.run_id, text: reply.trim() }); if (x.ok) setReply(''); };
    const hint = liveNow && active ? 'Message the agent while it works; it reads it after its current step (Ctrl+Enter)'
      : r.status === 'waiting_input' ? 'Your turn. Reply in your own words (Ctrl+Enter)' : 'Reply to continue this conversation (Ctrl+Enter to send)';
    const title = NL.runTitle(r);
    const sub = html`<span class="row-wrap"><${NL.RunPill} r=${r} />
      ${it ? html`<a class="chip" href=${'#/study/' + it.id}>${NL.clip(it.title || it.id, 40)}</a>` : html`<span class="chip">the lab</span>`}
      <span class="muted">${r.backend}${r.model_used || r.model ? ' · ' + (r.model_used || r.model) : ''}${r.attempt > 1 ? ' · attempt ' + r.attempt : ''}</span>
      <span class="mono muted small" title="this run's id">${r.run_id}</span></span>`;
    const footer = html`<div class="runfoot">
      ${r.status === 'waiting_input' && r.pending_question ? null : canReply ? html`<div class="reply">
        <${NL.Textarea} rows="2" value=${reply} onInput=${setReply} onSubmit=${sendReply} ariaLabel="Message to agent" ariaDescription=${hint} placeholder="Message the agent…" />
        <${NL.Btn} kind="primary" onClick=${sendReply} disabled=${!reply.trim()}>Send</${NL.Btn}></div>` : null}
      <div class="row">
        ${liveNow && active ? html`<${NL.Btn} onClick=${() => NL.act('/api/run/interrupt', { run_id: r.run_id })} title="Stops the current step. The run stays open for your next message.">⏸ Pause step</${NL.Btn}>` : null}
        ${active || (liveNow && r.status === 'waiting_input') ? html`<${NL.Btn} kind="danger" onClick=${async () => { if (await NL.confirm({ title: 'Stop this run?', body: 'The run stops now. You can resume it later from this sheet.', ok: 'Stop', danger: true })) NL.act('/api/run/stop', { run_id: r.run_id, confirm: true }, 'Stopping'); }} title="Stops this run. You can resume it later.">■ Stop</${NL.Btn}>` : null}
        ${r.status === 'queued' ? html`<${NL.Btn} onClick=${() => NL.act('/api/run/cancel', { run_id: r.run_id }, 'Cancelled')}>Cancel</${NL.Btn}>` : null}
        ${NL.RUN_DONE.has(r.status) && r.session_id && r.status !== 'completed' ? html`<${NL.Btn} onClick=${() => NL.act('/api/run/resume', { run_id: r.run_id }, 'Resuming')}>↻ Resume</${NL.Btn}>` : null}
        <span class="grow"></span>
        ${r.transcript ? html`<${NL.EditorLink} path=${r.transcript}>transcript ↗</${NL.EditorLink}>` : null}
        <button class="link small" onClick=${() => NL.open(NL.TextSheet, { title: 'Technical log', sub: r.run_id, path: `/api/run/log?${NL.qs({ run_id: r.run_id })}` })}>technical log</button>
      </div></div>`;
    return html`<${NL.Sheet} title=${title} sub=${sub} onClose=${onClose} wide footer=${footer}>
      <nav class="inspector-links" aria-label="Related work">${it?html`<a href=${NL.focusHref('workflow/map')} onClick=${onClose}>Task</a><a href=${NL.focusHref('library')} onClick=${onClose}>Outputs</a>`:null}${(s.agents||[]).some(a=>a.run_id===r.run_id)?html`<button type="button" class="link" onClick=${()=>{onClose();NL.followAgent(r.run_id)}}>Show in Lab</button>`:null}</nav>
      <div class="runmeta">
        ${r.elapsed_s != null ? html`<span><b>${NL.mins(r.elapsed_s)}</b>${budget ? html` of ${Math.round(r.max_minutes)}m <${NL.Bar} value=${r.elapsed_s} max=${budget} tone=${r.elapsed_s > budget * 0.85 ? 'warn' : ''} />` : null}</span>` : null}
        ${r.n_actions ? html`<span><b>${r.n_actions}</b> ${r.n_actions === 1 ? 'action' : 'actions'}</span>` : null}
        ${(r.subagents || []).length ? html`<span>${NL.plural(r.subagents.length, 'subagent')}</span>` : null}
        ${r.usage && r.usage.cost_usd != null ? html`<span>≈ $${(+r.usage.cost_usd).toFixed(2)}</span>` : null}
        ${r.status === 'queued' ? html`<span>${r.not_before ? 'scheduled for ' + NL.hhmm(r.not_before) : 'starts as soon as a slot is free'}</span>` : null}
        ${!r.explains ? html`<span class="grow"></span><${NL.Btn} small onClick=${() => NL.explain(r.run_id)} title="Start a separate explainer; this conversation continues unchanged">Visual summary</${NL.Btn}>` : null}
      </div>
      ${r.reason && !active && !['completed', 'waiting_input', 'queued'].includes(r.status) ? html`<div class="note note-warn">${r.reason}</div>` : null}
      ${r.remote ? html`<div class="small muted">${r.remote.machine} · ${r.remote.path} <button class="link" onClick=${()=>NL.openMachineSetup(r.remote.machine)}>Connection</button></div>` : null}
      ${r.remote_error ? html`<div class="note note-warn" role="status">${r.remote_error}</div>` : null}
      ${r.delivery_uncertain ? html`<div class="note note-warn">A message may not have reached the agent. Check the conversation before sending it again.</div>` : null}
      ${(r.external_interactions||[]).map(e=>html`<div class="small muted" role="status">${e.message||'External interaction'} · ${e.completed_at?'Completion reported by agent':'Link opened; completion not reported'}</div>`)}
      ${r.needs_followup ? html`<div class="note note-warn"><p>No outcome recorded.</p><div class="row wrap">
        ${r.session_id ? html`<${NL.Btn} small kind="primary" onClick=${() => NL.continueTask(r.run_id)}>Continue task</${NL.Btn}>` : null}
        <${NL.Btn} small kind=${r.session_id ? '' : 'primary'} onClick=${() => NL.continueTask(r.run_id,true)}>New agent with handoff</${NL.Btn}></div></div>` : null}
      ${r.status === 'waiting_input' && r.pending_question ? (r.pending_questions||[r.pending_question]).map(q=>q.input?.elicitation?html`<${ElicitationCard} key=${q.tool_use_id} r=${r} question=${q}/>`:html`<${AskCard} key=${q.tool_use_id} r=${{...r,pending_question:q}} />`) : null}
      <${Lineage} r=${r} />
      <${NL.FrameworkActivity} data=${r.external_activity} reload=${reload}/>
      <${Subagents} r=${r} focus=${focusSub} />
      <${Explanations} r=${r} />
      <${NL.RunFiles} r=${r} />
      <${Actions} r=${r} />
      <div class="convo" ref=${scroller} onScroll=${onScroll}>
        ${skipped ? html`<div class="msg-div"><span>earlier output skipped (${Math.round(skipped / 1024)} KB)</span></div>` : null}
        ${!blocks.length ? r.status === 'waiting_input' && !r.pending_question && r.last_text
          ? html`<div class="msg"><${NL.Markdown} text=${r.last_text} /></div>`
          : !err ? html`<div class="muted pad">${r.status === 'queued' ? 'Waiting for a free slot…' : NL.DEMO ? 'The demo has no transcripts. Its latest step is below.' : active ? (r.last_action ? 'Working. Its latest step is below.' : 'Starting up…') : 'No transcript yet.'}</div>` : null : null}
        ${err ? html`<div class="note note-warn" role="alert"><p>${err}</p><small>Retrying automatically. Loaded messages stay visible.</small></div>` : null}
        ${blocks.map((b, i) => html`<${Block} key=${i} b=${b} last=${i === blocks.length - 1 && active} />`)}
        ${active && r.last_action ? html`<div class="now"><i class="dot-live"></i> <b>${r.last_action.tool || ''}</b> ${NL.clip(r.last_action.summary, 140)}</div>` : null}
        <${PermissionRows} r=${r} />
        <${Report} r=${r} />
        <${Digest} r=${r} />
        ${(r.qa || []).length ? html`<details class="qa"><summary>${NL.plural(r.qa.length, 'earlier answer')}</summary>${r.qa.map(q => html`<div class="qa-row"><span class="muted">${NL.hhmm(q.answered_at)}</span>
          ${((q.question || {}).questions || []).map(x => x.question).join(' · ')} → <b>${Object.values(q.answers || {}).map(v => Array.isArray(v) ? v.join(', ') : v).join(' · ') || q.response || ''}</b></div>`)}</details>` : null}
      </div>
      ${!stick ? html`<button class="jump" onClick=${() => setStick(true)}>↓ latest</button>` : null}
    </${NL.Sheet}>`;
  };
  /* where this run came from and what it started: the PI, a chain, a repeat, a campaign pass */
  const Lineage = ({ r }) => {
    const s = NL.useLab();
    if(r.explains)return html`<div class="lineage"><span class="muted">Independent explanation of</span> <button type="button" class="link" onClick=${()=>NL.openRun(r.explains.run,r.explains.agent)}>${r.explains.agent?'subagent work':'the source run'} →</button></div>`;
    const all = s.runs || [];
    const parent = r.parent && all.find(x => x.run_id === r.parent);
    const kids = all.filter(x => x.parent === r.run_id);
    const by = { chain: 'the previous step', repeat: 'a repeat', campaign: 'a campaign', 'campaign-approval': 'a campaign, after approving a checkpoint',
      dashboard: 'you', cli: 'the command line', checkpoint: 'your approval of a checkpoint', 'checkpoint-auto': 'a checkpoint that approved itself',
      'panel-designer': 'you, asking for an instrument', loop: 'your approval of the loop' }[r.created_by] || r.created_by;
    if (!parent && !kids.length && !r.campaign) return null;
    return html`<div class="lineage">
      <span class="muted">Started by</span> ${parent ? html`<button type="button" class="chip click" onClick=${() => NL.openRun(parent.run_id)}>${NL.clip(NL.runTitle(parent), 48)}</button>` : html`<span>${by || 'you'}</span>`}
      ${r.campaign ? html`<button type="button" class="chip click" onClick=${() => NL.openCampaign(r.campaign)}>⟳ ${NL.clip(r.campaign.replace(/^\d{4}-\d{2}-\d{2}-/, ''), 32)}${r.campaign_cycle ? ' · pass ' + r.campaign_cycle : ''}</button>` : null}
      ${kids.length ? html`<span class="muted">→ started</span>${kids.slice(0, 8).map(k => html`<button type="button" class="chip click" onClick=${() => NL.openRun(k.run_id)}>${NL.clip(NL.runTitle(k), 36)} <${NL.RunPill} r=${k} /></button>`)}${kids.length > 8 ? html`<span class="muted">+${kids.length - 8}</span>` : null}` : null}
      ${r.campaign_retries ? html`<span class="muted">· retried ${r.campaign_retries}× after ${r.failure_kind || 'a failure'}</span>` : null}
    </div>`;
  };

  /* subagents as a tree (a subagent may spawn its own), each linked to its own trace */
  const Subagents = ({ r, focus }) => {
    const s = NL.useLab();
    const subs = r.subagents || [];
    if (!subs.length) return null;
    const live = subs.filter(x => x.status === 'working').length;
    const ids = new Set(subs.map(x => x.id));
    const kidsOf = pid => subs.filter(x => (x.parent && ids.has(x.parent) ? x.parent : null) === pid);
    const traceOf = sa => (s.workers || []).find(w => (w.spawn_id && w.spawn_id === sa.id) || (sa.session && w.worker_id === sa.session));
    const Row = ({ sa, depth }) => {
      const w = traceOf(sa);
      return html`<div class=${cls('sub-row', sa.status === 'working' && 'on', focus === sa.id && 'focus')} style=${{ marginLeft: (depth * 18) + 'px' }}>
        ${depth ? html`<span class="muted">↳</span>` : null}<${NL.RoleDot} role=${sa.type} /><b>${NL.roleOf(sa.type).label}</b><span class="grow clip">${sa.description || ''}</span>
        ${sa.background ? html`<span class="muted small" title="started in the background">bg</span>` : null}
        <span class="muted">${sa.status || ''}${sa.n_actions ? ' · ' + sa.n_actions + ' actions' : ''}</span>
        ${w ? html`<button type="button" class="link small" onClick=${() => NL.openWorker(w.worker_id)}>trace</button>` : null}
        <button type="button" class="link small" title="A separate agent explains this recorded subagent" onClick=${() => NL.explain(r.run_id, sa.id)}>explain</button>
        ${sa.status === 'working' && (sa.in_tool || sa.last_action) ? html`<div class="sub-last">${sa.in_tool ? html`<span title=${NL.activity(sa.in_tool.kind)[1]}>${NL.activity(sa.in_tool.kind)[0]}</span> ${NL.clip(sa.in_tool.summary || sa.in_tool.tool, 140)}` : html`▸ ${NL.clip(sa.last_action, 140)}`}</div>` : null}
        ${sa.result ? html`<details class="sub-res"><summary>result</summary><div>${sa.result}</div></details>` : null}</div>
        ${kidsOf(sa.id).map(k => html`<${Row} key=${k.id} sa=${k} depth=${depth + 1} />`)}`;
    };
    return html`<details class="subs" open=${live > 0 || !!focus}><summary>${NL.plural(subs.length, 'subagent')}${live ? html` · <b>${live} working</b>` : null}</summary>
      ${kidsOf(null).slice().reverse().map(sa => html`<${Row} key=${sa.id} sa=${sa} depth=${0} />`)}</details>`;
  };
  NL.openRun = (id, sub) => {if(!id)return;const r=NL.run(NL.getState(),id);if(r)NL.focusRun(r,sub);return NL.open(NL.RunSheet, { id, focusSub: sub || null }, { key: 'run:' + id,slot:'inspector' });};

  /* A separate terminal agent explains the recorded evidence without interrupting the source run. */
  NL.explain = async (runId, agent, options={}) => {
    const result=await NL.act('/api/run/explain', {run_id:runId,...(agent?{agent}:{}),...options});
    if(result.ok&&result.run_id)NL.openRun(result.run_id);
    return result;
  };
  const Explanations = ({ r }) => {
    const records=NL.useArtifactList({about:r.run_id}),list=records.rows;
    if (!(list && list.length)) return null;
    const latest = (r.last_action || {}).ts || r.finished || '';
    const sub = id => (r.subagents || []).find(x => x.id === id);
    return html`<details class="runfiles" open><summary>Explanations (${list.length})</summary>
      ${list.map(a => { const sa = a.about.agent && sub(a.about.agent);
        return html`<button type="button" class="runfile art" onClick=${() => NL.openArtifact(a.id)}><span>✦</span><b class="grow clip">${a.title}</b>
          <span class="muted small">${sa ? 'about ' + NL.clip(sa.description || NL.roleOf(sa.type).label, 28) + ' · ' : ''}${NL.ago(a.created)}</span>
          ${latest > a.created ? html`<${NL.Pill} tone="muted" title="It has done more since">earlier</${NL.Pill}>` : null}</button>`; })}
      ${records.next?html`<${NL.Btn} small busy=${records.loading} onClick=${records.loadMore}>Load older explanations</${NL.Btn}>`:null}</details>`;
  };

  /* everything the run's agents did, as the lab recorded it (tools/executor/actions.py — no model involved):
     the run's agent, and each subagent nested where it was started */
  const MAX_ROWS = 400;
  const Actions = ({ r }) => {
    const [open, setOpen] = useState(false);
    const g = NL.useGet(open && !NL.DEMO ? `/api/run/actions?${NL.qs({ run_id: r.run_id })}` : null, Math.floor((r.n_actions || 0) / 10) + ':' + r.status);
    const t = (g.data || g.previous)?.agents;
    const Agent = ({ id, depth }) => {
      const a = t[id], acts = a.actions.slice(-MAX_ROWS);
      return html`<div class="act-agent" style=${{ marginLeft: (depth * 16) + 'px' }}>
        ${id !== 'main' ? html`<div class="act-head"><${NL.RoleDot} role=${a.type} /><b>${NL.roleOf(a.type).label}</b><span class="clip grow">${a.summary || ''}</span><span class="muted small">${a.status || ''}</span></div>` : null}
        ${a.actions.length > acts.length ? html`<div class="muted small">${a.actions.length - acts.length} earlier actions not shown</div>` : null}
        ${acts.map(x => x.child && t[x.child] ? html`<${Agent} id=${x.child} depth=${depth + 1} />`
          : html`<div class="act-row"><span class="muted mono small">${NL.hhmm(x.ts)}</span><span title=${NL.activity(x.kind)[1]}>${NL.activity(x.kind)[0]}</span><span class="clip grow">${x.summary || x.tool || ''}</span></div>`)}</div>`;
    };
    return html`<details class="runfiles" onToggle=${e => setOpen(e.target.open)}><summary>Everything it did</summary>
      ${open && !NL.DEMO && (g.error || !g.data && !g.previous) ? html`<${NL.LoadState} ...${g} stale=${!!g.previous} />` : null}
      ${!open ? null : t && t.main && Object.values(t).some(a => a.actions?.length) ? html`<${Agent} id="main" depth=${0} />` : NL.DEMO || g.data ? html`<div class="muted small">${NL.DEMO ? 'The demo keeps no record of actions.' : 'Nothing recorded yet.'}</div>` : null}</details>`;
  };

  NL.TextSheet = ({ title, sub, text, path, onClose }) => {
    const g = NL.useGet(path || null), d = g.data || g.previous;
    return html`<${NL.Sheet} title=${title} sub=${sub} onClose=${onClose} wide>
      ${path && (g.error || !d) ? html`<${NL.LoadState} ...${g} stale=${!!g.previous} />` : null}
      ${!path || d ? html`<pre class="plain">${path ? d.text || '(empty)' : text}</pre>` : null}</${NL.Sheet}>`;
  };

  /* ── run rows (Home rail, Runs page, Study page) ───────────────────────── */
  NL.RunRow = ({ r, compact }) => {
    const s = NL.useLab();
    const it = r.subject && NL.item(s, r.subject);
    const budget = r.max_minutes ? r.max_minutes * 60 : null;
    return html`<button type="button" class=${cls('runrow', compact && 'compact', 'tone-' + (NL.RUN_TONE[r.status] || 'muted'))} onClick=${() => NL.openRun(r.run_id)}>
      <span class="runrow-top"><${NL.AgentAvatar} backend=${r.backend} /><${NL.RunPill} r=${r} /><b class="clip grow">${NL.runTitle(r)}</b>${r.usage && r.usage.cost_usd != null ? html`<span class="mono small muted runrow-cost" title="estimated from its token use">≈ $${(+r.usage.cost_usd).toFixed(2)}</span>` : null}</span>
      <span class="runrow-sub muted">${it ? NL.clip(it.title || it.id, 34) : 'the lab'}
        ${r.pending_permissions?.length ? ' · permission requested' : r.status === 'waiting_input' ? (r.pending_question ? ' · asking you' : ' · your turn') : NL.RUN_ACTIVE.has(r.status) && r.last_action ? ' · ' + NL.clip(r.last_action.summary || r.last_action.tool, 60) : r.finished ? ' · ' + NL.ago(r.finished) : ''}</span>
      ${NL.RUN_ACTIVE.has(r.status) && budget && r.elapsed_s != null ? html`<${NL.Bar} value=${r.elapsed_s} max=${budget} />` : null}</button>`;
  };

  /* ── the Runs page ─────────────────────────────────────────────────────── */
  const FILTERS = [
    { id: 'all', label: 'All', f: () => true },
    { id: 'needs', label: 'Waiting for you', f: needsAttention },
    { id: 'live', label: 'Running', f: r => NL.RUN_ACTIVE.has(r.status) },
    { id: 'queued', label: 'Queued', f: r => r.status === 'queued' },
    { id: 'done', label: 'Finished', f: r => r.status === 'completed'&&!r.needs_followup },
    { id: 'bad', label: 'Failed or stopped', f: r => ['failed', 'timeout', 'killed'].includes(r.status) },
  ];
  NL.RunsPage = () => {
    const s = NL.useLab();
    const [f, setF] = useState('all');
    const [q, setQ] = useState('');
    const [sort, setSort] = useState('new');
    const cost = r => +((r.usage || {}).cost_usd || 0);
    const all = (s.runs || []).slice().sort(sort === 'cost' ? (a, b) => cost(b) - cost(a) : (a, b) => (b.created || '').localeCompare(a.created || ''));
    const nRun = all.filter(r => NL.RUN_ACTIVE.has(r.status)).length;
    const flt = FILTERS.find(x => x.id === f);
    const list = all.filter(flt.f).filter(r => !q || (NL.runTitle(r) + ' ' + (r.subject || '')).toLowerCase().includes(q.toLowerCase()));
    const x = NL.exec(s);
    const caps = x.caps || {};
    const working = (s.agents || []).filter(a => a.run_id && a.status !== 'queued');
    const terminals = (s.workers || []).filter(w => w.interactive && w.status !== 'done' && !w.parent && !w.run_id);
    const openAgent = a => (a.run_id ? NL.openRun(a.run_id, a.sub) : a.worker_id && NL.openWorker(a.worker_id));
    return html`<div class="page">
      <header class="page-head"><div><h1>All agents</h1><p class="muted small">Dashboard tasks and connected terminal sessions.</p></div>
        <div class="row">${s.lab_paused ? html`<${NL.Btn} onClick=${() => NL.pauseLab(false)}>Resume all</${NL.Btn}>` : nRun ? html`<${NL.Btn} kind="ghost" onClick=${() => NL.pauseLab(true)} title="Stops every agent; you can resume them">Pause all</${NL.Btn}>` : null}
          <${NL.Btn} kind="primary" icon="＋" onClick=${() => NL.openStart()}>Start task</${NL.Btn}></div></header>
      <div class="statline">
        <span><b>${nRun}</b> dashboard runs active${caps.total ? html` · <a class="link" href="#/settings/autonomy" title="Change dashboard run limit">limit ${caps.total}</a>` : ''}</span><span><b>${all.filter(r => r.status === 'queued').length}</b> queued</span><span><b>${all.filter(needsAttention).length}</b> waiting for you</span><span><b>${terminals.length}</b> ${terminals.length === 1 ? 'terminal session' : 'terminal sessions'}</span>
        ${x.brake ? html`<span class="warn">⚠ daily limit reached: ${x.brake}</span>` : null}
        ${!NL.execOn(s) && !NL.DEMO ? html`<span class="warn">Starting agents from the dashboard is off. <a class="link" href="#/settings/autonomy">Turn it on</a></span>` : null}
      </div>
      ${working.length ? html`<${NL.Section} title="Dashboard agents" count=${working.length}><div class="agents-strip">${working.slice(0, 40).map(a => html`<button type="button" class=${cls('agent-chip', a.parent && 'sub')} onClick=${() => openAgent(a)}
          title=${a.doing ? `${NL.activity(a.doing.kind)[1]}: ${a.doing.summary || a.doing.tool || ''}` : a.last || ''}>
        ${a.parent ? html`<span class="muted">↳</span>` : null}<${NL.RoleDot} role=${a.role} /><span class="clip">${NL.clip(NL.agentTitle(a,s), 70)}</span>
        ${NL.run(s,a.run_id)?.needs_followup ? html`<span class="warn small">Task unfinished</span>` : a.status === 'asking' ? html`<span class="warn small">asking you</span>` : a.doing ? html`<span class="muted small">${NL.activity(a.doing.kind)[0]} ${NL.activity(a.doing.kind)[1]}</span>` : null}</button>`)}</div></${NL.Section}>` : null}
      ${terminals.length ? html`<${NL.Section} title="Terminal sessions" count=${terminals.length}><p class="muted small">Started in a terminal or editor. Reply there.</p>
        <div class="agents-strip">${terminals.slice(0, 12).map(w => html`<button type="button" class="agent-chip" onClick=${() => NL.openWorker(w.worker_id)}>
          <${NL.RoleDot} role=${w.role} /><span class="clip">${NL.clip(NL.agentTitle(w,s), 70)}</span><span class="muted small">${w.status}${(w.children || []).length ? ' · ' + NL.plural(w.children.length, 'subagent') : ''}</span></button>`)}</div></${NL.Section}>` : null}
      <h2 class="runs-history-title">Dashboard run history</h2><div class="toolbar runs-toolbar"><${NL.Tabs} tabs=${FILTERS.map(x2 => ({ id: x2.id, label: x2.label, count: x2.id === 'all' ? null : all.filter(x2.f).length || null }))} value=${f} onChange=${setF} />
        <${NL.Select} value=${sort} onChange=${setSort} ariaLabel="Sort runs" options=${[{ value: 'new', label: 'Newest first' }, { value: 'cost', label: 'Most expensive first' }]} />
        <input class="input search" aria-label="Find a run" placeholder="Find a run…" value=${q} onInput=${e => setQ(e.target.value)} /></div>
      ${list.length ? html`<div class="runlist">${list.slice(0, 200).map(r => html`<${NL.RunRow} key=${r.run_id} r=${r} />`)}</div>`
        : html`<${NL.Empty} icon="▸" title=${all.length ? 'No matching runs' : 'No dashboard runs yet'}>${all.length ? 'Try another filter.' : html`Choose <b>Start task</b> to run an agent here.`}</${NL.Empty}>`}
    </div>`;
  };

  /* ── the agent inspector (a worker = one agent or subagent) ───────────── */
  NL.WorkerSheet = ({ id, onClose }) => {
    const s = NL.useLab();
    const byId = x => ((s.workers) || []).find(w => w.worker_id === x);
    const w = byId(id);
    if (!w) return html`<${NL.Sheet} title="Agent" onClose=${onClose}><${NL.Empty}>This agent has finished and left the lab.</${NL.Empty}></${NL.Sheet}>`;
    const anchor = NL.item(s, w.project || w.idea);
    const parent = w.parent && byId(w.parent);
    const kids = (w.children || []).map(byId).filter(Boolean);
    const acts = (w.recent_actions || []).slice().reverse();
    const run = (s.runs || []).find(r => (w.run_id && r.run_id === w.run_id) || (r.session_id && (r.session_id === w.session_id || r.session_id === w.worker_id)));
    return html`<${NL.Sheet} title=${NL.clip(NL.agentTitle(w,s), 70)} onClose=${onClose}
      sub=${html`<span class="row-wrap"><${NL.RoleDot} role=${w.role} /> ${NL.roleOf(w.role).label} · <span class=${w.status === 'working' ? 'live' : 'muted'}>${w.status}</span> · ${anchor ? html`<a class="link" href=${'#/study/' + anchor.id}>${NL.clip(anchor.title || anchor.id, 30)}</a>` : 'the lab'}</span>`}>
      <div class="row">
        ${run ? html`<${NL.Btn} small onClick=${() => NL.openRun(run.run_id)}>Open its run</${NL.Btn}>` : null}
        ${run && !run.explains ? html`<${NL.Btn} small onClick=${() => NL.explain(run.run_id, w.spawn_id || null)}>Visual summary</${NL.Btn}>` : null}
        ${parent ? html`<${NL.Btn} small onClick=${() => NL.openWorker(parent.worker_id)}>↑ Started by ${NL.clip(parent.label || NL.roleOf(parent.role).label, 30)}</${NL.Btn}>` : null}</div>
      ${w.interactive ? html`<div class="note small">A session started outside the dashboard (a terminal or an editor), traced here by the lab's hooks. Its questions stay in that session.</div>` : null}
      <div class="runmeta"><span><b>${w.n_actions || 0}</b> ${w.n_actions === 1 ? 'action' : 'actions'}</span>${w.started ? html`<span>started ${NL.hhmm(w.started)}</span>` : null}${w.last_ts ? html`<span>last ${NL.hhmm(w.last_ts)}</span>` : null}${w.variant ? html`<span>variant ${w.variant}</span>` : null}</div>
      ${w.in_tool ? html`<div class="now"><i class="dot-live"></i> inside <b>${w.in_tool.tool || 'a tool'}</b> since ${NL.hhmm(w.in_tool.since)}: ${NL.clip(w.in_tool.summary, 200)}</div>` : null}
      ${w.result ? html`<div class="subres"><div class="subres-h">↩ handed back</div><div class="subres-t">${w.result}</div></div>` : null}
      ${kids.length ? html`<${NL.Section} title="Its subagents" count=${kids.length}>${kids.map(k => html`<button type="button" class="agent-chip wide" onClick=${() => NL.openWorker(k.worker_id)}><${NL.RoleDot} role=${k.role} /><span class="clip grow">${k.label || NL.roleOf(k.role).label}</span><span class="muted small">${k.status}</span></button>`)}</${NL.Section}>` : null}
      <${NL.Section} title="What it did">${acts.length ? html`<div class="timeline">${acts.map(a => html`<div class="tl-row"><span class="muted mono small">${NL.hhmm(a.ts)}</span><span class="grow">${a.text || ''}</span><span class="muted small">${a.kind || ''}</span></div>`)}</div>` : html`<div class="muted">No actions logged yet.</div>`}</${NL.Section}>
    </${NL.Sheet}>`;
  };
  NL.openWorker = id => {NL.focusAgent(id);return NL.open(NL.WorkerSheet, { id }, { key: 'worker:'+id,slot:'inspector' })};
})();
