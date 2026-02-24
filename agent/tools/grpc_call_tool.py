"""
agent/tools/grpc_call_tool.py
LangChain tool: execute a single gRPC test case.

Stub class and request class are resolved at runtime from the
agent.grpc_stubs auto-discovery registry — nothing hardcoded here.
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.tools import tool

from agent.state import TestCase, TestResult


@tool
def grpc_call_tool(test_case: dict) -> dict:
    """Execute a single gRPC TestCase and return a TestResult dict.

    The path field must be in the form "/ServiceName/MethodName".
    Stub and request classes are resolved from the auto-discovery registry.
    """
    import grpc  # type: ignore
    from google.protobuf.json_format import MessageToDict  # type: ignore
    import agent.grpc_stubs as stubs_registry
    from agent.config import settings

    tc: TestCase = test_case  # type: ignore[assignment]

    error: str | None = None
    actual_status: int | None = None
    response_body: Any = None
    latency_ms: float = 0.0

    parts        = tc["path"].lstrip("/").split("/")
    service_name = parts[0] if parts else ""
    method_name  = parts[1] if len(parts) > 1 else ""

    try:
        entry    = stubs_registry.get(service_name)
        stub_cls = entry["stub_cls"]
        req_cls  = stubs_registry.resolve_request_cls(service_name, method_name)

        channel  = grpc.insecure_channel(settings.base_url_grpc)
        stub     = stub_cls(channel)
        body     = tc.get("body") or {}
        request  = req_cls(**body)

        t0 = time.perf_counter()
        response = getattr(stub, method_name)(request, timeout=settings.timeout_seconds)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)

        response_body = MessageToDict(response)
        actual_status = 0
    except (KeyError, AttributeError) as exc:
        error = str(exc)
    except Exception as grpc_exc:
        try:
            actual_status = grpc_exc.code().value[0]  # type: ignore[attr-defined]
            error = str(grpc_exc.details())            # type: ignore[attr-defined]
        except Exception:
            error = str(grpc_exc)

    passed = error is None and actual_status == tc.get("expected_status")
    return TestResult(
        test_id=tc["test_id"],
        api_id=tc["api_id"],
        test_type=tc["test_type"],
        description=tc["description"],
        status="passed" if passed else "failed",
        expected_status=tc.get("expected_status"),
        actual_status=actual_status,
        latency_ms=latency_ms,
        response_body=response_body,
        validation_errors=[],
        error=error,
    )
