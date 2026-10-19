# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Publish iteration 1 of optagent.tracing.enriched.

The object is the baseline. A later iteration writes a new prefix and a new
tx. It does not replace this one. Run against the installed snapshot:

  python -m optagent.enriched /home/rch/local/src/zndx/optagent/.devenv/state/signals-snapshot

Metaflow, when the platform profile is active:

  python scripts/flows/enriched_trace_product.py run \\
    --snapshot /home/rch/local/src/zndx/optagent/.devenv/state/signals-snapshot
"""

from __future__ import annotations

from metaflow import FlowSpec, Parameter, step


class EnrichedTraceProductFlow(FlowSpec):
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
    EnrichedTraceProductFlow()
