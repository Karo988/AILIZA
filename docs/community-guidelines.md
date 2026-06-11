# AILIZA Community Guidelines

Diese Guidelines beschreiben, wie wir im AILIZA-Projekt zusammenarbeiten.

## Grundhaltung

AILIZA ist ein Governance-first Projekt.  
Das bedeutet: Qualität, Nachvollziehbarkeit, Sicherheit und Compliance sind wichtiger als schnelle, unkontrollierte Änderungen.

## Zusammenarbeit

Wir arbeiten respektvoll, ruhig und nachvollziehbar.

Wichtig:

- Fragen sind erlaubt
- Fehler werden früh sichtbar gemacht
- Änderungen werden erklärt
- Entscheidungen werden dokumentiert
- Niemand arbeitet heimlich direkt auf `main`

## Branch-Regeln

Jede Aufgabe bekommt einen eigenen Branch.

Beispiele:

```text
feature/frontend-dashboard
feature/business-governance
feature/governance-qa
feature/documentation-community
runtime-core
```

Nicht direkt auf `main` arbeiten.

## Architecture Freeze v0.1

Die offizielle Projektstruktur ist:

```text
apps/
  backend/
audit/
docs/
policies/
docker/
tests/
```

Wichtig:

- Keine neuen Hauptordner ohne Abstimmung
- Backend-Code gehört nach `apps/backend`
- `apps/api` wird nicht mehr verwendet
- Keine Ersatzordner wie `src`, `server`, `backend2` oder `api` anlegen

## Kommunikation

Bei Fragen oder Unsicherheiten lieber kurz nachfragen, bevor Dateien geändert werden.

Gute Kommunikation enthält:

- Was soll geändert werden?
- Warum ist die Änderung nötig?
- Welche Dateien sind betroffen?
- Gibt es Risiken für andere Bereiche?

## Pull Requests

Pull Requests sollen verständlich beschrieben werden.

Eine gute PR-Beschreibung enthält:

- Was wurde geändert?
- Warum wurde es geändert?
- Welche Dateien sind betroffen?
- Gibt es offene Punkte?
- Muss jemand besonders prüfen?

## Reviews

Reviews dienen nicht der Kritik an Personen, sondern der Qualität des Projekts.

Geprüft wird:

- richtige Dateien
- richtige Struktur
- keine Secrets
- nachvollziehbare Änderungen
- Governance-first bleibt erhalten
- EU-AI-Act- und DSGVO-Perspektive werden berücksichtigt

## Codex-Nutzung

Codex darf nur auf dem eigenen Feature-Branch arbeiten.

Codex darf nicht:

- direkt auf `main` arbeiten
- fremde Module ohne Abstimmung ändern
- Secrets oder API-Keys erzeugen
- neue Hauptordner ohne Rückfrage anlegen
- Governance-Regeln umgehen

## Dokumentation

Dokumentation soll einfach, klar und anfängerfreundlich sein.

Wenn Befehle erklärt werden, sollen sie mit `WO:` gekennzeichnet werden.

Beispiel:

```text
WO: PowerShell
git status
```

## Umgang mit Fehlern

Fehler sind normal.

Wichtig ist:

- Fehler nicht verstecken
- Screenshots oder Ausgaben teilen
- nicht wild weiterklicken
- erst verstehen, dann ändern
- bei Unsicherheit stoppen und fragen

## Ziel

Diese Guidelines helfen dem Team, AILIZA sauber, nachvollziehbar und governance-konform weiterzuentwickeln.