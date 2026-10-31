"""The journal: one append-only record of what happened to the lab's studies — lab/journal.jsonl.

Every line is an event {ts, study, kind, by, …}; `study` is a study's slug, or "lab" for the lab itself.

    new        {workflow, title, step}             a study was filed
    move       {from, to, outcome?, note?}         it moved to another step (or a shelf)
    wait       {at, to?, outcome, checkpoint?}     it is waiting: for a checkpoint's approval, or for the PI to
                                                   say where an outcome leads (no checkpoint)
    finish     {}                                  it finished its workflow's last step
    approval   {checkpoint, decision, via, note?}  the PI's decision (approved | changes-requested | revoked)
    workflow   {workflow}                          it follows another workflow from now on
    use        {use}                               its own procedure swaps ({lit-review: lit-review-quick})
    project    {path}                              where its project repository is
    remap      {map}  (study "lab")                steps were renamed: {old id: new id}

`by` says who: pi · run:<id> · campaign:<name> · auto · cli. Only the kernel writes here (the
signature guard refuses everything else); the state of every study is a fold over these lines, and
lab/REGISTRY.md is a view of that fold, written after every event. Extensions add kinds of their own, named
`<extension>:<kind>`; the fold ignores what it doesn't know.

An approval counts only when the kernel signed it, outside any agent run, with the per-user key in the ARLOtope
home (`journal.key`, owner-only, never in a run's environment) — and only once, so an old line appended again
approves nothing. An agent that appends a line approves nothing either. Refusals and revocations count unsigned
(they only hold work back), as do a study's `auto` approvals (a run's own `arlo move` records them; only an
`auto` checkpoint takes one).
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

import labfiles

REL = Path("lab") / "journal.jsonl"
KEY = "journal.key"
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,120}$")
DECISIONS = ("approved", "revoked", "changes-requested")
MAX_NOTE = 2000
_cache: dict[str, tuple[tuple, list[dict]]] = {}


def path(hub) -> Path:
    return Path(hub) / REL


def events(hub, study: str | None = None, kinds: tuple[str, ...] | None = None) -> list[dict]:
    """Every event, oldest first (a torn or malformed line is skipped, never fatal)."""
    p = path(hub)
    try:
        stt = p.stat()
        sig = (stt.st_size, stt.st_mtime_ns)
    except OSError:
        return []
    hit = _cache.get(str(p))
    if hit and hit[0] == sig:
        evs = hit[1]
    else:
        evs, key, signed = [], None, set()
        try:
            text = p.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            text = ""
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                e = json.loads(ln)
            except ValueError:
                continue
            if not (isinstance(e, dict) and isinstance(e.get("kind"), str) and isinstance(e.get("study"), str)):
                continue
            if _signed_only(e):
                key = key or _key()
                mac = e.get("sig")
                if not key or not isinstance(mac, str) or mac in signed or not hmac.compare_digest(mac, _sign(key, e)):
                    continue
                signed.add(mac)
            evs.append(e)
        _cache[str(p)] = (sig, evs)
    if study is not None:
        evs = [e for e in evs if e["study"] == study]
    if kinds is not None:
        evs = [e for e in evs if e["kind"] in kinds]
    return list(evs)


def append(hub, study: str, kind: str, by: str, **fields) -> dict:
    """Write one event (a single write per line: no torn records). Callers are the kernel's own actions."""
    for name, v in (("study", study), ("kind", kind), ("by", by)):
        if not isinstance(v, str) or not ID.match(v) or ".." in v:
            raise ValueError(f"invalid {name}: {v!r}")
    ev = {"ts": labfiles.now(), "study": study, "kind": kind, "by": by}
    for k, v in fields.items():
        if v is None or v == "" or k in ev:
            continue
        ev[k] = str(v)[:MAX_NOTE] if k == "note" else v
    if kind == "approval" and not os.environ.get("ARLOTOPE_RUN_ID"):
        key = _key(create=True)
        if not key:
            raise OSError(f"can't sign the approval: {labfiles.home_path(KEY)} is unreadable")
        ev["sig"] = _sign(key, ev)
    p = path(hub)
    p.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
    return ev


def _key(create: bool = False) -> bytes | None:
    """The per-user key approvals are signed with (made, owner-only, on the first approval), or None."""
    p = labfiles.home_path(KEY)
    if create and not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(FileExistsError):      # two first approvals at once: one key, the other reads it
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.write(fd, secrets.token_hex(32).encode("ascii"))
            finally:
                os.close(fd)
    try:
        key = bytes.fromhex(p.read_text(encoding="ascii"))
    except (OSError, ValueError):
        return None
    return key if len(key) == 32 else None


def _sign(key: bytes, ev: dict) -> str:
    body = json.dumps({k: v for k, v in ev.items() if k != "sig"}, sort_keys=True, ensure_ascii=False)
    return hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()


def _signed_only(e: dict) -> bool:
    """An approval counts only when signed — unless it is a study checkpoint's `auto` one."""
    return e["kind"] == "approval" and e.get("decision") == "approved" and (e.get("by") != "auto" or e["study"] == "lab")


# ── the fold: where every study stands ───────────────────────────────────────────────────────────
def _blank(slug: str) -> dict:
    return {"id": slug, "title": "", "workflow": None, "step": None, "since": None, "created": None,
            "updated": None, "finished": False, "waiting": None, "was": None, "project": None, "use": {},
            "approvals": {}}


def fold(evs: list[dict], shelves=("parked", "killed")) -> dict[str, dict]:
    """{slug: where it stands} from events, in order."""
    out: dict[str, dict] = {}
    for e in evs:
        k, slug = e["kind"], e["study"]
        if slug == "lab":
            if k == "remap" and isinstance(e.get("map"), dict):
                mp = e["map"]
                for s in out.values():
                    s["step"] = mp.get(s["step"], s["step"])
                    s["was"] = mp.get(s["was"], s["was"])
                    if s.get('entry'):
                        s['entry'] = dict(s['entry'], tasks={mp.get(k, k): v for k, v in s['entry']['tasks'].items()})
                    if s["waiting"]:
                        s["waiting"] = dict(s["waiting"], at=mp.get(s["waiting"].get("at"), s["waiting"].get("at")),
                                            to=mp.get(s["waiting"].get("to"), s["waiting"].get("to")))
            continue
        if k == "new":
            out.setdefault(slug, _blank(slug))
        s = out.get(slug)
        if s is None:                          # only `new` files a study; anything else about an unknown one waits
            continue
        s["updated"] = e.get("ts")
        if k == "new":
            s.update(workflow=e.get("workflow") or s["workflow"], title=e.get("title") or s["title"],
                     step=e.get("step"), since=e.get("ts"), created=s["created"] or e.get("ts"), finished=False)
            if e.get('entry'):
                s['entry'] = e['entry']
        elif k == 'entry-cancelled':
            s['entry_cancelled'] = True
        elif k == "move":
            if e.get("to") in shelves and s["step"] not in shelves:
                s["was"] = s["step"]
            s.update(step=e.get("to"), since=e.get("ts"), waiting=None, finished=False)
        elif k == "wait":
            s["waiting"] = {x: e.get(x) for x in ("at", "to", "outcome", "checkpoint", "note", "ts", "by")}
        elif k == "finish":
            s.update(finished=True, waiting=None)
        elif k == "approval":
            s["approvals"][e.get("checkpoint")] = e
        elif k == "workflow":
            s["workflow"] = e.get("workflow") or s["workflow"]
        elif k == "use":
            s["use"] = dict(e.get("use") or {})
        elif k == "project":
            s["project"] = e.get("path") or None
        elif k == "title":
            s["title"] = e.get("title") or s["title"]
    return out


# ── approvals: the PI's decisions, as journal events ─────────────────────────────────────────────
def approvals(hub, study: str | None = None, checkpoint: str | None = None) -> list[dict]:
    """Every decision, oldest first: {ts, study, checkpoint, decision, by, via, note?}."""
    out = []
    for e in events(hub, study, ("approval",)):
        if e.get("decision") in DECISIONS and (checkpoint is None or e.get("checkpoint") == checkpoint):
            out.append(e)
    return out


def latest(hub, study: str, checkpoint: str) -> dict | None:
    rs = approvals(hub, study, checkpoint)
    return rs[-1] if rs else None


def approved(hub, study: str, checkpoint: str) -> bool:
    r = latest(hub, study, checkpoint)
    return bool(r) and r.get("decision") == "approved"


def decisions(hub, study: str) -> dict[str, dict]:
    """{checkpoint: its latest decision} for one study."""
    out: dict[str, dict] = {}
    for r in approvals(hub, study):
        out[r.get("checkpoint")] = r
    return out


def notes(hub, study: str) -> list[dict]:
    """The PI's notes to agents in force for a study: the note on each approval still standing."""
    return [{"checkpoint": cp, "note": r.get("note"), "by": r.get("by"), "ts": r.get("ts")}
            for cp, r in decisions(hub, study).items() if r.get("decision") == "approved" and r.get("note")]


def when(rec: dict | None) -> str:
    return str((rec or {}).get("ts") or "")[:16].replace("T", " ")
