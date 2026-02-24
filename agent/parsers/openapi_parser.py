"""
agent/parsers/openapi_parser.py
Converts an OpenAPI 3.x YAML/JSON spec into a list of APIEndpoint dicts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from agent.state import APIEndpoint


def load_spec(path: str | Path) -> dict:
    """Load YAML or JSON OpenAPI spec from disk."""
    p = Path(path)
    with open(p) as f:
        if p.suffix in {".yaml", ".yml"}:
            return yaml.safe_load(f)
        return json.load(f)


def _resolve_ref(spec: dict, ref: str) -> dict:
    """Resolve a simple local $ref like '#/components/schemas/Foo'."""
    if not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    node: Any = spec
    for p in parts:
        node = node.get(p, {})
    return node or {}


def _resolve_schema(spec: dict, schema: dict | None) -> dict | None:
    """Follow $ref one level deep and return the concrete schema."""
    if not schema:
        return None
    if "$ref" in schema:
        return _resolve_ref(spec, schema["$ref"])
    return schema


def _extract_response_schemas(spec: dict, responses: dict) -> dict:
    """Return {status_code: schema} for each response in an operation."""
    result: dict[str, dict] = {}
    for code, resp in (responses or {}).items():
        content = resp.get("content", {})
        for media_type, media in content.items():
            schema = _resolve_schema(spec, media.get("schema"))
            if schema:
                result[str(code)] = schema
                break
    return result


def parse(spec_path: str | Path) -> list[APIEndpoint]:
    """Parse an OpenAPI 3.x spec and return a list of APIEndpoint objects."""
    spec = load_spec(spec_path)
    endpoints: list[APIEndpoint] = []

    for path, path_item in (spec.get("paths") or {}).items():
        for method in ["get", "post", "put", "patch", "delete"]:
            operation: dict | None = path_item.get(method)
            if not operation:
                continue

            # --- Parameters (path, query, header) ---
            raw_params: list[dict] = []
            for p in operation.get("parameters", []) + path_item.get("parameters", []):
                if "$ref" in p:
                    p = _resolve_ref(spec, p["$ref"])
                raw_params.append({
                    "name": p.get("name", ""),
                    "in": p.get("in", ""),
                    "required": p.get("required", False),
                    "schema": _resolve_schema(spec, p.get("schema")),
                    "description": p.get("description", ""),
                })

            # --- Request body schema ---
            request_schema: dict | None = None
            req_body = operation.get("requestBody")
            if req_body:
                content = req_body.get("content", {})
                for _media_type, media in content.items():
                    request_schema = _resolve_schema(spec, media.get("schema"))
                    break

            api_id = f"{method.upper()} {path}"

            endpoints.append(APIEndpoint(
                api_id=api_id,
                method=method.upper(),
                path=path,
                operation_id=operation.get("operationId", api_id),
                summary=operation.get("summary", ""),
                parameters=raw_params,
                request_schema=request_schema,
                response_schemas=_extract_response_schemas(spec, operation.get("responses", {})),
                tags=operation.get("tags", []),
                source="openapi",
            ))

    return endpoints
