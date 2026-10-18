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

PEERS = frozenset({"gaius", "metabase", "hermes"})
_TRACE = uuid.UUID("6f707461-6765-4e74-8000-000000000001")


def session_id(peer: str, *parts: str) -> str:
    """Return ``peer:local`` and refuse a bare id."""

    name = str(peer).strip()
    if name not in PEERS:
        raise ValueError(f"peer must be gaius, metabase, or hermes, got {name!r}")
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
    input_value: str = "",
    output_value: str = "",
    span_kind: str = "CHAIN",
) -> dict:
    """One span. Filter fields are on the span. The project is also on the resource.

    Phoenix renders ``input.value`` and ``output.value``. A span that only
    carries a name looks empty in the trace view.
    """

    sid = session if session.startswith(f"{project}:") else session_id(project, session)
    start_ns = int(start_time_unix_nano)
    end_ns = int(end_time_unix_nano)
    if start_ns and end_ns < start_ns:
        end_ns = start_ns + 1_000_000_000
    attrs = {
        "session.id": sid,
        "openinference.project.name": project,
        "openinference.span.kind": span_kind,
        "lattice.capability": capability,
        "service.name": service_name,
    }
    if input_value:
        attrs["input.value"] = input_value
        attrs["input.mime_type"] = "text/plain"
    if output_value:
        attrs["output.value"] = output_value
        attrs["output.mime_type"] = "text/plain"
    if project in PEERS:
        attrs[f"{project}.activity"] = activity
    for key, value in (attributes or {}).items():
        if value is None or value == "":
            continue
        attrs[str(key)] = value
    return {
        "trace_id": trace_id_for(project, trace_key),
        "span_id": trace_id_for(project, f"span:{trace_key}")[:16],
        "name": name,
        "start_time_unix_nano": start_ns,
        "end_time_unix_nano": end_ns,
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


def _attribute(key: str, value: object):
    from opentelemetry.proto.common.v1.common_pb2 import KeyValue

    item = KeyValue(key=str(key))
    if isinstance(value, bool):
        item.value.bool_value = value
    elif isinstance(value, int):
        item.value.int_value = value
    else:
        item.value.string_value = str(value)
    return item


def export_requests(spans: list[dict], *, batch: int = 200):
    """OTLP protobuf requests. One resource per peer so Phoenix opens one project."""

    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    grouped: dict[str, list[dict]] = {}
    for span in spans:
        resource = span.get("resource") if isinstance(span.get("resource"), dict) else {}
        project = str(resource.get("openinference.project.name") or "")
        if not project:
            continue
        grouped.setdefault(project, []).append(span)
    requests = []
    for project, group in grouped.items():
        for start in range(0, len(group), batch):
            chunk = group[start : start + batch]
            request = ExportTraceServiceRequest()
            resource_spans = request.resource_spans.add()
            for key, value in chunk[0]["resource"].items():
                resource_spans.resource.attributes.append(_attribute(key, value))
            scope = resource_spans.scope_spans.add()
            scope.scope.name = "optagent"
            for span in chunk:
                encoded = scope.spans.add()
                encoded.trace_id = bytes.fromhex(str(span["trace_id"]))
                encoded.span_id = bytes.fromhex(str(span["span_id"]))
                encoded.name = str(span.get("name") or "span")
                start_ns = int(span.get("start_time_unix_nano") or 0)
                end_ns = int(span.get("end_time_unix_nano") or 0)
                encoded.start_time_unix_nano = start_ns
                encoded.end_time_unix_nano = end_ns if end_ns >= start_ns else start_ns
                encoded.status.code = 1
                attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
                for key, value in attributes.items():
                    encoded.attributes.append(_attribute(key, value))
            requests.append(request)
    return requests


def post_spans(spans: list[dict], endpoint: str = "http://127.0.0.1:9891/v1/traces") -> int:
    """Load span records into a Phoenix OTLP/HTTP endpoint. Returns the span count sent."""

    import urllib.request

    sent = 0
    for request in export_requests(spans):
        count = sum(len(scope.spans) for resource in request.resource_spans for scope in resource.scope_spans)
        body = request.SerializeToString()
        call = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-protobuf"},
        )
        with urllib.request.urlopen(call, timeout=60) as response:
            if response.status != 200:
                raise RuntimeError(f"phoenix {endpoint} returned {response.status}")
        sent += count
    return sent


def activity_points(spans: list[dict]) -> list[dict]:
    """Compact points for the cognition heatmap. Trace bodies stay out of this list."""

    points = []
    for span in spans:
        resource = span.get("resource") if isinstance(span.get("resource"), dict) else {}
        attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
        project = str(resource.get("openinference.project.name") or attributes.get("openinference.project.name") or "")
        if not project:
            continue
        activity = str(
            attributes.get(f"{project}.activity")
            or attributes.get("gaius.activity")
            or attributes.get("metabase.activity")
            or ""
        )
        points.append(
            {
                "t": int(span.get("start_time_unix_nano") or 0) // 1_000_000,
                "project": project,
                "activity": activity,
                "session": str(attributes.get("session.id") or ""),
                "name": str(span.get("name") or "")[:160],
            }
        )
    points.sort(key=lambda item: (item["t"], item["project"], item["session"]))
    return points


def _span_identity(span: dict) -> tuple[str, str, str, dict]:
    resource = span.get("resource") if isinstance(span.get("resource"), dict) else {}
    attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
    project = str(resource.get("openinference.project.name") or attributes.get("openinference.project.name") or "")
    session = str(attributes.get("session.id") or "")
    activity = str(
        attributes.get(f"{project}.activity")
        or attributes.get("gaius.activity")
        or attributes.get("metabase.activity")
        or ""
    )
    return project, session, activity, attributes


def session_catalog(spans: list[dict], projects: list[str] | None = None) -> dict:
    """Session index for the explorer. Trace bodies are not included."""

    found: dict[str, dict] = {}
    for span in spans:
        project, sid, activity, _attributes = _span_identity(span)
        if not project or not sid.startswith(f"{project}:"):
            continue
        stamp = int(span.get("start_time_unix_nano") or 0) // 1_000_000
        row = found.get(sid)
        if row is None:
            found[sid] = {
                "id": sid,
                "project": project,
                "activity": activity,
                "name": str(span.get("name") or "")[:160],
                "t0": stamp,
                "t1": stamp,
                "trace_count": 1,
            }
            continue
        row["trace_count"] += 1
        row["t0"] = min(int(row["t0"]), stamp)
        if stamp >= int(row["t1"]):
            row["t1"] = stamp
            if span.get("name"):
                row["name"] = str(span["name"])[:160]
    names = list(projects or [])
    for row in found.values():
        if row["project"] not in names:
            names.append(row["project"])
    sessions = sorted(found.values(), key=lambda item: (-int(item["t1"]), item["id"]))
    return {"projects": names, "sessions": sessions}


def session_traces(spans: list[dict], session_id: str) -> dict | None:
    """Names and times for one session. No input or output."""

    traces = []
    for span in spans:
        _project, sid, _activity, attributes = _span_identity(span)
        if sid != session_id:
            continue
        traces.append(
            {
                "trace_id": span.get("trace_id"),
                "name": span.get("name") or "",
                "t": int(span.get("start_time_unix_nano") or 0) // 1_000_000,
                "span_kind": str(attributes.get("openinference.span.kind") or ""),
            }
        )
    if not traces:
        return None
    traces.sort(key=lambda item: (-int(item["t"]), str(item["trace_id"])))
    return {"id": session_id, "traces": traces}


def trace_detail(spans: list[dict], trace_id: str) -> dict | None:
    """One trace body. The explorer asks for this after a row is chosen."""

    small_keys = (
        "gaius.thought.type",
        "gaius.thought.id",
        "llm.model_name",
        "llm.token_count.total",
        "metabase.question.id",
        "user.id",
    )
    for span in spans:
        if str(span.get("trace_id") or "") != trace_id:
            continue
        project, sid, activity, attributes = _span_identity(span)
        small = {key: attributes[key] for key in small_keys if attributes.get(key) not in (None, "")}
        return {
            "trace_id": trace_id,
            "name": span.get("name") or "",
            "t": int(span.get("start_time_unix_nano") or 0) // 1_000_000,
            "project": project,
            "session": sid,
            "activity": activity,
            "span_kind": str(attributes.get("openinference.span.kind") or ""),
            "input": attributes.get("input.value") or "",
            "output": attributes.get("output.value") or "",
            "attributes": small,
        }
    return None
