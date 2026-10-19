# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Server-side terminal sessions for the AMP web tier.

The PTY lives in the app process, the same place Atelier keeps its gateway
terminal. The engine gRPC face stays Status-only. Ghostty in the browser is
only the VT. ``grok`` is the host process, built by Gaius from
``zndx/oss-grok-build``.
"""

from __future__ import annotations

import os
import pty
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

SECTIONS = ("archive", "current", "scratch")
_LOCK = threading.Lock()
_SESSIONS: dict[str, "TerminalSession"] = {}


def grok_bin() -> Path | None:
    for key in ("OPTAGENT_GROK_BIN", "GAIUS_GROK_BIN"):
        raw = os.environ.get(key, "").strip()
        if raw and Path(raw).is_file() and os.access(raw, os.X_OK):
            return Path(raw)
    home = Path.home() / ".local" / "bin" / "grok"
    if home.is_file() and os.access(home, os.X_OK):
        return home
    found = shutil.which("grok")
    return Path(found) if found else None


def _root() -> Path:
    raw = os.environ.get("OPTAGENT_SESSION_DIR", "").strip()
    base = Path(raw) if raw else Path.home() / ".local" / "state" / "optagent"
    path = base / "terminals"
    path.mkdir(parents=True, exist_ok=True)
    return path


class TerminalSession:
    def __init__(self, session_id: str, section: str) -> None:
        self.id = session_id
        self.section = section
        self.created = int(time.time() * 1000)
        self.status = "starting"
        self.detail = ""
        self._chunks: bytearray = bytearray()
        self._master: int | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def public(self) -> dict:
        with self._lock:
            return {
                "id": self.id,
                "section": self.section,
                "status": self.status,
                "detail": self.detail,
                "created": self.created,
                "bytes": len(self._chunks),
            }

    def read(self, cursor: int) -> dict:
        with self._lock:
            start = max(0, min(cursor, len(self._chunks)))
            data = bytes(self._chunks[start:])
            return {"cursor": len(self._chunks), "data": data.decode("utf-8", "replace"), "status": self.status}

    def write(self, data: str) -> None:
        fd = self._master
        if fd is None or not data:
            return
        try:
            os.write(fd, data.encode("utf-8"))
        except OSError:
            self.status = "closed"

    def resize(self, cols: int, rows: int) -> None:
        fd = self._master
        if fd is None:
            return
        import fcntl
        import struct
        import termios

        try:
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", int(rows), int(cols), 0, 0))
        except OSError:
            return

    def _append(self, data: bytes) -> None:
        with self._lock:
            self._chunks.extend(data)

    def start(self) -> None:
        binary = grok_bin()
        home = _root() / self.id
        home.mkdir(parents=True, exist_ok=True)
        if binary is None:
            self.status = "grok-missing"
            self.detail = "grok is not installed. Build it with `just grok-build` in Gaius."
            self._append((self.detail + "\r\n").encode())
            return
        master, slave = pty.openpty()
        cmd = [str(binary)]
        if shutil.which("bwrap"):
            cmd.extend(["--sandbox", "workspace"])
            self.status = "sandboxed"
        else:
            self.status = "host"
            self.detail = "bwrap is absent, so grok is not sandboxed"
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=str(home),
                start_new_session=True,
                env={**os.environ, "GROK_HOME": str(home / "grok-home")},
            )
        except OSError as exc:
            os.close(master)
            os.close(slave)
            self.status = "grok-missing"
            self.detail = str(exc)
            self._append((self.detail + "\r\n").encode())
            return
        os.close(slave)
        self._master = master

        def _read() -> None:
            while True:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                self._append(chunk)
            self.status = "closed"

        threading.Thread(target=_read, name=f"optagent-term-{self.id[:8]}", daemon=True).start()


def create_session(section: str = "current") -> dict:
    if section not in SECTIONS:
        raise ValueError("section must be archive, current, or scratch")
    session = TerminalSession(str(uuid.uuid4()), section)
    with _LOCK:
        _SESSIONS[session.id] = session
    session.start()
    return session.public()


def list_sessions(section: str = "") -> list[dict]:
    with _LOCK:
        rows = [item.public() for item in _SESSIONS.values()]
    if section:
        rows = [item for item in rows if item["section"] == section]
    return sorted(rows, key=lambda item: item["created"], reverse=True)


def move_session(session_id: str, section: str) -> dict:
    if section not in SECTIONS:
        raise ValueError("section must be archive, current, or scratch")
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise KeyError(session_id)
    session.section = section
    return session.public()


def get_session(session_id: str) -> TerminalSession:
    with _LOCK:
        session = _SESSIONS.get(session_id)
    if session is None:
        raise KeyError(session_id)
    return session
