# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _harvest():
    spec = importlib.util.spec_from_file_location(
        "optagent_harvest", ROOT / "scripts" / "phoenix" / "harvest.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hermes_messages_keep_their_timestamps_and_reasoning(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE sessions (
              id TEXT PRIMARY KEY, source TEXT, model TEXT, title TEXT,
              started_at REAL, hidden INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE messages (
              id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT,
              reasoning TEXT, timestamp REAL, token_count INTEGER, active INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            ("agent-rtc-4fcf", "agent-rtc", "grok-4.6", "Extract arXiv 2510.18032 into wiki", 1_700_000_000.5, 0),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "agent-rtc-4fcf", "user", "Read arXiv 2510.18032", "", 1_700_000_000.5, 0, 1),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (2, "agent-rtc-4fcf", "assistant", "Filed the wiki note.", "checked the pdf", 1_700_000_001.0, 12, 1),
        )
    spans, mark = _harvest().hermes_spans(str(db))
    assert mark["table"] == "messages"
    assert len(spans) == 2
    assistant = spans[1]
    assert assistant["attributes"]["session.id"] == "hermes:agent-rtc:4fcf"
    assert assistant["attributes"]["hermes.activity"] == "preprint"
    assert assistant["attributes"]["lattice.capability"] == "preprint"
    assert "checked the pdf" in assistant["attributes"]["output.value"]
    assert assistant["start_time_unix_nano"] == 1_700_000_001_000_000_000
    assert "output.value" not in assistant["resource"]
