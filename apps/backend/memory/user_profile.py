"""
Nutzerprofile — DSGVO Art. 17 (Löschen), Art. 20 (Portabilität), Art. 15 (Auskunft).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

try:
    from ..database import (
        get_or_create_user_profile,
        update_user_profile,
        complete_onboarding,
        delete_user_data,
        get_active_rules,
    )
except ImportError:
    from database import (
        get_or_create_user_profile,
        update_user_profile,
        complete_onboarding,
        delete_user_data,
        get_active_rules,
    )


class UserProfile:
    """Zugriffs-Wrapper für Nutzerprofile."""

    def get(self, user_id: str) -> dict[str, Any]:
        return get_or_create_user_profile(user_id)

    def update(self, user_id: str, **fields) -> None:
        update_user_profile(user_id, **fields)

    def finish_onboarding(
        self,
        user_id: str,
        display_name: str,
        company: str = "",
        language: str = "de",
    ) -> None:
        update_user_profile(
            user_id,
            display_name=display_name,
            company=company,
            language=language,
        )
        complete_onboarding(user_id)

    def get_preference(self, user_id: str, key: str, default: Any = None) -> Any:
        profile = get_or_create_user_profile(user_id)
        prefs = profile.get("preferences") or {}
        if isinstance(prefs, str):
            try:
                prefs = json.loads(prefs)
            except Exception:
                prefs = {}
        return prefs.get(key, default)

    def set_preference(self, user_id: str, key: str, value: Any) -> None:
        profile = get_or_create_user_profile(user_id)
        prefs = profile.get("preferences") or {}
        if isinstance(prefs, str):
            try:
                prefs = json.loads(prefs)
            except Exception:
                prefs = {}
        prefs[key] = value
        update_user_profile(user_id, preferences=json.dumps(prefs))

    def record_consent(
        self,
        user_id: str,
        action: str,
        purpose: str,
        legal_basis: str,
        granted: bool,
    ) -> None:
        profile = get_or_create_user_profile(user_id)
        records = profile.get("consent_records") or []
        if isinstance(records, str):
            try:
                records = json.loads(records)
            except Exception:
                records = []
        records.append({
            "action": action,
            "purpose": purpose,
            "legal_basis": legal_basis,
            "granted": granted,
            "timestamp": datetime.utcnow().isoformat(),
        })
        records = records[-200:]
        update_user_profile(user_id, consent_records=json.dumps(records))

    def export(self, user_id: str) -> dict[str, Any]:
        """Art. 20 — Datenportabilität."""
        profile = get_or_create_user_profile(user_id)
        rules = get_active_rules(user_id)
        return {
            "user_id": user_id,
            "profile": profile,
            "learned_rules": rules,
            "exported_at": datetime.utcnow().isoformat(),
        }

    def delete(self, user_id: str) -> dict[str, int]:
        """Art. 17 — Vollständige Löschung aller personenbezogenen Daten."""
        return delete_user_data(user_id)

    def build_system_prompt_additions(self, user_id: str) -> str:
        profile = get_or_create_user_profile(user_id)
        parts = []
        if profile.get("display_name"):
            parts.append(f"Der Nutzer heißt {profile['display_name']}.")
        if profile.get("company"):
            parts.append(f"Er/sie arbeitet bei {profile['company']}.")
        lang = profile.get("language", "de")
        if lang != "de":
            lang_names = {"en": "Englisch", "fr": "Französisch", "es": "Spanisch", "it": "Italienisch"}
            parts.append(f"Antworte auf {lang_names.get(lang, lang)}.")
        prefs = profile.get("preferences") or {}
        if isinstance(prefs, str):
            try:
                prefs = json.loads(prefs)
            except Exception:
                prefs = {}
        if prefs.get("formal_address"):
            parts.append("Verwende immer die Siezen (Sie-Form).")
        if prefs.get("brief_answers"):
            parts.append("Halte Antworten kurz und prägnant.")
        return "\n".join(parts)
