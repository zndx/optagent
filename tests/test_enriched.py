# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from optagent.enriched import PRODUCT_ID, build_manifest, product_facts, project_rows, publish
from optagent.lineup import build_lineup
from optagent.phoenix_spans import make_span, write_jsonl

LINEAGE = "https://signals.zndx.org/sdg#DATAENG_LINEAGE"
TEXT = (
    "What keeps pulling me back is that replay is the load-bearing idea, and the provenance axis "
    "is the one structure I trust enough to walk again tomorrow."
)


def _snapshot(tmp_path: Path) -> Path:
    project = tmp_path / "projects" / "hermes"
    project.mkdir(parents=True)
    start = TEXT.index("provenance")
    linked = make_span(
        project="hermes",
        session="hermes:agent-rtc:1",
        name="replay",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="replay",
        start_time_unix_nano=1_700_000_000_000_000_000,
        output_value=TEXT,
        attributes={
            "aegir.genus_code": "18.3.2",
            "aegir.genus_iri": LINEAGE,
            "aegir.genus_label": "Data Lineage and Provenance",
            "aegir.rel_margin_h": 0.11,
            "aegir.tau": 0.1,
            "typesafe.model": "jev-1.14.0",
            "typesafe.input_tokens": 40,
            "sdg.spans": [{
                "start": start,
                "end": start + len("provenance"),
                "text": "provenance",
                "iri": LINEAGE,
                "label": "Data Lineage and Provenance",
                "confidence": 0.99,
            }],
        },
    )
    missed = make_span(
        project="hermes",
        session="hermes:agent-rtc:bare",
        name="bare",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="bare",
        start_time_unix_nano=1_700_000_000_100_000_000,
        output_value="The afternoon conversation stayed with the paper and never settled on a concrete example worth citing today.",
        attributes={
            "aegir.genus_code": "14.4",
            "aegir.genus_iri": "https://signals.zndx.org/sdg#DATAENG_QUALITY",
            "aegir.genus_label": "Data Profiling, Quality and Observability",
            "overwatch.reason": "session-without-terms",
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
        output_value='{"content": "1|--- title: a file dump with many tokens and extra words"}',
        attributes={"aegir.genus_code": "18.1", "aegir.genus_iri": "https://signals.zndx.org/sdg#MBSE"},
    )
    write_jsonl(project / "spans.jsonl", [linked, missed, dump])
    (tmp_path / "signals-snapshot.json").write_text(
        json.dumps({"format": "signals-snapshot", "snapshot-id": "snap-1", "summary": {}}) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_baseline_keeps_short_links_and_omits_scores(tmp_path: Path) -> None:
    root = _snapshot(tmp_path)
    from optagent.enriched import load_snapshot

    snapshot_id, spans = load_snapshot(root)
    rows, unreadable = project_rows(spans, snapshot_id)
    assert unreadable == 1
    assert [row["trace_id"] != "" for row in rows]
    replay = next(row for row in rows if row["genus_iri"] == LINEAGE)
    assert replay["links"] == [{
        "start": TEXT.index("provenance"),
        "end": TEXT.index("provenance") + len("provenance"),
        "text": "provenance",
        "iri": LINEAGE,
        "label": "Data Lineage and Provenance",
        "confidence": 0.99,
    }]
    assert replay["text"] == TEXT
    assert replay["typesafe_input_tokens"] == 40
    assert "factors" not in replay
    manifest = build_manifest(rows, snapshot_id, unreadable=unreadable)
    assert manifest["baseline"] is True
    assert manifest["iteration"] == 1
    assert manifest["links"] == 1
    assert manifest["overwatch_sessions"] == 1
    assert "factors" not in manifest
    stored = {}

    def put(objects: dict[str, bytes]) -> None:
        stored.update(objects)

    def review(facts: dict, summary: str) -> dict:
        assert facts["id"] == PRODUCT_ID
        assert facts["data_uri"] == "s3://signals-dataproducts/optagent/tracing/enriched/1"
        assert facts["iteration"] == "1"
        assert facts["baseline"] == "true"
        assert "no prior product version" in facts["delta"]
        assert summary == facts["quality"]
        assert all(not str(value).startswith("/") for value in facts.values())
        assert "rustfsadmin" not in json.dumps(facts)
        return {"tx_id": "01900000-0000-7000-8000-000000000001", "assessment": "nominal"}

    result = publish(root, put=put, review=review, endpoint="http://127.0.0.1:9010")
    assert result["rows"] == 2
    assert result["links"] == 1
    body = json.loads(stored["traces.jsonl"].splitlines()[0])
    assert body["links"][0]["text"] == "provenance"
    document = json.loads((root / "signals-snapshot.json").read_text(encoding="utf-8"))
    assert document["summary"]["product.id"] == PRODUCT_ID
    assert document["summary"]["product.iteration"] == "1"
    assert document["summary"]["product.tx_id"].endswith("0001")
    lineup = build_lineup([], now_ms=1, product={
        "id": document["summary"]["product.id"],
        "iteration": document["summary"]["product.iteration"],
        "data_uri": document["summary"]["product.data_uri"],
        "tx_id": document["summary"]["product.tx_id"],
        "rows": document["summary"]["product.rows"],
        "links": document["summary"]["product.links"],
    })
    assert lineup["product"]["data_uri"].endswith("/enriched/1")
    facts = product_facts(manifest, lineup["product"]["data_uri"])
    assert facts["run.EnrichedTraceProduct/1.data_uri"].endswith("/enriched/1")
