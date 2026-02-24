"""
agent/executor/rest_executor.py
Runs a batch of HTTP TestCases concurrently and returns TestResult dicts.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from agent.config import settings
from agent.state import TestCase, TestResult


def _run_one(tc: TestCase) -> TestResult:
    url = settings.base_url_http.rstrip("/") + tc["path"]

    error: str | None = None
    actual_status: int | None = None
    response_body: Any = None
    latency_ms: float = 0.0

    for _ in range(settings.retry_attempts + 1):
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
    """Execute a list of HTTP test cases concurrently."""
    results: list[TestResult] = []
    with ThreadPoolExecutor(max_workers=settings.concurrency) as pool:
        futures = {pool.submit(_run_one, tc): tc for tc in test_cases}
        for future in as_completed(futures):
            results.append(future.result())
    return results
