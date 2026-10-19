# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import io
import json
import tarfile
from pathlib import Path

from optagent.enriched import (
    PRODUCT_ID,
    build_manifest,
    enrichment_counts,
    pack_snapshot,
    product_facts,
    publish,
    signals_root,
)
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
    counts = enrichment_counts(spans)
    assert counts["admitted_unreadable"] == 1
    assert counts["rows"] == 2
    assert counts["links"] == 1
    assert counts["overwatch_sessions"] == 1
    assert "factors" not in counts
    manifest = build_manifest(counts, snapshot_id)
    assert manifest["snapshot_id"] == "snap-1"
    assert manifest["links"] == 1
    assert manifest["overwatch_sessions"] == 1
    assert "factors" not in manifest
    stored: dict[str, bytes] = {}

    def put(uri: str, body: bytes) -> None:
        stored["uri"] = uri.encode()
        stored["body"] = body

    def review(facts: dict, summary: str) -> dict:
        assert facts["id"] == PRODUCT_ID
        assert facts["data_uri"] == "s3://signals-dataproducts/optagent/snapshots/snap-1.tar.gz"
        assert facts["snapshot_id"] == "snap-1"
        assert facts["kind"] == "snapshot"
        assert "parent none" in facts["delta"]
        assert summary == facts["quality"]
        assert all(not str(value).startswith("/") for value in facts.values())
        assert "rustfsadmin" not in json.dumps(facts)
        return {"tx_id": "01900000-0000-7000-8000-000000000001", "assessment": "nominal"}

    result = publish(root, put=put, review=review, endpoint="http://127.0.0.1:9010")
    assert result["rows"] == 2
    assert result["links"] == 1
    assert stored["uri"].decode().endswith("/snap-1.tar.gz")
    with tarfile.open(fileobj=io.BytesIO(stored["body"]), mode="r:gz") as tar:
        document = json.loads(tar.extractfile("signals-snapshot.json").read().decode())
        spans = tar.extractfile("projects/hermes/spans.jsonl").read().decode().splitlines()
    assert document["summary"]["product.version"] == "snap-1"
    assert document["summary"]["product.tx_id"].endswith("0001")
    linked = json.loads(next(line for line in spans if "provenance" in line))
    assert linked["attributes"]["sdg.spans"][0]["text"] == "provenance"
    assert pack_snapshot(root)
    lineup = build_lineup([], now_ms=1, product={
        "id": document["summary"]["product.id"],
        "version": document["summary"]["product.version"],
        "data_uri": document["summary"]["product.data_uri"],
        "tx_id": document["summary"]["product.tx_id"],
        "rows": document["summary"]["product.rows"],
        "links": document["summary"]["product.links"],
    })
    assert lineup["product"]["version"] == "snap-1"
    assert lineup["product"]["data_uri"].endswith("/snap-1.tar.gz")
    facts = product_facts(manifest, lineup["product"]["data_uri"])
    assert facts["run.Snapshot/snap-1.data_uri"].endswith("/snap-1.tar.gz")


def test_signals_root_defaults_to_the_user_checkout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SIGNALS_ROOT", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert signals_root() == tmp_path / "local" / "src" / "wxs" / "signals"
    monkeypatch.setenv("SIGNALS_ROOT", str(tmp_path / "elsewhere"))
    assert signals_root() == tmp_path / "elsewhere"
