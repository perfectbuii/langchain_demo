"""
agent/tools/http_call_tool.py
Tool: http_call_tool
Executes a single HTTP TestCase against the target API server.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from langchain_core.tools import tool

from agent.config import settings
from agent.state import TestCase, TestResult


@tool
def http_call_tool(test_case: dict) -> dict:
    """
    Execute a single HTTP test case and return a TestResult dict.

    Args:
        test_case: A TestCase dict with method, path, headers, body, etc.

    Returns:
        TestResult dict with status, latency_ms, response_body, error.
    """
    tc = TestCase(**{k: test_case.get(k) for k in TestCase.__annotations__})  # type: ignore[misc]

    url = settings.base_url_http.rstrip("/") + tc["path"]

    error: str | None = None
    actual_status: int | None = None
    response_body: Any = None
    latency_ms: float = 0.0

    attempt = 0
    while attempt <= settings.retry_attempts:
        try:
            t0 = time.perf_counter()
            with httpx.Client(timeout=settings.timeout_seconds) as client:
                resp = client.request(
                    method=tc["method"],
                    url=url,
                    headers=tc["headers"] or {},
                    params=tc["query_params"] or {},
                    json=tc["body"] if tc["body"] else None,
                )
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            actual_status = resp.status_code

            try:
                response_body = resp.json()
            except Exception:
                response_body = resp.text

            error = None
            break

        except httpx.TimeoutException:
            error = "Request timed out"
        except httpx.ConnectError as exc:
            error = f"Connection error: {exc}"
        except Exception as exc:
            error = f"Unexpected error: {exc}"

        attempt += 1

    passed = (
        error is None
        and actual_status is not None
        and actual_status == tc["expected_status"]
    )

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
