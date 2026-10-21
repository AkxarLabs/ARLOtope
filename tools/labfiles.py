"""The lab's own files, read the same way by every tool: lab/config.yaml, the studies (from the kernel's
journal), and where a study's project repo lives — plus the few defensive readers everything shares. Every lab function takes
the hub root, so a tool (or a test) can point it anywhere. pyyaml is used for YAML; the rest is stdlib.

    read_text(path)                    the text ("" when unreadable; bad bytes replaced, never raised)
    read_jsonl(path, tail=None)        the dict lines of a JSONL file (torn/invalid lines skipped)
    load_yaml(path)                    a YAML file as a dict ({} when missing, malformed or not a mapping)
    to_int / to_float(v, default)      a number, or the default
    now() / parse_ts(ts)               the lab's local timestamp format, and back to epoch seconds
    read_env(path)                     KEY=value lines (lab/.env.local)
    config(hub)                        lab/config.yaml
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

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

DEFAULT_PROJECTS_ROOT = "../newts-lab-projects"
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


def read_text(path) -> str:
    # errors="replace": one non-UTF-8 byte a training script writes into a tailed file must not raise
    try:
        return Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def read_jsonl(path, tail: int | None = None) -> list[dict]:
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


def to_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def to_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


TS_FORMAT = "%Y-%m-%dT%H:%M:%S"


def now() -> str:
    return time.strftime(TS_FORMAT)


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


def config(hub) -> dict:
    path = Path(hub) / "lab" / "config.yaml"
    return cached_read(('config', path), lambda: load_yaml(path))


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
    if raw.startswith('newts+ssh://'):
        return None
    p = Path(raw)
    return p if p.is_absolute() else (Path(hub) / p).resolve()


def project_dir(hub, slug: str, r: dict | None = None) -> Path | None:
    r = r if r is not None else (row(hub, slug) or {})
    if str(r.get('project') or '').startswith('newts+ssh://'):
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
