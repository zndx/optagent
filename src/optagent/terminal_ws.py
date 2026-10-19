# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""WebSocket for a server terminal session.

Ghostty-web is the VT. This socket carries bytes to that terminal and
keystrokes back. Closing the socket detaches the listener. The grok
process keeps running, and the next attach replays the byte log.
"""

from __future__ import annotations

import base64
import hashlib
import json
import queue
import socket
from typing import Any

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_value(key: str) -> str:
    digest = hashlib.sha1((key.strip() + _GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_frame(opcode: int, payload: bytes) -> bytes:
    header = bytearray([0x80 | (opcode & 0x0F)])
    size = len(payload)
    if size < 126:
        header.append(size)
    elif size < 65536:
        header.append(126)
        header.extend(size.to_bytes(2, "big"))
    else:
        header.append(127)
        header.extend(size.to_bytes(8, "big"))
    return bytes(header) + payload


def _read_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf.extend(chunk)
    return bytes(buf)


def read_frame(sock: socket.socket) -> tuple[int, bytes]:
    first, second = _read_exact(sock, 2)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    size = second & 0x7F
    if size == 126:
        size = int.from_bytes(_read_exact(sock, 2), "big")
    elif size == 127:
        size = int.from_bytes(_read_exact(sock, 8), "big")
    mask = _read_exact(sock, 4) if masked else b""
    payload = _read_exact(sock, size) if size else b""
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return opcode, payload


def session_loop(sock: socket.socket, session_id: str, section: str) -> None:
    """Attach to the server harness. Return when the browser disconnects."""

    from optagent.terminal_host import open_session

    try:
        session = open_session(section, session_id)
    except ValueError:
        return
    snap, box = session.listen()
    try:
        _send_json(sock, {"type": "status", "data": session.public()["status"]})
        if snap:
            _send_json(sock, {"type": "text", "data": snap.decode("utf-8", "replace"), "replay": True})
        sock.settimeout(0.25)
        while True:
            try:
                opcode, payload = read_frame(sock)
            except TimeoutError:
                opcode, payload = 0, b""
            except (ConnectionError, OSError, TimeoutError):
                break
            if opcode == 8:
                break
            if opcode == 9:
                try:
                    sock.sendall(encode_frame(10, payload))
                except OSError:
                    break
            elif opcode == 1 and payload:
                _handle_client(session, payload)
            _drain(sock, box)
    finally:
        session.unlisten(box)


def _handle_client(session: Any, payload: bytes) -> None:
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    if not isinstance(message, dict):
        return
    kind = message.get("type")
    if kind == "input":
        session.write(str(message.get("data") or ""))
    elif kind == "resize":
        try:
            session.resize(int(message.get("cols") or 80), int(message.get("rows") or 24))
        except (TypeError, ValueError):
            return


def _drain(sock: socket.socket, box: queue.Queue[bytes]) -> None:
    while True:
        try:
            chunk = box.get_nowait()
        except queue.Empty:
            return
        _send_json(sock, {"type": "text", "data": chunk.decode("utf-8", "replace")})


def _send_json(sock: socket.socket, message: dict) -> None:
    sock.sendall(encode_frame(1, json.dumps(message).encode("utf-8")))
