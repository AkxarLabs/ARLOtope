#!/usr/bin/env python3
"""Panels — the lab's instruments: something the dashboard tracks, and how it is drawn.

A panel is a folder holding `panel.yaml`, a `view.html` and, optionally, a collector script:

    title: GPU, jobs and time          icon: "◔"          description: one line
    source: collector                  # collector | files | events | runs | registry (or a list of them)
    collector: collect.py              # a script in ANY language that prints JSON (source: collector)
    files: ["{projects}/*/runs/*/meta.json"]   # globs ({hub}, {projects}) for source: files
    events: [run_finished]             # bus event kinds for source: events
    every: 2m                          # how often its data is gathered (≥ 30 s)
    scope: lab | study                 # a study panel's view is told which study it shows
    summary: "{gpu_hours:.0f} GPU-h"   # one line from the data (or the data's own `summary`)

Where panels live — every panel ever made stays (unpinning never deletes; archive hides; delete is explicit):
    dashboard/static/panels/shipped/<id>/   the shipped ones (code-owned)
    ~/.newts/panels/<id>/      yours across every lab ("Save to all my labs")
    lab/panels/<id>/           this lab's — designed or written for it (old versions in versions/)

The constraints, enforced by code rather than prose:
  * a view runs in a sandboxed iframe with an opaque origin and a CSP with no network: it sees only the data it
    is posted, and can only ask the dashboard to resize it, open a lab object, or show a summary line;
  * a collector is code, so it runs only once the PI approved THAT version of it (a record in lab/journal.jsonl,
    `panel:<id>`, carrying the script's sha); shipped collectors are the lab's own code. It runs with a timeout and
    its output (≤ 2 MB of JSON) is never imported;
  * every panel has a one-line summary (for Home, the dock, the CLI and screen readers);
  * alerts: the data may carry `alerts: [{level: info|warn|block, say, study?, hold?}]`. Each becomes a
    Needs-you item; `hold: true` holds that study's launches only if the PI let this panel do that.

    uv run --with pyyaml python tools/panels.py list
    uv run --with pyyaml python tools/panels.py show <id>       # its summary and data (collects if stale)
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from kernel import checkpoints, journal  # noqa: E402
import labfiles  # noqa: E402

SHIPPED = HERE.parent / "dashboard" / "static" / "panels" / "shipped"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
MIN_EVERY = 30
MAX_OUT = 2_000_000
SOURCES = ("collector", "files", "events", "runs", "registry")


def user_dir() -> Path:
    return Path(os.environ.get("NEWTS_HOME") or (Path.home() / ".newts")) / "panels"


def lab_dir(hub) -> Path:
    return Path(hub) / "lab" / "panels"


def _bus(hub) -> Path:
    return Path(hub) / "lab" / ".bus" / "panels"


def parse_every(v) -> int:
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*$", str(v or "5m"))
    if not m:
        return 300
    n = float(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
    return max(MIN_EVERY, int(n))


def _read_def(d: Path, origin: str) -> dict | None:
    f = d / "panel.yaml"
    if not f.is_file() or not ID_RE.match(d.name):
        return None
    try:
        p = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        p = {"title": d.name, "error": f"panel.yaml: {e}"}
    if not isinstance(p, dict):
        return None
    p["id"], p["origin"], p["dir"] = d.name, origin, str(d)
    p.setdefault("title", d.name.replace("-", " ").capitalize())
    p.setdefault("scope", "lab")
    src = p.get("source") or ("collector" if p.get("collector") else "registry")
    p["sources"] = [s for s in (src if isinstance(src, list) else [src]) if s in SOURCES]
    return p


def state_file(hub) -> Path:
    return lab_dir(hub) / "_state.json"


def state(hub) -> dict:
    """{id: {pinned: [home|dock|studies], archived: bool, may_hold: bool}} — this lab's choices."""
    try:
        d = json.loads(state_file(hub).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = None
    if not isinstance(d, dict):   # first use: the shipped Compute and spend panels are pinned
        d = {"compute": {"pinned": ["home", "dock", "studies"]}, "agent-spend": {"pinned": ["home", "dock"]}}
    return d


def _save_state(hub, d: dict) -> None:
    f = state_file(hub)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, indent=1), encoding="utf-8")


def library(hub) -> list[dict]:
    """Every panel: shipped, then yours, then the lab's (a later one with the same id wins), with this lab's
    pins/archive state."""
    found: dict[str, dict] = {}
    for root, origin in ((SHIPPED, "shipped"), (user_dir(), "yours"), (lab_dir(hub), "lab")):
        for d in sorted(root.iterdir()) if root.is_dir() else []:
            if d.is_dir():
                p = _read_def(d, origin)
                if p:
                    found[p["id"]] = p
    st = state(hub)
    out = []
    for pid, p in found.items():
        s = st.get(pid) or {}
        p["pinned"] = [x for x in (s.get("pinned") or []) if x in ("home", "dock", "studies")]
        p["archived"], p["may_hold"] = bool(s.get("archived")), bool(s.get("may_hold"))
        out.append(p)
    return out


def get(hub, pid: str) -> dict | None:
    return next((p for p in library(hub) if p["id"] == pid), None)


def _need(hub, pid: str) -> dict:
    p = get(hub, pid) if ID_RE.match(pid or "") else None
    if not p:
        raise ValueError(f"no panel {pid!r}")
    return p


def set_state(hub, pid: str, **kw) -> dict:
    _need(hub, pid)
    d = state(hub)
    s = d.setdefault(pid, {})
    for k, v in kw.items():
        if v is not None:
            s[k] = v
    _save_state(hub, d)
    return s


# ── the collector: code, approved by the PI version by version ───────────────────────────────────
def _collector(p: dict) -> Path | None:
    name = str(p.get("collector") or "")
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    f = Path(p["dir"]) / name
    return f if f.is_file() else None


def collector_sha(p: dict) -> str | None:
    f = _collector(p)
    return hashlib.sha256(f.read_bytes()).hexdigest()[:16] if f else None


def collector_approved(hub, p: dict, code: bytes | None = None) -> bool:
    if "collector" not in p["sources"]:
        return True
    if p["origin"] == "shipped":
        return True
    sha = collector_sha(p) if code is None else hashlib.sha256(code).hexdigest()[:16]
    rec = journal.latest(hub, "lab", f"panel:{p['id']}")
    return bool(sha and rec and rec.get("decision") == "approved" and rec.get("sha") == sha)


def approve_collector(hub, pid: str, by: str = "pi", via: str = "dashboard", expected_sha: str | None = None) -> dict:
    p = _need(hub, pid)
    sha = collector_sha(p)
    if not sha:
        raise ValueError(f"panel {pid} has no collector to approve")
    if expected_sha is not None and sha != expected_sha:
        raise ValueError('The collector changed. Review the updated code before approving.')
    return checkpoints.decide_lab(hub, f"panel:{pid}", "approved", by=by, via=via,
                                  note=f"its collector {p.get('collector')} may run", sha=sha)


def _interpreter(f: Path) -> list[str]:
    ext = f.suffix.lower()
    if ext == ".py":
        return [sys.executable, "-I", str(f)]
    if ext in (".sh", ".bash"):
        return [shutil.which("bash") or "bash", str(f)]
    if ext == ".ps1":
        return [shutil.which("pwsh") or shutil.which("powershell") or "powershell", "-NoProfile", "-File", str(f)]
    if ext == ".js":
        return [shutil.which("node") or "node", str(f)]
    if ext == ".r":
        return [shutil.which("Rscript") or "Rscript", str(f)]
    return [str(f)]


def _run_collector(hub, p: dict, study: str | None = None, timeout: float = 60) -> dict:
    f = _collector(p)
    if not f:
        return {"error": f"the collector {p.get('collector')!r} is missing"}
    env = dict(os.environ, NEWTS_HUB=str(hub), NEWTS_PANEL=p["id"], NEWTS_STUDY=study or "",
               NEWTS_COLLECTOR=str(f.resolve()),
               NEWTS_PROJECTS=str(labfiles.projects_root(Path(hub))),
               NEWTS_CONFIG=json.dumps(labfiles.config(Path(hub)) or {}, default=str))
    env.pop("NEWTS_RUN_ID", None)
    snapshot = None
    try:
        code = f.read_bytes()
        if not collector_approved(hub, p, code):
            return {"error": "its collector is waiting for your approval"}
        if p["origin"] != "shipped":
            # A sibling keeps __dirname / script-parent resources and the original cwd intact.
            with tempfile.NamedTemporaryFile(dir=f.parent, prefix=".newts-collector-", suffix=f.suffix, delete=False) as copy:
                snapshot = Path(copy.name)
                copy.write(code)
            snapshot.chmod(0o700)
            f = snapshot
        r = subprocess.run(_interpreter(f), cwd=str(hub), env=env, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": f"the collector did not finish: {e}"[:400]}
    finally:
        if snapshot is not None:
            try:
                snapshot.unlink(missing_ok=True)
            except OSError:
                pass  # A lingering child/OS file lock must not discard the collector's result.
    out = (r.stdout or b"")[:MAX_OUT + 1]
    if len(out) > MAX_OUT:
        return {"error": "the collector printed more than 2 MB"}
    if r.returncode != 0:
        return {"error": f"the collector exited {r.returncode}: " + (r.stderr or b"").decode("utf-8", "replace")[-400:]}
    try:
        data = json.loads(out.decode("utf-8", "replace") or "null")
    except ValueError as e:
        return {"error": f"the collector's output is not JSON ({e})"}
    return {"data": data}


# ── the other sources: plain reads of the lab ────────────────────────────────────────────────────
def _expand(hub, pat: str) -> list[str]:
    s = pat.replace("{hub}", Path(hub).as_posix()).replace("{projects}", labfiles.projects_root(Path(hub)).as_posix())
    if not Path(s).is_absolute():
        s = (Path(hub) / s).as_posix()
    return sorted(glob.glob(s, recursive=True))[:400]


def _read_any(f: Path):
    text = f.read_text(encoding="utf-8-sig", errors="replace")[:400_000]
    if f.suffix in (".json",):
        return json.loads(text)
    if f.suffix in (".jsonl",):
        return [json.loads(x) for x in text.splitlines()[-2000:] if x.strip().startswith("{")]
    if f.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    if f.suffix == ".csv":
        import csv  # noqa: PLC0415
        return list(csv.DictReader(text.splitlines()))[:5000]
    return text[:20000]


def _files(hub, p: dict) -> list[dict]:
    out = []
    for g in p.get("files") or []:
        for f in _expand(hub, str(g)):
            try:
                out.append({"path": Path(f).as_posix(), "data": _read_any(Path(f))})
            except (OSError, ValueError, yaml.YAMLError):
                continue
    return out


def _events(hub, p: dict) -> list[dict]:
    kinds = set(p.get("events") or [])
    buses = [Path(hub) / "lab" / ".bus" / "events.jsonl"]
    for r in labfiles.registry_rows(Path(hub)):
        d = labfiles.project_dir(Path(hub), r["id"], r)
        if d:
            buses.append(d / ".bus" / "events.jsonl")
    out = []
    for b in buses:
        for e in labfiles.read_jsonl(b)[-3000:] if b.is_file() else []:
            if not kinds or e.get("kind") in kinds:
                out.append(e)
    return sorted(out, key=lambda e: e.get("ts") or "")[-4000:]


def _runs(hub) -> list[dict]:
    try:
        from executor import all_runs, Lab  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    keep = ("run_id", "skill", "subject", "status", "backend", "model", "created", "started", "finished",
            "campaign", "created_by")
    out = []
    for *_x, m in all_runs(Lab(Path(hub))):
        r = {k: m.get(k) for k in keep}
        r["cost_usd"] = (m.get("usage") or {}).get("cost_usd")
        r["minutes"] = round(sum(float(a.get("wall_seconds") or 0) for a in (m.get("attempts") or [])) / 60, 2)
        out.append(r)
    return out


def _registry(hub) -> list[dict]:
    return [{k: r.get(k) for k in ("id", "title", "state", "updated", "next")} for r in labfiles.registry_rows(Path(hub))]


# ── collecting, caching, summaries, alerts ───────────────────────────────────────────────────────
def _cache(hub, pid: str, study: str | None = None) -> Path:
    return _bus(hub) / "data" / (f"{pid}.{study}.json" if study else f"{pid}.json")


def cached(hub, pid: str, study: str | None = None) -> dict:
    try:
        return json.loads(_cache(hub, pid, study).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class _Fmt(dict):
    def __missing__(self, k):
        return "?"


def summary_of(p: dict, data) -> str:
    if isinstance(data, dict) and isinstance(data.get("summary"), str):
        return data["summary"][:200]
    fmt = p.get("summary")
    if fmt and isinstance(data, dict):
        try:
            return str(fmt).format_map(_Fmt({k: v for k, v in data.items() if not isinstance(v, (dict, list))}))[:200]
        except (ValueError, TypeError, KeyError, IndexError):
            return ""
    return ""


def collect(hub, pid: str, study: str | None = None, timeout: float = 60) -> dict:
    """Gather one panel's data now (a collector only if its version is approved). Cached; returns the result."""
    p = _need(hub, pid)
    prev = cached(hub, pid, study)
    res = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "epoch": time.time(), "panel": pid, "study": study}
    data: dict = {}
    err = None
    for src in p["sources"]:
        if src == "collector":
            r = _run_collector(hub, p, study, timeout)
            if r.get("error"):
                err = r["error"]
            elif isinstance(r.get("data"), dict):
                data.update(r["data"])
            else:
                data["value"] = r.get("data")
        elif src == "files":
            data["files"] = _files(hub, p)
        elif src == "events":
            data["events"] = _events(hub, p)
        elif src == "runs":
            data["runs"] = _runs(hub)
        elif src == "registry":
            data["studies"] = _registry(hub)
    if err and not data and prev.get("data") is not None:   # keep the last good data, marked stale
        res.update(data=prev.get("data"), stale=True, error=err, summary=prev.get("summary"), alerts=prev.get("alerts") or [])
    else:
        alerts = [a for a in (data.get("alerts") or []) if isinstance(a, dict) and a.get("say")][:20]
        res.update(data=data, error=err, summary=summary_of(p, data), alerts=alerts)
    f = _cache(hub, pid, study)
    f.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(res, default=str)
    if len(blob) > MAX_OUT * 2:
        res.update(data={"note": "too much data to keep"}, error="the data is too large")
        blob = json.dumps(res, default=str)
    f.write_text(blob, encoding="utf-8")
    return res


def due(hub, p: dict) -> bool:
    c = cached(hub, p["id"])
    return time.time() - float(c.get("epoch") or 0) >= parse_every(p.get("every"))


def refresh_due(hub, on_alert=None) -> list[str]:
    """Gather every pinned (or recently opened) panel that is due; act on new alerts. The dashboard's
    background thread calls this every ~15 s; `on_alert(panel, alert)` is told about each NEW alert."""
    done = []
    seen_f = _bus(hub) / "alerts-seen.json"
    try:
        seen = set(json.loads(seen_f.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        seen = set()
    for p in library(hub):
        if p.get("archived") or not (p.get("pinned") or p.get("watch")) or not due(hub, p):
            continue
        try:
            res = collect(hub, p["id"])
        except Exception:  # noqa: BLE001 — one broken panel never stops the others
            continue
        done.append(p["id"])
        for a in res.get("alerts") or []:
            key = f"{p['id']}|{a.get('study')}|{a.get('say')}"
            if key in seen:
                continue
            seen.add(key)
            if a.get("hold") and a.get("study") and p.get("may_hold"):
                a["held"] = _hold(hub, a["study"], f"panel {p['title']}: {a['say']}")
            if on_alert:
                on_alert(p, a)
    seen_f.parent.mkdir(parents=True, exist_ok=True)
    seen_f.write_text(json.dumps(sorted(seen)[-500:]), encoding="utf-8")
    return done


def _hold(hub, study: str, reason: str) -> bool:
    try:
        from executor import Lab, pause  # noqa: PLC0415
        pause.hold(Lab(Path(hub)), study, by="panel", reason=reason[:280])
        return True
    except Exception:  # noqa: BLE001
        return False


def alert_items(hub) -> list[dict]:
    """The current alerts of every panel, for Needs you."""
    out = []
    for p in library(hub):
        if p.get("archived"):
            continue
        c = cached(hub, p["id"])
        for a in c.get("alerts") or []:
            out.append({"panel": p["id"], "title": p["title"], "level": a.get("level") or "warn", "say": a.get("say"),
                        "study": a.get("study"), "hold": bool(a.get("hold") and p.get("may_hold")), "ts": c.get("ts")})
    return out


def snapshot_view(hub) -> dict:
    """What the dashboard's snapshot carries: each panel's card (no data — that is fetched when shown)."""
    out = []
    for p in library(hub):
        c = cached(hub, p["id"])
        out.append({k: p.get(k) for k in ("id", "title", "icon", "description", "scope", "origin", "pinned", "archived",
                                           "may_hold", "tags", "every", "made_by", "error")}
                   | {"sources": p["sources"], "summary": c.get("summary"), "ts": c.get("ts"), "stale": bool(c.get("stale")),
                      "problem": c.get("error"), "alerts": len(c.get("alerts") or []),
                      "needs_approval": not collector_approved(hub, p), "gauge": _gauge(c.get("data"))})
    return {"panels": out}


def _gauge(data) -> dict | None:
    """A panel's main value for its dial: its data's `gauge: {value, max, label}` (optional)."""
    g = data.get("gauge") if isinstance(data, dict) else None
    if not isinstance(g, dict):
        return None
    try:
        return {"value": float(g.get("value") or 0), "max": float(g.get("max") or 0) or None,
                "label": str(g.get("label") or "")[:40], "tone": str(g.get("tone") or "")[:10]}
    except (TypeError, ValueError):
        return None


# ── writing: the PI's own panels and the designer's (through the dashboard) ──────────────────────
def save(hub, pid: str, definition: dict, view: str, collector: tuple[str, str] | None = None,
         where: str = "lab") -> dict:
    """Write a panel into the lab's library (or yours, `where='user'`). An existing one keeps its old version
    in versions/<ts>/. Returns its definition."""
    if not ID_RE.match(pid or ""):
        raise ValueError("a panel id is lowercase letters, digits and dashes")
    if not isinstance(definition, dict):
        raise ValueError("the definition must be a mapping")
    if len(view or "") > 400_000:
        raise ValueError("the view is over 400 KB")
    root = user_dir() if where == "user" else lab_dir(hub)
    d = root / pid
    if d.exists():
        v = d / "versions" / time.strftime("%Y%m%d-%H%M%S")
        v.mkdir(parents=True, exist_ok=True)
        for f in d.iterdir():
            if f.is_file():
                shutil.copy2(f, v / f.name)
    d.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in definition.items() if k not in ("id", "origin", "dir", "pinned", "archived", "may_hold", "sources")}
    if collector:
        name, code = collector
        if not re.match(r"^collect\.(py|sh|ps1|js|r|R)$", name or ""):
            raise ValueError("a collector is collect.py / .sh / .ps1 / .js / .r")
        if len(code) > 200_000:
            raise ValueError("the collector is over 200 KB")
        for old in d.glob("collect.*"):
            old.unlink()
        (d / name).write_text(code, encoding="utf-8", newline="\n")
        clean["collector"] = name
        if clean.get("source") is None:
            clean["source"] = "collector"
    (d / "panel.yaml").write_text(yaml.safe_dump(clean, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (d / "view.html").write_text(view or "", encoding="utf-8", newline="\n")
    return _need(hub, pid)


def view_html(hub, pid: str) -> str:
    p = _need(hub, pid)
    f = Path(p["dir"]) / str(p.get("view") or "view.html")
    return f.read_text(encoding="utf-8") if f.is_file() else "<p>(this panel has no view.html)</p>"


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="the lab's panels")
    ap.add_argument("--hub", default=str(HERE.parent))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sh = sub.add_parser("show")
    sh.add_argument("id")
    sh.add_argument("--study")
    sh.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    hub = Path(a.hub)
    if a.cmd == "list":
        for p in library(hub):
            c = cached(hub, p["id"])
            flags = ",".join(p["pinned"]) or ("archived" if p["archived"] else "in the cabinet")
            print(f"{p['id']:<22} {p['title'][:34]:<34} [{flags}] {c.get('summary') or ''}")
        return 0
    try:
        p = _need(hub, a.id)
    except ValueError as e:
        print(f"[panels] {e}", file=sys.stderr)
        return 2
    c = cached(hub, p["id"], a.study)
    if not c or due(hub, p):
        c = collect(hub, p["id"], a.study)
    if a.json:
        print(json.dumps(c, indent=1, default=str))
        return 0
    print(f"{p['title']} — {c.get('summary') or '(no summary)'}  ({c.get('ts')})")
    if c.get("error"):
        print(f"  problem: {c['error']}")
    for al in c.get("alerts") or []:
        print(f"  ▲ {al.get('say')}" + (f" ({al['study']})" if al.get("study") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
