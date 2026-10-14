# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from optagent.warehouse import foreign_table_sql, registration_sql

ROOT = Path(__file__).resolve().parents[1]


def test_impala_fdw_submodule_points_at_weathership() -> None:
    modules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert "path = components/impala_fdw" in modules
    assert "url = git@github.com:weathership/impala_fdw.git" in modules
    assert "branch = trunk" in modules
    assert (ROOT / "components/impala_fdw/Makefile").is_file()
    assert (ROOT / "components/impala_fdw/sql/impala_fdw--0.1.1.sql").is_file()


def test_registration_sql_uses_kerberos_for_the_server() -> None:
    sql = registration_sql(
        module_path="/opt/pg-ext/lib/impala_fdw",
        host="tinybox.dev.vista.zndx.org",
        kudu_masters="tinybox.dev.vista.zndx.org:7051",
        principal="optagent@DEV.VISTA.ZNDX.ORG",
        keytab="/var/lib/optagent/optagent.keytab",
    )
    assert "CREATE FOREIGN DATA WRAPPER impala_fdw" in sql
    assert "auth 'kerberos'" in sql
    assert "nosasl" not in sql.lower()
    assert "CREATE USER MAPPING" in sql
    assert "impala_fdw_exec" in sql


def test_registration_without_a_host_skips_the_server() -> None:
    sql = registration_sql(module_path="/opt/pg-ext/lib/impala_fdw")
    assert "CREATE SERVER" not in sql
    assert "CREATE USER MAPPING" not in sql


def test_kudu_and_iceberg_use_different_access_paths() -> None:
    kudu = foreign_table_sql(
        name="metrics_tier0",
        database="default",
        table="metrics_tier0",
        access="kudu_scan",
        columns="id bigint",
    )
    iceberg = foreign_table_sql(
        name="metrics",
        database="default",
        table="metrics",
        access="impala_sql",
        columns="id bigint",
    )
    assert "access 'kudu_scan'" in kudu
    assert "access 'impala_sql'" in iceberg
    assert 'SERVER impala_kudu_srv' in kudu
    assert 'SERVER impala_kudu_srv' in iceberg
