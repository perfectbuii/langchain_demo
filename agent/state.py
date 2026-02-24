"""
agent/state.py – shared mutable state carried through the LangGraph pipeline.
"""

from __future__ import annotations

from typing import Annotated, Any, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ── Individual data shapes ────────────────────────────────────────────────────


class APIEndpoint(TypedDict):
    """One API endpoint discovered from a spec."""

    api_id: str            # e.g. "GET /accounts/{id}"
    method: str            # HTTP method or "GRPC"
    path: str              # URL path or gRPC method name
    operation_id: str
    summary: str
    parameters: list[dict]
    request_schema: dict | None
    response_schemas: dict   # status_code → schema
    tags: list[str]
    source: str            # "openapi" | "proto"


class TestCase(TypedDict):
    """One generated test case."""

    test_id: str
    api_id: str
    test_type: str         # "positive" | "negative" | "schema"
    description: str
    method: str
    path: str
    headers: dict
    path_params: dict
    query_params: dict
    body: dict | None
    expected_status: int
    expected_schema: dict | None
    transport: str          # "http" | "grpc"


class TestResult(TypedDict):
    """Execution result for one TestCase."""

    test_id: str
    api_id: str
    test_type: str
    description: str
    status: str             # "passed" | "failed" | "error"
    expected_status: int
    actual_status: int | None
    latency_ms: float
    response_body: Any
    validation_errors: list[str]
    error: str | None


# ── Main Agent State ──────────────────────────────────────────────────────────


class AgentState(TypedDict):
    """Full state object threaded through every node of the LangGraph."""

    # Conversation / reasoning messages
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Input
    service: str

    # Discovery
    spec_path: str | None          # resolved path to the main spec file
    spec_type: str | None          # "openapi" | "proto" | "both"
    raw_spec: dict | None          # parsed spec content

    # API catalogue
    apis: list[APIEndpoint]

    # Optional filter: only test these api_ids (None = test all)
    api_filter: list[str] | None

    # Generated tests
    generated_tests: list[TestCase]

    # Execution results
    results: list[TestResult]

    # Aggregate metrics
    metrics: dict[str, Any]

    # Report artefacts
    report: dict | None
    report_paths: list[str]

    # Control flow
    phase: str        # "discover" | "generate" | "execute" | "validate" | "report" | "done"
    error: str | None
