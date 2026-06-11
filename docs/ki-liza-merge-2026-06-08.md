# Merge-Protokoll: KI-Liza nach AILIZA

**Datum:** 08.06.2026  
**Quelle:** `C:\ki-liza`  
**Ziel:** `C:\Ailiza`

## Vorgehen

- Bestehende Dateien in `C:\Ailiza` wurden beim Kopieren nicht überschrieben.
- Vor der Dokumentationsaktualisierung wurden Sicherungen unter
  `C:\Ailiza\.merge-backups\ki-liza-20260608-161842` angelegt.
- Generierte Dateien und Abhängigkeiten wurden ausgelassen, darunter
  `.git`, `.venv`, `.pytest_cache`, `deps`, `node_modules`, `dist`,
  `.npm-cache`, `.next`, `.wrangler`, `__pycache__`, `*.pyc` und Logs.

## Ergänzte Inhalte

- KI-Liza Backend Runtime und Gateway:
  `apps/backend/main.py`, `gateway.py`, `agent_runtime.py`, `approval.py`,
  `database.py`, `policy.py`, `tools.py`, `routers/` und `tests/`.
- KI-Liza Dashboard-Prototyp: `apps/web/dashboard.html`.
- New-Hire-Portal: `apps/new-hire-portal/`.
- Architektur- und Paketplatzhalter aus KI-Liza: `docs/`, `examples/`,
  `packages/` und `tests/`.
- Projektplan: `AILIZA_HERMES_PLAN.md`.

## Konflikte

Diese vorhandenen AILIZA-Dateien wurden nicht automatisch überschrieben:

- `.gitignore`
- `README.md`
- `apps/__init__.py`
- `apps/backend/__init__.py`

README, `.gitignore` und `docs/AILIZA_Projektübersicht.md` wurden anschließend
gezielt aktualisiert, damit AILIZA- und KI-Liza-Informationen zusammen sichtbar
sind.
