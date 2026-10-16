# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import io
import json
import tarfile
from pathlib import Path

import pytest

from optagent.phoenix_spans import (
    activity_points,
    make_span,
    session_catalog,
    session_id,
    session_traces,
    trace_detail,
    trace_id_for,
    write_jsonl,
)
from optagent.snapshot_store import install_archive


def test_session_ids_are_prefixed_and_bare_uuids_do_not_collide() -> None:
    shared = "3d7be767-c52e-4a20-bee7-5b1aa71ca19f"
    gaius = session_id("gaius", "cognition", shared)
    metabase = session_id("metabase", shared)
    assert gaius == f"gaius:cognition:{shared}"
    assert metabase == f"metabase:{shared}"
    assert gaius != metabase
    assert trace_id_for("gaius", shared) != trace_id_for("metabase", shared)
    with pytest.raises(ValueError):
        session_id("semantica", shared)


def test_one_thought_is_one_trace_and_the_project_is_on_the_resource() -> None:
    span = make_span(
        project="gaius",
        session=session_id("gaius", "cognition", "cycle-1"),
        name="curiosity",
        activity="cognition",
        capability="cognition",
        service_name="gaius-engine",
        trace_key="thought-9",
        attributes={"gaius.thought.id": "thought-9", "gaius.thought.type": "curiosity"},
        input_value="curiosity",
        output_value="The thought body.",
    )
    assert span["resource"]["openinference.project.name"] == "gaius"
    assert span["attributes"]["input.value"] == "curiosity"
    assert span["attributes"]["output.value"] == "The thought body."
    assert span["attributes"]["openinference.span.kind"] == "CHAIN"
    assert span["attributes"]["session.id"] == "gaius:cognition:cycle-1"
    assert span["attributes"]["gaius.activity"] == "cognition"
    assert span["attributes"]["gaius.thought.id"] == "thought-9"
    other = make_span(
        project="gaius",
        session=session_id("gaius", "cognition", "cycle-1"),
        name="later",
        activity="cognition",
        capability="cognition",
        service_name="gaius-engine",
        trace_key="thought-10",
        start_time_unix_nano=2_000_000_000_000_000,
        output_value="second body",
    )
    catalog = session_catalog([span, other], ["signals", "gaius"])
    assert catalog["projects"][:2] == ["signals", "gaius"]
    row = catalog["sessions"][0]
    assert row["id"] == "gaius:cognition:cycle-1"
    assert row["trace_count"] == 2
    assert row["name"] == "later"
    assert "output.value" not in row
    traces = session_traces([span, other], row["id"])
    assert traces is not None
    assert "output" not in traces["traces"][0]
    detail = trace_detail([span, other], span["trace_id"])
    assert detail is not None
    assert detail["output"] == "The thought body."
    assert detail["t"] == 0
    assert detail["attributes"]["gaius.thought.type"] == "curiosity"
    later = trace_detail([span, other], other["trace_id"])
    assert later is not None
    assert later["t"] == 2_000_000_000


def test_activity_points_keep_time_and_drop_trace_bodies() -> None:
    span = make_span(
        project="metabase",
        session="metabase:visit-1",
        name="Overview of SDG",
        activity="question",
        capability="dashboard",
        service_name="metabase",
        trace_key="msg-1",
        start_time_unix_nano=1_700_000_000_000_000_000,
        input_value="show the ontology",
        output_value="a long answer",
    )
    points = activity_points([span])
    assert points == [
        {
            "t": 1_700_000_000_000,
            "project": "metabase",
            "activity": "question",
            "session": "metabase:visit-1",
            "name": "Overview of SDG",
        }
    ]
    assert "output.value" not in points[0]


def test_upload_installs_a_version_two_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    root = tmp_path / "build"
    spans = root / "projects" / "gaius" / "spans.jsonl"
    write_jsonl(
        spans,
        [
            make_span(
                project="gaius",
                session="gaius:flow:run-1",
                name="select_article",
                activity="flow",
                capability="cognition",
                service_name="gaius-engine",
                trace_key="run-1:select_article",
                attributes={"gaius.flow.name": "ArticleCurationFlow", "gaius.flow.run_id": "run-1"},
            )
        ],
    )
    document = {
        "format": "signals-snapshot",
        "format-version": 2,
        "snapshot-id": "00000000-0000-7000-8000-0000000000aa",
        "sequence-number": 2,
        "timestamp-ms": 1,
        "summary": {},
        "members": [
            {
                "project": "gaius",
                "kind": "files",
                "name": "hx",
                "metadata-location": "s3://signals-snapshots/sample/workspace/gaius/",
            },
            {
                "project": "gaius",
                "kind": "spans",
                "name": "sessions",
                "metadata-location": "projects/gaius/spans.jsonl",
            },
        ],
    }
    (root / "signals-snapshot.json").write_text(json.dumps(document), encoding="utf-8")
    blob = io.BytesIO()
    with tarfile.open(fileobj=blob, mode="w:gz") as tar:
        tar.add(root / "signals-snapshot.json", arcname="signals-snapshot.json")
        tar.add(spans, arcname="projects/gaius/spans.jsonl")
    installed = install_archive(blob.getvalue())
    assert installed["format-version"] == 2
    assert installed["snapshot-id"].endswith("aa")
    stored = Path(installed["location"])
    assert (stored.parent / "projects" / "gaius" / "spans.jsonl").is_file()
