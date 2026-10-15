# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""CML job: build impala_fdw when the toolchain is present, then register it.

A stock PBJ image has neither PostgreSQL headers nor Thrift. This job then
prints that it skipped registration and exits 0, so the AMP still launches.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    """Find the repository root when CML runs this file inside a session.

    A session executes the script in a notebook cell, so __file__ is unset.
    """

    for key in ("CDSW_PROJECT_DIR", "ML_PROJECT_DIR"):
        value = os.environ.get(key)
        if value:
            return Path(value)
    start = Path.cwd()
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    file_name = globals().get("__file__")
    if file_name:
        here = Path(file_name).resolve()
        for candidate in here.parents:
            if (candidate / "pyproject.toml").is_file():
                return candidate
    return start


def can_build(root: Path) -> bool:
    if not (root / "components" / "impala_fdw" / "Makefile").is_file():
        return False
    have_pg = bool(os.environ.get("PG_DEV")) or shutil.which("pg_config") is not None
    have_thrift = bool(os.environ.get("THRIFT_HOME")) or shutil.which("thrift") is not None
    return have_pg and have_thrift


def main() -> None:
    root = project_root()
    sys.path.insert(0, str(root / "src"))
    from optagent.config import load_runtime

    if load_runtime().direct_impala:
        print(
            "AMP posture talks to Impala directly. Skipped FDW registration.",
            flush=True,
        )
        return
    so = root / "components" / "impala_fdw" / "impala_fdw.so"
    if not so.is_file() and not can_build(root):
        print(
            "impala_fdw toolchain is not on this worker. Skipped registration.",
            flush=True,
        )
        return
    env = os.environ.copy()
    if not so.is_file():
        subprocess.check_call(
            ["bash", str(root / "scripts" / "warehouse" / "build_impala_fdw.sh")],
            cwd=root,
            env=env,
        )
    subprocess.check_call(
        ["bash", str(root / "scripts" / "warehouse" / "install_impala_fdw.sh")],
        cwd=root,
        env=env,
    )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
