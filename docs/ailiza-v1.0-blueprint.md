# AILIZA v1.0 Beta Ready — Blueprint

**Version:** 1.0  
**Stand:** 2026-06-23  
**Status:** Arbeitsgrundlage — keine finale Rechtsberatung  
**Grundprinzip:** AILIZA v1.0 ist erst Beta Ready, wenn kein externer Zugriff ohne Provider-Profil, Policy, Freigabeprüfung und Audit möglich ist.

---

## 1. Finale v1.0-Roadmap

### Was bereits existiert (Stand 2026-06-23)

| Komponente | Datei | Status |
|---|---|---|
| Provider-Profil-System | `providers/provider_profiles.py` | ✅ Implementiert (4 Profile: groq, anthropic, openrouter, local) |
| Tool-Gateway | `gateway.py` | ✅ Implementiert (`guarded_tool_call`, Policy + Approval) |
| Capability Registry | `capabilities/registry.py` | ✅ Implementiert (11 Capabilities) |
| RBAC (USER/MANAGER/ADMIN/DSB) | `auth/rbac.py` | ✅ Implementiert |
| Memory-Governance | `reflection/reflection_skill.py` | ✅ Blockiert CREDENTIALS/SPECIAL/HR/LEGAL |
| Kill-Switch | `kill_switch.py` | ✅ Implementiert |
| Datenklassifikation | `governance/data_governance.py` | ✅ 11 Klassen, Pattern-basiert |
| Audit-Vault Stufe 1 | `audit/vault.py` | ✅ Append-only, Admin-only, sanitized |
| Approval-System | `gateway.py` + `approval.py` | ✅ Risikobewertung + Freigabe-Queue |
| Dokument-Scan Gate 6 | `documents/document_handler.py` | ✅ Injection + Klassifikation |
| Redaction | `governance/` | ✅ Vor Provider-Call |

### Was fehlt für v1.0

| Lücke | Schwere | Beschreibung |
|---|---|---|
| `audit_viewer`-Rolle | 🔴 Kritisch | Fehlt in `Role`-Enum. DSB hat zu viel Macht wenn kombiniert mit Admin |
| Audit-Vault Stufe 2 | 🔴 Kritisch | Kein Hash-Chain, keine Signatur, keine WORM-Option, keine Manipulationsprüfung |
| Freigabe-UI (Human Oversight) | 🟡 Hoch | Approval-API existiert, kein Frontend-UI für Freigaben |
| Gateway-Enforcement vollständig | 🟡 Hoch | `agent_runtime.py` ruft `tool_executor` direkt ohne Capability-Check |
| TLS in Produktion | 🔴 Kritisch | `allow_origins=["*"]` + kein HTTPS = kein Produktionsbetrieb |
| AILIZA_SECRET_KEY erzwungen | 🔴 Kritisch | Warnung im Log, aber kein Hard-Fail beim Start |
| Memory-Löschung durch Nutzer | 🟡 Hoch | Kein Frontend-UI, nur API |
| Memory-Sichtbarkeit für Nutzer | 🟡 Hoch | Nutzer kann gespeicherte Facts nicht einsehen |
| Incident-Log-Eintrag im Vault | 🟡 Hoch | Incident-Prozess dokumentiert, aber kein `incident.*`-Audit-Schema |
| CORS-Wildcard | 🟡 Hoch | Nur für Entwicklung akzeptabel |
| Backup | 🟡 Hoch | Keine automatische DB-Sicherung |
| Retention-Cleanup Prozess | 🟢 Mittel | Report vorhanden, Cleanup-Workflow fehlt |

---

## 2. Release-Gate: Muss-Kriterien für v1.0 Beta Ready

Keines dieser Kriterien darf offen sein. Kein Deployment ohne vollständige Checkliste.

### Gate 0 — Startup-Sicherheit
- [ ] `AILIZA_SECRET_KEY` ≥ 32 Zeichen erzwungen: Hard-Fail beim Start (nicht nur Warnung)
- [ ] `AILIZA_EXTERNAL_LLM_ENABLED=false` ist Default und dokumentiert
- [ ] TLS aktiv auf Produktion-URL (nginx/caddy Reverse Proxy)
- [ ] CORS `allow_origins` auf explizite Liste eingeschränkt (kein `*`)

### Gate 1 — Rollen & Zugriff
- [ ] `audit_viewer`-Rolle implementiert und im JWT-System registriert
- [ ] `audit_viewer` hat nur Lese-Zugriff auf Audit-Vault, keinen Admin-Zugriff
- [ ] Alle Admin-Endpunkte prüfen `Role.ADMIN` — kein `audit_viewer`-Zugriff auf Schreib-Ops
- [ ] Rollenprüfung: Alle aktiven Accounts und ihre Rollen dokumentiert

### Gate 2 — Tool-Gateway vollständig erzwungen
- [ ] `agent_runtime.py` ruft Tools **ausschließlich** über `guarded_tool_call`
- [ ] Direkter `execute_tool`-Aufruf ohne Gateway ist durch Code-Check verifiziert: nicht vorhanden
- [ ] Jeder Tool-Call produziert Audit-Event `tools.executed` oder `policy.decision`
- [ ] Unbekannte Tools erzeugen `PolicyDecision.BLOCK` + Audit-Event

### Gate 3 — Provider-Profil vollständig
- [ ] Kein externer Provider-Call ohne gültiges `ProviderProfile`
- [ ] `check_provider_policy()` wird vor **jedem** LLM-Call aufgerufen
- [ ] `avv_signed=False` → Provider darf nur `PUBLIC` Daten verarbeiten
- [ ] Jeder blockierte Provider-Call erzeugt Audit-Event `provider.blocked`

### Gate 4 — Audit-Vault Stufe 2
- [ ] SHA-256 Hash-Chain: jeder Eintrag referenziert Hash des Vorgängers
- [ ] Manipulationsprüfung: `GET /admin/audit/verify` prüft Kette
- [ ] WORM-Option: separates Readonly-Flag pro Audit-Tabelle
- [ ] Signatur-Stub: Vorbereitung für externe Signatur (kein externes System erforderlich für v1.0)

### Gate 5 — Memory-Governance
- [ ] Nutzer kann eigene Memory-Facts über API einsehen: `GET /memory/facts`
- [ ] Nutzer kann eigene Memory-Facts löschen: `DELETE /memory/facts/{id}`
- [ ] Frontend zeigt Memory-Status in Einstellungen
- [ ] Zweckbindung: `purpose`-Feld in jedem Fact, nicht überschreibbar

### Gate 6 — Human Oversight (Freigabe-UI)
- [ ] Frontend-Seite "Freigaben" zeigt offene Approval-Requests für Admin
- [ ] Admin kann Freigabe erteilen oder ablehnen aus dem Browser
- [ ] Ablehnung produziert Audit-Event `approval.rejected`
- [ ] Freigabe-UI zeigt: Tool, Risiko, Datenklasse, Zeitstempel

### Gate 7 — Tests & Integrität
- [ ] 100% der Regressionstests grün (aktuell: 635/635)
- [ ] Neuer Test: Gateway-Enforcement — direkter Tool-Call ohne Gateway schlägt fehl
- [ ] Neuer Test: Provider-Profil-Prüfung — unbekannter Provider → BLOCK
- [ ] Neuer Test: Audit-Vault Stufe 2 — Hash-Chain valide nach 5 Einträgen
- [ ] Neuer Test: `audit_viewer` kann lesen, nicht schreiben

---

## 3. Datenmodell: Provider-Profile

*Implementiert in `apps/backend/providers/provider_profiles.py`.*  
Hier das vollständige Schema als Referenz und Erweiterungsbasis.

```python
@dataclass
class ProviderProfile:
    # Identifikation
    provider_id: str              # "groq" | "anthropic" | "openrouter" | "local"
    name: str                     # Anzeigename
    profile_version: str          # Semver, z.B. "1.1.0"

    # Geografie & Transfer
    region: str                   # "EU" | "US" | "local"
    transfer_basis: TransferBasis # EU_INTERNAL | ADEQUACY_DECISION | SCC | BINDING_RULES | NONE
                                  # NONE → immer BLOCK

    # Vertragsgrundlage
    avv_signed: bool              # DSGVO Art. 28 — False → nur PUBLIC-Daten erlaubt

    # Erlaubte Verarbeitung
    allowed_data_classes: list[DataClass]
    allowed_use_cases: list[str]  # ["kmu_assistant", "summarization", ...] | ["all"]

    # Datenschutz-Eigenschaften
    logs_prompts: bool            # Speichert Provider Prompts? → wenn True: keine CONFIDENTIAL+
    used_for_training: bool       # Werden Daten für Training verwendet? → wenn True: nur PUBLIC

    # Steuerung
    active: bool                  # False → sofort BLOCK
    admin_disabled: bool          # Admin-Kill-Switch für einzelnen Provider
    failover_priority: int        # 0 = höchste Priorität

    # Metadaten
    notes: str
    tags: list[str]
```

### Fehlende Felder für v1.0 (Erweiterung erforderlich)

```python
    # Noch hinzuzufügen:
    avv_document_ref: str | None  # Pfad/URL zum AVV-Dokument
    avv_signed_date: date | None  # Datum der AVV-Unterzeichnung
    avv_expiry_date: date | None  # Ablaufdatum des AVV
    retention_days: int | None    # Aufbewahrungsfrist beim Provider
    deletion_confirmed: bool      # Löschbestätigung vertraglich zugesichert?
    subprocessors: list[str]      # Bekannte Subprozessoren
    data_residency_confirmed: bool # Datenstandort vertraglich bestätigt?
    last_review_date: date | None # Letztes Review
    blocked_reason: str           # Grund für admin_disabled=True
```

### Aktuelle Provider-Status

| Provider | AVV | Transfer | active | admin_disabled | Darf PII |
|---|---|---|---|---|---|
| local | — (kein AVV nötig) | EU_INTERNAL | ✅ | ✗ | ✅ alle |
| groq | ⚠️ Nicht unterzeichnet | SCC | ✅ | ✗ | 🔴 Nein (nur PUBLIC/INTERNAL) |
| anthropic | ⚠️ Nicht unterzeichnet | SCC | ✅ | ✗ | 🔴 Nein (nur PUBLIC/INTERNAL) |
| openrouter | ⚠️ Nicht vorhanden | SCC | ✗ | ✅ | 🔴 Nein (nur PUBLIC) |

---

## 4. Datenmodell: Capability Registry

*Implementiert in `apps/backend/capabilities/registry.py`.*

```python
@dataclass
class Capability:
    capability_id: str            # Eindeutige ID, z.B. "web_search"
    name: str                     # Anzeigename
    description: str              # Was tut diese Capability?
    target: DataTarget            # Wohin fließen Daten? (RAM | MEMORY | EXTERNAL_LLM | AUDIT | ...)
    allowed_data_classes: list[DataClass]  # Welche Datenklassen sind erlaubt?
    risk_level: RiskLevel         # LOW | MEDIUM | HIGH | CRITICAL
    requires_approval: bool       # Muss Mensch freigeben?
    external_call: bool           # Geht ein Netzwerkcall raus?
    gdpr_purpose: str             # Zweckbindung (Art. 5 DSGVO)
    enabled: bool                 # False → sofort BLOCK (kein Bypass)
    tags: list[str]
```

### Aktuelle Capabilities und Status

| Capability | Risk | Externer Call | Freigabe nötig | Enabled |
|---|---|---|---|---|
| `web_search` | MEDIUM | ✅ Ja (Tavily) | ✗ | ✅ |
| `web_fetch` | MEDIUM | ✅ Ja | ✗ | ✅ |
| `llm_call` | HIGH | ✅ Ja | ✗ | ✅ |
| `memory_store` | HIGH | ✗ | ✅ Ja | ✅ |
| `memory_read` | MEDIUM | ✗ | ✗ | ✅ |
| `skill_propose` | HIGH | ✗ | ✅ Ja | ✅ |
| `skill_execute` | MEDIUM | ✗ | ✗ | ✅ |
| `document_scan` | MEDIUM | ✗ | ✗ | ✅ |
| `audit_write` | LOW | ✗ | ✗ | ✅ |
| `messenger_receive` | MEDIUM | ✗ | ✗ | ✅ |
| `message_process` | LOW | ✗ | ✗ | ✅ |
| `messenger_send` | HIGH | ✅ Ja | ✅ Ja | ✅ |

### Fehlende Capabilities für v1.0

| Capability-ID | Beschreibung | Status |
|---|---|---|
| `memory_list` | Nutzer liest eigene Facts | 🔲 Fehlt |
| `memory_delete` | Nutzer löscht eigene Facts | 🔲 Fehlt |
| `incident_report` | Incident-Eintrag im Vault | 🔲 Fehlt |
| `approval_grant` | Admin erteilt Freigabe | 🔲 Fehlt |
| `approval_reject` | Admin lehnt Freigabe ab | 🔲 Fehlt |

---

## 5. Policy-Entscheidungsmodell

*Implementiert in `policy.py` + `gateway.py`. Hier das vollständige Entscheidungsmodell.*

### Entscheidungspfad (bei jedem Tool-Call)

```
Eingang: Tool-Name + Parameter + Datenklassen + Nutzer-Kontext
        ↓
[1] Capability-Check (registry.py)
    → Unbekannte Capability: BLOCK + Audit
    → Deaktivierte Capability: BLOCK + Audit
    → Verbotene Datenklasse: BLOCK + Audit
        ↓
[2] Provider-Profil-Check (provider_profiles.py)
    → Unbekannter Provider: BLOCK + Audit
    → inactive oder admin_disabled: BLOCK + Audit
    → AVV fehlt + Daten > PUBLIC: BLOCK + Audit
    → Transfer-Basis = NONE: BLOCK + Audit
    → Use-Case nicht freigegeben: BLOCK + Audit
        ↓
[3] Policy-Engine (policy.py)
    → data_governance.classify() ergibt verbotene Klasse: BLOCK
    → Kill-Switch = false und externer Call: BLOCK
    → CREDENTIALS/SPECIAL_CATEGORY: BLOCK immer
    → HR-Daten: requires_human_decision = True → BLOCK ohne Freigabe
        ↓
[4] Redaction (vor externem Call)
    → PII entfernen
    → Secrets maskieren
    → Audit: redaction.applied
        ↓
[5] Risikobewertung (approval.py)
    → Risiko < threshold: AUTO-APPROVE + Audit
    → Risiko ≥ threshold: APPROVAL_REQUIRED → Queue → warten
        ↓
[6] Ausführung (execute_tool)
    → Erfolg: Audit tools.executed
    → Fehler: Audit tools.error, nie Raw-Exception zum Client
        ↓
[7] Output-Check (streaming/safe_stream.py)
    → Sensible Muster im Output maskieren
    → Kein Stack-Trace zum Client
```

### Entscheidungsmatrix

| Situation | Entscheidung |
|---|---|
| Unbekannte Capability | `BLOCK` |
| Unbekannter Provider | `BLOCK` |
| `admin_disabled = True` | `BLOCK` |
| `AILIZA_EXTERNAL_LLM_ENABLED = false` | `BLOCK` (externer Call) |
| `TransferBasis.NONE` | `BLOCK` |
| AVV fehlt + Daten > PUBLIC | `BLOCK` |
| `DataClass.CREDENTIALS` | `BLOCK` immer |
| `DataClass.SPECIAL_CATEGORY` | `BLOCK` immer |
| `DataClass.HR` ohne menschliche Prüfung | `BLOCK` |
| Risiko HIGH ohne Freigabe | `APPROVAL_REQUIRED` |
| Kill-Switch false + externer Call | `BLOCK` |
| Alles grün | `ALLOW` oder `ALLOW_WITH_NOTICE` |

---

## 6. Rollen- und Freigabemodell

### Aktuelle Rollen

| Rolle | Wert | Kann |
|---|---|---|
| `user` | 0 | Chat, Dokument-Upload, eigene Runs sehen |
| `manager` | 1 | Wie user + Team-Ansichten (noch nicht implementiert) |
| `admin` | 2 | Audit-Vault lesen, User-Management, Freigaben erteilen |
| `dsb` | 3 | Wie admin, aber explizit für Datenschutzbeauftragte/n |

### Fehlende Rolle für v1.0

**`audit_viewer` (Wert: zwischen user=0 und admin=2)**

| Feld | Wert |
|---|---|
| Rolle | `audit_viewer` |
| IntEnum-Wert | 1.5 → als separater Wert: `AUDIT_VIEWER = 1` (manager auf 2, admin auf 3, dsb auf 4) |
| Kann | `GET /admin/audit/events`, `GET /admin/audit/export`, `GET /admin/audit/retention-report` |
| Kann nicht | User-Management, Approval-Erteilung, Konfigurationsänderungen |
| Zweck | Externe Prüfer, Datenschutzbeauftragte ohne Admin-Rechte |

**Implementierungsplan:**
```python
class Role(IntEnum):
    USER = 0
    AUDIT_VIEWER = 1   # NEU — nur Audit-Lesen
    MANAGER = 2        # Hochgestuft von 1
    ADMIN = 3          # Hochgestuft von 2
    DSB = 4            # Hochgestuft von 3
```

**Achtung:** IntEnum-Werte ändern sich → bestehende JWT-Tokens werden bei Neuausstellung korrekt gesetzt, aber `Role.from_str()` muss aktualisiert werden. Kein Breaking Change wenn `from_str()` string-basiert bleibt.

### Freigabe-Workflow

```
Nutzer startet Task mit riskantem Tool
        ↓
gateway.py: assess_risk() → risky=True
        ↓
create_approval_request() → Audit: approval.requested
        ↓
Frontend "Freigaben"-Seite (FEHLT) zeigt:
  - Tool, Risiko, Datenklasse, Zeitstempel
  - [Freigeben] [Ablehnen]
        ↓
Admin klickt [Freigeben]
→ Audit: approval.granted
→ execute_approved_tool()
        ↓
Admin klickt [Ablehnen]
→ Audit: approval.rejected
→ Nutzer erhält Fehlermeldung
```

---

## 7. Audit-Event-Schema

### Aktuell verwendete Events (Stufe 1)

| Event-Action | Trigger | Metadaten-Felder |
|---|---|---|
| `agent.run.started` | Agent-Run Start | `run_id`, `mode` |
| `agent.run.completed` | Agent-Run Ende | `run_id`, `status`, `steps_count` |
| `agent.degraded_missing_provider` | local_only wegen fehlendem Key | `run_id`, `tool`, `mode`, `reason` |
| `policy.decision` | Gateway-Policy-Check | `tool`, `decision`, `reason` |
| `approval.requested` | Freigabe angefordert | `approval_id`, `tool`, `risk` |
| `approval.auto` | Automatisch freigegeben | `tool`, `risk`, `approval_status` |
| `approval.executed` | Freigegebenes Tool ausgeführt | `approval_id`, `tool` |
| `tools.executed` | Tool erfolgreich ausgeführt | `tool`, `parameters` (typisiert, kein Inhalt) |
| `documents.scan` | Dokument hochgeladen | `file_type`, `decision`, `size_bytes` |
| `auth.login` | Login-Versuch | `user_id` (keine Passwörter) |
| `auth.logout` | Logout | `user_id` |

### Fehlende Events für v1.0

| Event-Action | Trigger | Metadaten (Pflicht) |
|---|---|---|
| `provider.blocked` | Provider-Check gescheitert | `provider_id`, `reason`, `data_class` |
| `capability.blocked` | Capability-Check gescheitert | `capability_id`, `reason`, `data_class` |
| `memory.stored` | Fact in Memory gespeichert | `tenant_id`, `purpose`, `ttl_days` (kein Inhalt) |
| `memory.deleted` | Fact gelöscht | `fact_id`, `reason`, `deleted_by` |
| `incident.detected` | Incident erkannt | `category`, `component`, `severity` |
| `incident.resolved` | Incident behoben | `incident_id`, `resolution` |
| `audit.verify.ok` | Hash-Chain Prüfung bestanden | `entries_checked`, `chain_valid` |
| `audit.verify.fail` | Hash-Chain Prüfung fehlgeschlagen | `first_broken_entry`, `expected_hash` |
| `approval.granted` | Admin erteilt Freigabe | `approval_id`, `granted_by`, `tool` |
| `approval.rejected` | Admin lehnt ab | `approval_id`, `rejected_by`, `reason` |
| `startup.secret_key_missing` | Kein/schwaches Secret beim Start | `component` |

### Verbotene Audit-Felder (niemals im Vault)

```python
_AUDIT_BLOCKED_FIELDS = frozenset({
    "task_content", "prompt", "input_summary", "password", "secret",
    "token", "totp", "backup_code", "credentials", "query_text",
    "message_content", "raw_input", "user_message",
})
```

### Audit-Vault Stufe 2: Hash-Chain-Schema

```python
@dataclass
class AuditEntry:
    id: int
    timestamp: datetime
    action: str
    tenant_id: str
    metadata: dict          # sanitized, kein Inhalt
    previous_hash: str      # SHA-256 des Vorgänger-Eintrags
    entry_hash: str         # SHA-256(id + timestamp + action + tenant_id + previous_hash)
    # Für v1.0: kein externe Signatur erforderlich
    # Für v1.1+: signature_stub: str | None  # Vorbereitung für HSM/externe Signatur
```

---

## 8. Modul-Freigabematrix

| Modul | Aktueller Status | v1.0-Freigabe möglich? | Voraussetzungen |
|---|---|---|---|
| Core Chat (local_only) | ✅ Aktiv | ✅ Ja | TLS, Secret-Key |
| Dokument-Scan | ✅ Aktiv | ✅ Ja | TLS, Secret-Key |
| Audit-Vault Stufe 1 | ✅ Aktiv | ✅ Ja | audit_viewer-Rolle |
| Audit-Vault Stufe 2 | 🔲 Fehlt | 🔲 Nicht vor Implementierung | Hash-Chain, Tests |
| Approval-System (API) | ✅ Aktiv | ✅ Ja | Freigabe-UI |
| Freigabe-UI (Frontend) | 🔲 Fehlt | 🔲 Nicht vor Implementierung | Gate 6 |
| Memory lesen (API) | ✅ Aktiv | ✅ Ja | Memory-UI |
| Memory schreiben | ✅ Aktiv (opt-in) | ✅ Ja | Memory-UI |
| Memory löschen (Nutzer) | ✅ API | 🟡 Ja mit UI | Memory-UI |
| Recherche (local_only) | ✅ Aktiv | ✅ Ja | — |
| Recherche mit Websuche | 🔲 Kein Provider | ⚠️ Erst nach AVV | Groq/Tavily AVV |
| LLM-Call extern (Groq) | 🔲 Kill-Switch | ⚠️ Erst nach AVV | Groq AVV + SCCs |
| LLM-Call extern (Anthropic) | 🔲 Kill-Switch | ⚠️ Erst nach AVV | Anthropic AVV |
| OpenRouter | 🔴 admin_disabled | 🔴 Blocked | Kein bekannter AVV |
| Buchhaltung | 🔴 Nicht implementiert | 🔴 responsibility_handoff | Rechtsprüfung, externes System |
| HR/Personal | 🔴 Nicht implementiert | 🔴 blocked | AI-Act Hochrisiko-Prüfung |
| Gesundheitsdaten | 🔴 Verboten | 🔴 prohibited | — |
| Vertragsfreigabe automatisch | 🔴 Verboten | 🔴 prohibited | — |
| Unkontrollierte Websuche | 🔴 Verboten | 🔴 prohibited | — |

---

## 9. Liste technischer Sperren

Folgende Mechanismen blockieren v1.0 **technisch** — kein Bypass über Konfiguration allein.

### Bereits technisch gesperrt (erzwungen durch Code)

| Sperre | Mechanismus | Datei |
|---|---|---|
| Externer LLM-Call ohne Kill-Switch | `enforce_kill_switch()` wirft Exception | `kill_switch.py` |
| Unbekannter Provider | `check_provider_policy()` → BLOCK | `provider_profiles.py` |
| Unbekannte Capability | `check_capability()` → BLOCK | `capabilities/registry.py` |
| CREDENTIALS im Audit | `_METADATA_BLOCKED_KEYS` filtert | `audit/vault.py` |
| HR/CREDENTIALS in Memory | `_BLOCKED_CLASSES` in `store_fact()` | `reflection/reflection_skill.py` |
| OpenRouter aktiv nutzen | `admin_disabled=True` | `provider_profiles.py` |
| Stack-Trace zum Client | Exception-Handler in `main.py` | `main.py` |
| DiagBlock ohne Debug-Flag | `DEBUG_ERRORS`-Konstante | `AgentChat.jsx` |

### Noch nicht vollständig technisch erzwungen (Lücken)

| Lücke | Risiko | Beschreibung |
|---|---|---|
| `agent_runtime.py` → direkter Tool-Aufruf | 🔴 Hoch | `plan_tool_calls()` + direkter `tool_executor`-Call bypassed `guarded_tool_call` teilweise |
| Schwaches Secret-Key startet trotzdem | 🔴 Hoch | Nur Warnung, kein Hard-Fail |
| AVV `False` blockiert nur Daten > PUBLIC | 🟡 Mittel | Wenn PUBLIC-Daten via Groq: erlaubt ohne AVV. Korrekt, aber zu dokumentieren |
| Memory-Löschen ohne Nutzer-Nachweis | 🟡 Mittel | Kein DSGVO-Art.-17-Prozess-Nachweis im Audit |

### Dauerhaft gesperrt (prohibited) — kein Aktivierungsweg

```python
_PROHIBITED_USE_CASES = frozenset({
    "autonomous_hr_decision",         # HR-Entscheidungen autonom
    "autonomous_accounting_decision",  # Buchhaltungsentscheidungen autonom
    "automatic_contract_approval",     # Vertragsfreigabe ohne Mensch
    "health_data_processing",          # Gesundheitsdaten (DSGVO Art. 9)
    "uncontrolled_web_search",         # Websuche ohne Policy
    "training_on_customer_data",       # Provider-Training auf Kundendaten
    "provider_without_avv",            # PII an Provider ohne AVV
    "provider_without_deletion_concept", # Provider ohne Löschkonzept
})
```

---

## 10. Konkrete Reihenfolge der Umsetzung

Priorisiert nach: Sicherheitsrelevanz > Compliance > Nutzerfreundlichkeit

### Woche 1 — Kritische Sicherheitslücken

| Schritt | Datei | Aufwand |
|---|---|---|
| 1.1 | `auth/rbac.py`: `audit_viewer`-Rolle hinzufügen | Klein |
| 1.2 | `main.py`: Audit-Vault-Endpunkte für `audit_viewer` öffnen (nur lesen) | Klein |
| 1.3 | `main.py`: Hard-Fail bei schwachem `AILIZA_SECRET_KEY` beim Start | Klein |
| 1.4 | `agent_runtime.py`: Tool-Calls über `guarded_tool_call` erzwingen | Mittel |

### Woche 2 — Audit-Vault Stufe 2

| Schritt | Datei | Aufwand |
|---|---|---|
| 2.1 | `database.py`: `previous_hash` + `entry_hash` Spalten zur `audit_logs`-Tabelle | Mittel |
| 2.2 | `database.py`: `write_audit_entry()` berechnet und speichert Hash-Chain | Mittel |
| 2.3 | `audit/vault.py`: `verify_audit_chain()` Funktion | Mittel |
| 2.4 | `main.py`: `GET /admin/audit/verify` Endpunkt | Klein |
| 2.5 | Tests: Hash-Chain valide, Manipulation erkennen | Mittel |

### Woche 3 — Memory-Governance UI

| Schritt | Datei | Aufwand |
|---|---|---|
| 3.1 | `main.py`: `GET /memory/facts` für eingeloggten Nutzer | Klein |
| 3.2 | `main.py`: `DELETE /memory/facts/{id}` mit Audit-Event | Klein |
| 3.3 | Frontend: Memory-Status in Einstellungen-Seite | Mittel |
| 3.4 | Audit-Events: `memory.stored`, `memory.deleted` | Klein |

### Woche 4 — Freigabe-UI

| Schritt | Datei | Aufwand |
|---|---|---|
| 4.1 | `main.py`: `GET /admin/approvals` (offene Requests) | Klein |
| 4.2 | Frontend: "Freigaben"-Seite für Admin | Mittel |
| 4.3 | Frontend: [Freigeben] / [Ablehnen] Buttons | Klein |
| 4.4 | Audit-Events: `approval.granted`, `approval.rejected` | Klein |

### Woche 5 — Produktions-Härtung

| Schritt | Datei/Ort | Aufwand |
|---|---|---|
| 5.1 | CORS: `allow_origins` auf explizite Liste | Klein |
| 5.2 | TLS-Konfiguration: nginx/caddy Reverse Proxy | Extern |
| 5.3 | Backup-Strategie: Cron-Job für SQLite-Sicherung | Klein |
| 5.4 | Incident-Events: `incident.detected`, `incident.resolved` im Schema | Klein |
| 5.5 | Fehlende Audit-Events (`provider.blocked`, `capability.blocked`) | Klein |

### Nach v1.0 — Geplant aber geblockt

| Feature | Status | Voraussetzung |
|---|---|---|
| Externe Provider mit PII | ⚠️ Geplant | AVV Groq + Anthropic |
| Websuche (Tavily) | ⚠️ Geplant | Tavily AVV + SCCs |
| Buchhaltungs-Modul | 🔲 Offen | Rechtsprüfung + Nutzerfreigabe |
| HR-Modul | 🔴 Blocked | AI-Act Hochrisiko-Konformitätsprüfung |
| Audit-Vault Stufe 3 (externe Signatur) | 🔲 Geplant | HSM oder externer Dienst |

---

## Widersprüche und Ehrliche Bewertung

| Thema | Befund |
|---|---|
| `eu_compliance_policy.md` behauptet "AES-256" | Nicht implementiert. SQLite ohne Feld-Verschlüsselung. Als `⚠️ prüfen` in TOM-Katalog markiert. |
| CORS `allow_origins=["*"]` | Inakzeptabel für Produktion. Noch nicht geändert. |
| `dsb`-Rolle hat IntEnum-Wert 3 | Wenn `audit_viewer` als 1 eingeführt wird, müssen alle Werte verschoben werden. Bestehende Tokens sind string-basiert → kein Breaking Change. |
| `avv_signed=False` bei Groq/Anthropic | Profile sind `active=True`. Das ist korrekt — aber nur wenn Kill-Switch aktiv ist. Ohne Kill-Switch-Freigabe kämen Calls durch. Kill-Switch muss Hard-Fail sein. |
| OpenRouter `logs_prompts=True` | Korrekt markiert. `admin_disabled=True`. Bleibt gesperrt. |

---

*Stand: 2026-06-23 — Kein Anspruch auf vollständige DSGVO- oder AI-Act-Konformität.*  
*Dieses Dokument ist eine Arbeitsgrundlage, keine finale Rechtsberatung.*
