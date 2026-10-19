# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Write the status snapshot the application serves."""

import os
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


ROOT = project_root()
sys.path.insert(0, str(ROOT / "src"))

from optagent import __version__
from optagent.status import greeting_from_env, status_path, write_status
from optagent.warehouse import probe_warehouse


def main() -> None:
    from optagent.lineup import ensure_corpora_checkout

    ensure_corpora_checkout(ROOT)
    path = write_status(
        status_path(ROOT),
        greeting_from_env(),
        __version__,
        warehouse=probe_warehouse(),
    )
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
