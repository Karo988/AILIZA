# AILIZA — Render Deployment Guide

## Übersicht

AILIZA Backend läuft als **Python Web Service** auf Render.  
Render liest `render.yaml` automatisch aus dem Repository.

---

## Schritt-für-Schritt (Browser)

### 1. Neuen Web Service erstellen

- Render Dashboard öffnen: https://dashboard.render.com
- **New → Web Service** klicken

### 2. GitHub Repository verbinden

- Repository auswählen: `karo988/ailiza` (oder dein Fork)
- **Connect** klicken

### 3. Basis-Konfiguration

| Feld | Wert |
|---|---|
| **Name** | `ailiza-backend` |
| **Region** | Frankfurt (EU — für DSGVO) |
| **Branch** | `main` |
| **Root Directory** | *(leer lassen — Repo-Root)* |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r apps/backend/requirements-core.txt` |
| **Start Command** | `python -m uvicorn apps.backend.main:app --host 0.0.0.0 --port $PORT` |

> **Wichtig:** `$PORT` wird von Render automatisch gesetzt — nicht hart kodieren!

> ⚠️ **Betriebsgrenze (PR 2, Genehmigungs-Nebenläufigkeit):** Die atomare
> Freigabeprüfung für Genehmigungsentscheidungen (`decide_approval_lock` in
> `apps/backend/database.py`) sowie die Audit-Hash-Chain
> (`_audit_write_lock`) sind ausschließlich **prozessinterne** Python-Sperren.
> Sie serialisieren gleichzeitige Anfragen korrekt **nur innerhalb EINES
> Uvicorn-Prozesses**. Solange keine datenbankseitige Sperre (z. B.
> `SELECT ... FOR UPDATE` bzw. ein Advisory Lock unter PostgreSQL/Neon)
> existiert, **darf AILIZA nicht mit mehreren Worker-Prozessen
> (`--workers N`, N > 1) und nicht mit mehreren parallel laufenden
> Instanzen/Render-Services betrieben werden** — sonst ist die
> Atomaritätsgarantie für Genehmigungsentscheidungen nicht mehr gegeben.
> Der Start Command oben startet bewusst genau einen Prozess ohne
> `--workers`-Flag; das MUSS so bleiben, bis eine DB-seitige Sperre
> nachgerüstet ist.

### 4. Environment Variables setzen

Unter **Environment → Add Environment Variable** folgende Keys eintragen:

#### Pflicht (ohne diese startet AILIZA nicht korrekt)

| Variable | Wert |
|---|---|
| `AILIZA_EXTERNAL_LLM_ENABLED` | `false` *(erst nach dokumentierter Provider-/AVV-Freigabe aktivieren)* |
| `AILIZA_ENV` | `production` |
| `AILIZA_SECRET_KEY` | *(zufälliges Secret, min. 32 Zeichen)* |
| `GROQ_API_KEY` | `gsk_...` *(von console.groq.com)* |
| `AILIZA_CORS_ORIGINS` | *(exakte öffentliche Frontend-Adresse, niemals `*`)* |
| `AILIZA_FORCE_HTTPS` | `true` *(erst nach verifiziertem Render-TLS aktivieren)* |

#### Empfohlen (Fallback-Provider)

| Variable | Wert |
|---|---|
| `OPENAI_API_KEY` | `sk-...` *(von platform.openai.com)* |
| `ANTHROPIC_API_KEY` | `sk-ant-...` *(von console.anthropic.com)* |

#### Optional

| Variable | Wert | Wofür |
|---|---|---|
| `TAVILY_API_KEY` | `tvly-...` | Web-Suche ("Recherchiere..."-Anfragen) |
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | Zusätzlicher Fallback (nur PUBLIC-Daten) |
| `AILIZA_PROVIDER_ORDER` | `groq,openai,openrouter,anthropic,local` | Reihenfolge der Provider |
| `AILIZA_CORS_ORIGINS` | `https://ailiza-frontend.onrender.com` | Wenn Frontend auf Render liegt |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Nur wenn default Modell geändert werden soll |
| `OPENAI_MODEL` | `gpt-4o-mini` | Nur wenn default Modell geändert werden soll |

#### Secret Key generieren

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Deploy starten

- **Create Web Service** klicken
- Build-Log beobachten — dauert ca. 1–3 Minuten

### 6. Deployment testen

Nach erfolgreichem Deploy wird eine URL angezeigt, z.B.:  
`https://ailiza-backend.onrender.com`

```bash
# Health Check
curl https://ailiza-backend.onrender.com/health

# Chat-Anfrage
curl -X POST https://ailiza-backend.onrender.com/agent/run \
  -H "Content-Type: application/json" \
  -d '{"task": "Erklaere mir was DSGVO bedeutet", "session_id": "test-001"}'
```

---

## CORS — Frontend-Backend-Verbindung

Wenn das AILIZA-Frontend separat deployed wird (z.B. auf Render Static Site):

1. Frontend-URL herausfinden, z.B. `https://ailiza-frontend.onrender.com`
2. Im Backend-Service unter **Environment** setzen:
   ```
   AILIZA_CORS_ORIGINS=https://ailiza-frontend.onrender.com
   ```
3. Mehrere Origins (kommagetrennt):
   ```
   AILIZA_CORS_ORIGINS=https://ailiza-frontend.onrender.com,https://www.meine-domain.de
   ```

> **Achtung:** Leerer Wert = `*` (alle Origins erlaubt) — nur für lokale Entwicklung!

---

## Provider-Reihenfolge und Fallback

AILIZA wechselt automatisch zum nächsten Provider wenn einer ausfällt:

```
Groq → OpenAI → OpenRouter → Anthropic
```

Steuerbar über `AILIZA_PROVIDER_ORDER` (kommagetrennt).  
Nur Provider mit gesetztem API-Key werden versucht.

---

## Häufige Fehler beim Render-Deploy

### "ModuleNotFoundError: No module named '...'"

Build Command prüfen: `pip install -r apps/backend/requirements-core.txt`
Root Directory muss **leer** (Repo-Root) sein, nicht `apps/backend`.

### "AILIZA_EXTERNAL_LLM_ENABLED nicht gesetzt"

Für einen rein lokalen/fail-closed Betrieb
`AILIZA_EXTERNAL_LLM_ENABLED=false` setzen. Erst nach dokumentierter
Provider-, AVV/DPA- und Transferfreigabe bewusst auf `true` ändern.

### Groq 403 / "Zugriff verweigert"

- Key unter https://console.groq.com → API Keys → **innerhalb eines Projekts erstellen**
- Nicht auf Top-Level, sondern in einem aktiven Projekt
- `GROQ_MODEL=llama-3.1-8b-instant` setzen (kostenloser Plan)

### "all_providers_failed"

Mindestens einen gültigen API-Key setzen. Der Debug-Provider-Endpunkt ist in
Produktion absichtlich nicht registriert. Providerfehler deshalb über
minimierte Betriebsmetriken und Audit-Ereignisse untersuchen, niemals durch
einen öffentlich erreichbaren Debug-Endpunkt.

### Port-Fehler / Service antwortet nicht

Start Command muss `$PORT` verwenden:  
`python -m uvicorn apps.backend.main:app --host 0.0.0.0 --port $PORT`  
Kein fester Port (8001 etc.)!

---

## render.yaml

Das Repository enthält `render.yaml` im Root.  
Render erkennt diese Datei automatisch und schlägt die Konfiguration vor.  
Secrets (API-Keys) werden in `render.yaml` als `sync: false` markiert und  
**müssen manuell im Render-Dashboard eingetragen werden — niemals im Code!**

---

## Datenbank

Ohne `AILIZA_DATABASE_URL` verwendet AILIZA einen Dev-Fallback (`ailiza_dev.db`).  
Für Produktion: Render PostgreSQL oder Persistent Disk für SQLite.

Beispiel SQLite auf Render Disk:
```
AILIZA_DATABASE_URL=sqlite:////data/ailiza.db
```
(Render Disk unter `/data` mounten)

---

## Nächste Schritte nach erstem Deploy

1. `/health` aufrufen → `{"status": "ok"}` erwartet
2. `/api/debug/provider-test` aufrufen → mindestens ein Provider `"allowed": true`
3. `/agent/run` mit Testanfrage aufrufen
4. In `render.yaml`: `autoDeploy: true` setzen für automatisches Deploy bei jedem Push
