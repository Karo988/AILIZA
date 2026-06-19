"""
AILIZA ProviderProfile-Register
================================
Zentrale Verwaltung der zugelassenen Provider.

Ein ProviderProfile beschreibt:
- Welcher Anbieter
- Welche Datenklassen verarbeitet werden duerfen
- Ob ein AVV vorliegt
- In welcher Region der Anbieter betreibt
- ob er fuer externe Calls aktiv ist

Hinweis: In Produktion kommen Profile aus der Datenbank/Admin-UI.
Hier ist ein statisches Standard-Register fuer das MVP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from ..governance.data_governance import DataClass
except ImportError:
    from governance.data_governance import DataClass


@dataclass
class ProviderProfile:
    provider_id: str
    name: str
    region: str               # z.B. "EU", "US"
    eu_certified: bool        # DSGVO Art. 46 Weg (SCC, Angemessenheitsbeschluss)
    avv_signed: bool          # Auftragsverarbeitungsvertrag vorhanden
    allowed_data_classes: list[DataClass]
    active: bool
    profile_version: str
    notes: str = ""

    def allows(self, data_class: DataClass) -> bool:
        return self.active and data_class in self.allowed_data_classes


# Statisches MVP-Register — in Produktion aus DB laden
_PROFILES: dict[str, ProviderProfile] = {
    "groq": ProviderProfile(
        provider_id="groq",
        name="Groq Cloud",
        region="US",
        eu_certified=False,
        avv_signed=False,   # AVV muss noch unterzeichnet werden
        allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
        active=True,
        profile_version="1.0.0",
        notes="US-Provider ohne AVV. Nur PUBLIC/INTERNAL bis AVV vorhanden.",
    ),
    "anthropic": ProviderProfile(
        provider_id="anthropic",
        name="Anthropic",
        region="US",
        eu_certified=False,
        avv_signed=False,
        allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
        active=True,
        profile_version="1.0.0",
        notes="US-Provider ohne AVV. Nur PUBLIC/INTERNAL bis AVV vorhanden.",
    ),
    "openrouter": ProviderProfile(
        provider_id="openrouter",
        name="OpenRouter",
        region="US",
        eu_certified=False,
        avv_signed=False,
        allowed_data_classes=[DataClass.PUBLIC],
        active=False,  # Standardmaessig inaktiv bis explizit konfiguriert
        profile_version="1.0.0",
        notes="Aggregator-API. Nur PUBLIC wenn aktiv.",
    ),
    "local": ProviderProfile(
        provider_id="local",
        name="Lokal (Fast-Path)",
        region="local",
        eu_certified=True,
        avv_signed=True,
        allowed_data_classes=list(DataClass),  # alle Klassen erlaubt lokal
        active=True,
        profile_version="1.0.0",
        notes="Lokale Verarbeitung, kein externer Datenabfluss.",
    ),
}


def get_profile(provider_id: str) -> ProviderProfile | None:
    return _PROFILES.get(provider_id)


def get_active_profiles() -> list[ProviderProfile]:
    return [p for p in _PROFILES.values() if p.active]


def is_data_class_allowed(provider_id: str, data_class: DataClass) -> bool:
    profile = get_profile(provider_id)
    if profile is None:
        return False
    return profile.allows(data_class)


def profile_to_dict(profile: ProviderProfile) -> dict[str, Any]:
    return {
        "provider_id": profile.provider_id,
        "name": profile.name,
        "region": profile.region,
        "eu_certified": profile.eu_certified,
        "avv_signed": profile.avv_signed,
        "allowed_data_classes": [c.value for c in profile.allowed_data_classes],
        "active": profile.active,
        "profile_version": profile.profile_version,
        "notes": profile.notes,
    }
