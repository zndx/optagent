# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0
"""Write llm.generations and hx.cot_reasoning rows as JSONL.

Run this with the Gaius virtualenv. OptAgent harvest turns each row into a span.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _iso(value) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value or "")


def main(path: Path) -> None:
    from gaius.hx.catalog import get_catalog
    from gaius.hx.cot_reasoning import get_cot_reasoning_table
    from gaius.hx.tables import get_llm_generation_table

    catalog = get_catalog()
    lines: list[str] = []
    generations = get_llm_generation_table(catalog).scan(
        selected_fields=(
            "id",
            "summary_type",
            "model_name",
            "prompt",
            "output",
            "thinking_trace",
            "input_tokens",
            "output_tokens",
            "latency_ms",
            "generated_at",
        )
    ).to_arrow().to_pylist()
    for row in generations:
        row["kind"] = "generation"
        row["generated_at"] = _iso(row.get("generated_at"))
        lines.append(json.dumps(row, default=str))
    cot_rows = get_cot_reasoning_table(catalog).scan().to_arrow().to_pylist()
    for row in cot_rows:
        lines.append(
            json.dumps(
                {
                    "kind": "cot",
                    "id": row.get("id"),
                    "technique": row.get("technique"),
                    "model_name": row.get("model_name"),
                    "prompt": row.get("prompt"),
                    "reasoning_trace": row.get("reasoning_trace"),
                    "output": row.get("output"),
                    "input_tokens": row.get("input_tokens"),
                    "output_tokens": row.get("output_tokens"),
                    "latency_ms": row.get("latency_ms"),
                    "generated_at": _iso(row.get("generated_at")),
                    "yk_queue": row.get("yk_queue"),
                    "flow_name": row.get("flow_name"),
                },
                default=str,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"generations {len(generations)} cot {len(cot_rows)}", file=sys.stderr)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
