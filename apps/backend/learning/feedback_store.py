"""
Feedback-Speicher — Bewertungen und Tool-Erfolgsquoten.
"""

from __future__ import annotations

from typing import Any

try:
    from ..database import record_feedback, get_engine
except ImportError:
    from database import record_feedback, get_engine

from sqlalchemy import text


class FeedbackStore:
    """Speichert und aggregiert Nutzerfeedback."""

    def add(
        self,
        message_id: int,
        user_id: str,
        rating: int,
        correction: str = "",
        tool_name: str = "",
        was_helpful: bool | None = None,
    ) -> int:
        if was_helpful is None:
            was_helpful = rating >= 4
        return record_feedback(
            message_id=message_id,
            user_id=user_id,
            rating=rating,
            correction=correction,
            tool_name=tool_name,
            was_helpful=was_helpful,
        )

    def get_corrections(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        engine = get_engine()
        with engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT message_id, correction, created_at FROM feedback "
                    "WHERE user_id=:uid AND correction!='' ORDER BY created_at DESC LIMIT :lim"
                ),
                {"uid": user_id, "lim": limit},
            ).fetchall()
        return [{"message_id": r[0], "correction": r[1], "created_at": r[2]} for r in rows]

    def tool_success_rate(self, tool_name: str, user_id: str | None = None) -> float:
        engine = get_engine()
        params: dict = {"tool": tool_name}
        where_user = "AND user_id=:uid" if user_id else ""
        if user_id:
            params["uid"] = user_id
        with engine.connect() as c:
            row = c.execute(
                text(
                    f"SELECT AVG(CASE WHEN was_helpful THEN 1.0 ELSE 0.0 END) "
                    f"FROM feedback WHERE tool_name=:tool {where_user}"
                ),
                params,
            ).fetchone()
        val = row[0] if row and row[0] is not None else 0.75
        return float(val)

    def recent_ratings(self, user_id: str, limit: int = 10) -> list[int]:
        engine = get_engine()
        with engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT rating FROM feedback WHERE user_id=:uid "
                    "ORDER BY created_at DESC LIMIT :lim"
                ),
                {"uid": user_id, "lim": limit},
            ).fetchall()
        return [r[0] for r in rows]
