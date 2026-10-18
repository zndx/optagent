# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Installed signals-snapshot archive.

An upload is one gzip tar. The root holds ``signals-snapshot.json`` and the
span files named by ``spans`` members. The installed copy wins over the
HOCON pointer for Sessions and Summary.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
from pathlib import Path

from optagent.snapshot import FORMAT, parse_snapshot

_MAX_BYTES = 256 * 1024 * 1024


def state_dir() -> Path:
    """Where an uploaded archive is kept.

    Local devenv sets OPTAGENT_SESSION_DIR. An AMP does not, so the file
    lands under the project directory and survives an application restart.
    """

    configured = os.environ.get("OPTAGENT_SESSION_DIR", "").strip()
    if configured:
        root = Path(configured)
    else:
        base = os.environ.get("CDSW_PROJECT_DIR") or os.environ.get("ML_PROJECT_DIR") or ""
        root = Path(base) / ".devenv" / "state" if base else Path(".devenv/state")
    root.mkdir(parents=True, exist_ok=True)
    return root


def store_root() -> Path:
    root = state_dir() / "signals-snapshot"
    root.mkdir(parents=True, exist_ok=True)
    return root


def installed_document() -> dict | None:
    """The installed snapshot document, or None when nothing has been uploaded."""

    path = store_root() / "signals-snapshot.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        return None
    payload["location"] = str(path)
    return payload


def install_archive(blob: bytes) -> dict:
    """Replace the installed snapshot. Rejects anything that is not signals-snapshot."""

    if len(blob) > _MAX_BYTES:
        raise ValueError("snapshot archive is too large")
    try:
        tar = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
    except tarfile.TarError as exc:
        raise ValueError("snapshot upload must be a gzip tar") from exc
    staging = store_root().parent / "signals-snapshot.incoming"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        _extract(tar, staging)
        document_path = staging / "signals-snapshot.json"
        if not document_path.is_file():
            raise ValueError("signals-snapshot.json is missing")
        payload = json.loads(document_path.read_text(encoding="utf-8"))
        snapshot = parse_snapshot(payload)
        for member in snapshot.members:
            if member.kind != "spans":
                continue
            span_path = (staging / member.metadata_location).resolve()
            if staging.resolve() not in span_path.parents or not span_path.is_file():
                raise ValueError(f"spans member {member.metadata_location} is missing")
        dest = store_root()
        if dest.exists():
            previous = dest / "signals-snapshot.json"
            if previous.is_file():
                try:
                    old = json.loads(previous.read_text(encoding="utf-8"))
                    old_id = str(old.get("snapshot-id") or "previous")
                except json.JSONDecodeError:
                    old_id = "previous"
                archive = dest.parent / "archive" / old_id
                if archive.exists():
                    shutil.rmtree(archive)
                archive.parent.mkdir(parents=True, exist_ok=True)
                dest.rename(archive)
            else:
                shutil.rmtree(dest)
        staging.rename(dest)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        tar.close()
    installed = installed_document()
    if installed is None:
        raise ValueError("installed snapshot is unreadable")
    return installed


def _extract(tar: tarfile.TarFile, dest: Path) -> None:
    root = dest.resolve()
    for member in tar.getmembers():
        if member.issym() or member.islnk():
            raise ValueError("snapshot archive must not contain links")
        target = (root / member.name).resolve()
        if root != target and root not in target.parents:
            raise ValueError("snapshot archive path escapes the archive")
        try:
            tar.extract(member, root, filter="data")
        except TypeError:
            tar.extract(member, root)
