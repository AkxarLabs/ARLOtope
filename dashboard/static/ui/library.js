/* ARLOtope — the Library: every document the lab writes (the lab layer, then one shelf per study
   with its project repo's ledgers), rendered with real typography, tables, code and KaTeX math. The
   same reader is reused by the Study page's Documents tab. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useState, useEffect, useMemo, cls } = NL;

  const cache = { tree: null, at: 0, wait: null };
  NL.invalidateLibrary = () => { cache.tree=null; cache.at=0; };
  NL.loadLibTree = async (force) => {
    if (!force && cache.tree && Date.now() - cache.at < 20000) return cache.tree;
    if (cache.wait) return cache.wait;
    cache.wait = NL.get('/api/library').then(t => { if (t && t.ok) { cache.tree = t; cache.at = Date.now(); } return t; }).finally(() => { cache.wait = null; });
    return cache.wait;
  };
  NL.useLibTree = () => {
    const [tree, setTree] = useState(cache.tree), [error, setError] = useState(''), [attempt, reload] = NL.useReducer(n => n + 1, 0);
    useEffect(() => { let on = true; setError(''); NL.loadLibTree(!!attempt).then(x => { if (on) { if (x.ok) setTree(x); else setError(x.error || 'Could not read documents.'); } }); return () => { on = false; }; }, [attempt]);
    useEffect(() => { window.addEventListener('nl-knowledge', reload); return () => window.removeEventListener('nl-knowledge', reload); }, []);
    return { tree, error, reload };
  };
  /** a readable name from any file name: "EXPERIMENT_LOG.md" → "Experiment log", "lit-review.md" → "Lit review",
   *  "2026-10-01-weekly.md" → "Weekly · 2026-10-01" (generic: no list of known files) */
  NL.docLabel = name => {
    const base = String(name || '').split('/').pop().replace(/\.[A-Za-z0-9]+$/, '');
    const m = base.match(/^(\d{4}-\d{2}-\d{2}(?:[T_-]\d{2}[-:]?\d{2}(?:[-:]?\d{2})?)?)(?:[-_ ]+(.*))?$/);
    const date = m ? m[1] : '', rest = m ? (m[2] || '') : base;
    let words = rest.replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim();
    if (words && words === words.toUpperCase()) words = words.toLowerCase();
    words = words ? words[0].toUpperCase() + words.slice(1) : '';
    return words && date ? `${words} · ${date}` : words || date || base;
  };
  /** a shelf entry: its readable name, with the file name as small secondary text */
  NL.DocName = ({ d }) => {
    const file = String(d.title || d.rel || '').split('/').pop(), label = NL.docLabel(file);
    return html`<span class="doc-name">${label}${label !== file ? html`<small class="doc-file mono">${file}</small>` : null}</span>`;
  };
  const docHref = d => {
    const f=NL.getFocus(),study=['study','project'].includes(d.scope)?d.slug:null,route=NL.parseRoute();
    const query=route.page==='library'&&(route.query.view==='documents'||route.args.length>=3)?{...route.query,study:study||'@lab'}:{view:'documents',study:study||'@lab'};
    if(f.study!==study)for(const key of ['task','agent','child','worker'])delete query[key];
    return NL.focusHref(`library/${encodeURIComponent(d.scope)}/${encodeURIComponent(d.slug || '_')}/${d.rel.split('/').map(encodeURIComponent).join('/')}?`+NL.qs(query),
      study?{...(f.study===study?f:{}),study}:{});
  };
  NL.openDoc = (scope, slug, rel) => { location.hash = docHref({ scope, slug, rel }); };

  NL.DocReader = ({ scope, slug, rel, bare, fallback }) => {
    const key = NL.qs({ scope, slug, rel }), [result, setResult] = useState(null), [attempt, reload] = NL.useReducer(n => n + 1, 0);
    const d = result?.key === key ? result.data : null;
    useEffect(() => { let on = true; setResult(null); NL.api('/api/libdoc', { scope, slug: slug || null, rel }).then(data => on && setResult({ key, data })); return () => { on = false; }; }, [key, attempt]);
    if (!d) return html`<div class="reader"><${NL.Spinner} /></div>`;
    if (!d.ok) return html`<div class="reader"><${NL.LoadState} error=${d.error || 'Could not read this document.'} reload=${reload} />${fallback}</div>`;
    return html`<article class=${cls('reader', bare && 'bare')}>
      ${bare ? null : html`<header class="reader-head"><div class="crumbs">${scope === 'lab' ? 'The lab' : slug}${scope === 'project' ? ' · project repo' : ''} › <span class="mono">${rel}</span></div>
        <div class="row">${d.mtime ? html`<span class="muted small">updated ${NL.when(d.mtime * 1000)}</span>` : null}<${NL.EditorLink} path=${d.path} /></div></header>`}
      <${NL.RecordActions} study=${scope==='lab'?'':slug} about=${{scope,slug,rel}}/>
      ${d.format==='file'?html`<p><a class="link" href=${d.url} target="_blank" rel="noopener">Open original file ↗</a></p>${d.type==='application/pdf'?html`<${NL.FilePreview} kind="pdf" className="material-preview" title=${d.title} url=${d.url} />`:d.type?.startsWith('image/')?html`<${NL.FilePreview} kind="image" className="material-image" title=${d.title} url=${d.url} />`:html`<p class="muted small">Download this file to open it in its own app.</p>`}`:d.format === 'markdown' ? html`<${NL.Markdown} text=${d.text || '(empty)'} sel=${{ scope, slug, rel }} className="md-doc" />` : html`<pre class="plain">${d.text || '(empty)'}</pre>`}
      ${d.clipped ? html`<p class="muted small">… clipped. Open it in your editor for the rest.</p>` : null}</article>`;
  };

  const Shelf = ({ groups, sel, filter }) => {
    const q = (filter || '').toLowerCase();
    return html`<nav class="shelf">${groups.map(g => {
      const secs = g.sections.map(sec => ({ ...sec, docs: sec.docs.filter(d => !q || (NL.docLabel(d.title) + ' ' + d.title + ' ' + d.rel + ' ' + g.title).toLowerCase().includes(q)) })).filter(sec => sec.docs.length);
      if (!secs.length) return null;
      const open = !q && sel ? (sel.slug || null) === (g.slug || null) || (g.kind === 'lab' && sel.scope === 'lab') : true;
      return html`<details class="shelf-group" open=${open || !!q}><summary><span class="clip">${g.title}</span>${g.state ? html`<${NL.StatePill} state=${g.state} />` : null}</summary>
        ${secs.map(sec => html`<div class="shelf-sec"><div class="shelf-sec-h">${sec.icon || ''} ${sec.title}</div>
          ${sec.docs.map(d => {const on=sel&&sel.scope===d.scope&&(sel.slug||null)===(d.slug||null)&&sel.rel===d.rel;return html`<a class=${cls('shelf-doc',on&&'on')} aria-current=${on?'page':null} href=${docHref(d)}><${NL.DocName} d=${d} /></a>`})}</div>`)}</details>`;
    })}</nav>`;
  };

  NL.archiveQuery = patch => {
    const query={...NL.parseRoute().query,...patch};
    history.replaceState(null,'',location.hash.split('?')[0]+'?'+NL.qs(query));
    window.dispatchEvent(new HashChangeEvent('hashchange'));
  };
  NL.LibraryNav = ({ active, study='', studies=[] }) => {
    const lab=NL.useLab(),query=NL.parseRoute().query,scope=active==='records'?(study||'@lab'):study;
    const key='nl-archive:'+(NL.getState()?.lab_info?.path||location.origin)+':';
    useEffect(()=>{NL.ls.set(key+active,location.hash)},[active,location.hash]);
    const target=section=>{
      const saved=NL.ls.get(key+section,'#/library'),[path,search='']=saved.split('?'),filters=Object.fromEntries(new URLSearchParams(search));
      const next=section==='records'?(scope==='@lab'?'':scope):scope;
      const same=(filters.study||'')===next;
      return NL.focusHref((same&&section!==active?path:'#/library')+'?'+NL.qs({...filters,view:section==='outputs'?undefined:section,study:next,record:same&&section!==active?filters.record:undefined}));
    };
    const options=[...(active==='records'?[]:[{value:'',label:'All studies & lab'}]),{value:'@lab',label:'Lab-wide'},
      ...[...new Set([...(lab.items||[]).map(i=>i.id),...studies,scope].filter(id=>id&&id!=='@lab'))].map(id=>({value:id,label:NL.item(lab,id)?.title||id}))];
    const choose=value=>{NL.setFocus(value&&value!=='@lab'?{study:value}:{});NL.go('library?'+NL.qs({...query,view:active==='outputs'?undefined:active,study:active==='records'&&value==='@lab'?'':value,record:undefined,task:undefined,agent:undefined,child:undefined,worker:undefined}))};
    return html`<header class="library-mast"><div><span class="kicker">Research archive</span><h1>Library</h1></div><div class="library-controls">
      <${NL.Select} ariaLabel="Library study" value=${scope} onChange=${choose} options=${options}/><nav aria-label="Library sections">
      <a href=${target('outputs')} aria-current=${active==='outputs'?'page':null}>Outputs</a>
      <a href=${target('documents')} aria-current=${active==='documents'?'page':null}>Documents</a>
      <a href=${target('records')} aria-current=${active==='records'?'page':null}>Notes & sources</a></nav></div></header>`;
  };
  NL.LibraryPage = props => props.args?.length>=3||props.query?.view==='documents'
    ?html`<${DocumentLibraryPage} ...${props}/>`:props.query?.view==='records'?html`<${NL.KnowledgePage} ...${props}/>`:html`<${NL.ArtifactsPage} ...${props}/>`;
  const DocumentLibraryPage = ({ args, query }) => {
    const { tree, error, reload } = NL.useLibTree();
    const filter=query?.q||'',setFilter=q=>NL.archiveQuery({view:'documents',q});
    const sel = args && args.length >= 3 ? { scope: args[0], slug: args[1] === '_' ? null : args[1], rel: args.slice(2).join('/') } : null;
    const study=query?.study||'',allGroups=(tree&&tree.groups)||[],groups=allGroups.filter(g=>!study||(study==='@lab'?g.kind==='lab':g.slug===study));
    return html`<div class="library-workspace"><${NL.LibraryNav} active="documents" study=${study} studies=${allGroups.map(g=>g.slug).filter(Boolean)}/><div class=${'page page-split document-library'+(sel?' has-selection':'')}>
      <aside class="split-left"><div class="split-head"><h2>Documents</h2>
        <input class="input search" aria-label="Find a document" placeholder="Find a document…" value=${filter} onInput=${e => setFilter(e.target.value)} /></div>
        ${!tree || error ? html`<${NL.LoadState} error=${error} reload=${reload} stale=${!!tree} />` : null}
        ${tree ? html`<${Shelf} groups=${groups} sel=${sel} filter=${filter} />` : null}
        ${tree&&!error&&!groups.some(g=>g.sections.some(s=>s.docs.length))?html`<p class="muted small pad">No documents in this scope.</p>`:null}
        ${tree && filter && !groups.some(g => (g.sections || []).some(sec => sec.docs.some(d => `${g.title} ${NL.docLabel(d.title)} ${d.title} ${d.rel}`.toLowerCase().includes(filter.toLowerCase())))) ? html`<div class="muted small pad">No documents match “${filter}”.</div>` : null}
        <div class="shelf-foot"><button class="link small" onClick=${() => NL.open(NL.DocEditSheet, { which: 'open-questions' })}>Add an open question for the lab</button></div></aside>
      <main class="split-right">${sel ? html`<a class="link documents-back" href=${'#/library?'+NL.qs({view:'documents',study,q:filter})}>← All documents</a><${NL.DocReader} ...${sel} />` : html`<${NL.Empty} icon="📖" title="Pick a document">Study notes, sources and research records.</${NL.Empty}>`}</main>
    </div></div>`;
  };

  /* PI-authored documents, edited in place (lab/SYSTEM.md, lab/knowledge/OPEN-QUESTIONS.md) */
  NL.DocEditSheet = ({ which, onClose }) => {
    const { data: d, error, reload } = NL.useGet(`/api/doc?${NL.qs({ which })}`);
    const [edit, setEdit] = NL.useDraft('doc:' + which, null), [preview, setPreview] = useState(false);
    const text = edit ?? d?.text ?? '';
    const save = async () => { const r = await NL.act('/api/doc/save', { doc: which, text }, 'Saved'); if (r.ok) { cache.at = 0; setEdit(null); onClose(); } };
    const title = which === 'system' ? 'This machine (SYSTEM.md)' : 'Open questions';
    const sub = which === 'system' ? 'Agents read this before running anything: hardware, GPUs, quirks, what not to touch.' : '/ideate reads these first. Add the questions you want the lab to chase.';
    return html`<${NL.Sheet} wide title=${title} sub=${sub} onClose=${onClose} footer=${html`<div class="row"><${NL.Seg} value=${preview ? 'p' : 'e'} onChange=${v => setPreview(v === 'p')} options=${[{ value: 'e', label: 'Edit' }, { value: 'p', label: 'Preview' }]} /><span class="grow"></span>
      <${NL.Btn} onClick=${() => { setEdit(null); onClose(); }}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" onClick=${save} disabled=${!d}>Save</${NL.Btn}></div>`}>
      ${!d ? html`<${NL.LoadState} error=${error} reload=${reload} />` : preview ? html`<${NL.Markdown} text=${text} className="md-doc" />` : html`<textarea class="input textarea mono editor" value=${text} onInput=${e => setEdit(e.target.value)}></textarea>`}
    </${NL.Sheet}>`;
  };
})();
