/* Newts' Lab — the Library: every document the lab writes (the lab layer, then one shelf per study
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
    cache.wait = NL.get('/api/library').then(t => { cache.wait = null; if (t && t.ok) { cache.tree = t; cache.at = Date.now(); } return cache.tree || t; });
    return cache.wait;
  };
  NL.useLibTree = () => {
    const [t, setT] = useState(cache.tree);
    useEffect(() => { let on = true; const refresh=()=>NL.loadLibTree(true).then(x=>on&&setT(x)); NL.loadLibTree().then(x => on && setT(x)); window.addEventListener('nl-knowledge',refresh); return () => { on = false; window.removeEventListener('nl-knowledge',refresh); }; }, []);
    return t;
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
  const docHref = d => `#/library/${encodeURIComponent(d.scope)}/${encodeURIComponent(d.slug || '_')}/${d.rel.split('/').map(encodeURIComponent).join('/')}` + (NL.parseRoute().page==='library'&&location.hash.includes('?')?'?'+location.hash.split('?')[1]:'');
  NL.openDoc = (scope, slug, rel) => { location.hash = docHref({ scope, slug, rel }); };

  NL.DocReader = ({ scope, slug, rel, bare, fallback }) => {
    const [d, setD] = useState(null);
    useEffect(() => { let on = true; setD(null); NL.api('/api/libdoc', { scope, slug: slug || null, rel }).then(x => on && setD(x)); return () => { on = false; }; }, [scope, slug, rel]);
    if (!d) return html`<div class="reader"><${NL.Spinner} /></div>`;
    if (!d.ok) return html`<div class="reader">${fallback || html`<${NL.Empty} icon="📄">${d.error}</${NL.Empty}>`}</div>`;
    return html`<article class=${cls('reader', bare && 'bare')}>
      ${bare ? null : html`<header class="reader-head"><div class="crumbs">${scope === 'lab' ? 'The lab' : slug}${scope === 'project' ? ' · project repo' : ''} › <span class="mono">${rel}</span></div>
        <div class="row">${d.mtime ? html`<span class="muted small">updated ${new Date(d.mtime * 1000).toLocaleString()}</span>` : null}<${NL.EditorLink} path=${d.path} /></div></header>`}
      <${NL.RecordActions} study=${scope==='lab'?'':slug} about=${{scope,slug,rel}}/>
      ${d.format==='file'?html`<p><a class="link" href=${d.url} target="_blank" rel="noopener">Open original file ↗</a></p>${d.type==='application/pdf'?html`<iframe class="material-preview" title=${d.title} src=${d.url}></iframe>`:d.type?.startsWith('image/')?html`<img class="material-image" alt=${d.title} src=${d.url}/>`:html`<p class="muted small">Download this file to open it in its own app.</p>`}`:d.format === 'markdown' ? html`<${NL.Markdown} text=${d.text || '(empty)'} sel=${{ scope, slug, rel }} className="md-doc" />` : html`<pre class="plain">${d.text || '(empty)'}</pre>`}
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
  NL.LibraryNav = ({ active }) => {
    const key='nl-archive:'+(NL.getState()?.lab_info?.path||location.origin)+':';
    useEffect(()=>{NL.ls.set(key+active,location.hash)},[active,location.hash]);
    return html`<header class="library-mast"><div><span class="kicker">Research archive</span><h1>Library</h1></div><nav aria-label="Library sections">
      <a href=${active==='outputs'?'#/library':NL.ls.get(key+'outputs','#/library')} aria-current=${active==='outputs'?'page':null}>Outputs</a>
      <a href=${active==='documents'?'#/library?view=documents':NL.ls.get(key+'documents','#/library?view=documents')} aria-current=${active==='documents'?'page':null}>Documents</a>
      <a href=${active==='records'?'#/library?view=records':NL.ls.get(key+'records','#/library?view=records')} aria-current=${active==='records'?'page':null}>Notes & sources</a></nav></header>`;
  };
  NL.LibraryPage = props => props.args?.length>=3||props.query?.view==='documents'
    ?html`<${DocumentLibraryPage} ...${props}/>`:props.query?.view==='records'?html`<${NL.KnowledgePage} ...${props}/>`:html`<${NL.ArtifactsPage} ...${props}/>`;
  const DocumentLibraryPage = ({ args, query }) => {
    const tree = NL.useLibTree();
    const filter=query?.q||'',setFilter=q=>NL.archiveQuery({view:'documents',q});
    const sel = args && args.length >= 3 ? { scope: args[0], slug: args[1] === '_' ? null : args[1], rel: args.slice(2).join('/') } : null;
    const groups = (tree && tree.groups) || [];
    return html`<div class="library-workspace"><${NL.LibraryNav} active="documents"/><div class=${'page page-split document-library'+(sel?' has-selection':'')}>
      <aside class="split-left"><div class="split-head"><h2>Documents</h2>
        <input class="input search" aria-label="Find a document" placeholder="Find a document…" value=${filter} onInput=${e => setFilter(e.target.value)} /></div>
        ${tree ? html`<${Shelf} groups=${groups} sel=${sel} filter=${filter} />` : html`<${NL.Spinner} />`}
        ${tree && filter && !groups.some(g => (g.sections || []).some(sec => sec.docs.some(d => `${g.title} ${NL.docLabel(d.title)} ${d.title} ${d.rel}`.toLowerCase().includes(filter.toLowerCase())))) ? html`<div class="muted small pad">No documents match “${filter}”.</div>` : null}
        <div class="shelf-foot"><button class="link small" onClick=${() => NL.open(NL.DocEditSheet, { which: 'open-questions' })}>Add an open question for the lab</button></div></aside>
      <main class="split-right">${sel ? html`<a class="link documents-back" href=${'#/library?'+NL.qs({view:'documents',q:filter})}>← All documents</a><${NL.DocReader} ...${sel} />` : html`<${NL.Empty} icon="📖" title="Pick a document">Study notes, sources and research records.</${NL.Empty}>`}</main>
    </div></div>`;
  };

  /* PI-authored documents, edited in place (lab/SYSTEM.md, lab/knowledge/OPEN-QUESTIONS.md) */
  NL.DocEditSheet = ({ which, onClose }) => {
    const [d, setD] = useState(null);
    const [text, setText] = useState('');
    const [preview, setPreview] = useState(false);
    useEffect(() => { NL.get(`/api/doc?${NL.qs({ which })}`).then(x => { setD(x); setText(x.text || ''); }); }, [which]);
    const save = async () => { const r = await NL.act('/api/doc/save', { doc: which, text }, 'Saved'); if (r.ok) { cache.at = 0; onClose(); } };
    const title = which === 'system' ? 'This machine (SYSTEM.md)' : 'Open questions';
    const sub = which === 'system' ? 'Agents read this before running anything: hardware, GPUs, quirks, what not to touch.' : '/ideate reads these first. Add the questions you want the lab to chase.';
    return html`<${NL.Sheet} wide title=${title} sub=${sub} onClose=${onClose} footer=${html`<div class="row"><${NL.Seg} value=${preview ? 'p' : 'e'} onChange=${v => setPreview(v === 'p')} options=${[{ value: 'e', label: 'Edit' }, { value: 'p', label: 'Preview' }]} /><span class="grow"></span>
      <${NL.Btn} onClick=${onClose}>Cancel</${NL.Btn}><${NL.Btn} kind="primary" onClick=${save} disabled=${!d}>Save</${NL.Btn}></div>`}>
      ${!d ? html`<${NL.Spinner} />` : preview ? html`<${NL.Markdown} text=${text} className="md-doc" />` : html`<textarea class="input textarea mono editor" value=${text} onInput=${e => setText(e.target.value)}></textarea>`}
    </${NL.Sheet}>`;
  };
})();
