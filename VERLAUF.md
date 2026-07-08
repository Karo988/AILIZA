# AILIZA — Entwicklungsverlauf (Session-Protokoll)

## Projektziel

**AILIZA** = DSGVO + EU AI Act konformer KI-Assistent für KMUs  
URL: https://ailiza.onrender.com  
Repo: https://github.com/Karo988/AILIZA  
Backend: FastAPI + SQLAlchemy (SQLite)  
Frontend: Statisches HTML (`apps/frontend/index.html`) — wird direkt von FastAPI ausgeliefert

---

## Umgesetzte Features (diese Session)

### 1. DSGVO-Redaction Pipeline

**Ziel:** Kein Name, keine Adresse, keine IBAN o.ä. darf unredaktiert die LLM erreichen.

**Fluss:**
```
Eingabe (original) → redactText() → Platzhalter → LLM → Platzhalter → de-redact → Antwort (original)
```

- Eingabefeld zeigt immer den **Originaltext** (keine Schwärzung sichtbar)
- Beim Absenden: `redactText(text)` ersetzt sensible Daten durch `[Name]`, `[E-Mail]`, `[IBAN]` etc.
- **User-Blase** zeigt den **redigierten Text** (mit Platzhaltern) → Nutzer sieht, dass Daten geschützt wurden
- LLM-Antwort: Platzhalter werden durch Originaldaten zurückersetzt (`activeRedactionMap`)

**PRIVACY_RULES (Regex-Kategorien):**
- IBAN, Kreditkarte, E-Mail, Telefon, Firma, Adresse, PLZ+Stadt, Name (titelbasiert), Referenz, Betrag, Datum, Transaktions-Nr.

**Fun-Effekt:**
- Erkannte PII-Tags (`<span class="dsgvo-bubble">`) fliegen beim Absenden nach rechts raus
- Bleiben als kleines 🔒-Symbol sichtbar (`.dsgvo-bubble.minimized`)

---

### 2. Login / Registrierung

**Ort:** `apps/frontend/index.html` — Login-Overlay oben rechts

**Tabs:**
- **Anmelden** — Nutzername + Passwort → `/auth/login` → JWT
- **Registrieren** — Neues Konto → `/auth/self-register` → JWT (auto-Login)

**Passwort-Policy (Selbstregistrierung):**
- Mind. 8 Zeichen
- Mind. 1 Großbuchstabe
- Mind. 1 Kleinbuchstabe
- Mind. 1 Zahl
- Kein Sonderzeichen erforderlich

**Backend-Endpunkt:** `POST /auth/self-register` (öffentlich, kein Token nötig)
```python
class SelfRegisterRequest(BaseModel):
    user_id: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=8)
    tenant_id: str = Field(default=DEFAULT_TENANT_ID)
```

**Topbar:**
- Nicht eingeloggt: Button `Anmelden` oben rechts
- Eingeloggt: `👤 Nutzername` (klicken → Abmelden)

**JWT-Handling:**
- Token in `localStorage("ailiza_jwt")`
- `authHeaders()` sendet `Authorization: Bearer <token>` bei jedem API-Call
- Bei vorhandenem Token: App startet direkt ohne Login-Overlay

---

### 3. Admin-Login

**Voraussetzung:** Umgebungsvariable in Render setzen:
- `AILIZA_ADMIN_PASSWORD` = gewünschtes Admin-Passwort
- `AILIZA_ADMIN_USER` = `admin` (Standard)

Ohne diese Variable wird kein Admin-User beim Start angelegt → Login schlägt fehl.

---

### 4. User-Blasen (Chat)

- User-Blasen **kollabieren nicht mehr** (altes `animateUserBubble` entfernt)
- Eingabefeld zeigt immer den **Originaltext** (kein Paste-Redaction im Feld)

---

## Fehler & Fixes

| Problem | Ursache | Fix |
|---|---|---|
| HTTP 401 bei Agent-Calls | `authHeaders()` sendete kein JWT | Bearer-Token aus localStorage eingefügt |
| Login schlägt still fehl | Checkboxen `l-consent` / `l-age` existierten nicht mehr | Checks entfernt |
| "Registrierung fehlgeschlagen" ohne Detail | Pydantic-Fehler als Array, Frontend löste nicht auf | `if(Array.isArray(msg)) msg=msg.map(e=>e.msg).join(" · ")` |
| Admin-Login funktioniert nicht | `AILIZA_ADMIN_PASSWORD` nicht in Render gesetzt | Env-Var in Render-Dashboard eintragen |
| User-Blase kollabiert nach 3s | `animateUserBubble()` fügte `.collapsed` hinzu | Funktion entfernt |
| Merge-Konflikt beim Push | Remote hatte `dsgvo-sidebar` Block, lokal Login-Overlay | Rebase-Konflikt aufgelöst, Login-Overlay behalten |

---

## Git-Verlauf (diese Session)

```
e417729  fix: Selbst-Registrierung repariert — einfachere Passwort-Policy, bessere Fehlermeldung
af5d097  (remote HEAD vor Merge)
```

Branch: `main` → Render auto-deploy aktiv

---

## Architektur-Übersicht

```
apps/
├── backend/
│   ├── main.py              # FastAPI, Endpoints, Auth
│   ├── kill_switch.py       # Globaler Notausschalter
│   ├── governance/          # DSGVO-Klassifikation, Redaction
│   ├── policy.py            # evaluate_policy()
│   ├── providers/           # LLM-Adapter (Groq, Anthropic, ...)
│   ├── routing/router.py    # Token-Budget, Routing
│   ├── audit/               # Security/Performance/Cost-Logs
│   ├── reflection/          # Memory & Reflection
│   ├── documents/           # Dokumenten-Scan
│   ├── streaming/           # Sicheres Streaming
│   └── database.py          # Tabellen, tenant_id-gefiltert
└── frontend/
    └── index.html           # Gesamtes Frontend (HTML + CSS + JS)
```

**Pipeline für externe LLM-Calls:**
```
Kill-Switch → Data Governance → Policy-Gateway → Redaction → Provider-Orchestrator
```

---

## Offene Punkte / TODO

- [ ] `AILIZA_ADMIN_PASSWORD` in Render Env-Vars setzen → Admin-Login testen
- [ ] Mobile: Sidebar-Verhalten auf kleinen Bildschirmen prüfen
- [ ] Tier-System (Anonym / Free / Pro / Enterprise) implementieren
- [ ] DSGVO-Consent: Zeit + Geo-Angabe beim Speichern prüfen
- [ ] Audit-Logs auf Vollständigkeit prüfen (lückenlos für Zertifizierung)

---

## Arbeitsregel (persistent)

> **Erst fragen, dann programmieren.**  
> Vor jeder Code-Änderung: erklären WAS und WARUM → auf OK warten → dann umsetzen.
