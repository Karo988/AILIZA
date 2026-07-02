# AILIZA — Lokale Entwicklungsumgebung

## Voraussetzungen

- Python 3.11+
- pip
- Mindestens ein LLM-Provider-Key (Groq kostenlos: https://console.groq.com)

---

## 1. Einmalige Einrichtung

### .env-Datei erstellen

```powershell
# Im Projektverzeichnis (z.B. C:\AILIZA\current)
Copy-Item .env.example apps\backend\.env
```

Öffne `apps\backend\.env` und trage deine Keys ein (Platzhalter ersetzen):

```
GROQ_API_KEY=gsk_...dein_echter_key...
AILIZA_EXTERNAL_LLM_ENABLED=true
```

Alle anderen Felder können zunächst leer bleiben.

> **Wichtig:** Die `.env`-Datei wird von `.gitignore` blockiert — sie wird NIEMALS committet.

### Python-Abhängigkeiten installieren

```powershell
cd apps\backend
pip install -r requirements.txt
```

---

## 2. Backend starten

```powershell
# Im Verzeichnis apps\backend
cd C:\AILIZA\current\apps\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

Backend läuft dann auf: http://localhost:8001

---

## 3. Testen

### Einfacher Health-Check

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/health" -Method GET
```

### Chat-Anfrage senden

```powershell
$body = @{
    task = "Erklaere mir was DSGVO bedeutet"
    session_id = "test-001"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://localhost:8001/agent/run" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

### Provider-Status prüfen

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/api/debug/provider-test" -Method GET
```

---

## 4. Umgebungsvariablen

### Welche Keys werden gebraucht?

| Variable | Wofür | Pflicht? |
|---|---|---|
| `GROQ_API_KEY` | LLM-Antworten (Groq, kostenlos) | Ja (oder ein anderer Provider) |
| `OPENAI_API_KEY` | LLM-Fallback | Nein |
| `ANTHROPIC_API_KEY` | LLM-Fallback | Nein |
| `OPENROUTER_API_KEY` | LLM-Fallback | Nein |
| `TAVILY_API_KEY` | Web-Suche (nur für Suchanfragen) | Nein |
| `AILIZA_EXTERNAL_LLM_ENABLED` | Kill-Switch, muss `true` sein | **Ja** |

### TAVILY_API_KEY — wann nötig?

AILIZA ruft Tavily nur auf, wenn die Anfrage als **Suchanfrage** erkannt wird
(z.B. "Recherchiere aktuelle News zu..."). Für direkte Fragen wie "Erkläre mir..."
wird Tavily **nicht** gerufen — nur der LLM-Provider.

Ohne Tavily-Key funktionieren alle LLM-Fragen normal. Suchanfragen geben dann
eine Fehlermeldung zurück.

### Provider-Reihenfolge steuern

```
AILIZA_PROVIDER_ORDER=groq,openai,openrouter,anthropic,local
```

Der erste Provider mit gesetztem API-Key und gültigem Zugang wird genutzt.
Bei Fehler (401/403/429) wechselt AILIZA automatisch zum nächsten.

---

## 5. Häufige Probleme

### "AILIZA_EXTERNAL_LLM_ENABLED ist nicht gesetzt"

In `apps\backend\.env` setzen:
```
AILIZA_EXTERNAL_LLM_ENABLED=true
```

### Groq 403 / "Zugriff verweigert"

- Key unter https://console.groq.com → API Keys → **in einem Projekt erstellen**
- Nicht auf Top-Level, sondern innerhalb eines aktiven Projekts
- Kostenloses Modell: `GROQ_MODEL=llama-3.1-8b-instant`

### "TAVILY_API_KEY is not configured"

Entweder Tavily-Key setzen (https://tavily.com) oder eine Frage stellen,
die kein Web-Suche auslöst (z.B. "Erkläre..." statt "Recherchiere...").

### PowerShell-Syntaxfehler bei JSON

Immer `ConvertTo-Json` nutzen — keinen JSON-String manuell schreiben:

```powershell
# Richtig:
$body = @{ task = "Hallo" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8001/agent/run" -Method POST -ContentType "application/json" -Body $body

# Falsch:
Invoke-RestMethod ... -Body '{"task": "Hallo"}'   # Encoding-Probleme unter Windows
```

---

## 6. Alle nötigen PowerShell-Befehle auf einmal

```powershell
# 1. Ins Projektverzeichnis wechseln
cd C:\AILIZA\current

# 2. .env-Datei anlegen (einmalig)
Copy-Item .env.example apps\backend\.env

# 3. .env öffnen und Keys eintragen (Notepad oder VSCode)
notepad apps\backend\.env

# 4. Abhängigkeiten installieren (einmalig)
pip install -r apps\backend\requirements.txt

# 5. Backend starten
cd apps\backend
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# --- In einem zweiten Terminal testen ---

# Health-Check
Invoke-RestMethod -Uri "http://localhost:8001/health" -Method GET

# Chat-Anfrage
$body = @{ task = "Erklaere mir was DSGVO bedeutet"; session_id = "test-001" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8001/agent/run" -Method POST -ContentType "application/json" -Body $body

# Provider-Status
Invoke-RestMethod -Uri "http://localhost:8001/api/debug/provider-test" -Method GET
```
