# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

from optagent.ledger import (
    DATABASE,
    SURFACE,
    TIER0,
    TIER1,
    create_view_call,
    foreign_tables_sql,
    view_sql,
    writable,
)

ROOT = Path(__file__).resolve().parents[1]
AGENTS_VIEW = (ROOT / "../../rch/oss-agentsview").resolve()


def test_only_the_hot_tier_is_writable() -> None:
    assert writable(TIER0)
    assert not writable(TIER1)
    assert not writable(SURFACE)


def test_view_hides_hours_still_in_the_hot_tier() -> None:
    sql = view_sql()
    assert f"CREATE VIEW IF NOT EXISTS {DATABASE}.{SURFACE} AS" in sql
    assert f"FROM {DATABASE}.{TIER0}" in sql
    assert f"FROM {DATABASE}.{TIER1} t1" in sql
    assert f"t1.epoch_hour NOT IN (SELECT epoch_hour FROM {DATABASE}.{TIER0} GROUP BY 1)" in sql
    assert "STORED AS ICEBERG" not in sql
    call = create_view_call()
    assert "impala_fdw_exec" in call
    assert "nosasl" not in call.lower()


def test_foreign_tables_split_kudu_scan_and_impala_sql() -> None:
    sql = foreign_tables_sql()
    tier0, tier1, surface = sql.split("CREATE FOREIGN TABLE ")[1:]
    assert "access 'kudu_scan'" in tier0
    assert f"kudu_table 'impala::{DATABASE}.{TIER0}'" in tier0
    assert "access 'kudu_scan'" not in tier1
    assert "kudu_table" not in tier1
    assert "access 'impala_sql'" in tier1
    assert "access 'impala_sql'" in surface
    assert "kudu_table" not in surface


def test_agentsview_is_the_local_editable_checkout() -> None:
    go_mod = (AGENTS_VIEW / "go.mod").read_text(encoding="utf-8")
    assert go_mod.startswith("module go.kenn.io/agentsview\n")
    work = (ROOT / "go.work").read_text(encoding="utf-8")
    assert "../../rch/oss-agentsview" in work
    replace = (ROOT / "ui" / "go.mod").read_text(encoding="utf-8")
    assert "replace go.kenn.io/agentsview => ../../../rch/oss-agentsview" in replace
    frontend = json.loads((ROOT / "ui" / "package.json").read_text(encoding="utf-8"))
    assert frontend["dependencies"]["agentsview-frontend"] == "file:../../../rch/oss-agentsview/frontend"
    assert (AGENTS_VIEW / "frontend" / "package.json").is_file()
    remote = (AGENTS_VIEW / ".git" / "config").read_text(encoding="utf-8")
    assert "git@github.com:weathership/oss-agentsview.git" in remote
