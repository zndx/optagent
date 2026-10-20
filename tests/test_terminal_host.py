# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import json
import os

from optagent import terminal_host
from optagent.terminal_host import create_session, list_sessions, move_session


def _reset() -> None:
    for name in (
        "OPTAGENT_MODEL",
        "OPTAGENT_MODEL_NAME",
        "OPTAGENT_MODEL_BASE_URL",
        "OPTAGENT_MODEL_API_KEY_ENV",
        "OPTAGENT_MODEL_BACKEND",
        "OPTAGENT_MODELS_JSON",
        "OPTAGENT_MODEL_API_KEY",
    ):
        os.environ.pop(name, None)
    for session in list(terminal_host._SESSIONS.values()):
        proc = session._proc
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
    terminal_host._SESSIONS.clear()


def test_the_settings_brand_replaces_the_grok_mark(monkeypatch, tmp_path) -> None:
    _reset()
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(state))
    monkeypatch.delenv("OPTAGENT_BRAND_ID", raising=False)
    (state / "optagent-ui.json").write_text('{"brand_id": "weathership"}\n', encoding="utf-8")
    rewriter = terminal_host.LogoRewriter()
    block = "\n".join(terminal_host._GROK_LOGO_SMALL) + "\nGrok Build  1.0.62"
    shown = (rewriter.feed(block.encode()) + rewriter.finish()).decode("utf-8")
    weather = dict(terminal_host.brand_logo_pairs("weathership"))
    assert weather[terminal_host._GROK_LOGO_SMALL[1]] in shown
    assert "OptAgent" in shown
    assert "Grok Build" not in shown
    assert "⣀⣤⣤⣀" not in shown
    (state / "optagent-ui.json").write_text('{"brand_id": "cloudera"}\n', encoding="utf-8")
    other = terminal_host.LogoRewriter()
    raw = "\n".join(terminal_host._GROK_LOGO_FULL).encode()
    text = (other.feed(raw[:12]) + other.feed(raw[12:]) + other.finish()).decode("utf-8")
    cloudera = dict(terminal_host.brand_logo_pairs("cloudera"))
    assert cloudera[terminal_host._GROK_LOGO_FULL[2]] in text
    assert weather[terminal_host._GROK_LOGO_SMALL[1]] not in text
    assert "⣀⣀⡀" not in text


def test_resize_wakes_the_harness(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    _fake_grok(tmp_path, monkeypatch)
    created = create_session("current", "66666666-6666-4666-8666-666666666666")
    session = terminal_host.get_session(created["id"])
    seen: list[int] = []
    real_kill = os.kill

    def record(pid: int, sig: int) -> None:
        seen.append(sig)
        if sig != terminal_host.signal.SIGWINCH:
            real_kill(pid, sig)

    monkeypatch.setattr(os, "kill", record)
    session.resize(100, 40)
    assert terminal_host.signal.SIGWINCH in seen
    assert session._proc is not None
    real_kill(session._proc.pid, terminal_host.signal.SIGKILL)
    session._proc.wait(timeout=2)


def test_brand_ascii_matches_the_harness_mark() -> None:
    for brand, small, full in (
        ("weathership", 10, 14),
        ("cloudera", 10, 14),
    ):
        pairs = terminal_host.brand_logo_pairs(brand)
        widths = {len(source) for source, _dest in pairs}
        assert widths == {small, full}
        assert all(len(source) == len(dest) for source, dest in pairs)
        ink = max(sum(ch not in " \u2800" for ch in dest) for _source, dest in pairs)
        assert ink >= 6


def test_a_browser_id_attaches_once_and_stays_inline(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    binary = tmp_path / "grok"
    binary.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("optagent.terminal_host.grok_bin", lambda: binary)
    monkeypatch.setattr("optagent.terminal_host.shutil.which", lambda name: None)
    session_id = "3d7be767-c52e-4a20-bee7-5b1aa71ca19f"
    first = create_session("current", session_id)
    again = create_session("current", session_id)
    assert first["id"] == session_id
    assert again["id"] == session_id
    assert first["status"] == "host"
    assert "--fullscreen" not in first_command(session_id)
    assert "--minimal" in first_command(session_id)
    assert "--no-alt-screen" in first_command(session_id)
    assert list_sessions("current")[0]["id"] == session_id
    proc = __import__("optagent.terminal_host", fromlist=["get_session"]).get_session(session_id)._proc
    assert proc is not None
    proc.kill()
    proc.wait(timeout=2)


def first_command(session_id: str) -> list[str]:
    return __import__("optagent.terminal_host", fromlist=["get_session"]).get_session(session_id).command


def test_a_project_grok_is_used_when_the_env_bin_is_absent(monkeypatch, tmp_path) -> None:
    binary = tmp_path / "grok"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.delenv("OPTAGENT_GROK_BIN", raising=False)
    monkeypatch.delenv("GAIUS_GROK_BIN", raising=False)
    monkeypatch.setattr("optagent.terminal_host.shipped_grok", lambda: binary)
    from optagent.terminal_host import grok_bin

    assert grok_bin() == binary


def test_missing_grok_still_records_a_server_session(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.setattr("optagent.terminal_host.grok_bin", lambda: None)
    created = create_session("current")
    assert created["status"] == "grok-missing"
    assert created["section"] == "current"
    listed = list_sessions("current")
    assert [item["id"] for item in listed] == [created["id"]]
    moved = move_session(created["id"], "archive")
    assert moved["section"] == "archive"
    assert list_sessions("current") == []
    assert list_sessions("archive")[0]["id"] == created["id"]
    text = __import__("optagent.terminal_host", fromlist=["get_session"]).get_session(created["id"]).read(0)
    assert "just grok-build" in text["data"]


def _fake_grok(tmp_path, monkeypatch):
    binary = tmp_path / "grok"
    binary.write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("optagent.terminal_host.grok_bin", lambda: binary)
    monkeypatch.setattr("optagent.terminal_host.shutil.which", lambda name: None)


def test_a_configured_endpoint_is_written_without_the_api_key(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.setenv("OPTAGENT_MODEL_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("OPTAGENT_MODEL_NAME", "qwen")
    monkeypatch.setenv("OPTAGENT_MODEL_API_KEY", "super-secret-value")
    _fake_grok(tmp_path, monkeypatch)
    session_id = "11111111-1111-4111-8111-111111111111"
    created = create_session("current", session_id)
    assert created["status"] == "host"
    assert created["detail"].startswith("optagent")
    assert "super-secret-value" not in created["detail"]
    command = first_command(session_id)
    assert command[command.index("-m") + 1] == "optagent"
    assert "super-secret-value" not in command
    config = (tmp_path / "terminals" / session_id / "grok-home" / "config.toml").read_text(encoding="utf-8")
    assert 'base_url = "http://127.0.0.1:8000/v1"' in config
    assert 'model = "qwen"' in config
    assert 'env_key = "OPTAGENT_MODEL_API_KEY"' in config
    assert "super-secret-value" not in config
    session = terminal_host.get_session(session_id)
    assert session.child_env["GROK_HOME"].endswith("/grok-home")
    assert session.child_env["OPTAGENT_MODEL_API_KEY"] == "super-secret-value"
    assert session._proc is not None
    session._proc.kill()
    session._proc.wait(timeout=2)


def test_models_json_selects_one_endpoint(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.setenv(
        "OPTAGENT_MODELS_JSON",
        json.dumps(
            [
                {"id": "local", "model": "qwen", "base_url": "http://127.0.0.1:8000/v1"},
                {"id": "hosted", "model": "grok-4", "base_url": "https://api.example.com/v1", "backend": "responses"},
            ]
        ),
    )
    monkeypatch.setenv("OPTAGENT_MODEL", "hosted")
    _fake_grok(tmp_path, monkeypatch)
    session_id = "22222222-2222-4222-8222-222222222222"
    created = create_session("current", session_id)
    assert created["detail"].startswith("hosted")
    config = (tmp_path / "terminals" / session_id / "grok-home" / "config.toml").read_text(encoding="utf-8")
    assert "https://api.example.com/v1" in config
    assert "127.0.0.1:8000" not in config
    assert 'api_backend = "responses"' in config
    session = terminal_host.get_session(session_id)
    assert session._proc is not None
    session._proc.kill()
    session._proc.wait(timeout=2)


def test_an_unknown_model_does_not_spawn(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.setenv("OPTAGENT_MODEL", "missing")
    monkeypatch.setenv(
        "OPTAGENT_MODELS_JSON",
        json.dumps([{"id": "local", "base_url": "http://127.0.0.1:8000/v1"}]),
    )
    _fake_grok(tmp_path, monkeypatch)
    created = create_session("scratch", "33333333-3333-4333-8333-333333333333")
    assert created["status"] == "model-config"
    assert "missing" in created["detail"]
    assert terminal_host.get_session(created["id"])._proc is None


def test_mistral_endpoints_wait_until_they_are_named(monkeypatch) -> None:
    _reset()
    monkeypatch.delenv("MISTRAL_MODEL", raising=False)
    monkeypatch.delenv("MISTRAL_WORKSPACE_MODEL", raising=False)
    assert terminal_host.resolve_model() is None
    monkeypatch.setenv("OPTAGENT_MODEL", "mistral")
    plain = terminal_host.resolve_model()
    assert plain is not None
    assert plain.base_url == "https://api.mistral.ai/v1"
    assert plain.api_key_env == "MISTRAL_API_KEY"
    assert plain.model == "mistral-small-latest"
    monkeypatch.setenv("OPTAGENT_MODEL", "mistral-studio")
    studio = terminal_host.resolve_model()
    assert studio is not None
    assert studio.api_key_env == "MISTRAL_WORKSPACE_API_KEY"
    assert studio.label_env == "MISTRAL_WORKSPACE_ID"


def test_mistral_studio_session_records_the_workspace_id_not_the_key(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.setenv("OPTAGENT_MODEL", "mistral-studio")
    monkeypatch.setenv("MISTRAL_WORKSPACE_API_KEY", "workspace-secret-value")
    monkeypatch.setenv("MISTRAL_WORKSPACE_ID", "019b2bd7-96e7-7219-8c0b-45a73da50088")
    monkeypatch.setattr("optagent.terminal_host._local_dotenv_values", lambda: {})
    _fake_grok(tmp_path, monkeypatch)
    session_id = "55555555-5555-4555-8555-555555555555"
    created = create_session("current", session_id)
    assert created["status"] == "host"
    assert "019b2bd7-96e7-7219-8c0b-45a73da50088" in created["detail"]
    assert "workspace-secret-value" not in created["detail"]
    config = (tmp_path / "terminals" / session_id / "grok-home" / "config.toml").read_text(encoding="utf-8")
    assert 'base_url = "https://api.mistral.ai/v1"' in config
    assert 'env_key = "MISTRAL_WORKSPACE_API_KEY"' in config
    assert "workspace-secret-value" not in config
    assert "019b2bd7-96e7-7219-8c0b-45a73da50088" not in config
    session = terminal_host.get_session(session_id)
    assert session.child_env["MISTRAL_WORKSPACE_API_KEY"] == "workspace-secret-value"
    assert session._proc is not None
    session._proc.kill()
    session._proc.wait(timeout=2)


def test_a_key_in_the_model_url_is_rejected(monkeypatch, tmp_path) -> None:
    _reset()
    monkeypatch.setenv("OPTAGENT_SESSION_DIR", str(tmp_path))
    monkeypatch.setenv("OPTAGENT_MODEL_BASE_URL", "http://user:super-secret-value@127.0.0.1:8000/v1")
    _fake_grok(tmp_path, monkeypatch)
    created = create_session("archive", "44444444-4444-4444-8444-444444444444")
    assert created["status"] == "model-config"
    assert "super-secret-value" not in created["detail"]
    assert terminal_host.get_session(created["id"])._proc is None
