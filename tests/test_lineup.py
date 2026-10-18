# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from optagent.lineup import SDG_PIN, bucket_unit, build_lineup, load_lexicon, load_schema, timeline_report, token_count
from optagent.phoenix_spans import make_span, rich_segments


def test_scratch_is_present_and_snapshot_only_without_a_stream() -> None:
    lineup = build_lineup([], now_ms=1_700_000_000_000, live=False)
    scratch = next(item for item in lineup["roots"] if item["id"] == "scratch")
    assert scratch["title"] == "SCRATCH"
    assert scratch["live"] is False
    assert lineup["pin"] == SDG_PIN


def test_an_unknown_iri_does_not_create_a_lexicon_panel() -> None:
    span = make_span(
        project="hermes",
        session="hermes:agent-rtc:1",
        name="lims",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="m1",
        start_time_unix_nano=1_700_000_000_000_000_000,
        output_value="The specimen is accessioned. The assay is run.",
        attributes={
            "sdg.spans": [
                {
                    "start": 0,
                    "end": 28,
                    "text": "The specimen is accessioned.",
                    "iri": "https://signals.zndx.org/sdg#NOT_A_PUBLISHED_TERM",
                    "label": "Missing",
                    "confidence": 0.4,
                }
            ],
            "sdg.augmented_at": 1_700_000_100_000,
        },
    )
    lineup = build_lineup([span], now_ms=1_700_000_100_000, project="hermes")
    assert all(item["iri"] != "https://signals.zndx.org/sdg#NOT_A_PUBLISHED_TERM" for item in lineup["lexicon"])
    session = lineup["sessions"][0]
    assert session["items"][0]["augmented_at"] == 1_700_000_100_000
    assert session["items"][0]["generated_at"] == 1_700_000_000_000
    sentence = "".join(part["text"] for part in session["items"][0]["rich"])
    assert sentence == "The specimen is accessioned. The assay is run."
    linked = [part for part in session["items"][0]["rich"] if part.get("iri")]
    assert linked[0]["iri"].endswith("NOT_A_PUBLISHED_TERM")
    report = lineup["tracing"]["projects"][0]
    assert report["traces"] == 1
    assert report["latency_ms"] is None
    assert report["total_cost"] is None
    assert report["errors"] is None
    assert report["top_iris"][0]["iri"].endswith("NOT_A_PUBLISHED_TERM")
    assert token_count(span) == len("The specimen is accessioned. The assay is run.".split())
    assert rich_segments(span["attributes"]["output.value"], span["attributes"]["sdg.spans"])


def test_broader_is_a_lexicon_link_and_not_a_class(tmp_path: Path) -> None:
    vocab = tmp_path / "vocabulary"
    vocab.mkdir()
    (vocab / "vocabulary.ttl").write_text(
        "\n".join(
            [
                '<https://signals.zndx.org/sdg#PARENT> a skos:Concept ;',
                '    skos:notation "1" ;',
                '    skos:prefLabel "Parent" ;',
                '    skos:definition "The parent topic." .',
                "",
                '<https://signals.zndx.org/sdg#CHILD> a skos:Concept ;',
                '    skos:notation "1.1" ;',
                '    skos:prefLabel "Child" ;',
                '    skos:definition "The child topic." ;',
                "    skos:broader <https://signals.zndx.org/sdg#PARENT> .",
                "",
            ]
        ),
        encoding="utf-8",
    )
    items = {item["iri"]: item for item in load_lexicon(tmp_path)}
    child = items["https://signals.zndx.org/sdg#CHILD"]
    parent = items["https://signals.zndx.org/sdg#PARENT"]
    assert child["broader"] == ["https://signals.zndx.org/sdg#PARENT"]
    assert "subClassOf" not in child
    assert parent["narrower"] == ["https://signals.zndx.org/sdg#CHILD"]
    assert child["narrower"] == []


def test_schema_foreign_keys_are_table_links(tmp_path: Path) -> None:
    ddl = tmp_path / "ddl" / "run"
    ddl.mkdir(parents=True)
    (ddl / "ddl.sql").write_text(
        "\n".join(
            [
                "CREATE TABLE specimen (",
                "  id VARCHAR(255) NOT NULL,",
                "  volume DECIMAL(38,9),",
                "  PRIMARY KEY (id)",
                ");",
                "CREATE TABLE assay (",
                "  id VARCHAR(255) NOT NULL,",
                "  run_on VARCHAR(255) NOT NULL,",
                "  PRIMARY KEY (id)",
                ");",
                "ALTER TABLE assay ADD FOREIGN KEY (run_on) REFERENCES specimen(id);",
                "",
            ]
        ),
        encoding="utf-8",
    )
    tables = {item["name"]: item for item in load_schema(tmp_path)}
    assert tables["specimen"]["columns"] == ["id", "volume"]
    assert tables["specimen"]["refs"] == []
    assert tables["assay"]["columns"] == ["id", "run_on"]
    assert tables["assay"]["refs"] == ["specimen"]


def _tiles(report: dict) -> None:
    bins = report["bins"]
    assert bins[0]["start"] == report["start"]
    assert bins[-1]["end"] == report["end"]
    for previous, current in zip(bins, bins[1:]):
        assert previous["end"] == current["start"]


def test_timeline_bins_follow_the_gaius_histogram() -> None:
    now = 1_700_000_000_000
    hours = timeline_report([], now_ms=now, window="24h")
    assert hours["unit"] == "hour"
    assert len(hours["bins"]) == 24
    _tiles(hours)
    six = timeline_report([], now_ms=now, window="7d")
    assert six["unit"] == "6h"
    assert len(six["bins"]) == 28
    _tiles(six)
    days = timeline_report([], now_ms=now, window="30d")
    assert days["unit"] == "day"
    _tiles(days)
    quarter = timeline_report([], now_ms=now, window="90d")
    assert quarter["unit"] == "day"
    _tiles(quarter)
    year = timeline_report([], now_ms=now, window="365d")
    assert year["unit"] == "week"
    _tiles(year)
    assert bucket_unit(1200 * 86_400_000) == "month"


def test_each_bin_counts_topic_domains_without_invented_metrics() -> None:
    now = 1_700_000_000_000
    inside = (now - 3_600_000) * 1_000_000
    span = make_span(
        project="hermes",
        session="hermes:agent-rtc:1",
        name="lims",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="bin-1",
        start_time_unix_nano=inside,
        output_value="The specimen is accessioned.",
        attributes={
            "aegir.genus_code": "16.2",
            "aegir.genus_iri": "https://signals.zndx.org/sdg#LIMS",
            "sdg.spans": [
                {
                    "start": 0,
                    "end": 4,
                    "text": "The",
                    "iri": "https://signals.zndx.org/sdg#LIMS_SPECIMEN_LIFECYCLE",
                    "label": "Specimen",
                }
            ],
        },
    )
    plain = make_span(
        project="hermes",
        session="hermes:agent-rtc:2",
        name="plain",
        activity="agent-rtc",
        capability="conversation",
        service_name="agent-rtc",
        trace_key="bin-2",
        start_time_unix_nano=inside,
        output_value="hello",
    )
    report = timeline_report([span, plain], now_ms=now, window="24h")
    hot = next(item for item in report["bins"] if item["traces"])
    assert hot["traces"] == 2
    assert hot["undomain"] == 1
    assert hot["latency_ms"] is None
    assert hot["total_cost"] is None
    assert hot["errors"] is None
    domain = hot["domains"][0]
    assert domain["code"] == "16.2"
    assert domain["iri"].endswith("#LIMS")
    assert domain["traces"] == 1
    assert domain["grounded"] == 1
    assert domain["top_iris"][0]["iri"].endswith("LIMS_SPECIMEN_LIFECYCLE")
    assert domain["top_sessions"][0]["id"] == "hermes:agent-rtc:1"
    assert report["totals"]["traces"] == 2
    assert report["domains"][0]["code"] == "16.2"
