"""
agent/executor/__init__.py
Auto-discovery registry: any file named <transport>_executor.py
in this folder is automatically registered as the executor for that transport.

To add a new transport (e.g. websocket):
  1. Create agent/executor/websocket_executor.py
  2. Implement run_batch(test_cases: list[TestCase]) -> list[TestResult]
  3. Done — no changes needed anywhere else.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

# Transport name → executor module, e.g. {"http": <module rest_executor>, "grpc": <module grpc_executor>}
_registry: dict[str, ModuleType] = {}


def _build_registry() -> None:
    executor_dir = Path(__file__).parent
    for path in executor_dir.glob("*_executor.py"):
        # "rest_executor.py" → transport = "http"
        # "grpc_executor.py" → transport = "grpc"
        stem = path.stem  # e.g. "rest_executor"
        transport = stem.replace("_executor", "")  # e.g. "rest"

        # Map conventional aliases so filenames stay descriptive
        _ALIASES = {"rest": "http"}
        transport = _ALIASES.get(transport, transport)

        module = importlib.import_module(f"agent.executor.{stem}")
        _registry[transport] = module


_build_registry()


def get(transport: str) -> ModuleType:
    """Return the executor module for the given transport name.

    Raises KeyError with a helpful message if none is registered.
    """
    if transport not in _registry:
        available = ", ".join(sorted(_registry))
        raise KeyError(
            f"No executor registered for transport '{transport}'. "
            f"Available: {available}. "
            f"Add agent/executor/{transport}_executor.py to support it."
        )
    return _registry[transport]


def registered_transports() -> list[str]:
    """Return all currently registered transport names."""
    return sorted(_registry.keys())
