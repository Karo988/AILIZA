"""
AgentRegistry — verwaltet und routet zu spezialisierten Sub-Agenten.
"""

from __future__ import annotations

from typing import Any

try:
    from .base_agent import BaseSpecializedAgent
except ImportError:
    from base_agent import BaseSpecializedAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseSpecializedAgent] = {}

    def register(self, agent: BaseSpecializedAgent) -> None:
        self._agents[agent.name] = agent

    def list_agents(self) -> list[dict[str, Any]]:
        return [{"name": a.name, "description": a.description, "capabilities": a.capabilities}
                for a in self._agents.values()]

    def get(self, name: str) -> BaseSpecializedAgent | None:
        return self._agents.get(name)

    def route(self, task: str) -> BaseSpecializedAgent | None:
        best_agent = None
        best_score = 0.3
        for agent in self._agents.values():
            score = agent.matches_task(task)
            if score > best_score:
                best_score = score
                best_agent = agent
        return best_agent

    def route_with_llm(self, task: str, llm_router, provider: str, model: str, api_key: str) -> BaseSpecializedAgent | None:
        if not self._agents:
            return None
        agent_list = "\n".join(f"- {a.name}: {a.description}" for a in self._agents.values())
        prompt = (f"Aufgabe: {task}\n\nVerfügbare Agenten:\n{agent_list}\n\n"
                  "Welcher Agent ist am besten geeignet? Antworte nur mit dem Agent-Namen oder 'keiner':")
        try:
            resp = llm_router.chat(message=prompt, provider=provider, model=model, api_key=api_key,
                                   system_prompt="Du wählst den passenden Agenten für eine Aufgabe.")
            name = resp.text.strip().lower()
            return self._agents.get(name)
        except Exception:
            return self.route(task)


_registry = AgentRegistry()


def get_registry() -> AgentRegistry:
    return _registry
