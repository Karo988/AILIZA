---
name: audit-vault-minimal-spec
description: AILIZA Audit-Vault Mindestspezifikation. JSONL-Schema, documentation_id, addendum_id, Nachtragsprinzip, Append-only-Regel, Hash-Konzept, Unveränderbarkeit, Minimalanforderungen für Stufe 1.
status: active
updated: 2026-06-23
---

# audit-vault-minimal-spec — AILIZA Audit-Vault Mindestspezifikation

Stand: 2026-06-23

Vollständiges Konzept: `policies/governance/audit-vault-concept.md`

---

## 1. Zweck

Der Audit-Vault speichert unveränderlich alle freigabepflichtigen, sicherheitsrelevanten und dokumentationspflichtigen Ereignisse in AILIZA.

Ziel: Rechenschaftspflicht (DSGVO Art. 5 Abs. 2) — nachweisbar und nachvollziehbar, welche Entscheidungen wann, warum und durch wen getroffen wurden.

---

## 2. Unveränderlichkeitsregel

**Keine Änderung, keine Löschung, kein Überschreiben bestehender Einträge.**

Korrekturen nur als neuer Nachtrag (addendum). Ursprünglicher Eintrag bleibt unverändert erhalten.

Diese Regel gilt absolut — auch für AILIZA selbst, auch nach Nutzerfreigabe. (ag-master §10)

---

## 3. JSONL-Schema: documentation_id (Haupteintrag)

Jeder Dokumentationseintrag ist eine einzelne JSONL-Zeile (kein Zeilenumbruch innerhalb des Eintrags):

```jsonl
{
  "documentation_id": "DOC-YYYYMMDD-NNN",
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "user_request_summary": "Kurzzusammenfassung — kein Roh-PII",
  "selected_agent": "ag-core | ag-compliance | ...",
  "module_status": "active | activatable | planned | blocked",
  "data_class": "öffentlich | intern | vertraulich | personenbezogen | besonders schützenswert | geheim",
  "risk_mode": "normal | orange | sonderkorridor | hochrisiko | responsibility_handoff",
  "decision": "was wurde entschieden oder abgelehnt",
  "reason": "Begründung: Blockgrund, Freigabebedingung, Risikoeinschätzung",
  "required_human_role": "welche menschliche Rolle ist verantwortlich",
  "approval_status": "ausstehend | erteilt | abgelehnt | nicht erforderlich",
  "sources_or_basis": "Regelgrundlage, Rechtsgrundlage oder Modul-Referenz",
  "next_safe_step": "empfohlener nächster sicherer Schritt"
}
```

**Pflichtfelder:** Alle 13 Felder sind Pflicht. Kein Eintrag ohne vollständige Felder.

**Verboten im Eintrag:** Roh-PII (Name, E-Mail, IBAN, Telefon etc.) — nur Datenklassen-Bezeichnung.

---

## 4. JSONL-Schema: addendum_id (Nachtrag)

Korrekturen oder Ergänzungen nur als neuer Nachtrag:

```jsonl
{
  "addendum_id": "ADD-YYYYMMDD-NNN",
  "timestamp": "YYYY-MM-DDTHH:MM:SSZ",
  "refers_to_documentation_id": "DOC-YYYYMMDD-NNN",
  "reason_for_addendum": "warum wird ein Nachtrag erstellt",
  "new_information": "was ist neu oder korrigiert — kein Roh-PII",
  "responsible_role": "wer erstellt den Nachtrag"
}
```

**Pflichtfelder:** Alle 6 Felder sind Pflicht.

---

## 5. Auslöser für Dokumentationspflicht

Dokumentation ist verpflichtend bei:

| Auslöser | risk_mode |
|---|---|
| Freigabepflichtige Aktion (ag-master §7) | orange oder responsibility_handoff |
| Sensible Daten (vertraulich, personenbezogen, besonders schützenswert, geheim) | orange oder sonderkorridor |
| Wirkungsrelevante Aktion (Außenwirkung, Systemänderung, Versand, Upload) | orange |
| blocked-Modul / responsibility_handoff | responsibility_handoff |
| Sonderkorridor (Art. 9 DSGVO, HR, Profiling) | sonderkorridor |
| Hochrisiko-Kontext (EU AI Act) | hochrisiko |
| Incidents und sicherheitsrelevante Auffälligkeiten | hochrisiko |

---

## 6. Append-only-Regel

Technische Anforderung an die Vault-Implementierung:

- Stufe 1 (aktuell): JSONL-Datei, neue Einträge werden am Ende angefügt (append)
- Stufe 2 (geplant): Insert-only-Datenbank mit Hash-Chain
- Stufe 3 (geplant): WORM-Speicher (Write Once Read Many)

Für Stufe 1 gilt: Kein Eintrag wird gelöscht oder überschrieben. Nur Anhängen erlaubt.

---

## 7. Hash-Konzept (Stufe 2, geplant)

Jeder Eintrag enthält in Stufe 2:
- `prev_hash`: SHA-256-Hash des vorherigen Eintrags
- `entry_hash`: SHA-256-Hash des eigenen Eintrags (ohne entry_hash-Feld selbst)

Dadurch ist Manipulation erkennbar: Jede Änderung eines Eintrags bricht die Hash-Kette.

---

## 8. ID-Format

```
documentation_id: DOC-YYYYMMDD-NNN    (NNN = dreistelliger Zähler je Tag)
addendum_id:      ADD-YYYYMMDD-NNN
```

Beispiele:
- `DOC-20260623-001` (erster Eintrag am 2026-06-23)
- `ADD-20260623-001` (erster Nachtrag am 2026-06-23)

---

## 9. Minimalanforderungen Stufe 1 (aktuell)

Stufe 1 gilt als implementiert wenn:

- [ ] JSONL-Datei vorhanden (`audit/vault.jsonl` oder äquivalent)
- [ ] Schreibzugriff nur Append (keine Delete/Update-Operationen)
- [ ] Alle 13 Pflichtfelder je Eintrag vorhanden
- [ ] Kein Roh-PII in Einträgen
- [ ] Nachtragsprinzip implementiert (addendum_id mit Verweis auf documentation_id)
- [ ] Eintrag bei jedem responsibility_handoff-Event
- [ ] Eintrag bei jeder Vollfreigabe-Bestätigung

---

## 10. Beispiel-Eintrag (Stufe 1)

```jsonl
{"documentation_id":"DOC-20260623-001","timestamp":"2026-06-23T10:00:00Z","user_request_summary":"Nutzer bittet um DATEV-Buchungsunterstützung — keine Roh-PII","selected_agent":"ag-core","module_status":"blocked","data_class":"vertraulich","risk_mode":"responsibility_handoff","decision":"Buchungsanfrage abgelehnt — ag-buchhaltung blocked","reason":"GoBD-Vault fehlt, AVV fehlt, skr-lookup nicht verfügbar","required_human_role":"Buchhalter oder Steuerberater","approval_status":"ausstehend","sources_or_basis":"ag-master §10, ag-buchhaltung-blocked-review.md, module-routing.toon","next_safe_step":"Übergabe an Buchhalter zur manuellen Buchung; AILIZA kann Übergabestruktur vorbereiten"}
```
