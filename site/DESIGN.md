# The ARLOtope website — design

The main site for ARLOtope: one page that shows what the dashboard does by *running* it, says hello
through ARLO, and gets people to the installer. It is plain HTML, CSS and JavaScript with no
framework or bundler, and it borrows everything visual from the dashboard instead of inventing a
marketing skin.

## 1. The identity we reuse (inventory)

| What | Source of truth | How the site uses it |
|---|---|---|
| Colour tokens, day and night | `dashboard/static/ui/ui.css` (`:root` shared, `:root, html[data-lamp=night]`, `html[data-lamp=day]`) | Linked directly. The site sets `html[data-lamp]` exactly like the dashboard and only *reads* `--bg --paper --paper-2/3 --edge --edge-2 --ink --ink-soft --ink-faint --accent --accent-2 --accent-ink --accent-wash --warm --ok --bad` and their washes. It defines no colour of its own except the ARLO gill tints (below). |
| Type | `ui.css` `@font-face` + `--serif` / `--sans` / `--mono` | **Newsreader** carries the few big statements (h1, section titles, ARLO's narration in italics), **Instrument Sans** every word of structure, **IBM Plex Mono** kickers, commands, data. Fonts are the dashboard's bundled SIL OFL files; nothing loads from a CDN. |
| Type scale | dashboard: h1 36 px serif 450, `.lede` 18 px serif, `.kicker` 11 px mono uppercase +.09em, body 14 px | Same ratios, scaled up one notch for a reading page: hero h1 `clamp(40px, 6vw, 72px)`, section h2 `clamp(30px, 4vw, 44px)` serif 450 with −.018em tracking, lede 20 px serif, body 16 px sans. |
| Atoms | `ui.css` `.btn .btn-primary .btn-ghost .pill .kicker .kbd` | Used as-is (9 px radius buttons, slate-teal primary, pills). |
| Wordmark and mark | `docs/assets/brand/arlotope-wordmark.svg` (editable vector, `currentColor`), `dashboard/static/brand/arlotope-mark.png` | The header uses the SVG wordmark inline so it follows `--ink` in both lamps. Favicon is the mark PNG. |
| ARLO | the SVG head in the wordmark (boxed axolotl, six gill loops, two dot eyes, small smile); `branding/arlotope/README.md` (ivory face, pink/lavender/teal gills) | ARLO is the same line drawing as a `<symbol>`, with gills split into two groups so they can wave. Ink is `currentColor`; the face fill is `--paper`. On hello, the gills take a faint pink / lavender / teal tint (the only non-token colours: `#e9a7b8`, `#b7a6e0`, `#8ccfc4` at low opacity). |
| ARLO's voice | `dashboard/static/ui/guide.js` (“Meet ARLO”, “Show me around”, numbered stops, a title + one plain sentence + a small hint) and `docs/ui-copy.md` | ARLO narrates the demo in exactly the guide's shape: `ARLO  3 / 8`, a Newsreader title, one sentence of what is happening, a small hint about why it matters. Plain, concrete, never a slogan. |
| The lab | `dashboard/static/lab-view.html` + `ui/lab-view.js` + `world3d/*` (three.js) | The demo **is** the dashboard's own lab frame, fed scripted snapshots (§4). |
| Product truth | `docs/assets/current/*.webp` screenshots, README “What you can do”, RELEASE_NOTES | Feature copy is the README's six points, tightened. Screenshots are the real ones the docs use. |

Tone check against `docs/ui-copy.md`: concrete labels, the stored model's words (study, task,
room, checkpoint, Inbox), movement only for real changes of place or activity, no hype adjectives.

## 2. Moodboard

*A research notebook on a sunny desk, with a toy lab beside it.* Warm paper (`#f8f5ee`) and
near-black ink by day; dark slate (`#181b1d`) and soft ink by night. Editorial serif headlines
like a quiet journal, a precise grotesk for everything you act on, monospace for anything you
could type. Generous white space, hairline `--edge` rules instead of boxes, one slate-teal accent.
The only bright colour on the page comes from the 3D lab itself — the green plots, the room
colours, the little characters — so the eye goes to the thing that is alive. ARLO is a line
drawing that occasionally peeks out of the margin, like a doodle in the notebook, and says one
short thing. No gradients on the chrome, no glassmorphism, no stock illustration, no emoji.

## 3. Page structure and narrative

1. **Header** (sticky, 56 px, hairline under it): wordmark · Lab demo · Features · Install · Docs ·
   GitHub · lamp toggle (`◑ Dark` / `◑ Light`, the dashboard's own control).
2. **Hero.** Kicker `Open source · AGPL-3.0 · Windows, macOS, Linux` (no version number to go stale). Headline (Newsreader):
   *“Visually manage agent teams across your research projects.”* Lede: the README's second
   paragraph, shortened. Buttons: **Install** (primary, jumps to §5) · **Watch the lab** ·
   GitHub. ARLO sits in the hero's right margin, peeks up once and says *“Hi, I'm ARLO.”*
3. **The live lab** (the central object). Full-width stage (16:10 on desktop, 4:5 on phones)
   holding the lab frame; beside it on desktop (below on phones) ARLO's narration card, the
   storyboard (eight numbered beats) and a mock **Inbox** card that mirrors the dashboard's.
   Controls: play/pause, back, next, and the beat list itself is clickable.
4. **What you can do.** Six features, three columns × two rows, each a mono kicker, a sans title,
   two lines, and a “Read more →” to the matching docs page. Below: three real screenshots
   (Inbox, a checkpoint, the workflow editor), lazy-loaded, captioned.
5. **Install.** Two tabs, *Windows (PowerShell)* and *macOS and Linux*, pre-selected from the
   visitor's platform; the one-liner in a mono block with a **Copy** button; “Then run `arlo`.”
   Secondary links: all releases, install guide (where things live, updating, uninstalling),
   from source. ARLO peeks from the edge when you copy: *“Copied. Paste it into a terminal.”*
6. **Footer.** Docs · GitHub · Releases · License (AGPL-3.0-only) · AkxarLabs. A small ARLO
   waves when it scrolls into view: *“See you in the lab.”*

### Sketch A — desktop (≥ 1040 px)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [▢ ARLOtope]        Lab demo  Features  Install  Docs  GitHub      [◑ Dark]  │
├──────────────────────────────────────────────────────────────────────────────┤
│  OPEN SOURCE · AGPL-3.0 · WINDOWS, MACOS, LINUX                               │
│  Visually manage agent teams                                    .-"-.         │
│  across your research projects.                     ╭──────────╮(◕‿◕) ARLO   │
│  Move several projects forward at once…             │Hi, I'm   │ peeks up     │
│  [ Install ]  [ Watch the lab ]  GitHub ↗           │ARLO.     │              │
├───────────────────────────────────────────────┬──────────────────────────────┤
│                                               │ ARLO   3 / 8   ❚❚  ‹  ›      │
│                                               │ A study moves on             │
│        the real 3D lab (lab-view.html)        │ Triage finished. A newt      │
│        rooms · cards · newts walking          │ carries Token routing's card │
│        click a character → peek card          │ to the Study.                │
│                                               │ ─────────────────────────    │
│                                               │ 1 Your lab        ●──        │
│                                               │ 2 Agents at work  ●──        │
│                                               │ 3 A study moves on ◉         │
│                                               │ …                            │
│                                               │ ┌ Inbox · 1 ───────────────┐ │
│                                               │ │ ? Lead Results with…     │ │
│                                               │ │ [The scaling law][Ablat.]│ │
│                                               │ └──────────────────────────┘ │
├───────────────────────────────────────────────┴──────────────────────────────┤
│ WHAT YOU CAN DO   (3 × 2 feature grid)  ·  three screenshots                  │
│ INSTALL  [Windows | macOS and Linux]  irm https://…/install.ps1 | iex  [Copy] │
│ footer                                                    ARLO: See you…      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Sketch B — phone (375 px, 16 px gutters, one column)

```
┌───────────────────────────────────┐
│ [▢ ARLOtope]          [◑]  [≡]    │   nav collapses to a <details> menu
│ OPEN SOURCE · AGPL-3.0            │
│ Visually manage                   │
│ agent teams across                │
│ your research                     │
│ projects.            (◕‿◕)        │   ARLO smaller, bubble above it
│ [ Install ] [Watch the lab]       │
│ ┌───────────────────────────────┐ │
│ │      lab frame, 4:5           │ │
│ └───────────────────────────────┘ │
│ ❚❚ ‹ › ●●◉○○○○○                    │   beats as dots
│ ARLO 3/8 — A study moves on       │
│ Triage finished…                  │
│ ┌ Inbox ────────────────────────┐ │
│ └───────────────────────────────┘ │
│ features stacked · install · foot │
└───────────────────────────────────┘
```

### Sketch C — the install block

```
 INSTALL
 Get ARLOtope running in one line.
 ┌ Windows (PowerShell) │ macOS and Linux ┐
 │ irm https://github.com/AkxarLabs/ARLOtope/releases/latest/download/install.ps1 | iex   [Copy] │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
 Then run arlo, or open the ARLOtope launcher.
 All releases ↗ · Install guide · Work from source
```

## 4. The interactive lab

**Reuse, not re-implementation.** The stage is an `<iframe>` of the dashboard's real
`static/lab-view.html`. That page is already a *disposable renderer frame*: it never reads lab
files, takes snapshots over `postMessage({labView:1, state, theme, cast, motion, labels})`, and
posts back what the visitor clicked (`inspect-agent` with a screen anchor, `agent-anchor`,
`study`, `checkpoint`, `inbox`, `dismiss-agent`). The dashboard's `app.js` is one host of that
protocol; `site/demo.js` is a second, much smaller one. No world code is copied or forked.

**The story** (`site/demo.js`) is eight beats. Each beat has a narration (title, sentence, hint)
and a pure function that changes a small model (six studies, a handful of runs). The snapshot for
beat *n* is rebuilt from the base model by applying beats 1…n, so back/next/jump are exact. The
snapshot uses the shipped default workflow (`static/ui/workflow-default.js`, generated by
`arlo docs`), so the rooms, steps and checkpoints are the real ones.

| # | Beat | What changes in the world | Inbox card |
|---|---|---|---|
| 1 | Your lab | Rooms = workflow steps; six study cards on shelves; ARLO at the desk; one agent reading | empty |
| 2 | Agents at work | Claude Code starts `/experiment` on *Sparse MoE routing*, briefs a subagent who walks to the bench | — |
| 3 | A study moves on | *Token routing* advances Ideas → Study; a newt carries the card; opencode starts `/lit-review` | — |
| 4 | An agent asks you | Codex, writing *Scaling laws note*, pauses with a question marker | the question with two real buttons |
| 5 | You answer | the chosen answer is shown; the agent goes back to editing `main.tex` | answered |
| 6 | Checkpoints wait | *Curriculum distillation* waits at the lantern for **Approve the proposal** | checkpoint with evidence + **Approve** |
| 7 | Approved | the study is carried to the Lab; `/spawn-project` sets up its repo | approved, by you |
| 8 | Results come back | the experiment finishes; a result is published; *Sparse MoE routing* moves to the Bench | an output to read |

Clicking an answer or **Approve** in the Inbox card advances the story with *your* choice;
autoplay uses the first option after the beat's dwell (≈7 s). At the end the stage fades, the
world is reset with motion off (so cards are not carried backwards), and the loop restarts.

**Interaction.** Click a character → a peek card over the stage (who: Claude Code / Codex /
opencode, task, what it is doing, study). Click a study card → its title, step and what is next.
Hover rooms → the renderer's own name tags. The frame's own controls (All rooms, Follow an agent,
Names) stay, since they are the product's. Keyboard: the controls are buttons, the beat list is a
list of buttons, `←`/`→` step when the story has focus, `Space` toggles play.

**Fallbacks and performance.** Above the fold the page costs HTML + CSS + one small script + two
woff2 fonts (target ≤ 150 KB transfer). The frame (three.js ≈ 690 KB raw / ≈ 170 KB gzip, the
world scripts ≈ 170 KB raw) loads only when the stage is within 300 px of the viewport. Until it
is ready — and permanently if WebGL is unavailable, the frame reports an error, or the visitor
saves data (`navigator.connection.saveData`) — the stage shows the real lab screenshot for the
current lamp (`lab-light.webp` / `lab-dark.webp`), and the narration and Inbox card still step
through the story. The frame is paused (`{active:false}`) when the stage scrolls out of view or
the tab is hidden.

**Reduced motion.** With `prefers-reduced-motion: reduce` the frame gets `motion:false` (the
renderer's own still mode: no walking, no carrying), the story does not autoplay (a Play button
starts it), ARLO does not peek or wave — its bubbles simply appear — and smooth scrolling is off.

## 5. ARLO — where and how

Three appearances, each once per page view, each triggered by the visitor (scroll into view or an
action), never on a timer loop:

* **Hero** — peeks up from behind the margin (translateY + 6° tilt, 500 ms), gills wave twice,
  bubble *“Hi, I'm ARLO.”* that fades after 6 s. Clicking ARLO waves again and changes the line
  (*“Want the tour? It's just below.”*).
* **Narrator** — ARLO's head labels the narration card (`ARLO · 3 / 8`), exactly as in the
  dashboard's guide. In the 3D lab, ARLO is also the big newt at the PI's desk.
* **Install** — after **Copy**, ARLO peeks from the code block's edge: *“Copied. Paste it into a
  terminal.”*
* **Footer** — a small ARLO waves once: *“See you in the lab.”*

Bubbles are `role="status"` text so screen readers hear them once; ARLO's SVG is `aria-hidden`.

## 6. Light and dark

Default follows `prefers-color-scheme`; the `◑` toggle overrides it and is remembered in
`localStorage` (wrapped in try/catch). An inline script in `<head>` sets `html[data-lamp]` before
first paint. The lab frame receives `theme` with every snapshot and switches its own lighting; the
poster swaps between the day and night screenshots. The wordmark and ARLO use `currentColor`.

## 7. Responsive and accessible

Container `max-width: 1200px`, side gutter `clamp(16px, 4vw, 36px)` (16 px at 375). Grids use
`minmax(0, 1fr)`; code blocks wrap (`overflow-wrap: anywhere`) rather than scroll the page.
No horizontal page scroll at 375 px. Headings form one outline; skip link; every control is a
`<button>` or `<a>`; focus rings are the dashboard's (`2px solid var(--accent)`); colour contrast
is the dashboard's tokens (AA on both lamps). The iframe has a title and the narration is the
accessible version of the scene (`aria-live="polite"` on the narration only while playing is
avoided — it announces on manual steps only).

## 8. Hosting — the least disruptive option

GitHub Pages currently serves the ProperDocs site at `akxarlabs.github.io/ARLOtope/`.

**Proposal: the website at the Pages root, the docs under `/docs/`, one workflow.**

* `.github/workflows/docs.yml` (renamed in spirit to “pages”, file kept so the Pages setting and
  history stay) builds the docs as today (`--strict`), then runs `python site/pages.py build _pages`,
  which assembles: `site/*` at the root, the dashboard files the lab frame needs under `static/`
  (copied from `dashboard/static/` at publish time — the one source of truth stays in the
  dashboard), and the built docs under `docs/`.
* Old deep links keep working: for every built docs page `X/index.html`, the build writes a tiny
  redirect stub at `X/index.html` in the root pointing to `docs/X/` (meta refresh + canonical).
* `properdocs.yml`: `site_url` gains `/docs/`, and `site_dir` moves from `site/` to `build/docs`
  (the website now owns `site/`; `/build/` is ignored instead).
* Only two references to the Pages URL exist (README, `properdocs.yml`); the README's
  Documentation link moves to `/docs/`.
* No Pages setting changes: the source stays “GitHub Actions”.

Why not a separate repo or a `gh-pages` branch: two deploy paths, two copies of the brand, and
the lab frame would have to be vendored by hand. Why not the site under `/home/`: the root is the
first thing people see.

**Why copy at publish time rather than commit copies:** the site's HTML references `static/…`.
`site/pages.py serve` maps `static/` → `dashboard/static/` and `docs/` → `docs/` on the fly for a
local preview (no build step while editing), and `site/pages.py build` copies the same mapping
into a folder for Pages. The world, tokens and fonts therefore exist once, in the dashboard;
when the dashboard's lab changes, the next deploy picks it up. The lab frame's room scripts are
injected at the `<!-- arlotope:rooms3d -->` marker exactly as `dashboard/serve.py` does.

The site is not part of the product: `install/build-archive.sh` excludes `site/`, and new Labs do
not copy it.

## 9. Files

```
site/
  DESIGN.md     this document
  index.html    the page (content, ARLO symbol, structure)
  site.css      layout and components; reads ui.css tokens, defines none
  site.js       lamp toggle, ARLO hellos, install tabs + copy
  demo.js       the scripted lab story and its host side of the lab-frame protocol
  pages.py      preview server and Pages assembler (stdlib only)
```
