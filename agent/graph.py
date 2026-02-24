"""
agent/graph.py
LangGraph pipeline:  DISCOVER → GENERATE → EXECUTE → VALIDATE → REPORT
Each node is a pure function over AgentState.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from agent.config import settings
from agent.state import AgentState, TestCase, TestResult
from agent.tools.load_spec_tool import load_spec_tool
from agent.tools.discover_apis_tool import discover_apis_tool
from agent.tools.generate_test_cases_tool import generate_test_cases_tool
from agent.tools.http_call_tool import http_call_tool
from agent.tools.grpc_call_tool import grpc_call_tool
from agent.tools.schema_validate_tool import schema_validate_tool
from agent.tools.report_builder_tool import report_builder_tool

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


# ═══════════════════════════════════════════════════════════════
# NODE: discover
# ═══════════════════════════════════════════════════════════════

def node_discover(state: AgentState) -> dict:
    """Locate spec files and parse all API endpoints."""
    console.print(Panel("[bold blue]PHASE 1 — DISCOVER[/bold blue]", expand=False))

    service = state["service"]

    # Load spec files
    spec_info = load_spec_tool.invoke({"service_name": service})
    console.print(f"  spec_type: [cyan]{spec_info['spec_type']}[/cyan]")

    if spec_info["spec_type"] == "none":
        return {
            "phase": "done",
            "error": f"No spec found for service '{service}'",
            "messages": [AIMessage(content=f"ERROR: No spec found for '{service}'")],
        }

    # Discover endpoints
    apis = discover_apis_tool.invoke({
        "openapi_path": spec_info["openapi_path"],
        "proto_path": spec_info["proto_path"],
    })
    console.print(f"  discovered [green]{len(apis)}[/green] API endpoints")

    return {
        "spec_path": spec_info["openapi_path"] or spec_info["proto_path"],
        "spec_type": spec_info["spec_type"],
        "raw_spec": spec_info["openapi_raw"],
        "apis": apis,
        "phase": "generate",
        "messages": [
            AIMessage(
                content=f"Discovered {len(apis)} endpoints for service '{service}': "
                        + ", ".join(a["api_id"] for a in apis)
            )
        ],
    }


# ═══════════════════════════════════════════════════════════════
# NODE: generate
# ═══════════════════════════════════════════════════════════════

def node_generate(state: AgentState) -> dict:
    """Use LLM to generate comprehensive test cases for all APIs."""
    console.print(Panel("[bold blue]PHASE 2 — GENERATE[/bold blue]", expand=False))

    apis = state["apis"]
    test_cases: list[TestCase] = generate_test_cases_tool.invoke({"apis": apis})
    console.print(f"  generated [green]{len(test_cases)}[/green] test cases")

    return {
        "generated_tests": test_cases,
        "phase": "execute",
        "messages": [
            AIMessage(content=f"Generated {len(test_cases)} test cases for {len(apis)} APIs.")
        ],
    }


# ═══════════════════════════════════════════════════════════════
# NODE: execute
# ═══════════════════════════════════════════════════════════════

def node_execute(state: AgentState) -> dict:
    """Run all test cases against the live server.

    Executors are resolved dynamically from the registry in
    agent/executor/__init__.py — no hardcoded transport names here.
    Adding a new transport only requires dropping a new *_executor.py file.
    """
    console.print(Panel("[bold blue]PHASE 3 — EXECUTE[/bold blue]", expand=False))

    from agent import executor as executor_registry

    # Group test cases by transport (e.g. "http", "grpc", "websocket", ...)
    groups: dict[str, list[TestCase]] = {}
    for tc in state["generated_tests"]:
        groups.setdefault(tc["transport"], []).append(tc)

    console.print(
        "  " + "  ".join(
            f"{t.upper()} tests: [cyan]{len(cases)}[/cyan]"
            for t, cases in groups.items()
        )
    )

    results: list[TestResult] = []

    for transport, cases in groups.items():
        try:
            executor = executor_registry.get(transport)
        except KeyError as exc:
            console.print(f"  [yellow]⚠ {exc}[/yellow]")
            continue

        batch_results = executor.run_batch(cases)
        results.extend(batch_results)
        passed = sum(1 for r in batch_results if r["status"] == "passed")
        console.print(f"  {transport.upper()}: {passed}/{len(batch_results)} passed")

    return {
        "results": results,
        "phase": "validate",
        "messages": [
            AIMessage(
                content=f"Executed {len(results)} tests. "
                        f"Passed: {sum(1 for r in results if r['status']=='passed')}."
            )
        ],
    }


# ═══════════════════════════════════════════════════════════════
# NODE: validate
# ═══════════════════════════════════════════════════════════════

def node_validate(state: AgentState) -> dict:
    """Schema-validate response bodies and update result statuses."""
    console.print(Panel("[bold blue]PHASE 4 — VALIDATE[/bold blue]", expand=False))

    validated_results: list[TestResult] = schema_validate_tool.invoke({
        "results": state["results"],
        "generated_tests": state["generated_tests"],
    })

    schema_failures = sum(1 for r in validated_results if r["validation_errors"])
    if schema_failures:
        console.print(f"  [yellow]{schema_failures} schema validation failures[/yellow]")
    else:
        console.print("  [green]All schema validations passed[/green]")

    return {
        "results": validated_results,
        "phase": "report",
        "messages": [
            AIMessage(content=f"Schema-validated {len(validated_results)} results.")
        ],
    }


# ═══════════════════════════════════════════════════════════════
# NODE: report
# ═══════════════════════════════════════════════════════════════

def node_report(state: AgentState) -> dict:
    """Build and persist the final report."""
    console.print(Panel("[bold blue]PHASE 5 — REPORT[/bold blue]", expand=False))

    output = report_builder_tool.invoke({
        "service": state["service"],
        "apis": state["apis"],
        "results": state["results"],
    })

    report = output["report"]
    paths = output["report_paths"]

    console.print(f"  total_apis:  [bold]{report['total_apis']}[/bold]")
    console.print(f"  total_tests: [bold]{report['total_tests']}[/bold]")
    console.print(f"  passed:      [bold green]{report['passed']}[/bold green]")
    console.print(f"  failed:      [bold red]{report['failed']}[/bold red]")
    console.print(f"  pass_rate:   [bold]{report['pass_rate_pct']}%[/bold]")
    if paths:
        console.print(f"  reports saved: {paths}")

    return {
        "report": report,
        "report_paths": paths,
        "metrics": {
            "total_tests": report["total_tests"],
            "passed": report["passed"],
            "failed": report["failed"],
        },
        "phase": "done",
        "messages": [AIMessage(content=f"Report complete. {report['passed']}/{report['total_tests']} passed.")],
    }


# ═══════════════════════════════════════════════════════════════
# ROUTING
# ═══════════════════════════════════════════════════════════════

def route(state: AgentState) -> str:
    """Route to the next node based on current phase."""
    p = state.get("phase", "discover")
    if p == "done" or state.get("error"):
        return END
    return p


# ═══════════════════════════════════════════════════════════════
# GRAPH CONSTRUCTION
# ═══════════════════════════════════════════════════════════════

def build_graph() -> Any:
    g = StateGraph(AgentState)

    g.add_node("discover", node_discover)
    g.add_node("generate", node_generate)
    g.add_node("execute", node_execute)
    g.add_node("validate", node_validate)
    g.add_node("report", node_report)

    g.set_entry_point("discover")

    # Each node routes via phase field
    for node in ("discover", "generate", "execute", "validate", "report"):
        g.add_conditional_edges(node, route)

    return g.compile()
