# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from optagent.classify import (
    FLOOR,
    choice_points,
    classify_snapshot,
    post_systemone,
    propose_spans,
    term_links,
)
from optagent.lineup import session_items, timeline_report
from optagent.phoenix_spans import make_span, read_jsonl

LINEAGE = "https://signals.zndx.org/sdg#DATAENG_LINEAGE"
QUALITY = "https://signals.zndx.org/sdg#DATAENG_QUALITY"
CATALOG = "https://signals.zndx.org/sdg#DATAENG_CATALOG"
MODELING = "https://signals.zndx.org/sdg#DATAENG_MODELING"
DATAENG = "https://signals.zndx.org/sdg#DATAENG"
LIMS = "https://signals.zndx.org/sdg#LIMS"
SPECIMEN = "https://signals.zndx.org/sdg#LIMS_SPECIMEN_LIFECYCLE"

REPLAY = (
    "What keeps pulling me back is that replay is the load-bearing idea, but it shows up in two different clothes. "
    "On the decision-graph side it's counterfactual — walk the typed edges under a different assumption and see the outcome shift. "
    "On the evidence side it's tamper-evident and replayable — you can re-walk the run and the structure of the log is what makes the delta trustworthy, not any summary. "
    "The minimal schema I'm after is the one where both of those are the same act: the causal axis and the provenance axis are one replayable structure."
)

SPECIMEN_TEXT = (
    "Vertex Casgevy starts when the laboratory receives the patient's cells. The specimen is collected, received, and accessioned "
    "under a unique identifier, partitioned into aliquots, and stored at a controlled location and temperature. "
    "The sample lifecycle is received, then accessioned, then aliquoted, then tested, then reported, then archived or destroyed."
)

CONSCIOUSNESS = "I see some connections between neural correlates of consciousness and the OptAgent paper. What do you think?"


def _leaf(iri: str, label: str, code: str, parent: str, alt: list[str] | None = None) -> dict:
    return {
        "iri": iri,
        "label": label,
        "code": code,
        "alt": alt or [],
        "definition": label,
        "broader": [parent],
        "narrower": [],
    }


def _lexicon() -> list[dict]:
    leaves = [
        _leaf(MODELING, "Relational and Schema Modeling", "14.1", DATAENG, ["Data Modeling"]),
        _leaf(LINEAGE, "Data Lineage and Provenance", "14.2", DATAENG, ["Data Provenance"]),
        _leaf(CATALOG, "Metadata Cataloging and Semantic Annotation", "14.3", DATAENG, ["Data Catalog"]),
        _leaf(QUALITY, "Data Profiling, Quality and Observability", "14.4", DATAENG, ["Data Quality"]),
        _leaf(SPECIMEN, "Specimen Lifecycle Management", "9.1", LIMS, ["Sample Lifecycle"]),
    ]
    return [
        {
            "iri": DATAENG,
            "label": "Data Engineering, Metadata and Lineage",
            "code": "14",
            "alt": ["Data Management"],
            "definition": "Lineage and catalogs.",
            "broader": [],
            "narrower": [MODELING, LINEAGE, CATALOG, QUALITY],
        },
        {
            "iri": LIMS,
            "label": "Laboratory Information Management",
            "code": "9",
            "alt": ["LIMS"],
            "definition": "Samples and results.",
            "broader": [],
            "narrower": [SPECIMEN],
        },
        *leaves,
    ]


def test_a_leaf_is_classified_among_its_siblings() -> None:
    points = choice_points(_lexicon(), LINEAGE)
    assert [item["iri"] for item in points] == [MODELING, LINEAGE, CATALOG, QUALITY]
    children = choice_points(_lexicon(), DATAENG)
    assert DATAENG not in {item["iri"] for item in children}
    assert LINEAGE in {item["iri"] for item in children}
    assert choice_points(_lexicon(), "https://signals.zndx.org/sdg#MBSE") == []


def test_proposals_are_short_label_phrases() -> None:
    points = choice_points(_lexicon(), LINEAGE)
    replay = propose_spans(REPLAY, points)
    assert replay
    assert all(1 <= len(item["text"].split()) <= 4 for item in replay)
    assert any(item["text"].lower() == "provenance" for item in replay)
    assert all(item["text"] != REPLAY for item in replay)
    specimen = propose_spans(SPECIMEN_TEXT, choice_points(_lexicon(), SPECIMEN))
    surfaces = [item["text"].lower() for item in specimen]
    assert "sample lifecycle" in surfaces
    assert "specimen" in surfaces
    assert len(specimen) <= 4
    assert propose_spans(CONSCIOUSNESS, choice_points(_lexicon(), QUALITY)) == []


def test_links_keep_the_floor_and_the_density_cap() -> None:
    points = choice_points(_lexicon(), LINEAGE)
    text = "lineage feeds provenance while quality and catalog and modeling stay beside the graph in this sentence here."
    candidates = [
        {"start": 0, "end": 7, "text": "lineage"},
        {"start": 14, "end": 24, "text": "provenance"},
        {"start": 31, "end": 38, "text": "quality"},
        {"start": 43, "end": 50, "text": "catalog"},
        {"start": 55, "end": 63, "text": "modeling"},
    ]
    # The proposer would not emit these offsets; the guard still has to.
    assert text[0:7] == "lineage"
    body = {
        "answers": {
            "w0": {"choice": "DATAENG_LINEAGE", "confidence": 0.91},
            "w1": {"choice": "none", "confidence": 0.99},
            "w2": {"choice": "DATAENG_QUALITY", "confidence": FLOOR - 0.01},
            "w3": {"choice": "NOT_A_TERM", "confidence": 0.99},
            "w4": {"choice": "DATAENG_MODELING", "confidence": 0.8},
        }
    }
    links = term_links(body, candidates, points, text)
    assert [item["text"] for item in links] == ["lineage", "modeling"]
    assert all(item["confidence"] >= FLOOR for item in links)
    crowded = term_links(
        {
            "answers": {
                "w0": {"choice": "DATAENG_LINEAGE", "confidence": 0.9},
                "w1": {"choice": "DATAENG_LINEAGE", "confidence": 0.8},
                "w2": {"choice": "DATAENG_QUALITY", "confidence": 0.7},
                "w3": {"choice": "DATAENG_CATALOG", "confidence": 0.6},
            }
        },
        candidates[:4],
        points,
        text,
    )
    assert len(crowded) <= 3
    assert sum(item["iri"] == LINEAGE for item in crowded) <= 2


def test_admitted_passage_without_a_term_is_overwatch(tmp_path: Path) -> None:
    project = tmp_path / "projects" / "hermes"
    project.mkdir(parents=True)
    stamp = 1_700_000_000_000_000_000
    replay = make_span(
        project="hermes",
        session="hermes:agent-rtc:802225c3cb6e",
        name="replay",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="replay",
        start_time_unix_nano=stamp,
        output_value=REPLAY,
        attributes={
            "aegir.genus_code": "18.3.2",
            "aegir.genus_iri": LINEAGE,
            "aegir.genus_label": "Data Lineage and Provenance",
            "sdg.spans": [{"start": 0, "end": len(REPLAY), "text": REPLAY, "iri": LINEAGE, "label": "whole"}],
        },
    )
    miss = make_span(
        project="hermes",
        session="hermes:agent-rtc:4fcf03d6b815",
        name="miss",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="miss",
        start_time_unix_nano=stamp,
        output_value=CONSCIOUSNESS,
        attributes={
            "aegir.genus_code": "16.2.4",
            "aegir.genus_iri": QUALITY,
            "aegir.genus_label": "Data Profiling, Quality and Observability",
            "sdg.spans": [{"start": 0, "end": len(CONSCIOUSNESS), "text": CONSCIOUSNESS, "iri": QUALITY}],
        },
    )
    dump = make_span(
        project="hermes",
        session="hermes:agent-rtc:dump",
        name="dump",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="dump",
        start_time_unix_nano=stamp,
        output_value='{"content": "1|--- title: OptAgent wiki note with many tokens and fields and more words"}',
        attributes={"aegir.genus_code": "18.1", "aegir.genus_iri": "https://signals.zndx.org/sdg#MBSE"},
    )
    from optagent.phoenix_spans import write_jsonl

    write_jsonl(project / "spans.jsonl", [replay, miss, dump])
    (tmp_path / "signals-snapshot.json").write_text('{"summary":{}}\n', encoding="utf-8")
    calls = []

    def post(state, questions):
        calls.append(state)
        answers = {}
        for key, question in questions.items():
            phrase = str(question["instructions"]).rsplit("Phrase: ", 1)[-1].strip().lower()
            if phrase == "provenance":
                answers[key] = {"choice": "DATAENG_LINEAGE", "confidence": 0.88}
            else:
                answers[key] = {"choice": "none", "confidence": 0.62}
        return {
            "model": "jev-1.14.0",
            "usage": {"input_tokens": 40, "output_tokens": 6},
            "answers": answers,
        }

    result = classify_snapshot(tmp_path, post=post, lexicon=_lexicon())
    assert result["called"] == 1
    assert result["linked"] == 1
    assert result["overwatch"] == 1
    assert result["errors"] == 0
    written = {span["name"]: span for span in read_jsonl(project / "spans.jsonl")}
    link = written["replay"]["attributes"]["sdg.spans"]
    assert link[0]["text"].lower() == "provenance"
    assert link[0]["iri"] == LINEAGE
    assert link[0]["end"] - link[0]["start"] < len(REPLAY)
    assert written["replay"]["attributes"]["typesafe.input_tokens"] == 40
    assert "overwatch.reason" not in written["replay"]["attributes"]
    assert written["replay"]["attributes"]["aegir.genus_iri"] == LINEAGE
    assert written["miss"]["attributes"]["overwatch.reason"] == "admitted-without-terms"
    assert "sdg.spans" not in written["miss"]["attributes"]
    assert "overwatch.reason" not in written["dump"]["attributes"]
    assert calls and "secret" not in json.dumps(calls)
    report = timeline_report(list(written.values()), now_ms=1_700_000_000_000 + 86_400_000, window="365d")
    assert report["totals"]["overwatch"] == 1
    session = {item["id"]: item for item in session_items(list(written.values()), "hermes")}
    replay_row = session["hermes:agent-rtc:802225c3cb6e"]["items"][0]
    assert replay_row["genus_label"] == "Data Lineage and Provenance"
    assert any(part.get("iri") == LINEAGE and part["text"].lower() == "provenance" for part in replay_row["rich"])


def test_post_pins_the_model_and_omits_the_key(monkeypatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret-token")
    seen = {}

    class Response:
        def read(self):
            return b'{"model":"jev-1.14.0","answers":{},"usage":{"input_tokens":3,"output_tokens":1}}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def opener(request, timeout=0):
        seen["body"] = json.loads(request.data.decode())
        seen["auth"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return Response()

    body = post_systemone("A short passage about provenance in the log.", {"w0": {"type": "choice"}}, opener=opener)
    assert seen["body"]["model"] == "jev-1.14.0"
    assert seen["auth"] == "Bearer secret-token"
    assert "secret-token" not in json.dumps(body)
    assert seen["timeout"] == 120
