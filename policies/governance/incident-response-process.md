# AILIZA — Incident-Response-Prozess

**Version:** 1.0  
**Stand:** 2026-06-23  
**Nächste Überprüfung:** 2026-12-23  
**Rechtsgrundlage:** DSGVO Art. 33–34, Art. 32; EU AI Act Art. 73  
**Verantwortlich:** Datenschutzverantwortliche/r (DSV), System Owner (SO)  
**Hinweis:** Ein Incident bedeutet nicht automatisch eine meldepflichtige Datenpanne. Jeder Vorfall wird zuerst geprüft, dann bewertet. Keine voreiligen Annahmen.

---

## Was ist ein Incident?

Ein Incident im Sinne dieses Prozesses ist jedes Ereignis, das:

- die Vertraulichkeit, Integrität oder Verfügbarkeit von Daten beeinträchtigen könnte,
- auf eine Fehlfunktion eines Sicherheits- oder Governance-Mechanismus hindeutet,
- gegen geltende Richtlinien (DSGVO, EU AI Act, interne TOMs) verstoßen könnte, oder
- unbeabsichtigte Auswirkungen auf Nutzer, Daten oder externe Systeme hat.

**Unsicherheit ist kein Grund, nicht zu handeln.** Auch vermutete Incidents werden gemeldet und geprüft.

---

## Incident-Kategorien und Beispiele

### Kategorie A — Datenschutz / PII

| Beispiel | Beschreibung |
|---|---|
| Datenleck | Unbefugte Offenlegung von Nutzerdaten, Audit-Logs oder Konfigurationsdaten |
| PII in Audit-Log | Personenbezogene Daten, Prompts oder Nutzereingaben wurden im Audit-Vault gespeichert |
| Fehlklassifikation sensibler Daten | Daten mit hohem Risiko wurden fälschlich als öffentlich klassifiziert |
| Backup-Zugriff | Datenbankdatei durch unberechtigte Person kopiert oder eingesehen |

### Kategorie B — Sicherheit / Zugriff

| Beispiel | Beschreibung |
|---|---|
| Prompt Injection erkannt | Injection-Angriff in Dokument oder Nutzereingabe erkannt oder möglicherweise durchgekommen |
| Geheimnis/Token im Prompt | API-Key, Passwort oder TOTP-Code wurde in Nutzereingabe übermittelt |
| Unzulässiger Provider-Call | Externer LLM-Call ohne AVV, ohne Kill-Switch-Freigabe oder mit sensiblen Daten |
| Falsche Freigabe | Nutzer mit zu hoher Rolle eingeloggt, unberechtigter Admin-Zugriff |
| Brute-Force-Versuch | Wiederholte Login-Fehlversuche mit Anzeichen auf Angriff |

### Kategorie C — System / Governance

| Beispiel | Beschreibung |
|---|---|
| Audit-Vault-Fehler | Audit-Einträge fehlen, werden verändert oder sind nicht lesbar |
| Kill-Switch umgangen | Externer Call trotz `AILIZA_EXTERNAL_LLM_ENABLED=false` |
| Governance-Pipeline unterbrochen | Gates 1–10 wurden nicht vollständig durchlaufen |
| Konfigurationsänderung ohne Dokumentation | `governance_integrity.json` nicht aktualisiert |

---

## Sofortmaßnahmen (innerhalb 1 Stunde)

```
Schritt 1: Erkennen und nicht vertuschen
  → Wer einen Incident bemerkt, meldet sofort an DSV und SO.
  → Keine Eigenversuche der Behebung ohne Absprache.
  → Kein Löschen von Logs oder Beweisen.

Schritt 2: Isolieren (falls nötig)
  → Bei aktivem Angriff oder laufendem Datenleck: Kill-Switch aktivieren
    (AILIZA_EXTERNAL_LLM_ENABLED=false setzen, Dienst ggf. stoppen)
  → Betroffene Accounts sperren falls Kompromittierung vorliegt

Schritt 3: Dokumentieren
  → Incident-Eintrag im Audit-Vault schreiben (action: "incident.detected")
  → Zeitstempel, Art des Vorfalls, betroffene Systeme
  → Keine Rohdaten, Prompts oder Passwörter im Audit-Eintrag

Schritt 4: 72h-Uhr starten
  → Falls personenbezogene Daten betroffen sein könnten:
    72-Stunden-Frist (DSGVO Art. 33) beginnt ab Kenntnisnahme.
  → DSV entscheidet über Meldepflicht — NICHT SO oder DEV allein.
```

---

## Rollen im Incident-Prozess

| Rolle | Aufgabe im Incident |
|---|---|
| **Meldende Person** | Sofortmeldung an DSV und SO. Keine eigenständige Behebung. |
| **System Owner (SO)** | Koordiniert technische Sofortmaßnahmen. Entscheidet über Dienststop. |
| **DSV** | Bewertet Meldepflicht (DSGVO Art. 33/34). Kommuniziert mit Behörden. Entscheidet über 72h-Meldung. |
| **DEV** | Technische Untersuchung und Behebung nach Freigabe durch SO. |
| **ADM** | Zugriff auf Audit-Logs für Untersuchung. |

**Vier-Augen-Prinzip:** Kein Löschen von Daten oder Logs ohne DSV + SO gemeinsam.

---

## 72-Stunden-Prüfung (DSGVO Art. 33)

**Auslöser:** Mögliche Verletzung des Schutzes personenbezogener Daten.

**Prüfung durch DSV:**

```
Frage 1: Sind personenbezogene Daten betroffen?
  → Nein: Kein Art.-33-Incident. Interne Dokumentation.
  → Ja oder unklar: Weiter zu Frage 2.

Frage 2: Besteht ein Risiko für Rechte und Freiheiten natürlicher Personen?
  → Nein: Interne Dokumentation, kein Meldebedarf.
  → Ja oder unklar: Weiter zu Frage 3.

Frage 3: Wann wurde der Incident bemerkt?
  → Prüfen ob 72-Stunden-Frist noch läuft.
  → Meldung an Aufsichtsbehörde durch DSV vorbereiten.

Frage 4: Besteht hohes Risiko für betroffene Personen?
  → Ja: Zusätzlich Benachrichtigung der Betroffenen (Art. 34 DSGVO)
  → Nein: Nur Behördenmeldung.
```

**Wichtig:** Die Entscheidung über Meldepflicht trifft ausschließlich die/der DSV, ggf. mit Rechtsberatung. Keine automatische Annahme einer Meldepflicht.

---

## Dokumentation

Jeder Incident wird dokumentiert durch:

1. **Audit-Eintrag** (Zeitpunkt der Erkennung, Art, betroffene Komponente) — ohne Rohdaten
2. **Incident-Protokoll** (externes Dokument, außerhalb des Audit-Vaults) mit:
   - Zeitlinie (Erkennung, Meldung, Maßnahmen, Behebung)
   - Betroffene Systeme und Daten
   - Sofortmaßnahmen
   - Ursachenanalyse
   - Behebungsmaßnahmen
   - Nachsorge
3. **DSGVO-Meldedokumentation** (falls Meldung erfolgt)

**Nachtrag statt Änderung:** Kein Überschreiben von Incident-Protokollen. Korrekturen werden als Nachtrag mit Datum angehängt.

---

## Kommunikation

| Zielgruppe | Wann | Inhalt |
|---|---|---|
| DSV + SO | Sofort bei Erkennung | Art des Vorfalls, erste Einschätzung |
| DEV | Nach Erst-Assessment | Technische Details, Aufgaben |
| Betroffene Nutzer | Nach DSV-Entscheidung (DSGVO Art. 34) | Klare, verständliche Meldung ohne technische Details |
| Aufsichtsbehörde | Nach DSV-Entscheidung, innerhalb 72h | DSGVO-Meldung nach Art. 33 |

**Keine öffentliche Kommunikation** ohne Freigabe durch DSV und SO.

---

## Review nach Incident

Nach Abschluss jedes Incidents:

1. **Root-Cause-Analyse** — Was war die eigentliche Ursache?
2. **Maßnahmenplan** — Welche TOMs müssen ergänzt oder geändert werden?
3. **TOM-Katalog aktualisieren** — Offene Punkte nachtragen
4. **Test-Plan aktualisieren** — Neue Testfälle für erkannte Schwachstelle
5. **Tabletop-Nachbesprechung** — Was hat im Prozess nicht funktioniert?

---

## Offene Punkte

| Nr. | Thema | Verantwortlich |
|---|---|---|
| 1 | Kontaktdaten DSV und SO hinterlegen | SO |
| 2 | Aufsichtsbehörde identifizieren und Meldewege dokumentieren | DSV |
| 3 | Tabletop-Übung durchführen vor Produktionsstart | DSV, SO |
| 4 | Incident-Protokoll-Vorlage erstellen | DSV |
| 5 | Formalen Incident-Kanal einrichten (E-Mail, Ticket) | SO |

---

*Stand: 2026-06-23 — Kein Incident impliziert automatisch eine DSGVO-Meldepflicht. Erst prüfen, dann entscheiden.*
