"""
AILIZA Dual-Gate PR-3 -- Spiegel-Linting
=========================================
Dieselben Regeln (aus RedactionEngineV2.PATTERNS -- NICHT dupliziert)
laufen getrennt auf der Ingress-Quelle (deterministisch, primaeres
Signal) UND dem Egress-Kandidaten (deterministisch, sekundaeres
Signal). Die risk_flags des Generators selbst sind nur ein tertiaeres,
NICHT entscheidendes Signal -- der Generator ist probabilistisch und
darf nicht die einzige zweite Instanz gegen sich selbst sein.

Asymmetrische Schwellen: zertifizierungskritische Kategorien (IBAN,
Kartendaten, Zugangsdaten/Secrets, amtliche IDs, Kinderdaten) duerfen
auf ein EINZELNES Signal blocken (False Negative ist hier schlimmer als
False Positive). Komfort-/Wording-Kategorien (Namen, Adresse, Referenz
etc.) brauchen BEIDE Signale.

Freigabe-Cockpit (minimal, PR-3): jede Kategorie hat einen Modus
"enforce" oder "shadow". Shadow-Regeln werden erkannt und geloggt,
blocken aber nie -- Rollout-Philosophie der Dual-Gate-v3-Spec
(componentwise, nie ein globaler Schalter). Unbekannte/neue Kategorien
defaulten fail-closed auf "shadow" (nie blockierend), nicht auf
"enforce" -- ein neues Muster darf nie ungeprueft live blocken.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    from .redaction_v2 import RedactionEngineV2
except ImportError:  # pragma: no cover
    from governance.redaction_v2 import RedactionEngineV2


# Reuse, keine Kopie -- T7 (test_reuses_redaction_v2_patterns_not_duplicated)
# prueft genau das.
_PATTERNS = RedactionEngineV2.PATTERNS

# Zertifizierungskritisch: einzelsignal_genuegt=True.
_CRITICAL_CATEGORIES = {
    "iban", "bic", "card", "card_cvv", "card_expiry", "credential",
    "secret_openai", "secret_groq", "secret_jwt", "secret_bearer",
    "official_id", "child_field",
}

# Freigabe-Cockpit: pro Kategorie enforce/shadow. Komfort-/Wording-Regeln
# starten in shadow (>= 1 Woche Beobachtung vor enforce, siehe Spec).
_RULE_MODE: dict[str, str] = {
    **{cat: "enforce" for cat in _CRITICAL_CATEGORIES},
    "reference": "enforce",  # Komfort-Kategorie, aber bereits beobachtet -> enforce
    "name": "shadow",
    "name_field": "shadow",
    "name_standalone_line": "shadow",
    "name_self_intro": "shadow",
    "name_signature": "shadow",
    "name_field_intl": "shadow",
    "name_context": "shadow",
    "email": "shadow",
    "birthdate": "shadow",
    "server_path": "shadow",
    "ip_address": "shadow",
    "gps_coords": "shadow",
    "device_id": "shadow",
    "financial_detail": "shadow",
    "financial_balance": "shadow",
    "financial_keyword": "shadow",
    "address": "shadow",
    "address_field_intl": "shadow",
    "postal_city": "shadow",
    "phone": "shadow",
}


def rule_mode(category: str) -> str:
    """Fail-closed: unbekannte/neue Kategorien sind IMMER 'shadow' (nie
    blockierend), nie 'enforce' per Default."""
    return _RULE_MODE.get(category, "shadow")


def einzelsignal_genuegt(category: str) -> bool:
    return category in _CRITICAL_CATEGORIES


@dataclass
class MirrorLintFinding:
    category: str
    in_ingress: bool
    in_egress: bool
    generator_flagged: bool = False

    @property
    def signal_count(self) -> int:
        return int(self.in_ingress) + int(self.in_egress)

    @property
    def should_block(self) -> bool:
        """Reine Signal-Schwelle (Ingress/Egress), IGNORIERT bewusst
        generator_flagged -- das Generator-Signal ist nur tertiaer/
        informativ, nie entscheidend (siehe Moduldoc)."""
        if einzelsignal_genuegt(self.category):
            return self.signal_count >= 1
        return self.signal_count >= 2

    @property
    def is_blocking(self) -> bool:
        """should_block UND die Kategorie steht auf 'enforce' -- Shadow-
        Regeln erkennen, aber blocken nie."""
        return self.should_block and rule_mode(self.category) == "enforce"


def run_mirror_lint(
    ingress_source: str,
    egress_candidate: str,
    generator_flagged_categories: set[str] | None = None,
) -> list[MirrorLintFinding]:
    generator_flagged_categories = generator_flagged_categories or set()
    findings: list[MirrorLintFinding] = []
    for category, pattern in _PATTERNS.items():
        in_ingress = bool(pattern.search(ingress_source or ""))
        in_egress = bool(pattern.search(egress_candidate or ""))
        if not (in_ingress or in_egress):
            continue
        findings.append(
            MirrorLintFinding(
                category=category,
                in_ingress=in_ingress,
                in_egress=in_egress,
                generator_flagged=category in generator_flagged_categories,
            )
        )
    return findings
