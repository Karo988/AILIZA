"""
PII Taxonomy: Central classification of sensitive data categories.

Status (Stand 2026-07-06): Bereit für kontrollierte Testumgebung und
Governance-Review. Nicht produktionsreif. Nicht zertifiziert.

Blocker:
- Nirgends in main.py eingebunden — nur von policy_engine.py (ebenfalls
  unverdrahtet) referenziert.
- Die tatsaechlich aktive PII-/Redaction-Klassifikation laeuft ueber
  apps/backend/governance/redaction_v2.py, eine unabhaengige, andere
  Implementierung mit ueberlappenden, aber nicht identischen Kategorien/
  Mustern. Verwechslungsgefahr.
- Keine Tests.

Aktives Gegenstueck: apps/backend/governance/redaction_v2.py
(RedactionEngineV2, NICHT diese Datei) — wird ueber
_governance_pre_check() in main.py tatsaechlich genutzt.
"""

class PIITaxonomy:
    """Central PII classification with 4-level hierarchy and detection patterns."""

    SECRETS = {
        "api_key_openai": {
            "action": "block",
            "label": "OpenAI API Key",
            "patterns": [r"\bsk-[\w\-]{15,}\b"],
        },
        "api_key_groq": {
            "action": "block",
            "label": "Groq API Key",
            "patterns": [r"\bgsk_[\w\-]{15,}\b"],
        },
        "api_key_anthropic": {
            "action": "block",
            "label": "Anthropic API Key",
            "patterns": [r"\bsk-ant-[\w\-]{15,}\b"],
        },
        "api_key_github": {
            "action": "block",
            "label": "GitHub Token",
            "patterns": [r"\b(?:ghp_[\w\-]{36,}|github_pat_[\w\-]{36,})\b"],
        },
        "jwt_token": {
            "action": "block",
            "label": "JWT Token",
            "patterns": [r"\beyJ[\w\-\.]+\b"],
        },
        "bearer_token": {
            "action": "block",
            "label": "Bearer Token",
            "patterns": [r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"],
        },
        "private_key": {
            "action": "block",
            "label": "Private Key",
            "patterns": [r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"],
        },
        "password_literal": {
            "action": "block",
            "label": "Password/Credentials",
            "patterns": [r"\b(?:passwort|password|kennwort|geheimwort|pin)\s*[:=]\s*\S+"],
        },
    }

    SPECIAL_CATEGORY = {
        "health": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Gesundheitsdaten",
            "patterns": [
                r"\b(?:diagnose|migräne|kopfschmerz|stressbelastung|krankschreibung|krankschreibungen)\b",
                r"\b(?:blutdruck|herzerkrankung|diabetes|krebs|hiv|aids)\b",
            ],
        },
        "religion": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Religiöse Überzeugung",
            "patterns": [
                r"\b(?:religion|muslimisch|islamisch|christlich|buddhistische|jüdisch|hinduistisch|atheist)\b",
            ],
        },
        "political_opinion": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Politische Überzeugung",
            "patterns": [
                r"\b(?:wahlbezirk|politische|spd|cdu|grüne|linke|afd|fdp|csu)\b",
            ],
        },
        "sexual_orientation": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Sexuelle Orientierung",
            "patterns": [
                r"\b(?:homosexuell|lesbisch|schwul|bisexuell|queer|transgender|transp\w*|sexuelle|sexualorientierung)\b",
            ],
        },
        "biometric": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Biometrische Daten",
            "patterns": [
                r"\b(?:fingerabdrück?(?:e)?|gesicht(?:serkennung|sanalyse|svergleich|sscan|smerkmale|sdaten|svermessung)?|retina(?:scan)?|biometrisch|biometrische)\b",
            ],
        },
        "criminal_offense": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Strafvollzug/Verurteilung",
            "patterns": [
                r"\b(?:strafvollzug|verurteilung|gerichtlich|gefängnis|straftat|strafregister)\b",
            ],
        },
        "trade_union": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Gewerkschaftsbezug",
            "patterns": [
                r"\b(?:gewerkschafts?|tarifvertrag|arbeitnehmervertretung|betriebsrat)\b",
            ],
        },
        "ethnic_origin": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Ethnische Herkunft",
            "patterns": [
                r"\b(?:herkunft|ethni|rasse|abstammung|nationalität)\b",
            ],
        },
        "genetic": {
            "action": "require_approval",
            "article": "Art. 9 DSGVO",
            "label": "Genetische Daten",
            "patterns": [
                r"\b(?:genetisch|gen(?:om)?sequenzierung|dna|chromosom)\b",
            ],
        },
    }

    HIGH_RISK_CONTEXTS = {
        "hr_health": {
            "action": "block",
            "reason_code": "HIGH_RISK_HR_HEALTH",
            "label": "HR/Bewerbung + Gesundheit",
            "hr_keywords": ["bewerbung", "bewerber", "kandidat", "lebenslauf", "recruiting", "einstellung", "personalentscheidung", "mitarbeiter"],
            "sensitive_keywords": ["gesundheit", "krankheit", "migräne", "psychisch", "depressiv"],
        },
        "hr_biometric": {
            "action": "block",
            "reason_code": "HIGH_RISK_HR_BIOMETRIC",
            "label": "HR/Bewerbung + Biometrie",
            "hr_keywords": ["bewerbung", "bewerber", "kandidat", "lebenslauf", "recruiting", "einstellung", "personalentscheidung", "mitarbeiter"],
            "sensitive_keywords": ["biometrisch", "gesichtserkennung", "fingerabdruck", "bewerbungsfoto"],
        },
        "hr_special_category": {
            "action": "block",
            "reason_code": "HIGH_RISK_HR_SPECIAL_CATEGORY",
            "label": "HR/Bewerbung + Art. 9 Daten",
            "hr_keywords": ["bewerbung", "bewerber", "kandidat", "lebenslauf", "recruiting", "einstellung", "personalentscheidung", "mitarbeiter"],
            "special_categories": ["health", "religion", "ethnic_origin", "political_opinion", "sexual_orientation", "biometric", "trade_union", "genetic"],
        },
        "automated_decision": {
            "action": "block",
            "reason_code": "HIGH_RISK_AUTOMATED_DECISION",
            "label": "Automatisierte Entscheidung über Person",
            "triggers": ["automatische empfehlung", "automatisierte entscheidung", "vollständig automatisch", "keine manuelle prüfung"],
            "impact": ["ablehnen", "kündigen", "nicht einstellen", "vorkasse", "score", "risiko", "bonität"],
        },
        "credit_scoring": {
            "action": "block",
            "reason_code": "HIGH_RISK_CREDIT_SCORING",
            "label": "Bonitätsbewertung/Kreditscoring",
            "keywords": ["bonitäts", "kreditwürdigkeit", "scoring", "creditworthiness", "kreditvergabe"],
        },
        "criminal_data": {
            "action": "block",
            "reason_code": "HIGH_RISK_CRIMINAL_DATA",
            "label": "Strafrechtliche Daten",
            "keywords": ["strafrechtlich", "verurteilung", "strafregister", "strafvollzug"],
        },
        "trade_union_data": {
            "action": "block",
            "reason_code": "HIGH_RISK_TRADE_UNION",
            "label": "Gewerkschaftsbezug",
            "keywords": ["gewerkschafts", "tarifvertrag", "arbeitnehmervertretung", "betriebsrat"],
        },
        "third_country_unclear": {
            "action": "conditional",  # depends on data_class
            "reason_code": "HIGH_RISK_THIRD_COUNTRY_UNCLEAR",
            "label": "Drittlandtransfer unklar",
            "countries": ["drittland", "drittlandübermittlung", "usa", "singapur", "außerhalb eu", "außerhalb der eu", "nicht-eu", "non-eu"],
            "unclear_markers": ["nicht geprüft", "unklar", "nicht abgeschlossen", "kein avv", "kein auftragsverarbeitungsvertrag", "standardbedingungen"],
        },
    }

    SENSITIVE = {
        "payment_card": {
            "action": "redact",
            "level": "high",
            "label": "Kreditkarte",
            "patterns": [r"\b(?:\d{4}[ \-]){3}\d{4}\b"],
        },
        "iban": {
            "action": "redact",
            "level": "high",
            "label": "IBAN",
            "patterns": [r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"],
        },
        "social_security": {
            "action": "redact",
            "level": "high",
            "label": "Versicherungsnummer",
            "patterns": [
                r"\b[A-Z]\d{8}[A-Z]\d{3}\b",
                r"\b(?:versicherungsnummer|versicherungs-?nr\.?)\s*[:№]?\s*[^\n]+?(?=\s*(?:\n|$))",
            ],
        },
        "salary": {
            "action": "redact",
            "level": "confidential",
            "label": "Gehalt/Lohn",
            "patterns": [
                r"\b(?:gehalt|lohn|brutto(?:gehalt|lohn)?|netto(?:gehalt|lohn)?|jahresgehalt|monatslohn|vergütung|honorar)\s*(?:[:=von]\s*)?(?:ca\.?\s*)?\d[\d.,:]*(?:\s+\d[\d.,:]*)*\s*(?:€|EUR|tsd\.?|k€)?"
            ],
        },
    }

    NORMAL = {
        "name": {
            "action": "redact",
            "level": "normal",
            "label": "Name",
            "patterns": [r"\b(?:Herr(?:n)?|Frau|Dr\.|Prof\.)\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+)*"],
        },
        "email": {
            "action": "redact",
            "level": "normal",
            "label": "E-Mail",
            "patterns": [r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"],
        },
        "phone": {
            "action": "redact",
            "level": "normal",
            "label": "Telefon",
            "patterns": [r"(?:\+49|0)[\s.-]?[1-9]\d{2,}[\s()\/.-]*\d{2,}(?![\d])"],
        },
        "address": {
            "action": "redact",
            "level": "normal",
            "label": "Adresse",
            "patterns": [
                r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß-]+(?:straße|strasse|gasse|weg|platz|allee|ring|damm|ufer|dom|berg|hof|markt|graben|garten|steig|stieg|anger)\s+\d+[a-z]?(?:\/\d+[a-z]?)?"
            ],
        },
        "postal_code": {
            "action": "redact",
            "level": "normal",
            "label": "PLZ",
            "patterns": [r"\b\d{5}\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\s-]{2,30}"],
        },
    }

    @classmethod
    def detect_secrets(cls, text: str) -> list[str]:
        """Detect all secret patterns in text. Returns list of secret type keys."""
        import re

        detected = []
        for secret_key, secret_def in cls.SECRETS.items():
            for pattern in secret_def["patterns"]:
                if re.search(pattern, text, re.IGNORECASE):
                    detected.append(secret_key)
                    break
        return detected

    @classmethod
    def detect_special_categories(cls, text: str) -> list[str]:
        """Detect DSGVO Art. 9 special categories. Returns list of category keys."""
        import re

        detected = []
        for cat_key, cat_def in cls.SPECIAL_CATEGORY.items():
            for pattern in cat_def["patterns"]:
                if re.search(pattern, text, re.IGNORECASE):
                    detected.append(cat_key)
                    break
        return detected

    @classmethod
    def get_all_categories(cls) -> dict:
        """Return all categories combined."""
        return {
            "secrets": cls.SECRETS,
            "special_category": cls.SPECIAL_CATEGORY,
            "sensitive": cls.SENSITIVE,
            "normal": cls.NORMAL,
        }

    @classmethod
    def get_category_label(cls, category_key: str) -> str:
        """Get human-readable label for a category key."""
        for level in [cls.SECRETS, cls.SPECIAL_CATEGORY, cls.SENSITIVE, cls.NORMAL]:
            if category_key in level:
                return level[category_key].get("label", category_key)
        return category_key

    @classmethod
    def detect_high_risk_context(cls, text: str, detected_special_categories: list[str] = None) -> list[tuple[str, str]]:
        """
        Detect high-risk contexts (combinations that require blockade).

        Returns list of (risk_code, risk_label) tuples.
        """
        import re

        text_lower = text.lower()
        risks = []

        # 1. HR + Health
        hr_found = any(kw in text_lower for kw in cls.HIGH_RISK_CONTEXTS["hr_health"]["hr_keywords"])
        health_found = any(kw in text_lower for kw in cls.HIGH_RISK_CONTEXTS["hr_health"]["sensitive_keywords"])
        if hr_found and health_found:
            risks.append(("HIGH_RISK_HR_HEALTH", cls.HIGH_RISK_CONTEXTS["hr_health"]["label"]))

        # 2. HR + Biometric
        hr_found = any(kw in text_lower for kw in cls.HIGH_RISK_CONTEXTS["hr_biometric"]["hr_keywords"])
        biometric_found = any(kw in text_lower for kw in cls.HIGH_RISK_CONTEXTS["hr_biometric"]["sensitive_keywords"])
        if hr_found and biometric_found:
            risks.append(("HIGH_RISK_HR_BIOMETRIC", cls.HIGH_RISK_CONTEXTS["hr_biometric"]["label"]))

        # 3. HR + Special Category (Art. 9)
        if detected_special_categories:
            hr_found = any(kw in text_lower for kw in cls.HIGH_RISK_CONTEXTS["hr_special_category"]["hr_keywords"])
            special_cat_found = any(cat in detected_special_categories for cat in cls.HIGH_RISK_CONTEXTS["hr_special_category"]["special_categories"])
            if hr_found and special_cat_found:
                risks.append(("HIGH_RISK_HR_SPECIAL_CATEGORY", cls.HIGH_RISK_CONTEXTS["hr_special_category"]["label"]))

        # 4. Automated Decision with Impact
        triggers_found = any(t in text_lower for t in cls.HIGH_RISK_CONTEXTS["automated_decision"]["triggers"])
        impact_found = any(i in text_lower for i in cls.HIGH_RISK_CONTEXTS["automated_decision"]["impact"])
        if triggers_found and impact_found:
            risks.append(("HIGH_RISK_AUTOMATED_DECISION", cls.HIGH_RISK_CONTEXTS["automated_decision"]["label"]))

        # 5. Credit Scoring
        if any(kw in text_lower for kw in cls.HIGH_RISK_CONTEXTS["credit_scoring"]["keywords"]):
            risks.append(("HIGH_RISK_CREDIT_SCORING", cls.HIGH_RISK_CONTEXTS["credit_scoring"]["label"]))

        # 6. Criminal Data
        if any(kw in text_lower for kw in cls.HIGH_RISK_CONTEXTS["criminal_data"]["keywords"]):
            risks.append(("HIGH_RISK_CRIMINAL_DATA", cls.HIGH_RISK_CONTEXTS["criminal_data"]["label"]))

        # 7. Trade Union Data
        if any(kw in text_lower for kw in cls.HIGH_RISK_CONTEXTS["trade_union_data"]["keywords"]):
            risks.append(("HIGH_RISK_TRADE_UNION", cls.HIGH_RISK_CONTEXTS["trade_union_data"]["label"]))

        # 8. Third Country Unclear (return info, decision in policy_engine based on data_class)
        country_found = any(c in text_lower for c in cls.HIGH_RISK_CONTEXTS["third_country_unclear"]["countries"])
        unclear_found = any(u in text_lower for u in cls.HIGH_RISK_CONTEXTS["third_country_unclear"]["unclear_markers"])
        if country_found and unclear_found:
            risks.append(("HIGH_RISK_THIRD_COUNTRY_UNCLEAR", cls.HIGH_RISK_CONTEXTS["third_country_unclear"]["label"]))

        return risks
