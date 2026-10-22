/* ARLOtope — Artifacts: what agents made for you to look at (tools/artifact.py publish) — plans, reports,
   figures, tables, HTML pages — each rendered in place, with the agent's question when it asked one and your
   reply, which goes back to the run that made it. Also "What it wrote" on a run's sheet: every file the run's
   own transcript says it wrote, openable here (Markdown rendered).

   An HTML artifact is shown in a sandboxed frame (and served with a CSP sandbox), so a page an agent wrote can
   never act as the dashboard. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useRef, cls } = NL;

  const KIND = { md: ['Document', '¶'], html: ['Page', '◫'], image: ['Figure', '◩'], pdf: ['PDF', '▤'], table: ['Table', '▦'], text: ['Text', '≡'], choice: ['Question', '?'] };
  const fileUrl = a => `/api/artifact/file?${NL.qs({ id: a.id })}`;
  NL.artifactsOf = s => (s && s.artifacts) || [];

  /* Full, scoped records are fetched separately from the small live-world snapshot. */
  NL.useArtifactList = (filter={}) => {
    const [attempt,reload]=NL.useReducer(n=>n+1,0);
    const s=NL.useLab(),key=NL.qs(filter),generation=useRef(0);
    const [data,setData]=useState({key,rows:[],next:null,error:'',loading:true,pages:1}),latest=useRef(data);
    latest.current=data;
    const stamp=s.artifact_revision||NL.artifactsOf(s).map(a=>a.id+':'+a.seen+':'+a.answered).join('|');
    const fallback=NL.artifactsOf(s).filter(a=>(!filter.study||(filter.study==='@lab'?!a.study:a.study===filter.study))&&(!filter.run||a.run_id===filter.run)&&(!filter.about||a.about?.run===filter.about));
    useEffect(()=>{const version=++generation.current;
      if(NL.DEMO){setData({key,rows:fallback,next:null,error:'',loading:false,pages:1});return}
      const previous=latest.current,same=previous.key===key,pages=same?previous.pages||1:1;
      setData(same?{...previous,loading:true}:{key,rows:[],next:null,error:'',loading:true,pages:1});
      const refresh=async()=>{let rows=[],next=null,loaded=0;
        do{const r=await NL.get('/api/artifacts?'+key+(next?'&'+NL.qs({before:next}):''));
          if(generation.current!==version)return;
          if(!r.ok){setData(d=>({...d,rows:same?d.rows:fallback,error:r.error||'Could not read results.',loading:false}));return}
          rows.push(...r.artifacts);next=r.next||null;loaded++;
        }while(next&&loaded<pages);
        setData({key,rows,next,error:'',loading:false,pages:loaded});
      };
      const timer=setTimeout(refresh,150);
      return()=>{clearTimeout(timer);generation.current++};
    },[key,stamp,attempt]);
    const loadMore=async()=>{if(data.key!==key||!data.next||data.loading)return;const version=generation.current;
      setData(d=>({...d,loading:true}));const r=await NL.get('/api/artifacts?'+key+'&'+NL.qs({before:data.next}));
      if(generation.current===version)setData(d=>({...d,rows:r.ok?[...d.rows,...r.artifacts]:d.rows,next:r.ok?r.next:d.next,pages:d.pages+(r.ok?1:0),error:r.error||'',loading:false}));
    };
    return {...(data.key === key ? data : {key,rows:fallback,next:null,error:'',loading:true,pages:1}),loadMore,reload};
  };

  const fetchOne = async id => (NL.DEMO && NL.demoArtifact) ? NL.demoArtifact(id) : NL.get(`/api/artifact?${NL.qs({ id })}`);
  const markSeen = ids => { if (ids.length && !NL.DEMO) NL.api('/api/artifact/seen', { ids }); };

  /* the content, by kind */
  const Body = ({ a, d }) => {
    if (a.kind === 'md') return html`<${NL.Markdown} text=${d.text || '(empty)'} className="md-doc" />`;
    if (a.kind === 'text') return html`<pre class="plain">${d.text || '(empty)'}</pre>`;
    if (a.kind === 'image') return html`<figure class="art-fig"><${NL.FilePreview} kind="image" url=${NL.DEMO && d.src ? d.src : fileUrl(a)} title=${a.title} /></figure>`;
    if (a.kind === 'pdf') return html`<${NL.FilePreview} kind="pdf" className="art-frame tall" url=${fileUrl(a)} title=${a.title} />`;
    if (a.kind === 'html') return html`<${NL.FilePreview} kind="html" className="art-frame" url=${fileUrl(a)} srcdoc=${NL.DEMO ? d.html || '' : undefined} title=${a.title} />`;
    if (a.kind === 'table') {
      const rows = (d.table && d.table.rows) || [];
      if (!rows.length) return html`<div class="muted">An empty table.</div>`;
      return html`<div class="art-table"><table><thead><tr>${rows[0].map(c => html`<th>${c}</th>`)}</tr></thead>
        <tbody>${rows.slice(1).map(r => html`<tr>${r.map(c => html`<td>${c}</td>`)}</tr>`)}</tbody></table>
        ${d.table.more ? html`<div class="muted small">… and ${d.table.more} more rows</div>` : null}</div>`;
    }
    return null;
  };

  /* the agent's question, and your answer (it goes back to the run that asked) */
  /** where your reply went, in words: to the run (its next message), or kept as a note when that run had ended */
  NL.replyWhere = r => {
    if (!r) return '';
    if (r.delivered && r.delivered.startsWith('run ')) return `went to ${r.delivered} as its next message`;
    if (r.delivered && r.delivered.startsWith('a note')) return `its run had ended; kept as ${r.delivered.replace('a note to', 'a note for the next agent on')}`;
    if (r.delivered) return 'went to ' + r.delivered;
    return r.delivered_error ? 'not delivered: ' + r.delivered_error : '';
  };
  const Reply = ({ a }) => {
    const [text, setText] = useState('');
    const [pick, setPick] = useState(null);
    const [busy, setBusy] = useState(false);
    const [local, setLocal] = useState(null);
    const r = a.reply || local;
    const choices = a.choices || [];
    if (r) return html`<div class="art-ask done">
      ${a.question ? html`<div class="art-q"><span class="art-q-ico">?</span><b>${a.question}</b></div>` : null}
      ${choices.length ? html`<div class="art-choices">${choices.map(c => html`<span class=${cls('art-choice', c === r.choice ? 'chosen' : 'not')}>${c === r.choice ? '✓ ' : ''}${c}</span>`)}</div>` : null}
      <div class="art-replied"><b>You replied</b>${r.choice ? html` <span class="pill pill-ok">${r.choice}</span>` : null}${r.text ? html` <span>“${r.text}”</span>` : null}
        <small class="muted">${NL.ago(r.ts)} · ${NL.replyWhere(r)}</small></div></div>`;
    const send = async () => {
      if (!pick && !text.trim()) return;
      setBusy(true);
      const x = NL.DEMO && NL.demoReply ? NL.demoReply(a.id, pick, text.trim())
        : await NL.api('/api/artifact/reply', { id: a.id, choice: pick, text: text.trim() });
      setBusy(false);
      if (x && x.ok) { setText(''); setLocal(x.reply); NL.toast('Sent: ' + NL.replyWhere(x.reply), 'ok'); setTimeout(NL.refresh, 300); }
      else NL.toast((x && x.error) || 'That did not work.', 'bad');
    };
    return html`<div class="art-ask">
      ${a.question ? html`<div class="art-q"><span class="art-q-ico">?</span><b>${a.question}</b></div>` : null}
      ${choices.length ? html`<div class="art-choices" role="radiogroup">${choices.map(c => html`<button type="button" role="radio" aria-checked=${pick === c} class=${cls('art-choice', 'pickable', pick === c && 'chosen')} disabled=${busy} onClick=${() => setPick(pick === c ? null : c)}>${pick === c ? '◉ ' : '○ '}${c}</button>`)}</div>` : null}
      <div class="reply"><${NL.Textarea} rows="2" value=${text} onInput=${setText} onSubmit=${send}
        placeholder=${a.question ? (choices.length ? 'Add a note, if you like (Ctrl+Enter sends)' : 'Your answer (Ctrl+Enter)') : 'Instruction for the producing agent (Ctrl+Enter)'} />
        <${NL.Btn} kind="primary" disabled=${busy || (!pick && !text.trim())} onClick=${send}>${a.question?'Send answer':'Send instruction'}</${NL.Btn}></div>
      <small class="muted">${a.run_id ? 'Continues the producing agent, or queues an instruction if it cannot resume.' : 'It is queued as an instruction for this study.'}</small></div>`;
  };

  /** one artifact, whole: where it came from, what it is, what it asks */
  const Viewer = ({ id, onLoaded }) => {
    const [d, setD] = useState(null), [attempt, reload] = NL.useReducer(n => n + 1, 0);
    const s = NL.useLab();
    const recent=NL.artifactsOf(s).find(x=>x.id===id),stamp=recent?recent.answered:s.artifact_revision;
    useEffect(() => { let on = true; setD(null); fetchOne(id).then(x => { if (on) { setD(x); if (x && x.ok) { markSeen([id]); onLoaded && onLoaded(x.artifact); } } }); return () => { on = false; }; }, [id, stamp, attempt]);
    if (!d) return html`<${NL.Spinner} />`;
    if (!d.ok) return html`<${NL.LoadState} error=${d.error || 'Could not open this file.'} reload=${reload} />`;
    const a = d.artifact, it = a.study && NL.item(s, a.study);
    return html`<article class="artifact">
      <header class="art-head"><div class="kicker">${a.about ? 'Explanation' : (KIND[a.kind] || ['Artifact'])[0]} · ${NL.ago(a.created)}</div><h2>${a.title}</h2>
        <div class="row-wrap">${it ? html`<a class="chip" href=${'#/study/' + it.id}>${NL.clip(it.title || it.id, 40)}</a>` : a.study ? html`<span class="chip">${a.study}</span>` : html`<span class="chip">the lab</span>`}
          ${a.run_id ? html`<button type="button" class="chip" title=${a.run_id} onClick=${() => NL.openRun(a.run_id)}>from the run “${a.skill ? NL.procTitle(a.skill) : 'an agent'}” ↗</button>` : null}
          ${a.source_path ? html`<${NL.EditorLink} path=${a.source_path} machine=${a.source_machine}>Open source ↗</${NL.EditorLink}>` : null}
          ${a.file && !NL.DEMO ? html`<a class="link small" href=${fileUrl(a)} target="_blank" rel="noopener">open in a new tab ↗</a>` : null}</div></header>
      ${a.note ? html`<p class="art-note">${a.note}</p>` : null}
      <${NL.RecordActions} study=${a.study} about=${{artifact:a.id}}/>
      ${a.kind !== 'choice' ? html`<div class=${cls('art-body', 'k-' + a.kind)}><${Body} a=${a} d=${d} /></div>` : null}
      <${Reply} a=${a} />
    </article>`;
  };

  NL.ArtifactSheet = ({ id, onClose }) => {
    const [a, setA] = useState(null);
    return html`<${NL.Sheet} title=${a ? a.title : 'Results'} sub=${a ? (KIND[a.kind] || ['Artifact'])[0] + ' an agent made for you' : ''} wide onClose=${onClose}>
      <${Viewer} id=${id} onLoaded=${setA} />
      <div class="row end"><a class="link small" href=${'#/artifacts/' + id} onClick=${onClose}>All results →</a></div></${NL.Sheet}>`;
  };
  NL.openArtifact = id => { if (id) NL.open(NL.ArtifactSheet, { id }, { key: 'artifact:' + id }); };

  /* ── the page: a list on the left (asking first, then new, then the rest), the artifact on the right ── */
  const FILTERS = [['all', 'All'], ['asking', 'Needs a response'], ['new', 'New'], ['explained', 'Explanations'], ['answered', 'Answered']];
  const Row = ({ a, on, s }) => {
    const it = a.study && NL.item(s, a.study);
    const state = a.question && !a.answered ? ['asks', 'warn'] : !a.seen ? ['new', 'info'] : a.answered ? ['answered', 'ok'] : null;
    return html`<a class=${cls('art-row', on && 'on', !a.seen && 'unseen')} aria-current=${on?'page':null} href=${'#/artifacts/' + a.id+(location.hash.includes('?')?'?'+location.hash.split('?')[1]:'')}>
      <span class="art-ico" aria-hidden="true">${a.about ? '✦' : (KIND[a.kind] || ['', '•'])[1]}</span>
      <span class="grow art-row-text"><b title=${a.title}>${a.title}</b><small class="muted">${it ? it.title || it.id : a.study || 'Lab-wide'} · ${NL.ago(a.created)}</small></span>
      ${state ? html`<${NL.Pill} tone=${state[1]}>${state[0]}</${NL.Pill}>` : null}</a>`;
  };
  NL.ArtifactsPage = ({ args, query }) => {
    const s = NL.useLab();
    const f=query?.f||'all',study=query?.study||'',search=query?.q||'';
    const setF=f=>NL.archiveQuery({f}),setSearch=q=>NL.archiveQuery({q});
    const records=NL.useArtifactList({study,f,q:search}),all=records.rows;
    const rank = a => (a.question && !a.answered ? 0 : !a.seen ? 1 : 2);
    const list = all.filter(a => (!study || (study==='@lab'?!a.study:a.study===study)) && (!search||[a.title,a.note,a.study,NL.item(s,a.study)?.title].join(' ').toLowerCase().includes(search.toLowerCase())) && (f === 'all' || (f === 'asking' && a.question && !a.answered) || (f === 'new' && !a.seen) || (f === 'explained' && a.about) || (f === 'answered' && a.answered)))
      .sort((a, b) => rank(a) - rank(b) || String(b.created).localeCompare(String(a.created)));
    const sel = (args && args[0]) || null;
    const studies = [...new Set([...(s.items||[]).map(i=>i.id),...all.map(a => a.study)].filter(Boolean))];
    const summary = () => NL.openAsk('Create a concise visual summary of the recorded work so far. '
      + 'Use an interactive, self-contained HTML page when it helps. Show what changed, evidence links, '
      + 'open questions and next steps. Publish it to Results with tools/artifact.py. '
      + 'Distinguish planned work from verified results; do not invent measurements.', study==='@lab'?'hub':study || 'hub');
    return html`<div class="library-workspace"><${NL.LibraryNav} active="outputs" study=${study} studies=${studies}/><div class=${'page page-split results-page'+(sel?' has-selection':'')}>
      <aside class="split-left"><div class="split-head"><h2>Outputs</h2>
        <${NL.Btn} onClick=${summary}>Ask for a visual summary</${NL.Btn}></div>
        <div class="art-filters">${FILTERS.map(([v, t]) => html`<button type="button" aria-pressed=${f===v} class=${cls('lens', f === v && 'on')} onClick=${() => setF(v)}>${t}</button>`)}</div>
        <div class="result-search"><${NL.Input} ariaLabel="Find a result" value=${search} onInput=${setSearch} placeholder="Find a result…"/></div>
        <nav class="art-list">${list.length ? list.map(a => html`<${Row} key=${a.id} a=${a} on=${a.id === sel} s=${s} />`)
          : html`<div class="muted small pad">${records.loading?html`<${NL.Spinner}/>`:'No matching results.'}</div>`}
          ${records.next?html`<${NL.Btn} small busy=${records.loading} onClick=${records.loadMore}>Load older results</${NL.Btn}>`:null}
          ${records.error?html`<p class="note note-warn" role="alert">${records.error}</p>`:null}</nav></aside>
      <main class="split-right">${sel?html`<a class="link results-back" href=${'#/library?'+NL.qs({f,study,q:search})}>← All outputs</a>${!list.some(a=>a.id===sel)?html`<p class="muted small" role="status">This result is outside the current filter.</p>`:null}<${Viewer} key=${sel} id=${sel} />` : html`<${NL.Empty} icon="❏" title="Select an output">
        Published work appears here and on the room’s board.</${NL.Empty}>`}</main>
    </div></div>`;
  };

  /* ── a run's sheet: what it wrote ─────────────────────────────────────────────────────────────── */
  NL.FileSheet = ({ run, f, onClose }) => {
    const g = NL.useGet(f.kind === 'md' || f.kind === 'text' ? `/api/run/file?${NL.qs({ run_id: run, path: f.path })}` : null), d = g.data || g.previous;
    const raw = `/api/run/rawfile?${NL.qs({ run_id: run, path: f.path })}`;
    return html`<${NL.Sheet} title=${f.name} sub=${html`<span class="mono small">${f.path}</span>`} wide onClose=${onClose}>
      <div class="row end"><a class="link small" href=${raw} target="_blank" rel="noopener">Open original file ↗</a><${NL.EditorLink} path=${f.path} /></div>
      ${f.kind === 'image' ? html`<figure class="art-fig"><${NL.FilePreview} kind="image" url=${raw} title=${f.name} /></figure>`
        : f.kind === 'pdf' ? html`<${NL.FilePreview} kind="pdf" className="art-frame tall" url=${raw} title=${f.name} />`
        : f.kind === 'html' ? html`<${NL.FilePreview} kind="html" className="art-frame" url=${raw} title=${f.name} />`
        : html`${!d || g.error ? html`<${NL.LoadState} ...${g} stale=${!!g.previous} />` : null}
          ${d ? (d.kind === 'md' ? html`<${NL.Markdown} text=${d.text || '(empty)'} className="md-doc" />` : html`<pre class="plain">${d.text}</pre>`) : null}`}
    </${NL.Sheet}>`;
  };
  NL.RunFiles = ({ r }) => {
    const n = r.n_actions || 0;
    const g = NL.useGet(`/api/run/files?${NL.qs({ run_id: r.run_id })}`, Math.floor(n / 5) + ':' + r.status), files = (g.data || g.previous)?.files || [];
    const filesBox=useRef();
    useEffect(()=>{if(g.error && filesBox.current)filesBox.current.open=true},[g.error]);
    const records=NL.useArtifactList({run:r.run_id,f:'outputs'}),arts=records.rows.filter(a=>!a.about);
    if (!files.length && !arts.length && !g.error && !records.error && g.data) return null;
    const ico = k => ({ md: '¶', text: '≡', image: '◩', pdf: '▤', html: '◫' }[k] || '·');
    return html`${arts.length || records.error ? html`<details class="runfiles" open><summary>Shown to you${arts.length ? ' (' + arts.length + ')' : ''}</summary>
      ${records.error ? html`<${NL.LoadState} error=${records.error} reload=${records.reload} stale=${!!arts.length} />` : null}
      ${arts.map(a => html`<button type="button" class="runfile art" onClick=${() => NL.openArtifact(a.id)}><span>${(KIND[a.kind] || ['', '•'])[1]}</span><b class="grow clip">${a.title}</b>${a.question && !a.answered ? html`<${NL.Pill} tone="warn">asks you</${NL.Pill}>` : null}</button>`)}
      ${records.next?html`<${NL.Btn} small busy=${records.loading} onClick=${records.loadMore}>Load older results</${NL.Btn}>`:null}</details>` : null}
      ${files.length || !g.data || g.error ? html`<details class="runfiles" ref=${filesBox}><summary>Files it changed${g.data || g.previous ? ' (' + files.length + ')' : ''}</summary>
      ${g.error || !g.data && !g.previous ? html`<${NL.LoadState} ...${g} stale=${!!g.previous} />` : null}
      ${(files || []).map(f => html`<button type="button" class="runfile" disabled=${!f.exists || f.kind === 'other'} onClick=${() => NL.open(NL.FileSheet, { run: r.run_id, f })}>
        <span>${ico(f.kind)}</span><span class="grow clip mono small">${f.name}</span><span class="muted small clip">${f.exists ? f.path.replace(/\\/g, '/').split('/').slice(-3, -1).join('/') : 'deleted since'}</span></button>`)}</details>` : null}`;
  };
})();
