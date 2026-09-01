# AILIZA — BYOK-Architektur (Bring Your Own Key)

Stand: 31.08.2026. **Reiner Architekturentwurf, nicht umgesetzt.** Keine der
hier beschriebenen Tabellen, Endpunkte oder UI-Elemente existiert im Code.
Jede Aussage unten ist entweder **VERIFIZIERT** (gegen den echten Code
geprüft) oder **VORSCHLAG** (Entwurf, noch nicht entschieden). Technische
Profilwerte sind kein Beleg fuer einen tatsaechlich abgeschlossenen Vertrag.
Verifizierte Codeaussagen beziehen sich auf den gemeinsamen Basis-Commit
`e591053`; nach einem Rebase muessen sie erneut gegen den dann aktuellen
Stand geprueft werden.

## 1. Ziel

Jede Kundenfirma nutzt ihren eigenen Anthropic-/Groq-/OpenAI-API-Key statt
eines gemeinsamen Betreiber-Keys: eigener Vertrag, eigene Abrechnung, klare
Verantwortungstrennung. Karos aktueller Key bleibt ausschließlich für ihre
eigene Organisation/Tests.

Nicht-Ziele dieses Dokuments: keine Provider-Vertragspruefung, keine
Produktionsfreigabe, kein UI-Redesign ausserhalb des Einrichtungsablaufs und
keine Umsetzung der beschriebenen Tabellen oder APIs.

## 2. Verifizierter Ist-Zustand

- `ProviderProfile` (`apps/backend/providers/provider_profiles.py`) ist
  **global pro Anbieter**, nicht pro Mandant. Keine Datenbanktabelle für
  mandantenspezifische Keys existiert.
- Aktuelle `avv_signed`-Werte je Provider (technischer Snapshot einer
  Betreiber-Entscheidung vom 2026-07-06, gilt nur fuer Karos eigene
  Organisation und ist kein aktueller Vertragsnachweis):
  Groq `False`, OpenAI `True`, Anthropic `True`, OpenRouter `False`,
  Lokal (Fast-Path) `True`.
- **Sicherheitsrelevanter Fund im Basis-Commit:**
  `apps/frontend/index.html` enthält ein
  verstecktes Entwicklerfeld (`class="dev-controls" style="display:none"`)
  mit `saveKey()`, das einen eingegebenen Key unverschlüsselt in
  `localStorage` unter `ailiza_key_<provider>` ablegt. Dieser Wert wird
  vom Provider-Orchestrator **nirgends gelesen** (Volltextsuche über
  `apps/backend/` ergibt null Treffer) — totes, aber unsicheres Feld.
  **Muss vor jeder BYOK-Einführung entfernt und aus bestehendem
  Browser-Speicher bereinigt werden**, nicht erst danach. Diese Doku-PR
  erledigt die Bereinigung ausdruecklich nicht.
- Der Orchestrator hat `tenant_id` im Ausführungskontext verfügbar, nutzt
  sie aber nicht zur Schlüsselauswahl. Groq/OpenAI/Anthropic-Adapter lesen
  ausschließlich globale Umgebungsvariablen (`GROQ_API_KEY` etc.).

## 3. UX-Vorschlag: sofortiger, einfacher Einrichtungs-Assistent

Nur für mandantenbezogen berechtigte Firmen-Admins mit unvollständigem
Setup, nie für normale Beschäftigte. Die vorhandene globale Rolle `ADMIN`
darf dafuer nicht ungeprueft wiederverwendet werden (offene Entscheidung in
Abschnitt 12):

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
`last_test_status`, `last_tested_at`, `active_credential_id` (nullable),
`created_at`, `updated_at`. Unique Constraint: `tenant_id + provider_id`.

**`tenant_provider_credentials`** — streng geschütztes Schlüsselmaterial:
`id`, `tenant_id`, `provider_id`, `ciphertext`, `key_id`,
`encryption_version`, `credential_version`, `wrapped_data_key`,
`credential_fingerprint` (ausschliesslich gekuerzter HMAC, nie Zeichen aus
dem Key), `provider_account_hint`, `status`
(`pending`/`valid`/`invalid`/`superseded`/`revoked`), `created_by`,
`created_at`, `verified_at`, `superseded_at`, `revoked_at`.

Verbindliche Invarianten im Vorschlag:

- Unique `tenant_id + provider_id + credential_version`;
- Unique `tenant_id + provider_id + id` als Referenzziel der
  zusammengesetzten Fremdschluesselbeziehung (zusaetzlich zum Primaerschluessel
  auf `id`);
- zusammengesetzter Fremdschluessel von Settings
  (`tenant_id`, `provider_id`, `active_credential_id`) auf die zugehoerige
  Credential-Zeile, damit kein fremder Tenant referenziert werden kann;
- hoechstens eine `valid`-Credential je Tenant/Provider (partieller Unique
  Index in PostgreSQL);
- `active` ist nur mit `dpa_status=confirmed`, erlaubten Datenklassen und
  einer `valid`-Credential zulaessig; die Datenbank schuetzt die strukturellen
  Invarianten, der Service den fachlichen Zustandsautomaten.

## 5. Verschlüsselung

Die bestehende AES-256-GCM-Feldverschlüsselung reicht für Credentials
**nicht** aus (gemeinsamer abgeleiteter Hauptschlüssel für alle Felder,
kein `key_id` für Rotation, kein Binden des Ciphertexts an Tenant/Provider,
Klartext-Legacy-Werte werden akzeptiert). Für Credentials vorgeschlagen:

- eigener Credential-Master-Key, getrennt von Session-/Feldverschlüsselung;
- Envelope Encryption: zufaelliger Data-Encryption-Key (DEK) je Credential;
  der DEK wird mit einem getrennt verwahrten Key-Encryption-Key (KEK) aus
  KMS/Secret-Management verschluesselt;
- AES-GCM mit AAD aus `tenant_id` + `provider_id` + Credential-ID + Version;
- eigene zufällige Nonce je Datensatz, keine Klartext-Kompatibilität;
- fail-closed ohne gültiges Schlüsselmaterial;
- Rotation ueber `key_id`/Version; Entschluesselung nur unmittelbar vor dem
  Provider-Aufruf; kein Endpunkt zum Zurücklesen des Klartexts.

Schreibrechte nur ueber eine neue tenant-gebundene Capability, vorgeschlagen
`tenant_provider_manage`. Der Bezeichner folgt damit der bestehenden
`lower_snake_case`-Konvention der Capability-IDs in
`apps/backend/capabilities/registry.py`. Leserechte auf Klartext: keine
Nutzerrolle — nur ein interner, serverseitiger Credential-Resolver. Auch
Betreiber-Admins erhalten keinen Klartext-Leseweg.

Ein Eintrag in der statischen Capability-Registry allein ist noch keine
Berechtigung. Die spaetere Autorisierung muss bei jedem Schreib- und
Testaufruf drei Bedingungen gemeinsam pruefen: Capability global aktiviert,
Tenant aus dem authentifizierten Sessionkontext und aktive Zuweisung
`user_id + tenant_id + capability_id`. Eine `tenant_id` aus Body, Query oder
Pfad darf die Sessionbindung niemals ersetzen. Damit verleiht weder die
globale Rolle `ADMIN` noch der Registry-Eintrag automatisch Zugriff auf einen
Kunden-Tenant.

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

Der Resolver akzeptiert keine `tenant_id` aus Request-Body oder Query,
cached keinen Klartext und liefert nur ein kurzlebiges In-Memory-Objekt an
genau den ausgewaehlten Adapter. Fehlerantworten und Metriken enthalten weder
Ciphertext noch Provider-Key-Fragmente.

## 7. Credential-Zustandsautomat und Rotation (Vorschlag)

Erstanlage: `pending` → isolierter Verbindungstest → `valid` oder `invalid`.
Aktivierung der Tenant-Einstellung erfolgt erst nach erfolgreichem Test und
vollstaendiger fachlicher Freigabe. Ein Verbindungstest nutzt nur eine
fest definierte, nicht personenbezogene Provider-Anfrage; Kundentext wird
dabei niemals uebertragen.

Rotation ist atomar und konkurrenzsicher:

1. neue Version als `pending` speichern;
2. ausserhalb der Aktivierungs-Transaktion testen;
3. in einer DB-Transaktion sperren, alte `valid`-Version auf `superseded`
   setzen, neue Version auf `valid` setzen und `active_credential_id`
   umhaengen;
4. bei Konflikt oder Fehler bleibt die bisherige Version aktiv;
5. Widerruf setzt Providerstatus sofort auf `blocked`, bevor weitere
   Aufrufe beginnen.

## 8. Minimale Admin-API (Vorschlag)

- `GET /tenant/providers` und `GET /tenant/providers/{provider}/status`:
  ausschliesslich Status, Version, Zeitpunkte und HMAC-Fingerprint;
- `POST /tenant/providers/{provider}/credentials`: Key nur im TLS-geschuetzten
  Request-Body, niemals in URL, Antwort, Audit oder Fehlertext;
- `POST .../test`, `POST .../activate`, `POST .../rotate`, `POST .../revoke`:
  tenant-gebundene Capability, CSRF-Schutz bei Cookie-Auth, Rate-Limit,
  atomare Zustandspruefung und minimiertes Audit;
- kein `GET`-Endpunkt fuer Ciphertext, wrapped DEK oder Klartext.

Der Verbindungstest erhaelt ein eigenes, serverseitiges Missbrauchslimit,
das vor jedem Provider-Aufruf greift: konfigurierbarer sicherer Startwert
von hoechstens 3 Versuchen je 5 Minuten und 20 je 24 Stunden pro
`tenant_id + provider_id`, zusaetzlich hoechstens ein gleichzeitig laufender
Test pro Tenant/Provider. Auch fehlgeschlagene Provider-Aufrufe zaehlen.
Ueberschreitungen antworten mit `429` und `Retry-After` und erzeugen nur einen
minimierten Reason-Code im Audit. In einer Mehrinstanz-Umgebung muss der
Zaehler in einem gemeinsamen Store liegen; ein rein prozesslokaler Zaehler
waere umgehbar. Rohschluessel und Provider-Antworten sind weder Bestandteil
des Limit-Schluessels noch des Audits.

## 9. Uebergang fuer Karos eigene Organisation

Der globale Betreiber-Key gilt nur für Karos Betreiber-/Testorganisation,
in entsprechend konfigurierter Umgebung, auditierbar, ohne automatischen
Fallback aus einem Kunden-Tenant. Langfristig sollte auch Karos
Organisation in dasselbe Tenant-Credential-Modell überführt werden.

## 10. Testplan (Auszug)

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

Zusaetzlich: parallele Rotation aktiviert genau eine Version; ein
`active_credential_id` eines anderen Tenants/Providers wird von DB und
Service abgewiesen; Verbindungstest sendet nur die feste synthetische
Anfrage; globale `ADMIN`-Rolle allein genuegt nicht; Listen-/Status-Endpunkte
enthalten weder Ciphertext noch wrapped DEK; CSRF-Prefix-Angriffe und fehlende
Origin/Referer werden blockiert; das Verbindungstest-Limit gilt tenantweit
auch bei wechselnden Nutzern und Instanzen, zaehlt Fehlversuche, blockiert
parallele Tests und liefert `429` mit `Retry-After`; Backups sind ohne
getrennten KEK wertlos, Restore mit korrektem KEK funktioniert dokumentiert.

## 11. Vorgeschlagene Arbeitspakete (Reihenfolge)

1. Unsicheren `localStorage`-Key-Pfad entfernen (eigenständig, unabhängig
   vom Rest — sollte nicht auf den restlichen BYOK-Umbau warten). Wird dieses
   Arbeitspaket vor der Doku gemergt, ist Abschnitt 2 beim Rebase als
   historischer Basisbefund/statusmaessig zu aktualisieren.
2. Die drei Owner-Entscheidungen aus Abschnitt 12 dokumentieren.
3. Credential-Bedrohungsmodell und Zustandsautomat abnehmen.
4. Tabellen, Constraints + Alembic-Migration.
5. Credential-Verschluesselung mit Rotation.
6. Tenant-isolierte Admin-API und Capability.
7. Anthropic-Credential-Resolver anbinden (Pilot, siehe Abschnitt 12).
8. Orchestrator fail-closed auf Tenant-Credentials umstellen.
9. Admin-Onboarding-Assistent integrieren.
10. Sicherheits-, Tenant- und Browsertests inklusive Rotation/Race Tests.
11. Danach OpenAI, spaeter Groq (siehe Abschnitt 12).

## 12. Offene Entscheidungen — NUR Karo

1. **Berechtigungsmodell:** Empfehlung: neue tenant-gebundene Capability
   `tenant_provider_manage` fuer explizit zugewiesene Firmen-Admins; die
   globale Rolle `ADMIN` allein reicht nicht. Optionaler Betreiberzugriff nur
   als zeitlich begrenzter, begruendeter Break-Glass-Vorgang ohne Klartextzugriff.
2. **Master-Key-/KMS-Betrieb:** Empfehlung: verwaltetes KMS mit versioniertem
   KEK und Envelope Encryption. Falls die gewaehlte Plattform kein KMS
   anbietet, muss Karo vor Umsetzung einen konkreten externen KMS-/Secret-
   Management-Weg, Rotation, Backup-Trennung und Notfallzugriff festlegen;
   ein im Repo oder in der Datenbank gespeicherter Master-Key ist unzulaessig.
3. **Pilotprovider:** Empfehlung Anthropic zuerst, weil der Adapter vorhanden
   ist und ein einzelner Durchstich das Risiko begrenzt. Voraussetzung ist
   ein zum Pilotzeitpunkt erneut gepruefter, organisationsbezogener DPA-/
   Transfernachweis. OpenAI danach; Groq erst nach fachlicher Klaerung.

### Entscheidungsprotokoll vor Implementierungsstart

| ID | Status | Empfohlene Entscheidung | Vor Umsetzung zu dokumentieren |
|---|---|---|---|
| BYOK-OWNER-1 Berechtigung | **OFFEN — NUR Karo** | `tenant_provider_manage` mit expliziter Tenant-Zuweisung | Zuweisungsquelle, erlaubte Firmen-Admin-Rolle, Entzug, Break-Glass-Ablauf und Audit-Reason-Codes |
| BYOK-OWNER-2 Schluesselbetrieb | **OFFEN — NUR Karo** | verwaltetes KMS, versionierter KEK, Envelope Encryption | Dienst/Region, Key-ID-Konzept ohne Secretwert, Rotationsintervall, Backup-Trennung, Wiederanlauf- und Notfallverfahren |
| BYOK-OWNER-3 Pilot | **OFFEN — NUR Karo** | Anthropic bedingt als erster Durchstich | aktueller organisationsbezogener AVV/DPA-/Transferbeleg, erlaubte Datenklassen, Loesch-/Trainingseinstellungen und Kostenlimit |

Eine Entscheidung gilt erst als getroffen, wenn Status, Datum,
verantwortliche Rolle und ein nicht sensibles Belegziel dokumentiert sind.
Personennamen, Vertragsinhalte, Keys und KMS-Geheimnisse gehoeren nicht in
diese Datei.

Ohne diese drei Entscheidungen beginnt keine BYOK-Umsetzung. Die unabhaengige
Entfernung des toten Browser-Key-Pfads darf und soll vorher erfolgen.
