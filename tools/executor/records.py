"""Durable exported responses and human exchanges. Read payloads only on demand."""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from labfiles import now
from .procs import excl_lock

FILE = 'conversation.jsonl'
MAX_TEXT = 450_000


def record(rd, manifest, kind, **fields):
    entry = {'id': uuid.uuid4().hex, 'at': now(), 'kind': kind,
             'attempt': manifest.get('attempt', 0), **fields}
    if isinstance(entry.get('text'), str) and len(entry['text']) > MAX_TEXT:
        entry.update(text=entry['text'][:MAX_TEXT], clipped=True)
    if len(json.dumps(entry, ensure_ascii=False).encode('utf-8')) > 1900_000:
        entry = {k:entry[k] for k in ('id','at','kind','attempt')} | {
            'clipped': True, 'payload_preview': json.dumps(fields, ensure_ascii=False)[:MAX_TEXT]}
    try:
        path = Path(rd)/FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (json.dumps(entry, ensure_ascii=False)+'\n').encode('utf-8')
        with excl_lock(path.with_suffix('.lock'), wait=2):
            fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, 'O_BINARY', 0), 0o600)
            try:
                if os.write(fd, content) != len(content):
                    raise OSError('Incomplete conversation record write.')
            finally:
                os.close(fd)
            manifest['record_count'] = manifest.get('record_count', 0)+1
    except OSError as error:
        manifest['record_error'] = str(error)
    return entry


def page(rd, offset=0):
    """Byte cursor, bounded complete lines; partial remote writes wait for the next read."""
    path = Path(rd)/FILE
    rows = []; skipped = 0
    offset = max(0, int(offset))
    try:
        with path.open('rb') as stream:
            size = stream.seek(0, 2)
            offset = min(offset, size)
            stream.seek(offset)
            while len(rows) < 30 and stream.tell()-offset < 2*1024*1024:
                start = stream.tell()
                line = stream.readline(2*1024*1024+1)
                if not line or not line.endswith(b'\n'):
                    stream.seek(start)
                    break
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
                except (ValueError, UnicodeError):
                    skipped += 1
                    continue
            end = stream.tell()
    except FileNotFoundError:
        return {'rows': [], 'offset': 0, 'next': None, 'available': False}
    return {'rows': rows, 'offset': end, 'next': end if end < size and end > offset else None, 'available': True, 'incomplete': end < size and end == offset, 'skipped': skipped}
