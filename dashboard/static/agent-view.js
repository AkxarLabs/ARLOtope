/* Shared presentation of recorded agents. No execution state or inferred progress. */
(function () {
  'use strict';
  const V = window.ArloAgents = {};
  V.message = (text, sub, role='general') => (sub ? 'For subagent '+sub+' ('+role+'), via its parent: ' : '')+text.trim();
  V.activities = {read:['▤','reading'],search:['⌕','searching'],edit:['✎','editing'],run:['⚗','running an experiment'],
    bash:['›','at the terminal'],git:['⑂','committing'],spawn:['⇢','briefing a subagent'],ask:['?','asking you'],
    plan:['☰','planning'],skill:['✦','following a procedure'],mcp:['⚙','using a tool'],tool:['•','working']};
  V.run = (s,a) => (s.runs || []).find(r => r.run_id === a.run_id);
  V.root = (s,a) => {
    const seen = new Set();
    while (a.parent && !seen.has(a.id)) {
      seen.add(a.id); const parent = (s.agents || []).find(p => p.id === a.parent);
      if (!parent) break; a = parent;
    }
    return a;
  };
  V.identity = (s,a) => {
    const root = V.root(s,a), r = V.run(s,root), sid = r?.session_id;
    let path=String(r?.remote?.path || r?.cwd || '').replace(/\\/g,'/').replace(/\/+$/,'');
    if(/^[a-z]:/i.test(path))path=path.toLowerCase();
    // Session IDs belong to a harness and execution location. A native fork has a new session.
    const family = sid ? JSON.stringify([r.backend,r.remote?.machine || r.machine || 'local',
      path,r.assignment?.identity || '',sid]) : root.id;
    return a === root ? family : family + '/' + (a.sub || a.worker_id || a.id);
  };
  V.task = (s,a) => {
    const root = V.root(s,a), r = V.run(s,root), node = r?.workflow_node || r?.assigned_step;
    return node && r.subject ? JSON.stringify([r.subject,node,r.workflow_visit || 1]) : root.id;
  };
  V.peers = (s,a) => (s.agents || []).filter(b => b.id !== a.id && !['done','completed','queued'].includes(b.status)
    && !['completed','failed','timeout','killed','cancelled'].includes(V.run(s,b)?.status) && V.task(s,b) === V.task(s,a));
  V.attention = (s,a) => {
    const r = V.run(s,a) || {}, main = !a.parent;
    const state = (id,label,mark,pose='wait') => ({id,label,mark,pose});
    if (main && r.pending_permissions?.length) return state('permission','Permission needed','!');
    if (a.doing?.kind === 'ask' || main && (r.pending_question || r.status === 'waiting_input'))
      return state('question','Waiting for you','?');
    const machine = r.remote?.machine || r.machine || a.machine;
    if (machine && (s.machines || []).some(m => m.id === machine && ['disconnected','error'].includes(m.state)))
      return state('offline','Machine disconnected','↯','idle');
    if (main && r.failure_kind === 'usage_limit' && !['starting','running','resuming','completed'].includes(r.status))
      return state('limit','Usage limit reached','Ⅱ','idle');
    if (main && r.needs_followup && !['starting','running','resuming'].includes(r.status)) return state('unfinished','Task unfinished','↻','idle');
    if (a.status === 'stalled') return state('quiet','No recent activity','…','sleep');
    if (a.status === 'queued' || r.status === 'queued') return state('queued','Queued','·','idle');
    if (a.status === 'asking') return state('question','Waiting for you','?');
    return null;
  };
  V.outputs = (s,a) => (s.artifacts || []).filter(x => a.run_id && (x.run_id === a.run_id || x.about?.run === a.run_id)
    && (!a.sub || x.about?.agent === a.sub));
})();
