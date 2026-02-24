"""
agent/executor/grpc_executor.py
Runs a batch of gRPC TestCases concurrently and returns TestResult dicts.

Fully dynamic: service name, stub class, and request class are all resolved
at runtime from the agent.grpc_stubs registry (auto-scanned).
No hardcoded service or method names live here.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from agent.config import settings
from agent.state import TestCase, TestResult


def _run_one(tc: TestCase) -> TestResult:
    error: str | None = None
    actual_status: int | None = None
    response_body: Any = None
    latency_ms: float = 0.0

    # path format: "/AccountService/CreateAccount"
    parts = tc["path"].lstrip("/").split("/")
    service_name = parts[0] if parts else ""
    method_name  = parts[1] if len(parts) > 1 else ""

    for _ in range(settings.retry_attempts + 1):
        try:
            import grpc  # type: ignore
            from google.protobuf.json_format import MessageToDict  # type: ignore
            import agent.grpc_stubs as stubs_registry

            # Resolve stub class + request class from registry — no names hardcoded
            entry    = stubs_registry.get(service_name)
            stub_cls = entry["stub_cls"]
            req_cls  = stubs_registry.resolve_request_cls(service_name, method_name)

            channel  = grpc.insecure_channel(settings.base_url_grpc)
            stub     = stub_cls(channel)
            body     = tc["body"] or {}
            request  = req_cls(**body)

            t0 = time.perf_counter()
            response = getattr(stub, method_name)(request, timeout=settings.timeout_seconds)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            response_body = MessageToDict(response)
            actual_status = 0   # gRPC OK
            error = None
            break

        except (KeyError, AttributeError) as exc:
            error = str(exc)
            break
        except Exception as grpc_exc:
            try:
                actual_status = grpc_exc.code().value[0]  # type: ignore[attr-defined]
                error = str(grpc_exc.details())            # type: ignore[attr-defined]
            except Exception:
                error = str(grpc_exc)
            break

    passed = error is None and actual_status == tc["expected_status"]
    return TestResult(
        test_id=tc["test_id"],
        api_id=tc["api_id"],
        test_type=tc["test_type"],
        description=tc["description"],
        status="passed" if passed else "failed",
        expected_status=tc["expected_status"],
        actual_status=actual_status,
        latency_ms=latency_ms,
        response_body=response_body,
        validation_errors=[],
        error=error,
    )


def run_batch(test_cases: list[TestCase]) -> list[TestResult]:
    """Execute a list of gRPC test cases concurrently."""
    results: list[TestResult] = []
    with ThreadPoolExecutor(max_workers=settings.concurrency) as pool:
        futures = {pool.submit(_run_one, tc): tc for tc in test_cases}
        for future in as_completed(futures):
            results.append(future.result())
    return results
