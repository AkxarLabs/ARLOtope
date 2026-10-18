"""Task-scoped requests to the owning Lab; the project worker never grants an approval."""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path


def control(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('verb', choices=('status', 'next', 'approved', 'move', 'emit'))
    parser.add_argument('values', nargs='*')
    parser.add_argument('--note', default='')
    parser.add_argument('--detail', default='')
    parser.add_argument('--data', action='append', default=[])
    parser.add_argument('--hub', help=argparse.SUPPRESS)
    parser.add_argument('--json', action='store_true', help=argparse.SUPPRESS)
    args = vars(parser.parse_args(argv))
    args.pop('hub')
    args.pop('json')
    try:
        result = request(args)
    except TimeoutError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(result.get('text') or json.dumps(result.get('result', {})))
    return int(result.get('code', 0))


def request(payload):
    """One durable request; callers keep the same record pending across a connection outage."""
    if os.environ.get('NEWTS_GATE_JUDGE') and payload.get('verb') == 'move':
        return {'code': 1, 'text': 'Return the gate verdict. Only the engine applies its decision.'}
    folder = Path(os.environ['NEWTS_RUN_DIR'])
    request_id = uuid.uuid4().hex
    queue = folder / 'controller'
    queue.mkdir(exist_ok=True)
    record = {'id': request_id, 'run_id': os.environ['NEWTS_RUN_ID'], **payload}
    temp = queue / (request_id + '.tmp')
    temp.write_text(json.dumps(record), encoding='utf-8')
    temp.replace(queue / (request_id + '.request.json'))
    response = queue / (request_id + '.response.json')
    # A missing controller never becomes an implicit permission to continue.
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if response.exists():
            return json.loads(response.read_text(encoding='utf-8'))
        time.sleep(.5)
    raise TimeoutError('The main Lab is unreachable. This request remains pending; wait for reconnection.')
