"""Initialize a configured ACP process without prompting a model or sharing workspace files."""
import json
import queue
import subprocess
import threading
import time
from .procs import kill_tree, NO_WINDOW


def probe(command, cwd, timeout=20):
    process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace',
        **NO_WINDOW)
    lines = queue.Queue()
    def read():
        for line in process.stdout:
            if len(line) <= 1_000_000:
                lines.put(line)
    threading.Thread(target=read, daemon=True).start()
    try:
        process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': 1, 'clientInfo': {'name': 'arlotope', 'version': '1'}, 'clientCapabilities': {}}})+'\n')
        process.stdin.flush()
        until = time.monotonic()+timeout
        while time.monotonic() < until:
            try:
                line = lines.get(timeout=.2)
            except queue.Empty:
                if process.poll() is not None:
                    raise ValueError('The ACP process exited before initialization. Check its command and installation.')
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict) or message.get('id') != 1:
                continue
            if message.get('error'):
                raise ValueError(str(message['error'].get('message') or 'ACP initialization failed.'))
            result = message.get('result') or {}
            if not isinstance(result, dict) or result.get('protocolVersion') != 1:
                raise ValueError('This agent did not negotiate ACP v1.')
            return {key: result.get(key) for key in ('protocolVersion', 'agentInfo', 'agentCapabilities', 'authMethods')}
        raise ValueError('ACP initialization timed out. Check the command and try again.')
    finally:
        try:
            process.stdin.close()  # Let stdio agents and their launchers clean up on EOF.
        except (OSError, ValueError):
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            kill_tree(process.pid); process.wait(timeout=3)
        process.stdout.close()
