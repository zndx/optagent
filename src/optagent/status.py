# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Status snapshot shared by the prepare job and the application."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_GREETING = "Hello from the Optagent AMP template."
DEFAULT_STATUS_PATH = Path("assets/data/status.json")


def greeting_from_env() -> str:
    return os.environ.get("OPTAGENT_GREETING", DEFAULT_GREETING)


def status_path(root: Path) -> Path:
    raw = os.environ.get("OPTAGENT_STATUS_PATH", str(DEFAULT_STATUS_PATH))
    path = Path(raw)
    if path.is_absolute():
        return path
    return root / path


def write_status(path: Path, greeting: str, version: str) -> Path:
    payload = {
        "name": "Optagent",
        "prototype_version": version,
        "greeting": greeting,
        "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def read_status(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
