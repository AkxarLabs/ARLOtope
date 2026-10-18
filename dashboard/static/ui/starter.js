/* A study starts with a question and optional existing code. No agent is launched by saving. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useRef, cls } = NL;
  const slugify = text => text.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
  const CHOICES = [
    { id: 'topic', title: 'A research question', sub: 'Start with a question.' },
    { id: 'local', title: 'An existing project', sub: 'On this computer or another machine.' },
    { id: 'github', title: 'A GitHub repository', sub: 'Clone a public repository.' }
  ];
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
  NL.ResearchInterests = Interests;
  NL.StarterPage = ({ query }) => {
    const draftKey = 'nl-study-draft:' + (NL.getState()?.lab_info?.path || location.origin);
    const [draft] = useState(() => NL.ls.get(draftKey, null) || {});
    const [context, setContext] = useState(null), [step, setStep] = useState(query?.kind||draft.title||draft.question||draft.local||draft.repo||draft.materialId?1:0), [kind, setKind] = useState(CHOICES.some(c=>c.id===query?.kind)?query.kind:draft.kind || 'topic');
    const form=useRef();
    useEffect(()=>{
      if(step===1)[...(form.current?.querySelectorAll('input:not([type=hidden]),textarea')||[])].find(el=>el.getClientRects().length)?.focus();
      if(step===2){document.querySelector('.stage')?.scrollTo(0,0);document.getElementById('study-review-heading')?.focus({preventScroll:true})}
    },[step,kind]);
    const [title, setTitle] = useState(draft.title || ''), [question, setQuestion] = useState(draft.question || ''), [id, setId] = useState(draft.id || '');
    const [local, setLocal] = useState(draft.local || ''), [repo, setRepo] = useState(draft.repo || ''), [resolved, setResolved] = useState(draft.resolved?.input===draft.repo?draft.resolved:null);
    const [workflow, setWorkflow] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
    const [created, setCreated] = useState(null);
    const [machine,setMachine]=useState(draft.machine||''), [tags,setTags]=useState(draft.tags||[]);
    const [materials,setMaterials]=useState(null),[materialId,setMaterialId]=useState(draft.materialId||''),[materialBusy,setMaterialBusy]=useState(false);
    const [agentChoices,setAgentChoices]=useState(draft.agentChoices||{});
    const [agent,setAgent]=useState(''),[instructions,setInstructions]=useState(draft.instructions||''),[applied,setApplied]=useState(false);
    const fileInput=useRef(),mounted=useRef(true),materialRef=useRef(draft.materialId||''),lab=NL.useLab();
    const receiveMaterials=r=>{if(r.id===materialRef.current)setMaterials(previous=>previous?.id===r.id&&previous.version>r.version?previous:r)};
    useEffect(()=>()=>{mounted.current=false},[]);
    const inputs={title,question,workflow,tags,instructions};
    const suggestion=materials?.suggestion, stale=!!suggestion&&(materials.analysis_revision!==materials.revision||JSON.stringify(materials.inputs)!==JSON.stringify(inputs));
    const active=['queued','starting','running','resuming','waiting_input'].includes(materials?.status);
    const loadMaterials=async value=>{const r=await NL.get('/api/starter/draft?'+NL.qs({id:value}));if(!mounted.current)return;
      if(r.error)setError(r.error);else receiveMaterials(r)};
    useEffect(()=>{if(materialId)loadMaterials(materialId)},[materialId]);
    useEffect(()=>{if(!active||!materialId)return;const timer=setInterval(()=>loadMaterials(materialId),2500);return()=>clearInterval(timer)},[active,materialId]);
    useEffect(() => { if (!created) NL.ls.set(draftKey, { kind, title, question, id, local, repo, resolved, workflow, machine, tags, materialId, instructions,agentChoices }); },
      [kind, title, question, id, local, repo, resolved, workflow, machine, tags, materialId, instructions,agentChoices,created]);
    const ensureMaterials=async()=>{
      if(materialRef.current)return materialRef.current;
      const r=await NL.api('/api/starter/draft',{action:'create'});if(!r.ok)throw Error(r.error||'Could not save the draft.');
      materialRef.current=r.id;setMaterialId(r.id);receiveMaterials(r);return r.id;
    };
    const materialAction=async body=>{const value=await ensureMaterials();const r=await NL.api('/api/starter/draft',{id:value,...body});
      if(!r.ok)throw Error(r.error||'Could not save the materials.');receiveMaterials(r);setApplied(false);return r};
    const upload=async files=>{if(!files.length)return;setMaterialBusy(true);setError('');try{
      for(const file of files){if(file.size>5*1024*1024)throw Error(file.name+' is larger than 5 MB.');
        const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('Could not read '+file.name));reader.readAsDataURL(file)});
        await materialAction({action:'upload',name:file.name,data});}
    }catch(e){setError(e.message)}finally{setMaterialBusy(false);if(fileInput.current)fileInput.current.value=''}};
    const analyze=async()=>{setMaterialBusy(true);setError('');try{await materialAction({action:'analyze',inputs,...(agent.startsWith('preset:')?{preset:agent.slice(7)}:agent?{backend:agent.slice(8)}:{})})}catch(e){setError(e.message)}finally{setMaterialBusy(false)}};
    const applySuggestion=()=>{if(!suggestion||stale)return;
      if(suggestion.title)setTitle(suggestion.title);if(suggestion.question)setQuestion(suggestion.question);
      if(context.workflows.some(w=>w.id===suggestion.workflow))setWorkflow(suggestion.workflow);
      if(suggestion.tags)setTags(suggestion.tags);setApplied(true);
    };
    useEffect(() => { let alive = true; NL.get('/api/starter').then(data => {
      if (!alive) return;
      if (data.error) setError(data.error);
      else { setContext(data); setWorkflow((data.workflows.find(w => w.id === draft.workflow) || data.workflows.find(w => w.default) || data.workflows[0] || {}).id || ''); }
    }); return () => { alive = false; }; }, []);
    const lookup = async () => {
      setError(''); setResolved(null); setBusy(true);
      try {
        const result = await NL.api('/api/starter/repository', { repository: repo });
        if (!result.ok) { setError(result.error || 'Could not look up that repository.'); return; }
        setResolved({ ...result.repository, input: repo });
        if (!title.trim()) setTitle(result.repository.name.split('/')[1]);
      } finally { setBusy(false); }
    };
    const sid = id || slugify(title), flow = context?.workflows.find(w => w.id === workflow);
    const valid = title.trim() && question.trim() && sid && workflow &&
      (kind === 'topic' || kind === 'local' && local.trim() || kind === 'github' && resolved?.input === repo && (!machine || local.trim()));
    const save = async () => {
      if (!valid || busy) return;
      setError(''); setBusy(true);
      try {
        const result = await NL.api('/api/starter', { confirm: true, title: title.trim(), question: question.trim(),
          slug: sid, workflow, tags, agents:agentChoices, draft:materialId, machine:kind==='topic'?'':machine, local: kind === 'local'||kind==='github'&&machine ? local.trim() : '', repo: kind === 'github' ? resolved.name : '' });
        if (!result.ok) { setError(result.error || 'The study could not be created.'); return; }
        NL.ls.set(draftKey, null); NL.invalidateLibrary(); setCreated(result); NL.refresh();
      } finally { setBusy(false); }
    };
    const firstTask = () => {
      NL.go('study/' + created.study);
      setTimeout(() => NL.openAsk((created.project ? 'Inspect the existing project and explain how it works before proposing changes. '
        + 'Keep its code, environment and structure. Do not add scaffolding or install dependencies unless I request it. ' : '')
        + 'My research question / task:\n' + question.trim(), created.study), 0);
    };
    if (created) return html`<div class="page starter-page"><div class="kicker">Study created</div><h1>${title}</h1>
      
      ${created.project ? html`<p class="mono path-wrap">${created.project}</p>` : null}
      <div class="starter-actions"><${NL.Btn} kind="primary" onClick=${firstTask}>Plan the first task with an agent</${NL.Btn}>
        <${NL.Btn} onClick=${() => NL.go('study/' + created.study)}>Open study</${NL.Btn}>
        <${NL.Btn} onClick=${() => { setCreated(null); setStep(0); setTitle(''); setQuestion(''); setId(''); setTags([]); setLocal(''); setRepo(''); setResolved(null); setMaterials(null);setMaterialId('');materialRef.current='';setInstructions('');setMachine('');setAgentChoices({});setAgent('');setApplied(false);setError('');setKind('topic'); }}>Create another study</${NL.Btn}></div>
      <section class="process-primer"><h2>Workflow</h2><p>${flow?.title || 'Workflow'} · Edit tasks, instructions and checkpoints.</p>
        <a class="link" href="#/workflow">Explore your workflow →</a></section></div>`;
    return html`<div class="page starter-page"><header class="page-head"><div><h1>New study</h1></div></header>
      <ol class="starter-progress" aria-label="New study steps">${['Study details', 'Review'].map((label, i) => html`<li aria-current=${(step===2?1:0) === i ? 'step' : null}><span>${String(i + 1).padStart(2, '0')}</span>${label}</li>`)}</ol>
      ${error ? html`<div class="note note-warn" role="alert">${error}</div>` : null}
      ${!context && !error ? html`<${NL.Spinner} />` : null}
      ${step === 0 ? html`<div class="starter-choices">${CHOICES.map((choice, i) => html`<button type="button" class=${cls('starter-choice', kind === choice.id && 'selected')}
        disabled=${!context} onClick=${() => { setKind(choice.id); setStep(1); setError(''); }}><span class="choice-number">0${i + 1}</span><span><b>${choice.title}</b><small>${choice.sub}</small></span><span aria-hidden="true">→</span></button>`)}</div>
        ${context ? html`<${Interests} initial=${context.topics} />` : null}
        ` : null}
      ${step === 1 ? html`<div class="starter-form" ref=${form}>
        <div class="starter-source" role="group" aria-label="Starting point">${CHOICES.map(c=>html`<button type="button" aria-pressed=${kind===c.id} onClick=${()=>{setKind(c.id);setError('')}}>${c.title}</button>`)}</div>
        ${kind!=='topic'?html`<${NL.MachinePicker} value=${machine} onChange=${v=>{setMachine(v);setLocal('')}} onProject=${p=>{setLocal(p.path);setMachine(p.machine==='local'?'':p.machine);setKind('local');if(!title.trim())setTitle(p.title||'');setId(p.ours?p.study||'':'')}}/>`:null}
        ${kind === 'github' ? html`<${NL.Field} label="GitHub repository" hint="An exact public owner/repository or GitHub URL. Sent to GitHub only when you press Look up."><${NL.Input} value=${repo} onInput=${v => { setRepo(v); setResolved(null); }} placeholder="numpy/numpy" /></${NL.Field}>
          <${NL.Btn} onClick=${lookup} busy=${busy} disabled=${!repo.trim()}>Look up repository</${NL.Btn}>
          ${resolved ? html`<div class="repo-summary"><a class="link" href=${resolved.url} target="_blank" rel="noopener">${resolved.name} ↗</a><p>${resolved.description}</p><span class="muted small">${resolved.language || 'Source repository'}${resolved.archived ? ' · Archived' : ''}</span></div>` : null}` : null}
        ${kind === 'local'||kind==='github'&&machine ? html`<div class="project-folder"><${NL.Field} label=${kind==='github'?'New working copy':'Project folder'} hint=${kind==='github'?'Choose a parent folder; a new repository folder will be created inside it.':machine?'An existing folder on the selected machine.':'An existing folder on this computer.'}><${NL.Input} value=${local} onInput=${setLocal} mono placeholder=${machine?'/home/me/research/project':'Choose a project folder'} /></${NL.Field}>
          <${NL.Btn} onClick=${()=>NL.pickFolder({machine,initial:local?(kind==='github'?local.replace(/[\\/][^\\/]+$/,''):local):'~',title:kind==='github'?'Choose clone location':'Choose project folder',onPick:p=>setLocal(kind==='github'?p.replace(/[\\/]$/,'')+'/'+(resolved?.name.split('/')[1]||sid||'project'):p)})}>Browse…</${NL.Btn}></div>` : null}
        <details class="study-materials" open=${!!materials?.files?.length||!!materials?.run_id}><summary>Brief & materials <span class="muted small">Optional${materials?.files?.length?' · '+materials.files.length+' files':''}</span></summary>
          <p class="muted small">Add a project brief, papers, notes or images. Up to 5 MB each · 20 MB total.</p>
          <input type="file" multiple ref=${fileInput} class="study-file-input" aria-label="Add study materials" disabled=${materialBusy} onChange=${e=>upload([...e.target.files])}/>
          ${materials?.files?.map(f=>html`<div class="material-row"><span class="grow path-wrap">${f.name}<small class="muted">${Math.max(1,Math.round(f.size/1024))} KB</small></span><${NL.Btn} small disabled=${materialBusy} onClick=${async()=>{setMaterialBusy(true);try{await materialAction({action:'remove',file:f.stored})}catch(e){setError(e.message)}finally{setMaterialBusy(false)}}}>Remove</${NL.Btn}></div>`)}
          ${materialId?html`<button type="button" class="link small" disabled=${materialBusy||active} onClick=${async()=>{
            if(!await NL.confirm({title:'Clear materials and suggestions?',body:'Your typed study details will stay.',ok:'Clear materials'}))return;
            setMaterialBusy(true);try{const r=await NL.api('/api/starter/draft',{action:'discard',id:materialId});if(!r.ok)throw Error(r.error);materialRef.current='';setMaterialId('');setMaterials(null);setApplied(false)}catch(e){setError(e.message)}finally{setMaterialBusy(false)}
          }}>Clear materials & suggestions</button>`:null}
          <details class="more"><summary>Agent help</summary>
            <p class="muted small">Read these materials and suggest details below. Uses your agent account; nothing starts until you ask.</p>
            <${NL.AgentChoice} value=${agent} onChange=${setAgent}/>
            <${NL.Field} label="What help would you like?" hint="Optional. Leave blank to suggest a title, research goal and process."><${NL.Textarea} value=${instructions} onInput=${setInstructions} rows=${2} placeholder="For example: clarify the hypothesis and list open questions."/></${NL.Field}>
            ${!NL.exec(lab).enabled?html`<div class="row"><${NL.Btn} small onClick=${async()=>{const r=await NL.api('/api/executor/enable',{enabled:true,confirm:true});if(r.ok)NL.refresh();else setError(r.error)}}>Enable agent runs</${NL.Btn}><a class="link small" href="#/setup">Agent setup</a></div>`:null}
            <div class="row"><${NL.Btn} onClick=${analyze} busy=${materialBusy} disabled=${active||!NL.exec(lab).enabled||!materials?.files?.length&&!question.trim()&&!title.trim()}>Suggest study details</${NL.Btn}>
              ${materials?.run_id?html`<button type="button" class="link" onClick=${()=>NL.openRun(materials.run_id)}>Open conversation</button>`:null}</div>
            ${active?html`<p role="status" class="muted small">${materials.status==='waiting_input'?'The agent needs your input. Open the conversation.':'Agent working… You can keep editing.'}</p>`:null}
            ${materials?.suggestion_error?html`<p role="status">${materials.suggestion_error}</p>`:null}
            ${materials?.status&&['failed','killed','unavailable'].includes(materials.status)?html`<p role="status">The agent stopped. Open the conversation or try again.</p>`:null}
          </details>
          ${suggestion?html`<section class="study-suggestion"><h3>Suggested details</h3><b>${suggestion.title}</b><p class="suggested-question">${suggestion.question}</p><p class="muted small">${context?.workflows.find(w=>w.id===suggestion.workflow)?.title||'Keep current process'}${suggestion.tags?.length?' · '+suggestion.tags.join(', '):''}</p>
            <details><summary>Full suggestion & notes</summary><p>${suggestion.question}</p>${suggestion.analysis?html`<${NL.Markdown} text=${suggestion.analysis}/>`:null}</details>
            <p class="muted small">${applied?'Applied. Edit the fields below before reviewing.':stale?'Your inputs changed. Ask again for an updated suggestion.':'Review this suggestion before applying it. It will replace the suggested fields below.'}</p>
            <${NL.Btn} disabled=${stale||applied||active} onClick=${applySuggestion}>Apply suggestion</${NL.Btn}></section>`:null}
        </details>
        <${NL.Field} label="Study title"><${NL.Input} value=${title} onInput=${setTitle} placeholder="A short, useful name" /></${NL.Field}>
        <${NL.Field} label="What would you like to investigate?" hint="A research topic, a question, or the first task for this project."><${NL.Textarea} value=${question} onInput=${setQuestion} rows=${4} placeholder="What do you want to understand, test or build on?" /></${NL.Field}>
        <${NL.Field} label="Starting workflow"><${NL.Select} value=${workflow} onChange=${setWorkflow} options=${(context?.workflows || []).map(w => ({ value: w.id, label: w.title }))} /></${NL.Field}>
        <p class="muted small">${flow?.blurb} You can edit this workflow later.</p>
        <details class="more"><summary>Tags & study ID</summary><${NL.Field} label="Tags"><${NL.TagInput} value=${tags} onChange=${setTags}/></${NL.Field}><${NL.Field} label="Folder and study ID"><${NL.Input} value=${sid} onInput=${setId} mono /></${NL.Field}></details>
        <div class="starter-actions"><${NL.Btn} kind="primary" disabled=${!valid || busy||materialBusy} onClick=${() => { setStep(2); setError(''); }}>Review study</${NL.Btn}></div></div>` : null}
      ${step === 2 ? html`<section class="starter-review"><h2 id="study-review-heading" tabIndex="-1">${title}</h2><p class="research-question">${question}</p><dl>
        <dt>Workflow</dt><dd>${flow?.title}</dd>${tags.length?html`<dt>Tags</dt><dd><${NL.Tags} value=${tags}/></dd>`:null}<dt>Study record</dt><dd class="mono">studies/${sid}/IDEA.md</dd>
        ${materials?.files?.length?html`<dt>Materials</dt><dd>${materials.files.map(f=>f.name).join(', ')}</dd>`:null}
        ${machine&&kind!=='topic'?html`<dt>Machine</dt><dd>${machine}</dd>`:null}
        ${kind === 'local' ? html`<dt>Existing folder</dt><dd class="mono path-wrap">${local}</dd>` : kind === 'github' ? html`<dt>Clone from</dt><dd>${resolved?.name}</dd><dt>New working copy</dt><dd class="mono path-wrap">${machine ? local : context?.projects_root+'/'+sid}</dd>` : null}</dl>
        <p class="muted">${kind === 'github' ? 'Saving downloads this repository and adds Lab registration files. It does not install or run its code.' : kind === 'local' ? 'Saving creates the study and adds Lab registration files to this folder. Your code and environment stay unchanged. No agent starts.' : 'Saving creates a study record. No agent starts.'}</p>
        <div class="starter-actions"><${NL.Btn} disabled=${busy} onClick=${() => setStep(1)}>Back</${NL.Btn}><${NL.Btn} kind="primary" busy=${busy} onClick=${save}>${kind === 'github' ? 'Clone & create study' : 'Create study'}</${NL.Btn}></div>
        ${busy && kind === 'github' ? html`<p class="muted" role="status">Cloning repository…</p>` : null}</section>` : null}
      <details class="starter-agent-choices"><summary>Agent choices (optional)</summary><${NL.AgentAssignments} compact value=${agentChoices} onDraft=${setAgentChoices}/></details>
      <p class="starter-help muted small">Connect an agent whenever you are ready. <a class="link" href="#/setup">Agent setup</a> · <a class="link" href="#/workflow">Workflow</a></p>
    </div>`;
  };
})();
