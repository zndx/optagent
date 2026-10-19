# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import io
import json
import tarfile
from pathlib import Path

from optagent.phoenix_spans import make_span, write_jsonl

from optagent.status import DEFAULT_GREETING, write_status

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INSTALL = _load(
    "optagent_install",
    ROOT / "0_session-install-dependencies" / "install-dependencies.py",
)
APP = _load("optagent_app", ROOT / "2_app-serve" / "app.py")


def test_install_skips_an_empty_requirements_file(tmp_path: Path, monkeypatch) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("# none\n\n", encoding="utf-8")
    monkeypatch.setenv("CDSW_PROJECT_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert INSTALL.installable_lines(requirements.read_text(encoding="utf-8")) == []
    INSTALL.main()


def test_prepare_job_writes_the_snapshot(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "status.json"
    monkeypatch.setenv("OPTAGENT_STATUS_PATH", str(destination))
    monkeypatch.setenv("OPTAGENT_GREETING", "good morning")
    job = _load("optagent_job", ROOT / "1_job-prepare-project" / "job.py")
    job.main()
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["name"] == "Optagent"
    assert payload["greeting"] == "good morning"
    assert payload["prototype_version"] == "0.1.0"
    assert payload["written_at"].endswith("Z")
    assert payload["warehouse"]["postgres"] in {"ok", "unreachable", "psycopg-missing"}
    assert payload["warehouse"]["fdw"] in {"impala_fdw", "absent"}


def test_page_reports_a_missing_snapshot(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_STATUS_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setenv("OPTAGENT_GREETING", DEFAULT_GREETING)
    status, content_type, body, _extra = APP.response_for("GET", "/ledger")
    page = body.decode("utf-8")
    assert status == 200
    assert content_type.startswith("text/html")
    assert "Optagent" in page
    assert DEFAULT_GREETING in page
    assert "has not written a snapshot" in page


def test_page_shows_the_snapshot(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "status.json"
    write_status(destination, "recorded greeting", "0.1.0")
    monkeypatch.setenv("OPTAGENT_STATUS_PATH", str(destination))
    status, _, body, _extra = APP.response_for("GET", "/ledger")
    page = body.decode("utf-8")
    assert status == 200
    assert "recorded greeting" in page
    assert "Prototype version 0.1.0" in page
    assert "Snapshot written at" in page


def test_home_is_the_kumo_settings_app() -> None:
    status, content_type, body, _extra = APP.response_for("GET", "/")
    page = body.decode("utf-8")
    assert status == 200
    assert content_type.startswith("text/html")
    assert 'id="root"' in page
    assert "/assets/index-" in page
    status, _, asset, _extra = APP.response_for("GET", "/settings")
    assert status == 200
    assert 'id="root"' in asset.decode("utf-8")


def test_settings_shows_the_trace_archive(monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_TRACES_S3_URI", "s3://agent-archive/laptop/raw")
    status, content_type, body, _extra = APP.response_for("GET", "/api/optagent/v1/settings")
    payload = json.loads(body)
    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["traces_s3_uri"] == "s3://agent-archive/laptop/raw"


def test_sample_mode_is_a_session_not_a_query(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.delenv("OPTAGENT_SAMPLE_MODE", raising=False)
    status, _, body, extra = APP.response_for("GET", "/api/optagent/v1/settings?sample=on")
    assert json.loads(body)["sample_mode"] is False
    assert json.loads(body)["sample_mode_source"] == "hocon"
    status, _, body, extra = APP.response_for(
        "POST",
        "/api/optagent/v1/sample-mode",
        {"Cookie": extra[0][1].split(";", 1)[0]},
        b'{"enabled": true}',
    )
    assert json.loads(body)["sample_mode"] is True
    cookie = next(value for key, value in extra if key == "Set-Cookie").split(";", 1)[0]
    status, _, ledger, _extra = APP.response_for("GET", "/ledger", {"Cookie": cookie})
    page = ledger.decode("utf-8")
    assert "Sample workspace" in page
    assert "gaius" in page
    assert "Impala is not contacted" in page
    payload = json.loads(body)
    assert payload["snapshot_s3_uri"] == "s3://signals-snapshots/sample/workspace"
    assert payload["snapshot_endpoint"] == "http://127.0.0.1:9010"


def test_listen_port(monkeypatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("CDSW_APP_PORT", "9000")
    assert APP.app_port() == 9000
    monkeypatch.setenv("PORT", "8123")
    assert APP.app_port() == 8123
    monkeypatch.delenv("PORT")
    monkeypatch.delenv("CDSW_APP_PORT")
    monkeypatch.delenv("OPTAGENT_BIND", raising=False)
    monkeypatch.delenv("CDSW_PROJECT_DIR", raising=False)
    assert APP.app_port() == 9892
    assert APP.listen_host() == "0.0.0.0"
    monkeypatch.setenv("CDSW_APP_PORT", "9000")
    assert APP.listen_host() == "127.0.0.1"


def test_tiers_page_names_the_span_stores() -> None:
    status, content_type, body, _extra = APP.response_for("GET", "/tiers")
    page = body.decode("utf-8")
    assert status == 200
    assert content_type.startswith("text/html")
    assert "span_tier0" in page
    assert "kudu_scan" in page
    assert "span_tier1" in page
    assert "impala_sql" in page


def test_framed_pages_share_one_shell() -> None:
    shell = None
    for route in ("/", "/sessions", "/summary", "/terminal", "/settings"):
        status, content_type, body, _extra = APP.response_for("GET", route)
        page = body.decode("utf-8")
        assert status == 200
        assert content_type.startswith("text/html")
        assert "<title>OptAgent</title>" in page
        assert 'id="root"' in page
        shell = shell or page
        assert page == shell
    status, content_type, body, _extra = APP.response_for(
        "GET",
        "/summary/hermes/agent-rtc:802225c3cb6e/DATAENG_LINEAGE",
    )
    assert status == 200
    assert content_type.startswith("text/html")
    assert body.decode("utf-8") == shell


def test_summary_reads_the_varnish_lineup(monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_VARNISH_PORT", "6095")
    seen: dict[str, object] = {}

    class Response(io.BytesIO):
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args) -> bool:
            return False

    def fake_open(url, timeout=0):
        seen["url"] = url
        seen["timeout"] = timeout
        body = json.dumps({
            "format": "optagent-summary",
            "lineup": {"pin": "cached", "sessions_by_project": {"hermes": []}},
            "groups": [],
        }).encode()
        return Response(body)

    monkeypatch.setattr(APP.urllib.request, "urlopen", fake_open)
    status, _, body, _extra = APP.response_for("GET", "/api/optagent/v1/summary?window=365d&project=hermes")
    document = json.loads(body)
    assert status == 200
    assert document["lineup"]["pin"] == "cached"
    url = str(seen["url"])
    assert "summary_origin?" in url
    assert "kind=lineup" in url
    assert "window=" not in url
    assert "project=" not in url
    assert seen["timeout"] == 30
    status, _, body, _extra = APP.response_for(
        "GET",
        "/api/optagent/v1/summary?window=7d&project=gaius&ranges=10:20",
    )
    assert json.loads(body)["lineup"]["pin"] == "cached"
    url = str(seen["url"])
    assert "kind=lineup" in url
    assert "window=7d" in url
    assert "project=" not in url
    assert "ranges=" not in url


def test_summary_window_is_its_own_cached_object(monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_VARNISH_PORT", "6095")
    seen: dict[str, object] = {}

    class Response(io.BytesIO):
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args) -> bool:
            return False

    def fake_open(url, timeout=0):
        seen["url"] = url
        seen["timeout"] = timeout
        return Response(json.dumps({"window": "7d", "timeline": {"window": "7d"}, "tracing": {"window": "7d"}}).encode())

    monkeypatch.setattr(APP.urllib.request, "urlopen", fake_open)
    status, _, body, _extra = APP.response_for("GET", "/api/optagent/v1/summary_window?window=7d")
    assert status == 200
    assert json.loads(body)["window"] == "7d"
    url = str(seen["url"])
    assert "kind=window" in url
    assert "window=7d" in url
    assert "kind=lineup" not in url
    assert seen["timeout"] == 30


def test_summary_ranges_are_their_own_cached_object(monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_VARNISH_PORT", "6095")
    seen: dict[str, object] = {}

    class Response(io.BytesIO):
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args) -> bool:
            return False

    def fake_open(url, timeout=0):
        seen["url"] = url
        seen["timeout"] = timeout
        return Response(json.dumps({"ranges": [{"start": 10, "end": 20}]}).encode())

    monkeypatch.setattr(APP.urllib.request, "urlopen", fake_open)
    status, _, body, _extra = APP.response_for("GET", "/api/optagent/v1/summary_ranges?ranges=10:20")
    assert status == 200
    assert json.loads(body)["ranges"][0]["start"] == 10
    url = str(seen["url"])
    assert "kind=ranges" in url
    assert "ranges=10" in url
    assert "kind=lineup" not in url
    assert seen["timeout"] == 30


def test_summary_and_sessions_origins_skip_varnish(monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_VARNISH_PORT", "1")
    status, content_type, body, _extra = APP.response_for("GET", "/api/optagent/v1/summary_origin")
    summary = json.loads(body)
    assert status == 200
    assert content_type.startswith("application/json")
    assert summary["format"] == "optagent-summary"
    assert "sessions_by_project" in summary["lineup"]
    assert summary["groups"][0]["title"] == "SECTION"
    assert any(panel["project"] == "aegir" for panel in summary["panels"])
    assert "metadata-location" in summary["panels"][0]["body"]
    status, _, body, _extra = APP.response_for("GET", "/api/optagent/v1/sessions_origin")
    sessions = json.loads(body)
    assert sessions["provider"] == "arize-phoenix"
    assert sessions["connected"] is False
    assert sessions["format-version"] == 2
    assert any(item["id"] == "aegir" for item in sessions["tenants"])
    assert any(item["name"] == "default" and item["tenant"] == "aegir" for item in sessions["profiles"])
    assert "not copied" in sessions["note"]
    assert all("messages" not in item for item in sessions["sessions"])
    status, _, body, _extra = APP.response_for("GET", "/api/optagent/v1/summary")
    assert json.loads(body)["format"] == "optagent-summary"
    status, _, body, _extra = APP.response_for("GET", "/api/optagent/v1/sessions")
    assert json.loads(body)["provider"] == "arize-phoenix"


def test_settings_upload_is_readable_without_varnish_or_phoenix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.setenv("OPTAGENT_VARNISH_PORT", "1")
    monkeypatch.setenv("CDSW_PROJECT_DIR", "")
    span = make_span(
        project="gaius",
        session="gaius:cognition:cycle-1",
        name="curiosity",
        activity="cognition",
        capability="cognition",
        service_name="gaius-engine",
        trace_key="thought-1",
        start_time_unix_nano=1_772_010_915_092_724_000,
        input_value="What changed?",
        output_value="The thought body.",
    )
    root = tmp_path / "build"
    write_jsonl(root / "projects" / "gaius" / "spans.jsonl", [span])
    document = {
        "format": "signals-snapshot",
        "format-version": 2,
        "snapshot-id": "00000000-0000-7000-8000-0000000000bb",
        "sequence-number": 2,
        "timestamp-ms": 1,
        "summary": {},
        "members": [
            {
                "project": "signals",
                "kind": "iceberg",
                "name": "hx",
                "metadata-location": "s3://signals-snapshots/sample/workspace/signals/",
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
        tar.add(root / "projects" / "gaius" / "spans.jsonl", arcname="projects/gaius/spans.jsonl")
    status, _, body, _extra = APP.response_for("POST", "/api/optagent/v1/snapshot", body=blob.getvalue())
    uploaded = json.loads(body)
    assert status == 200
    assert uploaded["loaded_snapshot_id"] == document["snapshot-id"]
    status, _, body, _extra = APP.response_for("GET", "/api/optagent/v1/activity")
    activity = json.loads(body)
    assert status == 200
    assert "signals" in activity["projects"]
    assert activity["points"][0]["t"] == 1_772_010_915_092
    assert "output" not in activity["points"][0]
    status, _, body, _extra = APP.response_for("GET", "/api/optagent/v1/sessions")
    catalog = json.loads(body)["phoenix"]
    assert catalog["sessions"][0]["trace_count"] == 1
    assert "output.value" not in catalog["sessions"][0]
    status, _, body, _extra = APP.response_for(
        "GET", "/api/optagent/v1/trace?id=" + span["trace_id"]
    )
    detail = json.loads(body)
    assert status == 200
    assert detail["input"] == "What changed?"
    assert detail["output"] == "The thought body."
    assert detail["t"] == 1_772_010_915_092


def test_health_and_unknown_routes() -> None:
    status, content_type, body, _extra = APP.response_for("GET", "/health")
    assert (status, content_type, body) == (200, "text/plain; charset=utf-8", b"ok\n")
    status, _, body, _extra = APP.response_for("GET", "/missing")
    assert status == 404
    assert body == b"not found\n"
    status, _, body, _extra = APP.response_for("POST", "/")
    assert status == 405
    assert body == b"method not allowed\n"
