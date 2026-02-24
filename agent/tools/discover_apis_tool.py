"""
agent/tools/discover_apis_tool.py
Tool: discover_apis_tool
Parses spec paths discovered by load_spec_tool and returns a
structured list of APIEndpoint dicts.
"""

from __future__ import annotations

from langchain_core.tools import tool

from agent.parsers import openapi_parser, proto_parser
from agent.state import APIEndpoint


@tool
def discover_apis_tool(openapi_path: str | None, proto_path: str | None) -> list[dict]:
    """
    Parse OpenAPI and/or proto spec files and return all API endpoints.

    Args:
        openapi_path: Absolute path to the OpenAPI YAML/JSON file (or None).
        proto_path:   Absolute path to the .proto file (or None).

    Returns:
        List of APIEndpoint dicts describing every API operation found.
    """
    endpoints: list[APIEndpoint] = []

    if openapi_path:
        endpoints.extend(openapi_parser.parse(openapi_path))

    if proto_path:
        endpoints.extend(proto_parser.parse(proto_path))

    # Deduplicate by api_id (openapi wins over proto for same path)
    seen: dict[str, APIEndpoint] = {}
    for ep in endpoints:
        if ep["api_id"] not in seen:
            seen[ep["api_id"]] = ep

    return list(seen.values())
