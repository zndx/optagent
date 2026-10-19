# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Server-side terminal sessions for the AMP web tier.

The PTY lives in the app process, the same place Atelier keeps its gateway
terminal. A browser-owned session id is created on first open and reused
after a reload. The engine gRPC face stays Status-only. Ghostty in the
browser is only the VT, inside the Summary layout. ``grok`` runs inline
in that pane (``--minimal --no-alt-screen``), not as a fullscreen TUI.
"""

from __future__ import annotations

import os
import pty
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

SECTIONS = ("archive", "current", "scratch")
_SESSION_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
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
        self.command: list[str] = []
        self._chunks: bytearray = bytearray()
        self._master: int | None = None
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._generation = 0

    def alive(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

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

    def ensure(self) -> None:
        """Start the PTY once. A second open of the same id reuses the child."""

        with self._start_lock:
            if self.alive():
                return
            if self.status == "grok-missing" and self._proc is None and self._chunks:
                return
            self.start()

    def start(self) -> None:
        binary = grok_bin()
        home = _root() / self.id
        home.mkdir(parents=True, exist_ok=True)
        if binary is None:
            self.status = "grok-missing"
            self.detail = "grok is not installed. In this repo run `just grok-build`."
            self._append((self.detail + "\r\n").encode())
            return
        self._close_master()
        master, slave = pty.openpty()
        # Inline in the center pane. --fullscreen would take the alternate
        # screen the way Gaius's full-bleed terminal does.
        cmd = [
            str(binary),
            "--minimal",
            "--no-alt-screen",
            "--cwd",
            str(home),
            "--leader-socket",
            str(home / "leader.sock"),
        ]
        if shutil.which("bwrap"):
            cmd.extend(["--sandbox", "workspace"])
            self.status = "sandboxed"
            self.detail = ""
        else:
            self.status = "host"
            self.detail = "bwrap is absent, so grok is not sandboxed"
        self.command = cmd
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=str(home),
                start_new_session=True,
                env={**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor"},
            )
        except OSError as exc:
            os.close(master)
            os.close(slave)
            self._proc = None
            self.status = "grok-missing"
            self.detail = str(exc)
            self._append((self.detail + "\r\n").encode())
            return
        os.close(slave)
        self._master = master
        self._generation += 1
        generation = self._generation

        def _read() -> None:
            while True:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                self._append(chunk)
            if generation == self._generation:
                self.status = "closed"

        threading.Thread(target=_read, name=f"optagent-term-{self.id[:8]}", daemon=True).start()

    def _close_master(self) -> None:
        fd = self._master
        self._master = None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            return


def open_session(section: str = "current", session_id: str = "") -> dict:
    """Attach a browser session id, or create one. The child survives reload."""

    if section not in SECTIONS:
        raise ValueError("section must be archive, current, or scratch")
    chosen = (session_id or "").strip()
    if chosen and not _SESSION_ID.match(chosen):
        raise ValueError("session id must be a uuid")
    with _LOCK:
        existing = _SESSIONS.get(chosen) if chosen else None
        if existing is None:
            existing = TerminalSession(chosen or str(uuid.uuid4()), section)
            _SESSIONS[existing.id] = existing
        else:
            existing.section = section
    existing.ensure()
    return existing.public()


def create_session(section: str = "current", session_id: str = "") -> dict:
    return open_session(section, session_id)


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
