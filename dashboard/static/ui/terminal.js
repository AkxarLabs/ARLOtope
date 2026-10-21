/* Newts' Lab — the in-browser terminal: a CLI's own sign-in, an installer, or a shell, running on the
   machine the lab lives on (remote or headless included). xterm.js is loaded only when one opens. The
   server picks the command from a fixed table (dashboard/term.py); the page never sends a command line. */
(function () {
  'use strict';
  const NL = window.NL;
  const { html, useEffect, useRef, useState } = NL;

  let loading = null;
  function loadXterm() {
    if (window.Terminal && window.FitAddon) return Promise.resolve();
    if (loading) return loading;
    const css = document.createElement('link');
    css.rel = 'stylesheet'; css.href = 'static/vendor/xterm/xterm.css';
    document.head.appendChild(css);
    const js = src => new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
    loading = js('static/vendor/xterm/xterm.js').then(() => js('static/vendor/xterm/addon-fit.js'))
      .catch(e => { loading = null; throw e; });
    return loading;
  }
  const b64 = s => { const bin = atob(s); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; };

  NL.TerminalSheet = ({ purpose, backend, machine, onClose }) => {
    const host = useRef();
    const [info, setInfo] = useState(null);
    const [err, setErr] = useState(null);
    const [controlError, setControlError] = useState(null);
    const [done, setDone] = useState(false);
    const [attempt, setAttempt] = useState(0);
    const retry = useRef();
    const request = NL.useMemo(() => crypto.randomUUID().replaceAll('-', ''), [purpose, backend, machine]);
    useEffect(() => {
      let alive = true, term = null, fit = null, id = null, offset = 0, timer = null, ro = null;
      setInfo(null); setErr(null); setControlError(null); setDone(false);
      retry.current = () => setAttempt(n => n + 1);
      (async () => {
        try { await loadXterm(); } catch (e) { if (alive) setErr('Could not load the terminal.'); return; }
        if (!alive) return;
        const dark = document.documentElement.dataset.lamp !== 'day';
        term = new window.Terminal({ cursorBlink: true, convertEol: false, fontFamily: getComputedStyle(document.body).getPropertyValue('--mono') || 'monospace', fontSize: 13,
          theme: dark ? { background: '#081a1f', foreground: '#dcf3ed', cursor: '#5ff0d8', selectionBackground: '#1b3f48' } : { background: '#fbf6ea', foreground: '#33251a', cursor: '#2d8a7c', selectionBackground: '#eadab4' } });
        fit = new window.FitAddon.FitAddon();
        term.loadAddon(fit);
        term.open(host.current);
        try { fit.fit(); } catch (e) { /* hidden */ }
        const command=(operation,body)=>NL.api(machine?'/api/project-machines/terminal':'/api/term/'+operation,{...body,...(machine?{machine,operation}:{})});
        const r = await command('open', { purpose, backend, request_id: request, cols: term.cols, rows: term.rows });
        if (!alive) {if(r.ok)await command('close',{id:r.id});return;}
        if (!r.ok) { setErr(r.error || 'Could not start it.'); return; }
        id = r.id; setInfo(r);
        term.focus();
        term.onData(async d => {
          const x = await command('write', { id, data: d });
          if (alive && !x.ok) {
            term.options.disableStdin = true;
            setControlError({text:'Input may not have arrived. Check the output before typing it again.',
              resume:() => { term.options.disableStdin = false; setControlError(null); term.focus(); }});
          }
        });
        term.onResize(async ({ cols, rows }) => {
          const x = await command('resize', { id, cols, rows });
          if (alive && !x.ok) {
            const problem = {text:'Could not resize the terminal.', label:'Retry resize',
              resume:async () => { const r = await command('resize', { id, cols, rows });
                if (alive && r.ok) setControlError(current => current === problem ? null : current); }};
            setControlError(previous => previous || problem);
          }
        });
        ro = new ResizeObserver(() => { try { fit.fit(); } catch (e) { /* ignore */ } });
        ro.observe(host.current);
        let reading = false;
        const poll = async () => {
          if (!alive || reading) return;
          clearTimeout(timer); reading = true;
          const x = machine ? await command('read',{id,offset}) : await NL.get(`/api/term/read?${NL.qs({ id, offset })}`);
          reading = false;
          if (!alive) return;
          if (x.ok) {
            if (x.skipped) term.writeln('\r\n[Earlier output is no longer available.]');
            if (x.data) term.write(b64(x.data));
            offset = x.offset;
            if (x.exited) { setDone(true); NL.refresh(); return; }
          } else {
            setErr(x.error || 'Could not read terminal output.');
            retry.current = () => { setErr(null); poll(); };
            return;
          }
          timer = setTimeout(poll, x.data ? 60 : 200);
        };
        poll();
      })();
      return () => { alive = false; clearTimeout(timer); ro && ro.disconnect(); if (id) NL.api(machine?'/api/project-machines/terminal':'/api/term/close', { id,...(machine?{machine,operation:'close'}:{}) }); term && term.dispose(); };
    }, [purpose, backend, machine, attempt]);
    const title = (info && info.title) || ({ login: `Sign in to ${backend}`, install: `Install ${backend}`, shell: 'Terminal' }[purpose]);
    const s = NL.getState() || {};
    const where = machine ? `on ${machine}` : s.remote ? `on ${s.remote.name || s.remote.host}` : 'on this machine';
    return html`<${NL.Sheet} wide title=${title} onClose=${onClose}
      sub=${html`<span class="row-wrap"><span>Running ${where}</span>${info ? html`<span class="mono small muted">${info.command}</span>` : null}${done ? html`<${NL.Pill} tone="ok">finished</${NL.Pill}>` : null}</span>`}
      footer=${html`<div class="row"><span class="muted small">${purpose === 'login' ? 'Type into the terminal as you would in any shell. Credentials go to the CLI only; this page never stores them.' : 'Everything typed here goes to this process only.'}</span><span class="grow"></span>
        <${NL.Btn} onClick=${onClose}>${done ? 'Close' : 'Close (stops it)'}</${NL.Btn}></div>`}>
      ${err ? html`<div class="note note-warn" role="alert">${err} <${NL.Btn} small onClick=${() => retry.current?.()}>${info ? 'Retry' : 'Try starting again'}</${NL.Btn}></div>` : null}
      ${controlError ? html`<div class="note note-warn" role="alert">${controlError.text} <${NL.Btn} small onClick=${controlError.resume}>${controlError.label || 'Continue input'}</${NL.Btn}></div>` : null}
      <div class="xterm-host" ref=${host}></div></${NL.Sheet}>`;
  };
  NL.openTerminal = (purpose, backend) => NL.open(NL.TerminalSheet, { purpose, backend }, { key: 'term:' + purpose + ':' + (backend || '') });

  /** Sign in / install / shell: a window on this machine's desktop when there is one (and the lab is
      local); otherwise — a remote lab, or a machine with no desktop — the in-browser terminal. */
  NL.runOnLabMachine = async (purpose, backend) => {
    const s = NL.getState() || {};
    const li = s.lab_info || {};
    const inBrowser = !!s.remote || li.desktop === false;
    if (!inBrowser) {
      const r = await NL.act('/api/terminal', { purpose, backend });
      return r.ok ? 'window' : null;
    }
    NL.openTerminal(purpose, backend);
    return 'browser';
  };
})();
