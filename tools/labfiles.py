"""The lab's own files, read the same way by every tool: lab/config.yaml, the studies (from the kernel's
journal), and where a study's project repo lives — plus the few defensive readers everything shares. Every lab function takes
the hub root, so a tool (or a test) can point it anywhere. pyyaml is used for YAML; the rest is stdlib.

    arlotope_home() / home_path(*p)    the per-user folder (ARLOTOPE_HOME or ~/.arlotope), and a path in it
    read_text(path)                    the text ("" when unreadable; bad bytes replaced, never raised)
    read_json(path, default)           a JSON file, or the default when missing or malformed
    home_rows / save_home_rows(name)   the labs.json / machines.json registries in that folder
    read_jsonl(path, tail=None)        the dict lines of a JSONL file (torn/invalid lines skipped)
    load_yaml(path)                    a YAML file as a dict ({} when missing, malformed or not a mapping)
    write_atomic / write_json          replace a file all-or-nothing (private=True: owner-only)
    append_jsonl(path, rec)            add one record to a JSONL file, best-effort
    inside(root, path)                 the path stays within root and is not itself a symlink
    safe_id(value)                     a study / run / checkpoint id that is safe to put in a path, or None
    pos_int / pos_float(v, default)    a finite number, or the default
    now(epoch=None) / parse_ts(ts)     the lab's local timestamp format, and back to epoch seconds
    read_env(path)                     KEY=value lines (lab/.env.local)
    ensure_lab_files(hub)              give a fresh clone its own settings file, registry view and knowledge documents
    config(hub)                        the lab's settings: config.defaults.yaml with the sparse config.yaml laid over it
    set_config(hub, {a.b: value})      change settings (only what differs from the defaults is saved; None resets)
    config_problems(hub)               what is wrong with config.yaml (unreadable, unknown key, wrong type), or []
    registry_rows(hub)                 every study as a row {id, title, state, workflow, project, updated, next}
    row(hub, slug)                     one study's row
    projects_root(hub)                 lab.projects_root, resolved against the hub
    registry_project_path(hub, slug)   where the journal says its project is (an /adopt-ed repo can live anywhere)
    project_dir(hub, slug)             that, or projects_root/<slug> when it exists
    template(hub, rel)                 templates/<rel>, or the lab's own lab/templates/<rel> when the PI wrote one
    project_types(hub)                 {type: its TYPE.md} — every folder in templates/project-types/ (+ the lab's)
    domain_profiles(hub)               {name: its file} — templates/domain-profiles/*.md (+ the lab's)
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

DEFAULT_PROJECTS_ROOT = "../arlotope-projects"
_EMPTY = ("—", "-", "")
_reads = ContextVar('lab_reads', default=None)


@contextmanager
def read_batch():
    """Reuse registry, config and model reads within one snapshot, never between requests."""
    if _reads.get() is not None:
        yield
        return
    token = _reads.set({})
    try:
        yield
    finally:
        _reads.reset(token)


def cached_read(key, read):
    cache = _reads.get()
    if cache is None:
        return read()
    if key not in cache:
        cache[key] = read()
    return cache[key]


def arlotope_home() -> Path:
    """The per-user ARLOtope folder: labs, machines, panels, keys, workers, logs."""
    return Path(os.environ.get("ARLOTOPE_HOME") or Path.home() / ".arlotope")


def home_path(*parts) -> Path:
    return arlotope_home().joinpath(*parts)


def read_text(path) -> str:
    # errors="replace": one non-UTF-8 byte a training script writes into a tailed file must not raise
    try:
        return Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def read_jsonl(path, tail: int | None = None) -> list[dict]:
    if tail and tail > 0:
        # Recent activity must not allocate the entire append-only history on every refresh.
        try:
            with Path(path).open('rb') as stream:
                offset = stream.seek(0, 2)
                blocks, newlines = [], 0
                while offset and newlines <= tail:
                    size = min(offset, 64 * 1024)
                    offset -= size
                    stream.seek(offset)
                    block = stream.read(size)
                    blocks.append(block)
                    newlines += block.count(b'\n')
            lines = b''.join(reversed(blocks)).decode('utf-8-sig', errors='replace').splitlines()[-tail:]
        except OSError:
            return []
    else:
        lines = read_text(path).splitlines()
        if tail:
            lines = lines[-tail:]
    out = []
    for ln in lines:
        if not ln.strip():
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def load_yaml(path) -> dict:
    try:
        import yaml
        data = yaml.safe_load(read_text(path))
    except Exception:  # noqa: BLE001 — a malformed file is an empty config, never a crash
        return {}
    return data if isinstance(data, dict) else {}


def pos_int(value, default: int, minimum: int) -> int:
    """A config knob as an int: unparseable -> default; below `minimum` -> `minimum`."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(v, minimum)


def pos_float(value, default: float = 0.0) -> float:
    """A config knob as a finite float: unparseable, NaN or infinite -> default."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")


def safe_id(value) -> str | None:
    """A study / run / checkpoint id that is safe to turn into a path (no separators, no leading dot, no
    '..'): the stripped id, or None — a non-string fails validation instead of raising."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if _SAFE_ID.match(value) and ".." not in value else None


def inside(root, path) -> bool:
    """`path` stays within `root` once resolved, and is not itself a symlink."""
    path = Path(path)
    return not path.is_symlink() and path.resolve().is_relative_to(Path(root).resolve())


def write_atomic(path, data, *, mode: int | None = None) -> None:
    """Replace `path` with `data` (bytes, or text written as UTF-8 with no newline translation) so a
    reader sees the old file or the new one, never half of one. A unique temp file in the same folder
    keeps concurrent writers apart; `mode` (e.g. 0o600) applies from creation, so a secret is never
    readable between the write and the rename. Windows can transiently deny the rename (antivirus,
    indexer): retry briefly."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        with os.fdopen(os.open(tmp, flags, 0o666 if mode is None else mode), "wb") as stream:
            stream.write(data.encode("utf-8") if isinstance(data, str) else data)
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02 * (attempt + 1))
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def write_json(path, obj, private: bool = False) -> None:
    """`obj` as indented JSON, atomically (`private`: readable by the owner only)."""
    write_atomic(path, json.dumps(obj, indent=2, default=str), mode=0o600 if private else None)


def read_json(path, default=None):
    """A JSON file's value, or `default` when it is missing or malformed."""
    try:
        return json.loads(read_text(path))
    except ValueError:
        return default


def home_rows(name: str) -> list[dict]:
    """The rows of a per-user registry in the ARLOtope home (`labs` -> labs.json, `machines` -> machines.json)."""
    data = read_json(home_path(f"{name}.json"), {})
    return [r for r in (data.get(name) if isinstance(data, dict) else None) or [] if isinstance(r, dict)]


def save_home_rows(name: str, rows: list[dict], private: bool = False) -> None:
    write_json(home_path(f"{name}.json"), {name: rows}, private)


def append_jsonl(path, rec: dict) -> bool:
    """Add one record to a JSONL file as a single write to an O_APPEND handle (POSIX then never tears or
    interleaves a line, whatever its size). Best-effort: False when it could not be written (the bus must
    never break the lab)."""
    line = (json.dumps(rec, default=str) + "\n").encode("utf-8")
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o666)
        try:
            return os.write(fd, line) == len(line)
        finally:
            os.close(fd)
    except OSError:
        return False


TS_FORMAT = "%Y-%m-%dT%H:%M:%S"


def now(epoch: float | None = None) -> str:
    """The lab's local timestamp, for `epoch` (default: now)."""
    return time.strftime(TS_FORMAT, time.localtime(epoch))


def parse_ts(ts) -> float | None:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return time.mktime(time.strptime(ts[:19], TS_FORMAT))
    except ValueError:
        return None


def read_env(path) -> dict:
    """KEY=value lines (lab/.env.local): comments and blanks skipped, surrounding quotes removed."""
    out = {}
    for line in read_text(path).splitlines():
        k, eq, v = line.strip().partition("=")
        if eq and k.strip() and not k.lstrip().startswith("#"):
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


CONFIG_HEADER = ("# This lab's own settings: only what differs from config.defaults.yaml (every setting is described there).\n"
                 "# The Settings page writes this file; editing it by hand is fine. `key: null` puts a key back to its default.\n")
_config_cache: dict = {}


def config_paths(hub) -> tuple[Path, Path]:
    """The shipped defaults, and this lab's overrides."""
    lab = Path(hub) / "lab"
    return lab / "config.defaults.yaml", lab / "config.yaml"


def ensure_lab_files(hub) -> Path:
    """Give a fresh clone the lab files it doesn't ship (lab state is untracked): a near-empty settings
    file, the registry view and the knowledge documents (from templates/knowledge). Never overwrites.
    Returns the settings file's path; a folder with no config.defaults.yaml is not a lab and gets nothing."""
    defaults, path = config_paths(hub)
    if not defaults.is_file():
        return path
    lab = path.parent
    seeds = {path: CONFIG_HEADER.encode()}
    seeds.update({lab / "knowledge" / f.name: f.read_bytes() for f in (Path(hub) / "templates" / "knowledge").glob("*.md")})
    for target, data in seeds.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(FileExistsError):   # another process seeded the same lab
            with target.open("xb") as output:
                output.write(data)
    if not (lab / "REGISTRY.md").exists():
        from kernel import studies  # noqa: PLC0415 — lazy: the kernel reads this module's helpers
        studies.render_registry(hub)
    return path


def _parse_config(path: Path) -> dict:
    """A settings file as a dict ({} when missing or blank); ValueError when it cannot be used."""
    import yaml
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"{path.name} is unreadable: {' '.join(str(e).split())}") from e
    if data is not None and not isinstance(data, dict):
        raise ValueError(f"{path.name} is unreadable: it is not a list of settings")
    return data or {}


def _merge(base: dict, over: dict) -> dict:
    """`over` laid on `base`: dicts merge, anything else replaces, null puts the default back."""
    out = dict(base)
    for k, v in over.items():
        if v is not None:
            out[k] = _merge(base[k] if isinstance(base.get(k), dict) else {}, v) if isinstance(v, dict) else v
    return out


def _kind(v) -> str:
    return "number" if isinstance(v, (int, float)) and not isinstance(v, bool) else type(v).__name__


def _issues(defaults: dict, over: dict, prefix: str = "") -> list[str]:
    """Overrides the defaults don't know, and overrides of another type than their default. A default of
    {} or null is an open slot (presets, an optional command): anything goes below it."""
    out = []
    if not defaults:
        return out
    for k, v in over.items():
        if v is None:
            continue
        if k not in defaults:
            out.append(f"unknown setting {prefix}{k}")
        elif defaults[k] is not None and _kind(v) != _kind(defaults[k]):
            out.append(f"{prefix}{k} should be a {_kind(defaults[k])}, not a {_kind(v)}")
        elif isinstance(v, dict):
            out += _issues(defaults[k], v, f"{prefix}{k}.")
    return out


def _stamp(path: Path):
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def _load_config(hub) -> dict:
    """Both files parsed again when either changed. A file that no longer parses keeps its last good
    parse (the defaults alone, if it never has) and shows up in `problems`; never an empty config."""
    paths = config_paths(hub)
    stamps = [_stamp(p) for p in paths]
    entry = _config_cache.setdefault(Path(hub), {"stamps": None, "good": [{}, {}], "problems": []})
    if entry["stamps"] != stamps:
        problems = []
        for i, path in enumerate(paths):
            try:
                entry["good"][i] = _parse_config(path)
            except ValueError as e:
                problems.append(f"{e}; using its last good settings")
        entry["problems"] = problems + _issues(*entry["good"])
        entry["stamps"] = stamps
    return entry


def config(hub) -> dict:
    return cached_read(('config', Path(hub)), lambda: _merge(*_load_config(hub)["good"]))


def config_problems(hub) -> list[str]:
    return list(_load_config(hub)["problems"])


def _put(tree: dict, parts: list[str], value) -> None:
    """tree[a][b]... = value, or removed when value is None; sections left empty are removed too."""
    head, *rest = parts
    if rest:
        child = tree[head] if isinstance(tree.get(head), dict) else {}
        _put(child, rest, value)
        value = child or None
    if value is None:
        tree.pop(head, None)
    else:
        tree[head] = value


def _sparse(value, default):
    """The part of `value` that differs from `default` (None when it all matches)."""
    if isinstance(value, dict) and isinstance(default, dict) and default:
        diff = {k: d for k, v in value.items() if (d := _sparse(v, default.get(k))) is not None}
        return diff or None
    return None if value == default else value


def set_config(hub, changes: dict) -> str | None:
    """Change settings: {"agents.programmatic.enabled": True}. Only what differs from the defaults is kept
    in config.yaml, and None puts a setting back to its default. Nothing is written when a value is
    unknown or of the wrong type, or when config.yaml can't be read. Returns None, or what went wrong."""
    import yaml  # noqa: PLC0415
    from executor.procs import excl_lock  # noqa: PLC0415 — lazy: the executor imports this module
    defaults_path, path = config_paths(hub)
    try:
        defaults = _parse_config(defaults_path)
    except ValueError as e:
        return f"refused: {e}"
    asked = {}
    for dotted, value in changes.items():
        _put(asked, dotted.split("."), value)
    if issues := _issues(defaults, asked):
        return f"refused: {'; '.join(issues)}"
    with excl_lock(path.with_name(".config.lock")):
        try:
            over = _parse_config(path)
        except ValueError as e:
            return f"refused: {e}"
        for dotted, value in changes.items():
            parts = dotted.split(".")
            default = defaults
            for part in parts:
                default = default.get(part) if isinstance(default, dict) else None
            _put(over, parts, _sparse(value, default))
        write_atomic(path, CONFIG_HEADER + (yaml.safe_dump(over, sort_keys=False, allow_unicode=True) if over else ""))
    return None


def registry_rows(hub) -> list[dict]:
    """Every study, as the kernel's journal has it (lab/REGISTRY.md is the same, written out)."""
    from kernel import studies  # noqa: PLC0415 — lazy: the kernel reads this module's helpers
    return cached_read(('registry', Path(hub)), lambda: studies.rows(hub))


def row(hub, slug: str) -> dict | None:
    return next((r for r in registry_rows(hub) if r["id"] == slug), None) if slug else None


def projects_root(hub) -> Path:
    root = (config(hub).get("lab") or {}).get("projects_root")
    return (Path(hub) / (root or DEFAULT_PROJECTS_ROOT)).resolve()


def registry_project_path(hub, slug: str, r: dict | None = None) -> Path | None:
    r = r if r is not None else row(hub, slug)
    raw = ((r or {}).get("project") or "").strip().strip("`")
    if raw in _EMPTY:
        return None
    if raw.startswith('arlotope+ssh://'):
        return None
    p = Path(raw)
    return p if p.is_absolute() else (Path(hub) / p).resolve()


def project_dir(hub, slug: str, r: dict | None = None) -> Path | None:
    r = r if r is not None else (row(hub, slug) or {})
    if str(r.get('project') or '').startswith('arlotope+ssh://'):
        return None
    p = registry_project_path(hub, slug, r)
    if p:
        return p
    cand = projects_root(hub) / slug
    return cand if cand.exists() else None


def template(hub, rel) -> Path:
    """A template file or folder: the lab's own copy (lab/templates/<rel>) when the PI wrote one, else the
    shipped templates/<rel>. A lab customises a template by copying it there — upgrades never touch it."""
    own = Path(hub) / "lab" / "templates" / rel
    return own if own.exists() else Path(hub) / "templates" / rel


def _template_roots(hub, rel) -> list[Path]:
    return [r for r in (Path(hub) / "templates" / rel, Path(hub) / "lab" / "templates" / rel) if r.is_dir()]


def project_types(hub) -> dict[str, str]:
    """Every project type (templates/project-types/<type>/TYPE.md, and the lab's own under lab/templates/):
    adding one is adding that folder."""
    out = {}
    for root in _template_roots(hub, "project-types"):        # the lab's own last: it wins
        for d in sorted(root.iterdir()):
            f = d / "TYPE.md"
            if f.is_file():
                out[d.name] = f.read_text(encoding="utf-8", errors="replace")
    return dict(sorted(out.items()))


def domain_profiles(hub) -> dict[str, Path]:
    """Every domain profile (templates/domain-profiles/<name>.md, and the lab's own)."""
    out = {}
    for root in _template_roots(hub, "domain-profiles"):
        for f in sorted(root.glob("*.md")):
            if f.name.lower() != "readme.md":
                out[f.stem] = f
    return dict(sorted(out.items()))
