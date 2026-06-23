# AILIZA — Provider-DPA-Checkliste (AVV-Prüfung)

**Version:** 1.0  
**Stand:** 2026-06-23  
**Nächste Überprüfung:** 2026-12-23  
**Rechtsgrundlage:** DSGVO Art. 28, Art. 44–49; EU AI Act Art. 25, Art. 28  
**Verantwortlich:** Datenschutzverantwortliche/r (DSV), System Owner (SO)  
**Hinweis:** Kein Provider darf mit personenbezogenen Daten eingesetzt werden ohne geprüften AVV/DPA. Ohne AVV: höchstens öffentliche oder anonyme Daten.

---

## Zweck

Diese Checkliste stellt sicher, dass vor der Aktivierung eines externen Providers:

1. Der Verarbeitungszweck klar ist
2. Ein Auftragsverarbeitungsvertrag (AVV / Data Processing Agreement, DPA) vorliegt und geprüft wurde
3. Drittlandtransfers bewertet wurden
4. Trainingsnutzung ausgeschlossen oder dokumentiert ist
5. Die Freigabe durch DSV und SO erfolgt ist

**Grundregel:** Zweifel → kein Einsatz. Kill-Switch bleibt aktiv bis zur Freigabe.

---

## Prüfschema (je Provider)

Für jeden geplanten oder eingesetzten Provider ist dieses Schema vollständig auszufüllen.

---

### Provider 1 — Groq (LLM-Inference)

| Feld | Inhalt |
|---|---|
| **Anbietername** | Groq, Inc. |
| **Zweck der Verarbeitung** | LLM-Textgenerierung (Completion) |
| **Datenarten** | Nutzerprompts (nach Redaction), ggf. strukturierte Anfragetexte |
| **AVV/DPA erforderlich** | Ja — personenbezogene Daten möglich nach Redaction |
| **AVV vorhanden** | 🔲 Nein — noch nicht geprüft |
| **Datenregion** | USA (primär) |
| **Drittlandtransfer** | Ja — USA, kein Angemessenheitsbeschluss |
| **Drittland-Grundlage** | SCCs erforderlich — noch nicht geprüft |
| **Subprozessoren** | Unbekannt — noch nicht dokumentiert |
| **Trainingsnutzung** | Unbekannt — muss vertraglich ausgeschlossen werden |
| **Logging beim Anbieter** | Unbekannt — muss geprüft werden |
| **Retention beim Anbieter** | Unbekannt — muss geprüft werden |
| **Löschung** | Unbekannt |
| **TOMs des Anbieters** | Nicht geprüft |
| **Freigabestatus** | 🔴 Nicht freigegeben |
| **Entscheidung** | Nur öffentliche/anonymisierte Daten bis AVV vorliegt. Kein Einsatz mit PII. |
| **Verantwortlich** | DSV, SO |
| **Offene Punkte** | AVV anfordern, SCCs prüfen, Trainingsnutzung vertraglich ausschließen, Subprozessoren dokumentieren |

---

### Provider 2 — Anthropic (Claude)

| Feld | Inhalt |
|---|---|
| **Anbietername** | Anthropic, PBC |
| **Zweck der Verarbeitung** | LLM-Textgenerierung (Completion) |
| **Datenarten** | Nutzerprompts (nach Redaction), strukturierte Anfragetexte |
| **AVV/DPA erforderlich** | Ja |
| **AVV vorhanden** | 🔲 Nein — noch nicht geprüft |
| **Datenregion** | USA |
| **Drittlandtransfer** | Ja — USA |
| **Drittland-Grundlage** | SCCs erforderlich — noch nicht geprüft |
| **Subprozessoren** | Unbekannt |
| **Trainingsnutzung** | Unbekannt — muss vertraglich ausgeschlossen werden |
| **Logging beim Anbieter** | Unbekannt |
| **Retention beim Anbieter** | Unbekannt |
| **Löschung** | Unbekannt |
| **TOMs des Anbieters** | Nicht geprüft |
| **Freigabestatus** | 🔴 Nicht freigegeben |
| **Entscheidung** | Nur öffentliche/anonymisierte Daten bis AVV vorliegt. Kein Einsatz mit PII. |
| **Verantwortlich** | DSV, SO |
| **Offene Punkte** | Wie Groq — AVV, SCCs, Trainingsnutzung |

---

### Provider 3 — Tavily (Websuche)

| Feld | Inhalt |
|---|---|
| **Anbietername** | Tavily AI |
| **Zweck der Verarbeitung** | Web-Recherche (Suchanfragen) |
| **Datenarten** | Suchanfragen (nach Redaction) — kein Klartext-Prompt |
| **AVV/DPA erforderlich** | Ja, sofern Suchanfragen personenbeziehbar sein können |
| **AVV vorhanden** | 🔲 Nein — noch nicht geprüft |
| **Datenregion** | USA |
| **Drittlandtransfer** | Ja — USA |
| **Drittland-Grundlage** | SCCs erforderlich |
| **Subprozessoren** | Unbekannt |
| **Trainingsnutzung** | Nicht relevant (Suche, kein Training) — prüfen |
| **Logging beim Anbieter** | Unbekannt |
| **Retention beim Anbieter** | Unbekannt |
| **Löschung** | Unbekannt |
| **TOMs des Anbieters** | Nicht geprüft |
| **Freigabestatus** | 🔴 Nicht freigegeben — TAVILY_API_KEY nicht gesetzt (Kill-Switch aktiv) |
| **Entscheidung** | Nur Suchanfragen ohne PII zulässig, wenn AVV vorliegt |
| **Verantwortlich** | DSV, SO |
| **Offene Punkte** | AVV prüfen, Suchanfragen-Redaction sicherstellen |

---

## Freigabeprozess (gilt für alle Provider)

Bevor ein Provider mit personenbezogenen Daten eingesetzt werden darf, müssen folgende Schritte abgeschlossen sein:

```
Schritt 1: Provider-Prüfung (DSV)
  ├── AVV angefordert und geprüft
  ├── Drittlandtransfer-Grundlage geprüft (SCCs oder Angemessenheitsbeschluss)
  ├── Trainingsnutzung vertraglich ausgeschlossen
  ├── Subprozessoren dokumentiert
  └── Logging/Retention des Anbieters bekannt und akzeptabel

Schritt 2: Technische Prüfung (DEV)
  ├── Redaction vor jedem Provider-Call aktiv
  ├── Kill-Switch konfiguriert
  └── Governance-Pipeline vollständig (Gates 1–10)

Schritt 3: Freigabe (DSV + SO, Vier-Augen)
  ├── Schriftliche Freigabe mit Datum
  ├── Eintrag in dieser Checkliste aktualisiert
  └── Freigabestatus → 🟢

Schritt 4: Aktivierung (DEV, nach Freigabe)
  └── AILIZA_EXTERNAL_LLM_ENABLED=true setzen
      (nur für freigegebene Provider)
```

---

## Grundregel: Keine Aktivierung ohne AVV

| Szenario | Erlaubt |
|---|---|
| Öffentliche Daten, keine PII, kein AVV | ⚠️ Nur nach Einzelfallprüfung |
| Anonymisierte Daten, kein AVV | ⚠️ Nur nach Prüfung und Dokumentation |
| Personenbezogene Daten, kein AVV | 🔴 Verboten |
| Personenbezogene Daten, AVV geprüft, Freigabe erteilt | 🟢 Erlaubt |
| Personenbezogene Daten, AVV unklar | 🔴 Verboten bis Klärung |

---

## Offene Punkte (alle Provider)

| Nr. | Thema | Provider | Verantwortlich |
|---|---|---|---|
| 1 | AVV anfordern und prüfen | Groq, Anthropic, Tavily | DSV |
| 2 | SCCs oder Angemessenheitsbeschluss prüfen | Alle | DSV |
| 3 | Trainingsnutzung vertraglich ausschließen | Groq, Anthropic | DSV |
| 4 | Subprozessoren der Provider dokumentieren | Alle | DSV |
| 5 | Logging/Retention-Praxis der Provider klären | Alle | DSV |
| 6 | Redaction-Vollständigkeit vor Provider-Call testen | Alle | DEV |
| 7 | Freigabe-Dokumentation einrichten | Alle | SO, DSV |

---

*Stand: 2026-06-23 — Kein Provider ist aktuell für PII-Verarbeitung freigegeben. Kill-Switch aktiv.*
