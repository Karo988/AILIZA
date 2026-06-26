# AILIZA — Konten, API-Keys und Provider-Status

> **Sicherheitsregel:**
> Diese Datei enthält KEINE echten API-Keys, KEINE Passwörter und KEINE Zahlungsdaten.
> Niemals echte Zugangsdaten in Git eintragen.

---

## Haupt-E-Mail für AILIZA

| Zweck | E-Mail |
|---|---|
| **Neue Haupt-E-Mail (Ziel)** | `aliza@amun-online.de` |
| Bisherige Adresse (Entwicklung) | `karofromm@gmail.com` |
| Bisherige Adresse (Betrieb) | `service@amun-online.de` |
| Temporär (nicht weiter verwenden) | `kfrommnasreldin@wbsedu.de` |

Ziel: Alle AILIZA-Dienste künftig einheitlich über `aliza@amun-online.de` verwalten.

---

## Dienste-Übersicht

| Dienst | Geplante Haupt-E-Mail | Aktueller Status | Key in Render ENV | Aktueller Fehler | Nächste Aktion |
|---|---|---|---|---|---|
| **GitHub** | `aliza@amun-online.de` | Repository `karo988/ailiza` aktiv | — | — | E-Mail am Account prüfen/ändern |
| **Render** | `aliza@amun-online.de` | Deployment aktiv (main) | — | — | Account-E-Mail prüfen |
| **OpenAI API Platform** | `aliza@amun-online.de` | Fehler: 429 rate_limited | Ja (OPENAI_API_KEY) | `rate_limited` — Guthaben oder Limit erschöpft | Billing + Limit prüfen, neuen Key unter `aliza@amun-online.de` erstellen |
| **Groq** | `aliza@amun-online.de` | Fehler: 403 provider_forbidden | Ja (GROQ_API_KEY) | `provider_forbidden` — Key oder Modell-Zugriff verweigert | Neuen Groq-Key unter `aliza@amun-online.de` erstellen, in Render ersetzen |
| **Tavily** | `aliza@amun-online.de` | Key vorhanden, Funktion noch nicht geprüft | Ja (TAVILY_API_KEY) | Unbekannt | Websuche testen |
| **Anthropic** | `aliza@amun-online.de` | Kein Key vorhanden | Nein | — | Später optional einrichten |
| **OpenRouter** | `aliza@amun-online.de` | Deaktiviert (Registry: admin_approved=false) | Nein | — | Später optional über Registry + Admin-Freigabe |

---

## Provider-Lage im Detail

### OpenAI

- **Fehler:** `429 rate_limited`
- **Bedeutung:** Das Guthaben ist aufgebraucht, das Anfrage-Limit ist erreicht, oder das API-Projektlimit greift.
- **Key vorhanden:** Ja (OPENAI_API_KEY in Render gesetzt)
- **Aktionen:**
  1. OpenAI Platform öffnen: [platform.openai.com](https://platform.openai.com)
  2. Einloggen mit `aliza@amun-online.de` (oder Account verknüpfen)
  3. Billing: Guthaben prüfen und ggf. aufladen
  4. Usage Limits: Monats-Limit und Projektlimit prüfen
  5. API-Keys: Neuen Key erstellen (Bezeichnung: `ailiza-render-prod`)
  6. In Render: `OPENAI_API_KEY` ersetzen
  7. Render-Deploy ausführen

### Groq

- **Fehler:** `403 provider_forbidden`
- **Modell:** `llama-3.1-8b-instant` (sicherer Default, kostenlos verfügbar)
- **Bedeutung:** Der aktuelle Key gehört zu einem anderen Account oder hat keinen Zugriff auf das Modell.
- **Key vorhanden:** Ja (GROQ_API_KEY in Render gesetzt, aber ungültig/falscher Account)
- **Aktionen:**
  1. Groq Console öffnen: [console.groq.com](https://console.groq.com)
  2. Einloggen mit `aliza@amun-online.de` (Account erstellen falls nötig)
  3. Neuen API-Key erstellen (Bezeichnung: `ailiza-render-prod`)
  4. In Render: `GROQ_API_KEY` mit neuem Key ersetzen
  5. `GROQ_MODEL=llama-3.1-8b-instant` in Render prüfen (sollte gesetzt sein)
  6. Render-Deploy ausführen
  7. Logs prüfen: `AILIZA GROQ RESULT | result=ok` erwartet

### Tavily

- **Status:** Key vorhanden, Funktion noch nicht bestätigt
- **Verwendung:** Websuche für research_task (nicht für writing_task)
- **Aktionen:**
  1. Tavily Dashboard öffnen: [app.tavily.com](https://app.tavily.com)
  2. Account auf `aliza@amun-online.de` prüfen/umstellen
  3. Key in Render (`TAVILY_API_KEY`) bestätigen
  4. Websuche mit Testprompt prüfen: "Recherchiere aktuelle DSGVO-Neuigkeiten"

### Anthropic

- **Status:** Kein Key vorhanden
- **Verwendung:** Dritter Fallback (nach Groq und OpenAI)
- **Aktionen:** Später optional. Account unter `aliza@amun-online.de` erstellen und Key in Render als `ANTHROPIC_API_KEY` eintragen.

### OpenRouter

- **Status:** Deaktiviert — `admin_approved=false` in `registry/provider_registry.yaml`
- **Grund:** Subverarbeiter-Kette ungeklärt, DSGVO Art. 28 Abs. 4 nicht abgedeckt
- **Aktionen:** Später optional. Erfordert: AVV, Subverarbeiter-Liste, Admin-Freigabe in der Registry.

---

## Render ENV-Checkliste

> Diese Variablen müssen in Render unter **Environment → Environment Variables** gepflegt werden.
> Werte NIEMALS in Git eintragen.

### Pflicht-Variablen

| Variable | Beschreibung | Status |
|---|---|---|
| `AILIZA_CORS_ORIGINS` | Erlaubte Frontend-Origins (z.B. `https://ailiza.onrender.com`) | Prüfen |
| `AILIZA_EXTERNAL_LLM_ENABLED` | `true` damit externe LLM-Calls erlaubt sind | Prüfen |
| `AILIZA_SECRET_KEY` | Sicherer Zufalls-String für Auth/Sessions (min. 32 Zeichen) | Prüfen |
| `GROQ_API_KEY` | Groq API-Key (unter `aliza@amun-online.de` erstellen) | Ersetzen |
| `GROQ_MODEL` | `llama-3.1-8b-instant` (kostenlos, breite Verfügbarkeit) | Setzen |
| `OPENAI_API_KEY` | OpenAI API-Key (unter `aliza@amun-online.de` erstellen) | Ersetzen |
| `TAVILY_API_KEY` | Tavily API-Key für Websuche | Prüfen |

### Optionale Variablen (später)

| Variable | Beschreibung | Status |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic Claude API-Key | Noch nicht benötigt |
| `OPENROUTER_API_KEY` | OpenRouter API-Key | Gesperrt bis Registry-Freigabe |

---

## Nächste manuelle Schritte für Karo

### Sofort (damit AILIZA wieder antwortet)

- [ ] **1. Groq-Key erneuern**
  - [console.groq.com](https://console.groq.com) → mit `aliza@amun-online.de` einloggen
  - Neuen API-Key erstellen: Bezeichnung `ailiza-render-prod`
  - In Render `GROQ_API_KEY` ersetzen
  - `GROQ_MODEL=llama-3.1-8b-instant` prüfen (muss gesetzt sein)

- [ ] **2. OpenAI Billing prüfen**
  - [platform.openai.com](https://platform.openai.com) → einloggen
  - Billing → Guthaben prüfen, ggf. aufladen
  - Usage Limits → Monatslimit prüfen
  - Neuen API-Key erstellen: Bezeichnung `ailiza-render-prod`
  - In Render `OPENAI_API_KEY` ersetzen

- [ ] **3. Render Deploy ausführen**
  - Nach Key-Tausch: Manual Deploy → "Deploy latest commit"
  - Logs prüfen:
    - `AILIZA GROQ CALL | model=llama-3.1-8b-instant`
    - `AILIZA GROQ RESULT | result=ok`
    - oder: `AILIZA PROVIDER OK | provider=openai`

### Mittelfristig

- [ ] GitHub-Account-E-Mail auf `aliza@amun-online.de` prüfen/umstellen
- [ ] Render-Account auf `aliza@amun-online.de` prüfen/umstellen
- [ ] Tavily-Websuche testen (Prompt: "Recherchiere aktuelle DSGVO-Neuigkeiten")
- [ ] Alle alten Keys aus dem Account `karofromm@gmail.com` widerrufen, sobald neue Keys aktiv sind

### Später optional

- [ ] Anthropic-Account unter `aliza@amun-online.de` erstellen
- [ ] `ANTHROPIC_API_KEY` in Render eintragen
- [ ] OpenRouter DSGVO-Prüfung durchführen (AVV + Subverarbeiter-Liste)

---

## Hinweise zur Sicherheit

- Alte API-Keys aus anderen Accounts (z.B. `karofromm@gmail.com`) **widerrufen**, sobald neue Keys aktiv sind.
- `kfrommnasreldin@wbsedu.de` wird für AILIZA nicht weiter verwendet.
- Jeder API-Key erhält eine beschreibende Bezeichnung (`ailiza-render-prod`) damit er im Notfall gezielt widerrufen werden kann.
- Bei Verdacht auf kompromittierten Key: sofort in der jeweiligen Konsole widerrufen, neuen Key erstellen, in Render ersetzen, Deploy ausführen.

---

*Zuletzt aktualisiert: 2026-06-26*
