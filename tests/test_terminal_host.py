# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

from optagent import terminal_host
from optagent.terminal_host import create_session, list_sessions, move_session


def _reset() -> None:
    for session in list(terminal_host._SESSIONS.values()):
        proc = session._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
    terminal_host._SESSIONS.clear()


def test_a_browser_id_attaches_once_and_stays_inline(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    binary = tmp_path / "grok"
    binary.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("optagent.terminal_host.grok_bin", lambda: binary)
    monkeypatch.setattr("optagent.terminal_host.shutil.which", lambda name: None)
    session_id = "3d7be767-c52e-4a20-bee7-5b1aa71ca19f"
    first = create_session("current", session_id)
    again = create_session("current", session_id)
    assert first["id"] == session_id
    assert again["id"] == session_id
    assert first["status"] == "host"
    assert "--fullscreen" not in first_command(session_id)
    assert "--minimal" in first_command(session_id)
    assert "--no-alt-screen" in first_command(session_id)
    assert list_sessions("current")[0]["id"] == session_id
    proc = __import__("optagent.terminal_host", fromlist=["get_session"]).get_session(session_id)._proc
    assert proc is not None
    proc.kill()
    proc.wait(timeout=2)


def first_command(session_id: str) -> list[str]:
    return __import__("optagent.terminal_host", fromlist=["get_session"]).get_session(session_id).command


def test_missing_grok_still_records_a_server_session(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.setattr("optagent.terminal_host.grok_bin", lambda: None)
    created = create_session("current")
    assert created["status"] == "grok-missing"
    assert created["section"] == "current"
    listed = list_sessions("current")
    assert [item["id"] for item in listed] == [created["id"]]
    moved = move_session(created["id"], "archive")
    assert moved["section"] == "archive"
    assert list_sessions("current") == []
    assert list_sessions("archive")[0]["id"] == created["id"]
    text = __import__("optagent.terminal_host", fromlist=["get_session"]).get_session(created["id"]).read(0)
    assert "just grok-build" in text["data"]
