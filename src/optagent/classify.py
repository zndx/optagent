# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Short SDG term links for a passage the local aperture already admitted.

The genus stays on the span. This stage asks TypeSafe which phrase of one to
a few words states a published child of that genus, or a sibling when the
admitted concept is itself a leaf. A whole window is not a link. None, a low
confidence, and an IRI outside the offered set are not links. Overwatch is recorded only when one session holds several admitted passages
and none of them received a term link. A single miss is left unmarked. This
module does not start an ACP agent and does not log the API key.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from optagent.backfill import TAU, parse_time, readable_segment, span_ms, span_text
from optagent.phoenix_spans import read_jsonl, write_jsonl

MODEL = "jev-1.14.0"
FLOOR = 0.55
MAX_WORDS = 4
MAX_CANDIDATES = 4
MAX_LINKS = 3
MAX_PER_IRI = 2
MAX_LINK_WORDS = 6
OVERWATCH_REASON = "session-without-terms"
_URL = "https://api.typesafe.ai/v1/systemone"
_NONE = "none"
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_STOP = frozenset(
    """
    a an the of and or to for in on at by with from as is are was were be been
    being this that these those it its into over under than then so if not no
    yes we you they i our your their but about than into
    """.split()
)


def typesafe_key() -> str:
    found = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if found:
        return found
    path = Path.home() / "local" / ".env"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("TYPESAFE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def choice_points(lexicon: list[dict], genus_iri: str) -> list[dict]:
    """Published terms a phrase may link to. The genus itself is not rediscovered.

    Children of the admitted concept are the choice set. A leaf has no
    children, so the set is the published siblings under its broader concept,
    which includes the leaf. An IRI that is not in the lexicon is not offered.
    """

    by_iri = {str(item.get("iri") or ""): item for item in lexicon if item.get("iri")}
    genus = by_iri.get(genus_iri)
    if genus is None:
        return []

    def published(iris: list) -> list[dict]:
        found = []
        seen: set[str] = set()
        for iri in iris or []:
            key = str(iri or "")
            if key in by_iri and key not in seen:
                seen.add(key)
                found.append(by_iri[key])
        return found

    children = published(genus.get("narrower") or [])
    if children:
        points = children
    else:
        siblings: list[dict] = []
        seen: set[str] = set()
        for parent in genus.get("broader") or []:
            parent_item = by_iri.get(str(parent))
            if parent_item is None:
                continue
            for item in published(parent_item.get("narrower") or []):
                if item["iri"] not in seen:
                    seen.add(item["iri"])
                    siblings.append(item)
        points = siblings or [genus]
    points.sort(key=lambda item: (str(item.get("code") or ""), str(item.get("iri") or "")))
    return points[:254]


def _phrase_forms(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text or ("_" in text and " " not in text):
        return []
    forms: list[str] = []
    tokens = text.split()
    if 1 <= len(tokens) <= MAX_WORDS and not all(token.lower() in _STOP for token in tokens):
        words = _WORD.findall(text)
        if len(tokens) > 1 or (words and len(words[0]) >= 5):
            forms.append(text)
    for word in _WORD.findall(text):
        if len(word) >= 5 and word.lower() not in _STOP:
            forms.append(word)
    return forms


def _find_phrase(text: str, phrase: str):
    parts = phrase.split()
    if not parts:
        return None
    pattern = r"\b" + r"\s+".join(re.escape(part) for part in parts) + r"\b"
    return re.search(pattern, text, flags=re.IGNORECASE)


def propose_spans(text: str, points: list[dict], *, limit: int = MAX_CANDIDATES) -> list[dict]:
    """Label phrases of one to four words that actually occur in ``text``.

    Longer phrases win over a word inside them. The whole passage is never
    proposed. A passage with no label phrase proposes nothing.
    """

    body = text or ""
    passage_words = _WORD.findall(body)
    if len(passage_words) <= MAX_WORDS:
        return []
    hits: list[dict] = []
    seen: set[str] = set()
    for point in points:
        raws = [str(point.get("label") or ""), *(str(item) for item in (point.get("alt") or []))]
        for raw in raws:
            for phrase in _phrase_forms(raw):
                norm = " ".join(phrase.lower().split())
                if not norm or norm in seen:
                    continue
                match = _find_phrase(body, phrase)
                if match is None:
                    continue
                excerpt = body[match.start() : match.end()]
                words = _WORD.findall(excerpt)
                if not (1 <= len(words) <= MAX_WORDS):
                    continue
                if len(words) >= len(passage_words):
                    continue
                seen.add(norm)
                hits.append(
                    {
                        "start": match.start(),
                        "end": match.end(),
                        "text": excerpt,
                        "words": len(words),
                    }
                )
    hits.sort(key=lambda item: (-int(item["words"]), -(int(item["end"]) - int(item["start"])), int(item["start"])))
    chosen: list[dict] = []
    for hit in hits:
        if any(hit["start"] < kept["end"] and kept["start"] < hit["end"] for kept in chosen):
            continue
        chosen.append(hit)
        if len(chosen) >= limit:
            break
    chosen.sort(key=lambda item: int(item["start"]))
    return [{"start": item["start"], "end": item["end"], "text": item["text"]} for item in chosen]


def choice_questions(candidates: list[dict], points: list[dict]) -> dict:
    """One Choice per candidate phrase. Criteria are the offered concepts plus none."""

    criteria = {_NONE: "The phrase does not state any of these concepts."}
    small = len(points) <= 12
    for point in points:
        fragment = str(point.get("iri") or "").rsplit("#", 1)[-1]
        if not fragment or fragment == _NONE:
            continue
        label = str(point.get("label") or fragment)
        code = str(point.get("code") or "")
        blurb = f"{code} {label}".strip()
        if small:
            definition = " ".join(str(point.get("definition") or "").split())
            if definition:
                blurb = f"{blurb}. {definition[:180]}"
        criteria[fragment] = blurb
    questions = {}
    for index, seq in enumerate(candidates):
        questions[f"w{index}"] = {
            "type": "choice",
            "instructions": (
                "Which concept does this phrase state in the passage? "
                "Choose none when the phrase does not state one of these concepts.\n\n"
                f"Phrase: {seq['text']}"
            ),
            "criteria": criteria,
        }
    return questions


def term_links(body: dict, candidates: list[dict], points: list[dict], text: str) -> list[dict]:
    """Keep short, non-overlapping choices above the confidence floor.

    The confidence is the number TypeSafe returned. A missing confidence, a
    choice of none, or an IRI that was not offered does not become a link.
    """

    answers = body.get("answers") if isinstance(body.get("answers"), dict) else {}
    by_fragment = {}
    for point in points:
        fragment = str(point.get("iri") or "").rsplit("#", 1)[-1]
        if fragment and fragment != _NONE:
            by_fragment[fragment] = point
    raw = []
    for index, seq in enumerate(candidates):
        answer = answers.get(f"w{index}")
        if not isinstance(answer, dict) or "confidence" not in answer:
            continue
        choice = str(answer.get("choice") or "")
        if not choice or choice == _NONE:
            continue
        point = by_fragment.get(choice)
        if point is None:
            continue
        try:
            confidence = float(answer["confidence"])
        except (TypeError, ValueError):
            continue
        if confidence < FLOOR:
            continue
        start, end = int(seq["start"]), int(seq["end"])
        if end <= start or start < 0 or end > len(text) or text[start:end] != seq.get("text"):
            continue
        words = _WORD.findall(text[start:end])
        if not (1 <= len(words) <= MAX_WORDS) or len(words) >= len(_WORD.findall(text)):
            continue
        raw.append(
            {
                "start": start,
                "end": end,
                "text": text[start:end],
                "iri": point["iri"],
                "label": str(point.get("label") or ""),
                "confidence": confidence,
                "words": len(words),
            }
        )
    raw.sort(key=lambda item: (-float(item["confidence"]), int(item["words"]), int(item["start"])))
    kept: list[dict] = []
    per_iri: dict[str, int] = {}
    budget = MAX_LINK_WORDS
    for item in raw:
        if any(item["start"] < other["end"] and other["start"] < item["end"] for other in kept):
            continue
        if per_iri.get(item["iri"], 0) >= MAX_PER_IRI:
            continue
        if int(item["words"]) > budget:
            continue
        kept.append(item)
        per_iri[item["iri"]] = per_iri.get(item["iri"], 0) + 1
        budget -= int(item["words"])
        if len(kept) >= MAX_LINKS:
            break
    kept.sort(key=lambda item: int(item["start"]))
    return [
        {
            "start": item["start"],
            "end": item["end"],
            "text": item["text"],
            "iri": item["iri"],
            "label": item["label"],
            "confidence": item["confidence"],
        }
        for item in kept
    ]


def post_systemone(state: str, questions: dict, *, opener=urllib.request.urlopen) -> dict:
    key = typesafe_key()
    if not key:
        raise RuntimeError("TYPESAFE_API_KEY is unset")
    payload = {"model": MODEL, "state": state, "questions": questions}
    request = urllib.request.Request(
        _URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with opener(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"typesafe systemone HTTP {exc.code}: {detail}") from exc
    if not isinstance(body, dict):
        raise RuntimeError("typesafe systemone response is not an object")
    return body


def _stamp_usage(attributes: dict, body: dict) -> None:
    attributes["typesafe.model"] = str(body.get("model") or MODEL)
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    for source, target in (("input_tokens", "typesafe.input_tokens"), ("output_tokens", "typesafe.output_tokens")):
        if source not in usage:
            continue
        try:
            attributes[target] = int(usage[source])
        except (TypeError, ValueError):
            continue


def _clear_links(attributes: dict) -> None:
    attributes.pop("sdg.spans", None)
    attributes.pop("overwatch.reason", None)
    attributes.pop("overwatch.phase", None)


def _has_term_link(attributes: dict) -> bool:
    spans = attributes.get("sdg.spans")
    if not isinstance(spans, list):
        return False
    return any(isinstance(item, dict) and str(item.get("iri") or "").startswith("https://signals.zndx.org/sdg#") for item in spans)


def _clear_overwatch(attributes: dict) -> bool:
    changed = False
    if "overwatch.reason" in attributes:
        attributes.pop("overwatch.reason", None)
        changed = True
    if "overwatch.phase" in attributes:
        attributes.pop("overwatch.phase", None)
        changed = True
    return changed


def apply_session_overwatch(spans: list[dict]) -> tuple[int, bool]:
    """Flag a session when several admitted passages all lack a term link.

    An admitted passage is a readable genus window. One miss is not Overwatch.
    A session that linked any of its admitted passages is not Overwatch.
    """

    groups: dict[str, list[dict]] = {}
    changed = False
    for span in spans:
        attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else None
        if not isinstance(attributes, dict):
            continue
        session_id = str(attributes.get("session.id") or "")
        if not attributes.get("aegir.genus_code") or not session_id or not readable_segment(span_text(span)):
            if _clear_overwatch(attributes):
                changed = True
            continue
        groups.setdefault(session_id, []).append(span)
    flagged = 0
    for passages in groups.values():
        linked = any(_has_term_link(span["attributes"]) for span in passages)
        fail = len(passages) >= 2 and not linked
        if fail:
            flagged += 1
        for span in passages:
            attributes = span["attributes"]
            if fail:
                if attributes.get("overwatch.reason") != OVERWATCH_REASON:
                    attributes["overwatch.reason"] = OVERWATCH_REASON
                    changed = True
                if attributes.get("overwatch.phase") != "classify":
                    attributes["overwatch.phase"] = "classify"
                    changed = True
            elif _clear_overwatch(attributes):
                changed = True
    return flagged, changed


def _already(attributes: dict) -> bool:
    return bool(attributes.get("typesafe.model") or attributes.get("overwatch.reason"))


def classify_snapshot(
    snapshot: Path,
    *,
    since: str = "",
    until: str = "",
    post=None,
    lexicon: list[dict] | None = None,
) -> dict:
    """Replace whole-window links on admitted spans with short term links.

    Spans the aperture did not admit are left alone. An unreadable window is
    not sent. A call that fails leaves the span's existing links in place.
    Overwatch is applied to the whole session after classification.
    """

    if lexicon is None:
        from optagent.lineup import corpora_root, load_lexicon

        lexicon = load_lexicon(corpora_root())
    if post is None:
        post = post_systemone
    root = Path(snapshot)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    since_ms = None if not (since or "").strip() else parse_time(since, default_ms=0)
    until_ms = None if not (until or "").strip() else parse_time(until, default_ms=now_ms)
    examined = called = linked = overwatch = errors = 0
    for path in sorted((root / "projects").glob("*/spans.jsonl")):
        spans = read_jsonl(path)
        changed = False
        for span in spans:
            attributes = span.get("attributes") if isinstance(span.get("attributes"), dict) else None
            if not isinstance(attributes, dict) or not attributes.get("aegir.genus_code"):
                continue
            stamp = span_ms(span)
            if since_ms is not None and stamp < since_ms:
                continue
            if until_ms is not None and stamp > until_ms:
                continue
            if _already(attributes):
                continue
            text = span_text(span)
            if not readable_segment(text):
                if attributes.get("sdg.spans"):
                    attributes.pop("sdg.spans", None)
                    changed = True
                continue
            examined += 1
            genus_iri = str(attributes.get("aegir.genus_iri") or "")
            points = choice_points(lexicon, genus_iri)
            candidates = propose_spans(text, points) if points else []
            if not points or not candidates:
                _clear_links(attributes)
                changed = True
                continue
            try:
                body = post(text, choice_questions(candidates, points))
            except Exception as exc:
                errors += 1
                print(f"classify error {type(exc).__name__}", flush=True)
                continue
            called += 1
            _stamp_usage(attributes, body if isinstance(body, dict) else {})
            links = term_links(body if isinstance(body, dict) else {}, candidates, points, text)
            if links:
                attributes["sdg.spans"] = links
                attributes.pop("overwatch.reason", None)
                attributes.pop("overwatch.phase", None)
                linked += 1
            else:
                _clear_links(attributes)
            changed = True
        flagged, flags_changed = apply_session_overwatch(spans)
        overwatch += flagged
        if changed or flags_changed:
            write_jsonl(path, spans)
    document_path = root / "signals-snapshot.json"
    if document_path.is_file():
        document = json.loads(document_path.read_text(encoding="utf-8"))
        summary = document.setdefault("summary", {})
        if called or linked or "classify.called" not in summary:
            summary["classify.examined"] = str(examined)
            summary["classify.called"] = str(called)
            summary["classify.linked"] = str(linked)
            summary["classify.errors"] = str(errors)
            summary["classify.model"] = MODEL
            summary["classify.tau"] = str(TAU)
        summary["classify.overwatch"] = str(overwatch)
        document_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    result = {
        "examined": examined,
        "called": called,
        "linked": linked,
        "overwatch": overwatch,
        "errors": errors,
    }
    print(
        f"classify examined={examined} called={called} linked={linked} overwatch={overwatch} errors={errors}",
        flush=True,
    )
    return result
