# AILIZA deployen — All-Inkl + Render.com

## Überblick

| Teil | Dienst | Dauer |
|---|---|---|
| Backend (Python/KI) | Render.com (kostenlos) | ~5 Min |
| Frontend (Website) | All-Inkl (Ihr Hosting) | ~2 Min |

---

## Schritt 1 — Backend auf Render.com

1. **render.com** aufrufen → kostenlosen Account erstellen
2. "New" → **"Web Service"** → **"Connect a Git repository"**
3. GitHub-Account verbinden → Repository **karo988/ailiza** auswählen
4. Einstellungen werden automatisch aus `render.yaml` geladen
5. Optional: Unter "Environment" Ihren `GROQ_API_KEY` eintragen
6. **"Deploy Web Service"** klicken
7. Nach ~3 Minuten erscheint Ihre URL, z.B.:
   ```
   https://ailiza-backend.onrender.com
   ```
   → Diese URL kopieren!

> **Hinweis:** Im Render Free-Tier schläft der Server nach 15 Min Inaktivität ein.
> Erste Anfrage dauert ~30 Sek. Für dauerhaften Betrieb: Render Starter ($7/Mo).

---

## Schritt 2 — config.js anpassen

Datei `apps/frontend/config.js` öffnen und Ihre Render-URL eintragen:

```js
window.AILIZA_API = "https://ailiza-backend.onrender.com";
```

---

## Schritt 3 — Frontend auf All-Inkl hochladen

### Per FTP (FileZilla o.ä.)

1. FTP-Zugangsdaten aus All-Inkl KAS holen
2. In FileZilla verbinden
3. Folgenden Ordner auf Ihren Webspace hochladen (in `public_html/` oder `/`):

```
apps/frontend/
├── index.html       ← Hauptdatei
├── config.js        ← API-URL (angepasst in Schritt 2)
├── manifest.json    ← PWA
├── sw.js            ← Service Worker
└── icon.svg         ← App-Icon
```

### Per All-Inkl Dateimanager (KAS)

1. All-Inkl KAS aufrufen → "Dateimanager"
2. In den `www`-Ordner Ihrer Domain wechseln
3. Dateien einzeln hochladen (5 Dateien)

---

## Schritt 4 — Fertig!

Ihre AILIZA-Adresse:
```
https://ihre-domain.de
```

### Auf dem Handy installieren

1. Chrome auf dem Handy öffnen
2. `https://ihre-domain.de` aufrufen
3. Chrome fragt automatisch: **"App installieren"** → Tippen
4. AILIZA erscheint als Icon auf dem Homescreen

> Mit HTTPS (All-Inkl hat kostenloses SSL) zeigt Chrome das Install-Banner automatisch!

---

## API-Key nachträglich eintragen

Ohne API-Key läuft AILIZA im Basis-Modus (Web-Suche funktioniert trotzdem).
Für volle KI-Antworten:

1. **Groq** (kostenlos, schnell): console.groq.com → API-Key erstellen
2. In AILIZA: 🔑 Klicken → Key eingeben → Speichern

ODER dauerhaft in Render.com unter "Environment Variables" eintragen.

---

## Häufige Probleme

| Problem | Lösung |
|---|---|  
| "Backend nicht erreichbar" | Render URL in config.js prüfen, Backend evtl. noch am Starten (30 Sek warten) |
| Kein "App installieren" Button | Seite über HTTPS öffnen (https://, nicht http://) |
| CORS-Fehler | In Render Env: `AILIZA_ALLOWED_ORIGINS=https://ihre-domain.de` setzen |
