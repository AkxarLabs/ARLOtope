"""Open a visible terminal window on this machine running one command — for the things a CLI must do
with the person at the keyboard (signing in, installing). The dashboard asks for a *purpose*, never a
command: every command line here is fixed, so a web page can't make this machine run anything else.

    uv run python tools/terminal.py login claude      # opens a window running `claude auth login`

The window stays open after the command finishes so its output can be read. Credentials are typed into
the CLI's own login flow (usually a browser page); nothing here sees them.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# purpose → how to phrase the command for a backend (the resolved CLI path is filled in)
LOGIN = {"claude": ["auth", "login"], "codex": ["login"], "opencode": ["auth", "login"]}
INSTALL = {
    "claude": {"win32": "powershell -NoProfile -ExecutionPolicy Bypass -Command \"irm https://claude.ai/install.ps1 | iex\"",
               "*": "curl -fsSL https://claude.ai/install.sh | bash"},
    "codex": {"*": "npm install -g @openai/codex"},
    "opencode": {"*": "npm install -g opencode-ai"},
}
TITLE = "ARLOtope"


def install_command(backend: str) -> str | None:
    table = INSTALL.get(backend) or {}
    return table.get(sys.platform) or table.get("*")


def login_argv(backend: str, cli: list[str]) -> list[str] | None:
    if backend not in LOGIN or not cli:
        return None
    return [*cli, *LOGIN[backend]]


def _plain(title: str) -> str:
    """A window title with nothing a shell could read as syntax (it may come from a machine's name)."""
    return re.sub(r"[^\w .,'()\-—]", " ", str(title))[:80].strip() or TITLE


def hold(title: str, argv: list[str]) -> int:
    """Run argv in this console and keep the window open after it ends (Windows: no cmd.exe in between, so
    the arguments reach the program exactly as given)."""
    if sys.platform == "win32":
        try:
            import ctypes  # noqa: PLC0415
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except (OSError, AttributeError):
            pass
    try:
        code = subprocess.call(argv)
    except OSError as e:
        print(f"could not run {argv[0]}: {e}")
        code = 127
    try:
        input("\n(finished - press Enter to close this window)")
    except EOFError:
        pass
    return code


def open_terminal(command: str | list[str], cwd: str | Path | None = None, *, title: str = TITLE) -> dict:
    """Start a new, visible console window running `command`; returns {"ok", "how"} or {"error"}."""
    cwd, title = str(cwd or Path.home()), _plain(title)
    if sys.platform == "win32":
        # a NEW console (not this server's) that stays open so the result can be read. An argv runs through
        # hold() — never re-quoted for cmd.exe, which would mangle nested quotes; a fixed command line (the
        # installers above, with their pipes) runs under cmd /k.
        flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)
        run = ([sys.executable, str(Path(__file__).resolve()), "hold", title, "--", *command] if isinstance(command, list)
               else ["cmd.exe", "/k", f"title {title} & {command}"])
        try:
            subprocess.Popen(run, cwd=cwd, creationflags=flags, close_fds=True)
        except OSError as e:
            return {"error": f"could not open a console window: {e}"}
        return {"ok": True, "how": "a new console window"}
    line = command if isinstance(command, str) else " ".join(shlex.quote(a) for a in command)
    script = f"cd {shlex.quote(cwd)} && {line}; echo; echo '(you can close this window)'"
    if sys.platform == "darwin":
        osa = ('tell application "Terminal"\nactivate\ndo script ' +
               '"' + script.replace("\\", "\\\\").replace('"', '\\"') + '"\nend tell')
        try:
            subprocess.Popen(["osascript", "-e", osa], close_fds=True)
        except OSError as e:
            return {"error": f"could not open Terminal: {e}"}
        return {"ok": True, "how": "a new Terminal window"}
    keep = f"{script}; exec bash"
    for exe, args in (("x-terminal-emulator", ["-e", "bash", "-lc", keep]),
                      ("gnome-terminal", ["--", "bash", "-lc", keep]),
                      ("konsole", ["-e", "bash", "-lc", keep]),
                      ("xfce4-terminal", ["-x", "bash", "-lc", keep]),
                      ("xterm", ["-T", title, "-e", "bash", "-lc", keep])):
        if shutil.which(exe):
            try:
                subprocess.Popen([exe, *args], close_fds=True, start_new_session=True)
            except OSError:
                continue
            return {"ok": True, "how": f"a new {exe} window"}
    return {"error": "no terminal emulator found — run the command yourself: " + line}


def main() -> int:
    if len(sys.argv) >= 4 and sys.argv[1] == "hold" and sys.argv[3] == "--":
        return hold(sys.argv[2], sys.argv[4:])
    if len(sys.argv) < 3 or sys.argv[1] not in ("login", "install"):
        print(__doc__)
        return 2
    purpose, backend = sys.argv[1], sys.argv[2]
    if purpose == "install":
        cmd = install_command(backend)
        res = open_terminal(cmd) if cmd else {"error": f"no install command for {backend}"}
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from executor import backends
        argv = login_argv(backend, backends.resolve_cli(backend, {}) or [])
        res = open_terminal(argv) if argv else {"error": f"{backend} is not installed"}
    print(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())
