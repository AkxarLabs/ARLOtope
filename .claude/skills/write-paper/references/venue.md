# Venue selection

Create `studies/<slug>/paper/` from `templates/paper/`. **Select the venue** from the resolved
`writing.venue` (project `control.yaml` overrides `lab/config.yaml`): for a non-`generic`
venue, copy the **entire** `templates/paper/venues/<venue>/` directory into `studies/<slug>/paper/`
— the official `.sty`/`.bst` are vendored there, so it compiles offline with no fetch. For
`generic`, use the venue-agnostic `templates/paper/main.tex` (`\documentclass{article}`).
Only if the deadline targets a **newer cycle** than the vendored version, refresh the style
file per `templates/paper/venues/README.md` (and if offline, keep the vendored one and queue
a finalize note — **never leave a non-compiling preamble**). Set `page_limit` from
`writing.page_limit` (the venue's typical limit is in that README).
