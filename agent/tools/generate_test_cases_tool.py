"""
agent/tools/generate_test_cases_tool.py
Tool: generate_test_cases_tool
Uses LLM reasoning to generate a comprehensive set of TestCase dicts
for every API endpoint provided.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.config import settings
from agent.state import APIEndpoint, TestCase


_SYSTEM = """\
You are an expert QA engineer specialising in API testing.
Given a list of API endpoints with their schemas, you generate a comprehensive
set of test cases covering:

1. Positive cases
   - Valid request with all required + optional fields
   - Valid request with required fields only
   - Boundary values (min, max)

2. Negative cases
   - Missing required field (one per required field)
   - Wrong type for a field
   - Invalid format (e.g. bad email, bad UUID)
   - Empty string for required string fields
   - Boundary violations (length, value)

3. Schema validation
   - Verify 2xx response matches the declared response schema

Rules:
- Return ONLY a valid JSON array of test case objects — no prose, no markdown fences.
- Every object must have these exact keys:
    test_id, api_id, test_type, description,
    method, path, headers, path_params, query_params, body,
    expected_status, expected_schema, transport

- test_id: unique short string like "tc_001"
- test_type: "positive" | "negative" | "schema"
- transport: "http" if method is GET/POST/PUT/PATCH/DELETE, else "grpc"
- headers: always include {{"Content-Type": "application/json"}} for POST/PUT
- expected_schema: the JSON schema object the response must match, or null
- For path parameters, put a concrete example value in path_params
  AND substitute it into `path` (e.g. /accounts/{{id}} → /accounts/abc123)
- For gRPC endpoints, set method="GRPC", transport="grpc", body = the request message fields

STRICT JSON RULES — violations will cause a crash:
- ALL values must be valid JSON literals (strings, numbers, booleans, null, arrays, objects).
- Do NOT use any JavaScript expressions such as .repeat(), .toString(), template literals, etc.
- For boundary test strings, write out the literal value directly, e.g. "aaaaaaaaaa" (10 a's).
- The output must parse cleanly with Python's json.loads() with zero modifications.
"""

_HUMAN = """\
Generate test cases for the following API endpoints:

{apis_json}

JSON array only, no markdown fences:
"""


def _fix_js_expressions(text: str) -> str:
    """Replace JS expressions like "a".repeat(101) with their literal JSON equivalents."""
    # "char".repeat(n)  →  "charcharchar..."
    def expand_repeat(m: re.Match) -> str:
        char_val = m.group(1)
        count = int(m.group(2))
        return f'"{char_val * count}"'

    return re.sub(r'"([^"]*)"\.repeat\((\d+)\)', expand_repeat, text)


def _extract_json_array(text: str) -> list[dict]:
    """
    Robustly extract a JSON array from raw LLM output.
    Tries in order:
      1. Strip markdown fences and json.loads()
      2. Find outermost [...] and json.loads()
      3. Use json_repair as a last resort
    """
    from json_repair import repair_json  # type: ignore

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    cleaned = re.sub(r"```(?:json)?", "", text).strip()

    # Fix JS expressions before trying to parse
    cleaned = _fix_js_expressions(cleaned)

    # Attempt 1: direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Attempt 2: find outermost [ ... ]
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        try:
            result = json.loads(candidate)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            # Attempt 3: json_repair on the candidate slice
            try:
                result = json.loads(repair_json(candidate))
                if isinstance(result, list):
                    return result
            except Exception:
                pass

    # Attempt 4: json_repair on the whole text
    try:
        result = json.loads(repair_json(cleaned))
        if isinstance(result, list):
            return result
    except Exception:
        pass

    raise ValueError(
        f"Could not parse LLM output as a JSON array.\n"
        f"Raw output (first 500 chars):\n{text[:500]}"
    )


@tool
def generate_test_cases_tool(apis: list[dict]) -> list[dict]:
    """
    LLM-driven test case generation for a list of APIEndpoint dicts.

    Args:
        apis: List of APIEndpoint dicts (output of discover_apis_tool).

    Returns:
        List of TestCase dicts ready for execution.
    """
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        google_api_key=settings.google_api_key,
    )

    prompt = ChatPromptTemplate.from_messages(
        [("system", _SYSTEM), ("human", _HUMAN)]
    )

    chain = prompt | llm | StrOutputParser()

    text: str = chain.invoke({"apis_json": json.dumps(apis, indent=2)})
    raw: list[dict] = _extract_json_array(text)

    # Ensure every test case has a unique test_id
    seen_ids: set[str] = set()
    normalised: list[TestCase] = []
    for i, tc in enumerate(raw):
        tid = tc.get("test_id") or f"tc_{i+1:03d}"
        while tid in seen_ids:
            tid = f"tc_{uuid.uuid4().hex[:6]}"
        seen_ids.add(tid)

        normalised.append(
            TestCase(
                test_id=tid,
                api_id=tc.get("api_id", ""),
                test_type=tc.get("test_type", "positive"),
                description=tc.get("description", ""),
                method=tc.get("method", "GET"),
                path=tc.get("path", "/"),
                headers=tc.get("headers") or {},
                path_params=tc.get("path_params") or {},
                query_params=tc.get("query_params") or {},
                body=tc.get("body"),
                expected_status=int(tc.get("expected_status", 200)),
                expected_schema=tc.get("expected_schema"),
                transport=tc.get("transport", "http"),
            )
        )

    return normalised
