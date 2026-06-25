"""
PreferenceLearner — kombiniert alle Lernquellen zu einem angepassten System-Prompt.
"""

from __future__ import annotations

try:
    from .rule_engine import RuleEngine
    from .skill_memory import SkillMemory, _classify_task
    from ..memory.user_profile import UserProfile
except ImportError:
    from rule_engine import RuleEngine
    from skill_memory import SkillMemory, _classify_task
    from memory.user_profile import UserProfile


class PreferenceLearner:
    def __init__(self, llm_router=None, provider: str = "groq", model: str = "llama-3.3-70b-versatile") -> None:
        self._rule_engine = RuleEngine(llm_router, provider, model)
        self._skill_memory = SkillMemory()
        self._profile = UserProfile()

    def adapt_system_prompt(self, base_prompt: str, user_id: str, task: str) -> str:
        result = base_prompt
        profile_additions = self._profile.build_system_prompt_additions(user_id)
        if profile_additions:
            result += f"\n\nNUTZER-KONTEXT:\n{profile_additions}"
        result = self._rule_engine.apply_rules_to_prompt(result, user_id)
        hint = self._skill_memory.hint_for_llm(task)
        if hint:
            result += f"\n\n{hint}"
        return result

    def record_correction(self, original: str, correction: str, user_id: str, api_key: str | None = None) -> str | None:
        return self._rule_engine.extract_from_correction(original, correction, user_id, api_key)

    def record_task_success(self, task: str, approach: str) -> None:
        self._skill_memory.record_success(_classify_task(task), approach)

    def record_task_failure(self, task: str, approach: str) -> None:
        self._skill_memory.record_failure(_classify_task(task), approach)

    def get_rule_engine(self) -> RuleEngine:
        return self._rule_engine
