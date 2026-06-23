---
name: data-classification
description: AILIZA Datenklassifizierung. 6 Datenklassen mit Beschreibung, Beispielen, Speicherregeln, Freigaberegeln und Auditpflicht. Verbindliche Referenz für alle Agenten.
status: active
updated: 2026-06-23
---

# data-classification — AILIZA Datenklassifizierung

Stand: 2026-06-23

Verbindlich für alle AILIZA-Agenten. Kein KI-Call ohne Datenklasse. (ag-master §6)

---

## Klasse 1: öffentlich

**Beschreibung:** Informationen ohne Personenbezug oder Vertraulichkeitsanspruch; frei verfügbar oder zur Veröffentlichung bestimmt.

**Beispiele:**
- Allgemeine Sachfragen (Was ist eine GmbH?)
- Öffentliche Gesetzestexte, Normen, Standards
- Produktbeschreibungen ohne Kundendaten
- Öffentliche Berichte und Statistiken

**Speicherregeln:** Keine Einschränkung.

**Freigaberegeln:** Keine Freigabe erforderlich.

**Auditpflicht:** Keine.

---

## Klasse 2: intern

**Beschreibung:** Interne Unternehmensinformationen ohne Personenbezug; nicht zur Veröffentlichung bestimmt, aber ohne direktes Risiko bei interner Verarbeitung.

**Beispiele:**
- Interne Prozessbeschreibungen
- Projektentwürfe ohne Kundendaten
- Interne Checklisten und Vorlagen
- Besprechungsnotizen ohne PII

**Speicherregeln:** Nur im Workspace; keine externe Weitergabe ohne Zweckbegründung.

**Freigaberegeln:** Kurzfreigabe ausreichend bei Speicheraktion.

**Auditpflicht:** Nur bei Speicheraktion (Kurzfreigabe dokumentieren).

---

## Klasse 3: vertraulich

**Beschreibung:** Informationen mit erhöhtem Schutzbedarf; Bekanntwerden könnte geschäftlichen, rechtlichen oder finanziellen Schaden verursachen.

**Beispiele:**
- Vertragsdetails und Konditionen
- Finanzdaten des Unternehmens (nicht Kundendaten)
- Strategische Pläne, Businesspläne
- Angebote und Preiskalkulationen

**Speicherregeln:** Nur lokal im Workspace; keine externe Route ohne Erforderlichkeit und Vollfreigabe.

**Freigaberegeln:** Vollfreigabe erforderlich bei externer Übertragung.

**Auditpflicht:** Ja — bei externer Übertragung.

---

## Klasse 4: personenbezogen

**Beschreibung:** Daten, die eine natürliche Person direkt oder indirekt identifizieren (DSGVO Art. 4 Nr. 1).

**Beispiele:**
- Name, Anschrift, E-Mail, Telefonnummer
- IP-Adresse, Kundennummer, Benutzerkonto
- Geburtsdatum, IBAN
- Kontaktlisten, Kundenstammdaten

**Speicherregeln:** Minimieren; Zweck, Rechtsgrundlage und Frist dokumentieren; keine externe Route ohne AVV.

**Freigaberegeln:** Vollfreigabe erforderlich; Rechtsgrundlage (Art. 6 DSGVO) nennen.

**Auditpflicht:** Ja — immer bei Verarbeitung außerhalb lokaler Analyse.

**DSGVO-Hinweis:** AILIZA fragt nach Rechtsgrundlage, Zweck und AVV bevor externe Verarbeitung.

---

## Klasse 5: besonders schützenswert

**Beschreibung:** Besondere Kategorien personenbezogener Daten nach Art. 9 DSGVO; erhöhtes Missbrauchsrisiko.

**Beispiele:**
- Gesundheitsdaten (Krankheit, Diagnose, AU)
- Biometrische Daten (Fingerabdruck, Gesichtserkennung)
- Religiöse oder politische Überzeugungen
- Sexuelle Orientierung
- Rassische oder ethnische Herkunft
- Strafrechtliche Verurteilungen (Art. 10 DSGVO)

**Speicherregeln:** Nur mit Erforderlichkeit, enger Zweckbindung und expliziter Freigabe; Pseudonymisierung anbieten.

**Freigaberegeln:** Vollfreigabe + Sonderkorridor-Modus; DPIA-Pflicht ansprechen; Rechtsgrundlage Art. 9 Abs. 2 DSGVO benennen.

**Auditpflicht:** Ja — immer; unveränderliche Dokumentation (ag-master §10).

**Sonderkorridor:** Modus `sonderkorridor-prüfen` wird automatisch ausgelöst. (ag-master §7b)

---

## Klasse 6: geheim / credentials

**Beschreibung:** Zugangsdaten, Geheimnisse und hochvertrauliche Informationen, deren Bekanntwerden direkten, unmittelbaren Schaden verursacht.

**Beispiele:**
- Passwörter, API-Keys, Tokens
- Privat-Schlüssel, Zertifikate
- Bankzugänge, Admin-Credentials

**Speicherregeln:** Niemals im Output, Audit-Log, Memory oder Write-Dateien.

**Freigaberegeln:** Kein Freigabeweg — absolute Sperre. (ag-master §8)

**Auditpflicht:** Incident-Logging wenn erkannt; keine Inhalte im Log.

---

## Zuordnungsregel

Wenn mehrere Klassen zutreffen: höchste Klasse gilt.

Beispiel: Ein Dokument enthält interne Prozessinfos (Klasse 2) und eine E-Mail-Adresse (Klasse 4) → Klasse 4 gilt für das gesamte Dokument.

---

## Sonderkorridor-Auslöser (ag-master §7b)

Folgende Inhalte lösen automatisch Modus `sonderkorridor-prüfen` aus, unabhängig von der Datenklasse:

- Art. 9 DSGVO (Gesundheit, Biometrie, Religion, politische Meinung, sexuelle Orientierung, Strafdaten)
- HR-Daten, Leistungsbewertung, Personalakten
- Profiling oder automatisierte Entscheidungen mit erheblicher Wirkung auf Personen
- Vertrauliche Finanz- oder Vertragsdaten mit Personenbezug

Im Sonderkorridor:
1. Pseudonymisierungsangebot machen
2. Zweck und Rechtsgrundlage erfragen
3. DPIA-Pflicht ansprechen
4. Keine externe Route ohne explizite Freigabe
5. Menschliche Verantwortungsrolle benennen
