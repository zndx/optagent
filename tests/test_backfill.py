# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from optagent.backfill import apply_admission, backfill_tree, last_days
from optagent.phoenix_spans import make_span, read_jsonl

ROOT = Path(__file__).resolve().parents[1]


def _harvest():
    spec = importlib.util.spec_from_file_location("optagent_harvest", ROOT / "scripts" / "phoenix" / "harvest.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_viz_show_keeps_the_chart_kind(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE sessions (id TEXT, source TEXT, model TEXT, title TEXT, started_at REAL, hidden INTEGER)"
        )
        conn.execute(
            """
            CREATE TABLE messages (
              id INTEGER, session_id TEXT, role TEXT, content TEXT, reasoning TEXT,
              timestamp REAL, token_count INTEGER, active INTEGER, display_metadata TEXT,
              tool_name TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO sessions VALUES ('agent-rtc-1', 'agent-rtc', 'm', 'call', 1, 0)"
        )
        conn.execute(
            "INSERT INTO messages VALUES (1, 'agent-rtc-1', 'tool', ?, '', 1, 0, 1, NULL, 'viz_show')",
            (json.dumps({"kind": "chord", "title": "domains", "ok": True}),),
        )
    spans, _mark = _harvest().hermes_spans(str(db))
    assert spans[0]["attributes"]["hermes.viz.kind"] == "chord"
    assert spans[0]["name"] == "viz:chord"


def test_generation_span_keeps_recorded_tokens_and_thinking() -> None:
    span = _harvest().generation_span(
        {
            "id": "g1",
            "summary_type": "cognition_synthesis",
            "model_name": "Qwen/Qwen3.8-27B",
            "prompt": "choose",
            "output": "the specimen",
            "thinking_trace": "consider the genus",
            "input_tokens": 10,
            "output_tokens": 4,
            "latency_ms": 80,
            "generated_at": "2026-10-18T12:00:00+00:00",
        }
    )
    assert span["attributes"]["gaius.activity"] == "hx-generation"
    assert span["attributes"]["llm.token_count.total"] == 14
    assert "Thinking" in span["attributes"]["output.value"]
    assert span["attributes"]["latency_ms"] == 80
    assert "sdg.iri" not in span["attributes"]


def test_admission_records_genus_without_inventing_an_iri() -> None:
    span = make_span(
        project="hermes",
        session="hermes:agent-rtc:1",
        name="turn",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="t",
        output_value="The specimen is accessioned.",
    )
    scan = {
        "n_admitted": 1,
        "items": [
            {"admitted": False, "span": [0, 4], "code": "", "genus_margin": 0.01},
            {"admitted": True, "span": [4, 20], "code": "16.2", "label": "LIMS", "genus_margin": 0.22},
        ],
    }
    assert apply_admission(span, scan, augmented_at_ms=1_700_000_100_000) is True
    attributes = span["attributes"]
    assert attributes["aegir.genus_code"] == "16.2"
    assert attributes["aegir.genus_label"] == "LIMS"
    assert attributes["aegir.tau"] == 0.10
    assert attributes["sdg.augmented_at"] == 1_700_000_100_000
    assert "sdg.iri" not in attributes
    assert "sdg.spans" not in attributes
    assert "semantica.confidence" not in attributes


def test_backfill_window_leaves_older_spans_unchanged(tmp_path: Path) -> None:
    now = datetime(2026, 10, 18, tzinfo=timezone.utc)
    recent = int((now - timedelta(days=1)).timestamp() * 1_000_000_000)
    old = int((now - timedelta(days=30)).timestamp() * 1_000_000_000)
    project = tmp_path / "projects" / "hermes"
    project.mkdir(parents=True)
    spans = [
        make_span(
            project="hermes",
            session="hermes:agent-rtc:1",
            name="new",
            activity="agent-rtc",
            capability="conversation",
            service_name="agent-rtc",
            trace_key="new",
            start_time_unix_nano=recent,
            output_value="The specimen is accessioned in the laboratory.",
        ),
        make_span(
            project="hermes",
            session="hermes:agent-rtc:1",
            name="old",
            activity="agent-rtc",
            capability="conversation",
            service_name="agent-rtc",
            trace_key="old",
            start_time_unix_nano=old,
            output_value="An older laboratory sentence that should stay untouched.",
        ),
    ]
    from optagent.phoenix_spans import write_jsonl

    write_jsonl(project / "spans.jsonl", spans)
    (tmp_path / "signals-snapshot.json").write_text('{"summary":{}}\n', encoding="utf-8")
    since, until = last_days(7, now=now)
    from optagent.backfill import parse_time

    result = backfill_tree(
        tmp_path,
        since_ms=parse_time(since, default_ms=0),
        until_ms=parse_time(until, default_ms=0),
        admit=lambda _text: {
            "items": [{"admitted": True, "span": [0, 10], "code": "9", "label": "Lab", "genus_margin": 0.3}]
        },
        augmented_at_ms=1,
    )
    assert result["examined"] == 1
    assert result["admitted"] == 1
    written = read_jsonl(project / "spans.jsonl")
    by_name = {span["name"]: span for span in written}
    assert by_name["new"]["attributes"]["aegir.genus_code"] == "9"
    assert "aegir.genus_code" not in by_name["old"]["attributes"]
