# AILIZA — BYOK-Architektur (Bring Your Own Key)

Stand: 30.08.2026. **Reiner Architekturentwurf, nicht umgesetzt.** Keine der
hier beschriebenen Tabellen, Endpunkte oder UI-Elemente existiert im Code.
Jede Aussage unten ist entweder **VERIFIZIERT** (gegen den echten Code
geprüft) oder **VORSCHLAG** (Entwurf, noch nicht entschieden).

## 1. Ziel

Jede Kundenfirma nutzt ihren eigenen Anthropic-/Groq-/OpenAI-API-Key statt
eines gemeinsamen Betreiber-Keys: eigener Vertrag, eigene Abrechnung, klare
Verantwortungstrennung. Karos aktueller Key bleibt ausschließlich für ihre
eigene Organisation/Tests.

## 2. Verifizierter Ist-Zustand

- `ProviderProfile` (`apps/backend/providers/provider_profiles.py`) ist
  **global pro Anbieter**, nicht pro Mandant. Keine Datenbanktabelle für
  mandantenspezifische Keys existiert.
- Aktuelle `avv_signed`-Werte je Provider (Betreiber-Entscheidung
  2026-07-06, gilt nur für Karos eigene Organisation):
  Groq `False`, OpenAI `True`, Anthropic `True`, OpenRouter `False`,
  Lokal (Fast-Path) `True`.
- **Sicherheitsrelevanter Fund:** `apps/frontend/index.html` enthält ein
  verstecktes Entwicklerfeld (`class="dev-controls" style="display:none"`)
  mit `saveKey()`, das einen eingegebenen Key unverschlüsselt in
  `localStorage` unter `ailiza_key_<provider>` ablegt. Dieser Wert wird
  vom Provider-Orchestrator **nirgends gelesen** (Volltextsuche über
  `apps/backend/` ergibt null Treffer) — totes, aber unsicheres Feld.
  **Muss vor jeder BYOK-Einführung entfernt werden**, nicht erst danach.
- Der Orchestrator hat `tenant_id` im Ausführungskontext verfügbar, nutzt
  sie aber nicht zur Schlüsselauswahl. Groq/OpenAI/Anthropic-Adapter lesen
  ausschließlich globale Umgebungsvariablen (`GROQ_API_KEY` etc.).

## 3. UX-Vorschlag: sofortiger, einfacher Einrichtungs-Assistent

Nur für Firmen-Admins mit unvollständigem Setup, nie für normale
Beschäftigte:

1. `/auth/me` bestimmt Nutzer, Tenant, Rolle.
2. Firmen-Admin + unvollständiges Setup → `/provider-onboarding/status`
   wird geladen, Einrichtungsdialog öffnet sich sofort.
3. Normale Nutzer sehen bei Bedarf nur: „Die KI-Anbieter werden gerade von
   Ihrer Administration eingerichtet." — kein Key-Eingabe-Popup, betroffene
   Funktionen bleiben geschlossen.

Dialogschritte (eine Frage gleichzeitig): Anbieter wählen → Vertrag
bestätigen → Schlüssel hinterlegen → Verbindung prüfen → Datenfreigabe
festlegen → Aktivieren. „Später einrichten" ist möglich, Provider bleibt
dann deaktiviert, Assistent erscheint beim nächsten Admin-Login erneut
(innerhalb derselben Sitzung reicht ein dauerhafter Hinweis statt
wiederholter Popups).

## 4. Datenmodell (Vorschlag, zwei getrennte Tabellen)

**`tenant_provider_settings`** — nicht geheime fachliche Konfiguration:
`id`, `tenant_id`, `provider_id`, `status` (`draft`/`verification_pending`/
`active`/`blocked`/`revoked`), `business_account_confirmed_at`,
`dpa_status` (`not_confirmed`/`confirmed`/`expired`/`revoked`),
`dpa_confirmed_at`, `dpa_confirmed_by`, `allowed_data_classes`,
`allowed_use_cases`, `admin_approved_at`, `admin_approved_by`,
`last_test_status`, `last_tested_at`, `credential_version`, `created_at`,
`updated_at`. Unique Constraint: `tenant_id + provider_id`.

**`tenant_provider_credentials`** — streng geschütztes Schlüsselmaterial:
`id`, `tenant_id`, `provider_id`, `ciphertext`, `key_id`,
`encryption_version`, `credential_fingerprint` (nur wenige nicht geheime
Zeichen oder HMAC, nie der volle Key), `provider_account_hint`, `status`
(`pending`/`valid`/`invalid`/`revoked`), `created_by`, `created_at`,
`verified_at`, `rotated_at`, `revoked_at`.

## 5. Verschlüsselung

Die bestehende AES-256-GCM-Feldverschlüsselung reicht für Credentials
**nicht** aus (gemeinsamer abgeleiteter Hauptschlüssel für alle Felder,
kein `key_id` für Rotation, kein Binden des Ciphertexts an Tenant/Provider,
Klartext-Legacy-Werte werden akzeptiert). Für Credentials vorgeschlagen:

- eigener Credential-Master-Key, getrennt von Session-/Feldverschlüsselung;
- bevorzugt KMS/Secret-Management des Hosting-Anbieters, alternativ
  Envelope Encryption;
- AES-GCM mit AAD aus `tenant_id` + `provider_id` + Credential-ID + Version;
- eigene zufällige Nonce je Datensatz, keine Klartext-Kompatibilität;
- fail-closed ohne gültiges Schlüsselmaterial;
- Rotation über `key_id`/Version; Entschlüsselung nur unmittelbar vor dem
  Provider-Aufruf; kein Endpunkt zum Zurücklesen des Klartexts.

Schreibrechte nur `ADMIN`. Leserechte auf Klartext: keine Nutzerrolle —
nur ein interner, serverseitiger Credential-Resolver.

## 6. Provider-Orchestrator (Ziel-Ablauf)

```
Anfrage → tenant_id aus geprüftem Sessionkontext (nie aus Frontendfeld)
        → globale Registry + ProviderProfile prüfen
        → Tenant-Providerstatus prüfen
        → DPA-/Datenklassenstatus prüfen
        → gültige Credential-Version auflösen
        → Schlüssel kurzzeitig entschlüsseln → Provider aufrufen
        → Schlüsselreferenz verwerfen
```

Regeln: Tenant-Einstellungen dürfen das globale `ProviderProfile` nur
einschränken, nie erweitern. Kein gültiger Key/DPA-Status → Provider ist
kein Kandidat. Ungültiger/widerrufener Key → fail-closed. Failover nur auf
für denselben Tenant vollständig eingerichtete Anbieter — kein Rückfall
auf Karos globalen Betreiber-Key für Kundenfirmen. Audit enthält nur
Tenant, Provider, Status, Reason-Code, Credential-Version — nie den
Schlüssel oder die Provider-Antwort.

## 7. Übergang für Karos eigene Organisation

Der globale Betreiber-Key gilt nur für Karos Betreiber-/Testorganisation,
in entsprechend konfigurierter Umgebung, auditierbar, ohne automatischen
Fallback aus einem Kunden-Tenant. Langfristig sollte auch Karos
Organisation in dasselbe Tenant-Credential-Modell überführt werden.

## 8. Testplan (Auszug)

Popup nur für Admin mit unvollständigem Setup, nie anonym/normale
Nutzer/Manager/DSB; kein erneutes Popup bei vollständigem Setup; „Später"
aktiviert nichts; Key erscheint nie in Browser-Speicher/API-Antwort/
Log/Audit; fremder Tenant kann Credential nicht sehen/ersetzen/testen/
widerrufen; manipulierter Ciphertext wird abgewiesen; falscher Master-Key
→ fail-closed; Rotation lässt nur neue Version aktiv; Widerruf/DPA-Widerruf
stoppen neue Aufrufe sofort; Tenant-Konfiguration kann globale
Datenklassen nicht erweitern; Failover nutzt nie den Key eines anderen
Tenants; Betreiber-Key wird bei Kunden-Tenants nie verwendet; Backup/
Restore erhalten verschlüsselte Credentials, nie den Master-Key.

## 9. Vorgeschlagene Arbeitspakete (Reihenfolge)

1. Unsicheren `localStorage`-Key-Pfad entfernen (eigenständig, unabhängig
   vom Rest — sollte nicht auf den restlichen BYOK-Umbau warten).
2. Credential-Bedrohungsmodell und Statusautomat festlegen.
3. Tabellen + Alembic-Migration.
4. Credential-Verschlüsselung mit Rotation.
5. Tenant-isolierte Admin-API.
6. Anthropic-Credential-Resolver anbinden (Pilot, siehe Abschnitt 10).
7. Orchestrator fail-closed auf Tenant-Credentials umstellen.
8. Admin-Onboarding-Assistent integrieren.
9. Sicherheits-, Tenant- und Browsertests.
10. Danach OpenAI, später Groq (siehe Abschnitt 10).

## 10. Offene Entscheidungen — NUR Karo

1. **Pilotprovider:** Empfehlung Anthropic zuerst (DPA bereits dokumentiert,
   Adapter vorhanden, ein klarer Durchstich statt gleichzeitiger Änderung
   aller Provider). OpenAI danach. Groq erst, wenn dessen DPA-/AVV-Status
   fachlich geklärt ist.
2. **Master-Key-/KMS-Betrieb:** welcher Schlüsselverwahrungsweg (Hosting-
   KMS vs. selbst verwaltete Envelope Encryption) tatsächlich eingesetzt
   wird — abhängig vom gewählten Hosting/Betrieb.

Ohne diese zwei Entscheidungen beginnt keine Umsetzung.
