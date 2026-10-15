# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Impala FDW registration for Kudu and Iceberg.

The foreign data wrapper is the native PostgreSQL extension from
weathership/impala_fdw. Kudu scans and writes use access kudu_scan.
Iceberg tables and Impala UNION views use access impala_sql. Product
sessions use Kerberos. This module does not open an Impala connection
of its own.
"""

import os
import re
from pathlib import Path

DEFAULT_DB_URL = "postgres://127.0.0.1:5599/optagent"
SERVER_NAME = "impala_kudu_srv"
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def db_url() -> str:
    return os.environ.get("OPTAGENT_DB_URL", DEFAULT_DB_URL)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def quote_ident(name: str) -> str:
    if not _IDENT.fullmatch(name):
        raise ValueError(f"unsupported SQL identifier {name!r}")
    return name


def foreign_table_sql(
    *,
    name: str,
    database: str,
    table: str,
    access: str,
    columns: str,
) -> str:
    """DDL for one foreign table. columns is a SQL column list."""

    if access not in {"kudu_scan", "impala_sql"}:
        raise ValueError("access must be kudu_scan or impala_sql")
    if not columns.strip():
        raise ValueError("columns is empty")
    return (
        f"CREATE FOREIGN TABLE {quote_ident(name)} (\n  {columns.strip()}\n)\n"
        f"SERVER {SERVER_NAME}\n"
        "OPTIONS (\n"
        f"  database {sql_literal(database)},\n"
        f"  \"table\" {sql_literal(table)},\n"
        f"  access {sql_literal(access)}\n"
        ");"
    )


def _server_options(host: str, port: str, kudu_masters: str) -> str:
    masters = kudu_masters or f"{host}:7051"
    return (
        "OPTIONS (\n"
        f"    host {sql_literal(host)},\n"
        f"    port {sql_literal(port)},\n"
        "    auth 'kerberos',\n"
        f"    kudu_masters {sql_literal(masters)},\n"
        "    default_access 'impala_sql'\n"
        "  )"
    )


def registration_sql(
    *,
    module_path: str,
    host: str = "",
    port: str = "21050",
    kudu_masters: str = "",
    principal: str = "",
    keytab: str = "",
) -> str:
    """SQL that installs the wrapper and, when host is set, the server.

    User mapping is included only when both a principal and a keytab path
    are provided. The keytab file is not required to exist yet: the path
    is what Postgres reads at query time.
    """

    if not module_path:
        raise ValueError("module_path is empty")
    module = sql_literal(module_path)
    statements = [
        "DROP EXTENSION IF EXISTS impala_fdw CASCADE;",
        "DROP FOREIGN DATA WRAPPER IF EXISTS impala_fdw CASCADE;",
        "DROP FUNCTION IF EXISTS impala_fdw_handler() CASCADE;",
        "DROP FUNCTION IF EXISTS impala_fdw_validator(text[], oid) CASCADE;",
        "DROP FUNCTION IF EXISTS impala_fdw_exec(text, text) CASCADE;",
        "CREATE FUNCTION impala_fdw_handler()\n"
        "RETURNS fdw_handler\n"
        f"AS {module}\n"
        "LANGUAGE C STRICT;",
        "CREATE FUNCTION impala_fdw_validator(text[], oid)\n"
        "RETURNS void\n"
        f"AS {module}\n"
        "LANGUAGE C STRICT;",
        "CREATE FUNCTION impala_fdw_exec(text, text)\n"
        "RETURNS text\n"
        f"AS {module}\n"
        "LANGUAGE C STRICT;",
        "CREATE FOREIGN DATA WRAPPER impala_fdw\n"
        "  HANDLER impala_fdw_handler\n"
        "  VALIDATOR impala_fdw_validator;",
    ]
    if host:
        statements.append(f"DROP SERVER IF EXISTS {SERVER_NAME} CASCADE;")
        statements.append(
            f"CREATE SERVER {SERVER_NAME}\n"
            "  FOREIGN DATA WRAPPER impala_fdw\n"
            f"  {_server_options(host, port, kudu_masters)};"
        )
        if principal and keytab:
            statements.append(
                "CREATE USER MAPPING FOR CURRENT_USER\n"
                f"  SERVER {SERVER_NAME}\n"
                "  OPTIONS (\n"
                f"    principal {sql_literal(principal)},\n"
                f"    keytab {sql_literal(keytab)}\n"
                "  );"
            )
    return "\n".join(statements) + "\n"


def registration_sql_from_env(module_path: str) -> str:
    auth = os.environ.get("IMPALA_FDW_AUTH", "kerberos")
    if auth != "kerberos":
        raise SystemExit("IMPALA_FDW_AUTH must be kerberos")
    return registration_sql(
        module_path=module_path,
        host=os.environ.get("IMPALA_HS2_HOST", ""),
        port=os.environ.get("IMPALA_HS2_PORT", "21050"),
        kudu_masters=os.environ.get("KUDU_MASTERS", ""),
        principal=os.environ.get("IMPALA_KRB_PRINCIPAL", ""),
        keytab=os.environ.get("IMPALA_KRB_KEYTAB", ""),
    )


def probe_warehouse(url: str | None = None) -> dict:
    """Report whether this Postgres has the FDW loaded. Never raises."""

    target = url or db_url()
    absent = {"postgres": "unreachable", "fdw": "absent", "server": None}
    try:
        import psycopg
    except ImportError:
        return {**absent, "postgres": "psycopg-missing"}
    try:
        with psycopg.connect(target, connect_timeout=2) as conn:
            fdw = conn.execute(
                "SELECT fdwname FROM pg_foreign_data_wrapper WHERE fdwname = 'impala_fdw'"
            ).fetchone()
            server = conn.execute(
                "SELECT srvname FROM pg_foreign_server WHERE srvname = %s",
                (SERVER_NAME,),
            ).fetchone()
    except Exception:
        return absent
    return {
        "postgres": "ok",
        "fdw": "impala_fdw" if fdw else "absent",
        "server": server[0] if server else None,
    }


def main() -> None:
    import sys

    if len(sys.argv) != 2 or sys.argv[1] != "sql":
        raise SystemExit("usage: python -m optagent.warehouse sql")
    module = os.environ.get("IMPALA_FDW_MODULE", "")
    if not module:
        raise SystemExit("IMPALA_FDW_MODULE is not set")
    sys.stdout.write(registration_sql_from_env(module))


if __name__ == "__main__":
    main()
