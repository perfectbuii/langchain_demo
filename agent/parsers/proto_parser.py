"""
agent/parsers/proto_parser.py
Extracts gRPC service / method information from a .proto file using regex.
Produces APIEndpoint entries with source="proto".
"""

from __future__ import annotations

import re
from pathlib import Path

from agent.state import APIEndpoint


_SERVICE_RE = re.compile(r"service\s+(\w+)\s*\{([^}]*)\}", re.DOTALL)
_RPC_RE = re.compile(
    r"rpc\s+(\w+)\s*\(\s*(\w+)\s*\)\s*returns\s*\(\s*(\w+)\s*\)", re.DOTALL
)
_MESSAGE_RE = re.compile(r"message\s+(\w+)\s*\{([^}]*)\}", re.DOTALL)
_FIELD_RE = re.compile(r"(?:optional\s+|repeated\s+)?(\w+)\s+(\w+)\s*=\s*(\d+)\s*;")


def _parse_fields(body: str) -> list[dict]:
    """Extract field definitions from a message body."""
    fields = []
    for match in _FIELD_RE.finditer(body):
        fields.append(
            {
                "type": match.group(1),
                "name": match.group(2),
                "number": int(match.group(3)),
                "repeated": "repeated" in match.string[match.start() - 20 : match.start()],
            }
        )
    return fields


def parse(proto_path: str | Path) -> list[APIEndpoint]:
    """Parse a .proto file and return a list of APIEndpoint objects."""
    text = Path(proto_path).read_text()

    # Build a messages catalogue: {name: [fields]}
    messages: dict[str, list[dict]] = {}
    for m in _MESSAGE_RE.finditer(text):
        msg_name = m.group(1)
        messages[msg_name] = _parse_fields(m.group(2))

    endpoints: list[APIEndpoint] = []

    for svc_match in _SERVICE_RE.finditer(text):
        svc_name = svc_match.group(1)
        svc_body = svc_match.group(2)

        for rpc_match in _RPC_RE.finditer(svc_body):
            method_name = rpc_match.group(1)
            request_msg = rpc_match.group(2)
            response_msg = rpc_match.group(3)

            # Map message fields → lightweight "schema"
            req_fields = messages.get(request_msg, [])
            resp_fields = messages.get(response_msg, [])

            request_schema = (
                {
                    "type": "object",
                    "message": request_msg,
                    "properties": {f["name"]: {"type": f["type"]} for f in req_fields},
                }
                if req_fields
                else None
            )

            resp_schema = (
                {
                    "type": "object",
                    "message": response_msg,
                    "properties": {f["name"]: {"type": f["type"]} for f in resp_fields},
                }
                if resp_fields
                else {}
            )

            api_id = f"GRPC {svc_name}/{method_name}"

            endpoints.append(
                APIEndpoint(
                    api_id=api_id,
                    method="GRPC",
                    path=f"/{svc_name}/{method_name}",
                    operation_id=f"{svc_name}.{method_name}",
                    summary=f"gRPC {svc_name}.{method_name}",
                    parameters=[],
                    request_schema=request_schema,
                    response_schemas={"0": resp_schema},
                    tags=[svc_name],
                    source="proto",
                )
            )

    return endpoints
