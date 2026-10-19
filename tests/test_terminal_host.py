# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

from optagent.terminal_host import create_session, list_sessions, move_session


def test_missing_grok_still_records_a_server_session(monkeypatch, tmp_path) -> None:
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
