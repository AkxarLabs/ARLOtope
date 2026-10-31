"""Bounded interactive process I/O shared by the dashboard and project worker."""
import base64
import os
import secrets
import subprocess
import threading
import time

MAX_BUF = 1 << 20

def has_pty():
    return os.name == "posix"

class Session:
    @classmethod
    def open(cls, sessions, argv, cwd, purpose, *, request_id=None, limit=8, cols=100, rows=28):
        """Caller holds its session lock. Repeated creation requests return the same process."""
        if request_id is not None:
            if not isinstance(request_id, str) or len(request_id) != 32 or any(c not in '0123456789abcdef' for c in request_id):
                raise ValueError('Invalid terminal request ID.')
            for session in sessions.values():
                if getattr(session, 'request_id', None) == request_id:
                    if (session.argv, session.cwd, session.purpose) != (argv, cwd, purpose):
                        raise ValueError('This terminal request belongs to another command.')
                    return session, False
        if sum(not s.exited for s in sessions.values()) >= limit:
            raise ValueError('Close an existing terminal first.')
        session = cls(argv, cwd, purpose, cols, rows)
        session.request_id = request_id
        sessions[session.id] = session
        return session, True

    def __init__(self, argv: list[str], cwd: str, purpose: str, cols: int = 100, rows: int = 28):
        self.id = secrets.token_hex(8)
        self.argv, self.cwd, self.purpose = argv, cwd, purpose
        self.buf = bytearray()
        self.base = 0                  # absolute offset of buf[0]
        self.lock = threading.Lock()
        self.exited, self.code, self.ended = False, None, None
        self.master = None
        env = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor", "ARLOTOPE_TERMINAL": "1"}
        if has_pty():
            import pty
            master, slave = pty.openpty()
            self._winsize(slave, cols, rows)
            self.proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=slave, stdout=slave, stderr=slave,
                                         start_new_session=True, close_fds=True)
            os.close(slave)
            self.master = master
        else:
            from executor.procs import popen
            self.proc = popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, bufsize=0)
        threading.Thread(target=self._pump, daemon=True).start()

    @staticmethod
    def _winsize(fd, cols, rows):
        try:
            import fcntl
            import struct
            import termios
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", max(2, rows), max(10, cols), 0, 0))
        except Exception:  # noqa: BLE001
            pass

    def _append(self, data: bytes) -> None:
        with self.lock:
            self.buf += data
            over = len(self.buf) - MAX_BUF
            if over > 0:
                del self.buf[:over]
                self.base += over

    def _pump(self) -> None:
        try:
            while True:
                if self.master is not None:
                    try:
                        chunk = os.read(self.master, 65536)
                    except OSError:       # EIO: the child closed the PTY
                        chunk = b""
                else:
                    chunk = self.proc.stdout.read1(65536) if hasattr(self.proc.stdout, "read1") else self.proc.stdout.read(4096)
                    if chunk:   # a pipe has no line discipline: give xterm the CRs it expects
                        chunk = chunk.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                if not chunk:
                    break
                self._append(chunk)
        finally:
            try:
                self.code = self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.code = None
            self.exited, self.ended = True, time.time()
            self._append(f"\r\n\x1b[2m[finished{'' if self.code in (0, None) else f' with exit code {self.code}'}]\x1b[0m\r\n".encode())
            if self.master is not None:
                try:
                    os.close(self.master)
                except OSError:
                    pass

    def read(self, offset: int) -> dict:
        with self.lock:
            start = max(offset, self.base)
            data = bytes(self.buf[start - self.base:])
            end = self.base + len(self.buf)
        return {"ok": True, "data": base64.b64encode(data).decode("ascii"), "offset": end,
                "skipped": start - offset if offset < self.base else 0, "exited": self.exited, "code": self.code}

    def write(self, data: str) -> None:
        if self.exited:
            return
        raw = data.encode("utf-8")
        if self.master is not None:
            os.write(self.master, raw)
        else:
            self.proc.stdin.write(raw.replace(b"\r", b"\r\n") if raw.endswith(b"\r") else raw)
            self.proc.stdin.flush()

    def resize(self, cols: int, rows: int) -> None:
        if self.master is not None:
            self._winsize(self.master, cols, rows)

    def close(self) -> None:
        if not self.exited:
            try:
                from executor.procs import kill_tree
                kill_tree(self.proc.pid)
            except Exception:  # noqa: BLE001
                try:
                    self.proc.kill()
                except OSError:
                    pass


