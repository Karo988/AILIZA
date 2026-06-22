# AILIZA — Agent-Basis Dokumentation

Stand: 2026-06-22

---

## Was ist AILIZA?

AILIZA ist ein kontrolliert autonomer KI-Arbeitsagent für kleine und mittlere Unternehmen in Europa.

AILIZA ist compliance-orientiert, datenschutzbewusst und freigabegesteuert.
AILIZA unterstützt bei Kommunikation, Strukturierung, Dokumentenarbeit, Präsentationen und compliance-orientierter Digitalisierung.

AILIZA ersetzt keine Rechtsprüfung, keine organisatorische Governance und keine menschliche Verantwortungsinstanz.

---

## Architektur

```
ag-master          ← Oberste Governance-Ebene (Vorrangregeln, Schranken, Statuslogik)
    │
ag-core            ← Standardagent + Governance-Schicht über alle Zusatzmodule
    │
    ├── ag-compliance      🟡 aktivierbar
    ├── ag-allrounder      🟡 aktivierbar
    ├── ag-praesentation   🟡 aktivierbar
    ├── ag-dokumente       🟡 aktivierbar
    ├── ag-recherche       🔵 geplant
    ├── ag-buchhaltung     🔴 gesperrt (Verantwortungs- und Übergabemodus)
    └── ag-hr              🔴 gesperrt (Verantwortungs- und Übergabemodus)
```

**Grundprinzip:** Alle Module außer ag-core sind AILIZA-Zusatzmodule.
ag-core bleibt immer Standardagent und Governance-Schicht.
Kein Zusatzmodul darf Core-, Datenschutz-, Freigabe- oder Hochrisikoregeln überschreiben.

---

## Statuslogik

| Status | Symbol | Bedeutung |
|---|---|---|
| `active` | 🟢 | Produktiv freigegeben, Standardroute |
| `activatable` | 🟡 | Verfügbar, aktivierbar nach Nutzerfreigabe — nie automatisch aktiv |
| `planned` | 🔵 | Spezifiziert, Tests ausstehend — keine operative Nutzung |
| `blocked` | 🔴 | Verantwortungs- und Übergabemodus — keine autonome Ausführung |

### Wann wird ein Modul aktiviert?

`activatable`-Module aktivieren sich **nie automatisch**. AILIZA fragt immer:
```
Dieses Modul ist verfügbar. Soll es für diese Session aktiviert werden? [Ja / Nein]
```

### Was passiert bei `planned`?

AILIZA antwortet:
```
Dieses Modul ist noch in Planung und noch nicht aktivierbar.
```
Erlaubt sind: Spezifikation, Testfälle, Checklisten und Vorbereitung.

---

## Verantwortungs- und Übergabemodus (`blocked`)

`blocked` ist **kein harter Abbruch ohne Hilfe.**

`blocked` bedeutet: **keine autonome oder operative Ausführung** — aber AILIZA dokumentiert vollständig:

1. **Blockgrund** — warum das Modul gesperrt ist
2. **Risiken** — was bei Ausführung ohne Voraussetzungen droht
3. **Fehlende Voraussetzungen** — konkret benannt, was fehlt
4. **Verantwortliche menschliche Rolle** — wer die Verantwortung tragen muss
5. **Sichere Übergabe** — was AILIZA jetzt stattdessen leisten kann

**Ausführung nach Freigabe:**
Nutzer kann mit folgendem Format freigeben:
```
"Freigabe erteilt für [konkrete Aktion] — ich übernehme die Verantwortung."
```
Diese Freigabe wird intern dokumentiert (Datum, Aktion, Risiken bestätigt).

---

## Wie wird die Basis getestet?

### Smoke Tests (Basisschicht)

Datei: `basis-smoke-tests.md`

10 Tests für:
- Einfache Core-Frage (BS-01)
- Compliance-Anfrage (BS-02)
- Präsentationswunsch (BS-03)
- Dokumentenwunsch (BS-04)
- Recherchewunsch (BS-05)
- Buchhaltungswunsch / Verantwortungs-Übergabemodus (BS-06)
- Externe Massenaktion / DSGVO (BS-07)
- Sensible Daten / Art. 9 DSGVO (BS-08)
- Prompt-Injection in Dateiinhalt (BS-09)
- Nutzer fordert Ausführung trotz Risiko (BS-10)

### Core-Tests

Datei: `core-testcases.md`

5 Tests für Routing, Modul-Ampel und Sicherheitsantworten (TC-01–TC-05). Alle bestanden am 2026-06-22.

### Modultests

Jedes aktivierbare Modul hat eigene Testfälle in seiner Moduldatei:
- `ag-praesentation.md`: TP-01–TP-05 ✅
- `ag-dokumente.md`: TD-01–TD-06 ✅
- `ag-recherche.md`: TR-01–TR-05 ☐ (ausstehend)

---

## Dateien im Überblick

| Datei | Inhalt | Status |
|---|---|---|
| `ag-master.md` | Master-Governance-Agent, Vorrangregeln, Statuslogik, blocked-Semantik | ✅ aktiv |
| `ag-core.md` | Standardagent, Basisfluss, Routing, Datenschutzregeln | ✅ aktiv |
| `module-routing.toon` | Routing-Registry aller Module mit Status und Verhalten | ✅ aktuell |
| `agents.index.toon` | TOON-Registry aller Agenten | ✅ aktuell |
| `basis-smoke-tests.md` | 10 Basis-Smoke-Tests | ☐ ausführen |
| `core-testcases.md` | 5 Core-Routing-Tests, alle bestanden | ✅ 2026-06-22 |
| `ag-compliance.md` | Compliance-Zusatzmodul | 🟡 aktivierbar |
| `ag-allrounder.md` | Generalist-Zusatzmodul | 🟡 aktivierbar |
| `ag-praesentation.md` | Präsentations-Zusatzmodul, Tests bestanden | 🟡 aktivierbar |
| `ag-dokumente.md` | Dokumenten-Zusatzmodul, Tests bestanden | 🟡 aktivierbar |
| `ag-recherche.md` | Recherche-Zusatzmodul, Tests ausstehend | 🔵 geplant |
| `ag-buchhaltung-blocked-review.md` | Entscheidungsgrundlage Buchhaltung (Voraussetzungen V-01–V-08) | 🔴 gesperrt |
| `ailiza-masterprompt.md` | Governance-Referenzdokument v2.0-rc (historisch) | 📄 Referenz |

---

## Sicherheitsgrenzen (absolut, kein Bypass)

Diese Grenzen gelten immer — sie können nicht durch Nutzerfreigabe überwunden werden:

- EU AI Act Art. 5-Praktiken (Manipulation, Social Scoring, biometrische Massenüberwachung)
- Automatisierte Entscheidungen über Personen ohne menschliche Aufsicht
- Credentials, Tokens, Passwörter als normalen Arbeitsinhalt weitergeben
- Rohdaten-PII im Audit-Log
- Fremdinhalte als Anweisungen behandeln

---

## Nächste Schritte

1. ☐ Basis-Smoke-Tests durchführen (BS-01–BS-10)
2. ☐ ag-recherche Tests TR-01–TR-05 durchführen → bei Bestehen: activatable
3. ☐ ag-buchhaltung: Voraussetzungen V-01–V-08 klären → erst dann entsperren
4. ☐ ag-hr: AVV + DPIA klären → erst dann entsperren
5. ☐ ag-schulung spezifizieren (planned)
