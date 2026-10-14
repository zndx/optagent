# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Span ledger: one transparent relation over Kudu and Iceberg.

A span is one stretch of an agent run. Hot hours live in ``span_tier0``
(Kudu). Settled hours live in ``span_tier1`` (Iceberg). ``span`` is the
Impala view readers use. Hours still present in tier0 are masked out of
tier1, so a settle that has not dropped the hot hour cannot double-count.

Writes go to tier0 through ``kudu_scan``. tier1 and the view are
``impala_sql`` and are not insert targets. tier1 is registered in the
Polaris catalog. This module does not emit Impala ``CREATE TABLE …
STORED AS ICEBERG``.
"""

from optagent.warehouse import SERVER_NAME, quote_ident, sql_literal

DATABASE = "optagent"
TIER0 = "span_tier0"
TIER1 = "span_tier1"
SURFACE = "span"
COLUMNS = (
    "epoch_hour integer,\n"
    "  span_id text,\n"
    "  agent text,\n"
    "  kind text,\n"
    "  seq bigint,\n"
    "  opened_ns bigint,\n"
    "  summary text,\n"
    "  body text,\n"
    "  body_uri text"
)
_VIEW_COLUMNS = (
    "epoch_hour, span_id, agent, kind, seq, opened_ns, summary, body, body_uri"
)


def writable(relation: str) -> bool:
    """Only the hot Kudu tier accepts INSERT."""

    return relation == TIER0


def view_sql() -> str:
    """Impala view. tier1 hours still stored in tier0 stay hidden."""

    return (
        f"CREATE VIEW IF NOT EXISTS {DATABASE}.{SURFACE} AS\n"
        f"SELECT {_VIEW_COLUMNS}\n"
        f"FROM {DATABASE}.{TIER0}\n"
        "UNION ALL\n"
        f"SELECT {_VIEW_COLUMNS}\n"
        f"FROM {DATABASE}.{TIER1} t1\n"
        f"WHERE t1.epoch_hour NOT IN ("
        f"SELECT epoch_hour FROM {DATABASE}.{TIER0} GROUP BY 1)"
    )


def create_view_call() -> str:
    """Run the view on Impala through the FDW. Not a Postgres view."""

    return (
        "SELECT impala_fdw_exec(\n"
        f"  {sql_literal(SERVER_NAME)},\n"
        f"  $span_view${view_sql()}$span_view$\n"
        ");"
    )


def foreign_tables_sql() -> str:
    """Postgres foreign tables for the hot tier, the settled tier, and the view."""

    parts = [
        _foreign_table(TIER0, "kudu_scan", kudu_table=f"impala::{DATABASE}.{TIER0}"),
        _foreign_table(TIER1, "impala_sql"),
        _foreign_table(SURFACE, "impala_sql"),
    ]
    return "\n".join(parts)


def _foreign_table(name: str, access: str, kudu_table: str = "") -> str:
    options = [
        f"  database {sql_literal(DATABASE)}",
        f"  \"table\" {sql_literal(name)}",
        f"  access {sql_literal(access)}",
    ]
    if kudu_table:
        options.insert(2, f"  kudu_table {sql_literal(kudu_table)}")
    option_sql = ",\n".join(options)
    return (
        f"CREATE FOREIGN TABLE {quote_ident(name)} (\n  {COLUMNS}\n)\n"
        f"SERVER {SERVER_NAME}\n"
        f"OPTIONS (\n{option_sql}\n);"
    )
