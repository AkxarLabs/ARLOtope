---
name: gate-review
description: Independently judge declared evidence against a gate's rubric.
arlotope:
  kind: utility
  launchable: false
  title: Review a gate
---

# Review a gate

Read the evidence files and rubric named in your task. Form an independent judgment; do not ask
the author to persuade you or inherit the author's conversation. Check claims against the evidence.
This is a scoped independent review. The owning Lab handles orientation, inboxes and shared ledgers;
do not read earlier verdicts or write session notes outside your result packet.
Choose exactly one of the declared decisions. For each claim you rely on, quote the file and the value
you checked. If required evidence is absent or inconclusive, do not choose a decision that approves
work (take the most conservative declared decision) and explain the deficiency instead.

Write the requested JSON verdict with `decision`, `reason` and `evidence` (the paths you inspected).
Do not move the study, approve checkpoints, change candidate work or start a following task.
The engine validates and applies your verdict. Return the verdict path.
