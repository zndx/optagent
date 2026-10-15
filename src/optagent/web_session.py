# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Browser sessions for the Optagent web application.

HOCON is the deployment default. A session may override sample mode for
one browser. The session id travels in an HttpOnly cookie. The URL does
not carry that choice.
"""

import json
import os
import threading
import uuid
from pathlib import Path

COOKIE = "optagent_sid"
_LOCK = threading.Lock()


def store_path() -> Path:
    root = Path(os.environ.get("OPTAGENT_SESSION_DIR", ".devenv/state"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "web-sessions.json"


def sid_from_cookie(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == COOKIE and value:
            return value
    return None


def cookie_header(sid: str) -> tuple[str, str]:
    return ("Set-Cookie", f"{COOKIE}={sid}; HttpOnly; Path=/; SameSite=Lax")


def _read() -> dict:
    path = store_path()
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write(data: dict) -> None:
    path = store_path()
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(path)


def ensure(sid: str | None) -> tuple[dict, bool]:
    with _LOCK:
        data = _read()
        if sid and sid in data:
            return data[sid], False
        fresh = uuid.uuid4().hex
        session = {"id": fresh, "sample_mode": None, "color_mode": None}
        data[fresh] = session
        _write(data)
        return session, True


def set_sample_mode(sid: str, enabled: bool) -> dict:
    with _LOCK:
        data = _read()
        session = data.get(sid) or {"id": sid, "sample_mode": None}
        session["id"] = sid
        session["sample_mode"] = bool(enabled)
        data[sid] = session
        _write(data)
        return session


def set_color_mode(sid: str, mode: str) -> dict:
    if mode not in {"dark", "light"}:
        raise ValueError("color mode must be dark or light")
    with _LOCK:
        data = _read()
        session = data.get(sid) or {"id": sid, "sample_mode": None, "color_mode": None}
        session["id"] = sid
        session["color_mode"] = mode
        data[sid] = session
        _write(data)
        return session


def effective_sample_mode(session: dict, configured: bool) -> tuple[bool, str]:
    chosen = session.get("sample_mode")
    if chosen is None:
        return configured, "hocon"
    return bool(chosen), "session"
