# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Load a signals-snapshot span archive into a local Phoenix.

Reads projects/*/spans.jsonl next to signals-snapshot.json and POSTs
OTLP/HTTP protobuf to Phoenix. OptAgent does not need Phoenix to read
the same file. This command is the check that Phoenix groups it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from optagent.phoenix_spans import load_member_spans, post_spans


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a signals-snapshot archive into Phoenix.")
    parser.add_argument("archive", type=Path, help="Directory that contains signals-snapshot.json")
    parser.add_argument("--endpoint", default="http://127.0.0.1:9891/v1/traces")
    args = parser.parse_args()
    document = json.loads((args.archive / "signals-snapshot.json").read_text(encoding="utf-8"))
    spans = load_member_spans(args.archive, document.get("members") or [])
    sent = post_spans(spans, args.endpoint)
    print(f"sent {sent} spans to {args.endpoint}")


if __name__ == "__main__":
    main()
