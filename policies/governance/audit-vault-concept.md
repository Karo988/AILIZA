# AILIZA Audit-Vault — Konzept
# Stand: 2026-06-22
# Teil von: AILIZA Governance Pack v1

---

## Zweck

Der Audit-Vault ist das unveränderbare Dokumentationssystem von AILIZA.
Er speichert alle freigabepflichtigen, sensiblen, wirkungsrelevanten und
responsibility_handoff-Fälle so, dass:

- jede Entscheidung nachvollziehbar bleibt
- keine Dokumentation rückwirkend geändert, gelöscht oder überschrieben werden kann
- Korrekturen ausschließlich als Nachtrag erfolgen
- die Dokumentationskette lückenlos bleibt

Der Audit-Vault dient als Nachweis gegenüber Datenschutzbehörden, Wirtschaftsprüfern,
internen Prüfungen und im Rahmen von Betroffenenrechtsanfragen.

---

## Auslöser — Wann schreibt AILIZA in den Vault?

| Auslöser | Beschreibung |
|---|---|
| Freigabepflichtige Aktion | Versand, Upload, externe Datenübertragung, Systemänderung |
| Sensible Daten | Datenklasse: vertraulich, personenbezogen, besonders schützenswert, geheim |
| Wirkungsrelevante Aktion | Außenwirkung, Rechts-, Finanz-, Personalwirkung |
| responsibility_handoff | ag-buchhaltung, ag-hr oder jedes zukünftige blocked-Modul |
| Hochrisiko-Kontext | EU AI Act Art. 5, ai-act-hochrisiko-prüfen Modus |
| Sonderkorridor | Art. 9 DSGVO, sonderkorridor-prüfen Modus |
| Incident | Sicherheitsrelevante Auffälligkeit, Prompt-Injection-Versuch, Datenpanne |
| Nutzerfreigabe erteilt | Protokoll welche Freigabe von wem für welche Aktion |

---

## Pflichtfelder je Vault-Eintrag

```
documentation_id:        eindeutige, unveränderliche ID des Eintrags
timestamp:               ISO-8601-Zeitstempel der Erstellung (UTC)
user_request_summary:    Kurzzusammenfassung der Anfrage — kein Roh-PII, nur Kontext
selected_agent:          welcher Agent / welche Route genutzt wurde
module_status:           active | activatable | planned | blocked
data_class:              öffentlich | intern | vertraulich | personenbezogen |
                         besonders schützenswert | geheim
risk_mode:               normal | orange | sonderkorridor | hochrisiko |
                         responsibility_handoff | incident
decision:                was wurde entschieden oder abgelehnt (kein Roh-PII)
reason:                  Begründung: Blockgrund, Freigabebedingung, Risikoeinschätzung
required_human_role:     welche menschliche Rolle ist verantwortlich
approval_status:         ausstehend | erteilt | abgelehnt | nicht erforderlich
sources_or_basis:        Regelgrundlage, Rechtsgrundlage oder Modul-Referenz
next_safe_step:          empfohlener nächster sicherer Schritt
```

**Hinweis:** Kein Roh-PII in Vault-Einträgen. Nur Datenklassen-Bezeichnungen und
abstrakte Beschreibungen — niemals echte Namen, IBANs, Krankendiagnosen oder ähnliches.

---

## Nachtragsprinzip

```
Regel: Einmal geschriebene Einträge sind unveränderlich.

Korrekturen erfolgen ausschließlich als neuer Nachtrag (Addendum).
Der ursprüngliche Eintrag bleibt unverändert und vollständig erhalten.
```

### Pflichtfelder je Nachtrag

```
addendum_id:                    eindeutige ID des Nachtrags
timestamp:                      ISO-8601-Zeitstempel der Erstellung (UTC)
refers_to_documentation_id:     Verweis auf den ursprünglichen Eintrag
reason_for_addendum:            warum wird ein Nachtrag erstellt
new_information:                was ist neu, korrigiert oder ergänzt — kein Roh-PII
responsible_role:               wer erstellt den Nachtrag (Rolle, nicht Klarnamen)
```

---

## Zugriffsregeln

| Aktion | Berechtigt |
|---|---|
| Eintrag erstellen | AILIZA (automatisch) |
| Nachtrag erstellen | AILIZA (automatisch) oder Datenschutzverantwortlicher / Admin manuell |
| Eintrag lesen | Admin, Datenschutzverantwortlicher, Compliance-Verantwortlicher |
| Eintrag ändern | **Niemand — technisch gesperrt** |
| Eintrag löschen | **Niemand — technisch gesperrt** |
| Eintrag exportieren | Admin mit Freigabe des Datenschutzverantwortlichen |

---

## Speicher- und Löschlogik

### Aufbewahrungsfristen

| Eintragstyp | Aufbewahrungsfrist | Rechtsgrundlage |
|---|---|---|
| Freigaben für normale Aktionen | 3 Jahre | interne Richtlinie (zu definieren) |
| Buchungsrelevante Einträge | 10 Jahre | §147 AO (Aufbewahrungspflicht) |
| HR-relevante Einträge | 10 Jahre oder nach Beschäftigungsende + gesetzliche Frist | §26 BDSG, AO |
| Datenpannen-Incidents | 5 Jahre | DSGVO Art. 33/34, behördliche Praxis |
| Freigabenachweise mit Außenwirkung | 10 Jahre | interne Richtlinie (zu definieren) |

**Hinweis:** Aufbewahrungsfristen sind noch nicht abschließend definiert (O-07).
Die obigen Angaben sind Orientierungswerte.

### Löschung

Löschung von Vault-Einträgen ist grundsätzlich gesperrt.

Ausnahme: gesetzlich oder aufsichtsbehördlich angeordnete Löschung nach
Ablauf einer Aufbewahrungspflicht — nur durch Datenschutzverantwortlichen
mit dokumentierter Begründung und Nachweis der Aufbewahrungsfrist-Erfüllung.

---

## Technische Minimalumsetzung

Das Audit-Vault-Konzept kann schrittweise implementiert werden:

### Stufe 1 — Minimal (sofort umsetzbar)

Append-only Log-Datei im Dateisystem (z.B. `audit/vault.jsonl`):
- JSON Lines Format: ein Eintrag pro Zeile
- Dateisystem-Schreibrechte: nur AILIZA-Prozess darf schreiben
- Keine Update- oder Delete-Operationen im Code erlaubt
- Backup-Strategie: täglich gesichertes Offsite-Backup

```jsonl
{"documentation_id":"DOC-20260622-001","timestamp":"2026-06-22T10:00:00Z","selected_agent":"ag-core","module_status":"blocked","data_class":"vertraulich","risk_mode":"responsibility_handoff","decision":"Buchungsanfrage abgelehnt","reason":"ag-buchhaltung blocked: GoBD-Vault fehlt","required_human_role":"Buchhalter","approval_status":"ausstehend","sources_or_basis":"ag-master §10, ag-buchhaltung-blocked-review.md","next_safe_step":"Übergabe an Buchhalter zur manuellen Buchung"}
```

### Stufe 2 — Produktiv (empfohlen)

- Dedizierte Datenbank mit Insert-only-Schema (kein UPDATE, kein DELETE in DB-Rechten)
- Kryptografische Hash-Kette (jeder Eintrag enthält Hash des Vorgängers)
- Separate Zugriffskontrolle für Vault vs. normale Anwendung
- Exportfunktion mit Audit-Trail der Exporte selbst

### Stufe 3 — Erweitert (zukünftig)

- Unveränderlicher Objektspeicher (z.B. S3 mit Object Lock, WORM)
- Zeitstempelservice mit qualifiziertem Zeitstempel
- Integrationstest: versuchte Vault-Änderung schlägt fehl

---

## Verhalten wenn Vault nicht verfügbar

Wenn kein Audit-Vault verfügbar ist:

- AILIZA darf nur vorbereiten, nicht ausführen
- Freigabepflichtige, sensible, wirkungsrelevante und blocked-Fälle werden
  nicht operativ bearbeitet
- AILIZA meldet: "Audit-Vault nicht verfügbar — keine Ausführung möglich."

---

## Offene Punkte

| # | Thema |
|---|---|
| O-04 | Technische Implementierung Audit-Vault (Stufe 1 mindestens) |
| O-07 | Aufbewahrungs- und Löschfristen abschließend definieren |
| — | WORM-Speicher oder kryptografische Hash-Kette für Produktivbetrieb |
| — | Exportverfahren für Betroffenenrechtsanfragen definieren |
| — | Zugriffsprotokoll für Vault-Lesezugriffe einrichten |
