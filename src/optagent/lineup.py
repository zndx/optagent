# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Summary lineup: published SDG panels plus tracing from a snapshot.

Lexicon and schema come from the sdg-corpora release Aegir pins. Traces do
not create concepts. Scratch is always listed. An AMP has no live stream.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from optagent.phoenix_spans import rich_segments

SDG_PIN = "b24ef9f606605dd7bb8877bddd2d9672c78282ad"
SDG_IRI = "https://signals.zndx.org/sdg#"
_WINDOWS = {
    "24h": 86_400_000,
    "7d": 7 * 86_400_000,
    "30d": 30 * 86_400_000,
    "90d": 90 * 86_400_000,
    "365d": 365 * 86_400_000,
}
_CONCEPT = re.compile(
    r"<(https://signals\.zndx\.org/sdg#[^>]+)>\s+a\s+skos:Concept\s*;(?P<body>.*?)(?=\n<https://|\Z)",
    re.S,
)
_NOTE = re.compile(r'skos:notation\s+"([^"]+)"')
_LABEL = re.compile(r'skos:prefLabel\s+"([^"]+)"')
_DEFN = re.compile(r'skos:definition\s+"([^"]+)"')
_TABLE = re.compile(r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?([A-Za-z0-9_\.]+)", re.I)
_BROADER = re.compile(r"skos:broader\s+<(https://signals\.zndx\.org/sdg#[^>]+)>")
_FK = re.compile(
    r"ALTER TABLE\s+([A-Za-z0-9_\.]+)\s+ADD\s+FOREIGN KEY\s*\([^)]*\)\s+REFERENCES\s+([A-Za-z0-9_\.]+)",
    re.I,
)
_COLUMN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+[A-Za-z]")
_SKIP_COLUMN = {"PRIMARY", "FOREIGN", "CONSTRAINT", "UNIQUE", "CHECK"}
_WORD = re.compile(r"\S+")
_LEXICON_CACHE: dict[tuple, list[dict]] = {}
_SCHEMA_CACHE: dict[tuple, list[dict]] = {}


def checkout_sha(root: Path | None) -> str:
    if root is None:
        return ""
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def corpora_root() -> Path | None:
    configured = os.environ.get("OPTAGENT_SDG_CORPORA", "").strip()
    if configured and Path(configured).is_dir():
        return Path(configured)
    sibling = Path("/home/rch/local/src/zndx/aegir/corpora")
    if sibling.is_dir():
        return sibling
    return None


def _file_stamp(paths: list[Path]) -> tuple:
    stamped = []
    for path in paths:
        stamped.append((str(path), path.stat().st_mtime_ns if path.is_file() else 0))
    return tuple(stamped)


def load_lexicon(root: Path | None) -> list[dict]:
    """Published SKOS concepts. ``broader`` is the skos:broader link, not a class axiom."""

    if root is None:
        return []
    paths = [root / "vocabulary" / "vocabulary.ttl", root / "vocabulary" / "domain-concepts.ttl"]
    key = _file_stamp(paths)
    cached = _LEXICON_CACHE.get(key)
    if cached is not None:
        return cached
    concepts: dict[str, dict] = {}
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _CONCEPT.finditer(text):
            iri = match.group(1)
            body = match.group("body")
            broader: list[str] = []
            for parent in _BROADER.findall(body):
                if parent not in broader:
                    broader.append(parent)
            concepts[iri] = {
                "iri": iri,
                "code": (_NOTE.search(body).group(1) if _NOTE.search(body) else ""),
                "label": (_LABEL.search(body).group(1) if _LABEL.search(body) else iri.rsplit("#", 1)[-1]),
                "definition": (_DEFN.search(body).group(1) if _DEFN.search(body) else ""),
                "broader": broader,
            }
    children: dict[str, list[str]] = {}
    for item in concepts.values():
        for parent in item["broader"]:
            kids = children.setdefault(parent, [])
            if item["iri"] not in kids:
                kids.append(item["iri"])
    for item in concepts.values():
        item["narrower"] = sorted(children.get(item["iri"], []))
    loaded = [concepts[iri] for iri in sorted(concepts)]
    _LEXICON_CACHE[key] = loaded
    return loaded


def _table_shape(text: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    columns: dict[str, list[str]] = {}
    name = ""
    depth = 0
    for line in text.splitlines():
        if line.lstrip().startswith("--"):
            continue
        if depth == 0:
            match = _TABLE.search(line)
            if match and "(" in line:
                name = match.group(1)
                columns.setdefault(name, [])
                depth = line.count("(") - line.count(")")
            continue
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            name = ""
            depth = 0
            continue
        column = _COLUMN.match(line)
        if column and column.group(1).upper() not in _SKIP_COLUMN:
            columns[name].append(column.group(1))
    refs: dict[str, list[str]] = {}
    for match in _FK.finditer(text):
        source, target = match.group(1), match.group(2)
        bucket = refs.setdefault(source, [])
        if target not in bucket:
            bucket.append(target)
    return columns, refs


def load_schema(root: Path | None) -> list[dict]:
    if root is None:
        return []
    paths = sorted((root / "ddl").rglob("ddl.sql")) + sorted((root / "ddl-comprehensive").rglob("ddl.sql"))
    key = _file_stamp(paths)
    cached = _SCHEMA_CACHE.get(key)
    if cached is not None:
        return cached
    tables: list[dict] = []
    seen: set[str] = set()
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        columns, refs = _table_shape(text)
        for match in _TABLE.finditer(text):
            name = match.group(1)
            if name in seen:
                continue
            seen.add(name)
            tables.append(
                {
                    "name": name,
                    "location": str(path.relative_to(root)),
                    "columns": columns.get(name, []),
                    "refs": refs.get(name, []),
                }
            )
    _SCHEMA_CACHE[key] = tables
    return tables


def token_count(span: dict) -> int:
    """Use a stored total when the workflow recorded one. Otherwise count the text we hold."""

    attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
    stored = attributes.get("llm.token_count.total")
    if isinstance(stored, int) and stored > 0:
        return stored
    if isinstance(stored, str) and stored.isdigit() and int(stored) > 0:
        return int(stored)
    text = f"{attributes.get('input.value') or ''} {attributes.get('output.value') or ''}"
    return len(_WORD.findall(text))


def _generated_ms(span: dict) -> int:
    return int(span.get("start_time_unix_nano") or 0) // 1_000_000


def _augmented_ms(span: dict) -> int | None:
    attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
    for key in ("sdg.augmented_at", "semantica.augmented_at"):
        value = attributes.get(key)
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _metric(span: dict, key: str):
    attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
    value = attributes.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def tracing_report(spans: list[dict], *, now_ms: int, window: str = "365d") -> dict:
    """LangSmith-style project dashboard from spans we actually stored."""

    start = 0 if window == "all" else now_ms - _WINDOWS.get(window, _WINDOWS["365d"])
    chosen = [span for span in spans if start <= _generated_ms(span) <= now_ms]
    by_project: dict[str, list[dict]] = {}
    for span in chosen:
        resource = span.get("resource") if isinstance(span.get("resource"), dict) else {}
        project = str(resource.get("openinference.project.name") or "unknown")
        by_project.setdefault(project, []).append(span)
    projects = []
    for name in sorted(by_project):
        rows = by_project[name]
        sessions = set()
        tokens = 0
        grounded = 0
        days: dict[str, int] = {}
        genera: dict[str, int] = {}
        leaves: dict[str, int] = {}
        latency = []
        cost = []
        errors = 0
        error_known = False
        augmented = 0
        for span in rows:
            attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
            sid = str(attributes.get("session.id") or "")
            if sid:
                sessions.add(sid)
            tokens += token_count(span)
            generated = _generated_ms(span)
            if generated:
                day = generated // 86_400_000
                days[str(day)] = days.get(str(day), 0) + 1
            if _augmented_ms(span) is not None:
                augmented += 1
            genus = str(attributes.get("aegir.genus_code") or "")
            if genus:
                genera[genus] = genera.get(genus, 0) + 1
            for item in attributes.get("sdg.spans") or []:
                if isinstance(item, dict) and item.get("iri"):
                    grounded += 1
                    iri = str(item["iri"])
                    leaves[iri] = leaves.get(iri, 0) + 1
            lat = _metric(span, "latency_ms")
            if lat is not None:
                latency.append(float(lat))
            spent = _metric(span, "total_cost")
            if spent is not None:
                cost.append(float(spent))
            if "error" in attributes:
                error_known = True
                if attributes.get("error"):
                    errors += 1
        projects.append(
            {
                "project": name,
                "traces": len(rows),
                "sessions": len(sessions),
                "tokens": tokens,
                "grounded": grounded,
                "augmented": augmented,
                "series": [{"day": day, "traces": days[day]} for day in sorted(days)],
                "genera": [{"code": code, "count": genera[code]} for code in sorted(genera, key=lambda c: -genera[c])],
                "top_iris": [{"iri": iri, "count": leaves[iri]} for iri in sorted(leaves, key=lambda i: -leaves[i])[:12]],
                "latency_ms": round(sum(latency) / len(latency), 3) if latency else None,
                "total_cost": round(sum(cost), 6) if cost else None,
                "errors": errors if error_known else None,
            }
        )
    return {"window": window, "projects": projects}


def session_items(spans: list[dict], project: str) -> list[dict]:
    """One summary item per trace, grouped into the session that owns it."""

    grouped: dict[str, list[dict]] = {}
    for span in spans:
        resource = span.get("resource") if isinstance(span.get("resource"), dict) else {}
        if str(resource.get("openinference.project.name") or "") != project:
            continue
        attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
        sid = str(attributes.get("session.id") or "")
        if not sid:
            continue
        grouped.setdefault(sid, []).append(
            {
                "name": span.get("name") or "",
                "output": attributes.get("output.value") or "",
                "rich": rich_segments(
                    str(attributes.get("output.value") or ""),
                    attributes.get("sdg.spans") if isinstance(attributes.get("sdg.spans"), list) else [],
                ),
                "generated_at": _generated_ms(span),
                "augmented_at": _augmented_ms(span),
            }
        )
    items = []
    for sid in sorted(grouped):
        rows = grouped[sid]
        rows.sort(key=lambda item: item["generated_at"])
        items.append({"id": sid, "traces": len(rows), "items": rows[:40]})
    return items


def build_lineup(
    spans: list[dict],
    *,
    now_ms: int,
    window: str = "365d",
    archive: list[str] | None = None,
    live: bool = False,
    project: str = "",
) -> dict:
    root = corpora_root()
    lexicon = load_lexicon(root)
    published = {item["iri"] for item in lexicon}
    checkout = checkout_sha(root)
    return {
        "pin": SDG_PIN,
        "checkout": checkout,
        "pin_matches": bool(checkout) and checkout == SDG_PIN,
        "release_installed": root is not None and bool(lexicon or load_schema(root)),
        "roots": [
            {"id": "current", "title": "CURRENT"},
            {"id": "scratch", "title": "SCRATCH", "live": live},
            {"id": "archive", "title": "ARCHIVE", "entries": list(archive or [])},
        ],
        "lexicon": lexicon,
        "schema": load_schema(root),
        "tracing": tracing_report(spans, now_ms=now_ms, window=window),
        "sessions": session_items(spans, project) if project else [],
        "published": sorted(published),
    }
