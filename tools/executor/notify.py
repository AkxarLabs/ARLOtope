"""Tell the PI when something needs them — from the scheduler, so it works with the dashboard closed.

Configured in Settings → Lab → Notifications, stored in lab/.env.local (git-ignored; a topic or a
webhook URL is a secret — anyone holding it can read or post) and never passed to agents:

  ARLOTOPE_NOTIFY_NTFY=https://ntfy.sh/<your-topic>     a phone push via ntfy (app or web); any ntfy server
  ARLOTOPE_NOTIFY_WEBHOOK=https://hooks.slack.com/...   Slack / Discord / Teams / anything taking JSON {text}
  ARLOTOPE_NOTIFY_LINK=http://my-pc.tailnet:8787        where the dashboard is reachable from your phone;
                                                     each notification links straight to the item

What is sent: title/body excerpts, which can include a question or command. Files, full transcripts
and configured credentials are not attached; excerpts are not automatically redacted. Actionable
Inbox items are sent; informational finished reports are skipped. The scheduler sends in the
background; its last supervisor flushes once on exit when no scheduler is running. Failed channels
retry on the next running scheduler; no notification-only service is kept alive.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .lab import Lab, labfiles, profile
from .manifest import now
from .procs import excl_lock

CHECK_EVERY = 15.0
MAX_PER_CHECK = 5
_last: dict[str, float] = {}
_busy: dict[str, threading.Lock] = {}


KEYS = {"ntfy": "ARLOTOPE_NOTIFY_NTFY", "webhook": "ARLOTOPE_NOTIFY_WEBHOOK", "link": "ARLOTOPE_NOTIFY_LINK"}


def config(lab: Lab) -> dict:
    env = labfiles.read_env(lab.lab / ".env.local")
    return {name: env[key] for name, key in KEYS.items() if env.get(key)}


def state_path(lab: Lab) -> Path:
    return lab.bus / "notified.json"


def items(lab: Lab) -> list[dict]:
    """The same actionable Inbox projection, available without a dashboard import."""
    from lab_attention import for_notifications
    return [it for it in for_notifications(lab) if it.get('sev') != 'info' and not it.get('seen')]


def link(cfg: dict, it: dict) -> str | None:
    base = cfg.get("link", "").rstrip("/")
    if not base:
        return None
    detail = it.get('detail') or {}
    if detail.get('checkpoint') and (detail.get('study') or it.get('idea')):
        return f"{base}/#/study/{urllib.parse.quote(detail.get('study') or it['idea'])}?checkpoint={urllib.parse.quote(detail['checkpoint'])}"
    if detail.get('artifact'):
        return f"{base}/#/artifacts/{urllib.parse.quote(detail['artifact'])}"
    if detail.get('panel'):
        return f"{base}/#/?" + urllib.parse.urlencode({'panel': detail['panel'], 'study': detail.get('study') or ''})
    if it.get("run_id"):
        return f"{base}/#/runs?run={urllib.parse.quote(it['run_id'])}"
    if detail.get("campaign"):
        return f"{base}/{profile.NOTIFY_PATH}"
    return f"{base}/#/"


def send(cfg: dict, it: dict, timeout: float = 8.0) -> list[str]:
    """Send one item to every configured channel. Returns the channels that failed."""
    title = str(it.get("title") or profile.NOTIFY_TITLE)[:200]
    body = str(it.get("body") or "")[:500]
    url = link(cfg, it)
    failed = []
    if cfg.get("ntfy"):
        headers = {"Title": title.encode("utf-8").decode("latin-1", "replace"), "Tags": "lizard",
                   "Priority": "high" if it.get("kind") in ("question", "permission") else "default"}
        if url:
            headers["Click"] = url
        try:
            req = urllib.request.Request(cfg["ntfy"], data=(body or title).encode("utf-8"), headers=headers,
                                         method="POST")
            urllib.request.urlopen(req, timeout=timeout).close()
        except (OSError, ValueError):
            failed.append("ntfy")
    if cfg.get("webhook"):
        text = f"*{title}*" + (f"\n{body}" if body else "") + (f"\n{url}" if url else "")
        try:
            req = urllib.request.Request(cfg["webhook"], data=json.dumps({"text": text, "content": text}).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=timeout).close()
        except (OSError, ValueError):
            failed.append("webhook")
    return failed


def check(lab: Lab, force: bool = False, *, wait: float = 0.01) -> list[dict]:
    """Send what's new (at most every CHECK_EVERY seconds per lab). Returns the items sent."""
    if not config(lab):
        return []
    try:
        with excl_lock(lab.bus / '.notify.lock', wait=wait):
            return _check(lab, force)
    except TimeoutError:
        return []


def _check(lab: Lab, force: bool) -> list[dict]:
    cfg = config(lab)
    key = str(lab.hub)
    if not (cfg.get("ntfy") or cfg.get("webhook")):
        return []
    if not force and time.time() - _last.get(key, 0) < CHECK_EVERY:
        return []
    _last[key] = time.time()
    channels = {name for name in ('ntfy', 'webhook') if cfg.get(name)}
    try:
        saved = json.loads(state_path(lab).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    delivered = saved.get('channels') or {iid: list(channels) for iid in saved.get('ids', [])}
    current = items(lab)
    pending = [it for it in current if channels - set(delivered.get(it['id'], []))]
    # A broken second channel must not starve items that have reached nobody yet.
    new = sorted(pending, key=lambda it: bool(delivered.get(it['id'])))[:MAX_PER_CHECK]
    out = []
    for it in new:
        remaining = channels - set(delivered.get(it['id'], []))
        failed = send({k: v for k, v in cfg.items() if k == 'link' or k in remaining}, it)
        reached = remaining - set(failed)
        if reached:
            delivered[it['id']] = sorted(set(delivered.get(it['id'], [])) | reached)
            out.append(it)
    if out:
        # Keep every still-pending item, even after a large burst. Prune only old resolved history.
        active = {it['id'] for it in current}
        keep = set(list(delivered)[-500:]) | active
        delivered = {iid: value for iid, value in delivered.items() if iid in keep}
        tmp = state_path(lab).with_suffix(".tmp")
        ids = [iid for iid, reached in delivered.items() if channels <= set(reached)]
        tmp.write_text(json.dumps({"ids": ids, "channels": delivered, "ts": now()}), encoding="utf-8")
        tmp.replace(state_path(lab))
    return out


def check_in_background(lab: Lab) -> None:
    """The scheduler's call: never blocks a tick, never overlaps itself."""
    busy = _busy.setdefault(str(lab.hub), threading.Lock())
    if not config(lab) or not busy.acquire(blocking=False):
        return

    def run():
        try:
            check(lab)
        except Exception:  # noqa: BLE001 — a notification must never break scheduling
            pass
        finally:
            busy.release()
    threading.Thread(target=run, daemon=True).start()
