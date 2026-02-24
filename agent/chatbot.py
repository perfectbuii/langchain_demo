"""
agent/chatbot.py
Interactive chatbot that replaces the config YAML.

On startup, ALL available APIs are loaded from spec files and
injected into the system prompt.  The LLM reasons about them
during conversation and selects the right ones itself — no
separate discovery round-trip.

Flow:  chat  →  confirm  →  run
"""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table

from agent.config import settings
from agent.chat_state import ChatIntent, ChatState

console = Console()

# ═══════════════════════════════════════════════════════════════
# STARTUP — load all APIs from every spec
# ═══════════════════════════════════════════════════════════════

def _load_all_apis() -> dict[str, list[dict]]:
    """Return {service_name: [APIEndpoint, ...]} for every service found in
    source_of_truth/.  Called once at startup."""
    from agent.tools.load_spec_tool import load_spec_tool
    from agent.tools.discover_apis_tool import discover_apis_tool

    service_apis: dict[str, list[dict]] = {}
    stems: set[str] = set()
    for p in settings.specs_dir.iterdir():
        if p.suffix in {".yaml", ".yml", ".json", ".proto"}:
            stems.add(p.stem)

    for stem in sorted(stems):
        spec_info = load_spec_tool.invoke({"service_name": stem})
        if spec_info["spec_type"] == "none":
            continue
        apis = discover_apis_tool.invoke({
            "openapi_path": spec_info["openapi_path"],
            "proto_path":   spec_info["proto_path"],
        })
        if apis:
            service_apis[stem] = apis

    return service_apis


def _build_api_catalogue_text(service_apis: dict[str, list[dict]]) -> str:
    """Render the full API catalogue as a compact text block for the prompt."""
    lines: list[str] = []
    for service, apis in service_apis.items():
        lines.append(f"Service: {service}")
        for api in apis:
            summary = api.get("summary") or api.get("operation_id") or ""
            lines.append(f"  {api['api_id']}  \u2014  {summary}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

_CHATBOT_SYSTEM = """\
You are a friendly API testing assistant. You help users choose which APIs
to test, then hand off to an automated testing pipeline.

Here is the COMPLETE catalogue of available services and their APIs:

{api_catalogue}

Your goals:
1. Greet the user and briefly explain what you can do.
2. Understand what the user wants to test (be specific about which API endpoints).
3. Ask clarifying questions if the request is ambiguous.
4. Once you are confident, OUTPUT a JSON block at the END of your reply:

```intent
{{
  "service": "<service name from catalogue>",
  "user_request": "<concise description of what to test>",
  "api_ids": [<list of exact api_id strings from the catalogue>],
  "confidence": <0.0-1.0>
}}
```

Rules:
- ONLY emit the ```intent block when confidence >= 0.85.
- `api_ids` MUST be exact strings from the catalogue above \u2014 do NOT invent new ones.
- If the user wants to test everything, include all api_ids for that service.
- After the user types yes/confirm, reply with exactly: CONFIRMED
- If the user says no or wants to change, drop the intent block and clarify.
"""

# ═══════════════════════════════════════════════════════════════
# INTENT PARSING
# ═══════════════════════════════════════════════════════════════

_INTENT_FENCED_RE = re.compile(r"```intent\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_INTENT_BARE_RE   = re.compile(r"(\{[^{}]*\"service\"[^{}]*\})", re.DOTALL)
_CONFIRMED_RE     = re.compile(r"^\s*CONFIRMED\s*$", re.IGNORECASE)


def _extract_intent(text: str) -> "ChatIntent | None":
    for pattern in (_INTENT_FENCED_RE, _INTENT_BARE_RE):
        m = pattern.search(text)
        if m:
            try:
                data = json.loads(m.group(1))
                service = data.get("service")
                confidence = float(data.get("confidence", 0.0))
                if service and confidence >= 0.85:
                    return ChatIntent(
                        service=service,
                        user_request=data.get("user_request"),
                        confidence=confidence,
                        api_ids=data.get("api_ids") or [],
                    )
            except (json.JSONDecodeError, ValueError):
                continue
    return None


def _strip_intent_block(text: str) -> str:
    text = _INTENT_FENCED_RE.sub("", text)
    text = _INTENT_BARE_RE.sub("", text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════
# CHATBOT SESSION
# ═══════════════════════════════════════════════════════════════

class ChatbotSession:
    """Phases: chat -> confirm -> run -> done.
    The LLM sees the full API catalogue from message 1 and picks
    api_ids during conversation — no extra round-trips."""

    def __init__(self) -> None:
        console.print("[dim]Loading API catalogue from specs\u2026[/dim]")
        self.service_apis = _load_all_apis()
        self.api_catalogue_text = _build_api_catalogue_text(self.service_apis)

        self.llm = ChatGoogleGenerativeAI(
            model=settings.llm_model,
            temperature=0.2,
            google_api_key=settings.google_api_key,
        )

        self.state: ChatState = {
            "messages": [],
            "available_services": list(self.service_apis.keys()),
            "intent": None,
            "discovered_apis": [],
            "selected_api_ids": [],
            "confirmed": None,
            "test_report": None,
            "report_paths": [],
            "phase": "chat",
            "error": None,
        }

        self._prompt = ChatPromptTemplate.from_messages([
            ("system", _CHATBOT_SYSTEM),
            MessagesPlaceholder(variable_name="messages"),
        ])
        self._chain = self._prompt | self.llm | StrOutputParser()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> str:
        self.state["messages"] = [HumanMessage(content="Hello!")]
        reply = self._llm()
        self.state["messages"].append(AIMessage(content=reply))
        return _strip_intent_block(reply)

    def process(self, user_input: str) -> "tuple[str, str]":
        """Returns (display_text, next_phase)."""
        if self.state["phase"] == "confirm":
            return self._handle_confirmation(user_input)

        self.state["messages"].append(HumanMessage(content=user_input))
        reply = self._llm()
        self.state["messages"].append(AIMessage(content=reply))

        if _CONFIRMED_RE.match(reply) and self.state.get("intent"):
            self.state["phase"] = "run"
            self.state["confirmed"] = True
            return "Starting the test run now\u2026 \U0001f680", "run"

        intent = _extract_intent(reply)
        display = _strip_intent_block(reply)

        if intent:
            all_ids = {
                a["api_id"]
                for apis in self.service_apis.values()
                for a in apis
            }
            valid = [i for i in (intent.get("api_ids") or []) if i in all_ids]
            if not valid:
                valid = [a["api_id"] for a in self.service_apis.get(intent["service"], [])]
            intent["api_ids"] = valid

            self.state["intent"] = intent
            self.state["selected_api_ids"] = valid
            self.state["discovered_apis"] = self.service_apis.get(intent["service"], [])
            self.state["phase"] = "confirm"
            return display, "confirm"

        return display, "chat"

    def run_tests(self) -> "tuple[dict, list[str]]":
        from agent.main import run_service
        intent = self.state["intent"]
        assert intent
        report = run_service(intent["service"], api_filter=self.state["selected_api_ids"] or None)
        self.state["test_report"] = report
        self.state["report_paths"] = report.get("report_paths", [])
        self.state["phase"] = "done"
        return report, self.state["report_paths"]

    def reset(self) -> None:
        """Reset for another test run, keeping conversation history."""
        self.state["phase"] = "chat"
        self.state["intent"] = None
        self.state["selected_api_ids"] = []
        self.state["discovered_apis"] = []
        self.state["confirmed"] = None
        self.state["test_report"] = None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _llm(self) -> str:
        return self._chain.invoke({
            "api_catalogue": self.api_catalogue_text,
            "messages": list(self.state["messages"]),
        })

    def _handle_confirmation(self, user_input: str) -> "tuple[str, str]":
        lowered = user_input.strip().lower()
        yes_words = {"yes", "y", "yep", "yeah", "sure", "ok", "okay", "go", "run", "confirm", "proceed"}
        no_words  = {"no", "n", "nope", "stop", "cancel", "change", "back", "wrong", "modify"}

        if any(w in lowered for w in yes_words) and not any(w in lowered for w in no_words):
            self.state["confirmed"] = True
            self.state["phase"] = "run"
            return "Starting the test run now\u2026 \U0001f680", "run"

        self.reset()
        self.state["messages"].append(HumanMessage(content=f"I want to change: {user_input}"))
        reply = self._llm()
        self.state["messages"].append(AIMessage(content=reply))
        return _strip_intent_block(reply), "chat"


# ═══════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════

def _print_bot(text: str) -> None:
    if text:
        console.print(Panel(Markdown(text), title="[bold cyan]\U0001f916 Assistant[/bold cyan]", border_style="cyan"))


def _print_plan(intent: "ChatIntent", apis: list[dict]) -> None:
    summary_table = Table(title="\U0001f4cb Testing Plan", show_header=False, border_style="green")
    summary_table.add_column("", style="bold")
    summary_table.add_column("")
    summary_table.add_row("Service",    intent.get("service") or "?")
    summary_table.add_row("Request",    intent.get("user_request") or "(all APIs)")
    summary_table.add_row("Confidence", f"{intent.get('confidence', 0)*100:.0f}%")
    console.print(summary_table)

    api_table = Table(title="\U0001f50d APIs to Test", border_style="blue", show_lines=True)
    api_table.add_column("#", style="dim", width=3)
    api_table.add_column("API ID", style="bold")
    api_table.add_column("Summary")
    for i, api in enumerate(apis, 1):
        api_table.add_row(str(i), api["api_id"], api.get("summary") or api.get("operation_id") or "")
    console.print(api_table)


def _print_results(report: dict) -> None:
    console.print()
    console.rule("[bold green]TEST RESULTS[/bold green]")
    t = Table(show_header=True, border_style="green")
    t.add_column("Metric", style="bold")
    t.add_column("Value")
    t.add_row("Total APIs",            str(report.get("total_apis", "?")))
    t.add_row("Total Tests",           str(report.get("total_tests", "?")))
    t.add_row("[green]Passed[/green]", f"[green]{report.get('passed', 0)}[/green]")
    t.add_row("[red]Failed[/red]",     f"[red]{report.get('failed', 0)}[/red]")
    t.add_row("Pass Rate",             f"{report.get('pass_rate_pct', 0)}%")
    t.add_row("Avg Latency",           f"{report.get('avg_latency_ms', 0)} ms")
    console.print(t)
    for p in report.get("report_paths") or []:
        console.print(f"  \U0001f4c4 {p}")


# ═══════════════════════════════════════════════════════════════
# MAIN REPL
# ═══════════════════════════════════════════════════════════════

def run_chatbot() -> None:
    console.print()
    console.rule("[bold magenta]\U0001f9ea API Testing Chatbot[/bold magenta]")
    console.print("[dim]Describe what you want to test in plain English. Type exit to quit.[/dim]\n")

    session = ChatbotSession()
    _print_bot(session.start())

    while True:
        try:
            user_input = Prompt.ask("\n[bold yellow]You[/bold yellow]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye![/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "bye", "q"}:
            console.print("[dim]Goodbye! \U0001f389[/dim]")
            break

        reply, phase = session.process(user_input)
        _print_bot(reply)

        if phase == "confirm":
            selected = [
                a for a in session.state["discovered_apis"]
                if a["api_id"] in session.state["selected_api_ids"]
            ]
            _print_plan(session.state["intent"], selected)
            console.print(
                "\n[bold green]Ready![/bold green] "
                "Type [bold]yes[/bold] to run, or tell me what to change."
            )

        elif phase == "run":
            console.print()
            console.rule("[bold magenta]\U0001f680 Running Test Pipeline[/bold magenta]")
            console.print()
            try:
                report, paths = session.run_tests()
            except Exception:
                import traceback
                console.print("[bold red]Test run failed:[/bold red]")
                console.print(traceback.format_exc())
                session.reset()
                _print_bot("Something went wrong. What would you like to do?")
                continue

            _print_results({**report, "report_paths": paths})

            console.print()
            again = Prompt.ask(
                "[bold yellow]Test something else?[/bold yellow] (yes/no)", default="no"
            ).strip().lower()

            if again in {"yes", "y"}:
                session.reset()
                _print_bot("Sure! What would you like to test next?")
            else:
                console.print("[dim]All done. Goodbye! \U0001f389[/dim]")
                break


if __name__ == "__main__":
    run_chatbot()
