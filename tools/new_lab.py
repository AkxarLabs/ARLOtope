"""Create an empty local Lab copy — what the dashboard's "Create a new lab" does.

    uv run --with pyyaml python tools/new_lab.py <dest> [--name "My lab"] [--projects-root ../my-lab-projects]

Normal installation is `git clone` followed by `arlo`. This optional local-copy helper exports this
checkout's committed files (`git archive HEAD`), creates private settings, and starts a separate Git
history. It does not copy local research or settings from the source Lab.
"""

from __future__ import annotations

import argparse
import io
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]
SKIP_TOP = {".github"}                      # the template's own CI is not the new lab's
EMPTY_KNOWLEDGE = {"FAILURES.md": "*(no failures recorded yet)*", "FINDINGS.md": "*(no findings yet)*",
                   "OPEN-QUESTIONS.md": "*(no open questions yet)*", "REFERENCES.md": "*(no references yet)*"}


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, timeout=120)


def _export(template: Path, dest: Path) -> int:
    """Write the template's committed tree into dest. Falls back to a filtered copy when the template
    is not a git checkout (e.g. a downloaded zip)."""
    n = 0
    if shutil.which("git") and (template / ".git").exists():
        r = _git(["archive", "--format=tar", "HEAD"], template)
        if r.returncode == 0:
            with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tf:
                for mem in tf.getmembers():
                    top = mem.name.split("/", 1)[0]
                    if top in SKIP_TOP or mem.name.startswith(("/", "..")) or ".." in Path(mem.name).parts:
                        continue
                    tf.extract(mem, dest, filter="data") if hasattr(tarfile, "data_filter") else tf.extract(mem, dest)
                    n += 1
            return n
    ignore = shutil.ignore_patterns(".git", ".bus", ".slots", "__pycache__", ".pytmp", ".pytest_cache", ".venv",
                                    "site", "assets-src", "*.pyc", ".env", ".env.*", "*.pem", "*.key", "settings.local.json")
    for item in template.iterdir():
        if item.name == 'lab':
            for rel in ('config.defaults.yaml', 'README.md', 'profiles', 'notebook/README.md', 'ideation/README.md'):
                source, target = item / rel, dest / 'lab' / rel
                if source.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                elif source.is_dir():
                    shutil.copytree(source, target, ignore=ignore)
            continue
        if item.name in SKIP_TOP or item.name in (".git", "site", ".venv", ".pytmp", ".pytest_cache", "output", "studies", "research", ".cache", ".playwright-cli") or item.name.startswith('.env'):
            continue
        if item.is_dir():
            shutil.copytree(item, dest / item.name, ignore=ignore)
        else:
            shutil.copy2(item, dest / item.name)
        n += 1
    return n


def _reset_state(dest: Path) -> None:
    nb = dest / "lab" / "notebook"
    for f in nb.glob("*.md") if nb.is_dir() else []:
        if f.name != "README.md":
            f.unlink()
    for d in ("lab/.bus", "lab/.slots", "lab/campaigns", "lab/records"):
        shutil.rmtree(dest / d, ignore_errors=True)
    (dest/'lab/identity.json').unlink(missing_ok=True)
    for d in (dest / "studies").iterdir() if (dest / "studies").is_dir() else []:
        if d.is_dir():
            shutil.rmtree(d)
    # the template may itself be someone's working lab: no studies (an empty journal and registry), an empty
    # knowledge base
    for rel in ("lab/journal.jsonl", "lab/approvals.jsonl", "lab/journal.jsonl.pre-kernel", "lab/approvals.jsonl.pre-kernel"):
        (dest / rel).unlink(missing_ok=True)
    import sys  # noqa: PLC0415
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kernel import studies  # noqa: PLC0415
    studies.render_registry(dest)
    for fname, empty in EMPTY_KNOWLEDGE.items():
        f = dest / "lab" / "knowledge" / fname
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8-sig")
        head = re.split(r"\n---\n", text, maxsplit=1)[0]
        f.write_text(f"{head}\n---\n\n{empty}\n", encoding="utf-8", newline="")


def _set_config(dest: Path, name: str | None, projects_root: str | None) -> None:
    import labfiles  # noqa: PLC0415
    labfiles.ensure_lab_files(dest)
    if err := labfiles.set_config(dest, {"lab.projects_root": projects_root, "lab.name": name and name[:80]}):
        raise ValueError(err)


def create_lab(dest: str | Path, name: str | None = None, projects_root: str | None = None,
               template: Path = HUB, commit: bool = True) -> dict:
    dest = Path(dest).expanduser().resolve()
    if dest.exists() and any(dest.iterdir()):
        return {"error": f"{dest} already exists and is not empty — pick a new folder"}
    if template.resolve() in (dest, *dest.parents):
        return {"error": "a new lab can't live inside the template itself"}
    dest.mkdir(parents=True, exist_ok=True)
    try:
        n = _export(template, dest)
        _reset_state(dest)
        _set_config(dest, name, projects_root or f"../{dest.name}-projects")
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(dest, ignore_errors=True)
        return {"error": f"could not create the lab: {e}"}
    out = {"ok": True, "path": str(dest), "files": n, "name": name or dest.name, "git": None}
    if shutil.which("git"):
        if _git(["init", "-q"], dest).returncode == 0:
            _git(["add", "-A"], dest)
            out["git"] = "initialized"
            if commit:
                r = _git(["commit", "-q", "-m", "Create an empty ARLOtope Lab"], dest)
                out["git"] = "committed" if r.returncode == 0 else \
                    "initialized (files staged — the first commit needs your git name/email)"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dest")
    ap.add_argument("--name")
    ap.add_argument("--projects-root")
    a = ap.parse_args()
    res = create_lab(a.dest, a.name, a.projects_root)
    print(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
