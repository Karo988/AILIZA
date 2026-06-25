# Security Incident: Groq-API-Key in Git-History

**Datum:** 2026-06-25  
**Schweregrad:** Hoch (kompromittierter API-Key in Public-Repository-History)  
**Status:** Technisch bereinigt — Key-Rotation ausstehend (Benutzeraktion)

---

## Was ist passiert?

Eine Datei, deren Name einem Groq-API-Key entsprach (Prefix `gsk_`, vollständiger Key in der Groq Console identifizierbar), wurde in Commit `9b73d4d` ("AILIZA v0.4 - Initial Release") ins Repository committed. Der Dateiinhalt war ein Placeholder (`GROQ_API_KEY=gsk_HIER_DEINEN_KEY_EINSETZEN`), der Key selbst steckte jedoch im Dateinamen.

**Betroffener Key:** `gsk_eNoo...JHYE` (vollständig in Groq Console → API Keys ersichtlich — dort widerrufen)

---

## Durchgeführte Maßnahmen (2026-06-25)

| # | Maßnahme | Ergebnis |
|---|---|---|
| 1 | Datei aus Working Tree entfernt | ✅ |
| 2 | Codebase auf Key-String durchsucht | ✅ Kein Treffer außer Git-Index |
| 3 | Git-History mit `git-filter-repo` bereinigt | ✅ 115 Commits umgeschrieben |
| 4 | Force-Push: `main` + `claude/admiring-curie-9my9rf` | ✅ |
| 5 | `.gitignore`: alle `.env`-Varianten geblockt | ✅ |
| 6 | `detect-secrets` Baseline + Pre-Commit-Hook | ✅ |
| 7 | GitHub Code Search: Key nicht mehr auffindbar | ✅ |

---

## Noch ausstehend (Benutzeraktion erforderlich)

- [ ] **Groq-Key widerrufen** in [console.groq.com](https://console.groq.com) → Key löschen
- [ ] **Neuen Groq-Key erzeugen** (nur als ENV Variable, nie ins Repo)
- [ ] **Render-Deployment**: Neuen Key als `GROQ_API_KEY` in Render-Umgebungsvariablen setzen
- [ ] **Lokale Klone** neu klonen oder `git fetch --all && git reset --hard origin/main`
- [ ] **GitHub Secret Scanning Alerts** prüfen und als resolved markieren (nach Key-Rotation)

---

## Präventive Maßnahmen (umgesetzt)

### .gitignore (erweitert)
```
.env
.env.*
*.env
*.env.local
apps/backend/.env
apps/backend/.env.*
apps/**/.env
apps/**/.env.*
```

### Pre-Commit-Hook
`detect-secrets-hook --baseline .secrets.baseline` — bricht Commit bei neuem Secret-Fund ab.

### Installieren auf neuen Entwicklungsmaschinen
```bash
pip install detect-secrets
detect-secrets scan > .secrets.baseline  # einmalig
```

---

## Lessons Learned

1. Dateinamen können Secrets enthalten — `*.env*` im `.gitignore` reicht nicht, wenn Dateinamen selbst Keys tragen.
2. Pre-Commit-Hook hätte dies verhindert.
3. GitHub Secret Scanning sollte aktiv sein (Repository-Einstellungen → Security → Secret scanning).
4. Groq-Key darf nie in `.env`-Dateinamen, nur im Dateiinhalt einer `.gitignore`-geschützten Datei.

---

## Verantwortlich
Admin / Repository-Owner: karo988  
Bereinigt durch: AILIZA-Entwicklungs-Session (2026-06-25)
