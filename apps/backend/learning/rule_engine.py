"""
RuleEngine — extrahiert, verwaltet und wendet Lernregeln an.
Konflikte werden dem Nutzer zur manuellen Entscheidung vorgelegt.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from ..database import add_learned_rule, get_active_rules, update_rule_confidence, deactivate_rule, get_engine
except ImportError:
    from database import add_learned_rule, get_active_rules, update_rule_confidence, deactivate_rule, get_engine

from sqlalchemy import text

_CONFIDENCE_THRESHOLD = 50
_MAX_RULES_IN_PROMPT = 10


class RuleEngine:
    """Lernt aus Nutzer-Korrekturen und generalisiert Regeln."""

    def __init__(self, llm_router=None, provider: str = "groq",
                 model: str = "llama-3.3-70b-versatile") -> None:
        self._router = llm_router
        self._provider = provider
        self._model = model

    def extract_from_correction(
        self,
        original_response: str,
        correction: str,
        user_id: str,
        api_key: str | None = None,
    ) -> str | None:
        if not self._router or not api_key:
            rule_text = f"Nutzer bevorzugt: {correction[:200]}"
            add_learned_rule(user_id=user_id, rule_text=rule_text, source="correction", confidence=60)
            return rule_text

        prompt = (
            f"Ursprüngliche Antwort:\n{original_response[:500]}\n\n"
            f"Nutzer-Korrektur:\n{correction[:300]}\n\n"
            "Formuliere eine allgemeine Regel (1 Satz, Deutsch) die AILIZA beim nächsten Mal besser macht. "
            "Nur die Regel, kein Kommentar:"
        )
        try:
            resp = self._router.chat(
                message=prompt, provider=self._provider, model=self._model,
                api_key=api_key, system_prompt="Du extrahierst allgemeine Regeln aus Korrekturen.",
            )
            rule_text = resp.text.strip() if not resp.error else f"Bevorzuge: {correction[:100]}"
        except Exception:
            rule_text = f"Bevorzuge: {correction[:100]}"

        rule_id = add_learned_rule(user_id=user_id, rule_text=rule_text, source="correction", confidence=70)
        self._check_conflicts(user_id, rule_id, rule_text)
        return rule_text

    def apply_rules_to_prompt(self, base_prompt: str, user_id: str) -> str:
        rules = get_active_rules(user_id)
        applicable = [r for r in rules if r.get("confidence", 0) >= _CONFIDENCE_THRESHOLD][:_MAX_RULES_IN_PROMPT]
        if not applicable:
            return base_prompt
        rule_text = "\n".join(f"- {r['rule_text']}" for r in applicable)
        return base_prompt + f"\n\nGELERNTE NUTZER-PRÄFERENZEN:\n{rule_text}"

    def positive_feedback(self, user_id: str, rule_text: str, delta: int = 10) -> None:
        engine = get_engine()
        with engine.begin() as c:
            c.execute(
                text("UPDATE learned_rules SET confidence=MIN(100, confidence+:d), "
                     "apply_count=apply_count+1, last_applied_at=datetime('now') "
                     "WHERE user_id=:uid AND rule_text=:rt AND active=1"),
                {"d": delta, "uid": user_id, "rt": rule_text},
            )

    def negative_feedback(self, user_id: str, rule_text: str, delta: int = 20) -> None:
        engine = get_engine()
        with engine.begin() as c:
            c.execute(
                text("UPDATE learned_rules SET confidence=MAX(0, confidence-:d) "
                     "WHERE user_id=:uid AND rule_text=:rt AND active=1"),
                {"d": delta, "uid": user_id, "rt": rule_text},
            )

    def get_conflicts(self, user_id: str) -> list[dict[str, Any]]:
        engine = get_engine()
        with engine.connect() as c:
            rows = c.execute(
                text("SELECT id, rule_text, conflicts_with FROM learned_rules "
                     "WHERE user_id=:uid AND active=1 AND conflicts_with IS NOT NULL AND conflicts_with!='null'"),
                {"uid": user_id},
            ).fetchall()
        return [{"id": r[0], "rule_text": r[1], "conflicts_with": json.loads(r[2] or "[]")} for r in rows]

    def resolve_conflict(self, user_id: str, keep_id: int, discard_id: int) -> None:
        deactivate_rule(discard_id)
        engine = get_engine()
        with engine.begin() as c:
            c.execute(text("UPDATE learned_rules SET conflicts_with=NULL WHERE id=:id"), {"id": keep_id})

    def _check_conflicts(self, user_id: str, new_id: int, new_rule: str) -> None:
        rules = get_active_rules(user_id)
        opposites = [
            ("kurz", "ausführlich"), ("formell", "informell"),
            ("deutsch", "englisch"), ("sie-form", "du-form"),
        ]
        for rule in rules:
            if rule.get("id") == new_id:
                continue
            existing = rule["rule_text"].lower()
            new_lower = new_rule.lower()
            for a, b in opposites:
                if (a in new_lower and b in existing) or (b in new_lower and a in existing):
                    engine = get_engine()
                    with engine.begin() as c:
                        c.execute(
                            text("UPDATE learned_rules SET conflicts_with=:cw WHERE id=:id"),
                            {"cw": json.dumps([rule["id"]]), "id": new_id},
                        )
                    return
