# Copyright 2026 zndx
# SPDX-License-Identifier: Apache-2.0

from concurrent import futures

import grpc
from zndx.engine.v1 import engine_pb2, engine_pb2_grpc

from optagent.engine import EngineServicer


def test_status_names_the_project_and_does_not_claim_a_model() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    engine_pb2_grpc.add_EngineServicer_to_server(EngineServicer(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = engine_pb2_grpc.EngineStub(channel)
        reply = stub.Status(engine_pb2.StatusRequest(), timeout=3)
        assert reply.project == "optagent"
        assert list(reply.endpoints) == []
        assert reply.total_gpus == 0
        assert reply.surfaces[0].kind == "primary"
        assert reply.surfaces[0].url == "http://127.0.0.1:9892"
        query = stub.ServerQuery(
            engine_pb2.ServerQueryRequest(kind=engine_pb2.SERVER_QUERY_KIND_SURFACES),
            timeout=3,
        )
        assert query.surfaces[0].url == reply.surfaces[0].url
    finally:
        server.stop(0)
