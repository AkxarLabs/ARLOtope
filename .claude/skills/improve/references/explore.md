## Explore-mode operators (expand / revisit)

These two operators **change the plan itself** rather than extend it, so they are bounded. Other procedures
rely on them. They are available only in **explore** mode — either a PI ran `/improve <slug> [focus] explore`
(the `explore` mode token, default `execute`), or `/research-loop` is sequencing them under a LOOP_BRIEF whose
`Mode: explore`. In `execute` mode only the [ordinary operators](../SKILL.md) run. The manual
`/improve <slug> explore` path honors the same checks as the loop path: the `loop.explore_*` caps
(`explore_max_expansion_rounds`/`…_new_lines_per_round`), the **frozen set**
(eval/test/seeds/budgets/kill-criteria — never touched), and the study's **checkpoints** (work behind one
waits for its approval, within the PI's note), and a `Headline: yes` reopen escalates the same way (below).

5. **expand** (results-grounded frontier expansion) — when the planned table, its ablation
   rows, and the `num_drafts` lines are all exhausted but budget remains. Context packet =
   a **results digest** (each line's best node + metric + one-line outcome from
   `EXPERIMENT_LOG.md`, the hub's `FINDINGS.md`/`FAILURES.md` for this idea, and the
   **headline hypothesis** verbatim from PLAN.md). Propose up to
   `loop.explore_max_new_lines_per_round` lines that the results so far make promising, each on a
   mechanism different from every prior line and each WITHIN the headline hypothesis.
   Each proposed line is appended to PLAN.md tagged `(expand Rn)` **with a pre-written
   promotion criterion** (no criterion → not a valid row), then runs through the four
   operators above like any planned work. Emit `frontier_expand`; then run
   `<hub>/tools/guard.py plan-trace <slug>` — a BLOCKED means a row reads as
   a headline change and must re-enter `/propose`, not sit in PLAN.md.
6. **revisit** (reopen a design decision — "discard a pre-conceived idea") — when artifacts
   satisfy the **`Revisit if:`** trigger (machine form: its **`Revisit predicate:`**, shape-checked
   by `guard.py decisions <slug>`) of a settled decision in the idea's `decisions.md`.
   (A project with no `decisions.md` skips the revisit scan; frontier expansion is the explore
   mechanism there.)
   - **Boundary check first (mechanical):** if that decision is `Headline: yes`, this is the
     escalation boundary — do NOT execute the reopen as an in-place re-plan. Route to divergent
     method-ideation: `/ideate --in-project <slug>` (enabled by `ideation.in_project: true`, who
     approves set by `ideation.in_project_approval` — **if `ideation.in_project: false`, fall back to a
     successor hub `/ideate`**). Its surviving approaches re-enter `/propose` or spawn a successor idea,
     never entering experiments on a bare PI note. In a manual run, stop and write a PI note naming this
     route; under `/research-loop`, queue that PI note **and emit
     `uv run python scripts/lab_bus.py escalate --detail "headline reopen — needs PI"`** so it reaches the
     hub mid-run — or, under a campaign the PI approved, check it against the campaign's bounds + an
     overseer `support` pass, exactly as for a request to approve a delegated checkpoint, then hand off to
     `/ideate --in-project`. A `Headline: no` decision, with the frozen set intact and the budget not
     exceeded, is **autonomous**.
   - **Overseer check** (`oversight.level` ≠ off): before reopening, spawn one `overseer`
     `support` check giving it the `Revisit if:` text + the contradicting run-artifact paths
     only — UNSUPPORTED means the trigger did **not** fire, leave the decision settled.
   - **Action:** append a new `D-NNN` to `decisions.md` referencing the old (the old stays —
     append-only), set the dependent PLAN.md experiment rows to `retired-by-revision` (the
     project continues; their artifacts and ledger entries remain as evidence), record a
     Re-planning-log row, and seed replacement line(s) under the new choice (which then flow
     through the operators above). Emit `decision_revisit` and `replan`.
