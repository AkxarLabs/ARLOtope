"""One-directory browsing for the local dashboard and the small SSH worker."""
import os
from pathlib import Path


def browse(value=None, hidden=False):
    if value is not None and (not isinstance(value, str) or len(value) > 4096 or '\0' in value):
        raise ValueError('Choose a folder.')
    folder = Path(value or '~').expanduser()
    if not folder.is_absolute():
        raise ValueError('Use an absolute folder path or ~ for home.')
    folder = folder.resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Choose a folder, not a file.')
    rows = []
    # No recursive scan, file contents, or shell invocation.
    with os.scandir(folder) as entries:
        for entry in entries:
            if not hidden and entry.name.startswith('.'):
                continue
            try:
                if entry.is_dir():
                    rows.append({'name':entry.name, 'path':str(folder / entry.name)})
            except OSError:
                continue
            if len(rows) >= 1000:
                break
    rows.sort(key=lambda r: r['name'].casefold())
    drives = [f'{letter}:\\' for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if Path(f'{letter}:\\').is_dir()] if os.name == 'nt' else []
    return {'path':str(folder), 'parent':str(folder.parent) if folder.parent != folder else None,
            'home':str(Path.home()), 'folders':rows, 'truncated':len(rows) == 1000, 'drives':drives}
