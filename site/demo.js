/* The lab tour: a short, scripted story played in the dashboard's own lab frame (static/lab-view.html),
   advanced by scrolling. The frame never reads lab files; it draws the snapshots it is sent and posts back
   what was clicked (the dashboard's app.js is its other host). The captions are the page's .beat items;
   each step's change to a small made-up model is below, and the snapshot for step n is the base model with
   steps 1…n applied, so scrolling either way is exact. Nothing in it is real. */
(function () {
'use strict';
const $ = (sel, root = document) => root.querySelector(sel), $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const CAST = { mode: 'backend', one: 'newt', claude: 'newt', codex: 'human', opencode: 'robot' };   // the dashboard's default cast
const AGENT = { claude: 'Claude Code', codex: 'Codex', opencode: 'opencode' };
const STEP = { seed: 'Ideas', 'lit-review': 'Literature review', scoping: 'Scoping', proposal: 'Proposal', setup: 'Setup', active: 'Experiments',
  analysis: 'Analysis', writing: 'Writing', 'internal-review': 'Internal review', final: 'Done' };
const QUESTION = 'Lead the Results section with the scaling law or with the ablation?';

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

/* ── what each step of the tour changes (steps 0 and 1 show the lab as it is) ── */
const CHANGES = [null, null,
  m => m.runs.push({ id: 'moe', skill: 'experiment', subject: 'moe', backend: 'claude', doing: ['spawn', 'Task', 'experiment runner for exp-015'],
    subs: [{ id: 'runner', role: 'experiment-runner', label: 'Runs exp-015 at pilot scale', doing: ['run', 'Bash', 'uv run scripts/run.py --stage PILOT --seed 2'] }] }),
  m => {
    item(m, 'routing').state = 'lit-review';
    m.runs.push({ id: 'routing', skill: 'lit-review', subject: 'routing', backend: 'opencode', doing: ['search', 'WebSearch', 'token routing in mixture-of-experts'] });
  },
  m => {
    Object.assign(run(m, 'scaling'), { status: 'waiting_input', doing: null, question: QUESTION });
    m.attention.push({ id: 'q:r-scaling', sev: 'block', kind: 'question', title: QUESTION, body: 'Scaling laws note', run_id: 'r-scaling', actions: [{ id: 'answer', label: 'answer' }] });
  },
  m => {
    Object.assign(run(m, 'scaling'), { status: 'running', question: null, doing: ['edit', 'Edit', 'paper/main.tex § Results'] });
    m.attention = m.attention.filter(a => a.kind !== 'question');
  },
  m => {
    item(m, 'curriculum').waiting = ['approve-proposal'];
    m.attention.push({ id: 'cp:curriculum:approve-proposal', sev: 'block', kind: 'checkpoint', title: 'Approve the proposal', body: 'Curriculum distillation',
      idea: 'curriculum', detail: { checkpoint: 'approve-proposal', study: 'curriculum' }, actions: [{ id: 'checkpoint', label: 'review' }] });
  },
  m => {
    Object.assign(item(m, 'curriculum'), { waiting: [], approved: ['approve-proposal'], state: 'setup', has_project: true });
    m.attention = m.attention.filter(a => a.kind !== 'checkpoint');
    m.runs.push({ id: 'curriculum', skill: 'spawn-project', subject: 'curriculum', backend: 'claude', doing: ['bash', 'Bash', 'tools/spawn_project.py curriculum-distillation'] });
  },
  m => {
    m.runs = m.runs.filter(r => r.id !== 'moe');
    item(m, 'moe').state = 'analysis';
    m.runs.push({ id: 'moe-analysis', skill: 'analyze', subject: 'moe', backend: 'codex', doing: ['bash', 'Bash', 'uv run scripts/compare.py'] });
    m.artifacts.push({ id: 'a-pilot', title: 'Pilot results: sparse MoE routing', kind: 'md', study: 'moe', run_id: 'r-moe', skill: 'experiment', created: ago(1), question: null, choices: 0, seen: false, answered: false });
  },
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
const tour = $('.tour'), world = $('.world'), poster = $('.poster', world), note = $('.stage-note', world), peek = $('.peek', world);
const steps = $$('.beat');
let at = 0, model = base(), frame = null, live = false, onScreen = true, loading = false;

const lamp = () => document.documentElement.dataset.lamp === 'night' ? 'night' : 'day';
const showPoster = () => { if (world.dataset.state === 'poster') poster.src = poster.dataset[lamp()]; };
addEventListener('arlo-lamp', () => { showPoster(); send(true); });
const roomy = () => world.clientWidth >= 600;   // room names crowd a small lab
let wasRoomy = roomy();
addEventListener('resize', () => { if (roomy() !== wasRoomy) { wasRoomy = roomy(); send(true); } });

function send(still) {
  if (!frame || !frame.contentWindow) return;
  frame.contentWindow.postMessage({ labView: 1, active: onScreen && !document.hidden, state: snapshot(model), theme: lamp(), cast: CAST,
    motion: !reduced.matches && !still, labels: roomy() }, '*');
}

/** Show step n. Moving forward one step plays the change; any other jump redraws it still (nothing walks backwards). */
function go(n) {
  if (n === at) return;
  const forward = n === at + 1;
  at = n; hidePeek();
  model = base(); for (let i = 1; i <= at; i++) CHANGES[i] && CHANGES[i](model);
  steps.forEach(s => s.classList.toggle('is-on', +s.dataset.beat === at));
  send(!forward);
}

/* the step whose heading has reached the reading line (mid-screen; lower on phones, under the lab) is the one shown */
const pick = () => {
  const line = innerHeight * (matchMedia('(max-width: 860px)').matches ? .75 : .55);
  let n = 0; for (const s of steps) if (s.firstElementChild.getBoundingClientRect().top <= line) n = +s.dataset.beat;
  go(n);
};
addEventListener('scroll', pick, { passive: true });   // nine rectangles: cheap enough to read on every scroll
addEventListener('resize', pick);
steps[0].classList.add('is-on');

/* the two steps that ask for you: answering or approving moves the tour on */
const scrollToStep = n => steps[n].scrollIntoView({ block: 'center', behavior: reduced.matches ? 'auto' : 'smooth' });
tour.addEventListener('click', e => {
  const b = e.target.closest('[data-answer], [data-approve]'); if (!b) return;
  const box = b.closest('.inbox');
  if (b.dataset.answer) $('.answer').textContent = b.dataset.answer.toLowerCase();
  box.classList.add('is-done');
  box.insertAdjacentHTML('beforeend', `<p class="done">${b.dataset.answer ? 'Answered: ' + esc(b.dataset.answer) : 'Approved by you, just now'}</p>`);
  scrollToStep(b.dataset.answer ? 5 : 7);
});

/* ── peeks: what a clicked character or card is ────────────────────── */
function showPeek(html, anchor) { $('.peek-body', peek).innerHTML = html; peek.hidden = false; place(anchor); }
/** beside the clicked character (the frame's anchor is in its own pixels, the same as the world box), else in its corner;
 *  the box runs past the page edges, so only its part on screen counts */
function place(anchor) {
  const r = world.getBoundingClientRect(), w = Math.min(r.width, innerWidth - r.left), h = Math.min(r.height, innerHeight - r.top), pw = peek.offsetWidth, ph = peek.offsetHeight;   // the part on screen
  const x = !anchor ? 16 : anchor.x + 16 + pw > w - 12 ? anchor.x - pw - 16 : anchor.x + 16, y = anchor ? anchor.y - ph / 2 : 16;
  peek.style.left = Math.max(12, Math.min(w - pw - 12, x)) + 'px';
  peek.style.top = Math.max(12, Math.min(h - ph - 12, y)) + 'px';
}
function hidePeek() { peek.hidden = true; }
const closePeek = () => { hidePeek(); frame && frame.contentWindow.postMessage({ labView: 1, command: 'dismiss-agent' }, '*'); };
$('.x', peek).addEventListener('click', closePeek);
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !peek.hidden) closePeek(); });
const facts = rows => `<div class="facts">${rows.filter(r => r[1]).map(([k, v]) => `<div><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div>`;
function agentPeek(target, anchor) {
  if (target.kind === 'assistant') return showPeek(`<h4>Your desk</h4><b>ARLO</b><p>The workspace assistant. Ask it about the lab, a study or an agent’s work; its answers are saved in the Library.</p>`, anchor);
  const a = snapshot(model).agents.find(x => x.id === target.agent_id); if (!a) return;
  const study = item(model, a.subject) || {};
  showPeek(`<h4>${a.parent ? 'Subagent' : 'Agent'}</h4><b>${esc(a.parent ? a.label : AGENT[a.backend])}</b>
    <p>${a.status === 'asking' ? 'Waiting for your answer in the Inbox.' : esc(a.doing ? `${a.doing.tool}: ${a.doing.summary}` : 'Working')}</p>
    ${facts([['Agent', a.parent ? AGENT[a.backend] : null], ['Role', a.parent ? a.role : null], ['Task', '/' + a.skill], ['Study', study.title]])}`, anchor);
}
function studyPeek(id) {
  const it = item(model, id); if (!it) return;
  showPeek(`<h4>Study</h4><b>${esc(it.title)}</b><p>${(it.waiting || []).length ? 'Waiting for you to approve the proposal.' : 'A card on the shelf of the room for its step.'}</p>
    ${facts([['Step', STEP[it.state] || it.state], ['Agents on it', String(model.runs.filter(r => r.subject === id).length)]])}`);
}

addEventListener('message', e => {
  if (!frame || e.source !== frame.contentWindow || !e.data || e.data.labView !== 1) return;
  const d = e.data;
  if (d.error) return fallback('The 3D lab could not start in this browser, so this is a picture of it.');
  if (d.kind === 'ready' && !live) { live = true; world.dataset.state = 'live'; note.hidden = true; }
  else if (d.kind === 'inspect-agent') agentPeek(d.target, d.anchor);
  else if (d.kind === 'agent-anchor' && !peek.hidden && d.anchor) place(d.anchor);
  else if (d.kind === 'dismiss-agent') hidePeek();
  else if (d.kind === 'study' || d.kind === 'checkpoint') studyPeek(d.id);
});

/* ── loading the frame: right away (it is the first screen), only with WebGL ── */
function fallback(text, action) {
  live = false; world.dataset.state = 'poster'; showPoster();
  if (frame) { frame.remove(); frame = null; }
  note.hidden = false; note.textContent = text;
  if (action) { const b = Object.assign(document.createElement('button'), { type: 'button', className: 'link small', textContent: action }); b.onclick = () => { note.hidden = true; load(true); }; note.append(' ', b); }
}
const webgl = () => { try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; } };
const script = src => new Promise((ok, fail) => document.head.append(Object.assign(document.createElement('script'), { src, onload: ok, onerror: fail })));
async function load(force) {
  if (frame || loading) return;
  if (!webgl()) return fallback('Your browser cannot show the 3D lab here, so this is a picture of it.');
  if (!force && navigator.connection && navigator.connection.saveData) return fallback('Data saver is on, so this is a picture of the lab.', 'Load the live lab (about 1 MB)');
  loading = true;
  try { if (!window.__WORKFLOW_DEFAULT__) await script('static/ui/workflow-default.js'); }
  catch { return fallback('The lab could not load, so this is a picture of it.'); }
  finally { loading = false; }
  world.dataset.state = 'loading';
  frame = Object.assign(document.createElement('iframe'), { title: 'The ARLOtope lab, playing a scripted tour', src: `static/lab-view.html?lamp=${lamp()}` });
  frame.addEventListener('load', () => {
    // the page shows the lab open, without the dashboard's camera bar (same origin: one style rule)
    try { frame.contentDocument.head.insertAdjacentHTML('beforeend', '<style>.view-controls { display: none; }</style>'); } catch {}
    send(true);
  });
  world.prepend(frame);
}

const activate = () => send(true);   // the frame ignores snapshots while it is inactive, so waking it resends the current one
if ('IntersectionObserver' in window) new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; activate(); }).observe(tour);
document.addEventListener('visibilitychange', activate);
reduced.addEventListener('change', () => send(true));
if (document.readyState === 'complete') load(); else addEventListener('load', () => load(), { once: true });
})();
