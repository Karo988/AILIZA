# AILIZA Team Workflow

Dieses Dokument beschreibt den gemeinsamen Arbeitsablauf im AILIZA-Projekt.

## Grundprinzip

Niemand arbeitet direkt auf `main`.

`main` ist die stabile Projektversion. Neue Arbeiten passieren immer in einem eigenen Feature-Branch.

## Standard-Ablauf pro Arbeitssession

### 1. Projekt öffnen

WO: PowerShell

```powershell
cd C:\Users\cheym\ailiza
```

### 2. Aktuellen Stand prüfen

WO: PowerShell

```powershell
git status
```

### 3. Neueste Änderungen holen

WO: PowerShell

```powershell
git pull
```

## Neuen Branch erstellen

Für jede neue Aufgabe wird ein eigener Branch erstellt.

WO: PowerShell

```powershell
git checkout -b feature/name-der-aufgabe
```

Beispiele:

```text
feature/team-workflow-docs
feature/readme-update
feature/prompt-templates
feature/community-guidelines
```

## Änderungen speichern

Nach der Bearbeitung:

WO: PowerShell

```powershell
git status
```

Dann geänderte Dateien hinzufügen:

WO: PowerShell

```powershell
git add pfad/zur/datei.md
```

Commit erstellen:

WO: PowerShell

```powershell
git commit -m "Kurze Beschreibung der Änderung"
```

Branch zu GitHub hochladen:

WO: PowerShell

```powershell
git push -u origin feature/name-der-aufgabe
```

## Pull Request erstellen

WO: Browser / GitHub

Nach dem Push auf GitHub:

1. Repository öffnen
2. Auf `Compare & pull request` klicken
3. Titel und Beschreibung prüfen
4. Pull Request erstellen
5. Nicht direkt ohne Prüfung mergen, außer bei kleinen Doku-Änderungen nach Absprache

## Nach einem Merge

Wenn der Pull Request gemerged wurde:

WO: PowerShell

```powershell
git checkout main
git pull
git status
```

Danach ist der lokale `main` wieder aktuell.

## Codex-Regeln

Codex darf nur auf dem eigenen Feature-Branch arbeiten.

Codex darf nicht:

- direkt auf `main` arbeiten
- fremde Module ändern
- Secrets oder API-Keys erzeugen oder committen
- große Architekturänderungen ohne Abstimmung durchführen

## Dokumentationsregeln

Dokumentation soll:

- einfach verständlich sein
- für Anfängerinnen und Anfänger geeignet sein
- konkrete Befehle mit `WO:` markieren
- Schritt für Schritt aufgebaut sein
- technische Begriffe kurz erklären

## Review-Regeln

Vor dem Merge sollte geprüft werden:

- Ist der richtige Branch verwendet?
- Sind nur passende Dateien geändert?
- Ist die Änderung verständlich?
- Gibt es keine Secrets?
- Ist die Dokumentation nützlich für das Team?

## Ziel

Der Workflow sorgt dafür, dass AILIZA sauber, nachvollziehbar und teamfähig entwickelt wird.