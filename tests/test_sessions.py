# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import re

from optagent.sessions import directory_from_snapshot, profile_id
from optagent.snapshot import load_bundled

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def test_profile_ids_follow_the_hermes_rule() -> None:
    taken: set[str] = {"default"}
    assert profile_id("signal_tier0", taken) == "signal_tier0"
    assert profile_id("Signal Tier0", taken) == "signal-tier0"
    assert profile_id("signal_tier0", taken) == "signal_tier0-2"
    assert profile_id("default", set()) != "default"
    assert _PROFILE_ID.match(profile_id("  --Weird Name-- ", set()))


def test_each_tenant_gets_an_isolated_default_and_named_profiles() -> None:
    snapshot = load_bundled()
    document = directory_from_snapshot(
        {
            "snapshot-id": snapshot.snapshot_id,
            "members": [
                {
                    "project": member.project,
                    "kind": member.kind,
                    "name": member.name,
                    "metadata-location": member.metadata_location,
                }
                for member in snapshot.members
            ],
        }
    )
    assert document["connected"] is False
    assert document["format-version"] == 2
    assert "not copied" in document["note"]
    tenants = {item["id"] for item in document["tenants"]}
    assert {"signals", "gaius", "aegir"} <= tenants
    for tenant in tenants:
        owned = [item for item in document["profiles"] if item["tenant"] == tenant]
        assert sum(1 for item in owned if item["is_default"]) == 1
        assert all(_PROFILE_ID.match(item["name"]) for item in owned)
    names = {(item["tenant"], item["name"]) for item in document["profiles"]}
    assert ("signals", "signal_tier0") in names
    assert ("gaius", "hx") in names
    chats = [item for item in document["sessions"] if item["category"] == "chats"]
    automation = [item for item in document["sessions"] if item["category"] == "automation"]
    assert chats and all(item["source"] == "files" for item in chats)
    assert automation and all(item["source"] != "files" for item in automation)
    assert all(item["message_count"] == 0 for item in document["sessions"])
    assert all("messages" not in item for item in document["sessions"])
    assert document["stats"]["tenants"] == len(tenants)
    assert document["stats"]["messages"] == 0
