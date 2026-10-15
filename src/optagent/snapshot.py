# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""signals-snapshot: a root pointer for a federated workspace.

Iceberg keeps table metadata next to the data and only needs an atomic
pointer to the current metadata file. Project Nessie stores that pointer
so a client can plan without a Hive metastore scan. A signals-snapshot
is the same kind of pointer for a whole workspace: Kudu and Iceberg
metadata locations, files, and relational dumps. The document does not
contain those bytes.

Members are an open list. A new deployment adds a project name or a
kind this process has not seen yet. Unknown kinds are kept and marked
unknown. They are not rejected.

Sample mode reads one snapshot so a walkthrough can run before the live
Impala warehouse answers. The bundled document is that sample. An
``s3://`` location records where the same document lives (RustFS locally,
AWS S3 in the AMP). This module does not copy warehouse tables.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = "signals-snapshot"
FORMAT_VERSION = 1
KNOWN_KINDS = frozenset({"iceberg", "kudu", "files", "relational"})

_BUNDLED = Path(__file__).resolve().parents[2] / "assets" / "sample" / "signals-snapshot.json"


@dataclass(frozen=True)
class Member:
    project: str
    kind: str
    name: str
    metadata_location: str
    extra: dict = field(default_factory=dict)

    @property
    def known_kind(self) -> bool:
        return self.kind in KNOWN_KINDS


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    parent_snapshot_id: str | None
    sequence_number: int
    timestamp_ms: int
    summary: dict[str, str]
    members: tuple[Member, ...]
    location: str = ""

    @property
    def projects(self) -> tuple[str, ...]:
        seen: list[str] = []
        for member in self.members:
            if member.project not in seen:
                seen.append(member.project)
        return tuple(seen)


def parse_snapshot(payload: dict, *, location: str = "") -> Snapshot:
    if payload.get("format") != FORMAT:
        raise ValueError("not a signals-snapshot document")
    version = int(payload.get("format-version", 0))
    if version != FORMAT_VERSION:
        raise ValueError(f"unsupported signals-snapshot version {version}")
    snapshot_id = str(payload.get("snapshot-id") or "")
    if not snapshot_id:
        raise ValueError("snapshot-id is required")
    raw_members = payload.get("members") or []
    if not isinstance(raw_members, list):
        raise ValueError("members must be a list")
    members: list[Member] = []
    for item in raw_members:
        if not isinstance(item, dict):
            raise ValueError("each member must be an object")
        project = str(item.get("project") or "")
        kind = str(item.get("kind") or "")
        name = str(item.get("name") or "")
        metadata = str(item.get("metadata-location") or "")
        if not project or not kind or not name:
            raise ValueError("a member needs project, kind, and name")
        extra = {
            key: value
            for key, value in item.items()
            if key not in {"project", "kind", "name", "metadata-location"}
        }
        members.append(
            Member(
                project=project,
                kind=kind,
                name=name,
                metadata_location=metadata,
                extra=extra,
            )
        )
    parent = payload.get("parent-snapshot-id")
    summary = payload.get("summary") or {}
    if not isinstance(summary, dict):
        summary = {}
    return Snapshot(
        snapshot_id=snapshot_id,
        parent_snapshot_id=str(parent) if parent else None,
        sequence_number=int(payload.get("sequence-number") or 0),
        timestamp_ms=int(payload.get("timestamp-ms") or 0),
        summary={str(key): str(value) for key, value in summary.items()},
        members=tuple(members),
        location=location,
    )


def load_bundled() -> Snapshot:
    payload = json.loads(_BUNDLED.read_text(encoding="utf-8"))
    return parse_snapshot(payload, location=str(_BUNDLED))


def resolve_snapshot(location: str) -> Snapshot:
    """Return the snapshot a sample-mode page should describe.

    A filesystem path is read. An ``s3://`` URI is recorded as the
    pointer and the bundled sample supplies the member list until an
    object-storage client is configured. The live warehouse is not opened.
    """

    if location.startswith("s3://") or not location:
        snapshot = load_bundled()
        return Snapshot(
            snapshot_id=snapshot.snapshot_id,
            parent_snapshot_id=snapshot.parent_snapshot_id,
            sequence_number=snapshot.sequence_number,
            timestamp_ms=snapshot.timestamp_ms,
            summary=snapshot.summary,
            members=snapshot.members,
            location=location or snapshot.location,
        )
    path = Path(location)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_snapshot(payload, location=str(path))
