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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from optagent.phoenix_spans import rich_segments

SDG_PIN = "b24ef9f606605dd7bb8877bddd2d9672c78282ad"
SDG_IRI = "https://signals.zndx.org/sdg#"
_HOUR_MS = 3_600_000
_DAY_MS = 86_400_000
_WINDOWS = {
    "24h": _DAY_MS,
    "7d": 7 * _DAY_MS,
    "30d": 30 * _DAY_MS,
    "90d": 90 * _DAY_MS,
    "365d": 365 * _DAY_MS,
}
_MAX_WINDOW_MS = 3660 * _DAY_MS
_CONCEPT = re.compile(
    r"<(https://signals\.zndx\.org/sdg#[^>]+)>\s+a\s+skos:Concept\s*;(?P<body>.*?)(?=\n<https://|\Z)",
    re.S,
)
_NOTE = re.compile(r'skos:notation\s+"([^"]+)"')
_LABEL = re.compile(r'skos:prefLabel\s+"([^"]+)"')
_ALT = re.compile(r'skos:altLabel\s+"([^"]+)"')
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
            alts: list[str] = []
            for alt in _ALT.findall(body):
                if alt not in alts:
                    alts.append(alt)
            concepts[iri] = {
                "iri": iri,
                "code": (_NOTE.search(body).group(1) if _NOTE.search(body) else ""),
                "label": (_LABEL.search(body).group(1) if _LABEL.search(body) else iri.rsplit("#", 1)[-1]),
                "alt": alts,
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


def bucket_unit(duration_ms: int) -> str:
    """Same duration policy as the Gaius cognition histogram.

    Hour through 48h, 6h through 14d, day through 180d, week through 1100d,
    otherwise month.
    """

    if duration_ms <= 48 * _HOUR_MS:
        return "hour"
    if duration_ms <= 14 * _DAY_MS:
        return "6h"
    if duration_ms <= 180 * _DAY_MS:
        return "day"
    if duration_ms <= 1100 * _DAY_MS:
        return "week"
    return "month"


def _ms(moment: datetime) -> int:
    return int(round(moment.timestamp() * 1000))


def _utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _midnight(moment: datetime) -> datetime:
    moment = moment.astimezone(timezone.utc)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def _next_month(moment: datetime) -> datetime:
    if moment.month == 12:
        return moment.replace(year=moment.year + 1, month=1)
    return moment.replace(month=moment.month + 1)


def build_bins(start_ms: int, end_ms: int, unit: str) -> list[tuple[int, int]]:
    """Half-open bins. Hour and 6h are anchored at the start; day, week, and month use UTC calendar edges."""

    if start_ms >= end_ms:
        return []
    if unit in ("hour", "6h"):
        step = _HOUR_MS if unit == "hour" else 6 * _HOUR_MS
        bins: list[tuple[int, int]] = []
        cursor = start_ms
        while cursor < end_ms:
            bins.append((cursor, min(cursor + step, end_ms)))
            cursor += step
        return bins
    start = _utc(start_ms)
    end = _utc(end_ms)
    if unit == "day":
        anchor, advance = _midnight(start), lambda moment: moment + timedelta(days=1)
    elif unit == "week":
        midnight = _midnight(start)
        anchor, advance = midnight - timedelta(days=midnight.weekday()), lambda moment: moment + timedelta(days=7)
    elif unit == "month":
        midnight = _midnight(start)
        anchor, advance = midnight.replace(day=1), _next_month
    else:
        return build_bins(start_ms, end_ms, "day")
    bins = []
    cursor_dt = anchor
    while cursor_dt < end:
        nxt = advance(cursor_dt)
        bin_start = max(cursor_dt, start)
        bin_end = min(nxt, end)
        if bin_end > bin_start:
            bins.append((_ms(bin_start), _ms(bin_end)))
        cursor_dt = nxt
    return bins


def _timeline_bounds(spans: list[dict], *, now_ms: int, window: str) -> tuple[int, int]:
    if window == "all":
        stamps = [stamp for span in spans if (stamp := _generated_ms(span)) > 0]
        start = min(stamps) if stamps else now_ms - _WINDOWS["365d"]
        if start >= now_ms:
            start = now_ms - _HOUR_MS
        if now_ms - start > _MAX_WINDOW_MS:
            start = now_ms - _MAX_WINDOW_MS
        return start, now_ms
    return now_ms - _WINDOWS.get(window, _WINDOWS["365d"]), now_ms


def _fresh() -> dict:
    return {
        "traces": 0,
        "sessions": {},
        "tokens": 0,
        "grounded": 0,
        "augmented": 0,
        "latency": [],
        "cost": [],
        "errors": 0,
        "error_known": False,
        "overwatch": set(),
        "leaves": {},
        "undomain": 0,
        "domains": {},
    }


def _observe(bucket: dict, span: dict, *, nest: bool) -> None:
    attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
    resource = span.get("resource") if isinstance(span.get("resource"), dict) else {}
    bucket["traces"] += 1
    sid = str(attributes.get("session.id") or "")
    project = str(resource.get("openinference.project.name") or "")
    if sid:
        row = bucket["sessions"].setdefault(sid, [project, 0])
        row[1] += 1
    bucket["tokens"] += token_count(span)
    if _augmented_ms(span) is not None:
        bucket["augmented"] += 1
    for item in attributes.get("sdg.spans") or []:
        if isinstance(item, dict) and item.get("iri"):
            bucket["grounded"] += 1
            iri = str(item["iri"])
            bucket["leaves"][iri] = bucket["leaves"].get(iri, 0) + 1
    lat = _metric(span, "latency_ms")
    if lat is not None:
        bucket["latency"].append(float(lat))
    spent = _metric(span, "total_cost")
    if spent is not None:
        bucket["cost"].append(float(spent))
    if "error" in attributes:
        bucket["error_known"] = True
        if attributes.get("error"):
            bucket["errors"] += 1
    if attributes.get("overwatch.reason") and sid:
        bucket["overwatch"].add(sid)
    if not nest:
        return
    code = str(attributes.get("aegir.genus_code") or "")
    if not code:
        bucket["undomain"] += 1
        return
    child = bucket["domains"].setdefault(code, _fresh())
    iri = str(attributes.get("aegir.genus_iri") or "")
    if iri and not child.get("iri"):
        child["iri"] = iri
    _observe(child, span, nest=False)


def _publish(bucket: dict, *, nest: bool) -> dict:
    sessions = bucket["sessions"]
    leaves = bucket["leaves"]
    body = {
        "traces": bucket["traces"],
        "sessions": len(sessions),
        "tokens": bucket["tokens"],
        "grounded": bucket["grounded"],
        "augmented": bucket["augmented"],
        "latency_ms": round(sum(bucket["latency"]) / len(bucket["latency"]), 3) if bucket["latency"] else None,
        "total_cost": round(sum(bucket["cost"]), 6) if bucket["cost"] else None,
        "errors": bucket["errors"] if bucket["error_known"] else None,
        "overwatch": len(bucket["overwatch"]),
        "top_iris": [
            {"iri": iri, "count": leaves[iri]}
            for iri in sorted(leaves, key=lambda item: (-leaves[item], item))[:8]
        ],
        "top_sessions": [
            {"id": sid, "project": sessions[sid][0], "traces": sessions[sid][1]}
            for sid in sorted(sessions, key=lambda item: (-sessions[item][1], item))[:8]
        ],
    }
    if nest:
        body["undomain"] = bucket["undomain"]
        body["domains"] = [
            {"code": code, "iri": child.get("iri") or "", **_publish(child, nest=False)}
            for code, child in sorted(bucket["domains"].items(), key=lambda item: (-item[1]["traces"], item[0]))
        ]
    return body


def _bin_index(bins: list[tuple[int, int]], stamp: int, end_ms: int) -> int:
    lo = 0
    hi = len(bins)
    while lo < hi:
        mid = (lo + hi) // 2
        start, end = bins[mid]
        if stamp < start:
            hi = mid
        elif stamp >= end:
            lo = mid + 1
        else:
            return mid
    if bins and stamp == end_ms:
        return len(bins) - 1
    return -1


def timeline_report(spans: list[dict], *, now_ms: int, window: str = "365d") -> dict:
    """Histogram bins for one window, with overall stats and topic-domain stats in each bin."""

    start_ms, end_ms = _timeline_bounds(spans, now_ms=now_ms, window=window)
    unit = bucket_unit(end_ms - start_ms)
    edges = build_bins(start_ms, end_ms, unit)
    overall = _fresh()
    per_bin = [_fresh() for _ in edges]
    for span in spans:
        stamp = _generated_ms(span)
        if stamp < start_ms or stamp > end_ms:
            continue
        _observe(overall, span, nest=True)
        index = _bin_index(edges, stamp, end_ms)
        if index >= 0:
            _observe(per_bin[index], span, nest=True)
    published = _publish(overall, nest=True)
    return {
        "window": window,
        "unit": unit,
        "start": start_ms,
        "end": end_ms,
        "totals": {key: published[key] for key in published if key != "domains"},
        "domains": published["domains"],
        "bins": [
            {"start": edges[index][0], "end": edges[index][1], **_publish(per_bin[index], nest=True)}
            for index in range(len(edges))
        ],
    }


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
        overwatch: set[str] = set()
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
            if attributes.get("overwatch.reason") and sid:
                overwatch.add(sid)
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
                "overwatch": len(overwatch),
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
        output = attributes.get("output.value") or ""
        incoming = attributes.get("input.value") or ""
        # The aperture scores output when it exists, otherwise the input.
        # The link offsets belong to that same string.
        body = output if str(output).strip() else incoming
        grouped.setdefault(sid, []).append(
            {
                "name": span.get("name") or "",
                "output": body,
                "rich": rich_segments(
                    str(body),
                    attributes.get("sdg.spans") if isinstance(attributes.get("sdg.spans"), list) else [],
                ),
                "generated_at": _generated_ms(span),
                "augmented_at": _augmented_ms(span),
                "genus_iri": str(attributes.get("aegir.genus_iri") or ""),
                "genus_label": str(attributes.get("aegir.genus_label") or ""),
                "genus_code": str(attributes.get("aegir.genus_code") or ""),
                "overwatch": str(attributes.get("overwatch.reason") or ""),
            }
        )
    items = []
    for sid in sorted(grouped):
        rows = grouped[sid]
        linked = [row for row in rows if any(part.get("iri") for part in row["rich"])]
        review = [row for row in rows if row.get("overwatch") and row not in linked]
        others = [row for row in rows if row not in linked and row not in review]
        others.sort(key=lambda item: item["generated_at"], reverse=True)
        shown = (linked + review + others)[:40]
        shown.sort(key=lambda item: item["generated_at"])
        items.append({"id": sid, "traces": len(rows), "items": shown})
    return items


def build_lineup(
    spans: list[dict],
    *,
    now_ms: int,
    window: str = "365d",
    archive: list[str] | None = None,
    live: bool = False,
    project: str = "",
    product: dict | None = None,
) -> dict:
    root = corpora_root()
    lexicon = load_lexicon(root)
    published = {item["iri"] for item in lexicon}
    checkout = checkout_sha(root)
    body = {
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
        "timeline": timeline_report(spans, now_ms=now_ms, window=window),
        "sessions": session_items(spans, project) if project else [],
        "published": sorted(published),
    }
    if product and product.get("id") and product.get("data_uri"):
        body["product"] = {
            "id": str(product.get("id") or ""),
            "iteration": str(product.get("iteration") or ""),
            "data_uri": str(product.get("data_uri") or ""),
            "tx_id": str(product.get("tx_id") or ""),
            "rows": str(product.get("rows") or ""),
            "links": str(product.get("links") or ""),
        }
    return body
