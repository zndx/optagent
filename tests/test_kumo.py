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
    css = (ROOT / "ui" / "src" / "index.css").read_text(encoding="utf-8")
    assert "@cloudflare/kumo/styles/tailwind" in css
    assert "theme-keiretsu.css" in css


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
