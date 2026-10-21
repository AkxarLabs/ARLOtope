/* Newts' Lab — demo mode (?demo, only when the server was started with --demo): a synthetic, living
   lab so the world and the panels can be seen with no real session. Pure client-side; nothing is
   written (every API write is refused in demo mode). Every few seconds the lab moves on: runs start and
   finish, a study advances (a newt carries its card), a question comes and goes, a new lab gets built. */
(function () {
'use strict';
const NL = window.NL;
const DEMO_CLIS = Object.fromEntries(['claude','codex','opencode'].map(id => [id, { found:true, logged_in:true, note:'Simulated agent' }]));

const BASE_ITEMS = [
  { id: 'spark-1', title: 'Sparse attention', state: 'seed' },
  { id: 'spark-2', title: 'Token routing', state: 'seed' },
  { id: 'lit-1', title: 'Distillation curricula', state: 'lit-review' },
  { id: 'scope-1', title: 'Adaptive optimizers', state: 'scoping' },
  { id: 'prop-1', title: 'Curriculum distillation', state: 'proposal', waiting: ['approve-proposal'], next: 'waiting for your approval' },
  { id: 'prop-2', title: 'Retrieval heads', state: 'proposal', approved: ['approve-proposal'], next: 'spawn-project' },
  { id: 'moe', title: 'Sparse MoE routing', state: 'active', has_project: true, project_type: 'ml', loop_active: true, next: 'experiment',
    approved: ['approve-proposal', 'approve-full-runs'], best: { val_loss: 1.31, run_id: 'exp-012' } },
  { id: 'rl', title: 'RL fine-tuning', state: 'active', has_project: true, project_type: 'ml', approved: ['approve-proposal'], waiting: ['approve-full-runs'], next: 'waiting for your approval' },
  { id: 'ana-1', title: 'Scaling probes', state: 'analysis', has_project: true, project_type: 'simulation', approved: ['approve-proposal', 'approve-full-runs'], next: 'analyze' },
  { id: 'paper-1', title: 'Scaling laws note', state: 'writing', has_project: true, project_type: 'theory', has_paper: true, approved: ['approve-proposal', 'approve-full-runs'], next: 'write-paper' },
  { id: 'rev-1', title: 'Long-context eval', state: 'internal-review', has_paper: true, approved: ['approve-proposal', 'approve-full-runs'], waiting: ['finalize-paper'], next: 'waiting for your approval' },
  { id: 'final-1', title: 'Quantization study', state: 'final', has_paper: true, approved: ['approve-proposal', 'approve-full-runs', 'finalize-paper'] },
  { id: 'gsm', title: 'Leaderboard: GSM-hard', state: 'active', workflow: 'target', has_project: true, project_type: 'ml', next: 'improve' },
  { id: 'park-1', title: 'Old idea (parked)', state: 'parked' },
];
const ACT = {
  experiment: ['Bash: uv run scripts/run.py --stage PILOT --seed 2', 'Edit: src/router.py', 'Read: runs/exp-014/metrics.json'],
  improve: ['Edit: src/policy.py', 'Bash: uv run scripts/run.py --stage SMOKE'], analyze: ['Bash: uv run scripts/compare.py', 'Write: analysis.md § H1'],
  'lit-review': ['WebSearch: curriculum distillation 2025', 'Read: papers/hinton-2015.pdf'], scope: ['Write: decisions.md § D3 eval set', 'Task: scoping advocate for B'],
  'write-paper': ['Edit: paper/main.tex § Results', 'Bash: latexmk -pdf'], ideate: ['Write: seeds/cheap-routing.md', 'Task: ideation critic ×2'],
  'review-paper': ['Task: fresh-context reviewer ×3', 'Write: meta-review.md'], 'spawn-project': ['Bash: tools/spawn_project.py retrieval-heads', 'Write: control.yaml'],
  ask: ['Read: lab/REGISTRY.md', 'Read: studies/moe/IDEA.md'],
};
const SUBS = { experiment: ['experiment-runner', 'overseer'], improve: ['experiment-runner'], 'lit-review': ['fresh-context-reviewer'], scope: ['scoping-advocate', 'scoping-advocate'],
  'review-paper': ['fresh-context-reviewer', 'fresh-context-reviewer'], ideate: ['ideation-critic'] };


// the demo happens now: every time is minutes before this page loaded (local time, like the lab's own stamps)
const T0 = Date.now();
const iso = ms => { const d = new Date(ms), p = n => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };
const ago = min => iso(T0 - min * 60e3);

/* artifacts the demo agents "published": the page, the rail and the world show them; nothing is written */
const SVG_LOSS = (() => {
  const line = (k, c) => { let d = ''; for (let i = 0; i <= 40; i++) { const x = 40 + i * 13, y = 40 + 200 * Math.exp(-i / (9 + k * 2)) + 30 + Math.sin(i * 0.9 + k) * 4; d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); } return `<path d="${d}" fill="none" stroke="${c}" stroke-width="2.5"/>`; };
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="320" viewBox="0 0 600 320"><rect width="600" height="320" fill="#fbf8f2"/><g stroke="#d9d1c3">${[80, 140, 200, 260].map(y => `<line x1="40" x2="580" y1="${y}" y2="${y}"/>`).join('')}</g>${line(0, '#2e8f84')}${line(1, '#6f9be6')}${line(2, '#d9884a')}<text x="300" y="304" font-family="sans-serif" font-size="13" text-anchor="middle" fill="#555">steps (k)</text><text x="300" y="24" font-family="sans-serif" font-size="15" text-anchor="middle" fill="#222">Validation loss, seeds 1–3</text></svg>`;
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
})();
const ARTS = [
  { id: 'a-20260619-081200-0001', title: 'Pilot results: sparse MoE routing', kind: 'md', study: 'moe', run_id: 'r-moe', skill: 'experiment', created: ago(52),
    note: 'The pilot beats the dense baseline on 2 of 3 seeds; one seed diverged at step 6k. Details below.',
    text: '# Pilot results\n\n| run | seed | val loss | Δ vs dense |\n|---|---|---|---|\n| exp-012 | 1 | **1.31** | −0.09 |\n| exp-013 | 2 | 1.36 | −0.04 |\n| exp-014 | 3 | 1.52 | +0.12 |\n\nThe router load stays balanced ($\\mathrm{CV} < 0.15$) except seed 3, where one expert takes\n$41\\%$ of tokens after step 6k.\n\n## What I would do next\n\n1. Re-run seed 3 with the auxiliary balance loss at $\\lambda = 10^{-2}$.\n2. If it holds, scale to PILOT-L (4× tokens).\n\n> Every number above links to `runs/exp-01x/metrics.json` in the project.' },
  { id: 'a-20260619-082500-0002', title: 'Which eval set should we freeze?', kind: 'choice', study: 'scope-1', run_id: 'r-scope', skill: 'scope', created: ago(38),
    question: 'Freeze the held-out benchmark (slower, standard) or the synthetic suite (fast, ours)?', choices: ['Held-out benchmark', 'Synthetic suite', 'Both: synthetic for pilots'] },
  { id: 'a-20260619-083000-0003', title: 'Loss curves, seeds 1–3', kind: 'image', study: 'moe', run_id: 'r-moe', skill: 'experiment', created: ago(31), src: SVG_LOSS },
  { id: 'a-20260619-084000-0004', title: 'Ablation explorer', kind: 'html', study: 'ana-1', run_id: 'r-ana', skill: 'analyze', created: ago(22),
    note: 'Drag the slider to see how the probe accuracy moves with model scale.',
    html: '<body style="font-family:sans-serif;margin:24px;background:#fbf8f2"><h3>Probe accuracy vs scale</h3><input id=s type=range min=0 max=4 value=2 style="width:300px"><p id=o></p><script>const v=[0.61,0.68,0.74,0.79,0.81],n=["70M","160M","410M","1B","2.8B"];const f=()=>o.textContent=n[s.value]+": "+(v[s.value]*100).toFixed(1)+"%";s.oninput=f;f();</script></body>' },
  { id: 'a-20260619-085000-0005', title: 'Routing ablation table', kind: 'table', study: 'moe', run_id: 'r-moe', skill: 'experiment', created: ago(14),
    rows: [['variant', 'top-k', 'val loss', 'tokens/s'], ['dense', '-', '1.40', '41k'], ['switch', '1', '1.36', '58k'], ['ours', '2', '1.31', '52k'], ['ours + balance', '2', '1.30', '51k']] },
  { id: 'a-20260619-090000-0006', title: 'Plan: the next three experiments', kind: 'md', study: 'rl', run_id: 'r-rl', skill: 'improve', created: ago(6),
    question: 'Good to run these three at PILOT scale?', choices: ['Yes, go', 'Only the first two', 'Not yet, let’s talk'],
    text: '# Plan\n\n- **E1**: KL penalty sweep $\\beta \\in \\{0.01, 0.05, 0.1\\}$, 3 seeds each.\n- **E2**: reward-model ensemble of 3 vs 1.\n- **E3**: curriculum on prompt difficulty.\n\nBudget: ~2.5 GPU-hours in total, within the full-run budget you approved.' },
];
const demoSeen = new Set(), demoReplied = {};
NL.demoArtifact = async id => { const a = ARTS.find(x => x.id === id); if (!a) return { error: 'no such artifact' };
  demoSeen.add(id);
  return { ok: true, artifact: { ...a, seen: true, reply: demoReplied[id] || null }, text: a.text, html: a.html, src: a.src, table: a.rows ? { rows: a.rows, more: 0 } : null }; };
NL.demoReply = (id, choice, text) => { demoReplied[id] = { ts: new Date().toISOString(), by: 'PI', choice, text: text || null, delivered: 'the demo (nothing is sent)' }; NL.toast('Demo mode: the reply stays on this page'); return { ok: true, reply: demoReplied[id] }; };
NL.demoFleet = { ok: true, labs: [
  { kind: 'local', key: 'demo::here', name: 'Demo lab', machine: 'This computer', current: true, state: 'here', summary: {} },
  { kind: 'remote', key: 'demo::cluster', name: 'Protein folding', machine: 'gpu-cluster', state: 'connected', summary: { needs: 2, running: 5 } },
  { kind: 'local', key: 'demo::side', name: 'Side project', machine: 'This computer', state: 'here', summary: { needs: 0, running: 1 } },
  { kind: 'remote', key: 'demo::lab-pc', name: 'Wet-lab analysis', machine: 'lab-pc', state: 'idle', summary: null }] };
NL.demoRunFile = f => ({ ok: true, kind: f.kind, path: f.path, text: f.kind === 'md'
  ? '# Experiment log\n\n## exp-014: PILOT, seed 3\n- config: `configs/experiments/exp-014.yaml`\n- val loss **1.52** (diverged at step 6k: one expert took 41% of tokens)\n- next: rerun with the balance loss at 1e-2\n\n## exp-013: PILOT, seed 2\n- val loss 1.36\n'
  : 'def route(x, experts, k=2):\n    scores = x @ experts.T\n    top = scores.topk(k)\n    return top.indices, top.values.softmax(-1)\n' });
const PROPOSAL = it => `# Proposal: ${it.title}\n\n## Hypothesis\nA curriculum ordered by teacher confidence distils a 7B teacher into a 1B student with **≥ 2 points** less accuracy loss than random order.\n\n## Frozen evaluation\nThe held-out split of the benchmark, fixed before any run; reported over 3 seeds.\n\n## Staged plan\n| stage | what | promote when |\n|---|---|---|\n| SMOKE | 100 steps, 1 seed | it runs end to end |\n| PILOT | 2k steps, 3 seeds | ≥ 1 point better than random order |\n| FULL | 20k steps, 3 seeds | — |\n\n## Budget\nPILOT ≈ 6 GPU-hours · FULL ≈ 40 GPU-hours.\n\n## Kill criteria\nStop if PILOT shows no gain over random order on 2 of 3 seeds.\n\n## Full-scale runs\nUp to **3 FULL runs**, ≤ 15 GPU-hours each, asked for at "Approve full runs".`;
const DOCS = { 'IDEA.md': it => `# ${it.title}\n\nState: **${it.state}**.\n\nThe idea in one paragraph, its scores from triage, and the state log the lab keeps.`,
  'lit-review.md': it => `# Literature review: ${it.title}\n\n**Verdict: incremental.** Three close papers; none orders the curriculum by teacher confidence.`,
  'proposal.md': PROPOSAL, 'PLAN.md': it => `# Plan: ${it.title}\n\n| exp | stage | status |\n|---|---|---|\n| exp-012 | PILOT | done |\n| exp-014 | PILOT | rerun |`,
  'EXPERIMENT_LOG.md': () => NL.demoRunFile({ kind: 'md' }).text };
NL.demoRead = (path, b) => {
  const it = (NL.getState()?.items || BASE_ITEMS).find(i => i.id === (b.idea || b.slug)) || BASE_ITEMS[4];
  if (path === '/api/read' && b.what === 'checkpoint') return { ok: true, sections: b.checkpoint === 'finalize-paper'
    ? [{ title: 'Meta-review', path: 'paper/reviews/meta-review.md', text: '# Meta-review\n\n**Verdict: accept.** All three reviewers agree the claims are supported; two minor fixes were made.' }]
    : [{ title: 'proposal.md', path: `studies/${it.id}/proposal.md`, text: PROPOSAL(it) }], note: 'Demo: a made-up proposal.' };
  if (path === '/api/read') return { ok: true, sections: [{ title: 'metrics.json', path: 'runs/exp-014/metrics.json', text: '{"val_loss": 1.52, "step": 6000}' }] };
  const f = DOCS[(b.rel || '').split('/').pop()];
  return f ? { ok: true, format: 'markdown', text: f(it), path: `(demo)/${b.rel}` } : { error: 'not in the demo' };
};
/* the Workflow lens in the demo: the lab's definition as /api/compose gives it, built from the shipped default */
const demoCompose = () => {
  const W = window.__WORKFLOW_DEFAULT__ || {};
  const stepsOf = n => (W.steps || []).filter(st => [st.do, ...(st.also || [])].includes(n)).map(st => st.id);
  const procedures = Object.fromEntries(Object.entries(W.procedures || {}).map(([n, x]) => [n, { ...x, description: x.does || '', steps: stepsOf(n),
    variants: n === 'lit-review' ? ['lit-review-quick'] : [], files: [`.claude/skills/${n}/SKILL.md`], origin: 'built in', own: [] }]));
  if (procedures['lit-review']) procedures['lit-review-quick'] = { ...procedures['lit-review'], title: 'Quick literature scan', like: 'lit-review', steps: [], variants: [],
    does: 'A shorter pass for workshop papers: the ten closest papers, read in full.', files: ['.claude/skills/lit-review-quick/SKILL.md'], origin: 'yours', own: ['like', 'title'] };
  const studies_at = {}; (NL.getState()?.items || BASE_ITEMS).forEach(i => { studies_at[i.state] = (studies_at[i.state] || 0) + 1; });
  const audit = (n, doc) => ({ file: `checks/audit_${n}.py`, name: n, doc, guard: false, origin: 'built in', usage: [] });
  return { ok: true, version: 1, steps: W.steps || [], rooms: W.rooms || [], workflows: W.workflows || [], procedures,
    roles: (W.roles || []).map(r => ({ name: r, label: (W.role_labels || {})[r] || r, description: 'A specialist subagent procedures call on.', files: [`agent-roles/${r}.yaml`, `agent-roles/${r}.md`], origin: 'built in' })),
    rules: { hard: [{ id: 'no-fabrication', text: '**Never fabricate results.** Every number in a document links to a run that produced it.', checks: ['claims'] },
      { id: 'append-only', text: '**Logs are append-only.** Experiment logs and the registry are never rewritten.', checks: [] }],
      subagent: [{ id: 'fresh-context', text: 'A reviewer subagent starts with a fresh context and sees only the artifacts.', checks: [] }], project: [] },
    checks: [{ file: 'checks/full_runs_without_approval.py', name: 'full-runs-without-approval', doc: 'Finds full-scale runs started before the full-runs checkpoint was approved.', guard: true, origin: 'built in', usage: [] },
      { file: 'checks/append_only.py', name: 'append-only', doc: 'Logs and the registry only ever grow.', guard: true, origin: 'built in', usage: [] },
      audit('claims', 'Every claim in the paper links to a registered run.'), audit('multiseed', 'Headline results have three or more seeds.'),
      audit('ablation_coverage', 'Each component the paper credits has an ablation.'), audit('eval_discipline', 'The test set was touched only as frozen.'), audit('prereg', 'The analysis follows the frozen plan.')],
    types: [{ name: 'ml', title: 'Machine learning', description: 'Training runs, seeds, a frozen eval.', files: ['templates/project-types/ml/TYPE.md'], origin: 'built in' }],
    domains: [], custom: { procedures: { 'lit-review': { add: true } }, roles: {} }, draft: { active: false, changes: [], problems: [] },
    proposals: [{ id: 'p1', kind: 'add', name: 'experiment', why: 'Log GPU memory with every run. Two OOMs this week went unexplained.', ts: ago(300), study: null }],
    history: [{ id: 'h1', ts: new Date(Date.now() - 864e5).toISOString(), note: 'A quicker literature pass for workshop papers', n: 2, files: ['.claude/skills/lit-review-quick/SKILL.md', 'workflow/workflows/research.yaml'] }],
    workflow_designs: [{ id: '20261010-0915', ts: ago(25), request: 'a quick replication check before writing, approved by me', problems: [],
      files: ['workflow/steps.yaml', 'workflow/workflows/research.yaml', '.claude/skills/replicate/SKILL.md'],
      changes: ['adds the step Replication to Research paper, after Analysis', 'adds the checkpoint Approve the replication (before Writing, only you approve) to Research paper', 'adds the procedure /replicate (a variant of /experiment)'],
      notes: 'Adds a **Replication** step before Writing: /replicate (a variant of /experiment) reruns the headline experiment from a clean checkout, and **Approve the replication** stops the study for you before it is written up. Nothing else changes.' }],
    studies_at, designs: [], locked: { never_write: ['lab/approvals.jsonl', 'lab/config.yaml'] } };
};
NL.demoGet = path => {
  const q = Object.fromEntries(new URLSearchParams(path.split('?')[1]));
  if (path.startsWith('/api/run/files?')) return { ok: true, files: NL.demoRunFiles({ run_id: q.run_id }) };
  if (path.startsWith('/api/run/file?')) return NL.demoRunFile({ path: q.path, kind: /\.md$/i.test(q.path || '') ? 'md' : 'text' });
  if (path.startsWith('/api/run/log?')) return { ok: true, text: 'Demo session; no CLI process was started.' };
  if (path.startsWith('/api/figs?')) return { ok: true, figures: [] };
  if (path.startsWith('/api/checkpoint?')) {
    const q = Object.fromEntries(new URLSearchParams(path.split('?')[1]));
    const it = (NL.getState()?.items || BASE_ITEMS).find(i => i.id === q.study) || {};
    const wf = (window.__WORKFLOW_DEFAULT__.workflows || []).find(w => w.id === (it.workflow || 'research')) || {};
    const cp = (wf.checkpoints || []).find(c => c.id === q.id) || { id: q.id, title: q.id };
    const approved = (it.approved || []).includes(q.id);
    const ev = { 'approve-proposal': [['proposal.md', 'studies/' + q.study + '/proposal.md', 1], ['lit-review.md', 'studies/' + q.study + '/lit-review.md', 1], ['decisions.md', 'studies/' + q.study + '/decisions.md', 0]],
      'approve-full-runs': [['PLAN.md', 'projects/' + q.study + '/PLAN.md', 1], ['EXPERIMENT_LOG.md', 'projects/' + q.study + '/EXPERIMENT_LOG.md', 1], ['control.yaml', 'projects/' + q.study + '/control.yaml', 1]],
      'finalize-paper': [['main.pdf', 'studies/' + q.study + '/paper/main.pdf', 1], ['reviews', 'studies/' + q.study + '/paper/reviews', 1], ['claims.yaml', 'studies/' + q.study + '/paper/claims.yaml', 1]] }[q.id] || [];
    const codes = { claims: 0, multiseed: 0, ablations: 0, eval: 2, prereg: 0 };
    const asking = { 'approve-full-runs': ['improve', 'Trial runs clear the promotion bar on all three seeds (+2.1 ± 0.4 over dense at 125M). I’d run the four full-scale rows at 1.3B next, about 38 GPU-hours.'],
      'approve-proposal': ['propose', 'The proposal is written: a confidence-ordered curriculum, a frozen held-out eval, 3 seeds, and a kill rule at the trial runs.'],
      'finalize-paper': ['review-paper', 'Internal review accepts the paper. Two minor fixes were made; every number links to a run.'] }[q.id];
    return { ok: true, study: q.study, checkpoint: { ...cp, workflow: wf.id }, state: it.state, waits_at: it.state, here: (it.waiting || []).includes(q.id), waiting: (it.waiting || []).includes(q.id), approved,
      record: approved ? { ts: ago(600), decision: 'approved', by: 'pi', via: 'dashboard', note: q.id === 'approve-full-runs' ? 'Stay under 40 GPU-hours; top-2 routing first.' : '' } : null,
      history: [], evidence: ev.map(([name, path, ex]) => ({ name, path, exists: !!ex, dir: name === 'reviews' })),
      checks: (cp.checks || []).map(n => ({ name: n, code: codes[n], out: '' })), checked_at: (cp.checks || []).length ? ago(12) : null,
      asking: asking ? { run_id: 'r-' + q.study, skill: asking[0], summary: asking[1], finished: ago(40), session: true } : null, title: it.title };
  }
  if (path === '/api/compose' || path.startsWith('/api/compose?')) return demoCompose();
  if (path.startsWith('/api/compose/file')) { const f = decodeURIComponent((path.split('path=')[1] || '').split('&')[0]);
    const t = /lit-review-quick\/SKILL\.md$/.test(f) ? '---\nname: lit-review-quick\nnewts:\n  like: lit-review\n  title: Quick literature scan\n---\n\n# Quick literature scan\n\n1. Search the three main venues and arXiv for the last two years.\n2. Read the ten closest papers in full.\n3. Write the verdict: novel, incremental or done-before.\n'
      : /\.add\.md$/.test(f) ? (f.includes('lit-review') ? 'Always include workshop papers from the last year.' : '') : `# ${f}\n\n(demo: the real lab shows this file here)\n`;
    return { ok: true, path: f, text: t, published: t }; }
  if (path.startsWith('/api/panel/data')) {
    const q = Object.fromEntries(new URLSearchParams(path.split('?')[1]));
    const data = (NL.demoPanelData || {})[q.id];
    return { ok: true, ts: ago(0.5), data: typeof data === 'function' ? data() : data || {} };
  }
  if (path.startsWith('/api/panels')) return { ok: true, panels: NL.demoPanels(), designs: [] };
  if (path.startsWith('/api/campaign/preflight')) return { ok: true, ready: true, checks: [
    { id: 'launch', ok: true, label: 'The dashboard may start agents', detail: 'on' },
    { id: 'backend', ok: true, label: 'Claude is signed in', detail: 'demo' },
    { id: 'perm', ok: true, label: 'Agents won’t stop to ask for tool permissions', detail: 'permission mode: auto' },
    { id: 'root', ok: true, label: 'The projects folder is writable', detail: 'demo/projects' },
    { id: 'sched', ok: true, label: 'The scheduler is running', detail: 'last tick just now' },
    { id: 'latex', ok: false, warn_only: true, label: 'LaTeX is installed', detail: 'optional: papers compile to PDF only with it' }] };
  if (path.startsWith('/api/lab/config')) return { ok: true, config: { name: 'Demo lab', projects_root: '../projects', max_concurrent_runs: 4, oversight: 'standard',
    loop_mode: 'execute', keep_awake: 'auto', claude_model: 'claude-sonnet-5-5', claude_effort: 'medium', codex_model: 'gpt-6-luna', codex_effort: 'low',
    opencode_model: '', opencode_variant: '', tier_strong: 'opus', tier_standard: 'inherit', tier_fast: 'haiku', reviewer_model: 'strong', runner_model: 'standard',
    overseer_model: 'standard', critic_model: 'standard', reviewer_effort: '', runner_effort: '', overseer_effort: '', critic_effort: '' }, setup: { completed: true } };
  if (!path.startsWith('/api/library')) return null;
  const groups = (NL.getState()?.items || BASE_ITEMS).filter(i => i.state !== 'parked').map(i => {
    const order = ['seed', 'lit-review', 'scoping', 'proposal', 'setup', 'active', 'analysis', 'writing', 'internal-review', 'final'], at = order.indexOf(i.state);
    const study = ['IDEA.md', ...(at >= order.indexOf('scoping') ? ['lit-review.md'] : []), ...(at >= order.indexOf('proposal') ? ['proposal.md'] : [])].map(rel => ({ scope: 'study', slug: i.id, rel, title: rel }));
    const proj = i.has_project ? ['PLAN.md', 'EXPERIMENT_LOG.md'].map(rel => ({ scope: 'project', slug: i.id, rel, title: rel })) : [];
    return { kind: 'study', key: 'study:' + i.id, slug: i.id, title: i.title, state: i.state,
      sections: [{ title: 'Study', icon: '📋', docs: study }, ...(proj.length ? [{ title: 'Project repo', icon: '🛠', docs: proj }] : [])] };
  });
  return { ok: true, groups };
};
NL.demoRunFiles = r => r.run_id === 'r-moe' ? [{ path: 'C:/demo/projects/moe/EXPERIMENT_LOG.md', name: 'EXPERIMENT_LOG.md', exists: true, kind: 'md', size: 2048 },
  { path: 'C:/demo/projects/moe/src/router.py', name: 'router.py', exists: true, kind: 'text', size: 4096 }] : [];
const artifactsAt = T => ARTS.filter((a, i) => i < ARTS.length - 1 || T >= 3).map(a => ({ id: a.id, title: a.title, kind: a.kind, study: a.study, run_id: a.run_id, skill: a.skill,
  created: a.created, question: a.question || null, choices: (a.choices || []).length, seen: demoSeen.has(a.id), answered: !!demoReplied[a.id] }));

/* what a demo line is doing, in the tracer's vocabulary (the world walks agents to the furniture for it) */
const kindOf = line => { const t = String(line).split(':')[0];
  return /run\.py|sweep/.test(line) ? 'run' : t === 'Bash' ? 'bash' : ['Edit', 'Write'].includes(t) ? 'edit' : t === 'Read' ? 'read'
    : t === 'WebSearch' ? 'search' : t === 'Task' ? 'spawn' : 'tool'; };
const call = (line, T) => ({ kind: kindOf(line), tool: String(line).split(':')[0], summary: String(line).split(': ').slice(1).join(': ') || line, since: ago(T % 3) });
/* the snapshot's `agents`: every run at work and its subagents (the server's workers.agents, for the demo's runs) */
const demoAgents = runs => runs.filter(r => ['running', 'waiting_input', 'queued'].includes(r.status)).flatMap(r => {
  const main = 'run:' + r.run_id, base = { run_id: r.run_id, backend: r.backend, subject: r.subject, target: r.target, skill: r.skill, interactive: false };
  const status = r.status === 'queued' ? 'queued' : r.status === 'waiting_input' ? 'asking' : (r.heartbeat_age_s || 0) > 180 ? 'stalled' : 'working';
  return [{ ...base, id: main, parent: null, depth: 0, sub: null, worker_id: r.run_id, role: 'orchestrator', label: r.label || r.skill, status,
    doing: r.status === 'running' ? r.in_tool : null, last: (r.last_action || {}).summary },
  ...(r.status === 'running' ? r.subagents.filter(x => x.status === 'working').map(sa => ({ ...base, id: `${main}/${sa.id}`, parent: main, depth: 1, sub: sa.id,
    worker_id: null, role: sa.type, label: sa.description, status: 'working', doing: sa.in_tool, last: sa.last_action })) : [])];
});

function demoState(T, items) {
  const h = id => [...id].reduce((a, c) => a + c.charCodeAt(0), 0);
  const run = (id, skill, subject, status, extra) => {
    const subs = (SUBS[skill] || []).map((type, i) => { const ln = (ACT[skill] || ACT.ask)[(T + i + 1) % (ACT[skill] || ACT.ask).length];
      return { id: `${id}-s${i}`, type, status: (T + i) % 7 === 0 ? 'done' : 'working', last_action: ln, in_tool: (T + i) % 7 === 0 ? null : call(ln, T),
        description: `${type.replace(/-/g, ' ')} for ${subject || 'the lab'}` }; });
    const a = ACT[skill] || ACT.ask;
    return Object.assign({ run_id: id, skill, subject, target: subject || 'hub', status, backend: ['claude', 'codex', 'opencode'][h(id) % 3], created: ago(20 + h(id) % 70), session_id: 'S-' + id, transport: 'live', pid: 1000 + h(id),
      label: skill === 'ask' ? 'Summarise what moved overnight' : null, last_action: { summary: a[T % a.length] }, in_tool: call(a[T % a.length], T), subagents: subs, n_actions: 12 + T * 3 + h(id) % 20, elapsed_s: (20 + h(id) % 70) * 60 + T * 4,
      usage: { cost_usd: +(0.15 + (h(id) % 9) * 0.11 + T * (0.004 + (h(id) % 5) * 0.002)).toFixed(2) } }, extra || {});
  };
  const runs = [
    run('r-moe', 'experiment', 'moe', 'running'),
    run('r-rl', 'improve', 'rl', 'running'),
    run('r-ana', 'analyze', 'ana-1', T % 9 < 5 ? 'running' : 'completed'),
    run('r-lit', 'lit-review', 'lit-1', 'running', { heartbeat_age_s: 420, reason: 'no word from it for 7 minutes' }),
    run('r-scope', 'scope', 'scope-1', 'running'),
    run('r-paper', 'write-paper', 'paper-1', 'waiting_input', { pending_question: { tool_use_id: 'tq-paper', asked_at: ago(9), live: true, input: { questions: [
      { header: 'Paper structure', question: 'Lead the Results section with the scaling law or with the ablation?', options: [
        { label: 'The scaling law', description: 'the headline claim first; the ablation backs it up' },
        { label: 'The ablation', description: 'build up to the law from what each part contributes' }] }] } } }),
    run('r-sweep', 'experiment', 'rl', 'failed', { reason: 'timed out after its 45-minute limit (exp-019, seed 2)', finished: ago(95) }),
    run('r-rev', 'review-paper', 'rev-1', 'running'),
    run('r-ask', 'ask', null, 'running'),
    run('r-spawn', 'spawn-project', 'prop-2', items.find(i => i.id === 'prop-2' && !i.has_project) ? 'running' : 'completed'),
    run('r-ideate', 'ideate', null, T % 10 < 6 ? 'queued' : 'running'),
  ];
  const done = [run('r-night1', 'lit-review', 'lit-1', 'completed', { finished: ago(300) }), run('r-night2', 'experiment', 'moe', 'completed', { finished: ago(180) })];
  const cpTitle = id => ((window.__WORKFLOW_DEFAULT__.workflows || []).flatMap(w => w.checkpoints || []).find(c => c.id === id) || {}).title || id;
  const attention = items.flatMap(i => (i.waiting || []).map(c => ({ id: `cp:${i.id}:${c}`, sev: 'block', kind: 'checkpoint', title: cpTitle(c),
    body: i.title, idea: i.id, detail: { checkpoint: c, study: i.id }, actions: [{ id: 'checkpoint', label: 'review' }] })));
  attention.push({ id: 'alert:compute:rl', sev: 'warn', kind: 'alert', title: 'exp-021 has run 7.2 h, past its expected 6 h', body: 'Compute', idea: 'rl', detail: { panel: 'compute', study: 'rl' }, actions: [{ id: 'panel', label: 'open' }] });
  attention.push({ id: 'q:r-paper', sev: 'block', kind: 'question', title: 'Lead the Results with the scaling law or the ablation?', body: 'Scaling laws note · the writing agent is paused until you answer',
    run_id: 'r-paper', actions: [{ id: 'answer', label: 'answer' }] });
  attention.push({ id: 'fail:r-sweep', sev: 'warn', kind: 'crashed', title: 'An RL fine-tuning experiment timed out', body: 'exp-019, seed 2, after its 45-minute limit', run_id: 'r-sweep', actions: [{ id: 'tail', label: 'open' }] });
  const artifacts = artifactsAt(T);
  for (const x of artifacts.filter(x => x.question && !x.answered)) attention.push({ id: 'artifact:' + x.id, sev: 'warn', kind: 'artifact', title: x.title, body: `asks you: ${x.question}; the agent keeps working meanwhile`, idea: x.study, run_id: x.run_id, detail: { artifact: x.id }, actions: [{ id: 'artifact', label: 'answer' }] });
  const events = [['state_change', 'Distillation curricula moved to literature review', 420, 'lit-1'], ['run_finished', 'lit-review finished', 300, 'lit-1', 'completed'],
    ['checkpoint_approved', 'Approve full runs: approved (Sparse MoE routing)', 260, 'moe'], ['run_finished', 'experiment finished: exp-014', 180, 'moe', 'completed'],
    ['run_finished', 'exp-019 timed out', 95, 'rl', 'failed'], ['agent_waiting', 'the writing agent asked you something', 9, 'paper-1']]
    .map(([kind, detail, min, idea, status]) => ({ ts: ago(min), source: 'hub', kind, detail, idea, ...(status ? { status } : {}) }));
  const rec = id => ({ ts: ago(600), decision: 'approved', by: 'pi', via: 'dashboard' });
  return { artifacts, workflow: window.__WORKFLOW_DEFAULT__, now: iso(Date.now()), panels: { panels: NL.demoPanels(T, items) }, holds: {},
    items: items.map(it => ({ inflight: [], events: [], directives: [], workflow: 'research', slipped: [], ...it, waiting: it.waiting || [],
      checkpoints: Object.fromEntries((it.approved || []).map(c => [c, rec(c)])) })), runs: runs.concat(done), attention, workers: [], agents: demoAgents(runs),
    directives: [], checkpoints_waiting: attention.filter(a => a.kind === 'checkpoint').length, cold: false, events,
    executor: { available: true, enabled: true, caps: { total: 7 }, clis: DEMO_CLIS },
    campaign_states: NL.demoCampaignStates ? NL.demoCampaignStates(T) : [],
    campaigns: [] };
}

/* the demo's instruments: the shipped panels, with made-up data (their views are the real shipped ones) */
NL.demoPanels = (T, items = NL.getState()?.items || BASE_ITEMS) => [
  { id: 'compute', title: 'Compute', icon: '◔', description: 'GPU-hours, jobs and time', origin: 'shipped', pinned: ['home', 'dock', 'studies'], sources: ['collector'],
    summary: '124 of 200 GPU-hours · 5 running · 12 queued', ts: ago(1), alerts: 1, gauge: { value: 124, max: 200, label: 'GPU-h' } },
  { id: 'agent-spend', title: 'Agent time and spend', icon: '$', description: 'what your agents cost', origin: 'shipped', pinned: ['home', 'dock'], sources: ['collector'],
    summary: '$18.40 this week · 41 runs · 23.5 agent-hours', ts: ago(2), alerts: 0, gauge: { value: 18.4, max: 35, label: '$/wk' } },
  { id: 'studies-by-step', title: 'Studies by step', icon: '▤', description: 'where every study stands', origin: 'shipped', pinned: [], sources: ['registry'],
    summary: `${items.length} studies · ${new Set(items.map(i=>i.state)).size} steps in use`, ts: ago(1), alerts: 0 },
  { id: 'val-loss', title: 'Validation loss by variant', icon: '∿', description: 'made by the designer from runs/*/metrics.json', origin: 'lab', pinned: ['dock'], sources: ['files'],
    summary: 'top-2 routing leads by 0.09', ts: ago(3), alerts: 0, gauge: { value: 1.31, max: null } },
  { id: 'cluster-queue', title: 'Cluster queue', icon: '▦', description: 'jobs on fir, from squeue', origin: 'lab', pinned: [], sources: ['collector'], needs_approval: true, summary: '' }];
const day = n => iso(T0 - n * 86400e3).slice(0, 10);
NL.demoPanelData = {
  compute: { gpu_hours: 124, gpu_hours_budget: 200, runs_running: 5, jobs_queued: 12, slurm: true, max_concurrent: 4,
    studies: [{ study: 'moe', gpu_hours: 41, budget: 120, running: 3, queued: 4 }, { study: 'rl', gpu_hours: 62, budget: 60, running: 1, queued: 6 },
      { study: 'ana-1', gpu_hours: 12, budget: null, running: 0, queued: 0 }, { study: 'gsm', gpu_hours: 9, budget: 30, running: 1, queued: 2 }],
    running: [{ run_id: 'exp-021', study: 'rl', stage: 'FULL', hours: 7.2, expected_h: 6, over: true }, { run_id: 'exp-016', study: 'moe', stage: 'PILOT', hours: 1.4, expected_h: 2 },
      { run_id: 'exp-017', study: 'moe', stage: 'PILOT', hours: 1.1, expected_h: 2 }, { run_id: 'exp-018', study: 'moe', stage: 'SMOKE', hours: 0.1 }, { run_id: 'gsm-044', study: 'gsm', stage: 'FULL', hours: 3.3, expected_h: 4 }],
    gpus: [{ index: '0', name: 'H100', util: 92, mem_used: 61000, mem_total: 81920 }, { index: '1', name: 'H100', util: 88, mem_used: 54000, mem_total: 81920 }],
    series: [3, 5, 4, 8, 6, 9, 7, 11, 6, 4, 9, 12, 10, 8].map((v, i) => ({ day: day(13 - i), gpu_hours: v })),
    alerts: [{ level: 'warn', study: 'rl', say: 'exp-021 has run 7.2 h, past its expected 6 h' }, { level: 'block', study: 'rl', say: 'rl is over its GPU budget (62 of 60 GPU-hours)', hold: false }],
    gauge: { value: 124, max: 200, label: 'GPU-h' } },
  'agent-spend': { usd_week: 18.4, minutes_week: 1410, runs_week: 41,
    series: [1.2, 2.4, 0.8, 3.1, 2.2, 4.0, 4.7].map((v, i) => ({ day: day(6 - i), usd: v })),
    backends: [{ backend: 'claude', usd: 15.1, minutes: 820, runs: 22 }, { backend: 'codex', usd: 0, minutes: 410, runs: 11 }, { backend: 'opencode', usd: 0, minutes: 180, runs: 8 }],
    studies: [{ study: 'moe', usd: 6.2, minutes: 380, runs: 12 }, { study: 'rl', usd: 4.4, minutes: 300, runs: 9 }, { study: 'paper-1', usd: 3.1, minutes: 260, runs: 6 }] },
  'studies-by-step': () => ({ studies: (NL.getState()?.items || BASE_ITEMS).map(i => ({ id: i.id, title: i.title, state: i.state, updated: day(i.id.length % 5) })) }),
};

NL.startDemo = function startDemo() {
  document.title = "Newts' Lab · demo";
  setTimeout(() => NL.toast('Demo mode: nothing here is real, and nothing is written.'), 700);
  const items = BASE_ITEMS.map(x => Object.assign({}, x));
  let T = 0;
  function step() {
    // the lab moves on: a study advances now and then, and the new lab finishes building
    if (T === 4) Object.assign(items.find(i => i.id === 'prop-2'), { has_project: true, state: 'active', project_type: 'ml', next: 'experiment' });
    if (T % 6 === 3) { const it = items.find(i => i.id === 'spark-2'); const order = ['seed', 'lit-review', 'scoping']; it.state = order[(order.indexOf(it.state) + 1) % order.length]; }
    const s = demoState(T, items);
    s.lab_info = { name: 'Demo lab', path: '(synthetic)', setup: { completed: true } };
    NL.setState(s); T++;
  }
  step(); setInterval(step, 4000);
};
})();
