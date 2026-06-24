# AILIZA Masterplan — Baseline v1.0

**Stand:** 24.06.2026 | **Status:** Frozen

AILIZA ist ein AI-Governance-System zur kontrollierten Nutzung externer KI-Anbieter (GPT, Claude, etc.) in regulierten Umgebungen. Kein eigenes Modell — ein Kontrollrahmen.

## Kernprinzipien

- Sicherheit vor Komfort
- Zweckbindung für jeden Memory-Eintrag
- Aufbewahrungsfrist ist Pflicht — kein ewiges Speichern
- Deaktivierung statt stiller Löschung
- Kein sensitiver Klartext als Default
- Prüfbarkeit vor Vollständigkeit

## Komponenten

| Komponente | Zweck |
|-----------|-------|
| Memory Backend | Was darf gespeichert werden, wie lange, für wen |
| Audit Vault | Unveränderliche Hash-Kette, nur Entscheidungsmetadaten |
| Kill Switch | Abschaltkontrolle auf vier Ebenen |
| Policy Engine | Regelprüfung vor jeder Tool-Ausführung |
| Approval Flow | Human-in-the-Loop für risikoreiche Aktionen |

## Offene Punkte (Gap-Liste)

| # | Lücke | Status |
|---|-------|--------|
| G-01 | Memory-Backend persistentes DB-Backend | 🟡 offen |
| G-02 | Audit Vault Exportformat standardisiert | 🟡 offen |
| G-03 | Kill-Switch Persistenz (überlebt Neustart) | 🟡 offen |
| G-04 | BS-14–18 auf DB-Backend heben | 🟡 offen |
| G-05 | Dokumentationsstruktur als Single Source of Truth | ✅ geschlossen |
| G-06 | DataClass-Feld in MemoryEntry | ✅ geschlossen |
| G-07 | Audit Vault verify_chain()-Bugfix | ✅ geschlossen |
| G-08 | Kill-Switch vier Ebenen | ✅ geschlossen |
| G-09 | Audit Vault Tests | ✅ geschlossen |
| G-10 | Memory Tests BS-14–18 | ✅ geschlossen |
| G-11 | Kill-Switch Tests | ✅ geschlossen |
| G-12 | Policy Engine Tests | ✅ geschlossen |
