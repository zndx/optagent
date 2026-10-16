# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""OpenInference span records carried by a signals-snapshot.

Phoenix groups by three fields, and OptAgent uses the same three when
Phoenix is not running. The project is ``openinference.project.name``.
A session is every span in that project with the same ``session.id``.
A trace is one span tree. Session ids are prefixed with the peer name
because Phoenix stores ``session.id`` uniquely across the whole database.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

PEERS = frozenset({"gaius", "metabase"})
_TRACE = uuid.UUID("6f707461-6765-4e74-8000-000000000001")


def session_id(peer: str, *parts: str) -> str:
    """Return ``peer:local`` and refuse a bare id."""

    name = str(peer).strip()
    if name not in PEERS:
        raise ValueError(f"peer must be gaius or metabase, got {name!r}")
    local = ":".join(str(part).strip() for part in parts if str(part).strip())
    if not local:
        raise ValueError("session id needs a local part")
    return f"{name}:{local}"


def trace_id_for(peer: str, raw: str) -> str:
    """Stable trace id. The peer is part of the key so bare UUIDs do not collide."""

    return uuid.uuid5(_TRACE, f"{peer}:{raw}").hex


def make_span(
    *,
    project: str,
    session: str,
    name: str,
    activity: str,
    capability: str,
    service_name: str,
    trace_key: str,
    attributes: dict | None = None,
    start_time_unix_nano: int = 0,
    end_time_unix_nano: int = 0,
) -> dict:
    """One span. Filter fields are on the span. The project is also on the resource."""

    sid = session if session.startswith(f"{project}:") else session_id(project, session)
    attrs = {
        "session.id": sid,
        "openinference.project.name": project,
        "lattice.capability": capability,
        "service.name": service_name,
    }
    if project == "gaius":
        attrs["gaius.activity"] = activity
    elif project == "metabase":
        attrs["metabase.activity"] = activity
    for key, value in (attributes or {}).items():
        if value is None or value == "":
            continue
        attrs[str(key)] = value
    return {
        "trace_id": trace_id_for(project, trace_key),
        "span_id": trace_id_for(project, f"span:{trace_key}")[:16],
        "name": name,
        "start_time_unix_nano": int(start_time_unix_nano),
        "end_time_unix_nano": int(end_time_unix_nano),
        "resource": {
            "openinference.project.name": project,
            "service.name": service_name,
        },
        "attributes": attrs,
    }


def write_jsonl(path: Path, spans: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(span, sort_keys=True) for span in spans]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    spans = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            spans.append(loaded)
    return spans


def load_member_spans(root: Path, members: list[dict]) -> list[dict]:
    """Read ``spans`` members. Paths stay inside ``root``."""

    spans: list[dict] = []
    base = root.resolve()
    for member in members:
        if str(member.get("kind") or "") != "spans":
            continue
        relative = str(member.get("metadata-location") or "")
        path = (base / relative).resolve()
        if base != path and base not in path.parents:
            continue
        spans.extend(read_jsonl(path))
    return spans


def index_spans(spans: list[dict]) -> dict:
    """Projects, then sessions, then traces. This is what the Sessions page reads."""

    projects: dict[str, dict] = {}
    for span in spans:
        resource = span.get("resource") if isinstance(span.get("resource"), dict) else {}
        attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
        project = str(resource.get("openinference.project.name") or attributes.get("openinference.project.name") or "")
        sid = str(attributes.get("session.id") or "")
        if not project or not sid.startswith(f"{project}:"):
            continue
        bucket = projects.setdefault(project, {})
        session = bucket.setdefault(
            sid,
            {
                "id": sid,
                "activity": attributes.get(f"{project}.activity") or attributes.get("gaius.activity") or attributes.get("metabase.activity") or "",
                "traces": [],
            },
        )
        session["traces"].append(
            {
                "trace_id": span.get("trace_id"),
                "name": span.get("name"),
                "attributes": attributes,
            }
        )
    listed = []
    for name in sorted(projects):
        sessions = list(projects[name].values())
        sessions.sort(key=lambda item: item["id"])
        listed.append({"name": name, "sessions": sessions})
    return {"projects": listed}
