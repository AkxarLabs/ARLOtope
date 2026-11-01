# In-project method ideation

The one first-class way to ideate **divergent new approaches** *inside* an active project (the
incremental, within-hypothesis generator is `/improve`'s `expand`). Use the [ideation pipeline](../SKILL.md) — generate →
fresh-context critic ensemble → tournament → triage — but **scoped to method approaches**; output is
**candidate approaches, NOT experiments**, and the study stays where it is (report no outcome for it;
only a `/propose` re-entry, which the PI approves like the first proposal, changes the headline). Full
policy in AGENT-GUIDE.md ("In-project method-ideation"); this skill is its **single enforcement point for
the ENABLE flag** `ideation.in_project`: if `false`, the capability is OFF — do not run it; tell the
caller the headline-reopen route must fall back to a **successor hub `/ideate`**.

**Scope & the frozen-set constraint (binds every phase).** Read the project's `PLAN.md`,
`control.yaml`, `decisions.md`, `EXPERIMENT_LOG.md` tail, and `SYSTEM.md` (if present). Every
candidate must hold the **frozen set constant** — problem/task, eval protocol, test split,
seeds policy, budgets are NEVER varied (hard rules 4–6); a candidate that needs to move any is
out of scope here (route to a hub `/ideate` or `/propose` re-entry).

*Optional human pre-step:* `/discuss in-project <slug>` scopes candidate approaches with the PI
(held to the frozen set); its session doc in `studies/<slug>/sessions/` seeds the candidate
framing. Skip silently in autonomous / `/autopilot` runs.

1. **Generate** `ideation.in_project_candidates` mechanism-distinct **approach** candidates — *methods*
   on the same frozen problem: a different mechanism, model family, training objective or
   representation. Ground each in the results digest (the best node and outcome of each line, the
   idea's findings and failures, the reading index, the headline hypothesis verbatim). Each states a
   one-sentence approach, why the results so far make it promising, the cheapest decisive experiment
   under the frozen budgets, and — explicitly — **whether it changes the headline hypothesis**
   (`Headline-change: yes/no`).
2. **Reflect** — fresh-context `ideation-critic` ensemble (`ideation.critics_per_idea`) on each
   candidate; critics receive only the candidate text + the frozen-set description, never your
   enthusiasm.
3. **Tournament & triage** — rank survivors as in the Tournament phase; then route each by the routing
   rule below. Keep all working state in `lab/ideation/<date>-<HHMMSS>-<slug>-inproject-ideation.md`
   (nothing lives only in chat).

**The routing rule (never bypassable):**
- A survivor with **`Headline-change: no`** (a new method still *within* the headline
  hypothesis): hand it to `/improve`'s `expand` to enter PLAN.md with a pre-written promotion
  criterion and run through the normal operators (still inside the frozen set, the budget and
  the study's checkpoints). It does **not** by itself need a new proposal approval.
- A survivor that would **change the headline hypothesis** (`Headline-change: yes`) must
  **re-enter `/propose`** — a mini-proposal: new hypothesis framing + kill-criteria + budget —
  **OR** become a **successor hub idea** (filed with `arlo new` under a fresh slug, the old study
  linked in its triage notes). It **NEVER** enters experiments on a bare PI note; only the `/propose`
  re-entry, approved by the PI, changes the headline. This preserves the `Headline: yes` autonomy
  boundary.

**Approval** (`ideation.in_project_approval`, PI-owned — full rule in AGENT-GUIDE.md):
- **Manual / PI-driven run:** always **the PI's** — queue surviving headline-changing approaches
  for a `/propose` re-entry the PI approves; report and stop, never approve it yourself.
- **Under a campaign the PI approved** with `campaign_auto`: apply `/autopilot`'s check for a
  delegated checkpoint (the campaign's bounds + an overseer `support` pass); within bounds →
  `/propose` → re-plan; outside bounds (or `in_project_approval: pi`) it queues for the PI **and
  emits `tools/lab_bus.py escalate --detail "in-project approach needs PI"`**
  (escalation requests attention, never grants an approval). `campaign_auto` never relaxes manual
  runs, never touches the frozen set, and never approves a checkpoint.

**Caps & cost.** At most `ideation.in_project_rounds` rounds (divergence terminates by config,
not convention); under a loop/campaign the round charges its minutes against the loop's budget
(or the project's iteration budget). Emit `approach_ideate`
(`tools/lab_bus.py emit approach_ideate --idea <slug> --detail "<n candidates → m routed>"`)
and — when a survivor re-plans the project — emit `replan` so a mid-campaign pivot is visible at the hub
(not only at loop exit). Record the round in the project's PLAN.md Re-planning log.
