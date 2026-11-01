"""Preview or assemble the ARLOtope website. Standard library only.

    python site/pages.py serve [--port 8000]            preview at http://127.0.0.1:8000/
    python site/pages.py build OUT [--docs build/docs]  the folder GitHub Pages publishes

The lab demo is the dashboard's own lab frame, so the site borrows those files from dashboard/static
instead of keeping copies: `serve` maps static/ onto dashboard/static/ as it runs, and `build` copies
the same files. Built docs go under docs/, with redirect stubs where their pages used to be. See
site/DESIGN.md, section 8.
"""
from __future__ import annotations

import argparse
import http.server
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE, STATIC = ROOT / "site", ROOT / "dashboard" / "static"
SITE_ONLY = {"DESIGN.md", "pages.py"}          # in site/ but not published
FONTS = ["newsreader-opsz-normal.woff2", "newsreader-opsz-italic.woff2", "instrument-sans-wght-normal.woff2",
         "instrument-sans-wght-italic.woff2", "ibm-plex-mono-400.woff2", "ibm-plex-mono-500.woff2",
         "OFL-newsreader.txt", "OFL-instrument-sans.txt", "OFL-ibm-plex-mono.txt"]
# What the page and the lab frame read from dashboard/static: nothing else is served or published.
BORROWED = ["lab-view.html", "agent-view.js", "world3d", "brand", "vendor/three", "ui/ui.css", "ui/research.css",
            "ui/lab-view.js", "ui/workflow-default.js", *("vendor/fonts/" + f for f in FONTS)]
ROOMS_START, ROOMS_END = "<!-- arlotope:rooms3d -->", "<!-- /arlotope:rooms3d -->"


def borrowed(rel: str) -> bool:
    return any(rel == b or rel.startswith(b + "/") for b in BORROWED)


def lab_frame() -> bytes:
    """lab-view.html with its room scripts listed, as dashboard/serve.py's _with_rooms3d does."""
    html = (STATIC / "lab-view.html").read_text(encoding="utf-8")
    tags = "\n".join(f'<script src="world3d/rooms/{f.name}"></script>' for f in sorted((STATIC / "world3d" / "rooms").glob("*.js")))
    i, j = html.index(ROOMS_START), html.index(ROOMS_END) + len(ROOMS_END)
    return (html[:i] + tags + html[j:]).encode("utf-8")


def serve(port: int, docs: Path) -> None:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, path: str) -> str:
            rel = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
            if rel.startswith("static/"):
                rel = rel[len("static/"):]
                return str(STATIC / rel) if borrowed(rel) else str(SITE / "missing")
            if rel.startswith("docs/"):
                return str(docs / rel[len("docs/"):])
            return str(SITE / "missing") if rel in SITE_ONLY else str(SITE / rel)

        def do_GET(self) -> None:
            if self.path.split("?", 1)[0] == "/static/lab-view.html":
                body = lab_frame()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def end_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    with http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"ARLOtope website: http://127.0.0.1:{httpd.server_address[1]}/  (docs from {docs})", flush=True)
        httpd.serve_forever()


def build(out: Path, docs: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SITE, out, ignore=lambda d, names: [n for n in names if Path(d) == SITE and n in SITE_ONLY])
    for rel in BORROWED:
        src, dst = STATIC / rel, out / "static" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
    (out / "static" / "lab-view.html").write_bytes(lab_frame())
    if not docs.is_dir():
        raise SystemExit(f"no built docs at {docs}: run `properdocs build` first")
    shutil.copytree(docs, out / "docs")
    # The docs used to be the Pages root: leave a pointer where each of their pages was.
    for page in (out / "docs").rglob("index.html"):
        rel = page.parent.relative_to(out / "docs").as_posix()
        if rel == "." or (out / rel).exists():
            continue
        target = "../" * (rel.count("/") + 1) + f"docs/{rel}/"
        (out / rel).mkdir(parents=True)
        (out / rel / "index.html").write_text(
            f'<!doctype html><meta charset="utf-8"><title>Moved to the docs</title>'
            f'<meta http-equiv="refresh" content="0; url={target}"><link rel="canonical" href="{target}">'
            f'<p>This page moved to <a href="{target}">the docs</a>.</p>\n', encoding="utf-8")
    if (out / "docs" / "404.html").exists():
        shutil.copy2(out / "docs" / "404.html", out / "404.html")
    print(f"built {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="preview the site")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--docs", type=Path, default=None, help="docs to serve under /docs/ (default: build/docs if built, else docs/)")
    b = sub.add_parser("build", help="assemble the folder Pages publishes")
    b.add_argument("out", type=Path)
    b.add_argument("--docs", type=Path, default=ROOT / "build" / "docs")
    a = ap.parse_args()
    if a.cmd == "serve":
        serve(a.port, (a.docs or (ROOT / "build" / "docs" if (ROOT / "build" / "docs").is_dir() else ROOT / "docs")).resolve())
    else:
        build(a.out.resolve(), a.docs.resolve())


if __name__ == "__main__":
    main()
