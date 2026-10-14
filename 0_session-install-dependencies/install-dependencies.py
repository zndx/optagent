# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Install runtime dependencies into the active Python environment.

The prepare job and the application add src/ to the import path, so this
job does not build the project package. Building it inside a Cloudera
session fails the engine. PBJ runtimes fail AMP setup steps that run as
sessions, so .project-metadata.yaml runs this file as a job.
"""

import os
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


def installable_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        body = line.split("#", 1)[0].strip()
        if body:
            lines.append(body)
    return lines


def main() -> None:
    root = project_root()
    requirements = root / "requirements.txt"
    if not requirements.is_file():
        raise SystemExit(f"requirements.txt was not found at {requirements}")
    pending = installable_lines(requirements.read_text(encoding="utf-8"))
    if not pending:
        print("requirements.txt has no runtime dependencies.", flush=True)
        return
    print(f"Python {sys.version}", flush=True)
    print(f"Installing {requirements}", flush=True)
    base = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "-r",
        str(requirements),
    ]
    attempts = (
        base,
        [*base, "--user"],
        [*base, "--break-system-packages"],
    )
    last_error: subprocess.CalledProcessError | None = None
    for command in attempts:
        print("+", " ".join(command), flush=True)
        try:
            subprocess.check_call(command)
        except subprocess.CalledProcessError as exc:
            last_error = exc
            print(f"pip install failed with status {exc.returncode}", flush=True)
            continue
        print("Installed runtime dependencies.", flush=True)
        return
    raise SystemExit("Could not install requirements.txt.") from last_error


if __name__ == "__main__":
    main()
