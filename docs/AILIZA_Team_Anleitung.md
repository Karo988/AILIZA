# AILIZA — Team Anleitung
**Für alle die mit AILIZA arbeiten möchten**  
Stand: 09.06.2026 | Version: 0.3.0

---

## 🚀 Schnellstart (5 Minuten)

### Was du brauchst
- Windows PC
- Internet-Verbindung
- Das war's!

### Schritt 1 — Python installieren
1. Gehe zu: https://www.python.org/downloads/
2. "Download Python 3.11" klicken
3. Installieren — **wichtig:** Haken bei "Add Python to PATH" setzen!

### Schritt 2 — AILIZA herunterladen
```cmd
cd C:\
git clone https://github.com/M-Imica/ailiza.git Ailiza
cd Ailiza
```

Falls git nicht installiert: https://git-scm.com/download/win

### Schritt 3 — Abhängigkeiten installieren
```cmd
cd C:\Ailiza
pip install -r requirements.txt
```

### Schritt 4 — API-Keys eintragen
```cmd
copy .env.example apps\backend\.env
notepad apps\backend\.env
```

Folgendes eintragen:
```
GROQ_API_KEY=gsk_...        ← kostenlos auf console.groq.com
TAVILY_API_KEY=tvly_...     ← kostenlos auf app.tavily.com
```

### Schritt 5 — AILIZA starten
```cmd
cd C:\Ailiza
start_ailiza.bat
```

Dann Browser öffnen: **http://127.0.0.1:8001/dashboard**

---

## 🔑 API-Keys holen (kostenlos)

### Groq API-Key (für KI-Antworten)
1. Gehe zu: https://console.groq.com
2. Mit Google-Konto anmelden
3. "API Keys" → "Create API Key" → Key kopieren
4. Sieht aus wie: `gsk_abc123...`

### Tavily API-Key (für Web-Suche)
1. Gehe zu: https://app.tavily.com
2. Konto erstellen
3. API-Key kopieren
4. Sieht aus wie: `tvly_abc123...`

---

## 💬 AILIZA benutzen

### Chat
- Einfach Nachricht eintippen und Enter drücken
- AILIZA sucht im Web und antwortet
- Chatverlauf wird gespeichert

### Modell wählen
Oben im Chat kannst du wählen:
| Option | Beschreibung |
|--------|-------------|
| 🔍 Web-Suche | Kein Key nötig — sucht im Internet |
| Groq | Kostenloser KI-Key — antwortet intelligent |
| Anthropic | Claude Modelle |
| OpenAI | GPT Modelle |
| Mistral | Mistral Modelle |

### Projekte
- "📁 Projekte" Tab → "+ Neues Projekt"
- Name, Beschreibung, Priorität eingeben
- Projekt erscheint in der Übersicht

### Skills nutzen
- "⚡ Skills" Tab klicken
- Skill anklicken → Chat öffnet sich automatisch
- Verfügbare Skills:
  - 🔍 Web-Suche
  - ⚖️ EU AI Act Check
  - 🔒 DSGVO Analyse
  - 🌐 URL abrufen
  - 📝 Zusammenfassen
  - ✉️ E-Mail verfassen
  - ⚠️ Risikoanalyse
  - 📰 News

---

## 🛡 Sicherheit & Compliance

AILIZA ist vollständig EU-konform:
- ✅ DSGVO Art. 5, 6, 17, 20, 25, 30, 35
- ✅ EU AI Act Art. 9, 13, 14, 52
- ✅ Risikoklasse: Limited Risk
- ✅ Audit-Trail für alle Aktionen
- ✅ Human Oversight für kritische Entscheidungen

**Wichtig:** AILIZA kennzeichnet sich immer als KI-System (EU AI Act Art. 50)

---

## ❓ Häufige Probleme

### "Backend nicht erreichbar"
→ `start_ailiza.bat` doppelklicken und Fenster offen lassen

### "Kein API-Key"
→ `.env` Datei öffnen und Keys eintragen

### "Alter Chat wird angezeigt"
→ Seitenleiste: "🗑 Verlauf löschen" klicken

### Backend stoppt automatisch
→ Das CMD-Fenster von `start_ailiza.bat` niemals schließen!

---

## 📞 Kontakt & Support

**Projekt:** github.com/M-Imica/Ailiza  
**Team:** Corinna, Frank, Jens, Karola, Michele  
**EU AI Act Frist:** 02.08.2026 (noch 54 Tage!)

---

*AILIZA v0.3.0 · EU AI Act Limited Risk · DSGVO konform*
