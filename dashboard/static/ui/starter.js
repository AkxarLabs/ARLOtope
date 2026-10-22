/* A study starts with a question and optional existing code. No agent is launched by saving. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useRef, cls } = NL;
  const slugify = text => text.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
  const CHOICES = [
    { id: 'topic', title: 'A research question', sub: 'Start with a question.' },
    { id: 'local', title: 'An existing project', sub: 'On this computer or another machine.' },
    { id: 'github', title: 'A GitHub repository', sub: 'Clone a repository.' }
  ];
  const ProjectFiles = () => html`<details class="more"><summary>Files added to this project</summary>
    <p class="muted small"><code>.newts/project.json</code> keeps its identity. Notes and saved answers use <code>.newts/knowledge/</code> by default. Commit these only if they should travel with the project.</p>
    <p class="muted small"><code>.bus/</code> holds local attachment and task records. Keep it out of Git by adding <code>/.bus/</code> to <code>.git/info/exclude</code> or your <code>.gitignore</code>. Your ignore files stay unchanged.</p></details>`;
  const StartingPlan = ({ flow, plan, onChange, selected, onClose }) => {
    const tasks = plan?.tasks || {};
    const change = (id, patch) => { const next = {...tasks}, choice = {...next[id],...patch}; if(choice.action==='run')delete next[id];else next[id]=choice;
      onChange({workflow:flow.id,revision:flow.entry_revision,tasks:next}); };
    if(!selected)return null;
    return html`<section class="starting-task" aria-label="Starting task options"><header class="row between"><b>${flow.tasks.find(t=>t.id===selected)?.label||selected}</b><button type="button" class="iconbtn sm" aria-label="Close starting task" onClick=${onClose}>×</button></header>
      ${(flow.tasks||[]).filter(t=>t.id===selected).map(t=>{const c=tasks[t.id]||{action:'run'};return html`<section class="entry-task" key=${t.id}>
        <div class="chips" role="group" aria-label="Starting task choice">${[{value:'run',label:'Run task'},{value:'reuse',label:'Use existing work'},{value:'omit',label:'Skip at start'}].map(o=>html`<button type="button" class=${cls('chip-btn',c.action===o.value&&'on')} aria-pressed=${c.action===o.value} onClick=${()=>change(t.id,{action:o.value,note:c.note||'',refs:c.refs||[],outcome:c.outcome||'done'})}>${o.label}</button>`)}</div>
        ${c.action!=='run'?html`
          <p class="muted small">${c.action==='reuse'?'Use your references instead of running this task at the start.':'Continue without running this task at the start.'}</p>
          ${c.action==='reuse'?html`<${NL.Field} label="Existing work" hint="File paths, uploaded filenames, record IDs or source URLs; one per line."><${NL.Textarea} rows=${2} value=${(c.refs||[]).join('\n')} onInput=${v=>change(t.id,{refs:v.split('\n').map(s=>s.trim()).filter(Boolean)})}/></${NL.Field}>`:null}
          <details><summary>${Object.keys(t.outcomes||{}).length?'Note & routing':'Add note'}</summary><${NL.Textarea} ariaLabel="Starting task note" rows=${2} value=${c.note||''} onInput=${note=>change(t.id,{note})}/>
          ${Object.keys(t.outcomes||{}).length?html`<${NL.Field} label="Route after this task"><${NL.Select} value=${c.outcome||'done'} onChange=${outcome=>change(t.id,{outcome})} options=${['done',...Object.keys(t.outcomes)]}/></${NL.Field}>`:null}</details>
          <details><summary>If the workflow returns here</summary><p class="muted small">This choice applies at the start only. If a later task sends work back to ${t.label||t.id}, an agent runs it normally. This is a new pass through a task, not a new message.</p></details>
          ${(flow.checkpoints||[]).filter(cp=>cp.before===t.id||cp.during===t.id).map(cp=>html`<p class="muted small">◆ ${cp.title} still needs a decision before this choice takes effect.</p>`)}
        `:null}</section>`})}
    </section>`;
  };
  const GithubConnection = ({ machine, connection, onPick }) => {
    const [listing,setListing]=useState(false);
    const repos=NL.useGet(listing?'/api/starter/github?'+NL.qs({action:'repositories',machine}):null);
    const data=connection.data;
    useEffect(()=>setListing(false),[machine]);
    return html`<div class="github-connection">
      ${connection.error?html`<${NL.LoadState} ...${connection}/>`:!data?html`<${NL.Spinner}/>`:html`
        <div class="row-wrap"><span class="muted small">${data.connected?'GitHub · '+data.login:!data.installed?'GitHub CLI is not installed. Public repository URLs still work.':'GitHub is not connected.'}</span>
          ${data.connected?html`<${NL.Btn} small onClick=${()=>setListing(true)}>Choose repository</${NL.Btn}>`:data.installed?html`<${NL.Btn} small onClick=${()=>machine?NL.open(NL.TerminalSheet,{purpose:'login',backend:'github',machine}):NL.runOnLabMachine('login','github')}>Connect GitHub</${NL.Btn}>`:html`<a class="link small" href="https://cli.github.com/" target="_blank" rel="noopener">Get GitHub CLI ↗</a>`}
          <button type="button" class="link small" onClick=${()=>{connection.reload();repos.reload()}}>Check connection</button></div>
        ${data.notice?html`<p class="muted small">${data.notice}</p>`:null}`}
      ${listing?html`${!repos.data||repos.error?html`<${NL.LoadState} ...${repos}/>`:html`<${NL.Field} label="Repository"><${NL.Select} value="" onChange=${name=>{if(name){onPick(name);setListing(false)}}} options=${[{value:'',label:'Choose a repository…'},...(repos.data.repositories||[]).map(r=>({value:r.name,label:r.name+(r.private?' · private':'')}))]}/></${NL.Field}><p class="muted small">Recent repositories you can access. You can also enter an exact owner/repository below.</p>`}`:null}
    </div>`;
  };
  const Interests = ({ initial }) => {
    const [text, setText] = useState(initial || ''), [saved, setSaved] = useState(initial || '');
    const save = async () => {
      const result = await NL.act('/api/doc/save', { doc: 'research', text }, 'Research interests saved');
      if (result.ok) setSaved(text);
    };
    return html`<details class="research-interests"><summary>Your lab’s research interests</summary>
      <p class="muted">Optional context for agents.</p>
      <${NL.Field} label="Research topics and interests"><${NL.Textarea} value=${text} onInput=${setText} rows=${4} placeholder="Topics, methods or constraints…" /></${NL.Field}>
      <${NL.Btn} disabled=${text === saved} onClick=${save}>Save interests</${NL.Btn}></details>`;
  };
  NL.StarterPage = ({ query }) => {
    const draftKey = 'nl-study-draft:' + (NL.getState()?.lab_info?.path || location.origin);
    const [draft] = useState(() => NL.ls.get(draftKey, null) || {});
    const [context, setContext] = useState(null), [step, setStep] = useState(query?.kind||draft.title||draft.question||draft.local||draft.repo||draft.materialId?1:0), [kind, setKind] = useState(CHOICES.some(c=>c.id===query?.kind)?query.kind:draft.kind || 'topic');
    const form=useRef();
    useEffect(()=>{
      if(step===1)[...(form.current?.querySelectorAll('input:not([type=hidden]):not([type=file]),textarea')||[])].find(el=>!el.closest('details:not([open])')&&el.getClientRects().length)?.focus();
      if(step===2){document.querySelector('.stage')?.scrollTo(0,0);document.getElementById('study-review-heading')?.focus({preventScroll:true})}
    },[step,kind]);
    const [title, setTitle] = useState(draft.title || ''), [question, setQuestion] = useState(draft.question || ''), [id, setId] = useState(draft.id || '');
    const [local, setLocal] = useState(draft.local || ''), [repo, setRepo] = useState(draft.repo || ''), [resolved, setResolved] = useState(draft.resolved?.input===draft.repo?draft.resolved:null);
    const [workflow, updateWorkflow] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
    const [created, setCreated] = useState(null);
    const errorBox=useRef();
    useEffect(()=>{if(error){errorBox.current?.focus();errorBox.current?.scrollIntoView({block:'start'})}},[error]);
    const [machine,setMachine]=useState(draft.machine||''), [tags,setTags]=useState(draft.tags||[]);
    const github=NL.useGet(kind==='github'?'/api/starter/github?'+NL.qs({machine}):null);
    const [materials,setMaterials]=useState(null),[materialId,setMaterialId]=useState(draft.materialId||''),[materialBusy,setMaterialBusy]=useState(false);
    const [materialError,setMaterialError]=useState(''),[materialLoading,setMaterialLoading]=useState(!!draft.materialId),[materialRetry,setMaterialRetry]=useState(0);
    const [agentChoices,setAgentChoices]=useState(draft.agentChoices||{});
    const [entry,setEntry]=useState(draft.entry||null);
    const [entryTask,setEntryTask]=useState(null);
    const setWorkflow=next=>{if(next!==workflow)setEntryTask(null);updateWorkflow(next)};
    const [planPreview,setPlanPreview]=useState(null),[planError,setPlanError]=useState('');
    const [agent,setAgent]=useState(''),[instructions,setInstructions]=useState(draft.instructions||''),[applied,setApplied]=useState(false);
    const fileInput=useRef(),mounted=useRef(true),materialRef=useRef(draft.materialId||''),materialRead=useRef(0),lab=NL.useLab();
    const receiveMaterials=r=>{if(r.id===materialRef.current)setMaterials(previous=>previous?.id===r.id&&previous.version>r.version?previous:r)};
    useEffect(()=>()=>{mounted.current=false},[]);
    const tools=NL.useGet('/api/frameworks?'+NL.qs({machine:kind==='topic'?'':machine,project:kind==='topic'?'':local}));
    const inputs={title,question,workflow,tags,instructions,entry,local:kind==='local'?local:'',machine:kind==='local'?machine:''};
    const suggestion=materials?.suggestion, stale=!!suggestion&&(materials.analysis_revision!==materials.revision||JSON.stringify(materials.inputs)!==JSON.stringify(inputs));
    const active=['queued','starting','running','resuming','waiting_input'].includes(materials?.status);
    useEffect(()=>{
      let off=false,timer;
      if(!materialId){setMaterialError('');setMaterialLoading(false);return;}
      const load=async()=>{const generation=materialRead.current,r=await NL.get('/api/starter/draft?'+NL.qs({id:materialId}));
        if(off||materialRef.current!==materialId||generation!==materialRead.current)return;
        setMaterialLoading(false);setMaterialError(r.error||'');if(!r.error)receiveMaterials(r);
        if(active)timer=setTimeout(load,2500);
      };
      setMaterialLoading(true);load();return()=>{off=true;clearTimeout(timer)};
    },[materialId,active,materialRetry]);
    const materialUnavailable=!!materialId&&(materialLoading||!!materialError);
    useEffect(() => { if (!created) NL.ls.set(draftKey, { kind, title, question, id, local, repo, resolved, workflow, machine, tags, materialId, instructions,agentChoices,entry }); },
      [kind, title, question, id, local, repo, resolved, workflow, machine, tags, materialId, instructions,agentChoices,entry,created]);
    const ensureMaterials=async()=>{
      if(materialRef.current)return materialRef.current;
      const r=await NL.api('/api/starter/draft',{action:'create'});if(!r.ok)throw Error(r.error||'Could not save the draft.');
      materialRef.current=r.id;setMaterialId(r.id);receiveMaterials(r);return r.id;
    };
    const materialAction=async body=>{const value=await ensureMaterials();materialRead.current++;
      const r=await NL.api('/api/starter/draft',{id:value,...body});
      materialRead.current++;
      if(!r.ok){setMaterialLoading(false);setMaterialError((r.error||'Could not confirm the change.')+' Reload the materials before trying again.');throw Object.assign(Error(r.error),{material:true});}
      receiveMaterials(r);setApplied(false);setMaterialRetry(n=>n+1);return r};
    const upload=async files=>{if(!files.length)return;setMaterialBusy(true);setError('');try{
      for(const file of files){if(file.size>5*1024*1024)throw Error(file.name+' is larger than 5 MB.');
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('Could not read '+file.name));reader.readAsDataURL(file)});
        await materialAction({action:'upload',name:file.name,data});}
    }catch(e){if(!e.material)setError(e.message)}finally{setMaterialBusy(false);if(fileInput.current)fileInput.current.value=''}};
    const analyze=async()=>{setMaterialBusy(true);setError('');try{await materialAction({action:'analyze',inputs,...(agent.startsWith('preset:')?{preset:agent.slice(7)}:agent?{backend:agent.slice(8)}:{})})}catch(e){if(!e.material)setError(e.message)}finally{setMaterialBusy(false)}};
    const applySuggestion=()=>{if(!suggestion||stale)return;
      if(suggestion.title)setTitle(suggestion.title);if(suggestion.question)setQuestion(suggestion.question);
      if(context.workflows.some(w=>w.id===suggestion.workflow))setWorkflow(suggestion.workflow);
      if(suggestion.entry)setEntry(suggestion.entry);else if(suggestion.workflow&&suggestion.workflow!==workflow)setEntry(null);
      if(suggestion.tags)setTags(suggestion.tags);setApplied(true);
    };
    const starter = NL.useGet('/api/starter');
    useEffect(() => { const data = starter.data; if (data) { setContext(data); setWorkflow((data.workflows.find(w => w.id === draft.workflow) || data.workflows.find(w => w.default) || data.workflows[0] || {}).id || ''); } }, [starter.data]);
    const lookup = async () => {
      setError(''); setResolved(null); setBusy(true);
      try {
        const result = await NL.api('/api/starter/repository', { repository: repo, machine, authenticated: github.data?.connected===true });
        if (!result.ok) { setError(result.error || 'Could not look up that repository.'); return; }
        setResolved({ ...result.repository, input: repo, machine });
        if (!title.trim()) setTitle(result.repository.name.split('/')[1]);
      } finally { setBusy(false); }
    };
    const sid = id || slugify(title), flow = context?.workflows.find(w => w.id === workflow);
    const selectedEntry=entry?.workflow===workflow&&Object.keys(entry.tasks||{}).length?entry:null;
    const customAgents=agentChoices.default_preset||Object.keys(agentChoices.role_presets||{}).length;
    const validEntry=!selectedEntry||(selectedEntry.revision===flow?.entry_revision&&Object.values(selectedEntry.tasks).every(c=>c.action!=='reuse'||c.refs?.length));
    const toolBlocked=w=>NL.frameworkBlocked(w,tools.data)||kind==='topic'&&NL.requiredFrameworks(w).length>0;
    const valid = !materialUnavailable && !toolBlocked(flow||{}) && title.trim() && question.trim() && sid && workflow &&
      validEntry && (kind === 'topic' || kind === 'local' && local.trim() || kind === 'github' && resolved?.input === repo && (resolved.machine||'')===machine && (!machine || local.trim()));
    const planKey=JSON.stringify([workflow,selectedEntry]),currentPlan=useRef(planKey);currentPlan.current=planKey;
    const review=async()=>{const key=planKey;setPlanError('');setPlanPreview(null);setBusy(true);try{
      const r=await NL.api('/api/starter/plan',{workflow,entry:selectedEntry});if(currentPlan.current!==key)return;
      if(!r.ok){setPlanError(r.error||'Could not preview the starting plan.');return}setPlanPreview(r);setStep(2);setError('');
    }finally{setBusy(false)}};
    const save = async () => {
      if (!valid || busy) return;
      setError(''); setBusy(true);
      try {
        const result = await NL.api('/api/starter', { confirm: true, title: title.trim(), question: question.trim(),
          slug: sid, workflow, tags, agents:agentChoices, entry:selectedEntry, draft:materialId, github_auth:github.data?.connected===true, machine:kind==='topic'?'':machine, local: kind === 'local'||kind==='github'&&machine ? local.trim() : '', repo: kind === 'github' ? resolved.name : '' });
        if (!result.ok) { setError(result.error || 'The study could not be created.'); return; }
        NL.ls.set(draftKey, null); NL.invalidateLibrary(); await NL.refresh(); setCreated(result);
      } finally { setBusy(false); }
    };
    const firstTask = () => {
      NL.go('study/' + created.study);
      setTimeout(() => NL.openAsk((created.project ? 'Inspect the existing project and explain how it works before proposing changes. '
        + 'Keep its code, environment and structure. Do not add scaffolding or install dependencies unless I request it. ' : '')
        + 'My research question / task:\n' + question.trim(), created.study), 0);
    };
    const reset = () => { setCreated(null); setStep(0); setTitle(''); setQuestion(''); setId(''); setTags([]); setLocal(''); setRepo(''); setResolved(null); setMaterials(null);setMaterialId('');materialRef.current='';setInstructions('');setMachine('');setAgentChoices({});setEntry(null);setAgent('');setApplied(false);setError('');setKind('topic'); };
    // A same-route New study click supplies a fresh query object. Keep unfinished drafts.
    useEffect(() => { if (created) reset(); }, [query]);
    if (created) return html`<div class="page starter-page"><div class="kicker">Study created</div><h1>${title}</h1>
      
      ${created.project ? html`<p class="mono path-wrap">${created.project}</p>` : null}
      ${created.project ? html`<${ProjectFiles}/>` : null}
      ${!NL.item(lab,created.study)?html`<${NL.LoadState} error="Study saved. Reload its details to continue." reload=${NL.refresh}/>`:null}
      <div class="starter-actions"><${NL.Btn} kind="primary" disabled=${!NL.item(lab,created.study)} onClick=${() => NL.go('study/' + created.study)}>Open study</${NL.Btn}>
        <${NL.Btn} disabled=${!NL.item(lab,created.study)} onClick=${firstTask}>Plan with an agent</${NL.Btn}>
        <${NL.Btn} onClick=${reset}>Create another study</${NL.Btn}></div>
      <section class="process-primer"><h2>Workflow</h2><p>${flow?.title || 'Workflow'} · Edit tasks, instructions and checkpoints.</p>
        ${flow?html`<${NL.WorkflowOverview} workflow=${flow} entry=${selectedEntry}/>`:null}
        <a class="link" href="#/workflow">Explore your workflow →</a></section></div>`;
    return html`<div class="page starter-page"><header class="page-head"><div><h1>New study</h1></div></header>
      <ol class="starter-progress" aria-label="New study steps">${['Study details', 'Review'].map((label, i) => html`<li aria-current=${(step===2?1:0) === i ? 'step' : null}><span>${String(i + 1).padStart(2, '0')}</span>${label}</li>`)}</ol>
      ${error ? html`<div class="note note-warn path-wrap" role="alert" tabIndex="-1" ref=${errorBox}>${error}</div>` : null}
      ${!context || starter.error ? html`<${NL.LoadState} ...${starter} />` : null}
      ${step === 0 ? html`<div class="starter-choices">${CHOICES.map((choice, i) => html`<button type="button" class=${cls('starter-choice', kind === choice.id && 'selected')}
        disabled=${!context} onClick=${() => { setKind(choice.id); setStep(1); setError(''); }}><span class="choice-number">0${i + 1}</span><span><b>${choice.title}</b><small>${choice.sub}</small></span><span aria-hidden="true">→</span></button>`)}</div>
        ${context ? html`<${Interests} initial=${context.topics} />` : null}
        ` : null}
      ${step === 1 ? html`<div class="starter-form" ref=${form}>
        <div class="starter-source" role="group" aria-label="Starting point">${CHOICES.map(c=>html`<button type="button" aria-pressed=${kind===c.id} onClick=${()=>{setKind(c.id);setError('')}}>${c.title}</button>`)}</div>
        ${kind!=='topic'?html`<${NL.MachinePicker} value=${machine} onChange=${v=>{setMachine(v);setLocal('')}} onProject=${p=>{setLocal(p.path);setMachine(p.machine==='local'?'':p.machine);setKind('local');if(!title.trim())setTitle(p.title||'');setId(p.ours?p.study||'':'')}}/>`:null}
        ${kind === 'github' ? html`<${GithubConnection} machine=${machine} connection=${github} onPick=${name=>{setRepo(name);setResolved(null)}}/>
          <${NL.Field} label="GitHub repository" hint="An exact owner/repository or GitHub URL. Private repositories use the connected account on the selected machine."><${NL.Input} value=${repo} onInput=${v => { setRepo(v); setResolved(null); }} placeholder="numpy/numpy" /></${NL.Field}>
          <${NL.Btn} onClick=${lookup} busy=${busy} disabled=${!repo.trim()}>Look up repository</${NL.Btn}>
          ${resolved ? html`<div class="repo-summary"><a class="link" href=${resolved.url} target="_blank" rel="noopener">${resolved.name} ↗</a><p>${resolved.description}</p><span class="muted small">${resolved.language || 'Source repository'}${resolved.private?' · Private':''}${resolved.archived ? ' · Archived' : ''}</span></div>` : null}` : null}
        ${kind === 'local'||kind==='github'&&machine ? html`<div class="project-folder"><${NL.Field} label=${kind==='github'?'New working copy':'Project folder'} hint=${kind==='github'?'Choose a parent folder; a new repository folder will be created inside it.':machine?'An existing folder on the selected machine.':'An existing folder on this computer.'}><${NL.Input} value=${local} onInput=${setLocal} mono placeholder=${machine?'/home/me/research/project':'Choose a project folder'} /></${NL.Field}>
          <${NL.Btn} onClick=${()=>NL.pickFolder({machine,initial:local?(kind==='github'?local.replace(/[\\/][^\\/]+$/,''):local):'~',title:kind==='github'?'Choose clone location':'Choose project folder',onPick:p=>setLocal(kind==='github'?p.replace(/[\\/]$/,'')+'/'+(resolved?.name.split('/')[1]||sid||'project'):p)})}>Browse…</${NL.Btn}></div>` : null}
        <details class="study-materials" open=${!!materialError||!!materials?.files?.length||!!materials?.run_id}><summary>Add a brief or files <span class="muted small">${materials?.files?.length?' · '+NL.plural(materials.files.length,'file'):''}</span></summary>
          <p class="muted small">Add a project brief, papers, notes or images. Up to 5 MB each · 20 MB total.</p>
          ${materialError?html`<${NL.LoadState} error=${materialError} stale=${!!materials} reload=${()=>setMaterialRetry(n=>n+1)}/>`:materialLoading?html`<p role="status" class="muted small">Loading materials…</p>`:null}
          <input type="file" multiple ref=${fileInput} class="study-file-input" aria-label="Add study materials" disabled=${materialBusy||materialUnavailable} onChange=${e=>upload([...e.target.files])}/>
          ${materials?.files?.map(f=>html`<div class="material-row"><span class="grow path-wrap">${f.name}<small class="muted">${Math.max(1,Math.round(f.size/1024))} KB</small></span><${NL.Btn} small disabled=${materialBusy||materialUnavailable} onClick=${async()=>{setMaterialBusy(true);try{await materialAction({action:'remove',file:f.stored})}catch(e){if(!e.material)setError(e.message)}finally{setMaterialBusy(false)}}}>Remove</${NL.Btn}></div>`)}
          ${materialId?html`<button type="button" class="link small" disabled=${materialBusy||active||materialUnavailable} onClick=${async()=>{
            if(!await NL.confirm({title:'Clear materials and suggestions?',body:'Your typed study details will stay.',ok:'Clear materials'}))return;
            setMaterialBusy(true);try{const r=await NL.api('/api/starter/draft',{action:'discard',id:materialId});if(!r.ok)throw Error(r.error);materialRef.current='';setMaterialId('');setMaterials(null);setApplied(false)}catch(e){setError(e.message)}finally{setMaterialBusy(false)}
          }}>Clear materials & suggestions</button>`:null}
          <details class="more"><summary>Agent help</summary>
            <p class="muted small">Read these materials and suggest details below. Uses your agent account; nothing starts until you ask.</p>
            <${NL.AgentChoice} value=${agent} onChange=${setAgent}/>
            <${NL.Field} label="What help would you like?" hint="Optional. Leave blank to suggest a title, research goal and process."><${NL.Textarea} value=${instructions} onInput=${setInstructions} rows=${2} placeholder="For example: clarify the hypothesis and list open questions."/></${NL.Field}>
            ${!NL.exec(lab).enabled?html`<div class="row"><${NL.Btn} small onClick=${async()=>{const r=await NL.api('/api/executor/enable',{enabled:true,confirm:true});if(r.ok)NL.refresh();else setError(r.error)}}>Enable agent runs</${NL.Btn}><a class="link small" href="#/setup">Agent setup</a></div>`:null}
            <div class="row"><${NL.Btn} onClick=${analyze} busy=${materialBusy} disabled=${materialUnavailable||active||!NL.exec(lab).enabled||!materials?.files?.length&&!question.trim()&&!title.trim()}>Suggest study details</${NL.Btn}>
              ${materials?.run_id?html`<button type="button" class="link" onClick=${()=>NL.openRun(materials.run_id)}>Open conversation</button>`:null}</div>
            ${active?html`<p role="status" class="muted small">${materials.status==='waiting_input'?'The agent needs your input. Open the conversation.':'Agent working… You can keep editing.'}</p>`:null}
            ${materials?.suggestion_error?html`<p role="status">${materials.suggestion_error}</p>`:null}
            ${materials?.status&&['failed','killed','unavailable'].includes(materials.status)?html`<p role="status">The agent stopped. Open the conversation or try again.</p>`:null}
          </details>
          ${suggestion?html`<section class="study-suggestion"><h3>Suggested details</h3><b>${suggestion.title}</b><p class="suggested-question">${suggestion.question}</p><p class="muted small">${context?.workflows.find(w=>w.id===suggestion.workflow)?.title||'Keep current process'}${suggestion.tags?.length?' · '+suggestion.tags.join(', '):''}</p>
            ${suggestion.analysis?html`<details><summary>Agent’s notes</summary><${NL.Markdown} text=${suggestion.analysis}/></details>`:null}
            ${suggestion.entry?html`<p class="muted small">Includes a starting plan. Review its task choices below after applying.</p>`:null}
            <p class="muted small">${applied?'Applied. Edit the fields below before reviewing.':stale?'Your inputs changed. Ask again for an updated suggestion.':'Review this suggestion before applying it. It will replace the suggested fields below.'}</p>
            <${NL.Btn} disabled=${materialUnavailable||stale||applied||active} onClick=${applySuggestion}>Apply suggestion</${NL.Btn}></section>`:null}
        </details>
        <${NL.Field} label="Study title"><${NL.Input} value=${title} onInput=${setTitle} placeholder="A short, useful name" /></${NL.Field}>
        <${NL.Field} label="What would you like to investigate?" hint="A research topic, a question, or the first task for this project."><${NL.Textarea} value=${question} onInput=${setQuestion} rows=${4} placeholder="What do you want to understand, test or build on?" /></${NL.Field}>
        <${NL.WorkflowPicker} label="Starting workflow" workflows=${context?.workflows||[]} value=${workflow} onChange=${setWorkflow} blocked=${toolBlocked}/>
        ${flow?html`<${NL.WorkflowOverview} workflow=${flow} entry=${selectedEntry} selected=${entryTask} onSelect=${id=>setEntryTask(current=>current===id?null:id)}/>
          <p class="muted small">Select a task to use existing work or skip it at the start.</p>`:null}
        ${flow?html`<${StartingPlan} flow=${flow} plan=${entry?.workflow===workflow?entry:null} selected=${entryTask} onClose=${()=>setEntryTask(null)} onChange=${setEntry}/>`:null}
        <${NL.FrameworkTools} read=${tools}/>
        ${selectedEntry&&selectedEntry.revision!==flow?.entry_revision?html`<p role="alert">The workflow changed. Review your starting plan and update a choice before continuing.</p>`:null}
        <details class="starter-agent-choices"><summary>Study settings <span class="muted small">${tags.length?'· '+NL.plural(tags.length,'tag'):''}${customAgents?' · custom agents':''}</span></summary><${NL.Field} label="Tags"><${NL.TagInput} value=${tags} onChange=${setTags}/></${NL.Field}><${NL.AgentAssignments} value=${agentChoices} onDraft=${setAgentChoices}/><details><summary>Study ID</summary><${NL.Field} label="Folder and study ID" hint="Generated from the title. Change it if you need another name."><${NL.Input} value=${sid} onInput=${setId} mono /></${NL.Field}></details></details>
        ${planError?html`<p class="note note-warn" role="alert">${planError}</p>`:null}
        <div class="starter-actions"><${NL.Btn} kind="primary" disabled=${!valid || busy||materialBusy} onClick=${review}>Review study</${NL.Btn}></div></div>` : null}
      ${step === 2 ? html`<section class="starter-review"><h2 id="study-review-heading" tabIndex="-1">${title}</h2><p class="research-question">${question}</p><dl>
        <dt>Workflow</dt><dd>${flow?.title}</dd>${tags.length?html`<dt>Tags</dt><dd><${NL.Tags} value=${tags}/></dd>`:null}<dt>Study record</dt><dd class="mono">studies/${sid}/IDEA.md</dd>
        ${materials?.files?.length?html`<dt>Materials</dt><dd>${materials.files.map(f=>f.name).join(', ')}</dd>`:null}
        ${selectedEntry?html`<dt>Starting choices</dt><dd>${Object.entries(selectedEntry.tasks).map(([id,c])=>html`<p><b>${flow?.tasks.find(t=>t.id===id)?.label||id}</b> · ${c.action==='reuse'?'Use existing work':'Skip at start'}${c.note?html`<br/>${c.note}`:null}${c.refs?.length?html`<br/><span class="mono path-wrap">${c.refs.join(' · ')}</span>`:null}</p>`)}<p>Checkpoints still apply. No agent starts.</p></dd>`:null}
        ${planPreview?html`<dt>First work</dt><dd>${planPreview.ready.length?planPreview.ready.map(id=>flow?.tasks.find(t=>t.id===id)?.label||id).join(' · '):planPreview.finished?'All selected work is already accounted for. No tasks to run.':'Waiting for a checkpoint decision.'}
          ${planPreview.waiting.map(cp=>html`<p>◆ ${cp.title}</p>`)}
          ${Object.keys(planPreview.joins||{}).length?html`<p class="muted small">Joins wait for the remaining branches.</p>`:null}</dd>`:null}
        ${machine&&kind!=='topic'?html`<dt>Machine</dt><dd>${machine}</dd>`:null}
        ${kind === 'local' ? html`<dt>Existing folder</dt><dd class="mono path-wrap">${local}</dd>` : kind === 'github' ? html`<dt>Clone from</dt><dd>${resolved?.name}</dd><dt>New working copy</dt><dd class="mono path-wrap">${machine ? local : context?.projects_root+'/'+sid}</dd>` : null}</dl>
        ${flow?html`<${NL.WorkflowOverview} workflow=${flow} entry=${selectedEntry} ready=${planPreview?.ready||[]}/>`:null}
        <p class="muted">${kind === 'github' ? 'Saving downloads this repository and adds Lab registration files. It does not install or run its code.' : kind === 'local' ? 'Saving creates the study and adds Lab registration files to this folder. Your code and environment stay unchanged. No agent starts.' : 'Saving creates a study record. No agent starts.'}</p>
        ${kind !== 'topic' ? html`<${ProjectFiles}/>` : null}
        ${customAgents?html`<p class="muted small">Agents: ${agentChoices.default_preset||'Lab default'}${Object.keys(agentChoices.role_presets||{}).length?' · '+NL.plural(Object.keys(agentChoices.role_presets).length,'role override'):''}. Use Back to edit.</p>`:null}
        ${materialError?html`<${NL.LoadState} error=${materialError} stale=${!!materials} reload=${()=>setMaterialRetry(n=>n+1)}/>`:materialLoading?html`<p role="status" class="muted small">Loading materials…</p>`:null}
        <div class="starter-actions"><${NL.Btn} disabled=${busy} onClick=${() => setStep(1)}>Back</${NL.Btn}><${NL.Btn} kind="primary" busy=${busy} disabled=${materialUnavailable} onClick=${save}>${kind === 'github' ? 'Clone & create study' : 'Create study'}</${NL.Btn}></div>
        ${busy && kind === 'github' ? html`<p class="muted" role="status">Cloning repository…</p>` : null}</section>` : null}
      <p class="starter-help muted small">${!NL.agentReady(lab) ? html`<a class="link" href="#/setup">Connect an agent</a> · ` : null}<a class="link" href="#/workflow">Workflow</a></p>
    </div>`;
  };
})();
