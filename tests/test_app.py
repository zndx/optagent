# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
from pathlib import Path

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
    status, content_type, body = APP.response_for("GET", "/ledger")
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
    status, _, body = APP.response_for("GET", "/ledger")
    page = body.decode("utf-8")
    assert status == 200
    assert "recorded greeting" in page
    assert "Prototype version 0.1.0" in page
    assert "Snapshot written at" in page


def test_home_is_the_empty_agentsview() -> None:
    status, content_type, body = APP.response_for("GET", "/")
    page = body.decode("utf-8")
    assert status == 200
    assert content_type.startswith("text/html")
    assert "agentsview" in page
    assert "No sessions" in page
    assert "No data for this period" in page
    assert "Search sessions and messages..." in page
    assert ">Sessions<" in page
    assert ">0<" in page
    assert 'id="mode-toggle"' in page
    assert 'id="waffle-toggle"' in page
    assert 'aria-label="Settings"' in page
    assert "No peers advertising a primary UI." in page
    assert 'data-theme="keiretsu"' in page
    assert "cldr-color-mode" in page
    assert 'aria-label="Switch to light"' in page
    assert "M788.3 465.9" in page
    status, _, usage = APP.response_for("GET", "/usage")
    assert status == 200
    assert "No data for this period" in usage.decode("utf-8")


def test_settings_shows_the_trace_archive(monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_TRACES_S3_URI", "s3://agent-archive/laptop/raw")
    status, _, body = APP.response_for("GET", "/settings")
    page = body.decode("utf-8")
    assert status == 200
    assert "Trace archive" in page
    assert "s3://agent-archive/laptop/raw" in page
    assert "M788.3 465.9" in page


def test_listen_port(monkeypatch) -> None:
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setenv("CDSW_APP_PORT", "9000")
    assert APP.app_port() == 9000
    monkeypatch.setenv("PORT", "8123")
    assert APP.app_port() == 8123
    monkeypatch.delenv("PORT")
    monkeypatch.delenv("CDSW_APP_PORT")
    assert APP.app_port() == 8123


def test_tiers_and_sessions_pages() -> None:
    status, content_type, body = APP.response_for("GET", "/tiers")
    page = body.decode("utf-8")
    assert status == 200
    assert content_type.startswith("text/html")
    assert "span_tier0" in page
    assert "kudu_scan" in page
    assert "span_tier1" in page
    assert "impala_sql" in page
    status, _, body = APP.response_for("GET", "/sessions")
    page = body.decode("utf-8")
    assert status == 200
    assert "weathership/oss-agentsview" in page
    assert "go.kenn.io/agentsview" in page


def test_health_and_unknown_routes() -> None:
    status, content_type, body = APP.response_for("GET", "/health")
    assert (status, content_type, body) == (200, "text/plain; charset=utf-8", b"ok\n")
    status, _, body = APP.response_for("GET", "/missing")
    assert status == 404
    assert body == b"not found\n"
    status, _, body = APP.response_for("POST", "/")
    assert status == 405
    assert body == b"method not allowed\n"
