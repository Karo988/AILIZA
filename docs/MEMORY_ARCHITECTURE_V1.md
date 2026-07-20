# AILIZA — Gedächtnis-Architektur v1 (Konzept, kein Code)

Stand: 20.07.2026 · Phase 0 (Bestandsaufnahme) + Konzeptvorschlag · **Noch nicht gebaut, nur Plan.**

---

## 1. Bestandsaufnahme: 17 vorhandene Tabellen

Einfach erklärt: Was AILIZA heute schon speichert, in drei Gruppen.

### Gruppe A — Nutzer-Inhalte (das eigentliche "Gedächtnis")
| Tabelle | Was drin ist | Verschlüsselt? |
|---|---|---|
| `users` | Login-Daten, Passwort-Hash | Passwort ist Hash, Rest Klartext |
| `user_projects` | Projekte des Nutzers | Ja (AES-256, seit Teilschritt 2) |
| `user_chats` | Chat-Nachrichten | Ja (AES-256) |
| `totp_secrets` / `totp_backup_codes` | 2FA-Geheimnisse | Ja (eigene Verschlüsselung) |
| `messenger_bindings` | Telegram-Verknüpfung | Klartext (nur IDs, keine Nachrichteninhalte) |

### Gruppe B — Betriebs-/Sicherheits-Protokolle (kein Nutzer-Gedächtnis)
| Tabelle | Was drin ist | Retention-Feld? |
|---|---|---|
| `audit_logs` | Nur Aktions-Codes + Hash-Kette, nie Inhalte | Nein |
| `security_logs` | Sicherheitsvorfälle, nur Codes | Ja |
| `performance_logs` | Latenz-Messwerte | Ja |
| `cost_logs` | Token-/Kostenzahlen | Ja |
| `approval_requests` | Freigabe-Anfragen (Text der Anfrage, nicht die Nutzerdaten selbst) | Ja |
| `agent_runs` | Aufgaben-Status, Ergebnis-Metadaten | Nein |
| `kill_switch_state` | Ein/Aus-Zustand | Nein |
| `routing_proposals` | Interne Modell-Routing-Vorschläge | Nein |
| `feedback` | Daumen hoch/runter zu Antworten | Nein |

### Gruppe C — "Echtes" KI-Gedächtnis (Ansatz vorhanden, kaum genutzt)
| Tabelle | Was drin ist | Status |
|---|---|---|
| `reflection_facts` | Einzelne "gelernte Fakten" über einen Nutzer, mit Datenklasse markiert | Existiert, aber **Opt-in, kaum verdrahtet** — kein echtes Langzeit-Gedächtnis im Sinne von "AILIZA erinnert sich über Sitzungen hinweg an Vorlieben" |
| `skills` | Von der KI vorgeschlagene/genehmigte Fähigkeiten | Existiert, admin-getrieben |

**Kurz gesagt:** AILIZA speichert heute *Chatverläufe* (verschlüsselt) und *Betriebsdaten* (Codes, keine Inhalte) sehr sauber. Ein *aktives* Gedächtnis — "AILIZA weiß aus früheren Gesprächen, dass Karo lieber kurze Antworten mag" — existiert nur als Rohbau (`reflection_facts`), wird aber nicht systematisch befüllt oder abgefragt.

---

## 2. Was fehlt für echtes Gedächtnis

1. **Aktive Befüllung von `reflection_facts`** — aktuell schreibt fast nichts automatisch dort hinein.
2. **Abruf beim nächsten Gespräch** — selbst wenn Fakten gespeichert wären, zieht der Chat-Flow sie nicht systematisch als Kontext.
3. **Nutzer-Kontrolle über das Gedächtnis** — kein "Was weißt du über mich?"/"Vergiss das bitte" im UI.
4. **Kein Nutzer-Export** ("Gib mir alle meine Daten") — nur Admin-Audit-Export existiert.
5. **Kein Account-/Komplett-Löschung-Endpoint** — Nutzer kann einzelne Chats/Projekte löschen, aber nicht "lösche mich komplett" auslösen.
6. **Keine automatische Lösch-Ausführung** — `retention_until`-Felder existieren an mehreren Stellen, aber es läuft (bewusst, laut Code-Kommentar) noch kein automatischer Job, der abgelaufene Daten wirklich entfernt.

---

## 3. Backup/Export-Stand heute

- **Backup:** Nur über die Infrastruktur (Neon-Snapshots automatisch, oder manuell laut `docs/AUTARKER_BETRIEB.md` bei SQLite). Keine AILIZA-eigene Backup-Funktion.
- **Export:** Nur `/admin/audit/export` (Betreiberin, keine Nutzerdaten-Inhalte). Kein "Meine Daten herunterladen" für Endnutzer.
- **Löschung:** Einzelne Objekte (Chat, Projekt, TOTP) ja. Kompletter Account/"Recht auf Vergessenwerden" (Art. 17 DSGVO) nein.

---

## 4. Datenklassen (Vorschlag, angelehnt an bestehendes 5-Stufen-System)

Nutzt das gleiche Schema, das die Redaction-Engine schon kennt (secret/forbidden/confidential/high/normal), aber jetzt auf *Speicherebene* statt nur auf *Sende-Ebene* angewendet:

| Klasse | Beispiel | Speicherregel |
|---|---|---|
| 🟢 Normal | Projektname, Chat-Titel | Verschlüsselt at rest, normale Aufbewahrung |
| 🟡 Kritisch | IBAN, Kartennummer (falls in einem Chat erwähnt) | Nie als Klartext, auch nicht verschlüsselt dauerhaft — nur als Platzhalter, Original nie gespeichert |
| 🟠 Vertraulich | Vertragsentwürfe, Kalkulationen | Verschlüsselt, kürzere Standard-Aufbewahrung möglich |
| 🔴 Art. 9/10 DSGVO | Gesundheit, Politik, strafrechtliche Verdachtsdaten | Nur mit explizitem Nutzer-Opt-in dauerhaft speicherbar, sonst nur für die Sitzung |
| ⚫ Geheimnis | API-Keys, Passwörter | Nie speichern (auch nicht verschlüsselt) — heute schon so (`strip_secrets_with_placeholder`) |

---

## 5. Speicherorte (Vorschlag)

- **Server-DB (Postgres/Neon oder autarkes SQLite):** Alles aus Gruppe A + B wie heute.
- **Kein Gedächtnis im Frontend/localStorage** außer UI-Zustand (offene Sidebar etc.) — Inhalte gehören serverseitig, damit geräteübergreifend nutzbar (bereits AILIZA-Prinzip).
- **Neu: `memory_facts`-Tabelle** (Nachfolger/Erweiterung von `reflection_facts`) — mit Datenklasse pro Fakt, Quelle (aus welchem Chat), Ablaufdatum, und einem Flag "vom Nutzer bestätigt" vs. "automatisch erkannt".

---

## 6. Memory-Policy (Vorschlag, Kernregeln)

1. **Opt-in bleibt Pflicht** für alles, was über die reine Chat-Historie hinausgeht (bereits so in `reflection_facts` angelegt — beibehalten).
2. **Jeder Fakt braucht eine Quelle und eine Datenklasse** — kein anonymes "AILIZA weiß irgendwas".
3. **Art. 9/10-Daten (🔴) werden nie automatisch ins Langzeit-Gedächtnis übernommen**, nur mit explizitem Zusatz-Opt-in pro Fall.
4. **Nutzer sieht und kontrolliert das Gedächtnis** — Minimalversion: Liste der gespeicherten Fakten, einzeln löschbar.
5. **Automatischer Ablauf** — jeder Fakt hat ein Ablaufdatum (Standard z.B. 90 Tage ohne Bestätigung, dauerhaft nur nach explizitem "das stimmt, merk dir das").

---

## 7. Lösch-/Aufbewahrungsregeln (Vorschlag)

| Datentyp | Standard-Aufbewahrung | Löschauslöser |
|---|---|---|
| Chats/Projekte | Unbegrenzt, bis Nutzer löscht | Manuell (existiert) |
| `reflection_facts`/`memory_facts` | 90 Tage ohne Bestätigung, sonst bis Widerruf | Automatischer Job (fehlt noch) + manuell |
| `audit_logs` | Rechtlich vorgeschrieben, i.d.R. länger, nie Inhalte | Nie vorzeitig (Integritätskette) |
| `security_logs`/`performance_logs`/`cost_logs` | Kurz (30-90 Tage), haben schon `retention_until` | Automatischer Job (fehlt noch) |
| Kompletter Account | — | **Fehlt: "Account löschen"-Funktion (Art. 17 DSGVO)** |

---

## 8. Backup/Restore (Vorschlag)

- **Autark (SQLite):** bereits in `docs/AUTARKER_BETRIEB.md` beschrieben (sqlite3 `.backup`, Volume-basiert).
- **Cloud (Neon):** Neon bietet automatische Point-in-Time-Recovery — dokumentieren, nicht neu bauen.
- **Neu vorzuschlagen:** ein Nutzer-Export-Endpoint (`GET /api/me/export`) — liefert die eigenen Chats/Projekte/Fakten als strukturierte Datei (Art. 20 DSGVO, Datenportabilität).

---

## 9. Autarker Betriebsmodus

Bereits mit PR #42 vorbereitet (SQLite + `/data`-Volume). Für dieses Gedächtnis-Konzept ändert sich daran nichts — `memory_facts` wäre einfach eine weitere Tabelle in derselben DB, egal ob SQLite oder Postgres.

---

## 10. Vorschlag: nächste 3 Mini-PRs (jeweils einzeln zu bestätigen)

1. **Mini-PR 1 — Nutzer-Datenexport** (Art. 20 DSGVO)
   `GET /api/me/export` — eigene Chats/Projekte als JSON-Download. Kein neues Gedächtnis, nur Transparenz über Bestehendes.

2. **Mini-PR 2 — Account-Löschung** (Art. 17 DSGVO)
   `DELETE /api/me` — löscht alle eigenen Datensätze (Chats, Projekte, TOTP, reflection_facts) in einer Transaktion. Audit-Eintrag bleibt (nur Code, keine Inhalte), das ist rechtlich zulässig.

3. **Mini-PR 3 — Memory-Sichtbarkeit + Ablauf**
   Kleines UI-Panel "Was AILIZA sich merkt" (Liste aus `reflection_facts`), einzeln löschbar + automatischer Ablauf-Job für Fakten ohne Bestätigung nach 90 Tagen.

**Bewusst NICHT als nächstes:** aktive automatische Gedächtnis-Befüllung während des Chats (das ist der größte, riskanteste Baustein — verdient einen eigenen, größeren Auftrag mit eigener Testliste, erst nachdem 1-3 stehen).

---

*Konzept, kein Code. Wartet auf Karo-Entscheidung, welcher Mini-PR zuerst kommt.*
