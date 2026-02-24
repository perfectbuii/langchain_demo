"""agent/report/json_report.py"""
from __future__ import annotations
import json


def build(report: dict) -> str:
    return json.dumps(report, indent=2, default=str)
