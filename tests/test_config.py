# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import subprocess
from pathlib import Path

import pytest

from optagent.config import load_runtime
from optagent.secrets import apply_dotenv

ROOT = Path(__file__).resolve().parents[1]


def _register():
    path = ROOT / "scripts" / "warehouse" / "register_impala_fdw.py"
    spec = importlib.util.spec_from_file_location("optagent_register_fdw", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_posture_stays_on_the_fdw(monkeypatch) -> None:
    monkeypatch.delenv("OPTAGENT_POSTURE", raising=False)
    monkeypatch.delenv("OPTAGENT_CDE_ENABLED", raising=False)
    runtime = load_runtime()
    assert runtime.posture == "local"
    assert runtime.uses_fdw
    assert not runtime.direct_impala
    assert runtime.database_url == "postgres://127.0.0.1:5599/optagent"
    assert runtime.cde_enabled is False


def test_amp_posture_is_impala_only(monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_POSTURE", "amp")
    monkeypatch.setenv("IMPALA_HS2_HOST", "tinybox.dev.vista.zndx.org")
    monkeypatch.setenv("IMPALA_HS2_PORT", "21050")
    monkeypatch.setenv("IMPALA_KRB_PRINCIPAL", "optagent@DEV.VISTA.ZNDX.ORG")
    monkeypatch.setenv("OPTAGENT_CDE_ENABLED", "true")
    monkeypatch.delenv("IMPALA_AUTH", raising=False)
    runtime = load_runtime()
    assert runtime.direct_impala
    assert not runtime.uses_fdw
    assert runtime.impala_host == "tinybox.dev.vista.zndx.org"
    assert runtime.impala_port == 21050
    assert runtime.auth == "kerberos"
    assert runtime.principal == "optagent@DEV.VISTA.ZNDX.ORG"
    assert runtime.cde_enabled is True


def test_amp_posture_rejects_nosasl(monkeypatch) -> None:
    monkeypatch.setenv("OPTAGENT_POSTURE", "amp")
    monkeypatch.setenv("IMPALA_AUTH", "nosasl")
    with pytest.raises(ValueError, match="kerberos"):
        load_runtime()


def test_sample_snapshot_stays_off_the_live_warehouse(monkeypatch) -> None:
    monkeypatch.delenv("OPTAGENT_POSTURE", raising=False)
    monkeypatch.delenv("OPTAGENT_SAMPLE_MODE", raising=False)
    monkeypatch.delenv("OPTAGENT_SNAPSHOT_ENDPOINT", raising=False)
    local = load_runtime()
    assert local.sample_mode is False
    assert local.snapshot_endpoint == "http://127.0.0.1:9010"
    assert local.snapshot_s3_uri == "s3://signals-snapshots/sample/workspace"
    monkeypatch.setenv("OPTAGENT_POSTURE", "amp")
    monkeypatch.setenv("OPTAGENT_SAMPLE_MODE", "true")
    monkeypatch.delenv("IMPALA_AUTH", raising=False)
    amp = load_runtime()
    assert amp.sample_mode is True
    assert amp.snapshot_endpoint == ""


def test_traces_s3_uri_is_shared_by_both_postures(monkeypatch) -> None:
    monkeypatch.delenv("OPTAGENT_POSTURE", raising=False)
    monkeypatch.delenv("OPTAGENT_TRACES_S3_URI", raising=False)
    assert load_runtime().traces_s3_uri == ""
    monkeypatch.setenv("OPTAGENT_TRACES_S3_URI", "s3://agent-archive/laptop/raw")
    assert load_runtime().traces_s3_uri == "s3://agent-archive/laptop/raw"


def test_local_posture_ignores_the_cde_flag(monkeypatch) -> None:
    monkeypatch.delenv("OPTAGENT_POSTURE", raising=False)
    monkeypatch.setenv("OPTAGENT_CDE_ENABLED", "true")
    assert load_runtime().cde_enabled is False


def test_dotenv_values_do_not_override_the_process(monkeypatch) -> None:
    parsed = apply_dotenv('IMPALA_HS2_HOST=\'impala.example\'\nIMPALA_AUTH="kerberos"\n')
    assert parsed["IMPALA_HS2_HOST"] == "impala.example"
    assert parsed["IMPALA_AUTH"] == "kerberos"
    monkeypatch.setenv("OPTAGENT_POSTURE", "local")
    monkeypatch.setenv("IMPALA_HS2_HOST", "from-process")
    text = "IMPALA_HS2_HOST='from-file'\n"
    for key, value in apply_dotenv(text).items():
        monkeypatch.setenv(key, value) if key not in {"IMPALA_HS2_HOST"} else None
    runtime = load_runtime()
    assert runtime.impala_host == "from-process"


def test_bootstrap_skips_when_there_is_no_ciphertext() -> None:
    completed = subprocess.run(
        ["bash", str(ROOT / "scripts" / "bootstrap-secrets.sh")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout == ""


def test_amp_registration_skips_the_fdw(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPTAGENT_POSTURE", "amp")
    monkeypatch.delenv("IMPALA_AUTH", raising=False)
    _register().main()
    assert "talks to Impala directly" in capsys.readouterr().out


def test_devenv_does_not_carry_the_amp_impala_profile() -> None:
    nix = (ROOT / "devenv.nix").read_text(encoding="utf-8")
    packages = nix.split("packages = with pkgs;", 1)[1].split("];", 1)[0]
    for name in ("sops", "impyla", "pyspark", "rustfs", "minio"):
        assert name not in packages
    assert "bootstrap-secrets" not in nix
    assert "services.postgres" in nix
