# AILIZA Prompt Templates

Dieses Dokument enthält Start-Prompts für die Arbeit im AILIZA-Projekt. Sie sorgen dafür, dass jeder neue Agenten-Chat sofort den richtigen Projektkontext, die richtigen Regeln und die richtige Arbeitsweise hat.

## Grundregel

Jeder neue Arbeitschat sagt klar:

- Projektname und Repository
- eigener Branch (nie main)
- Aufgabenpaket (nicht Einzelschritt)
- Freigabe-Modell (siehe unten)

## Freigabe-Modell (gilt für jeden Agenten, jederzeit)

Zwei Kategorien, klar getrennt:

**Rein lesend — keine Rückfrage nötig:**
Code lesen, grep/suchen, Status prüfen (`git status`, PR-Status, CI-Ergebnisse), Testläufe zur Analyse fahren, Dateien vergleichen. Das darf ein Agent jederzeit selbst tun, ohne vorher zu fragen.

**Ändernd — immer erst ankündigen, dann auf OK warten:**
Dateien ändern/anlegen/löschen, committen, pushen, mergen, PR erstellen/schließen, externe Aktionen (GitHub, Deploy, API-Calls mit echten Keys). Davor **immer**: kurz und leicht verständlich erklären, WAS gemacht werden soll und WARUM — dann auf mein OK warten. Erst danach ausführen.

Bei einem ganzen Aufgabenpaket gilt das für das **Paket als Ganzes**: einmal das Gesamtvorhaben erklären (welche Dateien, welche Reihenfolge, welches Risiko), einmal OK abwarten, dann das Paket zusammenhängend abarbeiten — keine Einzelrückfrage pro Datei oder Schritt.

## Der Profi-Arbeitsprompt (Standard für den Alltag)

```text
Projekt: AILIZA
Repository: https://github.com/Karo988/AILIZA

Ich arbeite allein an diesem Projekt, erfahren im Umgang mit Agenten/Claude Code/Codex.
Ich arbeite in Paketen, nicht Schritt für Schritt.

Aufgabenpaket: [kurzer Titel]
Betroffener Bereich: [z. B. Runtime/Governance, Frontend, Dokumentation, Tests]
Branch: [Branch-Name — nie main]

Freigabe-Modell:
- Rein lesende Prüfungen (Grep, Read, Status, Testläufe zur Analyse): keine Rückfrage.
- Änderungen, Löschungen, Commits, Pushes, Merges, externe Aktionen: erst kurz und
  leicht verständlich ankündigen (WAS, WARUM), dann auf mein OK warten. Bei einem
  ganzen Paket reicht EINE Ankündigung + EIN OK für das Gesamtpaket, danach
  zusammenhängend arbeiten statt dateiweise nachzufragen.

Verbindliche Regeln (Details stehen in CLAUDE.md / VISION.md — bei Widerspruch gelten
die Originale dort, nicht diese Zusammenfassung):

- Ein-Agent-Regel: Governance-kritischer Code (Redaction, Policy, Kill-Switch, Data
  Governance) wird nur von einem Agenten gleichzeitig verändert — vor Beginn prüfen,
  ob dort gerade woanders gearbeitet wird.
- Nie direkt auf main. Kleine, nachvollziehbare Commits. Pull Request vor Merge —
  gemergt wird nur nach meiner ausdrücklichen Freigabe, kein automatischer Merge.
- Keine Secrets/API-Keys in Code, Commits, Logs oder Dateinamen (gitleaks prüft
  Dateiinhalte, keine Dateinamen — das selbst mitdenken).
- Governance-Pipeline nicht umgehen: Kill-Switch → Data Governance → Policy-Gateway →
  Redaction → Provider-Orchestrator. Externe LLM-Calls nie direkt aus main.py.
- Tests: `pytest tests/` ist die maßgebliche Suite (läuft in CI). `apps/backend/tests/`
  nur auf ausdrückliche Anforderung.
- Context-Disziplin: `apps/backend/main.py`, `apps/frontend/index.html`,
  `apps/backend/database.py` nie vollständig lesen — gezielt grep + offset/limit,
  breite Suchen an einen Explore-Subagenten geben.
- Verständliche deutsche Fehlermeldungen, kein Stack-Trace an die Nutzerin.
- Abschluss: ein zusammenfassender Bericht (geänderte Dateien, was/warum, offene
  Punkte) — keine Narration jedes Einzelschritts währenddessen.

Aufgabe im Detail:
[hier die eigentliche Aufgabe einfügen]
```

## Setup-Prompt (nur bei Bedarf, z. B. neuer Rechner)

```text
Projekt: AILIZA
Repository: https://github.com/Karo988/AILIZA

Ich richte ein neues/weiteres lokales Setup ein.
Betriebssystem: [Windows/Mac/Linux]
Branch: [Branch eintragen]

Bitte prüfen und einrichten:
1. Git, Python, VS Code vorhanden/aktuell?
2. GitHub-Zugriff vorhanden?
3. Repository klonen, Branch anlegen
4. Python-Umgebung einrichten (siehe requirements-core.txt)
5. Backend testweise starten (uvicorn, siehe CLAUDE.md)

Jeden Befehl mit "WO: PowerShell/Terminal/Browser" kennzeichnen.
Freigabe-Modell wie oben: rein lesend ohne Rückfrage, Änderungen mit Ankündigung + OK.
```

## Pull-Request-Review-Prompt

```text
Projekt: AILIZA

Bitte prüfe diesen Pull Request — rein lesend, keine Änderung.

- Richtiger Branch, nur passende Dateien geändert?
- Verständlich und nachvollziehbar?
- Keine Secrets/API-Keys (auch nicht im Dateinamen)?
- README/Dokumentation angepasst, falls nötig?
- Risiken für EU-AI-Act- oder DSGVO-Konformität?
- Human Oversight und Auditierbarkeit weiterhin gegeben?
- Governance-Pipeline-Reihenfolge eingehalten (kein direkter externer Call)?

Ergebnis als einfache Empfehlung: Merge möglich / Änderungen erforderlich /
Rückfrage erforderlich. Danach auf meine Entscheidung warten — kein Merge durch
den Agenten selbst.
```

## Archiv — Rollen-Prompts für ein späteres Team

Aktuell nicht in Gebrauch (Karo arbeitet allein, siehe Profi-Arbeitsprompt oben). Aufbewahrt, falls später Teammitglieder dazukommen.

### Prompt für Documentation Community

```text
Projekt: AILIZA

Repository:
https://github.com/Karo988/AILIZA

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

### Prompt für Frontend Dashboard

```text
Projekt: AILIZA

Repository:
https://github.com/Karo988/AILIZA

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

### Prompt für Business Governance

```text
Projekt: AILIZA

Repository:
https://github.com/Karo988/AILIZA

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

### Prompt für Governance QA

```text
Projekt: AILIZA

Repository:
https://github.com/Karo988/AILIZA

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

### Prompt für Runtime Core

```text
Projekt: AILIZA

Repository:
https://github.com/Karo988/AILIZA

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

### Prompt für Codex-Nutzung

```text
Projekt: AILIZA

Repository:
https://github.com/Karo988/AILIZA

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

## Ziel

Diese Prompt-Vorlagen sorgen dafür, dass jeder Agent mit demselben Kontext, demselben Freigabe-Modell und derselben Projektlogik arbeitet — als Paket, nicht in Einzelschritten.
