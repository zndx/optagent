# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Absorb a decrypted AMP baseline without overriding the process environment."""

import shlex
import subprocess
from pathlib import Path


def apply_dotenv(text: str) -> dict[str, str]:
    """Parse dotenv lines written by scripts/bootstrap-secrets.sh."""

    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw = stripped.split("=", 1)
        parsed = shlex.split(raw, posix=True)
        values[key] = parsed[0] if parsed else ""
    return values


def absorb_secrets(root: Path) -> None:
    """Decrypt .env.cai.enc when it exists, then fill unset environment keys.

    Keys already set on the process win. The local shell has no ciphertext,
    so this returns immediately there.
    """

    import os

    enc = root / ".env.cai.enc"
    if not enc.is_file():
        return
    script = root / "scripts" / "bootstrap-secrets.sh"
    subprocess.run(["bash", str(script)], cwd=root, check=False)
    dotenv = root / ".env.cai"
    if not dotenv.is_file():
        return
    for key, value in apply_dotenv(dotenv.read_text(encoding="utf-8")).items():
        os.environ.setdefault(key, value)
