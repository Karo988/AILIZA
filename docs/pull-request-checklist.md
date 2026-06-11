# AILIZA Pull Request Checklist

Diese Checkliste hilft dabei, Pull Requests vor dem Merge nach `main` sauber zu prüfen.

## Grundregel

Kein Pull Request wird ungeprüft nach `main` übernommen.

`main` ist die stabile Projektversion.

## 1. Branch prüfen

- [ ] Der Pull Request kommt nicht direkt von `main`
- [ ] Der Branch-Name passt zur Aufgabe
- [ ] Der Branch gehört zum richtigen Aufgabenbereich

Beispiele:

```text
feature/frontend-dashboard
feature/business-governance
feature/governance-qa
runtime-core
feature/documentation-community
```

## 2. Dateien prüfen

- [ ] Es wurden nur passende Dateien geändert
- [ ] Keine fremden Module wurden ohne Abstimmung geändert
- [ ] Keine unnötigen Dateien wurden hinzugefügt
- [ ] Keine temporären Dateien wurden committed

Nicht committen:

```text
venv/
__pycache__/
.env
.DS_Store
node_modules/
```

## 3. Architecture Freeze v0.1 prüfen

Offizielle Struktur:

```text
apps/
  backend/
audit/
docs/
policies/
docker/
tests/
```

Prüfen:

- [ ] Es wurden keine neuen Hauptordner ohne Abstimmung angelegt
- [ ] Backend-Code liegt unter `apps/backend`
- [ ] Es wurde kein neuer Ordner `apps/api` angelegt
- [ ] Es wurden keine Ersatzordner wie `src`, `server`, `backend2` oder `api` angelegt

## 4. Secrets prüfen

- [ ] Keine API-Keys enthalten
- [ ] Keine Passwörter enthalten
- [ ] Keine Tokens enthalten
- [ ] Keine privaten Zugangsdaten enthalten
- [ ] Keine `.env`-Dateien committed

## 5. Governance prüfen

- [ ] Governance-first bleibt berücksichtigt
- [ ] Human Oversight wird nicht entfernt
- [ ] Auditierbarkeit wird nicht verschlechtert
- [ ] Runtime Enforcement wird nicht umgangen
- [ ] EU-AI-Act- und DSGVO-Perspektive wurden bedacht

## 6. Dokumentation prüfen

- [ ] README wurde aktualisiert, falls nötig
- [ ] Relevante Dokumentation wurde ergänzt, falls nötig
- [ ] Änderungen sind für Anfängerinnen und Anfänger verständlich
- [ ] Befehle sind mit `WO:` gekennzeichnet, falls Anleitungen enthalten sind

## 7. Technische Prüfung

- [ ] Die Änderung ist klein und nachvollziehbar
- [ ] Der Zweck des Pull Requests ist klar
- [ ] Der Pull Request enthält eine verständliche Beschreibung
- [ ] Es gibt keine offensichtlichen Konflikte
- [ ] Falls Tests vorhanden sind: Tests wurden berücksichtigt

## Review-Ergebnis

Am Ende soll eine der folgenden Empfehlungen stehen:

```text
Merge möglich
Änderungen erforderlich
Rückfrage erforderlich
```

## Ziel

Diese Checkliste schützt die gemeinsame Projektstruktur und hilft dem Team, AILIZA sauber, nachvollziehbar und governance-konform weiterzuentwickeln.