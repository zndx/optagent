# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Harvest lattice traces into a signals-snapshot version 2 archive.

Read-only. This is a procedure, not a CI gate. Project ``gaius`` holds
cognition thoughts, agent-written briefs, and the HX Iceberg exchanges
(``llm.generations`` and ``hx.cot_reasoning``). Metabot turns become
project ``metabase``. Hermes SessionDB, including reasoning and ``viz_show``
chart kinds, becomes project ``hermes``. Semantica ``decision`` nodes become
project ``semantica``. Rows that already point at an HX generation are not
copied again.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import tarfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from optagent.phoenix_spans import make_span, session_id, trace_id_for, write_jsonl
from optagent.snapshot import load_bundled


_PREPRINT = re.compile(r"arxiv|biorxiv|medrxiv|wiki:", re.IGNORECASE)
_ARXIV = re.compile(r"(\d{4}\.\d{4,5})", re.IGNORECASE)
_TEXT_CAP = 32_000
# Semantica record_decision limits. The full turn stays in input.value and
# output.value. These clips are the fields a later record_decision accepts.
_SCENARIO_CAP = 5_000
_REASONING_CAP = 10_000
_OUTCOME_CAP = 1_000


def _viz_kind(content: str, tool_name: str) -> str:
    """Chart kind stored on a ``viz_show`` tool result. Empty when this row is not one."""

    if str(tool_name or "") != "viz_show":
        return ""
    try:
        payload = json.loads(content or "")
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    kind = str(payload.get("kind") or "").strip()
    return kind[:40]


def _clip(text: str) -> str:
    body = (text or "").strip()
    if len(body) <= _TEXT_CAP:
        return body
    return body[: _TEXT_CAP - 1].rstrip() + "…"


def _unix_ns(value) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, datetime):
        return _ns(value)
    if isinstance(value, str) and "T" in value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0
        return _ns(parsed)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    # updated_ns from Semantica is already nanoseconds. Hermes timestamps are unix seconds.
    if number > 10_000_000_000_000:
        return int(number)
    return int(number * 1_000_000_000)


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
            SELECT m.id::text, c.id::text, c.summary, c.user_id::text, m.role,
                   m.total_tokens, m.data::text, m.created_at
            FROM metabot_message m
            JOIN metabot_conversation c ON c.id = m.conversation_id
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


def _assignment_iri(item: dict) -> str:
    return str(item.get("iri") or item.get("sdg.iri") or "").strip()


def _assignment_confidence(item: dict):
    if "confidence" in item and item.get("confidence") is not None:
        return item.get("confidence")
    return item.get("semantica.confidence")


def _join_entities(prior: str, iris: list[str]) -> str:
    seen: list[str] = []
    for part in (prior or "").split(","):
        part = part.strip()
        if part and part not in seen:
            seen.append(part)
    for iri in iris:
        if iri and iri not in seen:
            seen.append(iri)
    return ",".join(seen)


def _spans_from_link(link: dict) -> list[dict]:
    """Every system-one assignment. A declined genus (no child IRI) adds nothing."""

    assignments = link.get("assignments")
    spans: list[dict] = []
    if isinstance(assignments, list) and assignments:
        for item in assignments:
            if not isinstance(item, dict):
                continue
            iri = _assignment_iri(item)
            if not iri:
                continue
            span = {
                "start": int(item.get("start") or 0),
                "end": int(item.get("end") or 0),
                "text": str(item.get("text") or ""),
                "iri": iri,
                "label": str(item.get("label") or ""),
            }
            confidence = _assignment_confidence(item)
            if confidence is not None:
                span["confidence"] = confidence
            spans.append(span)
        return spans
    iri = str(link.get("sdg.iri") or "").strip()
    if not iri:
        return []
    span = {
        "start": int(link.get("start") or 0),
        "end": int(link.get("end") or 0),
        "text": str(link.get("text") or ""),
        "iri": iri,
        "label": str(link.get("genus_label") or ""),
    }
    confidence = link.get("semantica.confidence")
    if confidence is not None:
        span["confidence"] = confidence
    return [span]


def _stamp_sdg(attributes: dict, raw: str | None) -> None:
    """Copy every grounded span. The first genus link still fills aegir.*."""

    if not raw:
        return
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return
    links = loaded.get("links") if isinstance(loaded, dict) else None
    if not isinstance(links, list) or not links:
        return
    genus = next((item for item in links if isinstance(item, dict) and item.get("genus_iri")), None)
    if genus is not None:
        attributes["aegir.genus_iri"] = str(genus.get("genus_iri") or "")
        attributes["aegir.genus_code"] = str(genus.get("genus_code") or "")
        attributes["aegir.start"] = int(genus.get("start") or 0)
        attributes["aegir.end"] = int(genus.get("end") or 0)
        if genus.get("rel_margin_h") is not None:
            attributes["aegir.rel_margin_h"] = genus.get("rel_margin_h")
        if genus.get("tau") is not None:
            attributes["aegir.tau"] = genus.get("tau")
    grounded: list[dict] = []
    for link in links:
        if isinstance(link, dict):
            grounded.extend(_spans_from_link(link))
    if not grounded:
        return
    attributes["sdg.spans"] = grounded
    attributes["semantica.entities"] = _join_entities(
        str(attributes.get("semantica.entities") or ""),
        [str(item["iri"]) for item in grounded],
    )
    first = grounded[0].get("confidence")
    if first is not None:
        attributes["semantica.confidence"] = first


def hermes_spans(db_path: str) -> tuple[list[dict], dict]:
    """Local Hermes SessionDB. AgentRTC turns and the other Hermes sources.

    Mistral's hosted observability is not available. The trace is the
    message row: content, reasoning, and the unix timestamp Hermes stored.
    """

    path = Path(db_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    spans: list[dict] = []
    watermark = {"table": "messages", "max": ""}
    uri = f"file:{path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        sessions = conn.execute(
            """
            SELECT id, source, model, title, started_at
            FROM sessions
            WHERE coalesce(hidden, 0) = 0
            ORDER BY started_at
            """
        ).fetchall()
        previous: dict[str, str] = {}
        previous_decision: dict[str, str] = {}
        latest = 0.0
        for session in sessions:
            raw_id = str(session["id"])
            source = str(session["source"] or "hermes")
            local = raw_id[len("agent-rtc-") :] if source == "agent-rtc" and raw_id.startswith("agent-rtc-") else raw_id
            sid = session_id("hermes", source, local)
            title = str(session["title"] or "").strip()
            model = str(session["model"] or "")
            columns = {row[1] for row in conn.execute("pragma table_info(messages)")}
            tool_column = ", tool_name" if "tool_name" in columns else ""
            rows = conn.execute(
                f"""
                SELECT id, role, content, reasoning, timestamp, token_count, display_metadata{tool_column}
                FROM messages
                WHERE session_id = ? AND coalesce(active, 1) = 1
                  AND role IN ('user', 'assistant', 'tool')
                ORDER BY timestamp, id
                """,
                (raw_id,),
            ).fetchall()
            for message in rows:
                role = str(message["role"] or "")
                content = _clip(str(message["content"] or ""))
                reasoning = _clip(str(message["reasoning"] or ""))
                stamp = message["timestamp"]
                if stamp and float(stamp) > latest:
                    latest = float(stamp)
                preprint = bool(_PREPRINT.search(title) or _PREPRINT.search(content))
                activity = "preprint" if preprint else source
                if role == "user":
                    previous[raw_id] = content
                    incoming, outgoing, kind = content, "", "CHAIN"
                elif role == "assistant":
                    incoming = previous.get(raw_id) or title
                    outgoing = content
                    if reasoning:
                        outgoing = (outgoing + "\n\n## Reasoning\n\n" + reasoning).strip()
                    kind = "LLM"
                else:
                    incoming, outgoing, kind = title or role, content, "TOOL"
                name = title or (content.splitlines()[0][:120] if content else role)
                trace_key = f"{raw_id}:{message['id']}"
                attributes = {
                    "hermes.session": raw_id,
                    "hermes.source": source,
                    "llm.model_name": model,
                    "llm.token_count.total": int(message["token_count"] or 0),
                }
                viz_kind = _viz_kind(message["content"] if role == "tool" else "", message["tool_name"] if "tool_name" in message.keys() else "")
                if viz_kind:
                    attributes["hermes.viz.kind"] = viz_kind
                    name = f"viz:{viz_kind}"
                if role == "assistant":
                    # Shape Semantica can record later. Confidence is omitted:
                    # Hermes does not store one, and a default would be invented.
                    decision_id = trace_id_for("hermes", trace_key)
                    entities = []
                    for token in _ARXIV.findall(f"{title}\n{incoming}\n{content}"):
                        if token not in entities:
                            entities.append(token)
                    attributes.update(
                        {
                            "semantica.category": ("preprint" if preprint else source)[:100],
                            "semantica.scenario": _clip(incoming)[:_SCENARIO_CAP],
                            "semantica.reasoning": reasoning[:_REASONING_CAP],
                            "semantica.outcome": _clip(content)[:_OUTCOME_CAP],
                            "semantica.decision_maker": (model or source)[:200],
                            "semantica.caller_project": "hermes",
                            "semantica.caller_agent": source[:200],
                            "semantica.run_id": raw_id,
                            "semantica.tx_id": str(message["id"]),
                            "semantica.caused_by": previous_decision.get(raw_id, ""),
                            "semantica.relationship": "CAUSED" if previous_decision.get(raw_id) else "",
                            "semantica.entities": ",".join(entities[:8]),
                        }
                    )
                    previous_decision[raw_id] = decision_id
                    _stamp_sdg(attributes, message["display_metadata"] if "display_metadata" in message.keys() else None)
                spans.append(
                    make_span(
                        project="hermes",
                        session=sid,
                        name=name[:160],
                        activity=activity,
                        capability="preprint" if preprint else "conversation",
                        service_name="hermes" if source != "agent-rtc" else "agent-rtc",
                        trace_key=trace_key,
                        start_time_unix_nano=_unix_ns(stamp or session["started_at"]),
                        input_value=incoming,
                        output_value=outgoing,
                        span_kind=kind,
                        attributes=attributes,
                    )
                )
        if latest:
            watermark["max"] = datetime.fromtimestamp(latest, timezone.utc).isoformat()
    return spans, watermark


def _recorded_total(*parts: object) -> int:
    """Sum token counts a producer stored. A missing count stays out of the sum."""

    total = 0
    seen = False
    for part in parts:
        if part is None or isinstance(part, bool):
            continue
        try:
            total += int(part)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        seen = True
    return total if seen else 0


def _positive_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _pair(primary: str, extra: str, title: str) -> str:
    body = _clip(primary)
    note = (extra or "").strip()
    if not note:
        return body
    note = note[:16_000]
    return _clip(f"{body}\n\n## {title}\n\n{note}" if body else f"## {title}\n\n{note}")


def gaius_kb_spans(database_url: str) -> tuple[list[dict], dict]:
    """Agent-written briefs. These notes are not rows in an HX table."""

    import psycopg

    spans: list[dict] = []
    watermark = {"table": "cognition_briefs+agenda_briefs", "max": ""}
    statements = (
        (
            "cognition-brief",
            """
            SELECT id::text, created_at, title, body, spoken, model, tokens_used,
                   generation_context::text, note_path
            FROM cognition_briefs
            ORDER BY created_at
            """,
        ),
        (
            "agenda-brief",
            """
            SELECT id::text, created_at, title, body, spoken, model, tokens_used,
                   generation_context::text, note_path
            FROM agenda_briefs
            ORDER BY created_at
            """,
        ),
    )
    with psycopg.connect(database_url) as conn:
        for activity, sql in statements:
            for row in conn.execute(sql).fetchall():
                brief_id, created, title, body, spoken, model, tokens, context, note_path = row
                text = "\n\n".join(part for part in (str(body or ""), str(spoken or "")) if str(part).strip())
                spans.append(
                    make_span(
                        project="gaius",
                        session=session_id("gaius", "kb", activity),
                        name=str(title or note_path or activity)[:160],
                        activity=activity,
                        capability="kb",
                        service_name="gaius-kb",
                        trace_key=f"{activity}:{brief_id}",
                        start_time_unix_nano=_ns(created),
                        input_value=_clip(str(context or "")),
                        output_value=_clip(text),
                        span_kind="LLM" if model else "CHAIN",
                        attributes={
                            "llm.model_name": str(model or ""),
                            "llm.token_count.total": int(tokens or 0),
                            "gaius.note_path": str(note_path or ""),
                        },
                    )
                )
                if created is not None:
                    watermark["max"] = created.isoformat()
    return spans, watermark


def generation_span(row: dict) -> dict:
    """One ``llm.generations`` exchange, including its thinking trace when stored."""

    summary_type = str(row.get("summary_type") or "generation")
    thinking = str(row.get("thinking_trace") or "")
    output = _pair(str(row.get("output") or ""), thinking, "Thinking")
    attributes = {
        "llm.model_name": str(row.get("model_name") or ""),
        "llm.token_count.total": _recorded_total(row.get("input_tokens"), row.get("output_tokens")),
        "gaius.hx.summary_type": summary_type,
    }
    if thinking.strip():
        attributes["gaius.hx.thinking"] = "true"
    latency = _positive_int(row.get("latency_ms"))
    if latency:
        attributes["latency_ms"] = latency
    return make_span(
        project="gaius",
        session=session_id("gaius", "hx", summary_type),
        name=summary_type[:160],
        activity="hx-generation",
        capability="hx",
        service_name="gaius-hx",
        trace_key=f"generation:{row.get('id')}",
        start_time_unix_nano=_unix_ns(row.get("generated_at")),
        input_value=_clip(str(row.get("prompt") or "")),
        output_value=output,
        span_kind="LLM",
        attributes=attributes,
    )


def cot_span(row: dict) -> dict:
    """One optillm reasoning row from ``hx.cot_reasoning``."""

    technique = str(row.get("technique") or "cot_reflection")
    attributes = {
        "llm.model_name": str(row.get("model_name") or ""),
        "llm.token_count.total": _recorded_total(row.get("input_tokens"), row.get("output_tokens")),
        "gaius.hx.technique": technique,
        "gaius.hx.queue": str(row.get("yk_queue") or ""),
        "gaius.hx.flow": str(row.get("flow_name") or ""),
    }
    latency = _positive_int(row.get("latency_ms"))
    if latency:
        attributes["latency_ms"] = latency
    return make_span(
        project="gaius",
        session=session_id("gaius", "hx", technique),
        name=technique[:160],
        activity="cot-reasoning",
        capability="hx",
        service_name="gaius-hx",
        trace_key=f"cot:{row.get('id')}",
        start_time_unix_nano=_unix_ns(row.get("generated_at")),
        input_value=_clip(str(row.get("prompt") or "")),
        output_value=_pair(str(row.get("reasoning_trace") or ""), str(row.get("output") or ""), "Decision"),
        span_kind="LLM",
        attributes=attributes,
    )


def hx_records(python: str, script: str, dest: Path, cwd: str) -> tuple[list[dict], dict]:
    """Read HX Iceberg rows through the Gaius interpreter. Empty when that tree is absent."""

    watermark: dict = {"table": "llm.generations+hx.cot_reasoning"}
    if not python or not Path(python).is_file():
        watermark["skipped"] = "gaius python is not on this host"
        return [], watermark
    dest.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [python, script, str(dest)],
        cwd=cwd or None,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        watermark["error"] = (completed.stderr or completed.stdout or "hx export failed")[-500:]
        return [], watermark
    spans: list[dict] = []
    if dest.is_file():
        for line in dest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            kind = str(row.get("kind") or "")
            if kind == "generation":
                spans.append(generation_span(row))
            elif kind == "cot":
                spans.append(cot_span(row))
    watermark["rows"] = len(spans)
    return spans, watermark


def semantica_decision_spans(database_url: str) -> tuple[list[dict], dict]:
    """Durable Semantica decision nodes. Ontology classes in the same view are not traces."""

    import psycopg

    spans: list[dict] = []
    watermark = {"table": "warehouse.v_node", "node_type": "decision", "max": ""}
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT node_id, properties, updated_ns
            FROM warehouse.v_node
            WHERE node_type = 'decision'
            """
        ).fetchall()
    for node_id, properties, updated_ns in rows:
        try:
            payload = json.loads(properties or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        stamp = payload.get("recorded_at") or payload.get("timestamp") or updated_ns
        attributes = {
            "semantica.category": str(payload.get("category") or "")[:100],
            "semantica.scenario": _clip(str(payload.get("scenario") or payload.get("content") or ""))[:_SCENARIO_CAP],
            "semantica.reasoning": _clip(str(payload.get("reasoning") or ""))[:_REASONING_CAP],
            "semantica.outcome": _clip(str(payload.get("outcome") or ""))[:_OUTCOME_CAP],
            "semantica.decision_maker": str(payload.get("decision_maker") or "")[:200],
            "semantica.caller_project": str(payload.get("caller_project") or "")[:200],
            "semantica.caller_agent": str(payload.get("caller_agent") or "")[:200],
            "semantica.run_id": str(payload.get("run_id") or ""),
            "semantica.tx_id": str(payload.get("tx_id") or node_id or ""),
        }
        confidence = payload.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            attributes["semantica.confidence"] = confidence
        spans.append(
            make_span(
                project="semantica",
                session=session_id("semantica", "decision", str(payload.get("caller_project") or "semantica")),
                name=str(payload.get("category") or "decision")[:160],
                activity="decision",
                capability="decisions",
                service_name="semantica",
                trace_key=f"decision:{node_id}",
                start_time_unix_nano=_unix_ns(stamp),
                input_value=attributes["semantica.scenario"],
                output_value=_clip(str(payload.get("outcome") or payload.get("reasoning") or "")),
                span_kind="CHAIN",
                attributes=attributes,
            )
        )
    return spans, watermark


def build_archive(
    dest: Path,
    gaius_url: str,
    metabase_url: str,
    hermes_db: str,
    semantica_url: str = "",
    hx_python: str = "",
    hx_cwd: str = "",
) -> Path:
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
    try:
        hermes, hermes_mark = hermes_spans(hermes_db)
    except Exception as exc:
        hermes, hermes_mark = [], {"table": "messages", "error": str(exc)}
    try:
        briefs, brief_mark = gaius_kb_spans(gaius_url)
    except Exception as exc:
        briefs, brief_mark = [], {"table": "briefs", "error": str(exc)}
    gaius.extend(briefs)
    script = str(Path(__file__).with_name("export_hx.py"))
    hx_path = dest.parent / f".{dest.name}.hx.jsonl"
    hx, hx_mark = hx_records(hx_python, script, hx_path, hx_cwd)
    hx_path.unlink(missing_ok=True)
    gaius.extend(hx)
    try:
        decisions, decision_mark = semantica_decision_spans(semantica_url) if semantica_url else ([], {"table": "warehouse.v_node", "skipped": "no url"})
    except Exception as exc:
        decisions, decision_mark = [], {"table": "warehouse.v_node", "error": str(exc)}
    by_project["gaius"] = gaius
    by_project["metabase"] = metabase
    by_project["hermes"] = hermes
    by_project["semantica"] = decisions
    summary["watermark.gaius"] = json.dumps(gaius_mark)
    summary["watermark.gaius.kb"] = json.dumps(brief_mark)
    summary["watermark.gaius.hx"] = json.dumps(hx_mark)
    summary["watermark.metabase"] = json.dumps(metabase_mark)
    summary["watermark.hermes"] = json.dumps(hermes_mark)
    summary["watermark.semantica"] = json.dumps(decision_mark)
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


def argument_parser() -> argparse.ArgumentParser:
    """Peer checkouts are optional. Empty HX and Semantica settings skip those sources."""

    parser = argparse.ArgumentParser(description="Harvest lattice traces into a signals-snapshot archive.")
    parser.add_argument("--out", default=os.environ.get("OPTAGENT_HARVEST_OUT", "build/signals-snapshot"))
    parser.add_argument("--gaius-url", default=os.environ.get("OPTAGENT_GAIUS_URL", "postgresql://127.0.0.1:5444/zndx_gaius"))
    parser.add_argument("--metabase-url", default=os.environ.get("OPTAGENT_METABASE_URL", "postgresql://127.0.0.1:5432/metabase"))
    parser.add_argument("--hermes-db", default=os.environ.get("OPTAGENT_HERMES_DB", "~/.hermes/state.db"))
    parser.add_argument("--semantica-url", default=os.environ.get("SEMANTICA_DATABASE_URL", ""))
    parser.add_argument("--hx-python", default=os.environ.get("OPTAGENT_GAIUS_PYTHON", ""))
    parser.add_argument("--hx-cwd", default=os.environ.get("OPTAGENT_GAIUS_ROOT", ""))
    return parser


def main() -> None:
    args = argument_parser().parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = Path(args.out) / stamp
    archive = build_archive(
        dest,
        args.gaius_url,
        args.metabase_url,
        args.hermes_db,
        semantica_url=args.semantica_url,
        hx_python=args.hx_python,
        hx_cwd=args.hx_cwd,
    )
    print(archive)


if __name__ == "__main__":
    main()
