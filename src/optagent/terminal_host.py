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

import json
import os
import pty
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

SECTIONS = ("archive", "current", "scratch")
_SESSION_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_BACKENDS = frozenset({"chat_completions", "responses", "messages"})
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


@dataclass(frozen=True)
class ModelEndpoint:
    """One OpenAI-compatible endpoint for the Grok Build harness.

    ``api_key_env`` names the variable that holds the key. The key itself
    is never stored on the endpoint.
    """

    id: str
    model: str
    base_url: str
    api_key_env: str
    backend: str


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _check_base_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"model base_url must be an http(s) URL, got {value!r}")
    if parsed.username or parsed.password:
        raise ValueError("put the API key in the named environment variable, not in the model URL")
    return value.strip().rstrip("/")


def _endpoint(raw: dict, *, fallback_id: str = "optagent") -> ModelEndpoint:
    if not isinstance(raw, dict):
        raise ValueError("a model endpoint must be an object")
    ident = str(raw.get("id") or fallback_id).strip()
    if not _MODEL_ID.match(ident):
        raise ValueError(f"model id {ident!r} must match {_MODEL_ID.pattern}")
    model = str(raw.get("model") or ident).strip()
    if not _MODEL_ID.match(model):
        raise ValueError(f"model name {model!r} must match {_MODEL_ID.pattern}")
    backend = str(raw.get("backend") or raw.get("api_backend") or "chat_completions").strip()
    if backend not in _BACKENDS:
        raise ValueError(f"model backend must be one of {', '.join(sorted(_BACKENDS))}")
    base_url = str(raw.get("base_url") or "").strip()
    if base_url:
        base_url = _check_base_url(base_url)
    api_key_env = str(raw.get("api_key_env") or "OPTAGENT_MODEL_API_KEY").strip()
    if api_key_env and not _MODEL_ID.match(api_key_env):
        raise ValueError(f"api_key_env {api_key_env!r} is not an environment variable name")
    return ModelEndpoint(ident, model, base_url, api_key_env, backend)


def _hocon_models() -> tuple[str, list[ModelEndpoint]]:
    from pyhocon import ConfigFactory

    path = Path(__file__).resolve().parents[2] / "config" / "base.conf"
    if not path.is_file():
        return "", []
    tree = ConfigFactory.parse_file(str(path))
    block = tree.get("terminal", None)
    if block is None:
        return "", []
    selected = str(block.get("model", "") or "").strip()
    items = []
    for raw in block.get("models", []) or []:
        data = {key: raw.get(key, "") for key in ("id", "model", "base_url", "api_key_env", "backend")}
        items.append(_endpoint(data))
    return selected, items


def _json_models(raw: str) -> list[ModelEndpoint]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"OPTAGENT_MODELS_JSON is not JSON: {exc.msg}") from exc
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("OPTAGENT_MODELS_JSON must be a non-empty list")
    return [_endpoint(item) for item in parsed]


def resolve_model() -> ModelEndpoint | None:
    """The endpoint this session should use.

    An empty result means Grok's built-in catalog. ``OPTAGENT_MODELS_JSON``
    replaces the HOCON list. ``OPTAGENT_MODEL_BASE_URL`` fills the selected
    endpoint so a local shell and an AMP set the same variables.
    """

    raw_json = os.environ.get("OPTAGENT_MODELS_JSON", "").strip()
    if raw_json:
        items = _json_models(raw_json)
        selected = os.environ.get("OPTAGENT_MODEL", "").strip()
    else:
        selected, items = _hocon_models()
    if len({item.id for item in items}) != len(items):
        raise ValueError("model endpoint ids must be unique")
    url = os.environ.get("OPTAGENT_MODEL_BASE_URL", "").strip()
    name = os.environ.get("OPTAGENT_MODEL_NAME", "").strip()
    key_env = os.environ.get("OPTAGENT_MODEL_API_KEY_ENV", "").strip()
    backend = os.environ.get("OPTAGENT_MODEL_BACKEND", "").strip()
    if url or name or key_env or backend:
        target = selected or (items[0].id if len(items) == 1 else "optagent")
        current = next((item for item in items if item.id == target), None)
        merged = _endpoint(
            {
                "id": target,
                "model": name or (current.model if current else ""),
                "base_url": url or (current.base_url if current else ""),
                "api_key_env": key_env or (current.api_key_env if current else ""),
                "backend": backend or (current.backend if current else ""),
            }
        )
        items = [merged if item.id == merged.id else item for item in items]
        if merged.id not in {item.id for item in items}:
            items.append(merged)
        if not selected:
            selected = merged.id
    if selected:
        match = next((item for item in items if item.id == selected), None)
        if match is None:
            known = ", ".join(item.id for item in items) or "(none)"
            raise ValueError(f"OPTAGENT_MODEL {selected} is not a configured endpoint ({known})")
        return match if match.base_url else None
    filled = [item for item in items if item.base_url]
    if len(filled) == 1:
        return filled[0]
    if len(filled) > 1:
        names = ", ".join(item.id for item in filled)
        raise ValueError(f"set OPTAGENT_MODEL to one of: {names}")
    return None


def _write_model_home(home: Path, endpoint: ModelEndpoint) -> Path:
    grok_home = home / "grok-home"
    grok_home.mkdir(parents=True, exist_ok=True)
    config = "\n".join(
        [
            "[models]",
            f"default = {_toml_string(endpoint.id)}",
            "",
            f"[model.{_toml_string(endpoint.id)}]",
            f"model = {_toml_string(endpoint.model)}",
            f"base_url = {_toml_string(endpoint.base_url)}",
            f"name = {_toml_string(endpoint.id)}",
            f"api_backend = {_toml_string(endpoint.backend)}",
            f"env_key = {_toml_string(endpoint.api_key_env)}",
            "context_window = 262144",
            "max_completion_tokens = 8192",
            "",
        ]
    )
    (grok_home / "config.toml").write_text(config, encoding="utf-8")
    return grok_home


class TerminalSession:
    def __init__(self, session_id: str, section: str) -> None:
        self.id = session_id
        self.section = section
        self.created = int(time.time() * 1000)
        self.status = "starting"
        self.detail = ""
        self.command: list[str] = []
        self.model_id = ""
        self.child_env: dict[str, str] = {}
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
        try:
            endpoint = resolve_model()
        except ValueError as exc:
            self.status = "model-config"
            self.detail = str(exc)
            self._append((str(exc) + "\r\n").encode())
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
        child_env = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor"}
        notes: list[str] = []
        if endpoint is not None:
            grok_home = _write_model_home(home, endpoint)
            cmd.extend(["-m", endpoint.id])
            child_env["GROK_HOME"] = str(grok_home)
            self.model_id = endpoint.id
            notes.append(endpoint.id)
            if endpoint.api_key_env and not os.environ.get(endpoint.api_key_env, "").strip():
                notes.append(f"{endpoint.api_key_env} is unset")
            self._append(f"model {endpoint.id} → {endpoint.base_url}\r\n".encode())
        if shutil.which("bwrap"):
            cmd.extend(["--sandbox", "workspace"])
            self.status = "sandboxed"
        else:
            self.status = "host"
            notes.append("bwrap is absent, so grok is not sandboxed")
        self.detail = " · ".join(notes)
        self.command = cmd
        self.child_env = child_env
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=str(home),
                start_new_session=True,
                env=child_env,
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
