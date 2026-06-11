# AILIZA Prompt Templates

Dieses Dokument enthält Start-Prompts für die Arbeit im AILIZA-Projekt.

Die Prompts helfen dabei, neue Chats sauber zu starten und immer mit dem richtigen Projektkontext zu arbeiten.

## Grundregel

Jeder neue Arbeitschat sollte klar sagen:

* Projektname
* Repository
* eigener Branch
* eigener Aufgabenbereich
* wichtige Arbeitsregeln

So bleibt die Arbeit nachvollziehbar und sicher.

## Standard-Prompt für lokales Setup

Diesen Prompt nutzt ein Teammitglied, wenn der Rechner noch nicht eingerichtet ist.

```text
Projekt: AILIZA

Repository:
https://github.com/m-imica/ailiza

Ich bin Teammitglied und möchte mein lokales Setup selbst einrichten.

Mein Betriebssystem ist:
[Windows oder Mac]

Mein Aufgabenbereich ist:
[Aufgabenbereich eintragen]

Mein Branch soll heißen:
[Branch eintragen]

Bitte führe mich Schritt für Schritt durch:

1. Prüfen, ob Git installiert ist
2. Prüfen, ob Python installiert ist
3. Prüfen, ob VS Code installiert ist
4. GitHub-Zugriff prüfen
5. Repository klonen
6. In den Projektordner wechseln
7. Meinen Feature-Branch erstellen
8. Python-Umgebung einrichten
9. Backend testweise starten

Wichtige Regeln:

- Bitte jeden Befehl mit "WO: PowerShell", "WO: Terminal" oder "WO: Browser" kennzeichnen
- Bitte immer nur einen Schritt auf einmal
- Ich bin Anfänger/in
- Nicht direkt auf main arbeiten
- Keine fremden Module ohne Abstimmung ändern
- Keine Secrets/API-Keys committen
- Wenn Codex genutzt wird: Codex darf nur auf meinem Feature-Branch arbeiten
```

## Standard-Prompt für Arbeitschat

Diesen Prompt nutzt ein Teammitglied, wenn das Setup bereits fertig ist und an einer Aufgabe gearbeitet werden soll.

```text
Projekt: AILIZA

Repository:
https://github.com/m-imica/ailiza

Arbeitsmodus:
Feature-Branch Workflow

Mein Branch:
feature/...

Mein Aufgabenbereich:
...

Wichtige Regeln:

- Niemals direkt auf main arbeiten
- Keine fremden Module ohne Abstimmung ändern
- Kleine, nachvollziehbare Commits
- Vor jedem Arbeitsbeginn: git pull
- Änderungen immer dokumentieren
- Pull Requests vor Merge erstellen
- Keine Secrets/API-Keys committen

Architekturprinzipien:

- Governance-first
- EU-AI-Act-konform
- DSGVO-konform
- Auditierbarkeit
- Human Oversight
- Runtime Enforcement
- Controlled Autonomy
```

## Prompt für Documentation Community

```text
Projekt: AILIZA

Repository:
https://github.com/m-imica/ailiza

Mein Bereich:
Documentation Community

Mein Branch:
feature/documentation-community

Meine Aufgabe:
Ich erstelle und verbessere Dokumentation für neue Teammitglieder, Onboarding, Team-Workflow, README, Prompt-Vorlagen und Community-Regeln.

Wichtige Regeln:

- Nicht direkt auf main arbeiten
- Keine Backend- oder Frontend-Dateien ändern, außer nach Abstimmung
- Dokumentation einfach und anfängerfreundlich schreiben
- Befehle immer mit WO-Hinweisen kennzeichnen
- Änderungen über Pull Request zusammenführen
```

## Prompt für Frontend Dashboard

```text
Projekt: AILIZA

Repository:
https://github.com/m-imica/ailiza

Mein Bereich:
Frontend Dashboard

Mein Branch:
feature/frontend-dashboard

Meine Aufgabe:
Ich arbeite an der Benutzeroberfläche, Dashboard-Struktur, Nutzerführung und Visualisierung von Governance-, Audit- und Freigabeprozessen.

Wichtige Regeln:

- Nicht direkt auf main arbeiten
- Keine Backend- oder Governance-Dateien ohne Abstimmung ändern
- Keine Secrets/API-Keys committen
- Änderungen klein und nachvollziehbar halten
- Pull Request vor Merge erstellen
```

## Prompt für Business Governance

```text
Projekt: AILIZA

Repository:
https://github.com/m-imica/ailiza

Mein Bereich:
Business Governance

Mein Branch:
feature/business-governance

Meine Aufgabe:
Ich arbeite an Business-Prozessen, Governance-Logik, Risiko-Klassifikation und Human-Approval-Prozessen.

Wichtige Regeln:

- Nicht direkt auf main arbeiten
- Keine technischen Runtime-Module ohne Abstimmung ändern
- Entscheidungen dokumentieren
- EU-AI-Act- und DSGVO-Perspektive berücksichtigen
- Pull Request vor Merge erstellen
```

## Prompt für Governance QA

```text
Projekt: AILIZA

Repository:
https://github.com/m-imica/ailiza

Mein Bereich:
Governance QA

Mein Branch:
feature/governance-qa

Meine Aufgabe:
Ich prüfe Qualität, Review-Regeln, Issues, Testnotizen und Dokumentationskontrolle.

Wichtige Regeln:

- Nicht direkt auf main arbeiten
- Änderungen prüfen, bevor sie gemerged werden
- Keine Secrets/API-Keys zulassen
- Prüfschritte dokumentieren
- Pull Requests nachvollziehbar kommentieren
```

## Prompt für Runtime Core

```text
Projekt: AILIZA

Repository:
https://github.com/m-imica/ailiza

Mein Bereich:
Runtime Core

Mein Branch:
feature/runtime-core

Meine Aufgabe:
Ich arbeite an Agent Runtime, Backend-Kern, technischer Integration und Architekturentscheidungen.

Wichtige Regeln:

- Nicht direkt auf main arbeiten
- Keine Governance-Regeln umgehen
- Runtime Enforcement berücksichtigen
- Keine Secrets/API-Keys committen
- Technische Änderungen dokumentieren
- Pull Request vor Merge erstellen
```

## Prompt für Codex-Nutzung

```text
Projekt: AILIZA

Repository:
https://github.com/m-imica/ailiza

Codex darf nur auf folgendem Branch arbeiten:
feature/...

Aufgabe:
...

Wichtige Regeln:

- Nicht direkt auf main arbeiten
- Keine fremden Module ändern
- Keine Secrets/API-Keys erzeugen oder committen
- Keine großen Architekturänderungen ohne Rückfrage
- Kleine, nachvollziehbare Änderungen machen
- Änderungen dokumentieren
- Vor Abschluss erklären, welche Dateien geändert wurden
```

## Prompt für Pull-Request-Review

```text
Projekt: AILIZA

Bitte prüfe diesen Pull Request.

Achte besonders auf:

- Wurde der richtige Branch verwendet?
- Sind nur passende Dateien geändert?
- Ist die Änderung verständlich?
- Gibt es keine Secrets oder API-Keys?
- Wurden README oder Dokumentation angepasst, falls nötig?
- Gibt es Risiken für EU-AI-Act-Konformität?
- Gibt es Risiken für DSGVO-Konformität?
- Ist Human Oversight weiterhin berücksichtigt?
- Ist Auditierbarkeit weiterhin möglich?

Bitte gib eine einfache Review-Empfehlung:

- Merge möglich
- Änderungen erforderlich
- Rückfrage erforderlich
```

## Ziel

Diese Prompt-Vorlagen sorgen dafür, dass alle Teammitglieder mit demselben Kontext, denselben Regeln und derselben Projektlogik arbeiten.
