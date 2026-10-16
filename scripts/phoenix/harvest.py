# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Harvest lattice traces into a signals-snapshot version 2 archive.

Read-only. This is a procedure, not a CI gate. Gaius sittings, cognition
thoughts, and flow stages become project ``gaius``. Metabot turns become
project ``metabase``. The archive is what Settings uploads into an AMP.
"""

from __future__ import annotations

import argparse
import json
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from optagent.phoenix_spans import make_span, session_id, write_jsonl
from optagent.snapshot import load_bundled


def _ns(value) -> int:
    if value is None:
        return 0
    if isinstance(value, datetime):
        return int(value.timestamp() * 1_000_000_000)
    return 0


def gaius_spans(database_url: str) -> tuple[list[dict], dict]:
    import psycopg

    spans: list[dict] = []
    watermark = {"table": "cognition_thoughts", "max": ""}
    with psycopg.connect(database_url) as conn:
        try:
            sittings = conn.execute(
                "SELECT id::text, started_at FROM sessions ORDER BY started_at NULLS LAST"
            ).fetchall()
        except Exception:
            conn.rollback()
            sittings = []
        for row in sittings:
            spans.append(
                make_span(
                    project="gaius",
                    session=session_id("gaius", row[0]),
                    name="sitting",
                    activity="engine",
                    capability="cognition",
                    service_name="gaius-engine",
                    trace_key=f"sitting:{row[0]}",
                    start_time_unix_nano=_ns(row[1]),
                )
            )
        thoughts = conn.execute(
            """
            SELECT t.id::text, t.thought_type, t.title, t.summary, t.content,
                   t.generator_model, t.tokens_used, t.created_at, c.id::text
            FROM cognition_thoughts t
            LEFT JOIN cognition_cycles c
              ON t.created_at >= c.started_at
             AND (c.completed_at IS NULL OR t.created_at <= c.completed_at)
            ORDER BY t.created_at
            """
        ).fetchall()
        seen: set[str] = set()
        for row in thoughts:
            thought_id, thought_type, title, summary, content, model, tokens, created, cycle_id = row
            if thought_id in seen:
                continue
            seen.add(thought_id)
            local = ("cognition", cycle_id) if cycle_id else ("cognition", "unassigned")
            prompt = "\n\n".join(part for part in (str(title or ""), str(summary or "")) if part.strip())
            spans.append(
                make_span(
                    project="gaius",
                    session=session_id("gaius", *local),
                    name=str(title or thought_type or "thought"),
                    activity="cognition",
                    capability="cognition",
                    service_name="gaius-engine",
                    trace_key=thought_id,
                    start_time_unix_nano=_ns(created),
                    input_value=prompt or str(thought_type or "thought"),
                    output_value=str(content or summary or ""),
                    span_kind="LLM" if model else "CHAIN",
                    attributes={
                        "gaius.thought.id": thought_id,
                        "gaius.thought.type": thought_type or "",
                        "llm.model_name": model or "",
                        "llm.token_count.total": int(tokens or 0),
                    },
                )
            )
            if created is not None:
                watermark["max"] = created.isoformat()
    return spans, watermark


def _message_text(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(loaded, list):
        parts = []
        for item in loaded:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts) or raw
    if isinstance(loaded, dict):
        return str(loaded.get("text") or loaded.get("content") or raw)
    return str(loaded)


def metabase_spans(database_url: str) -> tuple[list[dict], dict]:
    import psycopg

    spans: list[dict] = []
    watermark = {"table": "metabot_message", "max": ""}
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT m.id::text, c.id::text, c.title, m.user_id::text, m.role,
                   m.total_tokens, m.data::text, m.created_at
            FROM metabot_message m
            JOIN metabot_conversation c ON c.id = m.conversation_id
            WHERE m.deleted_at IS NULL
            ORDER BY m.conversation_id, m.created_at
            """
        ).fetchall()
        previous_user: dict[str, str] = {}
        for message_id, conversation_id, title, user_id, role, tokens, data, created in rows:
            # The application row has a user, not a Metabase session id.
            # A conversation with a user is the interactive visit. A row
            # with no user is an unattended query.
            text = _message_text(data)
            if user_id:
                sid = session_id("metabase", conversation_id)
            else:
                sid = session_id("metabase", "query", conversation_id)
            role_name = str(role or "metabot")
            if role_name == "user":
                previous_user[conversation_id] = text
                incoming, outgoing, kind = text, "", "CHAIN"
            else:
                incoming, outgoing, kind = previous_user.get(conversation_id, title or ""), text, "LLM"
            spans.append(
                make_span(
                    project="metabase",
                    session=sid,
                    name=title or role_name,
                    activity="question",
                    capability="dashboard",
                    service_name="metabase",
                    trace_key=message_id,
                    start_time_unix_nano=_ns(created),
                    input_value=incoming,
                    output_value=outgoing,
                    span_kind=kind,
                    attributes={
                        "metabase.question.id": conversation_id,
                        "user.id": user_id or "",
                        "llm.token_count.total": int(tokens or 0),
                    },
                )
            )
            if created is not None:
                watermark["max"] = created.isoformat()
    return spans, watermark


def build_archive(dest: Path, gaius_url: str, metabase_url: str) -> Path:
    pointer = load_bundled()
    members = [
        {
            "project": member.project,
            "kind": member.kind,
            "name": member.name,
            "metadata-location": member.metadata_location,
        }
        for member in pointer.members
    ]
    summary = dict(pointer.summary)
    by_project: dict[str, list[dict]] = {}
    try:
        gaius, gaius_mark = gaius_spans(gaius_url)
    except Exception as exc:
        gaius, gaius_mark = [], {"table": "cognition_thoughts", "error": str(exc)}
    try:
        metabase, metabase_mark = metabase_spans(metabase_url)
    except Exception as exc:
        metabase, metabase_mark = [], {"table": "metabot_message", "error": str(exc)}
    by_project["gaius"] = gaius
    by_project["metabase"] = metabase
    summary["watermark.gaius"] = json.dumps(gaius_mark)
    summary["watermark.metabase"] = json.dumps(metabase_mark)
    dest.mkdir(parents=True, exist_ok=True)
    for project, spans in by_project.items():
        relative = f"projects/{project}/spans.jsonl"
        write_jsonl(dest / relative, spans)
        members.append(
            {
                "project": project,
                "kind": "spans",
                "name": "sessions",
                "metadata-location": relative,
            }
        )
        summary[f"spans.{project}"] = str(len(spans))
    snapshot_id = str(uuid.uuid4())
    document = {
        "format": "signals-snapshot",
        "format-version": 2,
        "snapshot-id": snapshot_id,
        "parent-snapshot-id": pointer.snapshot_id,
        "sequence-number": pointer.sequence_number + 1,
        "timestamp-ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "summary": summary,
        "members": members,
    }
    (dest / "signals-snapshot.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    archive = dest.with_suffix(".tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        for path in dest.rglob("*"):
            if path.is_file():
                tar.add(path, arcname=str(path.relative_to(dest)))
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description="Harvest lattice traces into a signals-snapshot archive.")
    parser.add_argument("--out", default="/raid/build/optagent/signals-snapshot")
    parser.add_argument("--gaius-url", default="postgresql://127.0.0.1:5444/zndx_gaius")
    parser.add_argument("--metabase-url", default="postgresql://127.0.0.1:5432/metabase")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = Path(args.out) / stamp
    archive = build_archive(dest, args.gaius_url, args.metabase_url)
    print(archive)


if __name__ == "__main__":
    main()
