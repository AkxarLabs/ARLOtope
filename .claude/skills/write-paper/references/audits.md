# Figures and claims re-audit

Run after EVERY reflection round.

**Figures + claims re-audit**: `.claude/skills/make-figures/tools/sync_figures.py <slug> --check` (hub figures still
match their project sources — a regenerated-but-unsynced or hand-edited figure fails), then
`checks/audit_claims.py studies/<slug>/paper --scan-novelty --rel-tol <critique.claim_rel_tol>` (completeness scan —
every numeral in Results/Ablations/Abstract carries a `% CNNN` annotation — plus the per-claim artifact check,
plus a **novelty WARN**: any priority/superiority claim — SOTA / "first to" / "outperforms all" / unprecedented —
with no `\cite` or `% Cnnn/Nnnn` backing gets cited against the closest prior work, a `% Nnnn` lit-review
pointer, or softened *now* — it hard-blocks at `/review-paper` + `/finalize`)
— after EVERY round, not just at the end. Revision is when fabrication happens: phantom
experiments hide in ablation/analysis subsections. Any number the audit can't trace gets
deleted, not defended. Also run the other `audits:` of `workflow/rules.yaml` on `studies/<slug>/paper`
as a **WARN** (they hard-block later at `/review-paper` + `/finalize`) — a headline result thin on
seeds, a dropped ablation, a validation-selected number or an unfilled Analysis-plan line gets fixed
now, not at finalization. Mark load-bearing claims `headline: true` and add
`split: test`/`multi_seed_waiver:` to `claims.yaml` as needed.
