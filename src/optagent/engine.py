# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

"""Lattice face: zndx.engine.v1.Engine on :50851.

Status advertises the product UI and does not claim a hosted model.
Other Engine methods stay unimplemented. Reflection is on so grpcurl
can call Status without a local descriptor.
"""

import os
import socket
from concurrent import futures

import grpc
from grpc_reflection.v1alpha import reflection
from zndx.engine.v1 import engine_pb2, engine_pb2_grpc

ENGINE_PORT = 50851
UI_PORT = 9892
_SERVICE = "zndx.engine.v1.Engine"


def ui_open(port: int) -> bool:
    sock = socket.socket()
    sock.settimeout(0.2)
    try:
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def surfaces() -> list:
    port = int(os.environ.get("OPTAGENT_UI_PORT", str(UI_PORT)))
    url = os.environ.get("OPTAGENT_PRIMARY_UI", f"http://127.0.0.1:{port}")
    return [engine_pb2.Surface(kind="primary", url=url, healthy=ui_open(port))]


class EngineServicer(engine_pb2_grpc.EngineServicer):
    def Status(self, request, context):
        return engine_pb2.StatusResponse(
            project="optagent",
            total_gpus=0,
            surfaces=surfaces(),
        )

    def ServerQuery(self, request, context):
        if request.kind == engine_pb2.SERVER_QUERY_KIND_SURFACES:
            return engine_pb2.ServerQueryResponse(project="optagent", surfaces=surfaces())
        if request.kind == engine_pb2.SERVER_QUERY_KIND_PEERS:
            return engine_pb2.ServerQueryResponse(project="optagent")
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "optagent does not serve this query")


def serve(port: int | None = None) -> None:
    bind = port if port is not None else int(os.environ.get("OPTAGENT_ENGINE_PORT", str(ENGINE_PORT)))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    engine_pb2_grpc.add_EngineServicer_to_server(EngineServicer(), server)
    reflection.enable_server_reflection((_SERVICE, reflection.SERVICE_NAME), server)
    server.add_insecure_port(f"127.0.0.1:{bind}")
    server.start()
    print(f"optagent engine listening on {bind}", flush=True)
    server.wait_for_termination()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
