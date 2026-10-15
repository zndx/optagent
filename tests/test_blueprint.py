# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Locks the AMP runbook and the devenv shell to the layout CML can launch."""

import re
import tomllib
from pathlib import Path

from optagent import __version__

ROOT = Path(__file__).resolve().parents[1]

ENTRYPOINTS = (
    "0_session-install-dependencies/install-dependencies.py",
    "scripts/warehouse/register_impala_fdw.py",
    "1_job-prepare-project/job.py",
    "2_app-serve/app.py",
)


def _metadata() -> str:
    return (ROOT / ".project-metadata.yaml").read_text(encoding="utf-8")


def _requirement_names(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        body = line.split("#", 1)[0].strip()
        if not body or body.startswith("-"):
            continue
        names.append(re.split(r"[<>=!~\[]", body, maxsplit=1)[0].strip().lower())
    return names


def test_amp_scripts_exist() -> None:
    metadata = _metadata()
    assert "type: run_session" not in metadata
    assert re.search(r"(?m)^[ ]*environment:\s*$", metadata) is None
    jobs = metadata.split("type: create_job")[1:]
    assert len(jobs) == 3
    for job in jobs:
        block = job.split("type: run_job", 1)[0]
        assert "kernel: python3" in block
        assert "arguments: None" not in block
        assert 'arguments: ""' in block
    app = metadata.split("type: start_application", 1)[1]
    assert "kernel: python3" in app
    assert "subdomain: optagent" in app
    scripts = re.findall(r"(?m)^[ ]*script:\s+(\S+)\s*$", metadata)
    assert scripts == list(ENTRYPOINTS)
    for script in scripts:
        source = (ROOT / script).read_text(encoding="utf-8")
        assert "!pip" not in source
        assert "CDSW_PROJECT_DIR" in source
        assert "ML_PROJECT_DIR" in source


def test_runtimes_cover_pbj_and_jupyterlab() -> None:
    metadata = _metadata()
    assert metadata.count("editor: PBJ Workbench") == 2
    assert "editor: JupyterLab" in metadata
    assert "kernel: Python 3.12" in metadata
    assert "kernel: Python 3.13" in metadata
    assert "edition: Standard" in metadata


def test_prototype_version_matches_package() -> None:
    metadata = _metadata()
    match = re.search(r'(?m)^prototype_version:\s*"([^"]+)"\s*$', metadata)
    assert match is not None
    assert match.group(1) == __version__
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)
    assert project["project"]["version"] == __version__


def test_runtime_dependencies_match_the_project() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)
    declared = [
        re.split(r"[<>=!~\[]", dep, maxsplit=1)[0].strip().lower()
        for dep in project["project"]["dependencies"]
    ]
    listed = _requirement_names((ROOT / "requirements.txt").read_text(encoding="utf-8"))
    assert listed == declared


def test_devenv_is_the_local_runtime() -> None:
    nix = (ROOT / "devenv.nix").read_text(encoding="utf-8")
    assert "package = pkgs.python312" in nix
    assert "uv.sync.enable = true" in nix
    assert 'uv.sync.extras = [ "dev" ]' in nix
    assert "processes.prepare" in nix
    assert 'restart.on = "never"' in nix
    assert "processes.app" in nix
    assert 'env.PORT = "9892"' in nix
    assert 'OPTAGENT_BIND = "0.0.0.0"' in nix
    assert 'OPTAGENT_PRIMARY_UI = "http://tinybox.dev.vista.zndx.org:9892"' in nix
    assert "devenv:processes:prepare@completed" in nix
    assert "ready.http.get" in nix
    assert 'path = "/health"' in nix
    assert 'tasks."devenv:enterTest"' in nix
    assert "python -m pytest" in nix
    assert "services.postgres" in nix
    assert "package = pkgs.postgresql_16" in nix
    assert "port = 5599" in nix
    assert 'env.OPTAGENT_ENGINE_PORT = "50851"' in nix
    assert "processes.engine" in nix
    assert 'tasks."impala-fdw:build"' in nix
    assert 'tasks."impala-fdw:install"' in nix
    assert "pkgs.thrift" in nix
    assert "pkgs.boost.dev" in nix
    assert "1_job-prepare-project/job.py" in nix
    assert "2_app-serve/app.py" in nix
    assert not (ROOT / "deploy" / "docker-compose.yml").exists()


def test_catalog_points_at_this_repo() -> None:
    catalog = (ROOT / "catalog-entry.yaml").read_text(encoding="utf-8")
    metadata = (ROOT / "METADATA.yaml").read_text(encoding="utf-8")
    assert 'git_url: "https://github.com/zndx/optagent"' in catalog
    assert 'git_ref: "main"' in catalog
    assert "is_prototype: true" in catalog
    assert 'public_github_link: "https://github.com/zndx/optagent"' in metadata
    assert "Launchable (AMP)" in metadata
    assert "launchable: true" in metadata
