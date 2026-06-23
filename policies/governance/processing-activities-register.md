# AILIZA Verzeichnis der Verarbeitungstätigkeiten (VVT)
# Stand: 2026-06-22
# Entwurf — keine abgeschlossene DSGVO-Konformität
# Teil von: AILIZA Governance Pack v1
# Rechtsgrundlage: DSGVO Art. 30

---

## Hinweis

Dieses VVT ist ein Arbeitsentwurf. Fehlende Rechtsgrundlagen, offene Speicherfristen
und ungeklärte Drittlandtransfers sind explizit markiert. Die Einträge müssen durch
den Datenschutzverantwortlichen geprüft, vervollständigt und freigegeben werden.

---

## VVT-01: AILIZA Core — Nutzeranfragen bearbeiten

| Feld | Inhalt |
|---|---|
| **Zweck** | Verarbeitung von Nutzeranfragen; Routing-Entscheidung; KI-gestützte Antwortgenerierung |
| **Betroffene Personen** | Nutzer von AILIZA (Mitarbeiter des Unternehmens) |
| **Datenkategorien** | Freitexteingaben, hochgeladene Dokumente, Routingdaten — potenziell PII wenn Nutzer Personendaten eingibt |
| **Empfänger** | LLM-Provider (extern, Verarbeitung für Inferenz) |
| **Speicherfrist** | Aktive Session; dauerhaft nur nach expliziter Freigabe — Frist offen (zu definieren) |
| **Rechtsgrundlage** | Offen — wahrscheinlich Art. 6 Abs. 1 b) DSGVO (Vertragserfüllung) oder f) (berechtigtes Interesse) — zu prüfen |
| **TOMs** | Datenminimierung; kein Roh-PII in Logs; Pseudonymisierungsangebot; Gate 1 (Klassifikation) — weitere TOMs zu dokumentieren (O-09) |
| **Drittlandtransfer** | Ja (LLM-Provider ggf. USA) — Analyse offen (O-06) |
| **Risiko** | mittel–hoch (abhängig von Eingabeinhalten und Provider) |
| **Status** | aktiv; AVV mit Provider offen (O-01) |

---

## VVT-02: Audit-Vault — Unveränderbare Aktionsdokumentation

| Feld | Inhalt |
|---|---|
| **Zweck** | Nachvollziehbare, unveränderliche Dokumentation freigabepflichtiger, sensibler und wirkungsrelevanter Aktionen; Freigabenachweise; Verantwortungsübergabe |
| **Betroffene Personen** | Nutzer, die freigabepflichtige Aktionen auslösen; indirekt betroffene Personen wenn Aktionsbeschreibung enthalten |
| **Datenkategorien** | Dokumentationseinträge (keine Roh-PII; Datenklassen-Bezeichnungen, Entscheidungen, Rollen) |
| **Empfänger** | Interner Speicher; lesend: Admin, Datenschutzverantwortlicher, Compliance-Verantwortlicher |
| **Speicherfrist** | Je nach Eintragstyp: 3–10 Jahre — Frist je Kategorie noch nicht abschließend definiert (O-07) |
| **Rechtsgrundlage** | Art. 6 Abs. 1 c) DSGVO (rechtliche Verpflichtung — GoBD, Rechenschaftspflicht Art. 5 Abs. 2 DSGVO) |
| **TOMs** | Append-only; kein Löschen/Ändern technisch gesperrt; Zugriffssteuerung; Backup |
| **Drittlandtransfer** | Nein (intern) |
| **Risiko** | niedrig (kein Roh-PII) |
| **Status** | Konzept definiert; technische Umsetzung offen (O-04) |

---

## VVT-03: Modulrouting — Aktivierungsentscheidungen

| Feld | Inhalt |
|---|---|
| **Zweck** | Entscheidung welches Modul für eine Nutzeranfrage genutzt wird; Aktivierungsfragen; Freigabedokumentation |
| **Betroffene Personen** | Nutzer |
| **Datenkategorien** | Routing-Metadaten, Modulstatus, Aktivierungsentscheidung — kein Inhalt der Anfrage |
| **Empfänger** | ag-core intern |
| **Speicherfrist** | Aktive Session; Audit-Vault-Einträge nach VVT-02 |
| **Rechtsgrundlage** | Offen — wahrscheinlich Art. 6 Abs. 1 b) oder f) — zu prüfen |
| **TOMs** | Kein Silent-Redirect; Aktivierungsfrage vor Weiterleitung; keine autonome Modulaktivierung |
| **Drittlandtransfer** | Nein |
| **Risiko** | niedrig |
| **Status** | aktiv |

---

## VVT-04: Präsentationsmodul (ag-praesentation)

| Feld | Inhalt |
|---|---|
| **Zweck** | Erstellung von Präsentationsgliederungen, Folienentwürfen, Sprechertexten auf Basis von Nutzerangaben |
| **Betroffene Personen** | Nutzer; ggf. Personen die in Präsentationsinhalten vorkommen |
| **Datenkategorien** | Freitexteingaben, Präsentationsinhalte — potenziell intern oder vertraulich (Quartalsdaten, Kundendaten) |
| **Empfänger** | LLM-Provider (für Inhaltserstellung); kein automatischer externer Versand |
| **Speicherfrist** | Aktive Session; dauerhaft nur nach expliziter Nutzerfreigabe — Frist offen |
| **Rechtsgrundlage** | Offen — Art. 6 Abs. 1 b) oder f) — zu prüfen |
| **TOMs** | Datenschutzcheck vor Bearbeitung; Pseudonymisierungsangebot; kein Auto-Upload; Footer mit Annahmen; Freigabe vor externer Weitergabe |
| **Drittlandtransfer** | Ja (LLM-Provider) — Analyse offen (O-06) |
| **Risiko** | niedrig–mittel (abhängig von Präsentationsinhalten) |
| **Status** | activatable; Tests bestanden 2026-06-22 |

---

## VVT-05: Dokumentmodul (ag-dokumente)

| Feld | Inhalt |
|---|---|
| **Zweck** | Zusammenfassung, Strukturierung, Verbesserung und Entwurf von Dokumenten |
| **Betroffene Personen** | Nutzer; ggf. Personen die in Dokumenten vorkommen (Vertragspartner, Kunden) |
| **Datenkategorien** | Dokumenteninhalte — potenziell vertraulich, personenbezogen (Verträge, Anschreiben, Berichte) |
| **Empfänger** | LLM-Provider (für Verarbeitung); kein automatischer externer Versand |
| **Speicherfrist** | Aktive Session; dauerhaft nur nach expliziter Nutzerfreigabe — Frist offen |
| **Rechtsgrundlage** | Offen — Art. 6 Abs. 1 b) oder f) — zu prüfen |
| **TOMs** | Vertraulichkeitscheck; Pseudonymisierungsangebot bei PII; kein Überschreiben von Originalen ohne Bestätigung; Analyse ≠ Rechtsgutachten |
| **Drittlandtransfer** | Ja (LLM-Provider) — Analyse offen (O-06) |
| **Risiko** | mittel (Verträge, personenbezogene Inhalte möglich) |
| **Status** | activatable; Tests bestanden 2026-06-22 |

---

## VVT-06: Rechercheplanung (ag-recherche) — geplant

| Feld | Inhalt |
|---|---|
| **Zweck** | Unterstützung bei Rechercheplanung, Quellenauswahl, Zusammenfassung öffentlicher Inhalte |
| **Betroffene Personen** | Nutzer |
| **Datenkategorien** | Suchanfragen (öffentlich); Zusammenfassungen öffentlicher Quellen; keine PII in Queries |
| **Empfänger** | WebSearch / WebFetch (öffentliche Dienste); LLM-Provider |
| **Speicherfrist** | Aktive Session — Frist offen |
| **Rechtsgrundlage** | Offen — zu prüfen wenn Modul aktiviert |
| **TOMs** | Kein PII in Web-Queries; Fremdinhalte = Daten; keine Personenrecherche ohne Freigabe |
| **Drittlandtransfer** | Ja (WebSearch-Provider, LLM-Provider) — Analyse offen |
| **Risiko** | niedrig (öffentliche Inhalte) |
| **Status** | planned; VVT-Eintrag vorbereitend — nicht aktivierbar bis Tests TR-01–05 bestanden |

---

## VVT-07: Buchhaltungsunterstützung (ag-buchhaltung) — responsibility_handoff

| Feld | Inhalt |
|---|---|
| **Zweck** | Unterstützung bei Buchhaltungsaufgaben — ausschließlich Dokumentation, Strukturierung, Risikoaufklärung und Übergabevorbereitung; keine operative Buchung |
| **Betroffene Personen** | Nutzer; Kunden/Lieferanten (wenn Rechnungsdaten erwähnt) |
| **Datenkategorien** | Rechnungsdaten, Buchungsvorlagen (strukturiert), Blockgründe — hochsensibel: potenziell IBAN, Beträge, USt-ID |
| **Empfänger** | Fachrolle Buchhaltung / Steuerberater; kein LLM-Provider für operative Buchungsdaten ohne AVV |
| **Speicherfrist** | 10 Jahre (§147 AO, GoBD) — nach Aktivierung; aktuell nicht operativ |
| **Rechtsgrundlage** | Offen — Art. 6 Abs. 1 b) oder c); bei Einzelunternehmern Art. 9-nah — DPIA erforderlich (O-08) |
| **TOMs** | responsibility_handoff; kein Auto-Commit; GoBD-Vault nötig (V-04, offen); skr-lookup nötig (V-03, offen); AVV nötig (V-01, offen) |
| **Drittlandtransfer** | Offen — nur nach AVV-Abschluss erlaubt |
| **Risiko** | sehr hoch |
| **Status** | blocked; Voraussetzungen V-01–V-08 nicht erfüllt; DPIA ausstehend (O-08) |

---

## VVT-08: HR-Unterstützung (ag-hr) — responsibility_handoff

| Feld | Inhalt |
|---|---|
| **Zweck** | Unterstützung bei HR-Aufgaben — ausschließlich risikoarme Vorarbeit; keine Personalentscheidungen |
| **Betroffene Personen** | Beschäftigte (besonderer Schutz nach §26 BDSG, Art. 88 DSGVO) |
| **Datenkategorien** | Beschäftigtendaten, Leistungsdaten, Gehaltsangaben — sehr hoch sensitiv |
| **Empfänger** | Fachrolle HR; kein LLM-Provider ohne AVV + DPIA |
| **Speicherfrist** | Abhängig von Beschäftigungsdauer und gesetzlichen Fristen — offen |
| **Rechtsgrundlage** | §26 BDSG (Beschäftigtendatenschutz), Art. 88 DSGVO — DPIA zwingend (O-03) |
| **TOMs** | responsibility_handoff; keine Personalentscheidungen ohne Mensch; AVV ausstehend; DPIA ausstehend |
| **Drittlandtransfer** | Offen — gesperrt bis AVV + DPIA abgeschlossen |
| **Risiko** | sehr hoch |
| **Status** | blocked; AVV und DPIA ausstehend (O-03) |

---

## VVT-Übersicht

| VVT-ID | Verarbeitung | Status | AVV | DPIA | Drittland |
|---|---|---|---|---|---|
| VVT-01 | Core — Nutzeranfragen | aktiv | **offen** | nicht zwingend | **offen** |
| VVT-02 | Audit-Vault | Konzept | nein | nein | nein |
| VVT-03 | Modulrouting | aktiv | nein | nein | nein |
| VVT-04 | Präsentation | activatable | **offen** | nein | **offen** |
| VVT-05 | Dokumente | activatable | **offen** | nein | **offen** |
| VVT-06 | Recherche | planned | offen | nein | offen |
| VVT-07 | Buchhaltung | blocked | **nötig** | **nötig** | **nötig** |
| VVT-08 | HR | blocked | **nötig** | **nötig** | **nötig** |

---

## Offene Punkte

- Rechtsgrundlage für VVT-01, 04, 05 abschließen
- AVV mit LLM-Provider (betrifft VVT-01, 04, 05, 06, 07, 08)
- Drittlandtransfer-Analyse (O-06) für alle LLM-basierten Verarbeitungen
- DPIA für VVT-07 (Buchhaltung) und VVT-08 (HR) vor Aktivierung
- Speicherfristen für alle aktiven Verarbeitungen definieren (O-07)
- Datenschutzverantwortlichen zur Prüfung und Freigabe dieses VVT beauftragen
