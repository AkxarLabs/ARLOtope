# Studies without a paper

The paper flow of `SKILL.md` does not apply to these; do its step 2 as usual.

**A study without a paper or external target** (for example, Quick study): close the agreed research
deliverables. Read its question, plan and analysis; verify the evidence pointers and reproducibility
steps appropriate to the existing project. Use its own tests and runner; do not require the generated
scaffold or a paper. Record incomplete checks honestly. Paper audits, venue changes, a winning run,
score files and `paper-v1` are N/A. Do step 2, link the actual report and supporting evidence in IDEA.md,
then report `done` only when the agreed checks pass; otherwise report `audit-failed` or `park`.
Do not invent a checkpoint approval, selected run or successful result to close the study.

**Target-driven studies without a paper** (e.g. from `/compete`): the PI chooses the final
output — never automated. The PI's note on the approval that let the study reach this step names the run
(`arlo.py approved <slug> <id>` prints it, with the id from the brief); record
it as `target.final_run_id` in `control.yaml`. If no run is named, ask. Step 1's reproducibility pass is then on the **winning run** (its
`submission`/`metrics.json` regenerable from config + seed), and the paper sub-steps (venue switch, figure
sync, artifact locking, the paper audits, paper-cited run ids) are **N/A** — record the selected run id and
the final `score.json` / `runs/scores.jsonl` line as the deliverable instead. Step 2 is as usual.
