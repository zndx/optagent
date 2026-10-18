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
SDG_IRI = "https://signals.zndx.org/sdg#"


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


def _window(item: dict) -> tuple[int, int]:
    span = item.get("span") or [0, 0]
    return int(span[0] or 0), int(span[1] or 0)


def link_admissions(span: dict, scan: dict, text: str) -> bool:
    """Copy admitted windows onto the same string the aperture scored.

    The IRI is the concept the aperture returned. A hit without that IRI
    does not become a link.
    """

    attributes = span.setdefault("attributes", {})
    if attributes.get("sdg.spans"):
        return False
    links = []
    for item in (scan or {}).get("items") or []:
        if not item.get("admitted"):
            continue
        iri = str(item.get("iri") or "").strip()
        if not iri.startswith(SDG_IRI):
            continue
        start, end = _window(item)
        if end <= start or start < 0 or end > len(text):
            continue
        links.append(
            {
                "start": start,
                "end": end,
                "text": text[start:end],
                "iri": iri,
                "label": str(item.get("label") or ""),
            }
        )
    if not links:
        return False
    attributes["sdg.spans"] = links
    best = max(
        (item for item in (scan or {}).get("items") or [] if item.get("admitted") and str(item.get("iri") or "").startswith(SDG_IRI)),
        key=lambda item: float(item.get("genus_margin") or 0),
    )
    if not attributes.get("aegir.genus_iri"):
        attributes["aegir.genus_iri"] = str(best.get("iri") or "")
    return True


def apply_admission(span: dict, scan: dict, *, augmented_at_ms: int, tau: float = TAU, text: str = "") -> bool:
    """Stamp the highest-margin admitted genus. Return whether a genus was recorded.

    A declined or root-only scan leaves the span unchanged. The link uses the
    aperture's concept IRI and the character window it scored.
    """

    items = [item for item in (scan or {}).get("items") or [] if item.get("admitted") and item.get("code")]
    if not items:
        return False
    chosen = max(items, key=lambda item: float(item.get("genus_margin") or 0))
    start, end = _window(chosen)
    attributes = span.setdefault("attributes", {})
    fresh = not attributes.get("aegir.genus_code")
    if fresh:
        attributes["aegir.genus_code"] = str(chosen.get("code") or "")
        label = str(chosen.get("label") or "")
        if label:
            attributes["aegir.genus_label"] = label
        attributes["aegir.genus_start"] = start
        attributes["aegir.genus_end"] = end
        attributes["aegir.rel_margin_h"] = float(chosen.get("genus_margin") or 0)
        attributes["aegir.tau"] = tau
        attributes["sdg.augmented_at"] = int(augmented_at_ms)
        attributes["aegir.admissions"] = [
            {
                "start": _window(item)[0],
                "end": _window(item)[1],
                "code": str(item.get("code") or ""),
                "label": str(item.get("label") or ""),
                "iri": str(item.get("iri") or ""),
                "rel_margin_h": float(item.get("genus_margin") or 0),
            }
            for item in items
        ]
    linked = link_admissions(span, scan, text) if text else False
    return fresh or linked


def span_text(span: dict) -> str:
    """The exact string whose offsets the aperture will use. Not a stripped copy."""

    attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else {}
    output = attributes.get("output.value")
    if isinstance(output, str) and output.strip():
        return output
    incoming = attributes.get("input.value")
    return incoming if isinstance(incoming, str) else ""


def backfill_tree(
    root: Path,
    *,
    since_ms: int | None,
    until_ms: int | None,
    admit,
    augmented_at_ms: int,
    minimum_chars: int = 40,
    links_only: bool = False,
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
            if attributes.get("sdg.spans"):
                continue
            already = bool(attributes.get("aegir.genus_code"))
            if links_only and not already:
                continue
            text = span_text(span)
            if not already and len(text.strip()) < minimum_chars:
                continue
            if not text:
                continue
            examined += 1
            if examined == 1 or examined % 25 == 0:
                print(f"admit {examined}", flush=True)
            try:
                scan = admit(text)
            except Exception:
                errors += 1
                continue
            if apply_admission(span, scan, augmented_at_ms=augmented_at_ms, text=text):
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


def run(snapshot: Path, *, since: str = "", until: str = "", install: bool = False, links_only: bool = False) -> dict:
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
        links_only=links_only,
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
