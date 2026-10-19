# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Fill Varnish when a snapshot is installed.

The page reads these objects later. A new snapshot id, or a new copy of
the same id, is a new cache key, so the warm request stores the new body.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request

WINDOWS = ("24h", "7d", "30d", "90d", "365d", "all")


def cache_revision() -> str:
    """Changes when the installed snapshot file is replaced."""

    from optagent.snapshot_store import store_root

    path = store_root() / "signals-snapshot.json"
    if not path.is_file():
        return ""
    try:
        return str(path.stat().st_mtime_ns)
    except OSError:
        return ""


def lineup_query(snapshot_id: str, revision: str, window: str = "365d") -> str:
    items: list[tuple[str, str]] = [("kind", "lineup")]
    if snapshot_id:
        items.append(("snapshot", snapshot_id))
    if revision:
        items.append(("rev", revision))
    if window and window != "365d":
        items.append(("window", window))
    return urllib.parse.urlencode(items)


def window_query(window: str, snapshot_id: str, revision: str) -> str:
    items: list[tuple[str, str]] = [("kind", "window"), ("window", window or "365d")]
    if snapshot_id:
        items.append(("snapshot", snapshot_id))
    if revision:
        items.append(("rev", revision))
    return urllib.parse.urlencode(items)


def range_query(ranges: str, snapshot_id: str, revision: str) -> str:
    items: list[tuple[str, str]] = [("kind", "ranges")]
    if snapshot_id:
        items.append(("snapshot", snapshot_id))
    if revision:
        items.append(("rev", revision))
    if ranges:
        items.append(("ranges", ranges))
    return urllib.parse.urlencode(items)


def origin_query(revision: str) -> str:
    return f"rev={urllib.parse.quote(revision)}" if revision else ""


def warm_snapshot_caches() -> None:
    """Store the snapshot, sessions, lineup, and timeline windows in Varnish.

    Returns when Varnish is not running. The AMP has no Varnish.
    """

    port = os.environ.get("OPTAGENT_VARNISH_PORT", "6095").strip() or "6095"
    if port in {"0", "1"}:
        return
    from optagent.snapshot_store import installed_document

    document = installed_document() or {}
    snapshot_id = str(document.get("snapshot-id") or "")
    if not snapshot_id:
        return
    revision = cache_revision()
    targets = [
        ("snapshot_origin", origin_query(revision)),
        ("sessions_origin", origin_query(revision)),
        ("summary_origin", lineup_query(snapshot_id, revision)),
    ]
    for window in WINDOWS:
        targets.append(("summary_origin", window_query(window, snapshot_id, revision)))
    stored = 0
    for name, query in targets:
        url = f"http://127.0.0.1:{port}/api/optagent/v1/{name}"
        if query:
            url = f"{url}?{query}"
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                response.read()
        except (OSError, TimeoutError):
            break
        stored += 1
    if stored:
        print(f"warmed {stored} snapshot cache objects for {snapshot_id}", flush=True)
