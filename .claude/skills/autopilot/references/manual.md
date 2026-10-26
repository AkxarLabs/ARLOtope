# Campaign started from a session

Use the common rules, Resume and Exit report in [the campaign skill](../SKILL.md).

## Authorize a manual campaign

1. Ask the PI: direction(s); how many ideas to carry; total compute/wall-clock budget; which of
   the workflow's checkpoints the campaign may approve (only those whose `approver` is
   `me-or-campaign`), and the bounds it approves them within. **Project concurrency** is
   `autopilot.max_concurrent_projects` (default **1** — one project carried end-to-end before the
   next). >1 means concurrent multi-project, which **requires** `agents.programmatic.enabled: true`
   (see Concurrent multi-project below); confirm both with the PI and record the chosen value + whether
   programmatic launching is exercised in the brief, so the approval covers it.
2. Fill `templates/loop/CAMPAIGN.md` → `lab/campaigns/<date>-<slug>.md` and present it. The
   brief's "Checkpoints this campaign may approve" section lists the delegated checkpoints; every
   other checkpoint waits for the PI. A delegated checkpoint is approved only by the keeper, on a
   cycle's request, after it re-checks the bounds and runs the checkpoint's checks. The agent never
   widens a bound or claims an approval beyond what the brief covers.
3. The PI approves the brief (the dashboard's campaign form, which records `campaign:<name>`) →
   begin. No approved brief, no campaign.

## 2. The campaign loop (unattended)

**Default — one project end-to-end at a time** (`autopilot.max_concurrent_projects: 1`): carry one
idea fully through the loop below (or to a kill) **before** starting the next. This keeps a single
project's frozen set / budget / ledgers in working memory — aligned with `compute.max_concurrent_runs: 1`
(training is serial regardless). Within that project you still interleave *its own* CPU-light work
around *its* in-flight training (zero-token monitoring, the compute-share rule).

**Concurrent multi-project** (`autopilot.max_concurrent_projects > 1` **and**
`agents.programmatic.enabled: true`): do **not** cram many projects into this one context, and do
**not** hand-background per-project shell commands. The usual way is a campaign started from the
dashboard (its keeper dispatches each project's procedures; see "Under the keeper" in ../SKILL.md).
From a session, this session becomes a **coordinator** and hands each project to the executor as its
own run:

```bash
uv run --with pyyaml python tools/executor_cli.py enqueue --target <slug> --prompt-file <brief>   # one per project; {{slug}} is substituted
uv run --with pyyaml python tools/executor_cli.py list                                            # what is queued / running / waiting
uv run --with pyyaml python tools/executor_cli.py stop --target <slug>                            # stop one project's runs
```

The executor caps concurrency itself (`agents.programmatic.max_concurrent*`), runs each project as a
headless top-level session in its own repo (a detached supervisor with a durable record), and every
run is traced and visible in the dashboard. Training still follows the compute-share rule (hard
rule 13: at most `compute.max_concurrent_runs` training campaigns at once; the Compute panel shows
what is running); CPU-light work runs in parallel across sessions. The coordinator's job is narrow:
enqueue, then monitor each project's Campaign Log / `arlo.py status` / `.bus` for completion or
escalation, and write the unified morning report. Each launched session is **top-level** (it writes
its OWN project ledgers), runs exactly the per-idea loop below, and **stops at every checkpoint
that is not approved** (`needs_pi=<checkpoint id>`); the launch depth is capped so a launched agent
can't launch more. **State the brakes in the prompt-file** — "stop at every unapproved checkpoint
and report `needs_pi`; **never `/finalize`**; escalate via `lab_bus.py` rather than widening
anything". Programmatic launching is **PI-owned and OFF by default**; see `docs/autonomy.md`.

The per-idea loop (run by this session, or by each launched session):

```
per idea:  repeat
             uv run --with pyyaml python arlo.py next <slug>   → the procedure to run
             run that procedure for the study                   → it reports its outcome (arlo move)
           until `next` says the study waits for the PI, is shelved, or has finished
           when it waits at a checkpoint:
               delegated to the campaign → check the evidence against the brief's bounds
                                           (oversight.level ≠ off: an overseer `support` check
                                            confirms "within bounds" first), then ask the keeper:
                                           within bounds → the keeper approves it and starts what follows
                                           outside       → it waits for the PI; take the next idea
               not delegated             → it waits for the PI; take the next idea
```
