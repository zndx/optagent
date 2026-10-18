# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from optagent.snapshot import load_bundled
from optagent.viz import chord_tables

ROOT = Path(__file__).resolve().parents[1]


def test_settings_page_uses_the_kumo_switch() -> None:
    source = (ROOT / "ui" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert 'from "@cloudflare/kumo"' in source
    assert "<Switch" in source
    assert 'label="Sample mode"' in source
    assert "OptAgent" in source
    assert "agentsview" not in source
    assert 'label="Dark theme"' in source
    assert "Logo brand pack" in source
    for label in ("Sessions", "Summary", "Terminal", "Settings"):
        assert f'label: "{label}"' in source
    assert 'label: "Landing"' not in source
    assert 'className="brand" href="/"' in source
    assert "cog-page" in source
    assert "cog-rail" in source
    assert "landing-stat" in source
    assert "cog-year" in source
    assert "Arize Phoenix" in source
    assert "Search sessions" in source
    assert "All profiles" in source
    assert 'aria-label="Tenant"' in source
    assert 'aria-label="signals-snapshot archive"' in source
    assert "sum-rail" in source
    for title in ("CURRENT", "SCRATCH", "ARCHIVE", "LEXICON", "SCHEMA", "TRACING", "Timeline"):
        assert title in source
    assert source.index('sum-group-title">TRACING') < source.index('sum-group-title">LEXICON')
    assert "Training" not in source
    assert "sum-panel" in source
    assert "Close panel" in source
    assert "This term is not in the current release." in source
    assert "This table is not in the current release." in source
    assert "/summary/term/" in source
    assert "function trailToPath" in source
    assert "kind: \"segment\"" in source
    assert "item.genus_iri" in source
    assert "item.overwatch" in source
    assert 'id="terminal"' in source
    assert "Ghostty not connected" in source
    assert "height={28}" in source
    css = (ROOT / "ui" / "src" / "index.css").read_text(encoding="utf-8")
    assert "@cloudflare/kumo/styles/tailwind" in css
    assert "theme-keiretsu.css" in css
    assert ".brand-logo" in css
    assert "height: 28px" in css
    assert ".sum-trail" in css
    assert ".term-full" in css


def test_snapshot_chord_is_holoviews_input() -> None:
    tables = chord_tables(load_bundled())
    assert tables["element"] == "Chord"
    assert tables["raster"] == "datashader"
    names = {node["name"] for node in tables["nodes"]}
    assert {"signals", "gaius", "aegir"} <= names
    assert tables["edges"]


def test_sample_mode_api_round_trip() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "optagent_app_api",
        ROOT / "2_app-serve" / "app.py",
    )
    assert spec is not None and spec.loader is not None
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    status, content_type, body, extra = app.response_for(
        "POST",
        "/api/optagent/v1/sample-mode",
        body=b'{"enabled": true}',
    )
    payload = json.loads(body)
    assert status == 200
    assert content_type.startswith("application/json")
    assert payload["sample_mode"] is True
    assert payload["snapshot_s3_uri"].startswith("s3://")
    cookie = next(value for key, value in extra if key == "Set-Cookie")
    assert "optagent_sid=" in cookie
    assert "HttpOnly" in cookie
    status, _, body, _extra = app.response_for(
        "GET",
        "/api/optagent/v1/workspace",
        {"Cookie": cookie.split(";", 1)[0]},
    )
    loaded = json.loads(body)
    assert status == 200
    assert loaded["sample_mode"] is True
    assert loaded["sample_mode_source"] == "session"
    assert loaded["snapshot"]["members"]


def test_brand_and_theme_are_settings(monkeypatch, tmp_path) -> None:
    import importlib.util

    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        "optagent_app_brand",
        ROOT / "2_app-serve" / "app.py",
    )
    assert spec is not None and spec.loader is not None
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    status, _, body, extra = app.response_for("GET", "/api/optagent/v1/settings")
    payload = json.loads(body)
    assert payload["brand_id"] == "weathership"
    assert [item["id"] for item in payload["brands"]] == ["weathership", "cloudera", "custom"]
    cookie = next(value for key, value in extra if key == "Set-Cookie").split(";", 1)[0]
    status, _, body, _extra = app.response_for(
        "POST",
        "/api/optagent/v1/brand",
        {"Cookie": cookie},
        b'{"brand_id": "cloudera"}',
    )
    assert json.loads(body)["brand_id"] == "cloudera"
    status, _, body, _extra = app.response_for(
        "POST",
        "/api/optagent/v1/theme",
        {"Cookie": cookie},
        b'{"mode": "light"}',
    )
    assert json.loads(body)["color_mode"] == "light"
    status, _, body, _extra = app.response_for("GET", "/api/optagent/v1/settings", {"Cookie": cookie})
    assert json.loads(body)["color_mode"] == "light"
    assert json.loads(body)["brand_id"] == "cloudera"
