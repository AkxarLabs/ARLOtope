# Research workflow limits

Lab organizes research, agent sessions, evidence and decisions. Its records help you inspect work;
they do not establish that an agent's interpretation is scientifically correct.

## Choose the right starting process

**Research paper** includes literature review, proposal, experiments, analysis, writing and review.
**Quick study** omits the paper/review stages and has no default workflow checkpoints. **Target-driven**
works toward a defined target with explicit external-scoring and final-output decisions. All remain
subject to the Lab's research protocol. A quick workflow does not silently authorize outward actions.

Quick study still begins with idea triage; replication is judged against its purpose rather than
novelty alone. For routine repository inspection or a small replication, use a direct instruction
or adapt the process. The default research workflow is more structured than such tasks require.

Attach an existing repository without adopting the generated project scaffold. Its starter question
can be a small inspection or replication task. Later, add a structured experiment/paper contract when
requested. Choosing a workflow or creating a study does not run code, approve a proposal or verify
existing results. At setup, an attached repository is reused rather than replaced by the scaffolder.
Non-paper studies close their agreed deliverables without requiring competition scores or paper files.

## Evidence needs more than a completed run

A completed agent conversation means its execution ended successfully. An assigned workflow task
can still be **Task unfinished** until the kernel accepts its outcome. Neither status marks a
hypothesis confirmed or an experiment valid. Review declared outputs, experiment records and provenance before
advancing. Failed, null and exploratory results should remain visible. Plans and suggested next steps
must not be presented as measured findings in a visual summary.

Human approvals control recorded transitions and supported launches. Mid-task actions also depend
on the agent following the procedure and its harness permissions. Tool hooks and watches are useful
checks, not a general-purpose security boundary. Native and ACP agents have different capabilities.

## Remote execution and paper audits

Remote projects support execution, conversations, scoped outcomes, output checks, text previews and
published summaries. The main Lab does not automatically mirror datasets or all run artifacts.
Existing paper audits and analysis tools often expect a locally readable project tree. Before those
stages, provide an explicit local evidence export or a compatible local checkout and verify its
provenance. Do not claim a remote paper audit passed because its agent run completed. A unified remote
artifact reader for all scientific audits remains an improvement to make.

## Methodology-specific verification

Methodology cards describe empirical, simulation, theory, ML and target-driven projects. Some paper
audits still encode an ML-shaped seed/metric contract. A deterministic proof or empirical robustness
check is not automatically converted into that contract by choosing a type. Use explicit evidence and
the existing manual-review/waiver path where applicable; do not fabricate seeds to satisfy a check.
Typed verification contracts would make this distinction clearer.

## Reviews, context and stopping

An independent review requires a separate context with evidence paths, not just a new role prompt.
A native fork inherits prior conversation and is not a fresh independent review. Use a new session
with evidence paths and the author summary off. Where native continuation is unavailable, a portable
handoff can support ordinary follow-up work. A reviewer's request for new evidence goes back to the experiment plan; it does not authorize invented
results or a changed evaluation set. Unattended loops need clear budgets, promotion criteria and stop
conditions, including an inconclusive outcome. Literature lookup and reproducibility checks still
need real source and environment verification.

See [Recovering interrupted work](recovering-work.md) for the implemented separation between a turn
ending, a workflow task finishing and a scientific finding being verified. Usage limits and process
failures preserve partial work; recovery still needs an agent or researcher to inspect it before
repeating actions.

Remaining improvements are a shared evidence reader for remote scientific audits and methodology-aware
proof/robustness checks. These should extend the existing file contracts rather than add another
workflow engine.
