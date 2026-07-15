# AILIZA — Vision & aktueller Fokus

> Diese Datei ist die Single Source of Truth für das aktuelle Ziel.
> Wird von Karo gepflegt, von Claude Code zuerst gelesen.

## Aktuelles Ziel

AILIZA für erste echte Testnutzer bereit machen (Beta), auf Basis des
Docker-Staging-Service `AILIZA-stagin`, danach kontrollierter Merge nach
`main`.

## Priorität diese Woche

1. Docker-Staging-Funktionscheckliste vollständig grün bekommen
   (Health-Check, Beta-Gate, Golden-Brief-Redaction, Testmodus-Banner,
   Art.-50-Texte, Static-Whitelist, danach echter LLM-Call getestet)
2. Merge-Konfliktcheck Feature-Branch → `main`, sauberer PR
3. Produktions-Checkliste vorbereiten (AVV, bezahlter Plan, ENV-Werte)

## Offene Entscheidungen

- AVV mit Anthropic: noch nicht formal unterschrieben (nur dokumentiert)
- Bezahlter Render-Plan + persistente Disk: noch nicht entschieden
  (Free-Plan löscht SQLite/Audit-Trail bei jedem Deploy — Blocker für
  echten Produktivbetrieb)
- Alter Python-Staging-Service `AILIZA-1`: wird erst pausiert, wenn
  `AILIZA-stagin` vollständig verifiziert ist

## Architektur-Grundsatz (nicht verhandelbar)

Ein Agent (diese Session, `claude/adoring-lamport-c1zs8h`). Governance-
kritischer Code (Kill-Switch, Redaction, Policy-Gateway, Audit) bleibt
ausschließlich hier. Kein Push auf `main` ohne Freigabe und PR.
