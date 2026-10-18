# Research discussions

Use `/discuss` to develop research framing with an agent: one focused question at a time, a
recommended answer, then your response. The agent investigates uncertain points between turns
and records the evidence. The session can clarify a direction, target, design or paper before the
next procedure.

This differs from **Add note**, which saves context without starting work, and workspace Q&A,
which saves a separate question/answer record. A discussion can produce a research session document
and seed later work. None of these interactions approves a checkpoint.

## `/discuss <purpose> [target]`

| Purpose | Useful before | Main result |
|---|---|---|
| `direction` | `/ideate` or `/adopt` | Research interests, constraints and a direction |
| `target` | `/compete` | Task, metric, rules, resources and scoring questions |
| `scope` | `/scope` | Candidate approaches and design decisions to settle |
| `in-project` | `/ideate --in-project` | New approach framing within frozen evaluation and budgets |
| `paper` | `/write-paper` | Headline claim, supporting results, positioning and outline |

In a harness, invoke the procedure directly. In the dashboard, a study’s **Talk it through** action
starts the discussion in that study’s scope. Use **Run something else, with options…** when the
procedure needs explicit arguments. This is an agent turn using its configured account.

The research loop logs literature searches and what sources actually support, subject to
`discuss.max_research_minutes`. Unsupported or unread details stay uncertain. Stop when the
important choices are clear or when you choose to end the discussion.

Pre-study sessions go under `lab/ideation/`; study sessions under
`studies/<slug>/sessions/`, using `templates/idea/session.md`. The record includes framing,
questions/answers, research evidence, outcomes and the intended next procedure.

A handoff can seed later work, but does not launch an unattended campaign or silently change frozen
settings. Skip human interviews during an unattended campaign unless the agent stops to request
your input.

## Engineering discussions

`grill-with-docs` combines the reusable `grilling` loop with `domain-modeling` for software
design/refactoring. It writes a glossary in `CONTEXT.md` and decisions in `adr/`, while research
design decisions belong in `studies/<slug>/decisions.md`.

The helpers are vendored from [mattpocock/skills](https://github.com/mattpocock/skills), with local
notices and licences. Their ADR path is adapted to avoid colliding with the rendered `docs/` site.
They are included in generated projects; attached repositories keep their existing setup.

See [skills](skills.md), [notes and workspace Q&A](knowledge.md) and [workflow design](extending.md).
