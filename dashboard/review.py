"""What the PI reads: a checkpoint's evidence (its `evidence:` in workflow/workflows/), a run's artifacts, the lab's
knowledge, and the claims map.
"""

from __future__ import annotations

import re
from pathlib import Path

import ctx  # noqa: E402
import sources  # noqa: E402

executor = sources.executor   # tools/executor, or None


_DOC_CLIP = 16000   # never stream a whole repo — clip each file


def _read_clip(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    txt = path.read_text(encoding="utf-8-sig", errors="replace")
    return txt if len(txt) <= _DOC_CLIP else txt[:_DOC_CLIP] + "\n\n… (clipped; open the file for the rest)"


def _filesec(title: str, f: Path, fallback: str = "") -> dict:
    """A doc-viewer section for a real file: its clipped text plus an absolute `path` (when the file
    exists) so the frontend can offer an 'open in editor' deep-link. The dashboard is local-only."""
    sec = {"title": title, "text": _read_clip(f) or fallback}
    if f.exists() and f.is_file():
        sec["path"] = str(f.resolve())
    return sec


def _checkpoint_bundle(slug: str, cid: str) -> dict:
    """What the PI reads at a checkpoint: its evidence files (its `evidence:`), each in full
    (a folder: its Markdown files)."""
    cps = ctx.tool("kernel").checkpoints
    try:
        cp = cps.find(ctx.HUB, slug, cid)
    except cps.CheckpointError as e:
        return {"error": str(e)}
    secs = []
    for ev in cps.evidence(ctx.HUB, slug, cp):
        f = Path(ev["path"]) if Path(ev["path"]).is_absolute() else ctx.HUB / ev["path"]
        if f.is_dir():
            for g in sorted(f.rglob("*.md"))[:12]:
                secs.append(_filesec(g.relative_to(ctx.HUB).as_posix() if g.is_relative_to(ctx.HUB) else g.name, g))
        elif f.suffix.lower() in (".md", ".yaml", ".yml", ".txt", ".jsonl", ".json"):
            secs.append(_filesec(ev["path"], f, "(not written yet)"))
        elif f.exists():
            secs.append({"title": ev["path"], "text": f"({f.suffix or 'file'}; open it from the Library)", "path": str(f.resolve())})
    return {"ok": True, "title": f"{cp['title']} · {slug}", "sections": secs}


def _as_list(v) -> list:
    """Coerce a YAML scalar to a one-item list — so a hand-edited `artifacts: foo` / `numbers: "0.9"`
    (a string written where a list belongs) isn't iterated character-by-character."""
    if isinstance(v, list):
        return v
    return [v] if v not in (None, "") else []


def _within(base: Path | None, target: Path) -> bool:
    """True iff `target` resolves to inside `base` — a cheap containment guard so a claim artifact
    like `../../x` can't surface an out-of-project absolute path as an openable editor link."""
    if not base:
        return False
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def _claim_project_dir(c: dict, slug: str) -> Path | None:
    # project_path is a documented override for /adopt or oddly-located projects, so it is NOT
    # contained to projects_root — it points wherever the PI's project actually lives.
    pp = str(c.get("project_path") or "").strip()
    if pp:
        p = Path(pp)
        return p if p.is_absolute() else (ctx.HUB / p).resolve()
    return ctx.pdir(c.get("project") or slug)


def claims_map(idea: str | None = None) -> dict:
    slug = ctx.slug(idea or "")
    if not slug:
        return {"error": "no study given"}
    cfile = ctx.HUB / "studies" / slug / "paper" / "claims.yaml"
    if not cfile.exists():
        return {"error": f"no claims.yaml at studies/{slug}/paper/claims.yaml"}
    doc = ctx.labfiles.load_yaml(cfile)
    if not isinstance(doc, dict):        # a malformed top-level scalar/list → empty map, never a 500
        doc = {}
    claims_in = doc.get("claims")
    if not isinstance(claims_in, list):  # the schema's top-level `claims:` is a list; anything else → none
        claims_in = []
    archive = ctx.HUB / "studies" / slug / "paper" / "artifacts"
    out = []
    for c in claims_in:
        if not isinstance(c, dict):      # count parity: sources._claims_count also counts dict items only
            continue
        proj = str(c.get("project") or slug)
        pdir = _claim_project_dir(c, slug)
        arts = []
        for rel in _as_list(c.get("artifacts")):
            rel = str(rel).replace("\\", "/")
            info = {"rel": rel, "exists": False}
            target = None
            live = (pdir / rel) if pdir else None
            if live and live.exists() and _within(pdir, live):                  # must stay inside its project
                target = live
            elif (archive / rel).exists() and _within(archive, archive / rel):  # hub archive (locked at /finalize)
                target = archive / rel
            if target:
                info.update(exists=True, abs=str(target.resolve()))
                mm = re.match(r"runs/([^/]+)/", rel)                            # a run artifact → peekable in the doc viewer
                if mm and mm.group(1) not in ("..", "."):
                    info.update(project=proj, run_id=mm.group(1))
            arts.append(info)
        out.append({
            "id": str(c.get("id") or ""), "claim": str(c.get("claim") or ""),
            "numbers": [str(n) for n in _as_list(c.get("numbers"))],
            "metric": str(c.get("metric") or ""), "location": str(c.get("location") or ""),
            "derivation": str(c.get("derivation") or ""), "project": proj,
            "has_hashes": bool(c.get("artifact_sha256")), "artifacts": arts,
            "linked": bool(arts) and all(a["exists"] for a in arts),
        })
    return {"ok": True, "title": f"{slug} · claims ↔ artifacts", "n": len(out),
            "claims_path": str(cfile.resolve()), "claims": out}


def read_doc(what: str, idea: str | None = None, run: str | None = None, checkpoint: str | None = None) -> dict:
    if what == "run":
        slug, rid = ctx.slug(idea or ""), ctx.slug(run or "")
        if not slug or not rid:
            return {"error": "need a project + run id"}
        pdir = ctx.pdir(slug)
        if not pdir:
            return {"error": f"no project dir for {slug}"}
        rdir = pdir / "runs" / rid
        secs = []
        for fn in ("metrics.json", "meta.json", "config.yaml"):
            f = rdir / fn
            if f.exists():
                secs.append(_filesec(f"runs/{rid}/{fn}", f))
        stream = rdir / "metrics.jsonl"
        if stream.exists():
            lines = [ln for ln in _read_clip(stream).splitlines() if ln.strip()]
            if lines:
                secs.append({"title": f"runs/{rid}/metrics.jsonl · last {min(8, len(lines))} of {len(lines)}",
                             "text": "\n".join(lines[-8:]), "path": str(stream.resolve())})
        if not secs:
            return {"error": f"no artifacts under {slug}/runs/{rid} (runs are gitignored; the project may be elsewhere)"}
        return {"ok": True, "title": f"{slug} · {rid}", "sections": secs}

    if what == "knowledge":
        secs = []
        for name in ("FINDINGS", "FAILURES", "OPEN-QUESTIONS", "REFERENCES"):
            secs.append(_filesec(name.replace("-", " ").title(),
                                 ctx.LAB / "knowledge" / f"{name}.md", "(none recorded yet)"))
        nb_dir = ctx.LAB / "notebook"
        entries = sorted(nb_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True) if nb_dir.exists() else []
        dated = [f for f in entries if f.name.lower() != "readme.md"]
        latest = (dated or entries)[0] if (dated or entries) else None
        if latest:
            secs.append(_filesec("Latest notebook entry · " + latest.name, latest))
        return {"ok": True, "title": "Lab knowledge", "sections": secs}

    if what == "checkpoint":
        slug, cid = ctx.slug(idea or ""), ctx.slug(checkpoint or "")
        if not slug or not cid:
            return {"error": "which study and checkpoint?"}
        return _checkpoint_bundle(slug, cid)
    return {"error": f"unknown document '{what}'"}
