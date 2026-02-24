"""
agent/main.py
Entry point for the Spec-Driven API Testing Agent.

Usage:
    python -m agent.main
    python -m agent.main --guideline path/to/guideline_testing.yaml
    python -m agent.main --service account --scenario "basic validation"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.rule import Rule

from agent.config import Settings, load_guideline
from agent.graph import build_graph
from agent.state import AgentState

console = Console()


def run_service(service_name: str, scenario: str, cfg: Settings) -> dict:
    """Run the full agent pipeline for one service and return the final report."""
    console.print(Rule(f"[bold]Service: {service_name.upper()} | Scenario: {scenario}[/bold]"))

    graph = build_graph()

    initial_state: AgentState = {
        "messages": [
            HumanMessage(
                content=(
                    f"Test the '{service_name}' service. Scenario: {scenario}. "
                    "PLAN → GENERATE → EXECUTE → VALIDATE → REPORT."
                )
            )
        ],
        "service": service_name,
        "scenario": scenario,
        "spec_path": None,
        "spec_type": None,
        "raw_spec": None,
        "apis": [],
        "generated_tests": [],
        "results": [],
        "metrics": {},
        "report": None,
        "report_paths": [],
        "phase": "discover",
        "error": None,
    }

    final_state: AgentState = graph.invoke(initial_state)

    if final_state.get("error"):
        console.print(f"[bold red]AGENT ERROR:[/bold red] {final_state['error']}")

    return final_state.get("report") or {}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Spec-Driven API Testing Agent"
    )
    parser.add_argument(
        "--guideline",
        default=None,
        help="Path to guideline_testing.yaml (default: project root)",
    )
    parser.add_argument("--service", default=None, help="Override service name")
    parser.add_argument("--scenario", default=None, help="Override scenario")
    args = parser.parse_args(argv)

    # Load config
    guideline = load_guideline(args.guideline) if args.guideline else load_guideline()
    cfg = Settings(guideline)

    # Determine what to test
    services: list[dict]
    if args.service:
        services = [{"service": args.service, "scenario": args.scenario or "basic validation"}]
    else:
        services = cfg.test_services

    if not services:
        console.print("[yellow]No test_services defined in guideline. Exiting.[/yellow]")
        sys.exit(0)

    all_reports: list[dict] = []
    for entry in services:
        svc_name = entry["service"]
        scenario = entry.get("scenario", "basic validation")
        report = run_service(svc_name, scenario, cfg)
        all_reports.append(report)

    # Print consolidated summary
    console.print()
    console.print(Rule("[bold green]ALL SERVICES COMPLETE[/bold green]"))
    for r in all_reports:
        if r:
            console.print(
                f"  [bold]{r.get('service','?')}[/bold]: "
                f"{r.get('passed',0)}/{r.get('total_tests',0)} passed "
                f"({r.get('pass_rate_pct',0)}%)"
            )


if __name__ == "__main__":
    main()
