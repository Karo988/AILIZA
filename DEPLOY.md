# AILIZA — Deployment-Anleitung

## Überblick

| Teil | Wo | Warum |
|------|----|-------|
| Backend (Python/FastAPI) | [Render.com](https://render.com) (kostenlos) | All-Inkl kann kein Python |
| Frontend (HTML/JS) | All-Inkl (Ihr Webspace) | Statische Dateien, HTTPS vorhanden |

---

## Schritt 1 — Backend auf Render.com deployen

1. Gehen Sie zu [render.com](https://render.com) → **New** → **Web Service**
2. GitHub-Repo verbinden: `karo988/ailiza`
3. Branch: `claude/compassionate-hopper-fre2o0`
4. Render erkennt `render.yaml` automatisch → einfach **Deploy** klicken
5. Nach ~2 Minuten: URL kopieren, z.B. `https://ailiza-backend.onrender.com`

**Optionale Umgebungsvariablen in Render (Dashboard → Environment):**
- `AILIZA_ALLOWED_ORIGINS` = `https://ihre-domain.de` (Ihre All-Inkl-Domain)
- `GROQ_API_KEY` = Ihr Groq-Key (kostenlos auf groq.com)
- `AILIZA_EXTERNAL_LLM_ENABLED` = `true` (erst setzen wenn API-Key vorhanden)

---

## Schritt 2 — config.js anpassen

Datei `apps/frontend/config.js` öffnen und die Zeile eintragen:

```javascript
window.AILIZA_API = "https://ailiza-backend.onrender.com";
```

(URL durch Ihre echte Render-URL ersetzen)

---

## Schritt 3 — Frontend auf All-Inkl hochladen

Per FTP (z.B. FileZilla) diese 5 Dateien in Ihr Webspace-Verzeichnis (`/html/` oder `/www/`) hochladen:

```
apps/frontend/index.html    → /html/index.html
apps/frontend/config.js     → /html/config.js
apps/frontend/manifest.json → /html/manifest.json
apps/frontend/sw.js         → /html/sw.js
apps/frontend/icon.svg      → /html/icon.svg
```

---

## Schritt 4 — Als App auf dem Handy installieren

### Android (Chrome):
1. `https://ihre-domain.de` im Chrome öffnen
2. Menü (3 Punkte) → **"Zum Startbildschirm hinzufügen"**
3. AILIZA erscheint als App-Icon

### iPhone (Safari):
1. `https://ihre-domain.de` in Safari öffnen
2. Teilen-Symbol → **"Zum Home-Bildschirm"**

---

## Lokal testen (ohne Hosting)

```bash
# Windows:
start.bat

# Mac/Linux:
./start.sh
```

Dann im Browser: `http://localhost:8000`

Auf dem Handy (gleiches WLAN): `http://192.168.x.x:8000`

---

## Hinweis: Render.com Kaltstarts

Der kostenlose Render-Plan "schläft" nach 15 Minuten Inaktivität.
Beim ersten Aufruf kann das Backend ~30 Sekunden brauchen.
AILIZA zeigt dann: *"Backend nicht erreichbar. Render.com noch am Starten?"*
→ Einfach 30 Sekunden warten und neu laden.
