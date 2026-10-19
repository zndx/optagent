# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import os
import socket

from optagent import terminal_host
from optagent.terminal_host import create_session
from optagent.terminal_ws import accept_value, read_frame


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
    created = create_session("current", "77777777-7777-4777-8777-777777777777")
    session = terminal_host.get_session(created["id"])
    _snap, box = session.listen()
    session._append(b"hello")
    assert box.get(timeout=1) == b"hello"
    session.unlisten(box)
    assert session.alive()
    assert session._proc is not None
    os.kill(session._proc.pid, 9)
    session._proc.wait(timeout=2)
