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
| Type scale | dashboard: h1 36 px serif 450, `.lede` 18 px serif, body 14 px | Same faces and weights, scaled for a reading page: h1 `clamp(44px, 5.4vw, 80px)` with -.03em tracking, captions and section titles 28-60 px serif 450, body 16-17 px sans. The dashboard's mono kickers are *not* used above headings (see section 2). |
| Atoms | `ui.css` `.btn .btn-primary .link .facts .x` | Used as-is. Class names the site defines are checked against `ui.css` so none collide (`.stage`, `.step`, `.tabs` and `.ask` did, and were renamed). |
| Wordmark and mark | `docs/assets/brand/arlotope-wordmark.svg` (editable vector, `currentColor`), `dashboard/static/brand/arlotope-mark.png` | The header uses the SVG wordmark inline so it follows `--ink` in both lamps. Favicon is the mark PNG. |
| ARLO | the SVG head in the wordmark (boxed axolotl, six gill loops, two dot eyes, small smile); `branding/arlotope/README.md` (ivory face, pink/lavender/teal gills) | The same line drawing without the box, inlined by `site.js`, with the gills split in two so they can wave. Ink is `currentColor`; the face fill is `--paper`. On hello the gills take a faint pink and teal tint (`#e9a7b8`, `#8ccfc4`, the only colours the site adds; the screenshot frames also use the screenshots' own paper, `#f8f5ee`). |
| ARLO's voice | `dashboard/static/ui/guide.js` ("Meet ARLO", "Show me around") and `docs/ui-copy.md` | Short, plain, first person: "Hi, I'm ARLO. Scroll, and I'll show you around." The tour captions follow the guide's shape: a title and one or two concrete sentences. |
| The lab | `dashboard/static/lab-view.html` + `ui/lab-view.js` + `world3d/*` (three.js) | The demo **is** the dashboard's own lab frame, fed scripted snapshots (§4). |
| Product truth | `docs/assets/current/*` screenshots, README "What you can do", RELEASE_NOTES | Copy comes from the README's points, tightened. Screenshots are the real ones the docs use, cropped to the part worth reading. |

Tone check against `docs/ui-copy.md`: concrete labels, the stored model's words (study, task,
room, checkpoint, Inbox), movement only for real changes of place or activity, no hype adjectives.

## 2. Direction (second revision)

The first version was a stock marketing page: a hero, the lab in a bordered box with a side panel of
controls, six feature cards, a CTA. The owner found it cluttered and the boxed lab toy-like. The
second revision follows the advice that kept recurring in the references below: **open with the most
characteristic thing in the product's world and lay the page out around it**, strip decoration that
does not serve the subject, use one orchestrated moment rather than many small effects, and end with
one contrasting call to action.

* The live lab is the first screen and stays pinned and unframed while the tour scrolls past it,
  centred top to bottom in the right of the screen. It stays put: dragging turns it, but nothing
  moves it off its anchor (see section 4).
* The story is told in plain words with plain project names (*A new idea*, *Reading list*,
  *Better baselines*, *Faster training*, *Results report*), and the first caption after the intro is
  a key to the picture: rooms are the steps of your work, cards are your projects, characters are AI
  agents, the middle is your desk.
* Scrolling *is* the control: no play/pause/next buttons, no beat list, no autoplay timer. Each
  caption, as it reaches mid-screen, changes the lab. Inactive captions fade to 16 % opacity.
* Removed: mono kickers above every heading, `A · B · C` meta strings, arrows on every link,
  identical feature cards, hairline-ruled newspaper sections, the floating Inbox and narration cards.
* Kept, because they are the product's own identity: the paper/slate palette, Newsreader + Instrument
  Sans, the slate-teal primary, ARLO.
* The one contrasting block is the installer: deep teal by day (`--accent-2`), `--paper-2` by night,
  with ARLO looking over its top edge.

References read for this revision (opinion pieces, weighed as such): Evil Martians' study of 100
developer-tool landing pages (hero with the product visual, a bold and a quiet CTA, a full-width
final CTA, alternating screenshot rows for UI-heavy tools); capitalandcompute.net, "How to fix AI
slop in web design, tell by tell" (both waves of tells, including the cream-serif-hairline "second
wave" the first version had fallen into); ice-ice-bear, "Three design principles that strip the AI
smell" (strip everything first, start from references, design for purpose); and the scrollytelling
pattern (a sticky visual with captions scrolling past it, as in Apple's product pages).

## 3. Page structure

1. **Header**: clear over the lab at the top, solid with a hairline once the page moves. Wordmark;
   Docs, GitHub, the lamp toggle (an icon), and **Install** as the one primary button.
2. **The tour** (`.tour`): a sticky, full-height `.pin` holding the lab (`.world`, the right two
   thirds of the screen under the header; on phones, the top half), with nine captions (`.beat`) scrolling on
   the left (on phones, underneath, over a soft fade):
   0. the intro: *"A lab for your agent teams."*, the lede, **Install ARLOtope** and **Read the
      guide**, and ARLO saying hello;
   1. this is your lab (with the key); 2. the characters are your agents; 3. projects move from
   room to room; 4. when an agent needs you, it asks (a mock Inbox item with two real buttons);
   5. you answer, it carries on; 6. big decisions are yours (a mock checkpoint with **Approve**);
   7. approved; 8. results come back.
3. **Three product rows** (`.work`): the Inbox, the workflow editor, a checkpoint with its evidence;
   each a short serif title, two sentences and one docs link, beside a `.showcase`: a tinted panel
   with the component floating on it and running off its bottom edge. The images in `site/shots/`
   are 2x captures of just that component from the dashboard's demo mode (`arlo --demo`), one for
   each lamp; the page shows the one for the current lamp (the other, hidden and lazy, is never
   fetched). To recapture, open the same views in demo mode at 2x: the Inbox sheet, the workflow
   map (`.wf-map-scroll`) and the checkpoint sheet for *Curriculum distillation*.
4. **A statement** (`.statement`): one large serif paragraph naming the agents and tools it works
   with, the names in ink and the rest faint.
5. **Install** (`.install`): the contrasting block: title, Windows / macOS and Linux tabs (the
   visitor's platform first), the one-liner with **Copy**, then a sentence with the install guide,
   releases and source links. ARLO peeks over the top edge and says *"Copied. Paste it into a
   terminal."* after a copy.
6. **Footer**: one line.

### Sketch: desktop

```
+------------------------------------------------------------------------------+
| [#] ARLOtope                                     Docs  GitHub  o  [Install]  |
|                                  /‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾ |
|  A lab for your                 /  The Incubator   The Study    The Lab       |
|  agent teams.                  /     [] []          [] [] *      [] [] *      |
|  Move several research ...    /                                               |
|  [Install ARLOtope] [Guide]  /      (trees)        (ARLO's desk)  The Bench   |
|  (ARLO) Hi, I'm ARLO ...    /                                                 |
|                            /   The Margins     The Archive   The Writing Room |
|                           /   ... the lab runs on past the edges of the page  |
+------------------------------------------------------------------------------+
   scroll: the left column's captions change; the lab stays pinned and acts them out
```

### Sketch: phone (375 px)

```
+--------------------------------+
| [#] ARLOtope        o [Install]|
| /‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\ |  the lab, top half, wider than the screen
|   rooms, characters, cards     |
| \___________________________/ |
| Agents ask; you answer         |  captions scroll up underneath
| Codex is writing ...           |
| +- Codex . Scaling laws note -+|
| | Lead the Results with ...   ||
| | [The scaling law] [Ablation]||
| +-----------------------------+|
+--------------------------------+
```

## 4. The interactive lab

**Reuse, not re-implementation.** The lab is an `<iframe>` of the dashboard's real
`static/lab-view.html`. That page is a *disposable renderer frame*: it never reads lab files, takes
snapshots over `postMessage({labView:1, state, theme, cast, motion, labels})`, and posts back what the
visitor clicked (`inspect-agent` with a screen anchor, `agent-anchor`, `study`, `checkpoint`,
`dismiss-agent`). The dashboard's `app.js` is one host of that protocol; `site/demo.js` is a second,
much smaller one. No world code is copied or forked.

**The story.** The captions live in the HTML. `demo.js` holds what each caption changes in a small
model (six studies, a few runs); the snapshot for caption *n* is the base model with changes 1..n
applied, so scrolling either way is exact. Moving forward one caption plays the change (characters
walk, cards are carried); any other jump redraws it still, so nothing walks backwards. The shipped
default workflow (`static/ui/workflow-default.js`, generated by `arlo docs`) supplies the real rooms,
steps and checkpoints. The active caption is the last one whose heading has passed the reading line
(55 % down the screen; 75 % on phones, below the lab), worked out on every scroll event (nine
rectangles; no observer or animation-frame timing that background tabs would pause).

**Always moving.** Each run in the model has a short cycle of calls (read, search, write, run an
experiment, run a check, plan). Every 2.4 s the page sends the snapshot again with the next call for
some of the agents, staggered so they do not all move at once, and the renderer walks each one to the
furniture for its call (shelves, benches, desks, the whiteboard). This only runs while the lab is on
screen and not under reduced motion.

**Whole at every angle.** The page puts two invisible, equal `data-world-inset` margins (19 % of the
frame's width) inside the frame, the dashboard's own hook for keeping the camera clear of its side
panels, and asks the frame to refit. The camera then fits the lab into the middle of the frame, which
leaves room for it to turn a full circle, and tilt up to the steepest view a drag allows, without
any part leaving the frame.

**A slow turn.** The renderer has an idle turntable, `setSpin(rate)` (`world3d/world.js`), which the
frame takes from the snapshot message's `spin`. The page asks for 0.05 radians a second, about one
turn every two minutes. It only turns the whole-lab view, only while nobody is dragging it or
following an agent, and never under reduced motion. The dashboard does not set it.

**Anchored.** The page adds three things to the frame (same origin): a capturing wheel listener so
the wheel scrolls the page instead of zooming the lab; after any click (a press and release that did
not move), the frame's own "All rooms" control, so a click on a room never leaves the camera inside
it; and `touch-action: pan-y` on the canvas, so a vertical swipe on a phone scrolls the page.
Dragging still turns the lab around its centre. Building this found a dashboard bug, fixed in
`ui/lab-view.js`: "All rooms" reported `onFollow(null)`, which matched any subagent (their
`worker_id` is null), so the camera started following a subagent.

**Interaction.** Clicking a character opens a peek beside it in plain words (who: Claude Code /
Codex / opencode, what it is doing, its task, its project); clicking a study card or a checkpoint lantern shows the
study's step; clicking ARLO at the desk describes the workspace assistant. Escape or the close button
closes it. Answering in step 4 or approving in step 6 records the choice in the page and scrolls to
the next caption, which uses the answer. The frame's own camera bar is hidden; room names
are on when the lab is at least 600 px wide.

**Loading and fallbacks.** The frame loads right after the page's `load` event, since it is the
first screen. Until it reports `ready` the lab area shows a small spinner, then the frame fades in.
Without WebGL, after a frame error, or with data saver on (with a "Load the live lab" button), the
lab area shows the real screenshot for the current lamp, fitted inside the visible part, with a
one-line note; the captions read the same. The frame is told `{active:false}` when the tour is off
screen or the tab is hidden, and the current snapshot is resent when it wakes (it ignores snapshots
while inactive).

**Reduced motion.** With `prefers-reduced-motion: reduce` the frame gets `motion:false` (the
renderer's still mode: no walking or carrying), captions change without fading, ARLO does not move,
its bubbles simply appear, and scrolling is not smoothed.

## 5. ARLO

Two appearances, each triggered once by the visitor, never on a loop:

* **Hello**, under the intro's buttons: ARLO rises, waves its gills and says *"Hi, I'm ARLO. Scroll,
  and I'll show you around."* (the bubble fades after a few seconds). Clicking ARLO waves again with
  the next line. In the lab itself, ARLO is the big character at the PI's desk.
* **Install**: ARLO always looks over the install block's top edge (its chin behind the block);
  after **Copy** it waves and says *"Copied. Paste it into a terminal."*

Bubbles are `role="status"`, so screen readers hear them once; the drawing is `aria-hidden`.

## 6. Light and dark

Default follows `prefers-color-scheme`; the lamp button overrides it and is remembered in
`localStorage` (wrapped in try/catch). An inline script in `<head>` sets `html[data-lamp]` before
first paint. The frame receives `theme` with every snapshot and relights the world; the install
block switches between deep teal and slate.

## 7. Responsive and accessible

Gutter `clamp(16px, 4vw, 48px)`; below 860 px the lab takes the top half and the captions scroll
underneath it as full-width text over a fade. No horizontal scroll at 375 px (checked). One `h1`,
an `h2` per caption and section; a skip link past the tour; every control is a `<button>` or `<a>`;
focus rings are the dashboard's. The captions are ordinary text in reading order, so the tour reads
as a list without the 3D; the iframe has a title.

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
* The docs' `404.html` is also copied to the root, so unknown paths get the docs' not-found page.
* Only two references to the Pages URL exist (README, `properdocs.yml`); the README now links
  the website (root) and the documentation (`/docs/`).
* No Pages setting changes: the source stays “GitHub Actions”.

Why not a separate repo or a `gh-pages` branch: two deploy paths, two copies of the brand, and
the lab frame would have to be vendored by hand. Why not the site under `/home/`: the root is the
first thing people see.

**Why copy at publish time rather than commit copies:** the site's HTML references `static/…`.
`site/pages.py serve` maps `static/` → `dashboard/static/` (only the files the page borrows) and
`docs/` → `build/docs/` if the docs were built, else the raw `docs/` folder (screenshots load;
docs pages need a build) on the fly for a local preview (no build step while editing), and `site/pages.py build` copies the same mapping
into a folder for Pages. The world, tokens and fonts therefore exist once, in the dashboard;
when the dashboard's lab changes, the next deploy picks it up. The lab frame's room scripts are
injected at the `<!-- arlotope:rooms3d -->` marker exactly as `dashboard/serve.py` does.

The site is not part of the product: `install/build-archive.sh` excludes `site/`, and new Labs do
not copy it.

## 9. Files

```
site/
  DESIGN.md     this document
  index.html    the page: content and structure
  site.css      layout and components; reads ui.css tokens, defines none
  site.js       lamp toggle, ARLO (its SVG and hellos), install tabs + copy
  demo.js       the scripted lab story and its host side of the lab-frame protocol
  pages.py      preview server and Pages assembler (stdlib only)
  shots/        2x captures for the product rows, a day and a night file each
```

## 10. Preview and publish

```bash
python site/pages.py serve            # http://127.0.0.1:8000/  (edit and reload; no build)
uv run --with properdocs --with mkdocs-material properdocs build --strict   # optional: docs into build/docs
python site/pages.py build _pages     # the folder the Pages workflow uploads
```
