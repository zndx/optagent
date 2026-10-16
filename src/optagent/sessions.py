# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Named agent profiles and the session lanes they own.

Hermes gives every named profile its own home (memory, persona, tools, and
sessions) and stamps each session with that profile. A profile id is
``^[a-z0-9][a-z0-9_-]{0,63}$``. ``default`` is the profile used when no
narrower route matches. OptAgent uses the same id rule, then adds a tenant
so one deployment can hold many independent agents from the federated
workspace. A session lane is a pointer. Message bodies are not copied.
"""

from __future__ import annotations

import re

_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_CHAT_KINDS = frozenset({"files"})


def profile_id(raw: str, taken: set[str]) -> str:
    """Return a Hermes-shaped profile id that is not already taken."""

    slug = re.sub(r"[^a-z0-9_-]+", "-", str(raw).lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:64]
    if not slug or not slug[0].isalnum():
        slug = f"a{slug}"[:64] if slug else "agent"
    base = slug
    number = 2
    while slug in taken or slug == "default" or not _PROFILE_ID_RE.match(slug):
        suffix = f"-{number}"
        slug = base[: 64 - len(suffix)] + suffix
        number += 1
    taken.add(slug)
    return slug


def _category(kind: str) -> str:
    return "chats" if kind in _CHAT_KINDS else "automation"


def directory_from_snapshot(snapshot: dict) -> dict:
    """Build the sessions document from snapshot members.

    Each federated project is a tenant. Each member is one named profile
    inside that tenant, plus a ``default`` profile that owns no lane of its
    own. Session rows carry counts of zero and no message list.
    """

    tenants: list[dict] = []
    profiles: list[dict] = []
    sessions: list[dict] = []
    seen_tenants: list[str] = []
    by_source: dict[str, int] = {}
    for member in snapshot.get("members") or []:
        tenant = str(member.get("project") or "workspace")
        if tenant not in seen_tenants:
            seen_tenants.append(tenant)
            tenants.append({"id": tenant, "display_name": tenant})
    taken_by_tenant: dict[str, set[str]] = {item["id"]: {"default"} for item in tenants}
    for tenant in tenants:
        profiles.append(
            {
                "name": "default",
                "display_name": "default",
                "tenant": tenant["id"],
                "description": (
                    f"Profile used for {tenant['id']} when no named profile matches. "
                    "Its sessions, memory, and tools stay in this profile."
                ),
                "is_default": True,
                "model": None,
                "provider": None,
                "skill_count": 0,
            }
        )
    for member in snapshot.get("members") or []:
        if str(member.get("kind") or "") == "spans":
            continue
        tenant = str(member.get("project") or "workspace")
        kind = str(member.get("kind") or "unknown")
        display = str(member.get("name") or "agent")
        name = profile_id(display, taken_by_tenant.setdefault(tenant, {"default"}))
        profiles.append(
            {
                "name": name,
                "display_name": display,
                "tenant": tenant,
                "description": (
                    f"{display} is an isolated {kind} profile for tenant {tenant}. "
                    "Sessions are not shared with other profiles."
                ),
                "is_default": False,
                "model": None,
                "provider": None,
                "skill_count": 0,
                "metadata-location": member.get("metadata-location") or "",
            }
        )
        category = _category(kind)
        sessions.append(
            {
                "id": f"{tenant}:{name}:{kind}",
                "tenant": tenant,
                "profile": name,
                "title": display,
                "source": kind,
                "category": category,
                "is_active": False,
                "archived": False,
                "message_count": 0,
                "tool_call_count": 0,
                "preview": (
                    "Messages stay with the agent. This lane is the profile pointer, "
                    "not a copied transcript."
                ),
            }
        )
        by_source[kind] = by_source.get(kind, 0) + 1
    return {
        "format": "optagent-sessions",
        "format-version": 2,
        "provider": "arize-phoenix",
        "connected": False,
        "note": (
            "Phoenix project is not connected. Agent traces stay in Phoenix "
            "and are not copied into this deployment."
        ),
        "snapshot-id": snapshot.get("snapshot-id"),
        "tenants": tenants,
        "profiles": profiles,
        "sessions": sessions,
        "stats": {
            "total": len(sessions),
            "active": 0,
            "archived": 0,
            "messages": 0,
            "profiles": len(profiles),
            "tenants": len(tenants),
            "by_source": by_source,
        },
    }
