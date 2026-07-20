# AILIZA — Intelligente Datenbank & Gedächtnis-Governance v1

Stand: 20.07.2026 · **Konzept, kein Code.** Fundament für alle späteren Migrationen.
Ersetzt/erweitert `docs/MEMORY_ARCHITECTURE_V1.md` (das bleibt als Bestandsaufnahme gültig).

> **Leitprinzip:** So wenig festes Profil wie möglich, so viel Nutzerkontrolle wie möglich.
> AILIZA soll nicht möglichst viel über Menschen wissen, sondern nachvollziehbar mit
> **bewusst freigegebenem** Wissen arbeiten. Kein heimliches Profiling.

---

## 1. Kurzurteil

- **Nutzerprofile sind nötig**, aber nur technisch (Login, Rolle, Sprache) — nicht als Wissensspeicher über den Menschen.
- **Arbeitspräferenzen** (Ton, Länge) sind Einstellungen, keine Persönlichkeitsanalyse — sie gehören nicht ins feste Profil.
- **Inhaltliches Wissen** gehört in sichtbare, bestätigte, löschbare Gedächtnis-Einträge.
- **Aktives Merken** ist erlaubt — aber nur sichtbar, als Vorschlag zur Bestätigung, nie heimlich.

Wichtig: Die Datenbank wird nicht durch Vektorsuche oder Wissensgraph "intelligent", sondern dadurch, dass sie **Rechte, Quellen, Sichtbarkeit, Zweck, Löschung und Gedächtnis sauber zusammendenkt**. pgvector/Graph kommen erst viel später.

---

## 2. Drei-Ebenen-Modell (Kern)

```text
users          = technische Stammdaten (klein halten!)
user_settings  = Bedien- und Arbeitsweise (änderbar)
memory_items   = sichtbares Wissen (company_memory | user_memory)
```

**Was NICHT in `users` gehört:** Arbeitspräferenzen, Projektwissen, Kundendaten,
Gedächtnis-Fakten, Chat-Zusammenfassungen, Persönlichkeitsannahmen.

---

## 3. Datenmodell v1 (13 Tabellen)

Für jede Tabelle: Zweck · wichtigste Felder · sensible Felder · Lösch-/Aufbewahrungslogik.
Heute existieren `users` und `audit_logs` bereits (siehe MEMORY_ARCHITECTURE_V1.md) — die anderen sind neu.

### Ebene 1 — Technische Identität

| Tabelle | Zweck | Wichtigste Felder | Sensibel | Lösch-/Aufbewahrung |
|---|---|---|---|---|
| `users` | Technische Stammdaten (**bleibt minimal**) | user_id, email, password_hash, display_name, org_id, sprache, zeitzone, account_status, agb_bestaetigt_at, last_login, speichermodus | password_hash (nie Klartext) | Bei Account-Löschung entfernt, Audit bleibt |
| `organizations` | Mandant/Firma | org_id, name, land, default_sprache | — | Nur mit allen abhängigen Daten |
| `roles` | Rollendefinitionen | role_id, name, beschreibung | — | Stammdaten, selten gelöscht |
| `permissions` | Rechte je Rolle | permission_id, role_id, resource, action | — | Stammdaten |

### Ebene 2 — Einstellungen

| Tabelle | Zweck | Wichtigste Felder | Sensibel | Lösch-/Aufbewahrung |
|---|---|---|---|---|
| `user_settings` | Bedien-/Arbeitspräferenzen | user_id, antwortlaenge, ton, sprache, ausgabeformat, ui_prefs (JSON), benachrichtigungen, aktives_merken (bool), speichermodus | — (keine Persönlichkeitsanalyse!) | Mit Account gelöscht |

### Ebene 3 — Bewusstes Gedächtnis

| Tabelle | Zweck | Wichtigste Felder | Sensibel | Lösch-/Aufbewahrung |
|---|---|---|---|---|
| `memory_items` | Sichtbares Wissen | item_id, scope (**company_memory\|user_memory**), owner_id, org_id, inhalt, kategorie, zweck, source_id, visibility_id, ablaufdatum, status (vorgeschlagen\|bestätigt\|veraltet\|gelöscht), letzte_nutzung | inhalt kann PII enthalten → verschlüsselt at rest | Ablaufdatum + manuelle Löschung + Account-Löschung |
| `memory_suggestions` | Vorschläge statt heimliches Lernen | suggestion_id, user_id, quelle_chat_id, vorgeschlagener_inhalt, status (offen\|bestätigt\|abgelehnt), erstellt_at | vorgeschlagener_inhalt verschlüsselt | Nach Ablehnung/Ablauf gelöscht |
| `memory_sources` | Herkunft/Belege | source_id, typ (nutzerbestätigung\|dokument\|admin_freigabe), referenz, freigegeben_von, freigegeben_at | — | Solange abhängiges memory_item lebt |
| `memory_visibility` | Sichtbarkeits-/Zugriffsregeln | visibility_id, item_id, scope, erlaubte_rollen (JSON), erlaubte_user (JSON) | — | Mit item gelöscht |

### Governance-Schicht

| Tabelle | Zweck | Wichtigste Felder | Sensibel | Lösch-/Aufbewahrung |
|---|---|---|---|---|
| `consent_records` | Einwilligungen/aktive Einstellungen dokumentiert | consent_id, user_id, zweck, gegeben_at, widerrufen_at | — | Rechtlich aufzubewahren (Nachweis) |
| `audit_log` | Nachvollziehbarkeit (**existiert schon** als audit_logs) | id, timestamp, action, reason_code, actor_id, tenant_id, hash-chain | Nur Codes, **nie Inhalte** | Nie vorzeitig (Integritätskette) |
| `deletion_requests` | Löschanträge (Art. 17) | request_id, user_id, umfang, status, angefordert_at, erledigt_at | — | Nachweis aufbewahren |
| `export_requests` | Exportanträge (Art. 20) | request_id, user_id, umfang, status, angefordert_at, erledigt_at | — | Nachweis aufbewahren |

**Pflicht für jeden `memory_items`-Eintrag:** Inhalt, Kategorie, **Quelle**, **Zweck**, **Besitzer**, **Sichtbarkeit**, **Ablaufdatum**, **Status** — sonst nicht speicherbar.

---

## 4. Rollen-/Rechtemodell

| Rolle | Sieht Profildaten | Ändert Einstellungen | Bestätigt Gedächtnis | Gibt Org-Wissen frei | Löst Export aus | Löscht/Sperrt |
|---|---|---|---|---|---|---|
| **System-Admin** | alle | technisch | alle Bereiche | ja | ja | ja (max. auditiert) |
| **Organisations-Admin** | eigene Org | eigene | Firmen + eigene | ja (eigene Org) | Org-Daten | Org-Daten |
| **Teamleitung** | Team | eigene | Team (je Recht) | nein | nein | nein (keine fremden Nutzer-Memories) |
| **Mitarbeiter** | eigene | eigene | eigene Vorschläge | nein | eigene | eigene Einträge |
| **Externer Nutzer** | eigene | eigene | eigene | nein | eigene | eigene |
| **Datenschutz/Audit** | alle (zweckgebunden, protokolliert) | nein | nein | nein | prüfen | prüfen |

Grundregel: **Organisationsweite Änderungen brauchen Admin/berechtigte Rolle.** Privates Nutzergedächtnis anderer ist für Teamleitung/Kollegen **nicht** änderbar.

---

## 5. Speicher-Entscheidungslogik

Wenn AILIZA eine Information erkennt, durchläuft sie diese Prüfung → Ergebnis:

| Prüfung | → wenn ja |
|---|---|
| Sensibel (Art. 9/10: Gesundheit, Politik, ...) ohne Grundlage? | **blockieren/schwärzen**, nie automatisch speichern |
| Geheimnis (Passwort, API-Key)? | **nie speichern** (bereits so: `strip_secrets_with_placeholder`) |
| Technisch notwendig (Login, Audit)? | **automatisch speichern** (nur Codes/Metadaten) |
| Nur Arbeitspräferenz? | **in `user_settings`** |
| Inhaltliches, wiederverwendbares Wissen mit Quelle? | **als `memory_suggestion` vorschlagen** → nach Bestätigung `memory_item` |
| Organisationsweit? | **Admin-Freigabe anfordern** |
| Einmalig / unbestätigt / Rohdokument vor Freigabe? | **nur temporär in der Sitzung nutzen**, nicht speichern |
| Vermutung / Persönlichkeitsannahme? | **verwerfen**, nie speichern |

**Nie dauerhaft:** Klartextpasswörter, Tokens, Gesundheits-/Politik-/Religionsdaten ohne Grundlage, Leistungsbewertungen, Persönlichkeitsannahmen, komplette Roh-Chats.

---

## 6. RAG-/Nutzungslogik (wie AILIZA gespeichertes Wissen verwendet)

AILIZA darf einen `memory_item` nur nutzen, wenn **alle** zutreffen:
bestätigt · Status aktiv · Zweck passt zur Anfrage · Sichtbarkeit erlaubt · Quelle dokumentiert · Ablaufdatum nicht überschritten · Rolle des Nutzers erlaubt Zugriff.

AILIZA soll Nutzung erklären können:
- „Ich nutze deine Einstellung für kurze Antworten."
- „Ich nutze gespeichertes Projektwissen. Quelle: Nutzerbestätigung vom [Datum]."
- „Das ist eine Vermutung und wurde nicht gespeichert."
- „Ich habe dazu keine gespeicherte Information."

Grenzen: Firmengedächtnis vor Nutzung auf Berechtigung prüfen. Nutzergedächtnis nur für den jeweiligen Nutzer (außer explizit freigegeben). **Keine freie LLM-Suche über alle Unternehmensdaten.** Keine gelöschten/veralteten/unbestätigten Einträge.

---

## 7. DSGVO / EU-AI-Act (konservativ)

Datenminimierung · Zweckbindung · Transparenz · Berichtigung · Löschung (Art. 17) · Export (Art. 20) · Einwilligung/aktive Einstellung · Protokollierung · Zugriffsbeschränkung · menschliche Kontrolle · keine automatisierte Personenbewertung ohne Grundlage.

> Dieses Konzept ist DSGVO-/EU-AI-Act-**orientiert**. Es ersetzt keine juristische Prüfung und bestätigt keine abschließende Konformität.

---

## 8. Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Zu viel Profilwissen | `users` strikt minimal, Trennung in 3 Ebenen |
| Verstecktes Profiling | Nur Vorschläge (`memory_suggestions`), sichtbar + bestätigungspflichtig |
| Falsche Zuordnung | Jeder Eintrag hat Besitzer + Quelle |
| Veraltete Informationen | Pflicht-Ablaufdatum + Status „veraltet" |
| Unklare Quellen | `memory_sources` Pflicht, sonst kein Eintrag |
| Rechtefehler | `memory_visibility` + Rollenmatrix, Admin-Freigabe für Org-Wissen |
| Nutzervertrauen verloren | UI „Mein AILIZA-Gedächtnis": alles sicht-/löschbar |
| Falsche KI-Schlüsse | Vermutungen werden verworfen, nicht gespeichert |

---

## 9. Mini-PR-Roadmap (jeweils einzeln zu bestätigen)

1. **PR 1 — Profil klein + `user_settings` trennen.** `users` minimal halten, neue `user_settings`-Tabelle für Arbeitspräferenzen. *Nicht im Scope:* Gedächtnis, UI.
2. **PR 2 — Memory-Kernschema + Entscheidungslogik.** `memory_items` (company/user), `memory_sources`, `memory_visibility`, Speicherentscheidung Profil/Einstellung/Gedächtnis/temporär/verwerfen. *Nicht im Scope:* Vorschläge-Automatik, UI, pgvector.
3. **PR 3 — Vorschläge + aktives Merken.** `memory_suggestions`, Schalter in `user_settings`, sichtbare Vorschläge statt heimliches Lernen. *Nicht im Scope:* automatische Chat-Speicherung.
4. **PR 4 — UI „Mein AILIZA-Gedächtnis".** Firmen-/Nutzergedächtnis sichtbar, bearbeit-/löschbar. *Nicht im Scope:* Backend-Neubau.
5. **PR 5 — Audit, Export, Löschung.** `deletion_requests`, `export_requests`, Admin-Löschung, Nutzerexport, volle Auditierung.

**Reihenfolge nach diesem Konzept:** erst Migrationen (PR 1-2), dann Vorschläge (PR 3), dann UI (PR 4-5), **danach erst pgvector, Wissensgraph erst viel später.**

---

## 10. Nicht im Scope für v1

Keine automatische Speicherung kompletter Chats · kein großes Persönlichkeitsprofil · keine Persönlichkeitsanalyse · keine Leistungsbewertung · kein Wissensgraph · keine pgvector-Suche · keine freie LLM-Suche über alle Unternehmensdaten · keine versteckten Profile · keine sensiblen Daten ohne ausdrückliche Grundlage.

*(Bestätigte, quellenbasierte Zusammenfassungen als `memory_item` sind erlaubt — vollständige Roh-Chats als Profil nicht.)*

---

*Konzept, kein Code. Wartet auf Karo-Entscheidung, welcher Mini-PR (Abschnitt 9) zuerst umgesetzt wird. Empfehlung: PR 1 (kleinster, klarster Schritt).*
