# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Metaflow procedure for an agent-trace genus backfill.

Airflow runs one day at a time so ``airflow dags backfill`` can walk the
whole snapshot. Pass ``--since`` and ``--until`` for an explicit range.
An empty ``--since`` admits every span in the snapshot directory.
``--classify true`` runs the TypeSafe short-span stage after admission.
The default leaves that stage off.

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
    classify = Parameter("classify", help="Run TypeSafe short-span classification after admission.", default="false")

    @step
    def start(self):
        from pathlib import Path

        from optagent.backfill import run

        root = Path(str(self.snapshot))
        since = str(self.since or "")
        until = str(self.until or "")
        self.result = run(root, since=since, until=until)
        if str(self.classify or "").lower() in {"1", "true", "yes"}:
            from optagent.classify import classify_snapshot

            self.result["classify"] = classify_snapshot(root, since=since, until=until)
        self.next(self.end)

    @step
    def end(self):
        print(self.result)


if __name__ == "__main__":
    AgentTraceBackfillFlow()
