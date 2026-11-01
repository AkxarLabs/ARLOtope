"""`scripts/compare.py digest`: the bounded state card an experiment session reads instead of the raw ledger."""

from __future__ import annotations

import shutil
import subprocess
import sys

from conftest import REPO

ENTRY = """## exp-{n:03d} attempt 1 — 2026-01-01 10:00
**Config:** configs/experiments/exp-{n:03d}.yaml · **Run id(s):** r{n}
**Parent:** exp-{p:03d} (operator: improve)
**Outcome:** metric {n}
**Decision:** keep
"""


def _digest(tmp_path, *args):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(REPO / "templates" / "project" / "scripts" / "compare.py", scripts / "compare.py")
    return subprocess.run([sys.executable, str(scripts / "compare.py"), "digest", *args],
                          capture_output=True, text=True, encoding="utf-8").stdout


def test_digest_keeps_the_last_entries_the_kill_criteria_and_the_notes_headings(tmp_path):
    (tmp_path / "EXPERIMENT_LOG.md").write_text("# Log\n\n" + "".join(ENTRY.format(n=n, p=n - 1) for n in range(1, 6)),
                                                encoding="utf-8")
    (tmp_path / "PLAN.md").write_text("## Kill criteria\n\n<!-- hint -->\nkill if exp-003 < 0.1\n\n## Experiments\nrows\n",
                                      encoding="utf-8")
    (tmp_path / "NOTES.md").write_text("# Notes\n## Tried & abandoned\ntext that is not a heading\n", encoding="utf-8")
    out = _digest(tmp_path, "--last", "2")
    assert "last 2 entries" in out and "exp-004 attempt 1" in out and "exp-005 attempt 1" in out
    assert "exp-003 attempt 1" not in out and "exp-002 (operator: improve)" not in out and "exp-003 (operator: improve)" in out
    assert "kill if exp-003 < 0.1" in out and "hint" not in out and "rows" not in out
    assert "- Tried & abandoned" in out and "not a heading" not in out


def test_digest_of_an_empty_project_is_still_readable(tmp_path):
    out = _digest(tmp_path)
    assert "last 0 entries" in out and "Kill criteria" in out and "NOTES.md headings" in out
