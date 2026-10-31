# Parallel variants

- **Parallel** (independent variants, e.g. several drafts or disjoint improves): up to
  `max_parallel_subagents` at once —
  1. Per variant: `git -C <projects_root>/<slug> worktree add ../<slug>-wt-exp-NNN -b exp-NNN`
     (worktrees are siblings inside the projects root, next to the project repo;
     check_lab.py ignores `-wt-` dirs).
  2. Spawn one `experiment-runner` subagent per variant (model: `agents.runner_model`)
     with: the worktree path, the operator type, the context packet, and the stage
     budget. PILOT-running variants count against the lab's compute share (hard rule 13) —
     check it as the parent before spawning. **Spawn at most as many PILOT-running variants
     as the share leaves room for**; with the default `max_concurrent_runs: 1`, that is one —
     run the rest SMOKE-only in parallel (SMOKE is exempt) or queue them for the next batch.
     Subagents commit in their branch, return a result packet, and never touch shared
     ledgers.
  3. **Merge through the journal, not git merges** (AGENTS.md subagent rule 3) — for each
     packet, in this order:
     - Append its `ledger_draft` to `EXPERIMENT_LOG.md` (keep AND revert both get entries).
     - **Copy `runs/<id>/` dirs + the variant's new `runs/registry.jsonl` lines into the
       main tree — for EVERY packet, keep or revert.** A reverted variant's artifacts are
       evidence too (hard rules 1, 2; `/experiment` step 4: revert the code but keep the
       ledger entry and registry line). Do this *before* removing the worktree — `runs/*` is
       gitignored and `git worktree remove` would delete it permanently.
     - For **kept** variants only, take the code by path — `git -C <projects_root>/<slug>
       checkout exp-NNN -- configs/ src/` (configs + new modules; never a full `git merge`,
       which would conflict/duplicate on the tracked `registry.jsonl`) — then commit
       `exp-NNN: <outcome>`.
     - Then `git worktree remove ../<slug>-wt-exp-NNN` and delete the branch (`-D`).
