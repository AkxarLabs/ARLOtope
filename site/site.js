/* The ARLOtope website: the lamp, ARLO's hellos, and the installer tabs. The lab demo is demo.js. */
(function () {
'use strict';
const $ = (sel, root = document) => root.querySelector(sel), $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const store = { get: k => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch {} } };

/* ── the lamp: day or night, as in the dashboard ───────────────────── */
const lampButton = $('.lamp');
const showLamp = () => {
  const night = document.documentElement.dataset.lamp === 'night';
  lampButton.lastElementChild.textContent = night ? 'Light' : 'Dark';
  lampButton.setAttribute('aria-label', night ? 'Switch to light mode' : 'Switch to dark mode');
};
const setLamp = lamp => { document.documentElement.dataset.lamp = lamp; showLamp(); dispatchEvent(new CustomEvent('arlo-lamp', { detail: lamp })); };
lampButton.addEventListener('click', () => { const next = document.documentElement.dataset.lamp === 'night' ? 'day' : 'night'; store.set('arlo-site-lamp', next); setLamp(next); });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => { if (!store.get('arlo-site-lamp')) setLamp(e.matches ? 'night' : 'day'); });
showLamp();

/* ── ARLO: the mark's line drawing without its box (docs/assets/brand/arlotope-wordmark.svg) ── */
const ARLO = `<svg viewBox="12 33 138 101" aria-hidden="true" focusable="false"><g fill="none" stroke="currentColor" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round">
<path class="gill gill-l" d="M47 65C44 55 51 42 45 40C37 37 34 49 36 54C21 44 17 58 27 64L39 72C20 63 14 76 25 82L38 87C18 83 17 98 29 99L43 97"/>
<path class="gill gill-r" d="M114 65C117 55 110 42 116 40C124 37 127 49 125 54C140 44 144 58 134 64L122 72C141 63 147 76 136 82L123 87C143 83 144 98 132 99L118 97"/>
<path class="face" d="M45 73C61 48 100 48 116 73C136 106 111 129 81 129C50 129 25 106 45 73Z"/><path d="M76 109Q81 117 86 109"/></g>
<g class="blink" fill="currentColor"><circle cx="62" cy="99" r="5"/><circle cx="100" cy="99" r="5"/></g></svg>`;
$$('.arlo').forEach(el => { el.innerHTML = ARLO; });

const timers = new WeakMap();
/** ARLO waves and says one line; the bubble goes after a while. Nothing repeats on its own. */
const hello = (arlo, line, ms = 6000) => {
  const bubble = $('.bubble', arlo.parentElement);
  arlo.classList.remove('waving'); void arlo.offsetWidth; arlo.classList.add('waving', 'is-in');
  arlo.parentElement.classList.add('is-in');
  bubble.textContent = line; bubble.classList.add('is-on');
  clearTimeout(timers.get(arlo));
  timers.set(arlo, setTimeout(() => { bubble.classList.remove('is-on'); arlo.classList.remove('waving'); }, ms));
};
const once = (el, fn) => {
  if (!('IntersectionObserver' in window)) return fn();
  const io = new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) { io.disconnect(); fn(); } }, { threshold: .6 });
  io.observe(el);
};

const hero = $('.arlo-narrator'), lines = hero.dataset.say.split('|');
let said = 0;
once(hero.parentElement, () => setTimeout(() => hello(hero, lines[0]), 450));
hero.addEventListener('click', () => hello(hero, lines[said = (said + 1) % lines.length]));
const foot = $('.arlo-foot');
once(foot.parentElement, () => hello(foot, foot.dataset.say, 5000));

/* ── install: tabs (the visitor's platform first) and copy ─────────── */
const tabs = $$('.os-tabs [role=tab]');
const select = tab => tabs.forEach(t => {
  const on = t === tab;
  t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1;
  document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
});
tabs.forEach((t, i) => {
  t.addEventListener('click', () => select(t));
  t.addEventListener('keydown', e => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (step) { const next = tabs[(i + step + tabs.length) % tabs.length]; select(next); next.focus(); }
  });
});
const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
if (!/win/i.test(platform)) select(tabs[1]);

const side = $('.arlo-side');
const copy = async text => {
  try { await navigator.clipboard.writeText(text); return true; } catch {}
  const area = Object.assign(document.createElement('textarea'), { value: text });
  area.setAttribute('readonly', ''); area.style.cssText = 'position:fixed;opacity:0';
  document.body.append(area); area.select();
  let ok = false; try { ok = document.execCommand('copy'); } catch {}
  area.remove(); return ok;
};
$$('.cmd .copy').forEach(button => button.addEventListener('click', async () => {
  const ok = await copy($('code', button.parentElement).textContent.trim());
  button.textContent = ok ? 'Copied' : 'Select it';
  setTimeout(() => { button.textContent = 'Copy'; }, 2000);
  if (!ok) { getSelection().selectAllChildren($('code', button.parentElement)); return; }
  hello(side, side.dataset.say, 4000);
  clearTimeout(timers.get(side.parentElement));
  timers.set(side.parentElement, setTimeout(() => side.parentElement.classList.remove('is-in'), 4200));
}));
})();
