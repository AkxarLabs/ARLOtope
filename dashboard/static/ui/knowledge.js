/* Notes, sources and answers are ordinary files, separate from the document they discuss. */
(function () {
  'use strict';
  const N = window.NL, { html, useState, useEffect, useRef } = N;
  const labels = { document: 'Documents', source: 'Sources', note: 'Notes', answer: 'Answers', output: 'Outputs', log: 'Logs' };
  const recordsHref = (study, filters = {}) => '#/library?' + N.qs({ view: 'records', study: study || '', ...filters });
  const acknowledgement = record => record.acknowledgements?.length ? 'Acknowledged' : 'Acknowledgement requested';

  const Note = ({ study = '', text = '', about, onClose }) => {
    const [value, setValue] = useState(text), [ack, setAck] = useState(true), [tags, setTags] = useState([]);
    const [busy, setBusy] = useState(false), [error, setError] = useState('');
    const save = async () => {
      if (busy || !value.trim()) return;
      setBusy(true); setError('');
      try {
        const result = await N.api('/api/knowledge/note', { study, text: value, about, acknowledge: ack, tags });
        if (!result.ok) { setError(result.error || 'Could not save this note. Your draft is still here.'); return; }
        N.invalidateLibrary(); window.dispatchEvent(new Event('nl-knowledge')); N.toast('Note saved'); onClose();
      } catch (error) { setError(error.message || 'Could not save this note. Your draft is still here.'); }
      finally { setBusy(false); }
    };
    return html`<div class="dialog"><h3>Add note</h3><p class="muted small">${study ? 'Saved with this study.' : 'Saved with the lab.'}</p>
      <${N.Field} label="Note"><${N.Textarea} rows=${5} value=${value} onInput=${setValue}/></${N.Field}>
      <label class="knowledge-ack" title="This records only that an agent read the note. It does not queue work.">
        <input type="checkbox" checked=${ack} onChange=${event => setAck(event.target.checked)}/> Ask an agent to acknowledge
      </label>
      <details class="knowledge-help muted small"><summary>What does acknowledgement mean?</summary>
        <p>An agent can mark the note as read at its next check-in. This does not queue a task, interrupt an agent or request an answer.</p>
      </details>
      <details><summary>Tags</summary><${N.TagInput} value=${tags} onChange=${setTags}/></details>
      ${error ? html`<p role="alert" class="note note-warn">${error}</p>` : null}
      <div class="dialog-actions"><${N.Btn} onClick=${onClose}>Cancel</${N.Btn}>
        <${N.Btn} kind="primary" busy=${busy} disabled=${!value.trim()} onClick=${save}>Save note</${N.Btn}>
      </div></div>`;
  };
  N.openNote = (target, text = '', options = {}) => N.open(Note, { study: target === 'hub' ? '' : target, text, ...options }, { kind: 'dialog' });
  N.RecordActions = ({ study, about }) => html`<div class="row knowledge-actions">
    <button type="button" class="link small" onClick=${() => N.openNote(study || 'hub', '', { about })}>Add note</button>
    <button type="button" class="link small" onClick=${() => N.openAssistant({ initialStudy: study || '', ...(about?.scope ? { initialDocument: about } : { initialReference: about }) })}>Ask workspace assistant</button>
  </div>`;

  N.StudyNotes = ({ study }) => {
    const [revision, refresh] = N.useReducer(n => n + 1, 0);
    const read = N.useGet('/api/knowledge?' + N.qs({ study, kind: 'note' }), revision), data = read.data || read.previous;
    useEffect(() => { window.addEventListener('nl-knowledge', refresh); return () => window.removeEventListener('nl-knowledge', refresh); }, []);
    return html`<section class="study-notes"><header class="row"><h3 class="grow">Notes</h3>
      <button type="button" class="link small" onClick=${() => N.openNote(study)}>Add note</button></header>
      ${!data || read.error ? html`<${N.LoadState} ...${read} stale=${!!read.previous} />` : null}
      ${(data?.rows || []).slice(0, 4).map(record => html`
        <a class="desk-entry" href=${recordsHref(study, { kind: 'note', record: record.id })}><b>${record.title}</b>
          <small>${record.acknowledge ? acknowledgement(record) : 'Human note'}</small></a>`)}
      <a class="link small" href=${recordsHref(study)}>Notes, answers & sources →</a>
    </section>`;
  };

  const Warnings = ({ warnings = [] }) => warnings.length ? html`<div class="note note-warn" role="status">
    <p>Answer delivery needs attention. Saved answers will retry delivery.</p><ul>${warnings.map(warning => html`<li>${warning}</li>`)}</ul>
  </div>` : null;

  const Toolbar = ({ study, kind, search, navigate }) => html`<div class="knowledge-toolbar">
    <${N.Field} label="Kind"><${N.Select} value=${kind} onChange=${value => navigate({ kind: value })}
      options=${[{ value: '', label: 'All records' }, ...Object.entries(labels).map(([value, label]) => ({ value, label }))]}/></${N.Field}>
    <${N.Field} label="Search records"><${N.Input} value=${search} onInput=${value => navigate({ q: value })} placeholder="Search text or tags…"/></${N.Field}>
    <${N.Btn} onClick=${() => N.openNote(study || 'hub')}>Add note</${N.Btn}>
    <${N.Btn} onClick=${() => N.openAssistant({ initialStudy: study, initialScope: true })}>Ask</${N.Btn}>
  </div>`;

  const RecordList = ({ data, loading, error, study, kind, search, selected, loadMore, reload }) => html`<aside class="split-left">
    <p class="muted small">Retained papers, human notes and saved answers. Project files are under Documents.</p>
    ${error ? html`<${N.LoadState} error=${error} reload=${reload} stale=${!!data} />` : null}
    ${!data && loading ? html`<p role="status"><${N.Spinner}/> Loading records…</p>` : data?.rows?.length ? data.rows.map(record => html`
      <a class=${'shelf-doc' + (selected === record.id ? ' on' : '')} aria-current=${selected === record.id ? 'page' : null}
        href=${recordsHref(study, { kind, q: search, record: record.id })}>
        <b>${record.title}</b><small>${labels[record.kind] || record.kind}${record.status ? ' · ' + record.status : ''}${record.acknowledge ? ' · ' + acknowledgement(record).toLowerCase() : ''}</small>
      </a>`) : !error ? html`<p class="muted">${kind || search ? 'No matching records.' : 'No records yet.'}</p>` : null}
    ${data?.next != null ? html`<${N.Btn} small busy=${loading} onClick=${loadMore}>Load more</${N.Btn}>` : null}
  </aside>`;

  const RecordBody = ({ record, study }) => html`<article class="reader"><header>
    <small>${labels[record.kind] || record.kind} · ${record.author || 'Imported'}${record.status ? ' · ' + record.status : ''}</small>
    <h2>${record.title}</h2>
    ${record.run ? html`<button type="button" class="link small" onClick=${() => N.openRun(record.run)}>Open agent conversation</button>` : null}
    ${record.about?.rel ? html`<p><a href=${'#/library/' + encodeURIComponent(record.about.scope) + '/' + encodeURIComponent(record.about.slug || '_') + '/' + record.about.rel.split('/').map(encodeURIComponent).join('/')}>About ${record.about.rel}</a></p>` : null}
    ${record.about?.artifact ? html`<p><a href=${'#/artifacts/' + encodeURIComponent(record.about.artifact)}>About the published output ↗</a></p>` : null}
    ${record.about?.run ? html`<p><button type="button" class="link" onClick=${() => N.openRun(record.about.run,record.about.agent)}>About the source run ↗</button></p>` : null}
    ${record.acknowledge ? html`<p class="muted small">${record.acknowledgements?.length ? 'Acknowledged by ' + record.acknowledgements.map(item => item.run).join(', ') : 'Acknowledgement requested. This note is not a queued task.'}</p>` : null}
    ${record.source?.url && /^https?:\/\//i.test(record.source.url) ? html`<p><a href=${record.source.url} target="_blank" rel="noopener">Open original source ↗</a> · ${record.source.coverage || 'Coverage not recorded'}</p>` : null}
  </header><${N.Markdown} text=${record.text} sel=${{ scope: record.scope, slug: record.slug, rel: record.rel, study, knowledgeId: record.id, attachment: record.attachment }}/>
    <${N.RecordActions} study=${study} about=${{ scope: record.scope, slug: record.slug, rel: record.rel }}/>
  </article>`;

  const RecordReader = ({ selected, state, study, back, retry }) => html`<main class="split-right">
    ${selected ? html`<a class="link documents-back" href=${back}>← All records</a>` : null}
    ${!selected ? html`<${N.Empty} title="Pick a record">Questions and answers are saved separately from their source documents.</${N.Empty}>`
      : state.record ? html`${state.error ? html`<${N.LoadState} error=${state.error} reload=${retry} stale />` : null}<${RecordBody} record=${state.record} study=${study}/>`
      : state.error ? html`<div class="reader"><p role="alert" class="note note-warn">${state.error}</p><${N.Btn} onClick=${retry}>Try again</${N.Btn}></div>`
      : html`<div class="reader" role="status"><${N.Spinner}/> Loading record…</div>`}
  </main>`;

  N.KnowledgePage = ({ query = {} }) => {
    const study = query.study || '', kind = query.kind || '', search = query.q || '', selected = query.record || '';
    const [listing, setListing] = useState({ data: null, loading: true, error: '' });
    const [reader, setReader] = useState({ record: null, error: '' }), [retry, setRetry] = useState(0);
    const listGeneration = useRef(0), listBusy = useRef(false);
    const navigate = patch => N.go('library?' + N.qs({ view: 'records', study, kind, q: search, ...patch }));
    const loadList = async (offset = 0) => {
      if (offset && listBusy.current) return;
      const generation = ++listGeneration.current;
      listBusy.current = true; setListing(old => ({ ...old, loading: true }));
      try {
        const result = await N.get('/api/knowledge?' + N.qs({ study, kind, query: search, offset }));
        if (generation !== listGeneration.current) return;
        if (!result.ok) setListing(old => ({ ...old, loading: false, error: result.error || 'Could not read records.' }));
        else setListing(old => ({ data: offset ? { ...result, rows: [...(old.data?.rows || []), ...result.rows] } : result, loading: false, error: '' }));
      } catch (error) {
        if (generation === listGeneration.current) setListing(old => ({ ...old, loading: false, error: error.message || 'Could not read records.' }));
      } finally { if (generation === listGeneration.current) listBusy.current = false; }
    };
    useEffect(() => {
      listGeneration.current++; listBusy.current = false;
      setListing({ data: null, loading: true, error: '' }); loadList();
      const reload = () => loadList(); window.addEventListener('nl-knowledge', reload);
      return () => { listGeneration.current++; window.removeEventListener('nl-knowledge', reload); };
    }, [study, kind, search]);
    useEffect(() => {
      let active = true, pending = false;
      setReader({ record: null, error: '' });
      if (!selected) return;
      const load = async () => {
        if (pending) return;
        pending = true;
        try {
          const result = await N.get('/api/knowledge?' + N.qs({ study, id: selected }));
          if (active) setReader(old => result.ok ? { record: result.record, error: '' } : { ...old, error: result.error || 'Could not open this record.' });
        } catch (error) { if (active) setReader(old => ({ ...old, error: error.message || 'Could not open this record.' })); }
        finally { pending = false; }
      };
      load(); const timer = setInterval(load, 5000); window.addEventListener('nl-knowledge', load);
      return () => { active = false; clearInterval(timer); window.removeEventListener('nl-knowledge', load); };
    }, [study, selected, retry]);
    return html`<div class="library-workspace"><${N.LibraryNav} active="records" study=${study}/>
      <${Toolbar} study=${study} kind=${kind} search=${search} navigate=${navigate}/>
      <${Warnings} warnings=${listing.data?.warnings}/>
      <div class=${'page page-split document-library' + (selected ? ' has-selection' : '')}>
        <${RecordList} ...${listing} study=${study} kind=${kind} search=${search} selected=${selected} reload=${() => loadList()} loadMore=${() => loadList(listing.data.next)}/>
        <${RecordReader} selected=${selected} state=${reader} study=${study} back=${recordsHref(study, { kind, q: search })} retry=${() => setRetry(value => value + 1)}/>
      </div></div>`;
  };
})();
