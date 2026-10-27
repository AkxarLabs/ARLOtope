# How it fits together

Use one Lab to follow agent teams working on several projects. A **study** holds one research
question, its workflow and its history. It can start without code or attach an existing repository.
Create as many studies as you need, then choose when to launch their tasks. Switching views does
not stop other teams.

## Tasks, skills and agents

| Part | Meaning | Example |
|---|---|---|
| Workflow | Connected tasks and the routes between them | Collect evidence → Check it → Report |
| Task | One assignment with instructions and an expected result | Compare the baseline results |
| Skill | A reusable method a task can use | Evidence review instructions in `SKILL.md` |
| Role | The agent's responsibility | Analyst or independent reviewer |
| Agent choice | The harness and optional model settings | A saved Codex configuration |
| Context | Which conversation the task uses | New, continued or forked |
| Checkpoint | A decision required before proceeding | Review the plan before full runs |
| Room | The shared place where a working agent appears | Analysis |

For example, a collection task and an independent reviewer can share the Study room while using
different agents. A report task can continue the collector's conversation after the review.
Rooms show where work happens; connections determine when it runs. Starting a study creates no room.

## Your workflow, your starting point

Use a supplied workflow, make a copy, or design your own. Tasks can use skills, instructions alone,
or a sequence of skills for one lead agent. Parallel tasks, named outcomes and loops add structure
when needed. No particular research stage is required.

Already have an idea, literature review or draft? The starting plan can reuse that work or skip
unneeded tasks. It uses your workflow's actual task IDs. See
[starting with existing work](agent-workflows.md#start-with-existing-work).

## What is kept

**Study → History** links task passes, agent sessions, recorded exchanges, decisions and outputs.
**Library** brings together project files, retained sources, human notes and saved answers.
Your repository keeps its code, environment and runner. See [project storage](projects.md).

An agent turn ending does not prove the task is complete. Workflow progression needs a recorded
outcome. Checkpoints govern that progression; the harness separately controls native tool permissions.
See [recovery](recovering-work.md) and [approval boundaries](monitoring.md).

Next: [First study](getting-started.md) · [Build a workflow](agent-workflows.md) ·
[Import a skill](skills.md#reuse-a-skill).
