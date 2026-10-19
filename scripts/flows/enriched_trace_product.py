# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Publish the portable snapshot as optagent.traces.snapshot.

Enriched term links are already on the spans in the archive. The snapshot
id is the version. A later snapshot is a new object. Run against the
installed snapshot:

  python -m optagent.enriched .devenv/state/signals-snapshot

Metaflow, when the platform profile is active:

  python scripts/flows/enriched_trace_product.py run \\
    --snapshot .devenv/state/signals-snapshot
"""

from __future__ import annotations

from metaflow import FlowSpec, Parameter, step


class SnapshotProductFlow(FlowSpec):
    snapshot = Parameter("snapshot", help="Unpacked signals-snapshot directory", required=True)

    @step
    def start(self):
        from pathlib import Path

        from optagent.enriched import publish

        self.result = publish(Path(str(self.snapshot)))
        self.next(self.end)

    @step
    def end(self):
        print(self.result)


if __name__ == "__main__":
    SnapshotProductFlow()
