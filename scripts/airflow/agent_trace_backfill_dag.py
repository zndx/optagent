# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Airflow backfill of agent-trace genus admission.

Each scheduled run covers that day's interval, so a backfill of the DAG
walks the full snapshot one UTC day at a time. A manual run can pass
``since`` and ``until`` in the DAG config to cover an explicit range instead.
Signals owns the Airflow scheduler. This file is the DAG to copy onto it.

  airflow dags backfill optagent_agent_trace_backfill \\
    --start-date 2026-02-01 --end-date 2026-10-18
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

DAG_ID = "optagent_agent_trace_backfill"


def _run(**context):
    from pathlib import Path

    from optagent.backfill import run

    dag_run = context.get("dag_run")
    conf = dict(dag_run.conf or {}) if dag_run is not None else {}
    snapshot = conf.get("snapshot") or context["params"]["snapshot"]
    if conf.get("since") or conf.get("until"):
        since = str(conf.get("since") or "")
        until = str(conf.get("until") or "")
    else:
        window = context.get("data_interval_start")
        end = context.get("data_interval_end")
        since = window.isoformat() if window is not None else ""
        until = end.isoformat() if end is not None else ""
    return run(Path(snapshot), since=since, until=until)


with DAG(
    dag_id=DAG_ID,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 0, "execution_timeout": timedelta(hours=6)},
    params={"snapshot": "/raid/build/optagent/signals-snapshot/current"},
    tags=["optagent", "backfill"],
) as dag:
    PythonOperator(task_id="admit_genera", python_callable=_run)
