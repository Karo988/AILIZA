"""
Regressionsschutz: Strafrechtliche Daten muessen als Art. 10 DSGVO gelabelt
werden, nicht als Art. 9 DSGVO (eigene, striktere Rechtsgrundlage fuer
strafrechtliche Verurteilungen/Straftaten). Fehlklassifizierung als Art. 9
wurde in einer externen Compliance-Pruefung bemaengelt (Fix: 1b9acbe).
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.governance.redaction_v2 import RedactionEngineV2


def test_criminal_data_labeled_as_article_10_not_9():
    text = "Strafrechtliche Information: Verdacht wegen Betrug, laufendes Ermittlungsverfahren, Vorstrafe bekannt."
    result = RedactionEngineV2().redact(text)

    assert "Art. 10 DSGVO" in result.redacted_text, (
        "Strafrechtliche Daten muessen als Art. 10 DSGVO gelabelt werden."
    )
    assert "Strafrechtliche Informationen - Art. 9 DSGVO" not in result.redacted_text, (
        "Regression: Strafrechtliche Daten duerfen NICHT als Art. 9 DSGVO gelabelt werden."
    )


def test_real_article_9_category_still_labeled_as_article_9():
    """Gegenprobe: eine echte Art.-9-Kategorie (Gesundheit) bleibt korrekt Art. 9."""
    text = "Gesundheit: wiederkehrende Migräne, frühere Krankschreibungen."
    result = RedactionEngineV2().redact(text)

    assert "Gesundheit - Art. 9 DSGVO" in result.redacted_text, (
        "Echte Art.-9-Kategorien (z.B. Gesundheit) muessen weiterhin als Art. 9 DSGVO gelabelt werden."
    )
    assert "Gesundheit - Art. 10 DSGVO" not in result.redacted_text
