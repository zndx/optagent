# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import json

import pytest

from optagent.snapshot import KNOWN_KINDS, load_bundled, parse_snapshot, resolve_snapshot


def test_bundled_sample_is_a_pointer_not_a_warehouse_copy() -> None:
    snapshot = load_bundled()
    assert snapshot.snapshot_id == "00000000-0000-7000-8000-000000000001"
    assert snapshot.summary["signals-snapshot.sample"] == "true"
    assert "signals" in snapshot.projects
    assert "gaius" in snapshot.projects
    assert "atelier" in snapshot.projects
    assert "aegir" in snapshot.projects
    assert "metabase" in snapshot.projects
    assert "semantica" in snapshot.projects
    iceberg = [member for member in snapshot.members if member.kind == "iceberg"]
    assert iceberg
    assert iceberg[0].metadata_location.startswith("s3://")
    assert all(member.known_kind for member in snapshot.members)
    assert KNOWN_KINDS == frozenset({"iceberg", "kudu", "files", "relational", "spans"})


def test_unknown_member_kind_is_kept() -> None:
    snapshot = load_bundled()
    payload = {
        "format": "signals-snapshot",
        "format-version": 1,
        "snapshot-id": snapshot.snapshot_id,
        "parent-snapshot-id": None,
        "sequence-number": 2,
        "timestamp-ms": 1,
        "summary": {},
        "members": [
            {
                "project": "future-peer",
                "kind": "graph",
                "name": "catalog",
                "metadata-location": "s3://signals-snapshots/sample/workspace/future-peer/",
                "note": "extension",
            }
        ],
    }
    parsed = parse_snapshot(payload)
    assert parsed.members[0].kind == "graph"
    assert parsed.members[0].known_kind is False
    assert parsed.members[0].extra["note"] == "extension"
    assert parsed.projects == ("future-peer",)


def test_s3_location_does_not_open_the_warehouse() -> None:
    snapshot = resolve_snapshot("s3://signals-snapshots/sample/workspace")
    assert snapshot.location == "s3://signals-snapshots/sample/workspace"
    assert "signals" in snapshot.projects


def test_bad_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="signals-snapshot"):
        parse_snapshot({"format": "other", "format-version": 1, "snapshot-id": "x"})


def test_version_two_keeps_pointer_members_and_span_files() -> None:
    payload = {
        "format": "signals-snapshot",
        "format-version": 2,
        "snapshot-id": "00000000-0000-7000-8000-000000000002",
        "parent-snapshot-id": "00000000-0000-7000-8000-000000000001",
        "sequence-number": 2,
        "timestamp-ms": 1,
        "summary": {"spans.gaius": "1"},
        "members": [
            {
                "project": "gaius",
                "kind": "iceberg",
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
    parsed = parse_snapshot(payload)
    assert parsed.members[0].kind == "iceberg"
    assert parsed.members[1].kind == "spans"
    assert parsed.members[1].known_kind is True


def test_round_trip_json() -> None:
    raw = json.loads(
        (__import__("pathlib").Path(__file__).resolve().parents[1] / "assets/sample/signals-snapshot.json").read_text()
    )
    assert raw["format-version"] == 1
