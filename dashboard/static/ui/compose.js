/* ARLOtope — the Workflow lens: how the lab works, in one place, all of it editable.
   The Map draws every workflow as a metro line — its steps are stations (what does the work there, where
   each outcome leads), its checkpoints lanterns you can open, move, add and remove. Then the Instruments
   cabinet, the steps, the procedures (each a skill, with any variants of it), rooms, roles, rules, checks and
   project types — as forms where a form helps, as their files for everything else. Every edit goes into a DRAFT (dashboard/compose.py): nothing reaches the lab or a run
   until the PI reviews it and publishes, and a publish can be undone. Adding anything starts from a copy
   of the closest thing the lab already has. Routes: #/workflow · #/workflow/<list> · #/workflow/<kind>/<name>. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useMemo, cls } = NL;

  /* ── data: GET /api/compose, read again after every edit ─────────────────── */
  const C = { d: null, error: '', read: 0, listeners: new Set() };
  const bump = () => C.listeners.forEach(f => f());
  const reload = async () => { const read = ++C.read, r = await NL.get('/api/compose'); if (read !== C.read) return r;
    C.error = r.error && !r.draft ? r.error : ''; if (!C.error) C.d = r; bump(); return r; };
  const useCompose = () => {
    const [, force] = NL.useReducer(x => x + 1, 0);
    useEffect(() => { C.listeners.add(force); reload(); return () => C.listeners.delete(force); }, []);
    return C.d;
  };
  /** one edit of the draft; toasts the outcome and reads the lab again */
  const edit = async (body, ok) => {
    const r = await NL.api('/api/compose', body);
    if (r && r.ok) { if (ok !== false) NL.toast(ok || r.note, 'ok'); (r.warnings || []).forEach(w => NL.toast(w, 'warn')); await reload(); }
    else NL.toast((r && r.error) || 'That did not work.', 'bad');
    return r || {};
  };
  const stripFm = t => String(t || '').replace(/\r\n/g, '\n').replace(/^---\n[\s\S]*?\n---\n?/, '').trim();
  const slugify = t => String(t || '').toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
  const href = (...p) => '#/workflow/' + p.filter(Boolean).map(encodeURIComponent).join('/');
  const go = (...p) => NL.go(href(...p).slice(2));
  const stateLabel = (d, id) => ((d.steps || []).find(s => s.id === id) || {}).label || id;
  const changes = d => (d && d.draft && d.draft.changes) || [];
  const touched = (d, ...prefixes) => changes(d).some(c => prefixes.some(p => c.path === p || c.path.startsWith(p)));
  const SAVED = 'Draft saved';
  /** a changed file, said plainly: "Room look: The Writing Room", "Procedure: Review the literature — your
   *  instructions"… — from the lab's own names; null when the path says nothing more than itself */
  const describePath = (d, path) => {
    const p = String(path || ''), parts = p.split('/'), file = parts[parts.length - 1];
    const proc = n => ((d.procedures || {})[n] || {}).title || n;
    const role = n => ((d.roles || []).find(r => r.name === n) || {}).label || n;
    const room = n => { const r = (d.rooms || []).find(x => x.id === n) || {}; return r.title || r.label || n; };
    let m;
    if ((m = p.match(/^lab\/rooms3d\/([^/.]+)(?:\.([^/]+))?\.json$/))) return `Room look: ${room(m[1])}${m[2] ? ` (${m[2]} projects)` : ''}`;
    if ((m = p.match(/^\.claude\/skills\/([^/]+)\/(.+)$/))) return `Procedure: ${proc(m[1])} · ${m[2] === 'SKILL.md' ? 'its skill' : m[2]}`;
    if ((m = p.match(/^lab\/workflow\/step\.([^/]+)\.add\.md$/))) return `Step: ${stateLabel(d, m[1])} · your instructions`;
    if ((m = p.match(/^lab\/workflow\/roles\/([^/]+)\.add\.md$/))) return `Role: ${role(m[1])} · your instructions`;
    if ((m = p.match(/^lab\/workflow\/([^/]+)\.add\.md$/))) return `Procedure: ${proc(m[1])} · your instructions`;
    if ((m = p.match(/^agent-roles\/([^/]+)\.(yaml|md)$/))) return `Role: ${role(m[1])} · ${m[2] === 'yaml' ? 'its tools and model' : 'what it is told'}`;
    if (p === 'workflow/steps.yaml') return 'The steps: what does the work at each, and its room';
    if ((m = p.match(/^workflow\/workflows\/([^/]+)\.yaml$/))) { const w = (d.workflows || []).find(x => x.id === m[1]); return `Workflow: ${(w && w.title) || m[1]} · its path, routes and checkpoints`; }
    if (p === 'workflow/rooms.yaml') return 'The rooms';
    if (p === 'workflow/rules.yaml') return 'Rules';
    if ((m = p.match(/^checks\/([^/]+)\.py$/))) { const c = (d.checks || []).find(x => x.file === p); return `Check: ${c ? c.name : m[1].replace(/_/g, '-')}`; }
    if ((m = p.match(/^(?:lab\/)?templates\/project-types\/([^/]+)\//))) return `Project type: ${m[1]}${file !== 'TYPE.md' ? ' · ' + file : ''}`;
    return null;
  };
  /** a changed file: its plain summary, with the path as small secondary text */
  const PathLabel = ({ d, path }) => {
    const say = describePath(d, path);
    return say ? html`<b>${say}</b> <span class="mono muted small">${path}</span>` : html`<b>${path.split('/').pop()}</b> <span class="mono muted small">${path.split('/').slice(0, -1).join('/')}</span>`;
  };

  /* ── unsaved text: every Compose form says whether it holds edits not yet saved to the draft; leaving the
     page (another route, a tab of the same item, closing the browser tab) asks first ───────────────────── */
  const DIRTY = new Map();
  let dirtySeq = 0;
  const anyDirty = () => [...DIRTY.values()].some(Boolean);
  /** mark the calling form dirty (true) or clean; it is forgotten when the form goes away */
  const useDirty = flag => {
    const id = NL.useRef(null);
    if (id.current == null) id.current = ++dirtySeq;
    useEffect(() => { DIRTY.set(id.current, !!flag); }, [!!flag]);
    useEffect(() => () => { DIRTY.delete(id.current); }, []);
  };
  const LEAVE = 'You have unsaved changes. Leave without saving?';
  /** true when it is fine to leave: nothing unsaved, or the PI said to drop it */
  const leaveOk = () => { if (!anyDirty()) return true; if (!window.confirm(LEAVE)) return false; DIRTY.clear(); return true; };
  /** while Compose is open: guard route changes and closing the tab */
  const useLeaveGuard = () => {
    useEffect(() => {
      let last = location.hash;
      // capture, so it runs before the router's own hashchange listener and can stop it
      const onHash = e => {
        if (location.hash === last) return;
        if (leaveOk()) { last = location.hash; return; }
        e.stopImmediatePropagation();
        history.replaceState(history.state, '', last || '#/');
      };
      const onUnload = e => { if (anyDirty()) { e.preventDefault(); e.returnValue = LEAVE; return LEAVE; } };
      window.addEventListener('hashchange', onHash, true);
      window.addEventListener('beforeunload', onUnload);
      return () => { window.removeEventListener('hashchange', onHash, true); window.removeEventListener('beforeunload', onUnload); };
    }, []);
  };
  /** a tab switch inside one item also drops what the open tab holds */
  const guardTab = set => v => { if (leaveOk()) set(v); };

  const KINDS = [
    { id: 'steps', item: 'step', label: 'Task defaults', one: 'step', n: d => (d.steps || []).filter(x => !x.shelf).length, blurb: 'Shared task definitions. A workflow can override these defaults.',
      dirty: d => touched(d, 'workflow/steps.yaml', 'lab/workflow/step.') },
    { id: 'procedures', item: 'procedure', label: 'Skills', one: 'skill', n: d => Object.keys(d.procedures).length, blurb: 'Reusable instructions for agents. Tasks can use a skill or their own instructions.',
      dirty: d => touched(d, '.claude/skills/') || changes(d).some(c => c.path.startsWith('lab/workflow/') && !/^lab\/workflow\/(step\.|roles\/)/.test(c.path)) },
    { id: 'roles', item: 'role', label: 'Subagent roles', one: 'role', n: d => d.roles.length, blurb: 'Reusable instructions for specialist subagents: critics, reviewers and experiment runners.',
      dirty: d => touched(d, 'agent-roles/', 'lab/workflow/roles/') },
    { id: 'rooms', item: 'room', label: 'Rooms', one: 'room', n: d => d.rooms.length, blurb: 'Group related workflow steps and place their agents in the Lab.',
      dirty: d => touched(d, 'lab/rooms3d/') },
    { id: 'rules', item: 'rule', label: 'Rules', one: 'rule', n: d => ['hard', 'subagent', 'project'].reduce((a, g) => a + (d.rules[g] || []).length, 0), blurb: 'What every agent always does. They are written into every agent’s manual.',
      dirty: d => touched(d, 'workflow/rules.yaml') },
    { id: 'checks', item: 'check', label: 'Checks', one: 'check', n: d => d.checks.length, blurb: 'Small programs that enforce a rule mechanically, so it doesn’t rest on an agent’s word.',
      dirty: d => touched(d, 'checks/') },
    { id: 'types', item: 'type', label: 'Project types', one: 'project type', n: d => d.types.length, blurb: 'Kinds of project, each with its own conventions, read by every agent working in one.',
      dirty: d => touched(d, 'templates/', 'lab/templates/') },
  ];
  const KIND_OF = Object.fromEntries(KINDS.map(k => [k.item, k]));

  /* ── the page ─────────────────────────────────────────────────────────────── */
  NL.ComposePage = ({ args, query }) => {
    const d = useCompose();
    const where = args[0] || '', name = args[1] || '';
    useLeaveGuard();
    if (!d) return html`<div class="page"><${NL.LoadState} error=${C.error} reload=${reload} /></div>`;
    if (d.error && !d.steps) return html`<div class="compose"><${Nav} d=${{ ...d, steps: [], workflows: [], procedures: {}, roles: [], rooms: [], rules: {}, checks: [], types: [] }} where="" />
      <main class="cmp-main"><${DemoNote} /><${DraftBar} d=${d} /><div class="cmp-page"><div class="kicker">Workflow</div><h1>The workflow can't be read</h1>
        <div class="note note-warn">${d.error}</div><p class="muted">Fix the file below (or a workflow's, under workflow/workflows/), or discard the draft.</p>
        <${FileEditor} path="workflow/steps.yaml" /></div></main></div>`;
    let body;
    if (!where || where === 'map') body = html`<${MapPage} d=${d} query=${query||{}} />`;
    else if (where === 'instruments') body = html`<div class="cmp-page"><header class="cmp-head"><div class="grow"><div class="kicker">Workflow</div><h1>Instruments</h1>
      </div></header><${NL.Cabinet} /></div>`;
    else if (where === 'suggestions') body = html`<${Suggestions} d=${d} />`;
    else if (where === 'history') body = html`<${History} d=${d} />`;
    else if (where === 'rules') body = html`<${RulesPage} d=${d} />`;
    else if (where === 'domain') body = html`<${DomainEditor} d=${d} name=${name} />`;
    else if (where === 'rule') body = html`<div class="cmp-page"><${ItemHead} k=${KIND_OF.rule} name="rules.yaml" title="The rules, as text" sub="The forms edit this same file. The tables after the rules are read by the lab's safety code and stay as they are." />
      <${FileEditor} path="workflow/rules.yaml" rows=${32} /></div>`;
    else {
      const k = KINDS.find(x => x.id === where || x.item === where);
      const Ed = { step: StepEditor, procedure: ProcedureEditor, role: RoleEditor, room: RoomEditor, check: CheckEditor, type: TypeEditor }[where];
      const List = { steps: StepsList, procedures: ProceduresList, roles: RolesList, rooms: RoomsList, checks: ChecksList, types: TypesList }[where];
      body = Ed ? html`<${Ed} key=${name} d=${d} name=${name} query=${query || {}} />` : List ? html`<${List} d=${d} k=${k} />` : html`<${MapPage} d=${d} />`;
    }
    return html`<div class="compose">
      <${Nav} d=${d} where=${where} />
      <main class="cmp-main"><${DemoNote} />${C.error ? html`<${NL.LoadState} error=${C.error} reload=${reload} stale />` : null}<${DraftBar} d=${d} />${body}</main></div>`;
  };
  /** the demo reads the lab like any page; NL.api refuses every write there (with a toast) */
  const DemoNote = () => NL.DEMO ? html`<div class="cmp-demo" role="note"><${NL.Icon} name="alert" /> Demo: look around. Nothing you change here is saved.</div>` : null;

  const Nav = ({ d, where }) => {
    const on=id=>where===id||(KINDS.find(k=>k.id===id)||{}).item===where;
    const link=k=>html`<a class=${cls('cmp-link',on(k.id)&&'on')} href=${href(k.id)}><span class="grow">${k.label}</span>${k.dirty(d)?html`<i class="cmp-dot" title="Changed in draft"></i>`:null}<span class="cmp-n">${k.n(d)}</span></a>`;
    return html`<nav class="cmp-nav" aria-label="Workflow"><div class="cmp-nav-sec">Your process</div>
      <a class=${cls('cmp-link',(!where||where==='map')&&'on')} href=${href('map')}>Workflows</a>
      ${KINDS.filter(k=>['procedures','rooms'].includes(k.id)).map(link)}
      <details class="cmp-advanced" open=${['steps','step','roles','role','rules','rule','checks','check','types','type','domain','instruments'].includes(where)}><summary>More settings</summary>
        ${KINDS.filter(k=>!['procedures','rooms'].includes(k.id)).map(link)}
        <a class="cmp-link" href=${href('instruments')}>Research instruments</a></details>
      <div class="cmp-nav-sec">Review</div><a class=${cls('cmp-link',where==='suggestions'&&'on')} href=${href('suggestions')}>Agent suggestions</a>
      <a class=${cls('cmp-link',where==='history'&&'on')} href=${href('history')}>Change history</a></nav>`;
  };

  /* ── the draft: a bar on every page, the review, publish / discard ─────────── */
  const discard = async () => {
    if (!await NL.confirm({ title: 'Discard the draft?', ok: 'Discard', danger: true, body: 'All edits since your last publish are lost. The lab is unchanged.' })) return;
    await edit({ op: 'discard' });
  };
  const openReview = () => NL.open(ReviewSheet, {}, { key: 'cmp-review' });
  const DraftBar = ({ d }) => {
    const dr = d.draft || {};
    if (!dr.active) return html`<div class="cmp-bar"><span class="cmp-bar-dot live"></span><span class="grow"><b>Published.</b> Edits stay in draft until published.</span></div>`;
    const n = (dr.changes || []).length, p = (dr.problems || []).length;
    return html`<div class=${cls('cmp-bar', 'draft', p && 'bad')}><span class="cmp-bar-dot"></span>
      <span class="grow"><b>Draft</b> · ${n ? NL.plural(n, 'file') + ' changed' : 'nothing changed yet'}${n ? html` · ${p ? html`<button type="button" class="link danger" onClick=${openReview}>${NL.plural(p, 'problem')} to fix</button>` : html`<span class="ok-t">ready to publish</span>`}` : null}</span>
      <${NL.Btn} small kind="ghost" onClick=${discard}>Discard</${NL.Btn}>
      <${NL.Btn} small kind="primary" disabled=${!n} onClick=${openReview}>Review & publish</${NL.Btn}>
      <span class="cmp-bar-undo muted small"><a class="link" href=${href('history')}>Change log</a></span></div>`;
  };

  const ChangeRow = ({ d, c, open: open0 }) => {
    const [open, setOpen] = useState(!!open0);
    const read = NL.useGet(open ? '/api/compose/file?path=' + encodeURIComponent(c.path) : null, d), f = read.data;
    return html`<div class="cmp-change">
      <button type="button" class="cmp-change-h" onClick=${() => setOpen(!open)}><span class=${'chg chg-' + c.status}>${c.status}</span>
        <span class="grow clip"><${PathLabel} d=${d} path=${c.path} /></span><${NL.Icon} name=${open ? 'caret' : 'chevron'} /></button>
      ${open ? (f ? f.resource ? html`<p class="muted small">Resource file · ${f.bytes} bytes. Included with the skill.</p>` : html`<${NL.Diff} a=${f.published || ''} b=${f.text || ''} context=${3} />` : html`<${NL.LoadState} ...${read} />`) : null}</div>`;
  };
  const ReviewSheet = ({ onClose }) => {
    const d = useCompose() || {};
    const dr = d.draft || {};
    const [note, setNote] = useState('');
    const probs = dr.problems || [], ch = dr.changes || [], affects = dr.affects || [];
    const publish = async () => {
      const r = await edit({ op: 'publish', note }, false);
      if (r.ok) { NL.toast(r.note, 'ok'); onClose(); NL.refresh(); }
    };
    return html`<${NL.Sheet} wide kicker="Workflow" title="Review your draft" sub="Running agents keep their current version. You can undo this publish." onClose=${onClose}
      footer=${html`<${NL.Btn} kind="ghost" onClick=${async () => { await discard(); if (!(C.d.draft || {}).active) onClose(); }}>Discard draft</${NL.Btn}>
        <${NL.Btn} kind="primary" disabled=${!!probs.length || !ch.length} onClick=${publish}>Publish ${ch.length ? NL.plural(ch.length, 'change') : ''}</${NL.Btn}>`}>
      ${probs.length ? html`<div class="cmp-problems"><b>Fix ${probs.length === 1 ? 'this' : 'these'} first</b><ul>${probs.map(p => html`<li>${p}</li>`)}</ul></div>`
        : ch.length ? html`<div class="cmp-ok"><${NL.Icon} name="check" /> The lab reads consistently with these changes.</div>` : null}
      ${affects.length ? html`<${NL.Section} title="Studies it affects" count=${affects.length}><ul class="cmp-affects">${affects.map(a => html`<li>${a}</li>`)}</ul></${NL.Section}>` : null}
      <${NL.Section} title="Changes" count=${ch.length}>${ch.length ? ch.map((c, i) => html`<${ChangeRow} key=${c.path} d=${d} c=${c} open=${ch.length <= 3 && i < 3} />`) : html`<div class="muted">Nothing changed yet.</div>`}</${NL.Section}>
      ${ch.length ? html`<${NL.Field} label="A note for the lab’s history (optional)"><${NL.Input} value=${note} onInput=${setNote} placeholder="e.g. a quicker literature pass for workshop papers" onEnter=${() => !probs.length && publish()} /></${NL.Field}>` : null}
    </${NL.Sheet}>`;
  };

  /* ── the Map: every workflow a metro line; its checkpoints are lanterns ─────────────────────────── */
  const APPROVER = {
    me: { glyph: 'me', title: 'Only you', desc: 'It waits for you, every time.', word: 'you approve' },
    'me-or-campaign': { glyph: 'campaign', title: 'You, or a campaign', desc: 'A campaign you approved may approve it only if its checks pass.', word: 'you or a campaign' },
    auto: { glyph: 'auto', title: 'Approves itself', desc: 'Approved the moment its checks pass; otherwise it waits for you.', word: 'approves itself' },
    agent: {glyph:'review',title:'Independent agent',desc:'A fresh reviewer judges the evidence with your chosen skill.',word:'an independent agent decides'},
  };
  const stepOf = (d, id) => (d.steps || []).find(x => x.id === id) || { id, also: [] };
  const hueOf = (d, id) => NL.roomHue(stepOf(d, id).room);
  const ROOM_G = { incubator: 'seed', study: 'book', lab: 'flask', bench: 'lens', writing: 'pen', archive: 'archive', margins: 'margin' };
  const glyphOf = (d, id) => ROOM_G[stepOf(d, id).room] || 'spark';
  /** the procedure that does a step's work in a workflow: the workflow's variant of it, else the step's own */
  const doesIn = (d, w, st) => { const node=w.nodes?.[st],p=node&&'procedure' in node?node.procedure:stepOf(d,st).do; return p ? w.use?.[p] || p : null; };
  const offers = (d, st, w) => [...new Set([doesIn(d,w,st),...(stepOf(d,st).also||[]).map(p=>w.use?.[p]||p)].filter(Boolean))];
  const procTitle = (d, p) => ((d.procedures || {})[p] || {}).title || p;
  const describeWorkflow = text => NL.launch({ prompt: 'Follow .claude/skills/design/SKILL.md to draft a research workflow change. Requirements:\n' + text });

  const VisualComposition=({d,w})=>{
    const focus=NL.useFocus(),study=NL.item(NL.getState(),focus.study),bound=study?.workflow===w.id;
    const make=()=>w.path.map((id,i)=>({id,label:stepOf(d,id).label||id,procedure:doesIn(d,w,id)||'',room:stepOf(d,id).room,
      next:w.path.slice(i+1,i+2),outcomes:{...(w.routes?.[id]||{})},tags:stepOf(d,id).tags||[],instructions:'',outputs:[],agent:{role:'general',...stepOf(d,id).agent},context:{mode:'fresh'},...(w.nodes?.[id]||{})}));
    const [nodes,setNodes]=useState(make),[saved,setSaved]=useState(JSON.stringify(make()));
    useDirty(JSON.stringify(nodes)!==saved);
    useEffect(()=>{const v=make();setNodes(v);setSaved(JSON.stringify(v))},[w.id,JSON.stringify(w.nodes),JSON.stringify(w.path)]);
    const room=async title=>{let id=title.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||'room',base=id,i=2;while(d.rooms.some(r=>r.id===id))id=base+'-'+i++;
      const result=await edit({op:'copy',kind:'room',like:d.rooms[0]?.id,name:id,plain:true,title,steps:[]});return result.ok?id:null};
    return html`<${NL.WorkflowCanvas} key=${w.id} nodes=${nodes} rooms=${d.rooms} frameworks=${d.frameworks||[]} roles=${d.roles.map(r=>({value:r.name,label:r.label}))}
      focusedTask=${bound?focus.task:null} onSelectTask=${id=>{if(bound)NL.setFocus(id===focus.task?focus:{study:study.id,task:id})}}
      tags=${d.tags||[]} checkpoints=${w.checkpoints||[]} skills=${Object.entries(d.procedures).map(([value,p])=>({value,label:p.title||value,task:p.ui?.task}))} onChange=${setNodes}
      onCreateRoom=${room} onDesignRoom=${id=>NL.openRoomDesign(id)} onEditSkill=${name=>NL.go('workflow/procedure/'+name)}
      onExport=${async()=>{const x=await NL.get('/api/compose/export?workflow='+encodeURIComponent(w.id));if(x.error)return NL.toast(x.error,'bad');const a=document.createElement('a'),bytes=Uint8Array.from(atob(x.data),c=>c.charCodeAt(0)),url=URL.createObjectURL(new Blob([bytes],{type:'application/zip'}));a.href=url;a.download=x.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);NL.toast('Procedure downloaded. Lab tools are required for enforced gates and parallel execution.')}}
      onCheckpoint=${(id,checkpoint)=>openCp(d,w,checkpoint||null,w.path[0]===id&&!w.nodes?{during:id}:{before:id})}
      dirty=${JSON.stringify(nodes)!==saved} onSave=${async()=>{const r=await edit({op:'graph',workflow:w.id,nodes},SAVED);if(r.ok)setSaved(JSON.stringify(nodes))}}/>`;
  };

  const MapPage = ({ d,query={} }) => {
    const s=NL.useLab(),focus=NL.useFocus(),workflows=d.workflows||[],study=NL.item(s,focus.study),wanted=query.workflow||study?.workflow;
    const [machine,setMachine]=useState(''),tools=NL.useGet('/api/frameworks?'+NL.qs({machine}));
    const [selected,setSelected]=useState(()=>workflows.find(w=>w.id===wanted)?.id||workflows.find(w=>w.id===NL.ls.get('workflow-editor-id'))?.id||workflows.find(w=>w.default)?.id||workflows[0]?.id);
    useEffect(()=>{if(wanted&&workflows.some(w=>w.id===wanted))setSelected(wanted)},[wanted]);
    const choose=id=>{setSelected(id);NL.go(NL.focusHref('workflow/map?workflow='+encodeURIComponent(id),study?.workflow===id?focus:{}))};
    useEffect(()=>{if(selected)NL.ls.set('workflow-editor-id',selected)},[selected]);
    const w=workflows.find(w=>w.id===selected)||workflows[0];
    return html`<div class="cmp-page process-page"><header class="cmp-hero"><h1>Workflow</h1></header>
      <details class="process-guide"><summary>How workflows work</summary>
        <div class="process-concepts"><div><span>01</span><h3>Tasks & agents</h3><p>Give each task a skill or instructions. Connect tasks in order or in parallel; change agents when needed.</p></div>
          <div><span>02</span><h3>Shared rooms</h3><p>A task's room is where its agent appears. Tasks and studies share rooms; arrows control what runs next.</p></div>
          <div><span>03</span><h3>Checkpoints</h3><p>Where work waits for a review or a check. You choose what needs approval and what evidence to inspect.</p></div></div>
        <p class="muted small">Edits stay in a draft. Review and publish when ready; the latest publication can be undone.</p>
        <button type="button" class="link small" onClick=${e=>{NL.ls.set('nl-process-introduced',true);e.currentTarget.closest('details').open=false;}}>Got it</button></details>
      <div class="process-toolbar"><${NL.WorkflowPicker} label="Research workflow" workflows=${workflows} value=${w?.id||''} onChange=${choose} blocked=${x=>NL.frameworkBlocked(x,tools.data)}/>
        <${NL.Btn} onClick=${()=>NL.open(NewWorkflow,{onMade:choose}, {kind:'dialog',key:'wf-new'})}>New workflow</${NL.Btn}></div>
      <${NL.FrameworkTools} read=${tools} machine=${machine} onMachine=${setMachine} onInspect=${id=>choose(workflows.find(x=>NL.requiredFrameworks(x).includes(id))?.id||selected)}/>
      ${w ? html`<${Line} d=${d} w=${w} first=${w.default} n=${(s.items||[]).filter(i=>i.workflow===w.id&&!i.finished&&!NL.isShelved(i.state)).length} onCopy=${choose} />` : null}
      <details class="process-agent"><summary>Draft with an agent</summary><p class="muted">Review the draft before publishing.</p>
        <${NL.DescribeBar} what="workflow" placeholder="For example: add a replication review before writing, approved by me." onSend=${describeWorkflow} /></details>
      ${(d.workflow_designs||[]).length ? html`<section class="cmp-sec"><h2>Agent proposals</h2>${d.workflow_designs.map(x=>html`<button type="button" class="search-result" onClick=${()=>NL.open(WorkflowDesign,{x},{key:'wf-design'})}><b>${NL.clip(x.request||x.id,100)}</b><small>${x.problems.length?'Needs revision':'Ready to review'}</small></button>`)}</section>`:null}
    </div>`;
  };

  const CheckpointRow=({d,w,c,ro})=>html`<button type="button" class="process-checkpoint" disabled=${ro} onClick=${()=>openCp(d,w,c)}>
    <span class="checkpoint-label">Checkpoint</span><span class="grow"><b>${c.title||c.id}</b><small>${c.during?'During this step'+(c.at?' · '+c.at:''):'Before this step'} · ${(APPROVER[c.approver]||APPROVER.me).word}</small></span><span>Edit →</span></button>`;

  /** a list's order with `x` moved to where `onto` stands */
  const moved = (xs, x, onto) => { const a = xs.filter(y => y !== x), i = a.indexOf(onto), j = xs.indexOf(onto) > xs.indexOf(x) ? i + 1 : i;
    a.splice(Math.max(0, j), 0, x); return a; };
  /** drag-to-reorder for one list: props for each item, and which one is being dragged / hovered */
  const useReorder = (items, onOrder) => {
    const [drag, setDrag] = useState(null), [over, setOver] = useState(null);
    const props = x => ({ draggable: true,
      onDragStart: e => { e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', x); setDrag(x); },
      onDragEnd: () => { setDrag(null); setOver(null); },
      onDragOver: e => { if (drag && drag !== x) { e.preventDefault(); setOver(x); } },
      onDragLeave: () => setOver(o => o === x ? null : o),
      onDrop: e => { e.preventDefault(); const from = drag; setDrag(null); setOver(null); if (from && from !== x) onOrder(moved(items, from, x)); } });
    return { props, drag, over };
  };

  const Line = ({ d,w,first,n,ro,onCopy }) => {
    const steps=w.path||[], checkpoints=w.checkpoints||[];
    return html`<section class="process-definition"><header class="process-definition-head"><div><h2>${w.title||w.id}</h2><p class="muted">${w.blurb||'Your steps and review decisions.'}</p>
      <span class="muted small">Shared workflow · ${first?'Lab default · ':''}${NL.plural(n||0,'active study','active studies')}</span><${NL.Tags} value=${w.tags||[]}/></div>
      ${ro?null:html`<${NL.Btn} small onClick=${()=>NL.open(NewWorkflow,{like:w.id,onMade:onCopy},{kind:'dialog',key:'wf-new'})}>Make a copy</${NL.Btn}>`}</header>
      ${ro?null:html`<${VisualComposition} d=${d} w=${w}/>`}
      <details class="process-step-details"><summary>Step and checkpoint details</summary><ol class="process-steps">${steps.map((st,i)=>html`<li>
        ${checkpoints.filter(c=>c.before===st).map(c=>html`<${CheckpointRow} key=${c.id} d=${d} w=${w} c=${c} ro=${ro} />`)}
        <div class="process-step"><span class="step-number">${String(i+1).padStart(2,'0')}</span><div class="grow"><button type="button" class="step-title" disabled=${ro} onClick=${()=>NL.open(StationSheet,{d,w,st},{key:'station'})}>${stepOf(d,st).label||st}</button>
          <p>${offers(d,st,w).map(p=>procTitle(d,p)).join(' · ')||'No procedure selected'}</p>
          ${Object.entries((w.routes||{})[st]||{}).map(([outcome,target])=>html`<span class="process-route">${outcome} → ${target==='ask'?'Researcher decides':stateLabel(d,target)}</span>`)}</div>
          ${ro?null:html`<button type="button" class="link small" onClick=${()=>NL.open(StationSheet,{d,w,st},{key:'station'})}>Edit step</button>`}</div>
        ${checkpoints.filter(c=>c.during===st).map(c=>html`<${CheckpointRow} key=${c.id} d=${d} w=${w} c=${c} ro=${ro} />`)}
      </li>`)}</ol></details>
      ${ro?null:html`<footer class="process-definition-foot"><${NL.Btn} small onClick=${()=>openCp(d,w,null,steps.length>1?{before:steps[1]}:{during:steps[0]})}>Add checkpoint</${NL.Btn}>
        <${NL.Btn} small onClick=${()=>NL.open(AboutWorkflow,{w},{kind:'dialog'})}>Workflow details</${NL.Btn}>
        <details><summary>Workflow settings</summary><div class="stack">${!w.nodes?html`<button type="button" class="link small" onClick=${()=>NL.open(StepsEditor,{w},{kind:'dialog',key:'wf-steps'})}>Edit ordered steps</button>`:null}${first?null:html`<button type="button" class="link small" onClick=${()=>edit({op:'workflow',id:w.id,default:true})}>Use as default</button>`}
          <button type="button" class="link small danger" onClick=${async()=>{if(await NL.confirm({title:'Remove this workflow?',body:n?'Studies using it will move to the default workflow when published.':'This change stays in your draft until published.',ok:'Remove',danger:true}))edit({op:'workflow-delete',id:w.id});}}>Remove workflow</button></div></details></footer>`}
    </section>`;
  };

  /** a change the designer drafted (a folder laid over the lab's definition): what it changes, said plainly —
   *  loosened checkpoints first — its notes and files; take it into your draft or leave it */
  const WorkflowDesign = ({ x, onClose }) => {
    const use = async () => { const r = await edit({ op: 'workflow-design-use', id: x.id }); if (r.ok) onClose(); };
    return html`<${NL.Sheet} wide kicker="A drafted change · not in your lab yet" title="What the designer suggests" onClose=${onClose}
      sub=${x.request ? html`You asked: <i>${NL.clip(x.request.replace(/^#.*\n/, ''), 160)}</i>` : null}
      footer=${html`<${NL.Btn} kind="ghost" onClick=${onClose}>Not now</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!!x.problems.length} onClick=${use}>Use this design (into your draft)</${NL.Btn}>`}>
      ${x.problems.length ? html`<div class="note note-warn"><b>It can't be used as it is:</b> ${x.problems.join(' · ')}. Describe it again for another try.</div>` : null}
      <${NL.Section} title="What it changes">${(x.changes || []).length ? html`<ul class="wd-changes">${x.changes.map(c => html`<li>${c}</li>`)}</ul>`
        : html`<div class="muted small">Nothing the lab would notice.</div>`}</${NL.Section}>
      ${x.notes ? html`<div class="voice"><span class="voice-who">the designer's notes</span><${NL.Markdown} text=${x.notes} /></div>` : null}
      <details class="more"><summary>Its files (${(x.files || []).length})</summary><ul class="mono small">${(x.files || []).map(f => html`<li>${f}</li>`)}</ul></details>
      <p class="muted small">Taking it puts it in your draft; Review shows every change and checks the lab still reads consistently before anything is published.</p>
    </${NL.Sheet}>`;
  };

  /** a station: who does the work at that step in this workflow (or a variant), where each outcome leads, and the
   *  checkpoints on it */
  const StationSheet = ({ d: d0, w: w0, st, onClose }) => {
    const d = useCompose() || d0;                      // live: an edit here shows here at once
    const w = (d.workflows || []).find(y => y.id === w0.id) || w0;
    const x = stepOf(d, st), room = (d.rooms || []).find(r => r.id === x.room) || {};
    const own = x.do, does = doesIn(d, w, st), P = d.procedures || {};
    const family = own ? [own, ...((P[own] || {}).variants || [])] : [];
    const routes = (w.routes || {})[st] || {};
    const notes = (P[does] || {}).outcome_notes || {};
    const extra = [...new Set([...((P[does] || {}).outcomes || []), ...Object.keys(routes)])].filter(o => !['done', 'park', 'kill'].includes(o));
    const next = (w.path || [])[(w.path || []).indexOf(st) + 1];
    const swap = v => edit({ op: 'workflow', id: w.id, fields: { use: { ...(w.use || {}), [own]: v === own ? '' : v } } }, SAVED);
    const route = (o, to) => edit({ op: 'route', workflow: w.id, step: st, outcome: o, to: to || null }, SAVED);
    const targets = [{ value: '', label: 'You decide, each time' }, ...(w.path || []).map(y => ({ value: y, label: stateLabel(d, y) })),
      ...(d.steps || []).filter(y => y.shelf).map(y => ({ value: y.id, label: y.label || y.id }))];
    return html`<${NL.Sheet} kicker=${(w.title || w.id) + ' · a step'} title=${x.label || st} onClose=${onClose}
      sub=${html`stands in <a class="link" href=${href('room', room.id || '')} onClick=${onClose}>${room.title || x.room || 'no room'}</a> · <a class="link" href=${href('step', st)} onClick=${onClose}>the step itself</a>`}>
      <${NL.Section} title="Who does the work">${own ? html`
        <a class="cp-line" href=${href('procedure', does)} onClick=${onClose}><span class="start-g"><${NL.Glyph} name=${NL.procGlyph ? NL.procGlyph(does) : 'spark'} size=${17} /></span>
          <span class="grow"><b>${procTitle(d, does)}</b><small class="muted">${does !== own ? `a variant of ${procTitle(d, own)}, in this workflow` : (P[own] || {}).does || ''}</small></span><${NL.Icon} name="chevron" /></a>
        ${family.length > 1 ? html`<${NL.Field} label="In this workflow, use"><${NL.Select} value=${does} onChange=${swap} options=${family.map(v => ({ value: v, label: procTitle(d, v) + (v === own ? ' · the step’s own' : '') }))} /></${NL.Field}>`
          : html`<p class="muted small">To do it differently here, make a variant of the procedure, then pick it here.</p>`}`
        : html`<p class="muted small">Nothing runs here by itself: a study waits at this step until it is moved. Give the step a procedure under <a class="link" href=${href('step', st)} onClick=${onClose}>Steps</a>.</p>`}
        ${(x.also || []).length ? html`<p class="muted small">Also offered here: ${x.also.map(p => procTitle(d, p)).join(', ')}.</p>` : null}</${NL.Section}>
      <${NL.Section} title="Where it goes next">
        <p class="muted small"><b>done</b> → ${next ? stateLabel(d, next) : 'the study is finished'} · <b>park</b> and <b>kill</b> put it on a shelf.</p>
        ${extra.map(o => html`<div class="row route-row"><span class="grow"><span class="mono">${o}</span>${notes[o] ? html` <span class="muted small">· ${notes[o]}</span>` : null}</span>
          <${NL.Select} value=${routes[o] && routes[o] !== 'ask' ? routes[o] : ''} onChange=${v => route(o, v)} options=${targets} /></div>`)}
        ${!extra.length && does ? html`<p class="muted small">${procTitle(d, does)} reports no other outcomes. A procedure lists the ones it can report under its About.</p>` : null}</${NL.Section}>
      <${NL.Section} title="Checkpoints here">${(w.checkpoints || []).filter(c => c.before === st || c.during === st).map(c => html`<button type="button" class="cp-line" onClick=${() => { onClose(); openCp(d, w, c); }}>
          <${NL.Seal} state="waiting" size=${24} /><span class="grow"><b>${c.title || c.id}</b><small class="muted">${c.before ? 'before it starts' : 'during it, at ' + (c.at || 'a point the agent names')}</small></span></button>`)}
        <div class="row">${st !== (w.path || [])[0] ? html`<${NL.Btn} small onClick=${() => { onClose(); openCp(d, w, null, { before: st }); }}><${NL.Glyph} name="plus" size=${14} /> Before it starts</${NL.Btn}>` : null}
          <${NL.Btn} small onClick=${() => { onClose(); openCp(d, w, null, { during: st }); }}><${NL.Glyph} name="plus" size=${14} /> At a point during it</${NL.Btn}></div></${NL.Section}>
    </${NL.Sheet}>`;
  };

  /* ── the checkpoint editor: a lantern, opened ───────────────────────────────────────────────────── */
  const openCp = (d, w, c, place) => NL.open(CheckpointEditor, { d, w, c, place }, { key: 'cp-edit' });
  const checkNames = d => [...new Set([...(d.built_in_checks || []).filter(x => x !== 'approved'), ...(d.checks || []).map(c => c.guard ? c.name : c.file.split('/').pop().replace(/\.py$/, ''))])];
  const ListEditor = ({ value, onChange, placeholder }) => {
    const [t, setT] = useState('');
    const add = () => { if (!t.trim()) return; onChange([...(value || []), t.trim()]); setT(''); };
    return html`<div class="list-ed">${(value || []).map((v, i) => html`<div class="list-ed-row"><span class="ex-l">${String.fromCharCode(65 + i)}</span><span class="mono grow clip">${v}</span>
        <button type="button" class="x" aria-label=${'remove ' + v} onClick=${() => onChange(value.filter((_, j) => j !== i))}><${NL.Icon} name="x" /></button></div>`)}
      <div class="list-ed-add"><input class="input mono" value=${t} placeholder=${placeholder} onInput=${e => setT(e.target.value)} onKeyDown=${e => e.key === 'Enter' && (e.preventDefault(), add())} />
        <${NL.Btn} small disabled=${!t.trim()} onClick=${add}>Add</${NL.Btn}></div></div>`;
  };
  const CheckpointEditor = ({ d, w, c, place, onClose }) => {
    const isNew = !c;
    const init = c ? { ...c } : { id: '', title: '', approver: 'me', ...(place || {}), at: '', evidence: [], checks: [], watch: [], means: '', tell: '' };
    const [f, setF] = useState(init);
    const [newDecision,setNewDecision]=useState('');
    const set = (k, v) => setF(o => ({ ...o, [k]: v }));
    const where = f.during ? 'during' : 'before';
    const step = f.during || f.before || (w.path || [])[0];
    const setWhere = v => setF(o => v === 'during' ? { ...o, during: step, before: undefined } : { ...o, before: step === w.path[0]&&!w.nodes ? w.path[1] : step, during: undefined, at: '' });
    const setStep = v => setF(o => o.during ? { ...o, during: v } : { ...o, before: v });
    const cid = f.id || slugify(f.title);
    const dirty = JSON.stringify(f) !== JSON.stringify(init);
    useDirty(dirty);
    const fields = () => { const o = {}; ['title', 'approver', 'at', 'means', 'tell', 'evidence', 'checks', 'watch', 'judge', 'decisions'].forEach(k => { if(f[k]!=null)o[k]=f[k]; });
      if (f.during) o.during = f.during; else o.before = f.before || step; return o; };
    const save = async () => { const r = await edit({ op: 'checkpoint', workflow: w.id, id: cid, new: isNew, fields: fields() }, SAVED); if (r.ok) onClose(); };
    const remove = async () => { if (!await NL.confirm({ title: `Remove “${c.title || c.id}”?`, ok: 'Remove', danger: true, body: 'Studies stop waiting there once you publish. Approvals already given stay in the record.' })) return;
      const r = await edit({ op: 'checkpoint', workflow: w.id, id: c.id, remove: true }, 'Removed in your draft'); if (r.ok) onClose(); };
    const checks = checkNames(d);
    return html`<${NL.Sheet} className="sheet-permit cpe" onClose=${onClose} title=${null}
      footer=${html`${!isNew ? html`<${NL.Btn} kind="ghost" onClick=${remove}><${NL.Icon} name="trash" /> Remove</${NL.Btn}>` : null}<span class="grow"></span>
        <${NL.Btn} kind="ghost" onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!(f.title || '').trim() || !cid || (where === 'during' && !(f.at || '').trim()) || (!dirty && !isNew)} onClick=${save}>${isNew ? 'Add to draft' : 'Save to draft'}</${NL.Btn}>`}>
      <div class="permit-head"><${NL.Seal} state="waiting" size=${58} /><div class="grow">
        <div class="kicker">${isNew ? 'A new checkpoint' : 'Checkpoint'} · ${w.title || w.id}</div>
        <input aria-label="Checkpoint name" class="cpe-title" value=${f.title || ''} placeholder="Name it, e.g. Approve the replication" onInput=${e => set('title', e.target.value)} autofocus=${isNew} />
        <p class="permit-sentence">${where === 'before' ? html`A study can't start <b>${stepOf(d, step).label || step}</b> until it is approved.` : html`During <b>${stepOf(d, step).label || step}</b>, the agent stops ${f.at ? html`at <b>${f.at}</b>` : 'at the point you name'} and asks.`}</p>
        ${isNew ? html`<div class="muted small">id <input class="input mono cpe-id" value=${cid} onInput=${e => set('id', e.target.value)} /></div>` : html`<div class="mono muted small">${c.id}</div>`}</div></div>
      <div class="permit-body">
        <h4 class="form-h">Who decides</h4>
        <${NL.ChoiceTiles} value=${f.approver || 'me'} onChange=${v => {set('approver',v);if(v==='agent'&&!f.decisions)set('decisions',{proceed:'continue',revise:step,stop:'parked'})}} columns=${2} options=${Object.entries(APPROVER).map(([v, a]) => ({ value: v, glyph: a.glyph, title: a.title, desc: a.desc }))} />
        ${f.approver==='agent'?html`<${NL.Field} label="Review skill"><${NL.Select} value=${f.judge?.skill||'gate-review'} options=${Object.entries(d.procedures).map(([value,p])=>({value,label:p.title||value}))} onChange=${v=>set('judge',{...f.judge,skill:v})}/></${NL.Field}>
        <${NL.AgentChoice} role="reviewer" value=${f.judge?.preset?'preset:'+f.judge.preset:f.judge?.backend?'backend:'+f.judge.backend:''} onChange=${v=>{const {model,effort,...judge}=f.judge||{};set('judge',{...judge,preset:v.startsWith('preset:')?v.slice(7):'',backend:v.startsWith('backend:')?v.slice(8):''})}}/>
        <${NL.Field} label="Review question / rubric"><${NL.Textarea} rows=${3} value=${f.judge?.rubric||''} onInput=${v=>set('judge',{...f.judge,rubric:v})}/></${NL.Field}>
        <${NL.Field} label="Review visit limit"><${NL.Input} type="number" value=${f.judge?.max_visits||''} placeholder="Optional" onInput=${v=>set('judge',{...f.judge,...(v?{max_visits:Number(v)}:{max_visits:undefined})})}/></${NL.Field}>`:null}
        <details><summary>Decision routes</summary><p class="muted small">Each named decision continues, returns to a step, or parks the study.</p>
          ${Object.entries(f.decisions||{proceed:'continue',revise:step,stop:'parked'}).map(([name,to])=>html`<div class="row"><b>${name}</b><${NL.Select} value=${to} ariaLabel=${'Route for '+name} options=${[{value:'continue',label:'Continue past gate'},...w.path.map(id=>({value:id,label:stepOf(d,id).label||id})),{value:'parked',label:'Park study'}]} onChange=${v=>set('decisions',{...(f.decisions||{proceed:'continue',revise:step,stop:'parked'}),[name]:v})}/><button class="link" type="button" onClick=${()=>set('decisions',Object.fromEntries(Object.entries(f.decisions||{proceed:'continue',revise:step,stop:'parked'}).filter(([k])=>k!==name)))}>Remove</button></div>`)}
          <div class="row"><${NL.Input} ariaLabel="New decision name" value=${newDecision} onInput=${setNewDecision} placeholder="New decision name"/><${NL.Btn} small disabled=${!newDecision.trim()} onClick=${()=>{const name=slugify(newDecision);if(name){set('decisions',{...(f.decisions||{proceed:'continue',revise:step,stop:'parked'}),[name]:'continue'});setNewDecision('')}}}>Add decision</${NL.Btn}></div>
        </details>
        <h4 class="form-h">Where it stops a study</h4>
        <div class="row"><${NL.Seg} value=${where} onChange=${setWhere} options=${[{ value: 'before', label: 'Before a step', disabled: w.path.length < 2&&!w.nodes }, { value: 'during', label: 'During a step' }]} />
          <${NL.Picker} value=${step} onChange=${setStep} label="the step" options=${(w.path || []).filter(x => where === 'during' || w.nodes || x !== w.path[0]).map(x => ({ value: x, label: stepOf(d, x).label || x, glyph: glyphOf(d, x), hint: offers(d, x, w).map(p => procTitle(d, p)).join(', ') }))} /></div>
        ${where === 'during' ? html`<${NL.Field} label="At what point" hint="the agent stops there and asks you; e.g. “full-scale runs”"><${NL.Input} value=${f.at || ''} onInput=${v => set('at', v)} placeholder="e.g. sending results outside the lab" /></${NL.Field}>` : null}
        ${where === 'before' ? html`<p class="muted small">A study whose work leads past it waits here. Approving it moves the study on and can start the next step's work in one go.</p>` : null}
        <h4 class="form-h">What you look at</h4>
        <${ListEditor} value=${f.evidence || []} onChange=${v => set('evidence', v)} placeholder="a file; {study} and {project} fill in, e.g. {project}/PLAN.md" />
        <${NL.Field} label="What approving it means" hint="one line, shown on the checkpoint"><${NL.Input} value=${f.means || ''} onInput=${v => set('means', v)} placeholder="e.g. the replication matches within the stated tolerance" /></${NL.Field}>
        <${NL.Field} label="What agents are told" hint="goes into every brief for a study on this workflow"><${NL.Textarea} rows=${2} value=${f.tell || ''} onInput=${v => set('tell', v)} placeholder="e.g. Stop when the replication is done and present it." /></${NL.Field}>
        <details class="more" open=${!!((f.checks || []).length || (f.watch || []).length)}><summary>Checks</summary>
          <p class="muted small">Scripts shown on the checkpoint. A campaign, or “approves itself”, needs every one passing.</p>
          <div class="chips">${checks.map(x => { const on = (f.checks || []).find(y => NL.checkName(y) === x);
            return html`<button type="button" class=${cls('chip-btn', on && 'on')} onClick=${() => set('checks', on ? f.checks.filter(y => NL.checkName(y) !== x) : [...(f.checks || []), x])}>${on ? NL.checkLabel(on) : x}</button>`; })}</div>
          <${NL.Field} label="Notice work done past it" hint="checks run after each run of a study on this workflow, until it is approved: one that finds work done without the approval raises a flag (“went past”)">
            <div class="chips">${checks.map(x => { const on = (f.watch || []).find(y => NL.checkName(y) === x);
              return html`<button type="button" class=${cls('chip-btn', on && 'on')} onClick=${() => set('watch', on ? f.watch.filter(y => NL.checkName(y) !== x) : [...(f.watch || []), x])}>${on ? NL.checkLabel(on) : x}</button>`; })}</div>
            <p class="muted small">A check that takes parameters (e.g. a budget) gets them in the workflow's file: <span class="mono">{budget-under: {usd: 50}}</span>.</p></${NL.Field}></details>
      </div></${NL.Sheet}>`;
  };

  /* ── a workflow's steps, its name, a new one ────────────────────────────────────────────────────── */
  const StepsEditor = ({ w, onClose }) => {
    const d = C.d;
    const [steps, setSteps] = useState(w.path || []);
    const [add, setAdd] = useState('');
    const move = (i, k) => setSteps(xs => { const a = xs.slice(), j = i + k; if (j < 0 || j >= a.length) return a; [a[i], a[j]] = [a[j], a[i]]; return a; });
    const dnd = useReorder(steps, setSteps);
    const lost = (w.checkpoints || []).filter(c => !steps.includes(c.before || c.during));
    const all = (d.steps || []).filter(x => !x.shelf && !steps.includes(x.id));
    const save = async () => { const r = await edit({ op: 'workflow', id: w.id, fields: { path: steps } }, SAVED); if (r.ok) onClose(); };
    return html`<div class="dialog dialog-wide"><h3>The steps of ${w.title || w.id}</h3>
      <p class="muted small">Work follows these steps in order: <b>done</b> takes it to the next one. Drag a step to move it. Steps are shared by every workflow. Open a step to set where alternative outcomes lead.</p>
      <ol class="steps-ed">${steps.map((st, i) => html`<li style=${{ '--h': hueOf(d, st) }} class=${cls(dnd.drag === st && 'dragging', dnd.over === st && 'drop-here')} ...${dnd.props(st)}><span class="steps-dot"><${NL.Glyph} name=${glyphOf(d, st)} size=${15} /></span><span class="grow"><b>${stepOf(d, st).label || st}</b> <span class="muted small">${procTitle(d, doesIn(d, w, st) || '') || 'nothing runs here'}</span></span>
        <button type="button" class="iconbtn sm" title="earlier" disabled=${!i} onClick=${() => move(i, -1)}><${NL.Icon} name="up" /></button>
        <button type="button" class="iconbtn sm" title="later" disabled=${i === steps.length - 1} onClick=${() => move(i, 1)}><${NL.Icon} name="down" /></button>
        <button type="button" class="iconbtn sm" title="take it out" onClick=${() => setSteps(xs => xs.filter(x => x !== st))}><${NL.Icon} name="x" /></button></li>`)}</ol>
      <div class="row"><${NL.Picker} value=${add} onChange=${v => { setSteps(xs => [...xs, v]); setAdd(''); }} placeholder="Add a step…" label="add a step"
        options=${all.map(x => ({ value: x.id, label: x.label || x.id, glyph: glyphOf(d, x.id), hint: x.do ? procTitle(d, x.do) : 'nothing runs here' }))} />
        <button type="button" class="link small" onClick=${() => { onClose(); NL.open(NewStepDialog, { w, after: steps[steps.length - 1] }, { kind: 'dialog' }); }}>or a new step…</button></div>
      ${lost.length ? html`<div class="note note-warn">${lost.map(c => c.title || c.id).join(', ')} ${lost.length === 1 ? 'sits' : 'sit'} on a step you took out; saving removes ${lost.length === 1 ? 'it' : 'them'} too.</div>` : null}
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!steps.length || JSON.stringify(steps) === JSON.stringify(w.path || [])} onClick=${save}>Save to draft</${NL.Btn}></div></div>`;
  };
  const AboutWorkflow = ({ w, onClose }) => {
    const [title, setTitle] = useState(w.title || '');
    const [blurb, setBlurb] = useState(w.blurb || ''),[tags,setTags]=useState(w.tags||[]);
    return html`<div class="dialog"><h3>${w.title || w.id}</h3>
      <${NL.Field} label="Its name"><${NL.Input} value=${title} onInput=${setTitle} autofocus /></${NL.Field}>
      <${NL.Field} label="One line about it" hint="shown when someone picks a workflow for a study"><${NL.Input} value=${blurb} onInput=${setBlurb} /></${NL.Field}>
      <${NL.Field} label="Workflow tags"><${NL.TagInput} ariaLabel="Workflow tags" value=${tags} onChange=${setTags} suggestions=${C.d.tags||[]}/></${NL.Field}><div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!title.trim()} onClick=${async () => { const r = await edit({ op: 'workflow', id: w.id, fields: { title, blurb, tags } }, SAVED); if (r.ok) onClose(); }}>Save to draft</${NL.Btn}></div></div>`;
  };
  const NewWorkflow = ({ like: like0, onClose, onMade }) => {
    const d = C.d;
    const [how, setHow] = useState(like0 ? 'copy' : 'blank');
    const [like, setLike] = useState(like0 || ((d.workflows || [])[0] || {}).id);
    const [title, setTitle] = useState('');
    const [id, setId] = useState('');
    const [say, setSay] = useState('');
    const wid = id || slugify(title);
    const make = async () => {
      if (how === 'describe') { const r = await describeWorkflow(say.trim()); if (r !== null) onClose(); return; }
      const r = await edit({ op: 'workflow', id: wid, new: true, preset:how==='single'?'single-agent':undefined, like: how === 'copy' ? like : undefined, fields: { title } }, `Added ${title} to your draft`);
      if (r.ok) { onClose(); onMade?.(wid); if (how === 'blank') { const w = (C.d.workflows || []).find(x => x.id === wid); if (w) NL.open(StepsEditor, { w }, { kind: 'dialog', key: 'wf-steps' }); } }
    };
    return html`<div class="dialog dialog-wide"><h3>New workflow</h3>
      <${NL.ChoiceTiles} value=${how} onChange=${setHow} columns=${2} options=${[{ value: 'blank', glyph: 'plus', title: 'Blank', desc: 'Pick its steps; add checkpoints after.' },
        {value:'single',glyph:'agent',title:'One lead agent',desc:'Chain skills and instructions in one task.'}, { value: 'copy', glyph: 'metro', title: 'A copy', desc: 'Copy a workflow and adapt it.' }, { value: 'describe', glyph: 'spark', title: 'Describe it', desc: 'The designer drafts it from your words, for you to look at.' }]} />
      ${how === 'describe' ? html`<${NL.Field} label="What should it be like?"><${NL.Textarea} rows=${4} value=${say} onInput=${setSay} autofocus placeholder="e.g. A theory workflow: ideas, a literature pass, a proof sketch I approve, then writing. No experiments." /></${NL.Field}>`
        : html`${how === 'copy' ? html`<${NL.Field} label="Copy"><${NL.Picker} value=${like} onChange=${setLike} options=${(d.workflows || []).map(w => ({ value: w.id, label: w.title || w.id, hint: w.blurb, glyph: 'metro' }))} /></${NL.Field}>` : null}
          <${NL.Field} label="Workflow name"><${NL.Input} value=${title} onInput=${setTitle} autofocus placeholder="e.g. Replication study" /></${NL.Field}>
          <details><summary>Workflow ID</summary><${NL.Field} label="Workflow ID" hint="Generated from the name. Change it if needed; use lower-case letters and dashes."><${NL.Input} mono value=${wid} onInput=${setId} /></${NL.Field}></details>`}
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${how === 'describe' ? !say.trim() : !title.trim() || !wid} onClick=${make}>${how === 'describe' ? 'Ask the designer' : 'Add to draft'}</${NL.Btn}></div></div>`;
  };

  const ListHead = ({ k, children }) => html`<header class="cmp-head"><div class="grow"><a class="kicker" href=${href()}>Workflow</a><h1>${k.label}</h1><p class="lede">${k.blurb}</p></div>
    <div class="row">${children}${k.item === 'procedure' ? html`<${NL.Btn} onClick=${openImportSkill}>Import folder</${NL.Btn}>` : null}${k.item !== 'step' && k.item !== 'rule' ? html`<${NL.Btn} kind="primary" onClick=${() => k.item === 'procedure' ? NL.open(CreateSkill, {}, {kind:'dialog'}) : openNew(k.item)}><${NL.Icon} name="plus" /> New ${k.one}</${NL.Btn}>` : null}</div></header>`;
  const ItemHead = ({ k, name, title, sub, chips, actions }) => html`<header class="cmp-head"><div class="grow">
      <div class="kicker"><a href=${href(k.id)}>${k.label}</a> / ${name}</div><h1>${title}</h1>${sub ? html`<p class="lede">${sub}</p>` : null}
      ${chips ? html`<div class="row cmp-chips">${chips}</div>` : null}</div><div class="row">${actions}</div></header>`;
  const Origin = ({ o, like }) => html`<span class=${cls('pill', o === 'yours' ? 'pill-live' : '')}>${o === 'yours' ? (like ? `yours · from ${like}` : 'yours') : 'built in'}</span>`;
  const CopyBtn = ({ kind, like }) => html`<${NL.Btn} small onClick=${() => openNew(kind, { like })}><${NL.Icon} name="copy" /> Make a copy</${NL.Btn}>`;
  const DeleteBtn = ({ kind, name, label, body, title, extra }) => html`<${NL.Btn} small kind="ghost" onClick=${async () => {
    if (!await NL.confirm({ title: title || `Remove ${label}?`, ok: 'Remove', danger: true, body: body || 'It is removed in your draft; the lab keeps it until you publish.' })) return;
    const r = await edit({ op: 'delete', kind, name, ...(extra || {}) }); if (r.ok) go(KIND_OF[kind].id); }}><${NL.Icon} name="trash" /> Remove</${NL.Btn}>`;

  /** one definition file: edit it in the draft, compare it with the published one */
  const FileEditor = ({ path, intro, rows, onSaved }) => {
    const read = NL.useGet('/api/compose/file?path=' + encodeURIComponent(path)), f = read.data || read.previous;
    const [t, setT] = useState('');
    const [view, setView] = useState('edit');
    const loaded = NL.useRef(null);
    const load = read.reload;
    NL.useLayoutEffect(() => { if (read.data) { const previous = loaded.current, text = read.data.text || '';
      setT(t => previous?.path === path && t !== previous.text ? t : text); loaded.current = { path, text }; } }, [read.data]);
    useEffect(() => { setView('edit'); }, [path]);
    const dirty = !!f && !f.error && t !== (f.text || '');
    useDirty(dirty);
    if (!f) return html`<${NL.LoadState} ...${read} />`;
    if (f.resource) return html`<div class="cmp-file"><p class="mono">${path}</p><p class="muted">Resource file · ${f.bytes} bytes. Included with the skill; edit it in its folder.</p></div>`;
    const state = f.text == null ? 'removed' : f.published == null ? 'new' : f.text !== f.published ? 'edited' : null;
    const save = async () => { const r = await edit({ op: 'write', path, text: t }, SAVED); if (r.ok) { await load(); onSaved && onSaved(); } };
    const revert = async () => { const r = await edit({ op: 'write', path, text: f.published }, 'Back to the published version'); if (r.ok) load(); };
    return html`<div class="cmp-file">
      ${read.error ? html`<${NL.LoadState} ...${read} stale />` : null}
      ${intro ? html`<p class="muted small">${intro}</p>` : null}
      <div class="cmp-file-bar"><${NL.Icon} name="file" /><span class="mono clip grow">${path}</span>${state ? html`<span class=${'chg chg-' + (state === 'edited' ? 'changed' : state === 'new' ? 'added' : 'removed')}>${state}</span>` : null}
        ${f.published != null && f.text != null ? html`<${NL.Seg} value=${view} onChange=${setView} options=${[{ value: 'edit', label: 'Edit' }, { value: 'diff', label: 'Changes' }]} />` : null}</div>
      ${view === 'diff' ? html`<${NL.Diff} a=${f.published || ''} b=${t} context=${4} />`
        : html`<textarea class="cmp-code" spellcheck="false" rows=${rows || 22} value=${t} onInput=${e => setT(e.target.value)}
            onKeyDown=${e => { if ((e.key === 's' || e.key === 'Enter') && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (dirty && read.data) save(); } }}></textarea>`}
      <div class="row end">${state && f.published != null ? html`<${NL.Btn} small kind="ghost" onClick=${revert}><${NL.Icon} name="undo" /> Back to published</${NL.Btn}>` : null}
        ${dirty ? html`<${NL.Btn} small kind="ghost" onClick=${() => setT(f.text || '')}>Cancel</${NL.Btn}>` : null}
        <${NL.Btn} small kind="primary" disabled=${!dirty || !read.data} onClick=${save}>Save to draft</${NL.Btn}></div></div>`;
  };
  const FilesTab = ({ files, intro, onSaved }) => {
    const first = files.find(f=>f.endsWith('/SKILL.md')) || files[0];
    const [sel, setSel] = useState(first);
    useEffect(() => { if (!files.includes(sel)) setSel(first); }, [files.join('|')]);
    if (!files.length) return html`<div class="muted">No files.</div>`;
    return html`<div class="cmp-files">${files.length > 1 ? html`<div class="cmp-file-list">${files.map(f => html`<button type="button" class=${cls('cmp-file-pick', f === sel && 'on')} onClick=${() => f !== sel && leaveOk() && setSel(f)}>${f.split('/').slice(-1)[0]}<small class="mono">${f.split('/').slice(0, -1).join('/')}</small></button>`)}</div>` : null}
      <div class="grow"><${FileEditor} key=${sel} path=${sel} intro=${intro} onSaved=${onSaved} /></div></div>`;
  };
  /** instructions the brief adds — edited as plain text, saved to the draft */
  const LayerText = ({ path, kind, name, placeholder, hint, rows, onSaved, saveLabel }) => {
    const read = NL.useGet('/api/compose/file?path=' + encodeURIComponent(path)), f = read.data || read.previous, cur = f ? stripFm(f.text) : null;
    const [t, setT] = useState('');
    const loaded = NL.useRef(null);
    const load = read.reload;
    NL.useLayoutEffect(() => { if (read.data) { const previous = loaded.current, text = stripFm(read.data.text);
      setT(t => previous?.path === path && t !== previous.text ? t : text); loaded.current = { path, text }; } }, [read.data]);
    useDirty(cur != null && t.trim() !== cur);
    if (cur == null) return html`<${NL.LoadState} ...${read} />`;
    const save = async text => { const r = await edit({ op: 'instructions', kind, name, text }, text.trim() ? SAVED : 'Removed in the draft'); if (r.ok) { await load(); onSaved && onSaved(text); } };
    return html`<div class="wf-editor">
      ${read.error ? html`<${NL.LoadState} ...${read} stale />` : null}
      <${NL.Textarea} value=${t} rows=${rows || 9} onInput=${setT} placeholder=${placeholder} mono onSubmit=${() => read.data && save(t)} />
      ${hint ? html`<div class="field-hint">${hint}</div>` : null}
      <div class="row end">${cur ? html`<${NL.Btn} small kind="ghost" disabled=${!read.data} onClick=${() => save('')}>Remove</${NL.Btn}>` : null}
        <${NL.Btn} small kind="primary" disabled=${!read.data || t.trim() === cur} onClick=${() => save(t)}>${saveLabel || 'Save to draft'}</${NL.Btn}></div></div>`;
  };
  const useTab = (query, first) => {
    const [t, setT] = useState((query && query.tab) || first);
    useEffect(() => { if (query && query.tab) setT(query.tab); }, [query && query.tab]);
    return [t, guardTab(setT)];
  };

  /* ── procedures ───────────────────────────────────────────────────────────── */
  const GROUPS = [['stage', 'Task skills', 'Reusable methods for tasks and their outcomes.'], ['driver', 'Drivers', 'Carry studies through several steps on their own.'],
    ['entry', 'Ways in', 'Start something new.'], ['utility', 'Utilities', 'Everything else agents can be asked to do.']];
  const openImportSkill = () => NL.open(ImportSkill, {}, {kind:'dialog', key:'skill-import'});
  const ImportSkill = ({onClose}) => {
    const [path, setPath] = useState(''), [info, setInfo] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
    const preview = async folder => {
      setPath(folder); setInfo(null); setError(''); setBusy(true);
      try { const r = await NL.api('/api/compose', {op:'skill-import', path:folder, preview:true});
        if (r.error) setError(r.error); else setInfo({...r.skill, exists:r.exists});
      } finally { setBusy(false); }
    };
    const add = async () => { setBusy(true); try { const r = await edit({op:'skill-import', path}); if (r.ok) {onClose(); NL.go(`workflow/procedure/${info.name}?tab=files`);} } finally {setBusy(false);} };
    return html`<div class="dialog"><h3>Import a skill</h3><p class="muted">Choose a folder containing SKILL.md. Its references, scripts and assets come with it.</p>
      <div class="row"><${NL.Input} ariaLabel="Skill folder" disabled=${busy} value=${path} onInput=${v=>{setPath(v);setInfo(null);}} placeholder="Folder on this machine"/>
        <${NL.Btn} disabled=${busy} onClick=${()=>NL.pickFolder({initial:path,onPick:preview,title:'Choose a skill folder'})}>Browse</${NL.Btn}>
        <${NL.Btn} disabled=${busy||!path.trim()} onClick=${()=>preview(path)}>Check</${NL.Btn}></div>
      ${error?html`<p class="note bad">${error}</p>`:null}
      ${info?html`<div class="stack"><h4>/${info.name}</h4><p>${info.description}</p><span class="muted small">${info.files.length} files · ${Math.ceil(info.bytes/1024)} KB</span>
        ${info.exists?html`<p class="note">This name is already in your Lab. Use it, or rename your source skill and its folder.</p>`:html`<p class="muted small">Added as a draft. Review and publish before using it.</p>`}</div>`:null}
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${busy||!info||info.exists} onClick=${add}>Add to draft</${NL.Btn}></div></div>`;
  };
  const CreateSkill = ({onClose}) => {
    const [title,setTitle]=useState(''),[description,setDescription]=useState(''),[text,setText]=useState(''),[busy,setBusy]=useState(false);
    const name=slugify(title);
    const save=async()=>{setBusy(true);try{const r=await edit({op:'skill-create',name,description,text});if(r.ok){onClose();go('procedure',name);}}finally{setBusy(false);}};
    return html`<div class="dialog dialog-wide"><h3>New skill</h3>
      <${NL.Field} label="Name"><${NL.Input} value=${title} onInput=${setTitle}/></${NL.Field}>
      <${NL.Field} label="When to use it"><${NL.Input} value=${description} onInput=${setDescription}/></${NL.Field}>
      <${NL.Field} label="Instructions"><${NL.Textarea} rows=${10} value=${text} onInput=${setText}/></${NL.Field}>
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${busy||!name||!description.trim()||!text.trim()} onClick=${save}>Add to draft</${NL.Btn}></div></div>`;
  };
  const ProcRow = ({ d, name, p }) => {
    const cu = (d.custom.procedures || {})[name] || {};
    return html`<a class="cmp-row" href=${href('procedure', name)}>
      <div class="cmp-row-main"><div class="row"><b>${p.title}</b><span class="mono muted small">/${name}</span>${touched(d, `.claude/skills/${name}/`, `lab/workflow/${name}.`) ? html`<i class="cmp-dot" title="changed in your draft"></i>` : null}</div>
        <div class="muted small clip">${p.does || p.description}</div><${NL.Tags} value=${p.tags||[]}/></div>
      <div class="cmp-row-side">${(p.steps || []).map(x => html`<span class="chip">${stateLabel(d, x)}</span>`)}
        ${p.like ? html`<span class="pill">a variant of /${p.like}</span>` : (p.variants || []).length ? html`<span class="pill">${NL.plural(p.variants.length, 'variant')}</span>` : null}
        ${cu.add ? html`<span class="pill pill-state">+ instructions</span>` : null}
        ${p.origin === 'yours' ? html`<${Origin} o="yours" like=${p.like} />` : null}</div></a>`;
  };
  const ProceduresList = ({ d, k }) => {
    const [q, setQ] = useState('');
    const all = Object.entries(d.procedures).filter(([n, p]) => !q || `${n} ${p.title} ${p.does} ${p.description} ${(p.tags||[]).join(' ')}`.toLowerCase().includes(q.toLowerCase()));
    const eng = all.filter(([, p]) => p.engineering);
    return html`<div class="cmp-page"><${ListHead} k=${k}><input class="input search" placeholder="Find a procedure…" value=${q} onInput=${e => setQ(e.target.value)} /></${ListHead}>
      ${GROUPS.map(([kind, title, sub]) => { const xs = all.filter(([, p]) => !p.engineering && (p.kind || 'utility') === kind); return xs.length ? html`
        <section class="cmp-sec"><div class="cmp-sec-h"><h2>${title}</h2><span class="muted small grow">${sub}</span><span class="cmp-n">${xs.length}</span></div>
          <div class="cmp-rows">${xs.map(([n, p]) => html`<${ProcRow} key=${n} d=${d} name=${n} p=${p} />`)}</div></section>` : null; })}
      ${eng.length ? html`<details class="cmp-sec more"><summary>Engineering helpers <span class="cmp-n">${eng.length}</span></summary><div class="cmp-rows">${eng.map(([n, p]) => html`<${ProcRow} key=${n} d=${d} name=${n} p=${p} />`)}</div></details>` : null}
    </div>`;
  };

  const ProcedureEditor = ({ d, name, query }) => {
    const p = d.procedures[name];
    const [tab, setTab] = useTab(query, 'about');
    if (!p) return html`<${Missing} k=${KIND_OF.procedure} name=${name} />`;
    const cu = (d.custom.procedures || {})[name] || {};
    const family = (d.procedures[p.like || name] || {}).variants || [];
    const tabs = [{ id: 'about', label: 'About' }, { id: 'variants', label: 'Variants', count: family.length || null },
      { id: 'instructions', label: 'Your instructions' }, { id: 'files', label: 'Its skill', count: p.files.length }];
    return html`<div class="cmp-page">
      <${ItemHead} k=${KIND_OF.procedure} name=${'/' + name} title=${p.title} sub=${p.does}
        chips=${html`<${Origin} o=${p.origin} like=${p.like} />${p.like ? html`<a class="pill" href=${href('procedure', p.like)}>a variant of /${p.like}</a>` : null}${cu.add ? html`<span class="pill pill-state">+ your instructions</span>` : null}`}
        actions=${html`<${CopyBtn} kind="procedure" like=${name} /><${DeleteBtn} kind="procedure" name=${name} label=${'/' + name} body=${'Its folder is removed in your draft, and it leaves every step. If anything still names it, Review will say so before you publish.'} />`} />
      <${NL.Tabs} tabs=${tabs} value=${tab} onChange=${setTab} />
      <div class="tabpane">
        ${tab === 'about' ? html`<${ProcAbout} key=${JSON.stringify(p)} d=${d} name=${name} p=${p} />` : null}
        ${tab === 'variants' ? html`<${VariantsTab} d=${d} name=${name} p=${p} />` : null}
        ${tab === 'instructions' ? html`<div class="cmp-narrow"><p class="muted">Added to <b>${p.title}</b> every time it runs, anywhere in the lab, on top of its skill. Write what you'd tell a new lab member: preferences, must-dos, datasets or tools to use, things to avoid.</p>
          <${LayerText} path=${`lab/workflow/${name}.add.md`} kind="add" name=${name} placeholder=${'e.g.\n- Always compare against the strongest 2024 baseline.\n- Never use dataset X (license).'} /></div>` : null}
        ${tab === 'files' ? html`<${FilesTab} files=${p.files} intro="SKILL.md contains the instructions and metadata. References, scripts and assets stay beside it." />` : null}
      </div></div>`;
  };

  /** a procedure and its variants: copies that do the same job their own way, each usable in the original's place */
  const VariantsTab = ({ d, name, p }) => {
    const base = p.like || name, family = [base, ...((d.procedures[base] || {}).variants || [])];
    const usedIn = v => (d.workflows || []).filter(w => Object.values(w.use || {}).includes(v)).map(w => w.title || w.id);
    return html`<div class="cmp-narrow">
      <p class="muted">A variant does the same job as <b>${procTitle(d, base)}</b>, its own way. It keeps the original's definition (its outcomes, what it must produce, where it runs) except what it changes, and its skill is yours to rewrite. A workflow (open one of its stations on the Map), or a single study, can use it in the original's place.</p>
      <div class="cmp-rows">${family.map(v => html`<a class=${cls('cmp-row', v === name && 'on')} href=${href('procedure', v)}>
        <div class="cmp-row-main"><div class="row"><b>${procTitle(d, v)}</b><span class="mono muted small">/${v}</span>${v === base ? html`<span class="pill">the original</span>` : null}</div>
          <div class="muted small clip">${(d.procedures[v] || {}).does || ''}</div></div>
        <div class="cmp-row-side">${usedIn(v).map(t => html`<span class="chip">used in ${t}</span>`)}</div></a>`)}</div>
      <div class="row"><${NL.Btn} kind="primary" onClick=${() => openNew('procedure', { like: base })}><${NL.Icon} name="plus" /> Make a variant</${NL.Btn}></div></div>`;
  };

  /** the outcomes a procedure can report besides done, park and kill — each with what it means */
  const OutcomesEditor = ({ value, onChange }) => {
    const [o, setO] = useState('');
    const [n, setN] = useState('');
    const v = value || {};
    const k = slugify(o);
    const add = () => { if (!k || ['done', 'park', 'kill'].includes(k)) return; onChange({ ...v, [k]: n.trim() }); setO(''); setN(''); };
    return html`<div class="list-ed">${Object.entries(v).map(([x, note]) => html`<div class="list-ed-row"><span class="mono">${x}</span><span class="muted small grow clip">${note}</span>
        <button type="button" class="x" aria-label=${'remove ' + x} onClick=${() => { const c = { ...v }; delete c[x]; onChange(c); }}><${NL.Icon} name="x" /></button></div>`)}
      <div class="list-ed-add"><input class="input mono" value=${o} placeholder="e.g. more-experiments" onInput=${e => setO(e.target.value)} />
        <input class="input" value=${n} placeholder="what it means" onInput=${e => setN(e.target.value)} onKeyDown=${e => e.key === 'Enter' && (e.preventDefault(), add())} />
        <${NL.Btn} small disabled=${!k || ['done', 'park', 'kill'].includes(k)} onClick=${add}>Add</${NL.Btn}></div></div>`;
  };

  const ICONS_START = ['▸', '✦', '◫', '⟳', '✎', '⌕', '☰', '◎', '△', '❖'];
  const ProcAbout = ({ d, name, p }) => {
    const outs = Object.fromEntries((p.outcomes || []).map(o => [o, (p.outcome_notes || {})[o] || '']));
    const init = { title: p.title || '', does: p.does || '', description: p.description || '', stops: p.stops || '', show_pi: p.show_pi || '', kind: p.kind, level: p.level, mode: p.mode,
      tags:p.tags||[], args: p.args || '', hint: p.hint || '', launchable: !!p.launchable, start: p.start || null, outcomes: outs };
    const [f, setF] = useState(init);
    const set = (k, v) => setF(o => ({ ...o, [k]: v }));
    const fields = Object.fromEntries(Object.entries(f).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(init[k])));
    if (fields.outcomes && !Object.keys(fields.outcomes).length) fields.outcomes = [];
    const dirty = Object.keys(fields).length > 0;
    useDirty(dirty);
    const from = k => p.like && !(p.own || []).includes(k) ? html`<span class="muted">from /${p.like}</span>` : null;
    const save = () => edit({ op: 'procedure', name, fields }, SAVED);
    return html`<div class="cmp-form">
      <div class="grid2"><${NL.Field} label="Title" hint=${from('title')}><${NL.Input} value=${f.title} onInput=${v => set('title', v)} /></${NL.Field}>
        <${NL.Field} label="When it stops" hint=${from('stops') || 'e.g. “with the verdict”'}><${NL.Input} value=${f.stops} onInput=${v => set('stops', v)} /></${NL.Field}></div>
      <${NL.Field} label="What it shows you" hint=${from('show_pi') || 'what the agent publishes for you to look at (Results), e.g. “the headline findings and the key figure”; blank = nothing'}><${NL.Input} value=${f.show_pi} onInput=${v => set('show_pi', v)} /></${NL.Field}>
      <${NL.Field} label="What it does (one line)" hint="shown on buttons and lists"><${NL.Input} value=${f.does} onInput=${v => set('does', v)} /></${NL.Field}>
      <${NL.Field} label="Tags"><${NL.TagInput} value=${f.tags} onChange=${v=>set('tags',v)} suggestions=${d.tags||[]}/></${NL.Field}><${NL.Field} label="Description for agents" hint="agent CLIs read this to know when the skill applies"><${NL.Textarea} rows=${3} value=${f.description} onInput=${v => set('description', v)} /></${NL.Field}>
      <${NL.Field} label="Outcomes it can report" hint=${from('outcomes') || 'besides done, park and kill. A workflow says where each leads (open a station on the Map); one it doesn’t route comes to you.'}>
        <${OutcomesEditor} value=${f.outcomes} onChange=${v => set('outcomes', v)} /></${NL.Field}>
      ${(p.steps || []).length ? html`<p class="muted small">Does the work at ${p.steps.map(x => stateLabel(d, x)).join(', ')}. Change that under <a class="link" href=${href('steps')}>Steps</a>.</p>` : null}
      <${NL.Toggle} on=${!!f.start} onChange=${v => set('start', v ? { icon: '▸', order: 50, ...(p.start || {}) } : null)} label="Offer in Start task" sub="Available from All agents." />
      ${f.start ? html`<div class="grid3"><${NL.Field} label="Icon"><div class="row">${ICONS_START.map(i => html`<button type="button" class=${cls('chip', 'click', f.start.icon === i && 'on')} onClick=${() => set('start', { ...f.start, icon: i })}>${i}</button>`)}</div></${NL.Field}>
        <${NL.Field} label="Its label there" hint="blank = the title"><${NL.Input} value=${f.start.title || ''} onInput=${v => set('start', { ...f.start, title: v || undefined })} /></${NL.Field}>
        <${NL.Field} label="Position" hint="lower comes first"><${NL.Input} type="number" value=${f.start.order ?? 50} onInput=${v => set('start', { ...f.start, order: +v })} /></${NL.Field}></div>` : null}
      <details class="more"><summary>How it runs</summary><div class="grid2">
        <${NL.Field} label="Kind" hint=${from('kind')}><${NL.Select} value=${f.kind} onChange=${v => set('kind', v)} options=${[{ value: 'stage', label: 'Step: does a step’s work' }, { value: 'driver', label: 'Driver: runs several steps' }, { value: 'entry', label: 'Way in: starts something new' }, { value: 'utility', label: 'Utility' }]} /></${NL.Field}>
        <${NL.Field} label="Runs in" hint=${from('level')}><${NL.Select} value=${f.level} onChange=${v => set('level', v)} options=${[{ value: 'hub', label: 'the lab' }, { value: 'project', label: 'a study’s project repo' }]} /></${NL.Field}>
        <${NL.Field} label="Talks with you?" hint=${from('mode')}><${NL.Select} value=${f.mode} onChange=${v => set('mode', v)} options=${[{ value: 'headless', label: 'No, it works on its own' }, { value: 'interactive', label: 'Yes, it asks you questions' }]} /></${NL.Field}>
        <${NL.Field} label="Arguments" hint=${from('args') || 'slug = a study · text = free text · ? = optional'}><${NL.Input} mono value=${f.args} onInput=${v => set('args', v)} /></${NL.Field}>
      </div>
      <${NL.Toggle} on=${f.launchable} onChange=${v => set('launchable', v)} label="Can be started from the dashboard" sub="otherwise only another procedure, a step or an agent runs it" /></details>
      <div class="row end sticky-save">${dirty ? html`<span class="muted small">unsaved</span><${NL.Btn} small kind="ghost" onClick=${() => setF(init)}>Cancel</${NL.Btn}>` : null}
        <${NL.Btn} kind="primary" disabled=${!dirty} onClick=${save}>Save to draft</${NL.Btn}></div></div>`;
  };

  /* ── steps ───────────────────────────────────────────────────────────────── */
  const studiesAt = (d, id) => (d.studies_at || {})[id] || 0;
  const onWorkflows = (d, id) => (d.workflows || []).filter(w => (w.path || []).includes(id));
  const StepsList = ({ d, k }) => {
    const [q,setQ]=useState('');
    return html`<div class="cmp-page"><${ListHead} k=${k}><${NL.Input} ariaLabel="Find a step" value=${q} onInput=${setQ} placeholder="Find a step or tag…"/><${NL.Btn} kind="primary" onClick=${() => NL.open(NewStepDialog, {}, { kind: 'dialog' })}><${NL.Icon} name="plus" /> New step</${NL.Btn}></${ListHead}>
    <div class="cmp-rows">${(d.steps || []).filter(x=>!q||[x.label,x.id,...(x.tags||[])].join(' ').toLowerCase().includes(q.toLowerCase())).map(x => html`<a class="cmp-row" href=${href('step', x.id)}>
      <span class="steps-dot" style=${{ '--h': hueOf(d, x.id) }}><${NL.Glyph} name=${glyphOf(d, x.id)} size=${15} /></span>
      <div class="cmp-row-main"><div class="row"><b>${x.label || x.id}</b><span class="mono muted small">${x.id}</span>${x.shelf ? html`<span class="pill">a shelf</span>` : null}${touched(d, `lab/workflow/step.${x.id}.`) ? html`<i class="cmp-dot" title="changed in your draft"></i>` : null}</div>
        <div class="muted small">${x.do ? procTitle(d, x.do) : x.shelf ? 'parked or killed studies rest here' : 'nothing runs here; a study waits until it is moved'}${(x.also || []).length ? ' · also ' + x.also.map(q => procTitle(d, q)).join(', ') : ''}</div><${NL.Tags} value=${x.tags||[]}/></div>
      <div class="cmp-row-side">${onWorkflows(d, x.id).map(w => html`<span class="chip">${w.title || w.id}</span>`)}${studiesAt(d, x.id) ? html`<span class="cmp-n" title="studies here now">${studiesAt(d, x.id)}</span>` : null}</div></a>`)}</div>
    <p class="muted small cmp-foot">Under the hood: <a class="link" href=${href('step', '_file')}>workflow/steps.yaml</a>, and one file per workflow in workflow/workflows/.</p></div>`;
  };

  const StepEditor = ({ d, name, query }) => {
    const [tab, setTab] = useTab(query, 'about');
    if (name === '_file') return html`<div class="cmp-page"><${ItemHead} k=${KIND_OF.step} name="steps.yaml" title="The steps, as text" sub="Every step a workflow can use: its label, the procedure that does its work, what else is offered there, and its room. The forms edit this same file." />
      <${FileEditor} path="workflow/steps.yaml" rows=${28} /></div>`;
    const x = (d.steps || []).find(y => y.id === name);
    if (!x) return html`<${Missing} k=${KIND_OF.step} name=${name} />`;
    const cps = (d.workflows || []).flatMap(w => (w.checkpoints || []).filter(c => (c.before || c.during) === name).map(c => ({ ...c, wf: w })));
    const n = studiesAt(d, name), on = onWorkflows(d, name);
    return html`<div class="cmp-page">
      <${ItemHead} k=${KIND_OF.step} name=${name} title=${x.label || name} sub=${x.shelf ? 'A shelf: studies that are parked or killed rest here, until you bring one back.' : `On ${on.map(w => w.title || w.id).join(', ') || 'no workflow yet. Add it to one from the Map'}`}
        actions=${x.shelf ? null : html`<${DeleteBtn} kind="step" name=${name} label=${'the step ' + (x.label || name)} body=${`It leaves every workflow, with its routes and the checkpoints on it.${n ? ` ${NL.plural(n, 'study', 'studies')} stand${n === 1 ? 's' : ''} here now. Review says so before you publish.` : ''}`} />`} />
      <${NL.Tabs} tabs=${[{ id: 'about', label: 'About' }, ...(x.shelf ? [] : [{ id: 'instructions', label: 'Your instructions' }])]} value=${tab} onChange=${setTab} />
      <div class="tabpane">${tab === 'about' ? html`<${StepAbout} key=${JSON.stringify(x)} d=${d} x=${x} cps=${cps} />` : html`<div class="cmp-narrow">
        <p class="muted">Added to whatever runs at ${x.label || name}, in every workflow, on top of each procedure's own instructions.</p>
        <${LayerText} path=${`lab/workflow/step.${name}.add.md`} kind="step" name=${name} rows=${6} placeholder="e.g. Keep every run at this step under 2 GPU-hours." /></div>`}</div></div>`;
  };
  const StepAbout = ({ d, x, cps }) => {
    const init = { label: x.label || x.id, do: x.do || '', also: x.also || [], room: x.room || '', tags: x.tags || [] };
    const [f, setF] = useState(init);
    const [add, setAdd] = useState('');
    const set = (k, v) => setF(o => ({ ...o, [k]: v }));
    const fields = Object.fromEntries(Object.entries(f).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(init[k])));
    const dirty = Object.keys(fields).length > 0;
    useDirty(dirty);
    const procs = Object.entries(d.procedures || {}).filter(([, q]) => !q.engineering);
    return html`<div class="cmp-form">
      <div class="grid2"><${NL.Field} label="Its name"><${NL.Input} value=${f.label} onInput=${v => set('label', v)} /></${NL.Field}>
        <${NL.Field} label="Room"><${NL.Select} value=${f.room} onChange=${v => set('room', v)} options=${[{ value: '', label: 'no room' }, ...(d.rooms || []).map(r => ({ value: r.id, label: r.title || r.label }))]} /></${NL.Field}></div>
      <${NL.Field} label="Tags"><${NL.TagInput} ariaLabel="Step tags" value=${f.tags} onChange=${v => set('tags', v)} suggestions=${d.tags} /></${NL.Field}>
      ${x.shelf ? null : html`<${NL.Field} label="Who does the work" hint="the procedure that runs here and reports where the study goes next; a workflow can swap in a variant of it">
          <${NL.Picker} value=${f.do} onChange=${v => set('do', v)} label="the procedure" options=${[{ value: '', label: 'Nothing: a study waits here until it is moved', glyph: 'pause' },
            ...procs.map(([n2, q]) => ({ value: n2, label: q.title || n2, hint: q.does, glyph: NL.procGlyph ? NL.procGlyph(n2) : 'spark' }))]} /></${NL.Field}>
        <${NL.Field} label="Also offered here" hint="procedures you or an agent can run at this step besides its own; they never move the study"><div class="row wrap">
          ${f.also.map(q => html`<span class="chip">${procTitle(d, q)} <button type="button" class="link small" aria-label=${'take out ' + q} onClick=${() => set('also', f.also.filter(y => y !== q))}>×</button></span>`)}
          <${NL.Select} value=${add} onChange=${v => { if (v) set('also', [...f.also, v]); setAdd(''); }} options=${[{ value: '', label: 'Add one…' },
            ...procs.filter(([n2]) => n2 !== f.do && !f.also.includes(n2)).map(([n2, q]) => ({ value: n2, label: `${q.title || n2} (/${n2})` }))]} /></div></${NL.Field}>`}
      <div class="row end sticky-save">${dirty ? html`<${NL.Btn} small kind="ghost" onClick=${() => setF(init)}>Cancel</${NL.Btn}>` : null}
        <${NL.Btn} kind="primary" disabled=${!dirty} onClick=${() => edit({ op: 'step', id: x.id, fields }, SAVED)}>Save to draft</${NL.Btn}></div>
      ${cps.length ? html`<${NL.Section} title="Checkpoints on it">${cps.map(c => html`<button type="button" class="cp-line" onClick=${() => openCp(d, c.wf, c)}><${NL.Seal} state="waiting" size=${22} />
        <span class="grow"><b>${c.title || c.id}</b><small class="muted">${c.wf.title || c.wf.id} · ${c.before ? 'before it' : 'during it, at ' + (c.at || '…')}${c.means ? ' · ' + c.means : ''}</small></span></button>`)}</${NL.Section}>` : null}
    </div>`;
  };
  /** a new step: its name, who does the work, its room — and, if you like, its place on a workflow */
  const NewStepDialog = ({ w, after: after0, onClose }) => {
    const d = C.d;
    const [title, setTitle] = useState('');
    const [id, setId] = useState('');
    const [inWf, setInWf] = useState(w ? w.id : '');
    const wf = (d.workflows || []).find(x => x.id === inWf) || null;
    const [after, setAfter] = useState(after0 || '');
    const [doP, setDo] = useState('');
    const [room, setRoom] = useState('');
    const sid = id || slugify(title);
    const at = after || (wf ? (wf.path || []).slice(-1)[0] : '');
    const make = async () => {
      const r = await edit({ op: 'step', id: sid, new: true, after: at || undefined, in: inWf || undefined,
        fields: { label: title, ...(doP ? { do: doP } : {}), ...((room || stepOf(d, at).room) ? { room: room || stepOf(d, at).room } : {}) } }, `Added the step ${title} to your draft`);
      if (r.ok) { onClose(); if (!w) go('step', sid); }
    };
    return html`<div class="dialog dialog-wide"><h3>A new step</h3>
      <p class="muted small">A step is a place a study stands, with the procedure that does its work there. Steps are shared: put it on a workflow now, or later from any workflow's steps.</p>
      <div class="grid2"><${NL.Field} label="Its name"><${NL.Input} value=${title} onInput=${setTitle} autofocus placeholder="e.g. Replication" /></${NL.Field}>
        <${NL.Field} label="Its id" hint="lower-case, dashes"><${NL.Input} mono value=${sid} onInput=${setId} /></${NL.Field}>
        <${NL.Field} label="On the workflow"><${NL.Select} value=${inWf} onChange=${v => { setInWf(v); setAfter(''); }} options=${[{ value: '', label: 'none yet' }, ...(d.workflows || []).map(x => ({ value: x.id, label: x.title || x.id }))]} /></${NL.Field}>
        ${wf ? html`<${NL.Field} label="Comes after"><${NL.Select} value=${at} onChange=${setAfter} options=${(wf.path || []).map(x => ({ value: x, label: stateLabel(d, x) }))} /></${NL.Field}>` : html`<div></div>`}
        <${NL.Field} label="Who does the work"><${NL.Select} value=${doP} onChange=${setDo} options=${[{ value: '', label: 'nothing yet' }, ...Object.entries(d.procedures || {}).filter(([, q]) => !q.engineering).map(([n2, q]) => ({ value: n2, label: `${q.title || n2} (/${n2})` }))]} /></${NL.Field}>
        <${NL.Field} label="Room"><${NL.Select} value=${room} onChange=${setRoom} options=${[{ value: '', label: 'same room as the previous step' }, ...(d.rooms || []).map(r => ({ value: r.id, label: r.title || r.label }))]} /></${NL.Field}></div>
      <p class="muted small">No procedure fits yet? Make a variant of the closest one under <a class="link" href=${href('procedures')} onClick=${onClose}>Procedures</a>, then pick it here.</p>
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!title.trim() || !sid} onClick=${make}>Add the step</${NL.Btn}></div></div>`;
  };

  /* ── rooms ────────────────────────────────────────────────────────────────── */
  const RoomsList = ({d,k})=>html`<div class="cmp-page"><${ListHead} k=${k} /><div class="cmp-rows">${d.rooms.map(r=>html`<a class="cmp-row" href=${href('room',r.id)}><div class="grow"><b>${r.label||r.title||r.id}</b><p class="muted small">${(r.steps||[]).map(x=>stateLabel(d,x)).join(' · ')||'No steps'}</p></div></a>`)}</div></div>`;
  const RoomEditor=({d,name})=>{const r=d.rooms.find(x=>x.id===name);return r?html`<div class="cmp-page"><${ItemHead} k=${KIND_OF.room} name=${name} title=${r.label||r.title} sub="Group related research steps." actions=${html`<${CopyBtn} kind="room" like=${name} /><${NL.Btn} small onClick=${()=>NL.open(RoomRemoveDialog,{r},{kind:'dialog'})}>Remove</${NL.Btn}>`} /><${RoomAbout} key=${JSON.stringify(r)} d=${d} r=${r} /></div>`:html`<${Missing} k=${KIND_OF.room} name=${name} />`;};
  const RoomAbout = ({ d, r }) => {
    const init = { label: r.label || '', title: r.title || '' };
    const [f, setF] = useState(init);
    const [pick, setPick] = useState('');
    const set = (k, v) => setF(o => ({ ...o, [k]: v }));
    const dirty = JSON.stringify(f) !== JSON.stringify(init);
    useDirty(dirty);
    const here = r.steps || [];
    const elsewhere = (d.steps || []).filter(x => !here.includes(x.id));
    return html`<div class="cmp-form">
      <div class="grid2"><${NL.Field} label="Group title" hint="a descriptive group name"><${NL.Input} value=${f.title} onInput=${v => set('title', v)} /></${NL.Field}>
        <${NL.Field} label="Short name" hint="the column on the Studies board"><${NL.Input} value=${f.label} onInput=${v => set('label', v)} /></${NL.Field}></div>
      <div class="row end"><${NL.Btn} kind="primary" disabled=${!dirty} onClick=${() => edit({ op: 'room', id: r.id, fields: f }, SAVED)}>Save to draft</${NL.Btn}></div>
      <${NL.Section} title="The steps that stand here">${here.length ? here.map(x => html`<div class="cmp-li"><a class="grow" href=${href('step', x)}><b>${stateLabel(d, x)}</b> <span class="mono muted small">${x}</span></a>
          ${studiesAt(d, x) ? html`<span class="cmp-n" title="studies here now">${studiesAt(d, x)}</span>` : null}</div>`) : html`<div class="muted small">No step stands here yet.</div>`}
        <div class="row"><${NL.Select} value=${pick} onChange=${setPick} options=${[{ value: '', label: 'Move a step here…' }, ...elsewhere.map(x => ({ value: x.id, label: `${x.label || x.id} (now in ${((d.rooms || []).find(y => y.id === x.room) || {}).title || x.room || 'no room'})` }))]} />
          <${NL.Btn} small disabled=${!pick} onClick=${async () => { await edit({ op: 'step', id: pick, fields: { room: r.id } }); setPick(''); }}>Move</${NL.Btn}></div></${NL.Section}>
</div>`;
  };
  const RoomRemoveDialog = ({ r, onClose }) => {
    const d = C.d;
    const others = d.rooms.filter(x => x.id !== r.id);
    const [to, setTo] = useState((others[0] || {}).id || '');
    return html`<div class="dialog"><h3>Remove ${r.title || r.label}?</h3>
      ${(r.steps || []).length ? html`<${NL.Field} label=${`Its steps (${r.steps.map(x => stateLabel(d, x)).join(', ')}) move to`}><${NL.Select} value=${to} onChange=${setTo} options=${others.map(x => ({ value: x.id, label: x.title || x.label }))} /></${NL.Field}>` : html`<p class="muted">Nothing stands in it.</p>`}
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="danger" onClick=${async () => { const x = await edit({ op: 'delete', kind: 'room', name: r.id, move_to: to }); if (x.ok) { onClose(); go('rooms'); } }}>Remove it</${NL.Btn}></div></div>`;
  };

  /* ── roles ────────────────────────────────────────────────────────────────── */
  const RolesList = ({ d, k }) => html`<div class="cmp-page"><${ListHead} k=${k} />
    <p class="muted small">Which model each kind of subagent runs is under <a class="link" href="#/settings/agents">Settings → Agents & models</a>.</p>
    <div class="cmp-rows">${d.roles.map(r => html`<a class="cmp-row" href=${href('role', r.name)}><${NL.RoleDot} role=${r.name} />
      <div class="cmp-row-main"><div class="row"><b>${r.label}</b><span class="mono muted small">${r.name}</span>${touched(d, `agent-roles/${r.name}.`, `lab/workflow/roles/${r.name}.`) ? html`<i class="cmp-dot"></i>` : null}</div><div class="muted small clip">${r.description}</div></div>
      <div class="cmp-row-side">${(d.custom.roles || {})[r.name] ? html`<span class="pill pill-state">+ instructions</span>` : null}${r.origin === 'yours' ? html`<${Origin} o="yours" like=${r.like} />` : null}</div></a>`)}</div></div>`;
  const RoleEditor = ({ d, name, query }) => {
    const [tab, setTab] = useTab(query, 'about');
    const r = d.roles.find(x => x.name === name);
    if (!r) return html`<${Missing} k=${KIND_OF.role} name=${name} />`;
    return html`<div class="cmp-page">
      <${ItemHead} k=${KIND_OF.role} name=${name} title=${r.label} sub=${r.description} chips=${html`<${Origin} o=${r.origin} like=${r.like} />`}
        actions=${html`<${CopyBtn} kind="role" like=${name} /><${DeleteBtn} kind="role" name=${name} label=${'the role ' + r.label}
          ...${r.origin === 'yours' ? {} : { title: `Remove the built-in role ${r.label}?`, body: 'Procedures may rely on this built-in role. Remove it anyway?' }} />`} />
      <${NL.Tabs} tabs=${[{ id: 'about', label: 'About' }, { id: 'instructions', label: 'Your instructions' }, { id: 'files', label: 'Files' }]} value=${tab} onChange=${setTab} />
      <div class="tabpane">
        ${tab === 'about' ? html`<${RoleAbout} key=${r.label + r.description} r=${r} />` : null}
        ${tab === 'instructions' ? html`<div class="cmp-narrow"><p class="muted">Added to this role's instructions for every agent CLI (Claude, Codex, opencode), wherever it is used.</p>
          <${LayerText} path=${`lab/workflow/roles/${name}.add.md`} kind="role" name=${name} placeholder="e.g. Be especially strict about leakage between train and test." /></div>` : null}
        ${tab === 'files' ? html`<${FilesTab} files=${r.files} intro="The .yaml says which tools and model it gets; the .md is what it is told. Both are rendered for every agent CLI when you publish." />` : null}
      </div></div>`;
  };
  const RoleAbout = ({ r }) => {
    const [label, setLabel] = useState(r.label);
    const [desc, setDesc] = useState(r.description);
    const dirty = label !== r.label || desc !== r.description;
    useDirty(dirty);
    return html`<div class="cmp-form"><${NL.Field} label="Its name in the dashboard"><${NL.Input} value=${label} onInput=${setLabel} /></${NL.Field}>
      <${NL.Field} label="What it is for" hint="agents read this to decide when to call it"><${NL.Textarea} rows=${3} value=${desc} onInput=${setDesc} /></${NL.Field}>
      <div class="row end"><${NL.Btn} kind="primary" disabled=${!dirty} onClick=${() => edit({ op: 'role', name: r.name, fields: { label, description: desc } }, SAVED)}>Save to draft</${NL.Btn}></div></div>`;
  };

  /* ── rules ────────────────────────────────────────────────────────────────── */
  const RULE_GROUPS = [['hard', 'Hard rules', 'Every agent, every session. Skills cite them by number, so new ones go at the end.'],
    ['subagent', 'Subagent rules', 'Every subagent, and every agent that starts one.'], ['project', 'Project rules', 'Every session inside a study’s project repo.']];
  const RulesPage = ({ d }) => {
    const k = KIND_OF.rule;
    const checks = [...(d.built_in_checks || []), ...d.checks.filter(c => c.guard).map(c => c.name), ...d.checks.filter(c => !c.guard).map(c => c.file.split('/').pop().replace(/\.py$/, ''))];
    return html`<div class="cmp-page"><${ListHead} k=${k} />
      ${RULE_GROUPS.map(([g, title, sub]) => html`<section class="cmp-sec"><div class="cmp-sec-h"><h2>${title}</h2><span class="muted small grow">${sub}</span><span class="cmp-n">${(d.rules[g] || []).length}</span></div>
        ${g === 'hard' ? html`<p class="muted small cmp-rules-note">Hard rules can be edited but not removed: skills cite them by number.</p>` : null}
        ${(d.rules[g] || []).map((r, i) => html`<${RuleCard} key=${r.id + r.text} r=${r} n=${g === 'hard' ? i + 1 : null} group=${g} checks=${checks} />`)}
        <${RuleAdd} group=${g} checks=${checks} /></section>`)}
      <details class="cmp-sec more"><summary><${NL.Icon} name="lock" /> Read by the lab's safety code (fixed here)</summary>
        <p class="muted small">What an unattended run may never write, which settings only you change, the rigor floors no profile lowers, and the paper audits a check can name.</p>
        <pre class="plain">${Object.entries(d.locked || {}).map(([k2, v]) => `${k2}: ${JSON.stringify(v, null, 1)}`).join('\n\n')}</pre></details>
      <p class="muted small cmp-foot">Under the hood: <a class="link" href=${href('rule', '_file')}>workflow/rules.yaml</a>.</p></div>`;
  };
  const RuleCard = ({ r, n, group, checks }) => {
    const [ed, setEd] = useState(false);
    const [t, setT] = useState(r.text);
    const [cs, setCs] = useState(r.checks || []);
    useDirty(ed && (t !== r.text || JSON.stringify(cs) !== JSON.stringify(r.checks || [])));
    if (!ed) return html`<div class="cmp-rule">${n ? html`<span class="cmp-num">${n}</span>` : null}<div class="grow"><${NL.Markdown} text=${r.text} />
        <div class="row"><span class="mono muted small">${r.id}</span>${(r.checks || []).map(c => html`<span class="chip">checked by ${c}</span>`)}</div></div>
      <div class="cmp-rule-acts"><button type="button" class="link small" onClick=${() => setEd(true)}>Edit</button>
        ${group !== 'hard' ? html`<button type="button" class="link small danger" onClick=${async () => { if (await NL.confirm({ title: `Remove the rule “${r.id}”?`, ok: 'Remove', danger: true, body: 'Removed in your draft; every manual drops it when you publish.' })) edit({ op: 'rule', id: r.id, remove: true }); }}>Remove</button>` : null}</div></div>`;
    return html`<div class="cmp-rule editing">${n ? html`<span class="cmp-num">${n}</span>` : null}<div class="grow">
      <${NL.Textarea} rows=${4} value=${t} onInput=${setT} autofocus />
      <div class="row"><span class="muted small">Enforced by these checks:</span>${checks.map(c => html`<button type="button" class=${cls('chip', 'click', cs.includes(c) && 'on')} onClick=${() => setCs(x => x.includes(c) ? x.filter(y => y !== c) : [...x, c])}>${c}</button>`)}</div>
      <div class="row end"><${NL.Btn} small kind="ghost" onClick=${() => { setEd(false); setT(r.text); setCs(r.checks || []); }}>Cancel</${NL.Btn}>
        <${NL.Btn} small kind="primary" onClick=${async () => { const x = await edit({ op: 'rule', id: r.id, text: t, checks: cs }, SAVED); if (x.ok) setEd(false); }}>Save to draft</${NL.Btn}></div></div></div>`;
  };
  const RuleAdd = ({ group, checks }) => {
    const [open, setOpen] = useState(false);
    const [t, setT] = useState('');
    const [id, setId] = useState('');
    const [c, setC] = useState('');
    useDirty(open && !!t.trim());
    const rid = id || slugify(t.replace(/\*\*/g, '').split(/[.!?]/)[0]).slice(0, 30);
    if (!open) return html`<button type="button" class="cmp-add" onClick=${() => setOpen(true)}><${NL.Icon} name="plus" /> Add a rule</button>`;
    return html`<div class="cmp-rule editing"><div class="grow">
      <${NL.Textarea} rows=${3} value=${t} onInput=${setT} autofocus placeholder="**Short title.** What every agent must do, in a sentence or two." />
      <div class="grid2"><${NL.Field} label="Its id"><${NL.Input} mono value=${rid} onInput=${setId} /></${NL.Field}>
        <${NL.Field} label="Checked by (optional)"><${NL.Select} value=${c} onChange=${setC} options=${[{ value: '', label: 'nothing; agents keep it' }, ...checks.map(x => ({ value: x, label: x }))]} /></${NL.Field}></div>
      <div class="row end"><${NL.Btn} small kind="ghost" onClick=${() => setOpen(false)}>Cancel</${NL.Btn}>
        <${NL.Btn} small kind="primary" disabled=${!t.trim() || !rid} onClick=${async () => { const x = await edit({ op: 'copy', kind: 'rule', name: rid, text: t, list: group, check: c }, 'Rule added to the draft'); if (x.ok) { setOpen(false); setT(''); setId(''); } }}>Add to draft</${NL.Btn}></div></div></div>`;
  };

  /* ── checks, project types, domain profiles ───────────────────────────────── */
  const checkId = c => c.file.split('/').pop().replace(/\.py$/, '');
  const CheckRow = ({ c, label }) => html`<a class="cmp-row" href=${href('check', checkId(c))}><div class="cmp-row-main"><b>${label}</b>
    <div class="muted small clip">${c.doc || 'No description yet. Open it to add one.'}</div></div>${c.origin === 'yours' ? html`<${Origin} o="yours" />` : null}</a>`;
  const ChecksList = ({ d, k }) => {
    const guard = d.checks.filter(c => c.guard), audits = d.checks.filter(c => !c.guard);
    return html`<div class="cmp-page"><${ListHead} k=${k} />
      <section class="cmp-sec"><div class="cmp-sec-h"><h2>Safety checks</h2><span class="muted small grow">Procedures run these as they work, and rules name them.</span></div>
        <div class="cmp-rows">${guard.map(c => html`<${CheckRow} key=${c.file} c=${c} label=${c.name} />`)}</div></section>
      ${audits.length ? html`<section class="cmp-sec"><div class="cmp-sec-h"><h2>Paper audits</h2><span class="muted small grow">Checks a checkpoint can name. The default research workflow runs them before a paper is final.</span></div>
        <div class="cmp-rows">${audits.map(c => html`<${CheckRow} key=${c.file} c=${c} label=${checkId(c).replace(/_/g, ' ')} />`)}</div></section>` : null}
      <details class="cmp-sec more cmp-hood"><summary>Under the hood</summary>
        <p class="muted small">Safety checks run as <span class="mono">${'tools/guard.py <name> <study>'}</span>; a checkpoint can name any of them.</p>
        <div class="cmp-hood-list">${d.checks.map(c => html`<div class="cmp-hood-row"><a class="link mono small" href=${href('check', checkId(c))}>${c.file}</a>
          ${(c.usage || []).map(u => html`<code class="mono small">${u}</code>`)}</div>`)}</div></details></div>`;
  };
  const CheckEditor = ({ d, name }) => {
    const c = d.checks.find(x => checkId(x) === name);
    if (!c) return html`<${Missing} k=${KIND_OF.check} name=${name} />`;
    return html`<div class="cmp-page"><${ItemHead} k=${KIND_OF.check} name=${c.name} title=${c.name} sub=${c.doc} chips=${html`<${Origin} o=${c.origin} />`}
      actions=${html`${c.guard ? html`<${CopyBtn} kind="check" like=${c.name} />` : null}<${DeleteBtn} kind="check" name=${name.replace(/_/g, '-')} label=${'the check ' + c.name} />`} />
      <${FileEditor} path=${c.file} rows=${30} intro="Python, run by the lab's safety code. NAME is how rules and procedures call it; run(args, guard) returns the problems it finds." /></div>`;
  };
  const TypesList = ({ d, k }) => html`<div class="cmp-page"><${ListHead} k=${k} />
    ${d.types.length ? html`<div class="cmp-rows">${d.types.map(t => html`<a class="cmp-row" href=${href('type', t.name)}><div class="cmp-row-main"><div class="row"><b>${t.title || t.name}</b>${t.title && t.title !== t.name ? html`<span class="mono muted small">${t.name}</span>` : null}</div>
      <div class="muted small cmp-desc">${t.description || 'No description yet. Open its TYPE.md to add one.'}</div></div>${t.origin === 'yours' ? html`<${Origin} o="yours" />` : null}</a>`)}</div>`
      : html`<${NL.Empty} title="No project types yet">Add one (e.g. ml, theory) to define its research conventions.</${NL.Empty}>`}
    ${d.domains.length ? html`<section class="cmp-sec"><div class="cmp-sec-h"><h2>Domain profiles</h2><span class="muted small grow">Field conventions a study can adopt.</span></div>
      <div class="cmp-rows">${d.domains.filter(x => x.file).map(x => html`<a class="cmp-row" href=${href('domain', x.name)}><div class="cmp-row-main"><b>${x.name}</b><div class="mono muted small">${x.file}</div></div></a>`)}</div></section>` : null}</div>`;
  const TypeEditor = ({ d, name }) => {
    const t = d.types.find(x => x.name === name);
    if (!t) return html`<${Missing} k=${KIND_OF.type} name=${name} />`;
    return html`<div class="cmp-page"><${ItemHead} k=${KIND_OF.type} name=${name} title=${t.title || name} sub=${t.description} chips=${html`<${Origin} o=${t.origin} />`}
      actions=${html`<${CopyBtn} kind="type" like=${name} />${t.origin === 'yours' ? html`<${DeleteBtn} kind="type" name=${name} label=${'the project type ' + name} />` : null}`} />
      <${FilesTab} files=${t.files} intro="TYPE.md is what every agent in a project of this type reads first." /></div>`;
  };
  const DomainEditor = ({ d, name }) => {
    const x = d.domains.find(y => y.name === name);
    if (!x || !x.file) return html`<${Missing} k=${KIND_OF.type} name=${name} />`;
    return html`<div class="cmp-page"><${ItemHead} k=${KIND_OF.type} name=${name} title=${name} sub="A domain profile" /><${FileEditor} path=${x.file} /></div>`;
  };

  const Missing = ({ k, name }) => html`<div class="cmp-page"><${NL.Empty} title="Not in this lab">There is no ${k.one} called <span class="mono">${name}</span>${(C.d && C.d.draft && C.d.draft.active) ? ' in your draft' : ''}. <a class="link" href=${href(k.id)}>All ${k.label.toLowerCase()}</a></${NL.Empty}></div>`;

  /* ── suggestions and history ──────────────────────────────────────────────── */
  const Suggestions = ({ d }) => html`<div class="cmp-page"><header class="cmp-head"><div class="grow"><a class="kicker" href=${href()}>Workflow</a><h1>Agents’ suggestions</h1>
      </div></header>
    ${(d.proposals || []).length ? html`<div class="cmp-rows">${d.proposals.map(p => html`<button type="button" class="cmp-row" onClick=${() => NL.open(NL.ProposalSheet, { id: p.id, onClose: reload })}>
      <div class="cmp-row-main"><b>Instructions for ${p.kind === 'step' ? 'the step ' + stateLabel(d, p.name) : p.kind === 'role' ? 'the role ' + p.name : '/' + p.name}</b>
        <div class="muted small clip">${p.why || ''}</div></div><div class="cmp-row-side"><span class="muted small">${p.study ? 'for ' + p.study : 'lab-wide'} · ${NL.ago(p.ts)}</span></div></button>`)}</div>`
      : html`<${NL.Empty} title="Nothing to review">When an agent suggests a change, it waits here.</${NL.Empty}>`}</div>`;
  const History = ({ d }) => {
    const latest = (d.history || []).find(h => !h.undone);
    return html`<div class="cmp-page"><header class="cmp-head"><div class="grow"><a class="kicker" href=${href()}>Workflow</a><h1>Change log</h1>
      </div></header>
      ${(d.history || []).length ? html`<div class="cmp-rows">${d.history.map(h => html`<div class=${cls('cmp-row', h.undone && 'undone')}>
        <div class="cmp-row-main"><div class="row"><b>${h.note || NL.plural(h.n, 'change')}</b>${h.undone ? html`<span class="pill">undone</span>` : null}</div>
          <ul class="cmp-log-files">${(h.files || []).map(f => { const say = describePath(d, f); return html`<li>${say ? html`<span>${say}</span> <span class="mono muted small">${f}</span>` : html`<span class="mono small">${f}</span>`}</li>`; })}
            ${h.n > (h.files || []).length ? html`<li class="muted small">and ${NL.plural(h.n - h.files.length, 'more file')}</li>` : null}</ul></div>
        <div class="cmp-row-side"><span class="mono muted small">${(h.ts || '').replace('T', ' ').slice(0, 16)}</span>
          ${latest && h.id === latest.id ? html`<${NL.Btn} small onClick=${async () => { if (await NL.confirm({ title: 'Undo this publish?', ok: 'Undo it', body: 'The files go back to how they were before it. Runs started since keep what they started with.' })) { const r = await edit({ op: 'undo', id: h.id }); if (r.ok) NL.refresh(); } }}><${NL.Icon} name="undo" /> Undo</${NL.Btn}>` : null}</div></div>`)}</div>`
        : html`<${NL.Empty} title="Nothing published yet">What you publish from a draft is listed here.</${NL.Empty}>`}</div>`;
  };

  /* ── "New …": start from a copy of the closest thing ──────────────────────── */
  const optionsFor = (d, kind) => kind === 'procedure' ? Object.entries(d.procedures).filter(([, p]) => !p.engineering).map(([n, p]) => ({ id: n, title: p.title, sub: p.does, tag: '/' + n }))
    : kind === 'room' ? d.rooms.map(r => ({ id: r.id, title: r.title || r.label, sub: (r.steps || []).map(x => stateLabel(d, x)).join(' · ') }))
    : kind === 'role' ? d.roles.map(r => ({ id: r.name, title: r.label, sub: r.description }))
    : kind === 'check' ? d.checks.filter(c => c.guard).map(c => ({ id: c.name, title: c.name, sub: c.doc }))
    : kind === 'type' ? d.types.map(t => ({ id: t.name, title: t.title || t.name, sub: t.description, tag: t.name })) : [];
  const openNew = async (kind, props) => { if (!C.d || !C.d.procedures) await reload(); NL.open(NewDialog, { kind, ...(props || {}) }, { kind: 'dialog', key: 'cmp-new' }); };
  const NewDialog = ({ kind, like: like0, title: title0, onClose }) => {
    const d = C.d;
    const opts = optionsFor(d, kind);
    const [like, setLike] = useState(like0 || (opts[0] || {}).id);
    const [q, setQ] = useState('');
    const [title, setTitle] = useState(title0 || '');
    const [name, setName] = useState('');
    const [plain, setPlain] = useState(false);
    const nm = name || slugify(title);
    const k = KIND_OF[kind];
    const blank = kind === 'type' && !opts.length;    // nothing to copy yet: compose.py starts it blank
    const list = opts.filter(o => !q || `${o.id} ${o.title} ${o.sub}`.toLowerCase().includes(q.toLowerCase()));
    const make = async () => {
      const r = await edit({ op: 'copy', kind, like: blank ? '' : like, name: nm, title: title || undefined, plain: kind === 'room' || plain }, blank ? `Added ${nm}. Now fill in its TYPE.md.` : `Made ${nm} from ${like}. Now make it its own.`);
      if (r.ok) { onClose(); go(kind, kind === 'check' ? nm.replace(/-/g, '_') : nm); }
    };
    return html`<div class="dialog dialog-wide cmp-new"><h3>A new ${k.one}</h3>
      ${blank ? null : html`<p class="muted">${kind === 'procedure' ? 'Start from the closest one the lab has. The new one is a variant of it: it keeps everything the original has, and you change what makes yours different.' : 'Start from the closest one the lab has. The copy keeps everything; you change what makes yours different.'}</p>`}
      ${blank ? html`<p class="note">The lab has no project type to start from yet, so this one starts blank: a TYPE.md for you to fill in.</p>` : html`<${NL.Field} label="Start from">${opts.length > 6 ? html`<input class="input" placeholder="Find…" value=${q} onInput=${e => setQ(e.target.value)} />` : null}
        <div class="cmp-pick">${list.map(o => html`<button type="button" class=${cls('cmp-pick-row', like === o.id && 'on')} onClick=${() => setLike(o.id)}>
          <span class="grow"><b>${o.title}</b>${o.tag ? html` <span class="mono muted small">${o.tag}</span>` : null}<small class="clip">${o.sub || ''}</small></span>${like === o.id ? html`<${NL.Icon} name="check" />` : null}</button>`)}</div></${NL.Field}>`}
      <div class="grid2"><${NL.Field} label=${`Name your ${k.one}`}><${NL.Input} value=${title} onInput=${setTitle} autofocus placeholder=${kind === 'procedure' ? 'e.g. Quick literature scan' : kind === 'room' ? 'e.g. The Data Room' : kind === 'type' ? 'e.g. fieldwork' : 'e.g. Data wrangler'} onEnter=${() => nm && (like || blank) && make()} /></${NL.Field}>
        <${NL.Field} label="Its id" hint=${kind === 'procedure' ? 'agents run it as /' + (nm || 'its-id') : 'lower-case, dashes'}><${NL.Input} mono value=${nm} onInput=${setName} /></${NL.Field}></div>
      <div class="dialog-actions"><${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" disabled=${!nm || !(like || blank)} onClick=${make}>Make it</${NL.Btn}></div></div>`;
  };

})();
