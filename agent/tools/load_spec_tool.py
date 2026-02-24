"""
agent/tools/load_spec_tool.py
Tool: load_spec_tool
Scans specs/ and proto/ for a service by name, returns the raw spec content.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from langchain_core.tools import tool

from agent.config import settings


@tool
def load_spec_tool(service_name: str) -> dict:
    """
    Load the spec (OpenAPI YAML or proto) for the given service name.

    Scans specs/ directory for <service_name>.yaml / .json and
    proto/ directory for <service_name>.proto.

    Returns a dict with keys:
      - openapi_path:  str | None
      - proto_path:    str | None
      - openapi_raw:   dict | None   (parsed YAML/JSON)
      - proto_text:    str | None    (raw proto text)
      - spec_type:     "openapi" | "proto" | "both" | "none"
    """
    name = service_name.lower()
    result: dict = {
        "openapi_path": None,
        "proto_path": None,
        "openapi_raw": None,
        "proto_text": None,
        "spec_type": "none",
    }

    # ── OpenAPI ──────────────────────────────────────────────────────────────
    for ext in [".yaml", ".yml", ".json"]:
        candidate = settings.specs_dir / f"{name}{ext}"
        if candidate.exists():
            result["openapi_path"] = str(candidate)
            with open(candidate) as f:
                result["openapi_raw"] = (
                    yaml.safe_load(f) if ext in {".yaml", ".yml"} else json.load(f)
                )
            break

    # ── Proto ────────────────────────────────────────────────────────────────
    for candidate in settings.proto_dir.glob(f"{name}*.proto"):
        result["proto_path"] = str(candidate)
        result["proto_text"] = candidate.read_text()
        break

    # ── Spec type ────────────────────────────────────────────────────────────
    has_oa = result["openapi_path"] is not None
    has_pr = result["proto_path"] is not None

    if has_oa and has_pr:
        result["spec_type"] = "both"
    elif has_oa:
        result["spec_type"] = "openapi"
    elif has_pr:
        result["spec_type"] = "proto"

    return result
