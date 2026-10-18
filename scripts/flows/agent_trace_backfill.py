# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Metaflow procedure for an agent-trace genus backfill.

Airflow runs one day at a time so ``airflow dags backfill`` can walk the
whole snapshot. Pass ``--since`` and ``--until`` for an explicit range.
An empty ``--since`` admits every span in the snapshot directory.

  python scripts/flows/agent_trace_backfill.py run \\
    --snapshot /raid/build/optagent/signals-snapshot/<stamp> \\
    --since 2026-10-11T00:00:00+00:00 --until 2026-10-18T00:00:00+00:00
"""

from __future__ import annotations

from metaflow import FlowSpec, Parameter, step


class AgentTraceBackfillFlow(FlowSpec):
    snapshot = Parameter("snapshot", help="Unpacked signals-snapshot directory", required=True)
    since = Parameter("since", help="UTC inclusive start. Empty covers the whole snapshot.", default="")
    until = Parameter("until", help="UTC inclusive end. Empty means now.", default="")

    @step
    def start(self):
        from pathlib import Path

        from optagent.backfill import run

        self.result = run(Path(str(self.snapshot)), since=str(self.since or ""), until=str(self.until or ""))
        self.next(self.end)

    @step
    def end(self):
        print(self.result)


if __name__ == "__main__":
    AgentTraceBackfillFlow()
