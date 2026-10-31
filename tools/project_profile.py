"""Execution-only profile packed as lab_profile.py in the project worker.

No research kernel, registry, approvals or scheduler live here. The controller supplies a run brief.
"""
from pathlib import Path

GUARD = TRACER = Path('/__arlotope_no_controller_hook__')


class WorkerLab:
    def __init__(self, project, config, owner):
        self.hub = Path(project)
        self.bus = self.hub / '.bus' / 'arlotope' / owner
        self.lab = self.bus
        self._prog = config
        self.runs_ledger = self.bus / 'runs.jsonl'

    def prog(self):
        return self._prog

    def bus_of(self, workdir):
        return self.bus

    def source_of(self, workdir):
        return self.hub.name


def begin_run(lab, manifest):
    return None  # The controller admitted this exact task visit before dispatch.


def flag_runs(hub, runs):
    return runs  # Task completion is projected by the owning controller.


def run_env(manifest, env):
    if manifest.get('judge'):
        env['ARLOTOPE_GATE_JUDGE'] = '1'
    env['ARLOTOPE_WORKER_OWNER'] = manifest['remote_owner']
    env['ARLOTOPE_WORKER_RUNTIME'] = manifest['worker_runtime']


def watch_start(lab, manifest, workdir):
    return {}


def definition(lab, manifest):
    return {}   # A project holds no lab definition; the controller watches its own.


def definition_changed(lab, manifest, before):
    return None


def bus_script(hub, level, workdir):
    # The task brief gives the command: python <worker.pyz> control …
    return Path(__file__)


def trace_script(workdir):
    return None  # The existing supervisor traces the native/ACP event stream.


def agent_commands(hub, bus):
    return []
