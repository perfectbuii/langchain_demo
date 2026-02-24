"""
agent/config.py – loads guideline_testing.yaml and propagates settings.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parent.parent  # repo root


def load_guideline(path: str | Path | None = None) -> dict:
    """Load and return the parsed guideline_testing.yaml."""
    p = Path(path) if path else _ROOT / "guideline_testing.yaml"
    with open(p) as f:
        return yaml.safe_load(f)


class Settings:
    """Central settings object populated from guideline + env vars."""

    def __init__(self, guideline: dict | None = None):
        if guideline is None:
            guideline = load_guideline()

        self.guideline = guideline

        agent_cfg = guideline.get("agent", {})
        exec_cfg = guideline.get("execution", {})
        report_cfg = guideline.get("report", {})

        # LLM
        self.llm_model: str = agent_cfg.get("model", "gpt-4o")
        self.llm_temperature: float = float(agent_cfg.get("temperature", 0))
        self.max_iterations: int = int(agent_cfg.get("max_iterations", 30))
        self.google_api_key: str = os.getenv("GOOGLE_API_KEY", "")

        # Execution
        self.base_url_http: str = exec_cfg.get("base_url_http", "http://localhost:8080")
        self.base_url_grpc: str = exec_cfg.get("base_url_grpc", "localhost:9090")
        self.timeout_seconds: int = int(exec_cfg.get("timeout_seconds", 10))
        self.retry_attempts: int = int(exec_cfg.get("retry_attempts", 2))
        self.concurrency: int = int(exec_cfg.get("concurrency", 4))

        # Paths  (single source of truth for both OpenAPI specs & proto files)
        self.specs_dir: Path = _ROOT / "source_of_truth"
        self.proto_dir: Path = _ROOT / "source_of_truth"
        self.report_dir: Path = _ROOT / report_cfg.get("output_dir", "reports")
        self.report_formats: list[str] = report_cfg.get("formats", ["json"])
        self.save_report: bool = bool(report_cfg.get("save_to_file", True))

        # Services to test
        self.test_services: list[dict] = guideline.get("test_services", [])


# Singleton used throughout the project
settings = Settings()
