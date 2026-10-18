# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Genus admission over a signals-snapshot.

The procedure covers every span in the archive. A run passes ``since`` and
``until``; an empty ``since`` is the whole snapshot. Airflow backfill walks
those bounds one day at a time. This module does not call TypeSafe and does
not invent a leaf IRI. An admitted window records the genus the local
aperture returned.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from optagent.phoenix_spans import read_jsonl, write_jsonl

TAU = 0.10


def parse_time(value: str, *, default_ms: int) -> int:
    raw = (value or "").strip()
    if not raw:
        return default_ms
    if raw.isdigit():
        return int(raw)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def span_ms(span: dict) -> int:
    return int(span.get("start_time_unix_nano") or 0) // 1_000_000


def apply_admission(span: dict, scan: dict, *, augmented_at_ms: int, tau: float = TAU) -> bool:
    """Stamp the highest-margin admitted genus. Return whether a genus was recorded.

    Leaf IRIs are not assigned here. A declined or root-only scan leaves the
    span unchanged.
    """

    items = [item for item in (scan or {}).get("items") or [] if item.get("admitted") and item.get("code")]
    if not items:
        return False
    chosen = max(items, key=lambda item: float(item.get("genus_margin") or 0))
    start, end = (chosen.get("span") or [0, 0])[:2]
    attributes = span.setdefault("attributes", {})
    if attributes.get("aegir.genus_code"):
        return False
    attributes["aegir.genus_code"] = str(chosen.get("code") or "")
    label = str(chosen.get("label") or "")
    if label:
        attributes["aegir.genus_label"] = label
    attributes["aegir.genus_start"] = int(start or 0)
    attributes["aegir.genus_end"] = int(end or 0)
    attributes["aegir.rel_margin_h"] = float(chosen.get("genus_margin") or 0)
    attributes["aegir.tau"] = tau
    attributes["sdg.augmented_at"] = int(augmented_at_ms)
    attributes["aegir.admissions"] = [
        {
            "start": int((item.get("span") or [0, 0])[0] or 0),
            "end": int((item.get("span") or [0, 0])[1] or 0),
            "code": str(item.get("code") or ""),
            "label": str(item.get("label") or ""),
            "rel_margin_h": float(item.get("genus_margin") or 0),
        }
        for item in items
    ]
    return True


def span_text(span: dict) -> str:
    attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
    output = str(attributes.get("output.value") or "").strip()
    if output:
        return output
    return str(attributes.get("input.value") or "").strip()


def backfill_tree(
    root: Path,
    *,
    since_ms: int | None,
    until_ms: int | None,
    admit,
    augmented_at_ms: int,
    minimum_chars: int = 40,
) -> dict:
    """Admit genera on spans inside ``[since_ms, until_ms]``. Other spans stay as harvested."""

    files = sorted((root / "projects").glob("*/spans.jsonl"))
    spans_by_file: list[tuple[Path, list[dict]]] = [(path, read_jsonl(path)) for path in files]
    stamps = [span_ms(span) for _, spans in spans_by_file for span in spans if span_ms(span) > 0]
    if since_ms is None:
        since_ms = min(stamps) if stamps else 0
    if until_ms is None:
        until_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    examined = 0
    admitted = 0
    errors = 0
    for path, spans in spans_by_file:
        changed = False
        for span in spans:
            stamp = span_ms(span)
            if stamp < since_ms or stamp > until_ms:
                continue
            attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
            if attributes.get("aegir.genus_code"):
                continue
            text = span_text(span)
            if len(text) < minimum_chars:
                continue
            examined += 1
            if examined == 1 or examined % 25 == 0:
                print(f"admit {examined}", flush=True)
            try:
                scan = admit(text)
            except Exception:
                errors += 1
                continue
            if apply_admission(span, scan, augmented_at_ms=augmented_at_ms):
                admitted += 1
                changed = True
        if changed:
            write_jsonl(path, spans)
    document_path = root / "signals-snapshot.json"
    if document_path.is_file():
        document = json.loads(document_path.read_text(encoding="utf-8"))
        summary = document.setdefault("summary", {})
        summary["backfill.since_ms"] = str(since_ms)
        summary["backfill.until_ms"] = str(until_ms)
        summary["backfill.examined"] = str(examined)
        summary["backfill.admitted"] = str(admitted)
        summary["backfill.errors"] = str(errors)
        document_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return {
        "since_ms": since_ms,
        "until_ms": until_ms,
        "examined": examined,
        "admitted": admitted,
        "errors": errors,
    }


def aperture_admit(text: str) -> dict:
    """Local Aegir aperture. The import is deferred so harvest tests do not load the encoder."""

    from aegir.ontology.admission_items import item_scan

    return item_scan(text, tau=TAU)


def run(snapshot: Path, *, since: str = "", until: str = "", install: bool = False) -> dict:
    """Backfill one snapshot directory. Empty ``since`` covers every span in it."""

    root = Path(snapshot)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    since_ms = None if not (since or "").strip() else parse_time(since, default_ms=0)
    until_ms = None if not (until or "").strip() else parse_time(until, default_ms=now_ms)
    result = backfill_tree(
        root,
        since_ms=since_ms,
        until_ms=until_ms,
        admit=aperture_admit,
        augmented_at_ms=now_ms,
    )
    if install:
        from optagent.snapshot_store import install_archive

        archive = _gzip(root)
        install_archive(archive.read_bytes())
        result["installed"] = str(archive)
    return result


def _gzip(root: Path) -> Path:
    import tarfile

    archive = root.with_suffix(".tar.gz")
    if archive.is_dir():
        archive = root.parent / f"{root.name}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in root.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                tar.add(path, arcname=str(path.relative_to(root)))
    return archive


def last_days(days: int, *, now: datetime | None = None) -> tuple[str, str]:
    moment = now or datetime.now(timezone.utc)
    start = moment - timedelta(days=days)
    return start.isoformat(), moment.isoformat()
