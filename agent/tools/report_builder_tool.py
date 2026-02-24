"""
agent/tools/report_builder_tool.py
Tool: report_builder_tool
Aggregates TestResult objects into the final report dict and
persists JSON / HTML / Markdown artefacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from agent.config import settings


def _compute_metrics(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "passed")
    failed = total - passed
    latencies = [r.get("latency_ms", 0) for r in results if r.get("latency_ms")]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    by_type: dict[str, dict] = {}
    for r in results:
        t = r.get("test_type", "unknown")
        if t not in by_type:
            by_type[t] = {"total": 0, "passed": 0, "failed": 0}
        by_type[t]["total"] += 1
        if r.get("status") == "passed":
            by_type[t]["passed"] += 1
        else:
            by_type[t]["failed"] += 1

    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
        "avg_latency_ms": avg_latency,
        "by_type": by_type,
    }


@tool
def report_builder_tool(
    service: str,
    apis: list[dict],
    results: list[dict],
) -> dict:
    """
    Build and persist the test report.

    Args:
        service:  Service name (e.g. "account").
        apis:     List of APIEndpoint dicts that were tested.
        results:  List of TestResult dicts after schema validation.

    Returns:
        Final report dict + list of file paths where reports were saved.
    """
    from agent.report.json_report import build as build_json
    from agent.report.html_report import build as build_html
    from agent.report.markdown_report import build as build_md

    metrics = _compute_metrics(results)

    report: dict = {
        "service": service,
        "total_apis": len(apis),
        "total_tests": metrics["total_tests"],
        "passed": metrics["passed"],
        "failed": metrics["failed"],
        "pass_rate_pct": metrics["pass_rate_pct"],
        "avg_latency_ms": metrics["avg_latency_ms"],
        "metrics_by_type": metrics["by_type"],
        "details": results,
    }

    saved_paths: list[str] = []

    if settings.save_report:
        settings.report_dir.mkdir(parents=True, exist_ok=True)
        base = settings.report_dir / service

        if "json" in settings.report_formats:
            p = Path(f"{base}_report.json")
            p.write_text(build_json(report))
            saved_paths.append(str(p))

        if "html" in settings.report_formats:
            p = Path(f"{base}_report.html")
            p.write_text(build_html(report))
            saved_paths.append(str(p))

        if "markdown" in settings.report_formats:
            p = Path(f"{base}_report.md")
            p.write_text(build_md(report))
            saved_paths.append(str(p))

    return {"report": report, "report_paths": saved_paths}
