"""
agent/tools/schema_validate_tool.py
Tool: schema_validate_tool
Validates a response body against a JSON Schema and enriches TestResult objects.
"""

from __future__ import annotations

from typing import Any

import jsonschema
from langchain_core.tools import tool

from agent.state import TestResult


def _validate(instance: Any, schema: dict) -> list[str]:
    """Return a list of validation error messages (empty = valid).

    Returns an empty list (no errors) if the schema itself is invalid
    (e.g. contains non-standard types like 'Account', or unresolvable $refs)
    so that a bad LLM-generated schema never crashes the pipeline.
    """
    try:
        validator = jsonschema.Draft7Validator(schema)
        return [e.message for e in validator.iter_errors(instance)]
    except (
        jsonschema.exceptions.UnknownType,
        jsonschema.exceptions.RefResolutionError,
        Exception,  # catch-all for any other jsonschema internal error
    ):
        return []


@tool
def schema_validate_tool(results: list[dict], generated_tests: list[dict]) -> list[dict]:
    """
    Post-process execution results: validate each response body against the
    expected_schema declared in the corresponding TestCase.

    Args:
        results:          List of TestResult dicts from execution.
        generated_tests:  List of TestCase dicts (used to look up expected_schema).

    Returns:
        Updated list of TestResult dicts with validation_errors populated.
    """
    # Build a quick lookup from test_id → expected_schema
    schema_map: dict[str, dict | None] = {
        tc["test_id"]: tc.get("expected_schema")
        for tc in generated_tests
    }

    updated: list[TestResult] = []
    for raw in results:
        result: TestResult = TestResult(**{k: raw.get(k) for k in TestResult.__annotations__})  # type: ignore[misc]

        schema = schema_map.get(result["test_id"])
        if schema and result["response_body"] is not None:
            errors = _validate(result["response_body"], schema)
            result["validation_errors"] = errors
            # Downgrade status if schema validation fails and test was initially "passed"
            if errors and result["status"] == "passed":
                result["status"] = "failed"

        updated.append(result)

    return updated
