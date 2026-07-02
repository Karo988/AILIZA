# AILIZA v1.0 Beta Ready — Masterplan

> Eingefrorene Basis. Nicht ohne explizite Freigabe ändern.
> Änderungen und Korrekturen gehören in `01_addendum/`.

Vollständige v1.0-Blaupause mit 10 Artefakten — siehe `docs/ailiza-v1.0-blueprint.md` im Repository-Root.

## Verweis

Die vollständige Blaupause liegt unter:
`docs/ailiza-v1.0-blueprint.md`

Sie enthält:
1. Roadmap (v0.9 → v1.0 → v1.1)
2. Release-Gate-Kriterien
3. Provider-Profil-Datenmodell
4. Capability-Modell
5. Policy-Modell
6. Rollen-Modell (USER / AUDIT_VIEWER / MANAGER / ADMIN / DSB)
7. Audit-Schema (Stufe 1 + 2, SHA-256 Hash-Chain)
8. Modul-Matrix (freigegeben / blocked / responsibility_handoff)
9. Technische Sperrblöcke
10. Implementierungsreihenfolge (Woche 1–5)

## Identifizierte Lücken (Stand v0.9 → v1.0)

12 Lücken, davon 4 kritisch:

| # | Lücke | Priorität |
|---|---|---|
| 1 | AUDIT_VIEWER-Rolle fehlte | Kritisch — behoben |
| 2 | Audit-Vault Stufe 2 (Hash-Chain) fehlte | Kritisch — behoben |
| 3 | Freigabe-UI für Human Oversight | Kritisch — offen |
| 4 | TLS-Terminierung | Kritisch — offen |
| 5 | CORS Wildcard | Hoch — offen |
| 6 | Secret-Key-Startup-Check | Hoch — behoben |
| 7 | Memory-Governance UI | Mittel — offen |
| 8 | Fehlende Audit-Events | Mittel — offen |
| 9 | Backup-Strategie | Mittel — offen |
| 10 | Provider-Freigabe-Flow UI | Mittel — offen |
| 11 | CORS-Whitelist | Niedrig — offen |
| 12 | Retention-Löschauftrag-Flow | Niedrig — offen |
