/* The lab demo: a short, scripted story played in the dashboard's own lab frame (static/lab-view.html).
   That frame never reads lab files; it draws the snapshots it is sent and posts back what was clicked
   (the dashboard's app.js is its other host). Each beat changes a small made-up model; the snapshot for
   beat n is the base model with beats 1…n applied, so stepping and jumping are exact. Nothing is real. */
(function () {
'use strict';
const $ = (sel, root = document) => root.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const CAST = { mode: 'backend', one: 'newt', claude: 'newt', codex: 'human', opencode: 'robot' };   // the dashboard's default cast
const AGENT = { claude: 'Claude Code', codex: 'Codex', opencode: 'opencode' };
const STEP = { seed: 'Ideas', 'lit-review': 'Literature review', scoping: 'Scoping', proposal: 'Proposal', setup: 'Setup', active: 'Experiments',
  analysis: 'Analysis', writing: 'Writing', 'internal-review': 'Internal review', final: 'Done' };
const QUESTION = { q: 'Lead the Results section with the scaling law or with the ablation?', options: ['The scaling law', 'The ablation'] };
const DWELL = 7500, WAIT = 13000;   // ms per beat; longer where the visitor is invited to answer

/* ── the made-up lab ───────────────────────────────────────────────── */
const T0 = Date.now(), ago = min => new Date(T0 - min * 60e3).toISOString().slice(0, 19);
const base = () => ({
  items: [
    { id: 'routing', title: 'Token routing', state: 'seed' },
    { id: 'distil', title: 'Distillation curricula', state: 'lit-review' },
    { id: 'curriculum', title: 'Curriculum distillation', state: 'proposal' },
    { id: 'moe', title: 'Sparse MoE routing', state: 'active', approved: ['approve-proposal', 'approve-full-runs'] },
    { id: 'scaling', title: 'Scaling laws note', state: 'writing', approved: ['approve-proposal', 'approve-full-runs'] },
    { id: 'quant', title: 'Quantization study', state: 'final', approved: ['approve-proposal', 'approve-full-runs', 'finalize-paper'] },
  ],
  runs: [
    { id: 'distil', skill: 'lit-review', subject: 'distil', backend: 'claude', doing: ['read', 'Read', 'papers/hinton-2015.pdf'] },
    { id: 'scaling', skill: 'write-paper', subject: 'scaling', backend: 'codex', doing: ['edit', 'Edit', 'paper/main.tex § Method'] },
  ],
  attention: [], artifacts: [],
});
const item = (m, id) => m.items.find(i => i.id === id);
const run = (m, id) => m.runs.find(r => r.id === id);

/* ── the story ─────────────────────────────────────────────────────── */
const BEATS = [
  { title: 'Your lab', text: 'Each room is a step of a workflow: ideas, reading, experiments, analysis, writing. Every study is a card on the shelf of the room it is in.',
    hint: 'Six studies share one set of rooms. ARLO waits at your desk in the middle.' },
  { title: 'Agents at work', text: 'Claude Code starts the next experiment for Sparse MoE routing. It briefs a subagent, who goes to the bench to run it.',
    hint: 'Each character is an agent at work. A subagent is smaller and walks back to its parent when it is done.',
    apply: m => {
      m.runs.push({ id: 'moe', skill: 'experiment', subject: 'moe', backend: 'claude', doing: ['spawn', 'Task', 'experiment runner for exp-015'],
        subs: [{ id: 'runner', role: 'experiment-runner', label: 'Runs exp-015 at pilot scale', doing: ['run', 'Bash', 'uv run scripts/run.py --stage PILOT --seed 2'] }] });
    } },
  { title: 'A study moves on', text: 'Triage says Token routing is worth a look. A character carries its card from Ideas to the Study, and opencode starts the literature review.',
    hint: 'A study moves when a task reports its outcome, never on a timer.',
    apply: m => {
      item(m, 'routing').state = 'lit-review';
      m.runs.push({ id: 'routing', skill: 'lit-review', subject: 'routing', backend: 'opencode', doing: ['search', 'WebSearch', 'token routing in mixture-of-experts'] });
    } },
  { title: 'An agent asks you', text: 'Codex is writing the Scaling laws note and needs a decision. It pauses, and the question waits in your Inbox.',
    hint: 'Try it: choose an answer in the Inbox.', wait: 'question',
    apply: m => {
      Object.assign(run(m, 'scaling'), { status: 'waiting_input', doing: null, question: QUESTION.q });
      m.attention.push({ id: 'q:r-scaling', sev: 'block', kind: 'question', title: QUESTION.q, body: 'Scaling laws note', run_id: 'r-scaling', actions: [{ id: 'answer', label: 'answer' }] });
    } },
  { title: 'You answer', text: answer => `You chose “${answer}”. The answer goes into Codex's own conversation, and it goes back to the Results section.`,
    hint: 'Questions, permission requests and checkpoints all arrive in the one Inbox.',
    apply: m => {
      Object.assign(run(m, 'scaling'), { status: 'running', question: null, doing: ['edit', 'Edit', 'paper/main.tex § Results'] });
      m.attention = m.attention.filter(a => a.kind !== 'question');
    } },
  { title: 'A checkpoint waits for you', text: 'The proposal for Curriculum distillation is written. Before any experiment starts, the study waits at the lantern for your approval.',
    hint: 'Checkpoints are yours: an agent never approves its own work. Try it: approve in the Inbox.', wait: 'checkpoint',
    apply: m => {
      item(m, 'curriculum').waiting = ['approve-proposal'];
      m.attention.push({ id: 'cp:curriculum:approve-proposal', sev: 'block', kind: 'checkpoint', title: 'Approve the proposal', body: 'Curriculum distillation',
        idea: 'curriculum', detail: { checkpoint: 'approve-proposal', study: 'curriculum' }, actions: [{ id: 'checkpoint', label: 'review' }] });
    } },
  { title: 'Approved', text: 'You approved. The study is carried to the Lab, and Claude Code sets up its project repository.',
    hint: 'The approval is recorded with the study: who decided, and when.',
    apply: m => {
      Object.assign(item(m, 'curriculum'), { waiting: [], approved: ['approve-proposal'], state: 'setup', has_project: true });
      m.attention = m.attention.filter(a => a.kind !== 'checkpoint');
      m.runs.push({ id: 'curriculum', skill: 'spawn-project', subject: 'curriculum', backend: 'claude', doing: ['bash', 'Bash', 'tools/spawn_project.py curriculum-distillation'] });
    } },
  { title: 'Results come back', text: 'The pilot finishes and publishes its results, every number linked to the run that produced it. Sparse MoE routing moves to the Bench for analysis.',
    hint: 'Outputs, from tables to interactive HTML reports, are kept in each study’s Library.',
    apply: m => {
      m.runs = m.runs.filter(r => r.id !== 'moe');
      item(m, 'moe').state = 'analysis';
      m.runs.push({ id: 'moe-analysis', skill: 'analyze', subject: 'moe', backend: 'codex', doing: ['bash', 'Bash', 'uv run scripts/compare.py'] });
      m.artifacts.push({ id: 'a-pilot', title: 'Pilot results: sparse MoE routing', kind: 'md', study: 'moe', run_id: 'r-moe', skill: 'experiment', created: ago(1), question: null, choices: 0, seen: false, answered: false });
    } },
];

/* ── the model as the dashboard's snapshot ─────────────────────────── */
const call = ([kind, tool, summary]) => ({ kind, tool, summary, since: ago(0) });
function snapshot(m) {
  const runs = m.runs.map(r => ({ run_id: 'r-' + r.id, skill: r.skill, subject: r.subject, target: r.subject, backend: r.backend, status: r.status || 'running',
    created: ago(12), session_id: 'S-' + r.id, transport: 'live', in_tool: r.doing ? call(r.doing) : null, last_action: { summary: r.doing ? r.doing[2] : '' },
    pending_question: r.question ? { question: r.question } : null, subagents: [] }));
  const agents = m.runs.flatMap(r => {
    const id = 'run:r-' + r.id, title = (item(m, r.subject) || {}).title || '';
    const shared = { run_id: 'r-' + r.id, backend: r.backend, subject: r.subject, target: r.subject, skill: r.skill, interactive: false };
    return [{ ...shared, id, parent: null, depth: 0, sub: null, worker_id: 'r-' + r.id, role: 'orchestrator', label: r.skill, display_label: `${title} · /${r.skill}`,
      status: r.status === 'waiting_input' ? 'asking' : 'working', doing: r.doing ? call(r.doing) : null, last: r.doing ? r.doing[2] : '' },
    ...(r.subs || []).map(s => ({ ...shared, id: `${id}/${s.id}`, parent: id, depth: 1, sub: s.id, worker_id: null, role: s.role, label: s.label,
      display_label: s.label, status: 'working', doing: call(s.doing), last: s.doing[2] }))];
  });
  return { workflow: window.__WORKFLOW_DEFAULT__, world_view: 'unified', now: ago(0), lab_info: { name: 'Demo lab' },
    items: m.items.map(i => ({ workflow: 'research', inflight: [], events: [], directives: [], slipped: [], waiting: [], ...i,
      checkpoints: Object.fromEntries((i.approved || []).map(c => [c, { ts: ago(600), decision: 'approved', by: 'pi', via: 'dashboard' }])) })),
    runs, agents, attention: m.attention, artifacts: m.artifacts, workers: [], directives: [], events: [], campaigns: [], holds: {} };
}

/* ── the page side ─────────────────────────────────────────────────── */
const stage = $('.lab-stage'), poster = $('.poster', stage), note = $('.lab-stage-note', stage), peek = $('.peek', stage);
const story = $('.story'), narration = $('.narration'), playButton = $('.play'), bar = $('.progress i'), beatList = $('.beats');
const inboxBody = $('.inbox-body'), inboxCount = $('.inbox-count');
let at = 0, answer = QUESTION.options[0], playing = !reduced.matches, elapsed = 0, last = 0, tick = 0;
let frame = null, live = false, onScreen = false, model = base();

const lamp = () => document.documentElement.dataset.lamp === 'night' ? 'night' : 'day';
const showPoster = () => { if (stage.dataset.state === 'poster') poster.src = poster.dataset[lamp()]; };
addEventListener('arlo-lamp', () => { showPoster(); send(); });

beatList.innerHTML = BEATS.map((b, i) => `<li><button type="button" data-beat="${i}">${esc(b.title)}</button></li>`).join('');
beatList.addEventListener('click', e => { const b = e.target.closest('[data-beat]'); if (b) go(+b.dataset.beat, { user: true }); });

const roomy = () => stage.clientWidth >= 560;   // room names crowd a small stage
let wasRoomy = roomy();
addEventListener('resize', () => { if (roomy() !== wasRoomy) { wasRoomy = roomy(); send(true); } });
function send(still) {
  if (!frame || !frame.contentWindow) return;
  frame.contentWindow.postMessage({ labView: 1, active: onScreen && !document.hidden, state: snapshot(model), theme: lamp(), cast: CAST,
    motion: !reduced.matches && !still, labels: roomy() }, '*');
}

function renderInbox() {
  const beat = BEATS[at], open = model.attention;
  inboxCount.textContent = open.length;
  if (beat.wait === 'question') inboxBody.innerHTML = `<div class="inbox-item"><div class="who">Codex · Scaling laws note · paused until you answer</div>
    <p class="q">${esc(QUESTION.q)}</p><div class="row">${QUESTION.options.map(o => `<button type="button" class="btn btn-sm" data-answer="${esc(o)}">${esc(o)}</button>`).join('')}</div></div>`;
  else if (beat.wait === 'checkpoint') inboxBody.innerHTML = `<div class="inbox-item"><div class="who">Checkpoint · Curriculum distillation</div>
    <p class="q">Approve the proposal</p><ul><li>proposal.md</li><li>lit-review.md</li><li>decisions.md</li></ul>
    <div class="row"><button type="button" class="btn btn-sm btn-primary" data-approve>Approve</button><button type="button" class="btn btn-sm btn-ghost" data-later>Not yet</button></div></div>`;
  else if (at === 4) inboxBody.innerHTML = `<div class="inbox-item"><div class="who">Codex · Scaling laws note</div><p class="q">${esc(QUESTION.q)}</p><p class="done">Answered: ${esc(answer)}</p></div>`;
  else if (at === 6) inboxBody.innerHTML = `<div class="inbox-item"><div class="who">Checkpoint · Curriculum distillation</div><p class="q">Approve the proposal</p><p class="done">Approved by you, just now</p></div>`;
  else if (at === 7) inboxBody.innerHTML = `<div class="inbox-item result"><div class="who">New output · Sparse MoE routing · /experiment</div><p class="q">Pilot results: sparse MoE routing</p>
    <p class="muted small" style="margin:0">Beats the dense baseline on 2 of 3 seeds. Every number links to its run.</p></div>`;
  else inboxBody.innerHTML = '<p class="muted small">Nothing needs you right now.</p>';
}
inboxBody.addEventListener('click', e => {
  const t = e.target.closest('button'); if (!t) return;
  if (t.dataset.answer) { answer = t.dataset.answer; go(4, { user: true }); }
  else if ('approve' in t.dataset) go(6, { user: true });
  else if ('later' in t.dataset) { setPlaying(false); t.closest('.inbox-item').insertAdjacentHTML('beforeend', '<p class="muted small" style="margin:8px 0 0">The study keeps waiting. Nothing moves past a checkpoint without you.</p>'); t.parentElement.remove(); }
});

function render(user) {
  const beat = BEATS[at];
  narration.setAttribute('aria-live', user ? 'polite' : 'off');
  $('.beat-count').textContent = `${at + 1} / ${BEATS.length}`;
  $('.beat-title').textContent = beat.title;
  $('.beat-text').textContent = typeof beat.text === 'function' ? beat.text(answer) : beat.text;
  $('.beat-hint').textContent = beat.hint;
  beatList.querySelectorAll('button').forEach((b, i) => { if (i === at) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current'); });
  renderInbox();
}

/** Show beat n. Going forward plays the change; going back or looping redraws it still (nothing walks backwards). */
function go(n, { user = false } = {}) {
  const forward = n === at + 1;
  if (n >= BEATS.length) return restart();
  at = Math.max(0, n); elapsed = 0; hidePeek();
  model = base(); for (let i = 1; i <= at; i++) BEATS[i].apply && BEATS[i].apply(model);
  render(user); send(!forward);
}
function restart() {
  stage.classList.add('is-resetting');
  setTimeout(() => { go(0); setTimeout(() => stage.classList.remove('is-resetting'), 350); }, reduced.matches ? 0 : 450);
}

function setPlaying(on) {
  playing = on; last = 0;
  playButton.textContent = on ? '❚❚' : '▶';
  playButton.setAttribute('aria-label', on ? 'Pause' : 'Play');
  if (on) loop();
}
function loop() {
  cancelAnimationFrame(tick);
  tick = requestAnimationFrame(now => {
    if (!playing) return;
    if (onScreen && !document.hidden) elapsed += last ? now - last : 0;
    const dwell = BEATS[at].wait ? WAIT : DWELL;
    last = now; bar.style.width = Math.min(100, elapsed / dwell * 100) + '%';
    if (elapsed >= dwell) go(at + 1);
    loop();
  });
}
playButton.addEventListener('click', () => setPlaying(!playing));
$('.prev').addEventListener('click', () => go(at - 1, { user: true }));
$('.next').addEventListener('click', () => go(at + 1, { user: true }));
story.addEventListener('keydown', e => {
  if (e.target.closest('input, textarea')) return;
  if (e.key === 'ArrowRight') go(at + 1, { user: true }); else if (e.key === 'ArrowLeft') go(at - 1, { user: true });
});

/* ── peeks: what a clicked character or card is ────────────────────── */
function showPeek(html, anchor) { $('.peek-body', peek).innerHTML = html; peek.hidden = false; place(anchor); }
/** beside the clicked character (the frame's anchor is in stage pixels), else in the stage's corner */
function place(anchor) {
  const w = stage.clientWidth, h = stage.clientHeight, pw = peek.offsetWidth, ph = peek.offsetHeight;
  const x = !anchor ? 12 : anchor.x + 16 + pw > w - 12 ? anchor.x - pw - 16 : anchor.x + 16, y = anchor ? anchor.y - ph / 2 : 12;
  peek.style.left = Math.max(12, Math.min(w - pw - 12, x)) + 'px';
  peek.style.top = Math.max(12, Math.min(h - ph - 12, y)) + 'px';
}
function hidePeek() { peek.hidden = true; }
const closePeek = () => { hidePeek(); frame && frame.contentWindow.postMessage({ labView: 1, command: 'dismiss-agent' }, '*'); };
$('.x', peek).addEventListener('click', closePeek);
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !peek.hidden) closePeek(); });
const facts = rows => `<div class="facts">${rows.filter(r => r[1]).map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div>`;
function agentPeek(target, anchor) {
  if (target.kind === 'assistant') return showPeek(`<h4>The desk</h4><b>ARLO</b><p>The workspace assistant. Ask it about the lab, a study or an agent’s work; its answers are saved in the Library.</p>`, anchor);
  const a = snapshot(model).agents.find(x => x.id === target.agent_id); if (!a) return;
  const study = item(model, a.subject) || {};
  showPeek(`<h4>${a.parent ? 'Subagent' : 'Agent'}</h4><b>${esc(a.parent ? a.label : AGENT[a.backend])}</b>
    <p>${a.status === 'asking' ? 'Waiting for your answer in the Inbox.' : esc(a.doing ? `${a.doing.tool}: ${a.doing.summary}` : 'Working')}</p>
    ${facts([['Agent', a.parent ? AGENT[a.backend] : null], ['Role', a.parent ? a.role : null], ['Task', '/' + a.skill], ['Study', study.title]])}`, anchor);
}
function studyPeek(id) {
  const it = item(model, id); if (!it) return;
  showPeek(`<h4>Study</h4><b>${esc(it.title)}</b><p>${(it.waiting || []).length ? 'Waiting for you to approve the proposal.' : 'A card on the shelf of the room for its step.'}</p>
    ${facts([['Step', STEP[it.state] || it.state], ['Agents here', String(model.runs.filter(r => r.subject === id).length)], ['Approved', String((it.approved || []).length) + ' checkpoint(s)']])}`);
}

addEventListener('message', e => {
  if (!frame || e.source !== frame.contentWindow || !e.data || e.data.labView !== 1) return;
  const d = e.data;
  if (d.error) return fallback('The 3D lab could not start in this browser, so this is a picture of it. The story still plays alongside.');
  if (d.kind === 'ready' && !live) { live = true; stage.dataset.state = 'live'; note.hidden = true; }
  else if (d.kind === 'inspect-agent') { setPlaying(false); agentPeek(d.target, d.anchor); }
  else if (d.kind === 'agent-anchor' && !peek.hidden && d.anchor) place(d.anchor);
  else if (d.kind === 'dismiss-agent') hidePeek();
  else if (d.kind === 'study') { setPlaying(false); studyPeek(d.id); }
  else if (d.kind === 'checkpoint') { setPlaying(false); studyPeek(d.id); }
  else if (d.kind === 'inbox') { $('.inbox').scrollIntoView({ block: 'nearest', behavior: reduced.matches ? 'auto' : 'smooth' }); }
});

/* ── loading the frame: only near the viewport, only with WebGL ────── */
function fallback(text, action) {
  live = false; stage.dataset.state = 'poster'; showPoster();
  if (frame) { frame.remove(); frame = null; }
  note.hidden = false; note.textContent = text;
  if (action) { const b = Object.assign(document.createElement('button'), { type: 'button', className: 'link small', textContent: action }); b.onclick = () => { note.hidden = true; load(true); }; note.append(' ', b); }
}
const webgl = () => { try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; } };
const script = src => new Promise((ok, fail) => document.head.append(Object.assign(document.createElement('script'), { src, onload: ok, onerror: fail })));
let loading = false;
async function load(force) {
  if (frame || loading) return;
  if (!webgl()) return fallback('Your browser cannot show the 3D lab here, so this is a picture of it. The story still plays alongside.');
  if (!force && navigator.connection && navigator.connection.saveData) return fallback('Data saver is on, so this is a picture of the lab.', 'Load the live lab (about 1 MB)');
  loading = true;   // two observers may ask at once
  try { if (!window.__WORKFLOW_DEFAULT__) await script('static/ui/workflow-default.js'); }
  catch { return fallback('The lab could not load, so this is a picture of it.'); }
  finally { loading = false; }
  frame = Object.assign(document.createElement('iframe'), { title: 'The ARLOtope lab, playing a scripted demo', src: `static/lab-view.html?lamp=${lamp()}`, loading: 'eager' });
  frame.addEventListener('load', () => {
    // the frame lifts its controls clear of the dashboard's phone tab bar; this page has none (same origin)
    try { frame.contentDocument.head.insertAdjacentHTML('beforeend', '<style>@media (max-width: 700px) { .view-controls { bottom: 10px; } }</style>'); } catch {}
    send(true);
  });
  stage.prepend(frame);
}

const activate = () => send(true);   // the frame ignores snapshots while it is inactive, so waking it resends the current one
const area = stage.parentElement;
if ('IntersectionObserver' in window) {
  new IntersectionObserver(([e]) => { if (e.isIntersecting) load(); }, { rootMargin: '300px 0px' }).observe(area);
  new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; activate(); }, { threshold: .35 }).observe(area);
}
else { onScreen = true; load(); }
document.addEventListener('visibilitychange', activate);
reduced.addEventListener('change', () => { if (reduced.matches) setPlaying(false); send(true); });

go(0);
setPlaying(playing);
})();
