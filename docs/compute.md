# Machines and compute

Keep one Lab for studies, workflows and decisions. Attach projects wherever their code and compute
live. Connecting a project machine installs a small runner; opening a separate Lab switches to that
Lab’s independent journal. These are different operations.

## Connect a project machine

Use **+ Machine** in the Lab, or **New study → An existing project → Connect a machine**.
Enter an SSH alias or `user@host`, finish any sign-in prompt, then browse projects.

![Machines and their connection controls](assets/current/machines.webp)

The runner needs OpenSSH, `bash` and Python 3.10+ on a Linux/macOS-style host. Cloning needs Git.
It bundles its Python support; no remote `pip` installation or system service is required.
Choose **Disconnect** to close the project-runner connection. This does not cancel work already
running there. Choose **Forget** only to remove the saved machine entry.

SSH keys, aliases and jump hosts use your SSH configuration. Password, MFA and host-key prompts
use an SSH window on the controller. Keep that window open. **Restart sign-in** replaces a missed
attempt; **Cancel connection** stops it. Provider login is separate and runs on the project machine.
See [remote setup and recovery](remote-projects.md).

**Machines** in the Lab and footer opens machine connections and compute readings.
Its **Separate Labs** controls open or create an independent Lab on a machine. **Keep connected**
refreshes that Lab’s activity on this page while you work elsewhere; it does not merge journals.

## Run a controller over SSH

Start the dashboard on the host:

```bash
uv run --with pyyaml python arlotope.py --background
```

Use the SSH forwarding command it prints, then open the local forwarded address. `--status` and
`--stop` inspect or stop that dashboard. It binds loopback rather than a public interface.
The dashboard must be available to admit new tasks and settle controller requests. Existing run
supervisors are separate processes.

Sign-in and installation use a terminal sheet; on a POSIX host this is a real PTY. Its output passes
through the dashboard. Enter credentials only through the agent’s intended authentication flow.

## Agent slots and experiment jobs

Agent concurrency controls how many agent sessions the executor admits. Training jobs have their
own project budgets and scheduler. One agent can launch a sweep, so an agent-slot limit does not
bound all GPU work.

The default is **7 task sessions across the Lab**, with a separate per-study default of **7**. Change
both in **Settings → Limits & permissions**. Each branch that performs a task uses one slot, whether
local or remote. Independent reviewers, gate judges, explainers and assistants do not use task slots.
Continued task work occupies one slot; a forked task session occupies another. Hub and project tasks
for one study share its limit.

Starting, running and resuming task sessions count. A task chat that keeps its process open for your reply
also counts; a fully parked question without a process releases its slot. Queued and ended tasks,
native child agents inside a harness, and independently opened terminals do not count. Thus the
number of visible characters can exceed the managed-session limit. The cap is not a token budget
or a bound on every child process. Lab-wide task jobs without a study keep their separate default of 1.
Excluded support sessions remain visible and monitored; they still use provider quota and count in
daily usage brakes. Their exclusion does not bypass pauses, gates, time limits or permissions.

`compute.max_concurrent_runs` is the lab-wide limit agents are instructed to respect for PILOT/FULL
campaigns. It is monitored, rather than an automatic GPU reservation system. SMOKE runs are exempt.
Before a substantial run, inspect the Compute instrument or:

```bash
uv run --with pyyaml python arlotope.py panel compute
```

## Scheduler setup

**Settings → This machine & compute** describes the controller’s scheduler. Generated projects can
override `compute.scheduler` in `control.yaml`. The current generated scheduler helper reads the
hub block named by `hub_path`, then overlays the project block; a remote project therefore needs
its execution-machine settings supplied explicitly. An attached repository keeps its existing runner.

```yaml
# Project control.yaml: execution settings for this project
compute:
  scheduler:
    kind: slurm                 # local | slurm | custom
    stages: [PILOT, FULL]
    poll_seconds: 30
    max_queue_hours: 48
    slurm:
      partition: gpu
      account: my-lab
      gpus_per_run: 1
      mem: 32G
      time_grace_minutes: 10
      setup: ["module load cuda", "source .venv/bin/activate"]
```

The generated `scripts/run.py` submits the configured stages and waits for their result.
SMOKE normally runs where launched. The run directory appears immediately with the job ID and queued
state. The job writes the same run artifacts as local execution. Stopping the submitter requests
scheduler cancellation; a vanished unfinished job is recorded as failed.

Queue time does not consume the run’s stage minutes. Slurm’s wall-time request uses
`budget.max_minutes` plus its configured grace. A custom scheduler uses `submit`, `state`,
`cancel`, `header` and `setup` templates in `compute.scheduler.custom`; inspect
`templates/project/scripts/_scheduler.py` before adapting them to a site.

## Budgets and machine instructions

Project `control.yaml` holds stage and total budgets. Runs record their resolved budget in
`meta.json`. The Compute instrument tracks recorded jobs, time and GPU use; available readings
depend on the project records and execution host. It can raise alerts, and may hold a study only
when you allow its alerts to do so. A hold prevents new work; it is not cancellation of existing jobs.

Budgets are research constraints, not a universal spending lock. A local process can exceed its
expected time; a scheduler’s wall-time limit is a separate enforcement mechanism. Agents must not
raise budgets or reduce evaluation to make a run pass.

Put data paths, quotas, scratch rules, environment setup and “never train on the login node” in
`SYSTEM.md`. The dashboard edits the Lab’s `lab/SYSTEM.md`; generated projects receive a copy at
spawn. Keep the project’s machine instructions accurate when execution moves to another host.
See [configuration](configuration.md) and [platform scope](platforms-and-agents.md).
