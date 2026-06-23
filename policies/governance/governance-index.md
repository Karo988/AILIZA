# AILIZA Governance Pack v1
# Stand: 2026-06-22
# Ablage: policies/governance/

---

## Zweck

Dieses Governance Pack bereitet AILIZA als prüfungsfähiges Governance-System vor.
Es richtet sich an KMU-Betreiber, Datenschutzverantwortliche, Compliance-Verantwortliche
und technische Betreiber, die AILIZA verantwortungsvoll einsetzen wollen.

**Wichtiger Hinweis:**
Dieses Pack stellt keine abgeschlossene DSGVO-Konformität, keine EU-AI-Act-Freigabe
und keine behördliche Genehmigung dar. Es ist eine strukturierte Arbeitsbasis für
die eigene Compliance-Arbeit. Rechtliche Endprüfung durch qualifizierte Fachleute
bleibt erforderlich.

---

## Enthaltene Dokumente

| Datei | Inhalt | Status |
|---|---|---|
| `governance-index.md` | Übersicht, Zweck, offene Punkte | diese Datei |
| `roles-and-responsibilities.md` | Rollen, Aufgaben, Freigaberechte, Dokumentationspflichten | ✅ v1 |
| `data-flow-map.md` | Datenflüsse, Empfänger, Risiken, Schutzmaßnahmen | ✅ v1 |
| `audit-vault-concept.md` | Append-only Dokumentation, Pflichtfelder, Nachtragsprinzip | ✅ v1 |
| `processing-activities-register.md` | Verzeichnis der Verarbeitungstätigkeiten (VVT-Entwurf) | ✅ v1 (Entwurf) |

### Verwandte Dokumente (in `.claude/agents/`)

| Datei | Bezug |
|---|---|
| `ag-master.md` | Governance-Schicht, Vorrangregeln, Unveränderbare Dokumentationspflicht |
| `ag-buchhaltung-blocked-review.md` | Entscheidungsgrundlage blocked-Modul |
| `module-routing.toon` | Routing-Regeln, responsibility_handoff |
| `basis-smoke-tests.md` | Testnachweis Basisschicht |

---

## Abgedeckte Risiken

| Risiko | Abdeckung | Dokument |
|---|---|---|
| Unklare Rollenzuständigkeit | Rollen und Freigaberechte definiert | roles-and-responsibilities.md |
| Unkontrollierter Datenfluss zu externen Providern | Datenflüsse dokumentiert, Schutzmaßnahmen benannt | data-flow-map.md |
| Fehlende Nachvollziehbarkeit bei sensiblen Aktionen | Audit-Vault-Konzept, Pflichtfelder | audit-vault-concept.md |
| DSGVO Art. 30 — fehlendes VVT | VVT-Entwurf für alle aktiven Verarbeitungen | processing-activities-register.md |
| Autonome Buchungshandlung ohne Freigabe | ag-buchhaltung = blocked, responsibility_handoff | ag-master.md + blocked-review |
| KI-Entscheidung über Personen ohne Aufsicht | Absolute Sperre, Freigabepflicht | ag-master.md §8 |
| Rückwirkende Änderung von Dokumentation | Append-only, Korrekturen nur per Nachtrag | audit-vault-concept.md |

---

## Was noch offen ist

| # | Thema | Priorität | Verantwortlich |
|---|---|---|---|
| O-01 | AVV mit LLM-Provider abschließen | hoch | Admin / legal |
| O-02 | Provider-Profil: Training-Opt-out + kein Logging bestätigt | hoch | Admin / privacy |
| O-03 | DPIA/DSFA für HR-Modul (sobald aktiviert) | hoch | Datenschutzverantwortlicher |
| O-04 | Audit-Vault technisch implementieren (bisher nur Konzept) | mittel | technischer Betreiber |
| O-05 | Rechtsgrundlage für Verarbeitungen im VVT abschließen | mittel | Datenschutzverantwortlicher |
| O-06 | Drittlandtransfer-Analyse (LLM-Provider außerhalb EU) | hoch | legal / privacy |
| O-07 | Aufbewahrungs- und Löschkonzept finalisieren | mittel | Datenschutzverantwortlicher |
| O-08 | DPIA für Buchhaltungsmodul vor Entsperrung | hoch | Datenschutzverantwortlicher |
| O-09 | Technische Schutzmaßnahmen (TOMs) dokumentieren und prüfen | mittel | technischer Betreiber |
| O-10 | Compliance-Update-Check-Prozess etablieren | mittel | Compliance-Verantwortlicher |

---

## Was als nächstes ergänzt werden sollte

1. **AVV-Vorlage** — Auftragsverarbeitungsvertrag mit LLM-Provider
2. **TOM-Katalog** — technische und organisatorische Maßnahmen nach Art. 32 DSGVO
3. **Datenschutzerklärung** — für Endnutzer von AILIZA
4. **Incident-Response-Plan** — Datenpanne, Meldepflicht Art. 33/34 DSGVO
5. **DPIA-Vorlage** — für HR und Buchhaltung vor Aktivierung

---

## Versionierung

| Version | Datum | Änderung |
|---|---|---|
| v1 | 2026-06-22 | Erstversion: 5 Basisdokumente |
