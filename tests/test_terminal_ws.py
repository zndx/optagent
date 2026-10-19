# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
import os
import socket
import threading
import time
from pathlib import Path

from optagent import terminal_host
from optagent.terminal_host import create_session, get_session
from optagent.terminal_ws import accept_value, read_frame

ROOT = Path(__file__).resolve().parents[1]
SESSION_ID = "77777777-7777-4777-8777-777777777777"


def test_accept_matches_the_rfc_sample() -> None:
    assert accept_value("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_masked_client_frame_round_trips() -> None:
    payload = b'{"type":"input","data":"a"}'
    mask = b"\x01\x02\x03\x04"
    header = bytes([0x81, 0x80 | len(payload)]) + mask
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    left, right = socket.socketpair()
    try:
        left.sendall(header + masked)
        opcode, body = read_frame(right)
    finally:
        left.close()
        right.close()
    assert opcode == 1
    assert body == payload


def _reset() -> None:
    for name in (
        "OPTAGENT_MODEL",
        "OPTAGENT_MODEL_NAME",
        "OPTAGENT_MODEL_BASE_URL",
        "OPTAGENT_MODEL_API_KEY_ENV",
        "OPTAGENT_MODEL_BACKEND",
        "OPTAGENT_MODELS_JSON",
        "OPTAGENT_MODEL_API_KEY",
    ):
        os.environ.pop(name, None)
    for session in list(terminal_host._SESSIONS.values()):
        proc = session._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
    terminal_host._SESSIONS.clear()


def _install_fake_grok(monkeypatch, tmp_path: Path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    binary = tmp_path / "grok"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdout.buffer.write(b'banner\\r\\n')\n"
        "sys.stdout.buffer.flush()\n"
        "while True:\n"
        "    chunk = sys.stdin.buffer.read(1)\n"
        "    if not chunk:\n"
        "        break\n"
        "    sys.stdout.buffer.write(chunk)\n"
        "    sys.stdout.buffer.flush()\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    monkeypatch.setattr("optagent.terminal_host.grok_bin", lambda: binary)
    monkeypatch.setattr("optagent.terminal_host.shutil.which", lambda name: None)


def _client_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    mask = b"\x11\x22\x33\x44"
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    header = bytes([0x81, 0x80 | len(payload)])
    sock.sendall(header + mask + masked)


def _read_text(sock: socket.socket, seconds: float) -> str:
    sock.settimeout(0.2)
    deadline = time.time() + seconds
    parts: list[str] = []
    while time.time() < deadline:
        try:
            opcode, payload = read_frame(sock)
        except (TimeoutError, socket.timeout):
            continue
        if opcode != 1 or not payload:
            continue
        message = json.loads(payload.decode("utf-8"))
        if message.get("type") == "text":
            parts.append(str(message.get("data") or ""))
    return "".join(parts)


def test_unlisten_leaves_the_harness_running(monkeypatch, tmp_path) -> None:
    for name in (
        "OPTAGENT_MODEL",
        "OPTAGENT_MODEL_NAME",
        "OPTAGENT_MODEL_BASE_URL",
        "OPTAGENT_MODEL_API_KEY_ENV",
        "OPTAGENT_MODEL_BACKEND",
        "OPTAGENT_MODELS_JSON",
        "OPTAGENT_MODEL_API_KEY",
    ):
        os.environ.pop(name, None)
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    binary = tmp_path / "grok"
    binary.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("optagent.terminal_host.grok_bin", lambda: binary)
    monkeypatch.setattr("optagent.terminal_host.shutil.which", lambda name: None)
    created = create_session("current", SESSION_ID)
    session = terminal_host.get_session(created["id"])
    _snap, box = session.listen()
    session._append(b"hello")
    assert box.get(timeout=1) == b"hello"
    session.unlisten(box)
    assert session.alive()
    assert session._proc is not None
    os.kill(session._proc.pid, 9)
    session._proc.wait(timeout=2)


def test_socket_replays_keystrokes_and_detach_keeps_the_child(monkeypatch, tmp_path) -> None:
    from optagent.terminal_ws import session_loop

    _install_fake_grok(monkeypatch, tmp_path)
    left, right = socket.socketpair()
    worker = threading.Thread(target=session_loop, args=(right, SESSION_ID, "current"), daemon=True)
    worker.start()
    try:
        seen = _read_text(left, 2)
        assert "banner" in seen
        _client_text(left, '{"type":"input","data":"z\\r"}')
        seen += _read_text(left, 2)
        assert "z" in seen
        left.close()
        worker.join(timeout=2)
        assert not worker.is_alive()
        session = get_session(SESSION_ID)
        assert session.alive()
        assert session._listeners == []
    finally:
        left.close()
        right.close()
        _reset()


def test_http_upgrade_streams_a_frame_and_leaves_the_child(monkeypatch, tmp_path) -> None:
    from http.server import ThreadingHTTPServer

    _install_fake_grok(monkeypatch, tmp_path)
    spec = importlib.util.spec_from_file_location("optagent_app_ws", ROOT / "2_app-serve" / "app.py")
    assert spec is not None and spec.loader is not None
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    server = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = socket.create_connection(server.server_address, timeout=2)
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    request = (
        f"GET /ws/terminal/{SESSION_ID}?section=current HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    try:
        client.sendall(request.encode("ascii"))
        client.settimeout(2)
        head = bytearray()
        while b"\r\n\r\n" not in head:
            byte = client.recv(1)
            assert byte
            head.extend(byte)
        text = head.decode("latin-1")
        assert " 101 " in text
        assert accept_value(key) in text
        seen = _read_text(client, 2)
        assert "banner" in seen
        client.close()
        deadline = time.time() + 2
        while time.time() < deadline and get_session(SESSION_ID)._listeners:
            time.sleep(0.05)
        session = get_session(SESSION_ID)
        assert session._listeners == []
        assert session.alive()
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        _reset()
