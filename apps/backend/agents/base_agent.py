"""
BaseSpecializedAgent — ABC für alle spezialisierten Sub-Agenten.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSpecializedAgent(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> list[str]: ...

    def get_system_prompt_extension(self) -> str:
        return ""

    def get_tools(self) -> list[dict[str, Any]]:
        return []

    def get_pii_types(self) -> list[str]:
        return []

    def requires_approval(self, tool_name: str, args: dict) -> bool:
        return False

    @abstractmethod
    def handle_tool_call(self, tool_name: str, args: dict[str, Any], user_id: str) -> dict[str, Any]: ...

    def matches_task(self, task: str) -> float:
        task_lower = task.lower()
        score = sum(0.3 for cap in self.capabilities if cap.lower() in task_lower)
        return min(1.0, score)
