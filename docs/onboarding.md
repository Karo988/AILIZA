# AILIZA Onboarding

Willkommen im AILIZA-Projekt.

AILIZA ist eine Governance-first Plattform für kontrollierte autonome KI-Agenten.  
Das Ziel ist ein Agentensystem mit EU-AI-Act-Konformität, DSGVO-Konformität, Auditierbarkeit, Human Oversight und kontrollierter Autonomie.

## Ziel dieses Dokuments

Dieses Dokument hilft neuen Teammitgliedern dabei, das Projekt zu verstehen und sicher mitzuarbeiten.

## Grundregeln

- Niemals direkt auf `main` arbeiten
- Immer auf dem eigenen Feature-Branch arbeiten
- Vor Arbeitsbeginn immer `git pull` ausführen
- Kleine, nachvollziehbare Commits erstellen
- Keine Secrets, API-Keys oder Passwörter committen
- Keine fremden Module ohne Abstimmung ändern
- Änderungen über Pull Requests zusammenführen

## Arbeitsweise

Jede Person arbeitet in einem eigenen Branch.

Beispiele:

- `feature/documentation-community`
- `feature/frontend-dashboard`
- `feature/business-governance`
- `feature/governance-qa`
- `feature/runtime-core`

## Standard-Start

### WO: PowerShell

```powershell
cd C:\Users\cheym\ailiza
git status
git pull