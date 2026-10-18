"""The panel cabinet in the dashboard: every panel (tools/panels.py), its data, its sandboxed view, saving a
designed one into the lab's library, pinning, archiving, approving a collector, and asking the designer for a
new one. Plus the background keeper that gathers pinned panels' data and turns their alerts into events.

    list_panels / get_panel / panel_data / panel_view           GET
    save_panel / pin_panel / archive_panel / approve_collector / collect_now / design_panel   POST
    start_keeper()                                               the background thread (serve.py)
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import ctx  # noqa: E402
import runops  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static" / "panels"
DESIGNS = Path("lab") / ".bus" / "designs" / "panels"
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def _p():
    return ctx.tool("panels")


def _designs() -> list[dict]:
    root = ctx.HUB / DESIGNS
    out = []
    for d in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True) if root.is_dir() else []:
        if not (d.is_dir() and _ID.match(d.name)):
            continue
        has = (d / "panel.yaml").is_file() and (d / "view.html").is_file()
        req = (d / "request.md").read_text(encoding="utf-8", errors="replace")[:600] if (d / "request.md").is_file() else ""
        notes = (d / "notes.md").read_text(encoding="utf-8", errors="replace")[:2000] if (d / "notes.md").is_file() else ""
        out.append({"id": d.name, "ready": has, "request": req, "notes": notes,
                    "collector": next((f.name for f in d.glob("collect.*")), None),
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(d.stat().st_mtime))})
    return out[:30]


def list_panels(q: dict) -> tuple[dict, int]:
    return {"ok": True, **_p().snapshot_view(ctx.HUB), "designs": _designs()}, 200


def get_panel(q: dict) -> tuple[dict, int]:
    pid = str(q.get("id") or "")
    d = ctx.HUB / DESIGNS / pid
    if q.get("design") and _ID.match(pid) and d.is_dir():   # a candidate the designer made
        import yaml  # noqa: PLC0415
        try:
            definition = yaml.safe_load((d / "panel.yaml").read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as e:
            return {"error": f"the design's panel.yaml can't be read: {e}"}, 400
        col = next(iter(d.glob("collect.*")), None)
        return {"ok": True, "design": True, "id": pid, "definition": definition,
                "collector": {"name": col.name, "code": col.read_text(encoding="utf-8", errors="replace")} if col else None,
                "notes": (d / "notes.md").read_text(encoding="utf-8", errors="replace") if (d / "notes.md").is_file() else ""}, 200
    try:
        p = _p()._need(ctx.HUB, pid)
    except ValueError as e:
        return {"error": str(e)}, 404
    col = _p()._collector(p)
    versions = sorted((Path(p["dir"]) / "versions").iterdir(), reverse=True) if (Path(p["dir"]) / "versions").is_dir() else []
    return {"ok": True, "panel": {k: v for k, v in p.items() if k != "dir"},
            "collector": {"name": col.name, "code": col.read_text(encoding="utf-8", errors="replace"),
                          "sha": _p().collector_sha(p), "approved": _p().collector_approved(ctx.HUB, p)} if col else None,
            "versions": [v.name for v in versions[:20]], "cached": _p().cached(ctx.HUB, pid)}, 200


def panel_data(q: dict) -> tuple[dict, int]:
    pid, study = str(q.get("id") or ""), ctx.safe_id(q.get("study") or "") or None
    try:
        p = _p()._need(ctx.HUB, pid)
    except ValueError as e:
        return {"error": str(e)}, 404
    c = _p().cached(ctx.HUB, pid, study)
    if not c or (q.get("fresh") and _p().due(ctx.HUB, p)) or (study and not c):
        c = _p().collect(ctx.HUB, pid, study)
    return {"ok": True, **c}, 200


def _kit() -> tuple[str, str]:
    css = (STATIC / "panelkit.css").read_text(encoding="utf-8") if (STATIC / "panelkit.css").is_file() else ""
    js = (STATIC / "panelkit.js").read_text(encoding="utf-8") if (STATIC / "panelkit.js").is_file() else ""
    return css, js


CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
       "font-src data:; connect-src 'none'; form-action 'none'; frame-src 'none'; base-uri 'none'")


def compose_view(view: str) -> str:
    """The document a panel's sandboxed iframe gets: no network (CSP), the house kit inlined, then its view."""
    css, js = _kit()
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<meta http-equiv=\"Content-Security-Policy\" content=\"{CSP}\">"
            f"<style>{css}</style><script>{js}</script></head><body>{view or ''}</body></html>")


def panel_view(q: dict) -> tuple[dict, int]:
    pid = str(q.get("id") or "")
    if q.get("design"):
        d = ctx.HUB / DESIGNS / pid
        if not (_ID.match(pid) and (d / "view.html").is_file()):
            return {"error": "no such design"}, 404
        return {"ok": True, "html": compose_view((d / "view.html").read_text(encoding="utf-8", errors="replace"))}, 200
    try:
        return {"ok": True, "html": compose_view(_p().view_html(ctx.HUB, pid))}, 200
    except ValueError as e:
        return {"error": str(e)}, 404


def save_panel(body: dict) -> tuple[dict, int]:
    """Save a panel into the lab's library — a designer's candidate (`from_design`), or one written here."""
    if not body.get("confirm"):
        return {"error": "saving a panel needs explicit confirm"}, 400
    where = "user" if body.get("where") == "user" else "lab"
    try:
        if body.get("from_design"):
            did = str(body["from_design"])
            d = ctx.HUB / DESIGNS / did
            if not (_ID.match(did) and (d / "panel.yaml").is_file()):
                return {"error": "no such design"}, 400
            import yaml  # noqa: PLC0415
            definition = yaml.safe_load((d / "panel.yaml").read_text(encoding="utf-8")) or {}
            definition.setdefault("made_by", "designer")
            col = next(iter(d.glob("collect.*")), None)
            p = _p().save(ctx.HUB, str(body.get("id") or did), definition,
                          (d / "view.html").read_text(encoding="utf-8"),
                          (col.name, col.read_text(encoding="utf-8")) if col else None, where)
        else:
            pid = str(body.get("id") or "")
            col = body.get("collector") or None
            p = _p().save(ctx.HUB, pid, body.get("definition") or {}, str(body.get("view") or ""),
                          (str(col.get("name")), str(col.get("code") or "")) if isinstance(col, dict) else None, where)
    except (ValueError, OSError) as e:
        return {"error": str(e)}, 400
    if body.get("pin"):
        _p().set_state(ctx.HUB, p["id"], pinned=[x for x in body["pin"] if x in ("home", "dock", "studies")])
    ctx.pi_log({"action": "panel.save", "panel": p["id"], "where": where, "from_design": body.get("from_design")})
    return {"ok": True, "id": p["id"], "note": f"saved to the cabinet: {p['title']}",
            "needs_approval": not _p().collector_approved(ctx.HUB, p)}, 200


def pin_panel(body: dict) -> tuple[dict, int]:
    pid = str(body.get("id") or "")
    pinned = body.get("pinned")
    try:
        s = _p().set_state(ctx.HUB, pid,
                           pinned=[x for x in pinned if x in ("home", "dock", "studies")] if isinstance(pinned, list) else None,
                           may_hold=bool(body["may_hold"]) if "may_hold" in body else None)
    except ValueError as e:
        return {"error": str(e)}, 400
    ctx.pi_log({"action": "panel.pin", "panel": pid, "state": s})
    return {"ok": True, "state": s}, 200


def archive_panel(body: dict) -> tuple[dict, int]:
    pid = str(body.get("id") or "")
    try:
        s = _p().set_state(ctx.HUB, pid, archived=bool(body.get("archived", True)), pinned=[] if body.get("archived", True) else None)
    except ValueError as e:
        return {"error": str(e)}, 400
    return {"ok": True, "state": s, "note": "archived; it stays in the cabinet" if s.get("archived") else "back in the cabinet"}, 200


def approve_collector(body: dict) -> tuple[dict, int]:
    if not body.get("confirm"):
        return {"error": "approving a collector needs explicit confirm"}, 400
    pid = str(body.get("id") or "")
    try:
        rec = _p().approve_collector(ctx.HUB, pid)
    except ValueError as e:
        return {"error": str(e)}, 400
    ctx.pi_log({"action": "panel.approve_collector", "panel": pid, "sha": rec.get("sha")})
    res = _p().collect(ctx.HUB, pid)
    return {"ok": True, "note": "approved; it runs now", "data": res}, 200


def collect_now(body: dict) -> tuple[dict, int]:
    pid, study = str(body.get("id") or ""), ctx.safe_id(body.get("study") or "") or None
    try:
        return {"ok": True, **_p().collect(ctx.HUB, pid, study)}, 200
    except ValueError as e:
        return {"error": str(e)}, 400




# ── the keeper: gathers pinned panels' data, raises their alerts ─────────────────────────────────
_state = {"thread": None}


def _on_alert(panel: dict, alert: dict) -> None:
    ctx.emit_hub("panel_alert", idea=alert.get("study"), detail=f"{panel['title']}: {alert.get('say')}",
                 data={"panel": panel["id"], "level": alert.get("level") or "warn", "held": bool(alert.get("held"))})


def start_keeper(period: float = 15.0) -> None:
    if _state["thread"] is not None:
        return

    def loop():
        while True:
            try:
                _p().refresh_due(ctx.HUB, on_alert=_on_alert)
            except Exception:  # noqa: BLE001 — the keeper never dies
                pass
            time.sleep(period)

    t = threading.Thread(target=loop, name="panel-keeper", daemon=True)
    _state["thread"] = t
    t.start()


