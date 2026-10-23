/* A browser-local guide. Navigation only: never signs in, changes settings or starts work. */
(function () {
  const N=window.NL,{html,useState,useEffect}=N;
  const stops=[
    {title:'Choose your agent',route:'setup',action:'Agents & model settings',open:()=>N.go('settings/agents'),
      text:'Connect Claude Code, Codex, opencode or an ACP agent. Sign in with its own account, then choose your model in Settings.',
      hint:'You decide whether the dashboard can start agents. Set task limits and permissions there too.'},
    {title:'Start a study',route:'start',action:'Open New study',
      text:'Bring a research question, an existing folder or a GitHub repository. Add a brief or files, then review the starting workflow.',
      hint:'Have work already? Select a task to use it or skip that task at the start. Creating a study starts no agents.'},
    {title:'Shape the workflow',route:'workflow',action:'Open Workflow',
      text:'Each task uses a skill, written instructions, or both. Connect tasks in order or in parallel. Choose a new, continued or forked conversation.',
      hint:'Import reusable skills under Skills. Shared workflow edits stay in draft until you review and publish them.'},
    {title:'Read the Lab',route:'',action:'Open the Lab',
      text:'Rooms are shared workspaces for tasks. Click a character for its task, conversation and outputs. Follow it to watch activity; hover to see teammates.',
      hint:'By machine keeps connected machines separate; Unified brings agents together. Use + Machine to connect over SSH.'},
    {title:'Know when to step in',route:'',action:'Open Inbox',open:()=>N.open(N.InboxSheet,{}, {key:'inbox'}),
      text:'The Inbox brings together agent questions, permission requests, checkpoints and interrupted work. The character also shows when it needs you.',
      hint:'A turn ending does not finish a task. Continue unfinished work from its conversation; checkpoint approval is a separate decision.'},
    {title:'Keep the evidence',route:'library',action:'Open Library',
      text:'Outputs holds published results and interactive HTML summaries. Documents shows project files. Notes & sources keeps retained papers, human notes and saved answers.',
      hint:'Choose a study to narrow the Library. Ask for a visual summary when you want an explainer to review recorded work.'},
    {title:'Ask ARLO',route:'',action:'Open workspace assistant',open:()=>N.openAssistant(),
      text:'The workspace assistant helps you understand the Lab, a study or an agent’s work. Choose its focus and agent in the conversation.',
      hint:'Answers are saved separately in the Library. A human note records context; an instruction asks a working agent to do something.'}
  ];
  N.openGuide=()=>window.dispatchEvent(new Event('arlo-guide'));
  N.Guide=({lab,home})=>{
    const key='arlo-guide:'+lab.lab_info.path;
    const [progress,setProgress]=useState(()=>N.ls.get(key)||{status:'new',step:0});
    const step=Math.floor(Math.max(0,Math.min(stops.length-1,Number(progress.step)||0))),stop=stops[step];
    const update=next=>{N.ls.set(key,next);setProgress(next)};
    const start=()=>{const next=progress.status==='done'?0:step;update({status:'open',step:next});N.go(stops[next].route)};
    useEffect(()=>{window.addEventListener('arlo-guide',start);return()=>window.removeEventListener('arlo-guide',start)},[progress.status,step]);
    const close=status=>{update({status,step});requestAnimationFrame(()=>document.querySelector('[aria-label="Open ARLO guide"]')?.focus())};
    const move=next=>{update({status:'open',step:next});N.go(stops[next].route)};
    if(progress.status!=='open')return home&&!N.DEMO&&progress.status==='new'?html`
      <aside class="arlo-welcome" aria-label="Welcome to ARLOtope"><img src="static/brand/arlotope-mark.png" alt=""/>
        <div class="grow"><h2>Meet ARLO</h2><p>A short guide to your agents, workflows and research workspace.</p></div>
        <div class="row"><${N.Btn} small kind="primary" onClick=${start}>Show me around</${N.Btn}><a class="btn btn-sm" href="#/start">New study</a></div>
        <button type="button" class="iconbtn sm" aria-label="Dismiss welcome" onClick=${()=>close('done')}>×</button></aside>`:null;
    return html`<aside class="arlo-guide" aria-label="ARLO guide">
      <header><img src="static/brand/arlotope-mark.png" alt=""/><b>ARLO</b><span class="muted small">${step+1} / ${stops.length}</span>
        <button type="button" class="iconbtn sm" aria-label="Close guide" onClick=${()=>close('paused')}>×</button></header>
      <div class="guide-copy" aria-live="polite"><h2>${stop.title}</h2><p>${stop.text}</p><small>${stop.hint}</small></div>
      <nav aria-label="Guide steps"><button type="button" class="link" onClick=${()=>stop.open?stop.open():N.go(stop.route)}>${stop.action} →</button>
        <span class="grow"></span><${N.Btn} small disabled=${step===0} onClick=${()=>move(step-1)}>Back</${N.Btn}>
        <${N.Btn} small kind="primary" onClick=${()=>step===stops.length-1?close('done'):move(step+1)}>${step===stops.length-1?'Done':'Next'}</${N.Btn}></nav>
    </aside>`;
  };
})();
