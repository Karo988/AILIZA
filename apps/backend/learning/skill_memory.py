"""
Skill-Memory — merkt sich welche Ansätze für welche Aufgabentypen funktionieren.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from ..database import get_engine
except ImportError:
    from database import get_engine

from sqlalchemy import text


class SkillMemory:
    def record_success(self, task_type: str, approach: str, context: dict | None = None) -> None:
        self._upsert(task_type, approach_worked=approach, context=context, success=True)

    def record_failure(self, task_type: str, approach: str, context: dict | None = None) -> None:
        self._upsert(task_type, approach_failed=approach, context=context, success=False)

    def hint_for_llm(self, task: str) -> str:
        task_type = _classify_task(task)
        engine = get_engine()
        with engine.connect() as c:
            row = c.execute(
                text("SELECT approach_worked, approach_failed, success_count, fail_count "
                     "FROM skill_memory WHERE task_type=:tt ORDER BY last_updated DESC LIMIT 1"),
                {"tt": task_type},
            ).fetchone()
        if not row:
            return ""
        parts = []
        if row[0] and row[2] and row[2] > 0:
            parts.append(f"Hat bisher funktioniert: {row[0]}")
        if row[1] and row[3] and row[3] > 2:
            parts.append(f"Hat nicht funktioniert: {row[1]}")
        return f"[Skill-Hinweis für {task_type}] " + " | ".join(parts) if parts else ""

    def _upsert(self, task_type: str, approach_worked: str = "", approach_failed: str = "",
                context: dict | None = None, success: bool = True) -> None:
        engine = get_engine()
        ctx_json = json.dumps(context or {})
        with engine.begin() as c:
            existing = c.execute(
                text("SELECT id, success_count, fail_count FROM skill_memory WHERE task_type=:tt"),
                {"tt": task_type},
            ).fetchone()
            if existing:
                sc = (existing[1] or 0) + (1 if success else 0)
                fc = (existing[2] or 0) + (0 if success else 1)
                updates: dict[str, Any] = {"tt": task_type, "sc": sc, "fc": fc}
                set_parts = ["success_count=:sc", "fail_count=:fc", "last_updated=datetime('now')"]
                if approach_worked:
                    set_parts.append("approach_worked=:aw")
                    updates["aw"] = approach_worked
                if approach_failed:
                    set_parts.append("approach_failed=:af")
                    updates["af"] = approach_failed
                c.execute(text(f"UPDATE skill_memory SET {', '.join(set_parts)} WHERE task_type=:tt"), updates)
            else:
                c.execute(
                    text("INSERT INTO skill_memory "
                         "(task_type, approach_worked, approach_failed, context, success_count, fail_count, last_updated) "
                         "VALUES (:tt, :aw, :af, :ctx, :sc, :fc, datetime('now'))"),
                    {"tt": task_type, "aw": approach_worked, "af": approach_failed, "ctx": ctx_json,
                     "sc": 1 if success else 0, "fc": 0 if success else 1},
                )


def _classify_task(task: str) -> str:
    task_l = task.lower()
    if any(w in task_l for w in ["e-mail", "mail", "schreiben", "antwort"]):
        return "email"
    if any(w in task_l for w in ["zusammenfass", "analyse", "auswert"]):
        return "analysis"
    if any(w in task_l for w in ["übersetze", "translate", "übersetzung"]):
        return "translation"
    if any(w in task_l for w in ["rechnung", "buchhaltung", "beleg", "vat", "mwst"]):
        return "accounting"
    if any(w in task_l for w in ["termin", "datum", "kalender", "planen"]):
        return "scheduling"
    if any(w in task_l for w in ["präsentation", "folie", "slide"]):
        return "presentation"
    if any(w in task_l for w in ["suche", "recherche", "aktuel", "news"]):
        return "search"
    return "general"
