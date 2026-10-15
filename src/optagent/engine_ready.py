# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Exit 0 when Engine/Status on the lattice port answers project=optagent."""

import os
import sys

import grpc
from zndx.engine.v1 import engine_pb2, engine_pb2_grpc


def main() -> int:
    port = os.environ.get("OPTAGENT_ENGINE_PORT", "50851")
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = engine_pb2_grpc.EngineStub(channel)
    try:
        reply = stub.Status(engine_pb2.StatusRequest(), timeout=3)
    except Exception as exc:  # noqa: BLE001 — probe must report, not raise
        print(f"Status failed: {exc}", file=sys.stderr)
        return 1
    if reply.project != "optagent":
        print(f"project={reply.project!r}", file=sys.stderr)
        return 1
    kinds = [surface.kind for surface in reply.surfaces]
    if "primary" not in kinds:
        print("no primary surface", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
