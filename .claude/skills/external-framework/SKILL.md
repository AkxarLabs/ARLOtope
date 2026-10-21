---
name: external-framework
description: Run one configured phase of an optional research framework and inspect its evidence.
newts:
  kind: utility
  launchable: false
  title: External research phase
---

Use the framework command supplied in your assigned task. This is a normal Newts task with a
tool, not a new agent harness. Use the selected harness's shell tools; no provider is required.

1. Read `.newts/frameworks.yaml` in the project. If required inputs or the timeout are missing,
   ask the researcher; do not invent a budget, install software, acquire credentials or launch
   the upstream defaults without review. Follow `docs/external-frameworks.md` for configuration.
2. Inspect the command using `--plan`, including its phase, immutable run directory and arguments.
   Launch only the phase assigned to you. Keep all applicable Newts checkpoints.
3. Run the command without `--plan` and wait for it. Never background a second copy. A failed or
   interrupted receipt requires diagnosis and explicit `--retry`; reuse the same run directory.
   Upstream resume support varies. If it refuses recovery, stop and ask; don't delete its state.
4. Read the phase receipt, log and original scientific evidence. The receipt verifies command
   completion and declared outputs, not scientific correctness, novelty or performance gains.
   Inspect manifests, validity, held-out protocols and limitations. Missing evidence is not zero.
5. Publish one concise report with evidence paths. An HTML explanation can be published through
   the normal artifact command. Preserve the original evidence, logs and negative results.
6. Report the assigned task's outcome through Newts only after those checks. Do not run the next
   phase. The workflow owns sequencing, human decisions and independent review.

The moving character represents this phase's supervising task. A configured JSONL activity mapping
can show upstream steps in its run and update its activity. These are observations, never completion
receipts or independently controllable tasks. Internal framework workers are not native Newts
conversations; don't claim messaging or control that isn't exposed.
Stopping the owning run kills native descendants. Remote services/containers have their own
cleanup semantics: verify external cleanup before retrying; Newts does not certify it here.
