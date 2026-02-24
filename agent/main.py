"""
agent/main.py
Entry point for the Spec-Driven API Testing Agent.

Usage:
    python -m agent.main    # launches the interactive chatbot
    python -m agent.chatbot # same, directly
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.rule import Rule

from agent.config import Settings
from agent.graph import build_graph
from agent.state import AgentState

console = Console()


def run_service(service_name: str, api_filter: list[str] | None = None) -> dict:
    """Run the full agent pipeline for one service and return the final report."""
    console.print(Rule(f"[bold]Service: {service_name.upper()}[/bold]"))

    graph = build_graph()

    initial_state: AgentState = {
        "messages": [
            HumanMessage(
                content=(
                    f"Test the '{service_name}' service. "
                    "PLAN → GENERATE → EXECUTE → VALIDATE → REPORT."
                )
            )
        ],
        "service": service_name,
        "spec_path": None,
        "spec_type": None,
        "raw_spec": None,
        "apis": [],
        "api_filter": api_filter,
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

    report = final_state.get("report") or {}
    report["report_paths"] = final_state.get("report_paths") or []
    return report


def main() -> None:
    from agent.chatbot import run_chatbot
    run_chatbot()


if __name__ == "__main__":
    main()
