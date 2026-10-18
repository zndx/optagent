# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
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
              reasoning TEXT, timestamp REAL, token_count INTEGER, active INTEGER,
              display_metadata TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?)",
            ("agent-rtc-4fcf", "agent-rtc", "grok-4.6", "Extract arXiv 2510.18032 into wiki", 1_700_000_000.5, 0),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "agent-rtc-4fcf", "user", "Read arXiv 2510.18032", "", 1_700_000_000.5, 0, 1, None),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                2,
                "agent-rtc-4fcf",
                "assistant",
                "Filed the wiki note.",
                "checked the pdf",
                1_700_000_001.0,
                12,
                1,
                '{"links":[{"start":0,"end":5,"genus_iri":"https://signals.zndx.org/sdg#LIMS","genus_code":"9","rel_margin_h":0.55,"tau":0.1}]}',
            ),
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
    assert assistant["attributes"]["semantica.category"] == "preprint"
    assert assistant["attributes"]["semantica.scenario"] == "Read arXiv 2510.18032"
    assert assistant["attributes"]["semantica.reasoning"] == "checked the pdf"
    assert assistant["attributes"]["semantica.outcome"] == "Filed the wiki note."
    assert assistant["attributes"]["semantica.caller_project"] == "hermes"
    assert assistant["attributes"]["semantica.caller_agent"] == "agent-rtc"
    assert assistant["attributes"]["semantica.run_id"] == "agent-rtc-4fcf"
    assert assistant["attributes"]["semantica.tx_id"] == "2"
    assert assistant["attributes"]["semantica.entities"] == "2510.18032"
    assert "semantica.confidence" not in assistant["attributes"]
    assert "semantica.caused_by" not in assistant["attributes"]
    assert assistant["attributes"]["aegir.genus_iri"] == "https://signals.zndx.org/sdg#LIMS"
    assert assistant["attributes"]["aegir.start"] == 0
    assert assistant["attributes"]["aegir.end"] == 5
    assert "semantica.confidence" not in assistant["attributes"]
    assert "sdg.spans" not in assistant["attributes"]
    assert "output.value" not in assistant["resource"]
    with sqlite3.connect(db) as conn:
        conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            3,
            "agent-rtc-4fcf",
            "assistant",
            "The specimen is accessioned. The assay is run on a named instrument.",
            "",
            1_700_000_002.0,
            20,
            1,
            json.dumps(
                {
                    "links": [
                        {
                            "start": 0,
                            "end": 120,
                            "genus_iri": "https://signals.zndx.org/sdg#LIMS",
                            "genus_code": "16.2",
                            "genus_label": "Laboratory Information Management",
                            "rel_margin_h": 0.22,
                            "tau": 0.1,
                            "sdg.iri": "https://signals.zndx.org/sdg#LIMS_SPECIMEN_LIFECYCLE",
                            "semantica.confidence": 0.98,
                            "assignments": [
                                {
                                    "start": 0,
                                    "end": 77,
                                    "text": "The specimen is collected from the patient, received, and accessioned under a",
                                    "iri": "https://signals.zndx.org/sdg#LIMS_SPECIMEN_LIFECYCLE",
                                    "label": "Specimen Lifecycle Management",
                                    "confidence": 0.98,
                                },
                                {
                                    "start": 80,
                                    "end": 120,
                                    "text": "The assay is run on a named instrument.",
                                    "iri": "https://signals.zndx.org/sdg#LIMS_ASSAY_EXECUTION",
                                    "label": "Assay Execution",
                                    "confidence": 0.91,
                                },
                            ],
                        },
                        {
                            "start": 200,
                            "end": 240,
                            "genus_iri": "https://signals.zndx.org/sdg#LIMS",
                            "genus_code": "16.2",
                            "rel_margin_h": 0.05,
                            "tau": 0.1,
                        },
                    ],
                    "text_len": 120,
                }
            ),
        ),
        )
    spans, _mark = _harvest().hermes_spans(str(db))
    grounded = spans[-1]["attributes"]
    assert grounded["aegir.genus_iri"] == "https://signals.zndx.org/sdg#LIMS"
    assert grounded["aegir.genus_code"] == "16.2"
    assert grounded["aegir.start"] == 0
    assert grounded["aegir.end"] == 120
    iris = [item["iri"] for item in grounded["sdg.spans"]]
    assert iris == [
        "https://signals.zndx.org/sdg#LIMS_SPECIMEN_LIFECYCLE",
        "https://signals.zndx.org/sdg#LIMS_ASSAY_EXECUTION",
    ]
    assert grounded["sdg.spans"][0]["start"] == 0
    assert grounded["sdg.spans"][0]["end"] == 77
    assert grounded["sdg.spans"][1]["start"] == 80
    assert "LIMS_SPECIMEN_LIFECYCLE" in grounded["semantica.entities"]
    assert "LIMS_ASSAY_EXECUTION" in grounded["semantica.entities"]
    assert grounded["semantica.entities"].count("LIMS_SPECIMEN_LIFECYCLE") == 1
    assert grounded["semantica.confidence"] == 0.98
    dest = tmp_path / "signals-snapshot" / "fixture"
    archive = _harvest().build_archive(
        dest,
        "postgresql://127.0.0.1:1/optagent?connect_timeout=1",
        "postgresql://127.0.0.1:1/metabase?connect_timeout=1",
        str(db),
    )
    written = json.loads((dest / "projects" / "hermes" / "spans.jsonl").read_text().splitlines()[-1])
    document = json.loads((dest / "signals-snapshot.json").read_text())
    assert document["format"] == "signals-snapshot"
    assert written["attributes"]["sdg.spans"][1]["iri"].endswith("LIMS_ASSAY_EXECUTION")
    assert written["attributes"]["sdg.spans"][0]["start"] == 0
    assert written["attributes"]["sdg.spans"][0]["end"] == 77
    assert archive.is_file()
