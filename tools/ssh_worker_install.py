"""Interactive SSH bootstrap: passwords stay in OpenSSH's terminal, package bytes go through stdin."""
import json
import subprocess
import sys
from pathlib import Path


def main():
    spec = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    package = Path(spec['archive']).open('rb') if spec.get('archive') else None
    try:
        proc = subprocess.Popen(spec['argv'], stdin=package, stdout=subprocess.PIPE if spec.get('sessionfile') else None)
        Path(spec['pidfile']).write_text(str(proc.pid), encoding='utf-8')
        if spec.get('sessionfile'):
            for line in proc.stdout:
                try:
                    value = json.loads(line)
                except ValueError:
                    if b'"cookie"' not in line:
                        sys.stdout.buffer.write(line);sys.stdout.buffer.flush()
                    continue
                if isinstance(value, dict) and value.get('newts_worker_session'):
                    from project_worker import private_json
                    private_json(Path(spec['sessionfile']), value)
                elif b'"cookie"' not in line:
                    sys.stdout.buffer.write(line);sys.stdout.buffer.flush()
        return proc.wait()
    finally:
        if package:
            package.close()


if __name__ == '__main__':
    raise SystemExit(main())
