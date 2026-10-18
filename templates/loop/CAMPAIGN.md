# Campaign Brief — {{date}}-{{slug}}

*Approved by the PI in the dashboard (the record `campaign:{{date}}-{{slug}}` in the lab's journal). Everything
above the Campaign Log is FROZEN once approved.*

## Direction & targets

- **Research direction(s):** <!-- from the PI -->
- **Target:** carry up to ___ ideas end-to-end
- **Parallelism:** ≤ ___ ideas in flight

## Checkpoints this campaign may approve

<!-- the PI's choice on the campaign form; nothing else is delegated -->
- none — every checkpoint waits for the PI

A cycle asks the executor's keeper to approve one of these only when ALL of these hold (have the overseer check
the evidence first):
- Budget: ___ in total; each study's full-scale runs within ___
- Kill criteria, the frozen evaluation and a held-out test are present
- The novelty verdict from /lit-review is `novel` (not `incremental`)
- Scoping's value re-verification passed with ≤ ___ open questions

The keeper re-checks every request (the PI still approves this campaign, the checkpoint is delegated to it, the
study is a member and not held, no escalation is open) and runs the checkpoint's own checks; only then is the
approval recorded, as this campaign's. Anything else queues for the PI and the campaign moves to the next idea.

**Loop mode for spawned projects:** `execute` <!-- execute | explore -->. In `explore`,
each project's loop may autonomously expand the frontier and reopen NON-headline design
decisions within its budget (caps: ___ expansion rounds, ___ new lines/round → written into
each LOOP_BRIEF). Reopening a project's **headline** decision, touching the frozen set, or
exceeding the budget is checked against these bounds + an overseer `support` pass; out of
bounds → queue for the PI. Never silent.

## What is NEVER delegated

- Sending anything outside the lab (arXiv, a submission, email).
- Changes to frozen settings; budgets beyond these bounds; resurrection of killed ideas.

## Campaign budget & stop conditions

- **Total wall-clock:** ___ (e.g. "tonight, 8h") · **Total compute:** ___
- Stops when: budget exhausted · all target ideas reach their workflow's last checkpoint / killed ·
  `loop.no_progress_backoff_cycles` applied campaign-wide · environment failure.
- **Campaign cycle / progress (so the backoff is measurable):** one campaign cycle = one
  `/autopilot continue` (re-)entry, i.e. one full portfolio pass. *Progress* in that cycle =
  any idea moved to a new step, OR any project loop logged `progress=yes`, OR an idea
  was killed (a kill is knowledge, not a stall). `loop.no_progress_backoff_cycles`
  consecutive cycles with none of those → stop with a written diagnosis.

## Campaign Log (append-only)

| time | idea | step | outcome / route | progress? | note |
|---|---|---|---|---|---|
