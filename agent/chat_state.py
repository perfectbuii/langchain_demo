"""
agent/chat_state.py – state carried through the chatbot LangGraph.
"""

from __future__ import annotations

from typing import Annotated, Any, Sequence
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ChatIntent(TypedDict, total=False):
    """Structured intent extracted from the conversation."""
    service: str | None           # resolved service name (e.g. "account")
    user_request: str | None      # raw natural-language description of what to test
    confidence: float             # 0.0 – 1.0 how confident we are about the intent
    api_ids: list[str]            # exact api_id strings the LLM picked from the catalogue


class ChatState(TypedDict):
    """Full state for the chatbot graph."""

    # Conversation messages (accumulates with every turn)
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # Available services discovered from spec files
    available_services: list[str]

    # Extracted intent from the conversation
    intent: ChatIntent | None

    # APIs discovered from the chosen service spec
    discovered_apis: list[dict]

    # API IDs the LLM selected to actually test
    selected_api_ids: list[str]

    # Whether the user confirmed they want to run the tests
    confirmed: bool | None        # None = not yet asked, True/False = answered

    # Test run result (populated after tests complete)
    test_report: dict | None
    report_paths: list[str]

    # Control flow
    phase: str   # "chat" | "confirm" | "run" | "done"
    error: str | None
