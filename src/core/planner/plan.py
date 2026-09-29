from __future__ import annotations

import json
from typing import Any, Dict, List

from src.core.planner.models import Plan, PlanStep


class PlanParser:
    """Parse planner output into a structured Plan object."""

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> Plan:
        steps = []
        for item in data.get("steps", []):
            steps.append(
                PlanStep(
                    tool=item.get("tool", ""),
                    args=item.get("args", {}),
                    timeout=item.get("timeout"),
                    retries=item.get("retries", 0),
                )
            )
        return Plan(goal=data.get("goal", ""), steps=steps)

    @staticmethod
    def from_json(payload: str) -> Plan:
        return PlanParser.from_dict(json.loads(payload))
