"""The shared I/O layer in tools/labfiles.py: atomic writes, JSONL appends, ids, numbers, and the one
place the per-user home folder is resolved."""

import os
import re
import sys
import threading
from pathlib import Path

import pytest

import labfiles
from conftest import REPO


def test_write_atomic_replaces_whole_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "a" / "b.json"
    labfiles.write_atomic(target, "one")                # creates the folder
    labfiles.write_atomic(target, b"two")
    assert target.read_bytes() == b"two"
    assert [p.name for p in target.parent.iterdir()] == ["b.json"]


def test_write_atomic_keeps_line_endings_exactly(tmp_path):
    target = tmp_path / "f.txt"
    labfiles.write_atomic(target, "a\r\nb\r\n")
    assert target.read_bytes() == b"a\r\nb\r\n"


def test_write_atomic_cleans_up_when_the_rename_fails(tmp_path, monkeypatch):
    target = tmp_path / "f.json"
    monkeypatch.setattr(labfiles.time, "sleep", lambda _s: None)

    def deny(_src, _dst):
        raise PermissionError("held by an indexer")

    monkeypatch.setattr(labfiles.os, "replace", deny)
    with pytest.raises(PermissionError):
        labfiles.write_atomic(target, "x")
    assert list(tmp_path.iterdir()) == []


def test_write_atomic_retries_a_transient_rename_denial(tmp_path, monkeypatch):
    target, real, calls = tmp_path / "f.json", os.replace, []
    monkeypatch.setattr(labfiles.time, "sleep", lambda _s: None)

    def flaky(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("busy")
        real(src, dst)

    monkeypatch.setattr(labfiles.os, "replace", flaky)
    labfiles.write_atomic(target, "ok")
    assert target.read_text() == "ok" and len(calls) == 3


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_write_json_private_is_owner_only_from_creation(tmp_path):
    target = tmp_path / "secret.json"
    labfiles.write_json(target, {"k": "v"}, private=True)
    assert target.stat().st_mode & 0o777 == 0o600
    assert labfiles.read_json(target) == {"k": "v"}


def test_read_json_defaults_when_missing_or_malformed(tmp_path):
    assert labfiles.read_json(tmp_path / "nope.json", {"d": 1}) == {"d": 1}
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert labfiles.read_json(tmp_path / "bad.json") is None


def test_concurrent_writers_never_leave_a_torn_file(tmp_path):
    target = tmp_path / "state.json"

    def writer(n):
        for i in range(25):
            labfiles.write_json(target, {"writer": n, "pad": "x" * 5000, "i": i})

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert labfiles.read_json(target)["pad"] == "x" * 5000
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_append_jsonl_adds_whole_lines_and_creates_folders(tmp_path):
    log = tmp_path / "deep" / "events.jsonl"
    assert labfiles.append_jsonl(log, {"n": 1, "text": "é"})
    assert labfiles.append_jsonl(log, {"n": 2, "when": Path("p")})      # non-JSON values are stringified
    assert [r["n"] for r in labfiles.read_jsonl(log)] == [1, 2]
    assert log.read_bytes().count(b"\n") == 2


def test_append_jsonl_is_best_effort_and_says_so(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert labfiles.append_jsonl(blocker / "events.jsonl", {"n": 1}) is False


@pytest.mark.skipif(os.name == "nt", reason="Windows has no atomic O_APPEND write")
def test_concurrent_appends_keep_every_line_intact(tmp_path):
    log = tmp_path / "events.jsonl"

    def writer(n):
        for i in range(60):
            labfiles.append_jsonl(log, {"w": n, "i": i, "pad": "y" * 9000})   # larger than a text-mode buffer

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(labfiles.read_jsonl(log)) == 240


def test_safe_id_is_a_bare_slug_or_none():
    assert labfiles.safe_id(" idea-1 ") == "idea-1"
    for bad in ("", "../x", "a/b", ".hidden", "a..b", "x" * 121, 7, None, ["a"]):
        assert labfiles.safe_id(bad) is None


def test_inside_rejects_escapes_and_symlinks(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.txt").write_text("x")
    assert labfiles.inside(root, root / "ok.txt")
    assert not labfiles.inside(root, root / ".." / "elsewhere.txt")
    try:
        (root / "link").symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        pytest.skip("no symlinks here")
    assert not labfiles.inside(root, root / "link")


def test_inside_refuses_a_network_or_device_path_before_touching_it(tmp_path, monkeypatch):
    """Resolving a UNC path makes Windows sign in to that host (an NTLM leak): refused without a look."""
    def touched(self, *a, **k):
        raise AssertionError(f"looked at {self}")
    monkeypatch.setattr(Path, "resolve", touched)
    monkeypatch.setattr(Path, "is_symlink", touched)
    for bad in (r"\\attacker.invalid\share\x", "//attacker.invalid/share/x", r"\\?\C:\x", r"\\.\pipe\x"):
        assert not labfiles.inside(tmp_path, bad)
        assert not labfiles.inside(tmp_path, tmp_path / bad)


def test_numbers_fall_back_on_junk_and_non_finite():
    assert labfiles.pos_int("7", 1, 0) == 7 and labfiles.pos_int("x", 3, 0) == 3 and labfiles.pos_int(-4, 1, 2) == 2
    assert labfiles.pos_float("2.5", 0.0) == 2.5
    for bad in ("nan", float("inf"), "-inf", None, "x"):
        assert labfiles.pos_float(bad, 9.0) == 9.0


def test_now_formats_an_epoch():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", labfiles.now())
    assert labfiles.parse_ts(labfiles.now(1_700_000_000)) == pytest.approx(1_700_000_000, abs=1)


def test_home_honours_arlotope_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARLOTOPE_HOME", str(tmp_path / "h"))
    assert labfiles.arlotope_home() == tmp_path / "h"
    assert labfiles.home_path("workers", "x.json") == tmp_path / "h" / "workers" / "x.json"
    monkeypatch.delenv("ARLOTOPE_HOME")
    assert labfiles.arlotope_home() == Path.home() / ".arlotope"


def test_registries_in_the_home_folder_skip_junk_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("ARLOTOPE_HOME", str(tmp_path))
    assert labfiles.home_rows("machines") == []
    labfiles.save_home_rows("machines", [{"id": "a"}, "junk", {"id": "b"}])
    assert [m["id"] for m in labfiles.home_rows("machines")] == ["a", "b"]
    (tmp_path / "labs.json").write_text("[]", encoding="utf-8")        # not the {labs: [...]} shape
    assert labfiles.home_rows("labs") == []


HOME_LITERAL = re.compile(r"Path\.home\(\)[^\n]*arlotope|environ[^\n]*ARLOTOPE_HOME|~/\.arlotope", re.I)
# the code that must stay standalone (hooks and scripts copied into projects) never resolves the home
SKIP = {REPO / "tools" / "labfiles.py", Path(__file__).resolve()}


def test_the_home_folder_is_resolved_in_one_place():
    code = [*(REPO / "tools").rglob("*.py"), *(REPO / "dashboard").glob("*.py"), REPO / "arlo.py"]
    offenders = []
    for path in code:
        if path in SKIP:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HOME_LITERAL.search(line) and not line.lstrip().startswith(("#", '"""')):
                offenders.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:100]}")
    assert offenders == [], "resolve the home with labfiles.arlotope_home()/home_path()"


def test_procs_hide_the_console_and_decode_text_as_utf8():
    from executor import procs
    code = "import sys; sys.stdout.buffer.write(b'caf" + chr(92) + "xc3" + chr(92) + "xa9 " + chr(92) + "xff')"
    out = procs.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout == "café �"                          # bad bytes are replaced, never raised
    assert (procs._defaults({}).get("creationflags", 0) != 0) == (os.name == "nt")
    assert procs._defaults({"text": True})["errors"] == "replace"
