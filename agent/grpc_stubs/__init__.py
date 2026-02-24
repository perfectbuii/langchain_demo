"""
agent/grpc_stubs/__init__.py
Auto-discovery registry for gRPC stubs.

On import, scans this directory for every *_pb2_grpc.py file, imports it,
finds all Stub classes via their DESCRIPTOR, and registers:

    service_name (e.g. "AccountService")
        → { "pb2": <pb2 module>, "stub_cls": <Stub class> }

So any executor or tool just does:
    entry = grpc_stubs.get("AccountService")
    entry["stub_cls"](channel)           # instantiate the stub
    entry["pb2"].CreateAccountRequest     # access message classes

Adding a new service only requires dropping new *_pb2.py / *_pb2_grpc.py
files into this directory — no other code changes needed.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

# service_name → {"pb2": module, "stub_cls": type, "pb2_grpc": module}
_registry: dict[str, dict[str, Any]] = {}


def _build_registry() -> None:
    stubs_dir = Path(__file__).parent

    for grpc_path in stubs_dir.glob("*_pb2_grpc.py"):
        stem = grpc_path.stem                        # e.g. "account_pb2_grpc"
        prefix = stem.replace("_pb2_grpc", "")       # e.g. "account"
        pkg_base = f"agent.grpc_stubs.{prefix}"

        try:
            pb2_grpc = importlib.import_module(f"{pkg_base}_pb2_grpc")
            pb2 = importlib.import_module(f"{pkg_base}_pb2")
        except ImportError:
            continue

        # Service descriptors live on the *pb2* file descriptor, not the stub class.
        # pb2.DESCRIPTOR is google.protobuf.descriptor.FileDescriptor containing
        # .services_by_name: {service_name: ServiceDescriptor}
        file_desc = getattr(pb2, "DESCRIPTOR", None)
        if file_desc is None:
            continue

        for service_name, _svc_desc in file_desc.services_by_name.items():
            # Conventional stub class name: AccountService → AccountServiceStub
            stub_cls = getattr(pb2_grpc, f"{service_name}Stub", None)
            if stub_cls is None:
                continue

            _registry[service_name] = {
                "pb2": pb2,
                "pb2_grpc": pb2_grpc,
                "stub_cls": stub_cls,
            }


_build_registry()


def get(service_name: str) -> dict[str, Any]:
    """
    Return the registry entry for a service name.

    Args:
        service_name: e.g. "AccountService"

    Returns:
        Dict with keys: pb2, pb2_grpc, stub_cls

    Raises:
        KeyError if no stubs are registered for the service.
    """
    if service_name not in _registry:
        available = ", ".join(sorted(_registry)) or "(none)"
        raise KeyError(
            f"No gRPC stubs registered for service '{service_name}'. "
            f"Available: {available}. "
            f"Run `make proto` to generate stubs for new services."
        )
    return _registry[service_name]


def resolve_request_cls(service_name: str, method_name: str) -> type:
    """
    Resolve the protobuf request class for a given service + method
    using the pb2 file descriptor — no hardcoded names.

    Strategy:
      pb2.DESCRIPTOR.services_by_name[service_name]
        .methods_by_name[method_name].input_type.name
      → getattr(pb2, input_type_name)

    Fallback:
      pb2.<MethodName>Request  (conventional proto naming)
    """
    entry = get(service_name)
    pb2 = entry["pb2"]

    input_type_name: str | None = None

    file_desc = getattr(pb2, "DESCRIPTOR", None)
    if file_desc:
        svc_desc = file_desc.services_by_name.get(service_name)
        if svc_desc:
            method_desc = svc_desc.methods_by_name.get(method_name)
            if method_desc:
                input_type_name = method_desc.input_type.name  # e.g. "CreateAccountRequest"

    if input_type_name is None:
        # Conventional fallback: CreateAccount → CreateAccountRequest
        input_type_name = f"{method_name}Request"

    req_cls = getattr(pb2, input_type_name, None)
    if req_cls is None:
        raise AttributeError(
            f"Could not find request class '{input_type_name}' in {pb2.__name__}. "
            f"Descriptor lookup and conventional fallback both failed."
        )
    return req_cls


def registered_services() -> list[str]:
    """Return all currently registered gRPC service names."""
    return sorted(_registry.keys())
