"""
PII Taxonomy: Central classification of sensitive data categories.

Status: Bereit für kontrollierte Testumgebung und Governance-Review.
Nicht produktionsreif. Nicht zertifiziert.
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
