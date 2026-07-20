# AILIZA — Profil-, Einstellungs- und Gedächtnis-Governance (Konzept v1)

Stand: 20.07.2026 · **Reines Konzeptdokument, kein Code, keine Rechtsgarantie.**
Sprache: Deutsch. Mehrsprachigkeit (Deutsch, Englisch, weitere EU-Sprachen je
nach Land) ist als Einstellung vorgesehen, nicht als festes Profilmerkmal.

> Konservativer Hinweis vorab: Dieses Dokument ist DSGVO- und
> EU-AI-Act-**orientiert**. Es ersetzt keine juristische Prüfung und bestätigt
> keine abschließende Konformität.

---

## 1. Kurzurteil

- **Warum Nutzerprofile notwendig sind:** AILIZA braucht ein Minimum an
  technischen Stammdaten (wer ist eingeloggt, welche Rolle, welcher Mandant,
  welche Sprache), um überhaupt sicher, mandantengetrennt und rollenbasiert zu
  funktionieren.
- **Warum sie strikt klein bleiben müssen:** Jedes Feld im festen Profil ist
  ein Datum, das dauerhaft über einen Menschen existiert. Je größer das Profil,
  desto größer die Angriffsfläche, das Missbrauchsrisiko und die
  Zertifizierungslast. Datenminimierung (Art. 5 DSGVO) ist nicht verhandelbar.
- **Warum Arbeitskontext und Präferenzen nicht ins feste Profil gehören:**
  „Nutzer mag kurze Antworten" ist eine **Bedieneinstellung**, keine
  Eigenschaft der Person. Solche Dinge gehören in `user_settings`, jederzeit
  änderbar, nicht in ein Persönlichkeitsbild.
- **Warum „Mein AILIZA-Gedächtnis" die bessere Produktlinie ist:** Statt eines
  unsichtbaren Profils bekommt der Nutzer einen sichtbaren, kontrollierbaren
  Wissensspeicher. Jeder Eintrag ist begründbar, änderbar, löschbar. Das
  schafft Vertrauen und ist gleichzeitig die datenschutzfreundlichste Bauweise.
- **Warum aktives Merken nur mit transparenter Nutzerkontrolle vertretbar ist:**
  Automatisches Lernen ohne Sichtbarkeit wäre verstecktes Profiling. Mit
  sichtbaren Vorschlägen, Bestätigung und jederzeitiger Löschung bleibt der
  Mensch in Kontrolle.

**Leitsatz:** AILIZA soll nicht möglichst viel über Menschen wissen, sondern
nachvollziehbar mit bewusst freigegebenem Wissen arbeiten.

---

## 2. Zielbild

- Kleines technisches Nutzerprofil (nur Stammdaten).
- Einstellungen strikt getrennt vom Profil.
- Inhaltliches Wissen ausschließlich in sichtbaren Gedächtnis-Einträgen.
- Zwei klar getrennte Gedächtnisbereiche:
  - **Firmengedächtnis** (organisationsweit, admin-freigegeben)
  - **Nutzergedächtnis** (persönlich, nutzer-bestätigt)
- Aktives Merken **nur**, wenn der Nutzer es in den Einstellungen aktiviert hat
  — und auch dann nur als sichtbarer Vorschlag, nie als heimliche Speicherung.
- Admin-kontrollierte Löschung und Governance.
- Jede Erinnerung trägt: Zweck, Quelle, Sichtbarkeit, Ablaufdatum, Status.

---

## 3. Drei-Ebenen-Modell

### Ebene 1 — Festes Nutzerprofil (klein, technisch)

Nur notwendige Stammdaten:

| Feld | Zweck |
|---|---|
| Nutzer-ID | eindeutige Kennung |
| E-Mail | Login, Kommunikation |
| Passwort-Hash | Authentifizierung (nie Klartext) |
| Anzeigename | Anrede in der UI |
| Organisation / Mandant | Mandantentrennung |
| Rolle | Rechtevergabe |
| Sprache | UI-/Antwortsprache |
| Zeitzone | Termin-/Zeitlogik |
| Account-Status | aktiv/gesperrt/gelöscht |
| Datenschutz/AGB bestätigt | Rechtsgrundlage, Zeitstempel |
| Letzter Login | Sicherheit |
| Speichermodus | nie automatisch / immer fragen / projektbezogen fragen |

**Das Profil ist ausdrücklich kein Wissensspeicher über den Menschen.** Es
enthält keine Vorlieben, keine Persönlichkeitsmerkmale, keine inhaltlichen
Fakten.

### Ebene 2 — Nutzereinstellungen (Bedien-/Arbeitspräferenzen)

Änderbare Einstellungen, keine Persönlichkeitsanalyse:

- Antwortlänge: kurz / normal / ausführlich
- Ton: sachlich / freundlich / formell
- Standard-Sprache (Deutsch, Englisch, weitere EU-Sprachen je nach Land)
- Bevorzugtes Ausgabeformat
- UI-Einstellungen
- Benachrichtigungen
- **Aktives Merken wichtiger Informationen: an/aus**
- Gewünschter Speichermodus

**Einstellungen sind Bedienpräferenzen, keine Bewertung der Person.** Sie sind
jederzeit umstellbar und beschreiben nur, *wie* AILIZA arbeiten soll.

### Ebene 3 — Gedächtnis-Einträge

**3a. Firmengedächtnis** (organisationsweit, admin-freigegeben):
- freigegebene Unternehmensinformationen
- Projektwissen
- freigegebene Dokumentquellen
- organisatorische Regeln
- fachliche Vorgaben

**3b. Nutzergedächtnis** (persönlich, nutzer-bestätigt):
- persönliche Arbeitspräferenzen (über reine Einstellungen hinaus)
- vom Nutzer bestätigte wiederverwendbare Hinweise
- projektbezogene Nutzerkontexte
- bewusst gespeicherte Informationen

Beispiele: „Firma nutzt DATEV." · „Nutzer bevorzugt Compliance-Hinweise." ·
„Projekt X hat Ziel Y." · „Kunde Z braucht Rechnung als PDF." · „Dokumentquelle
Q ist freigegeben."

**Pflichtfelder jedes Gedächtnis-Eintrags:**

| Feld | Bedeutung |
|---|---|
| Inhalt | die eigentliche Information (Zusammenfassung, nie Roh-Chat) |
| Kategorie | z.B. Projektwissen, Arbeitspräferenz, Kundenvorgabe |
| Quelle | Nutzerbestätigung / freigegebenes Dokument / Admin-Freigabe |
| Zweck | wofür AILIZA es verwenden darf |
| Besitzer | Nutzer oder Organisation |
| Sichtbarkeit | privat / team / organisation |
| Ablaufdatum | wann es automatisch verfällt |
| Status | vorgeschlagen / bestätigt / veraltet / gelöscht |
| Letzte Nutzung | wann zuletzt in einer Antwort verwendet |

---

## 4. Speicherregeln

### Automatisch technisch speicherbar
Nutzer-ID · Login-Zeitpunkt · Account-Status · Rollen-/Berechtigungsänderungen
· Zustimmung zu Datenschutz/AGB · technische Sicherheitsereignisse ·
Audit-Ereignisse mit Reason-Codes · technische Fehlzustände.
→ **Keine unnötigen Rohinhalte.**

### Nur als Einstellung speicherbar
Antwortlänge · Ton · Sprache · Ausgabeformat · UI-Vorlieben · Benachrichtigungen
· Speichermodus · aktive Merken-Funktion.

### Nur als bestätigter Gedächtnis-Eintrag speicherbar
Projektziele · wiederverwendbares Nutzerwissen · wiederkehrende Arbeitsregeln ·
fachliche Präferenzen · bestätigte Kundenvorgaben mit Zweck · **bestätigte
Zusammenfassungen aus Chats — aber niemals vollständige Roh-Chats.**

### Nur nach Admin-Freigabe speicherbar
organisationsweite Quellen · Dokumentbibliotheken · Firmengedächtnis · teamweite
Regeln · Mandantenrichtlinien · RAG-Datenquellen · organisationsweite
Berechtigungen.

### Nie dauerhaft speichern
Klartextpasswörter · Tokens/API-Keys · Gesundheitsdaten ohne ausdrückliche
Grundlage · politische/religiöse Informationen · private Konflikte · private
Bewertungen · Vermutungen über Persönlichkeit · Leistungsbewertungen ·
Kundendaten ohne Zweck · einmalige Gesprächsdetails ohne Wiederverwendungsnutzen
· sensible Daten (Art. 9/10 DSGVO) ohne ausdrückliche Grundlage.

### Nur temporär im aktuellen Gespräch nutzen
unbestätigte Informationen · Einmalinformationen · sensible Inhalte für eine
konkrete Bearbeitung · Rohdokumente vor Quellenfreigabe · Modellvermutungen ·
nicht bestätigte Chat-Zusammenhänge.

---

## 5. Datenmodell v1

> Struktur-Skizze, keine Implementierung. „Sensible Felder" = besonders
> schützenswert, verschlüsselt at rest bzw. gar nicht speichern.

### `users` — festes technisches Profil
- **Zweck:** Authentifizierung, Rolle, Mandant.
- **Felder:** user_id, email, password_hash, display_name, org_id, role,
  language, timezone, account_status, terms_accepted_at, last_login,
  storage_mode.
- **Sensible Felder:** password_hash (nur Hash), email.
- **Löschlogik:** Löschung über Account-Löschung (Art. 17); Audit-Verweis bleibt
  (nur Code, kein Inhalt).

### `organizations` — Mandanten
- **Zweck:** Organisationseinheit, an der Firmengedächtnis + Berechtigungen
  hängen.
- **Felder:** org_id, name, region/land, default_language, status.
- **Sensible Felder:** keine direkten PII.
- **Löschlogik:** Organisationslöschung kaskadiert auf Firmengedächtnis
  (dokumentierter Prozess, admin-gesteuert).

### `roles` — Rollendefinitionen
- **Zweck:** benennt Rollen (siehe Abschnitt 6).
- **Felder:** role_id, name, beschreibung.
- **Sensible Felder:** keine.
- **Löschlogik:** stabil, selten geändert; Änderungen im Audit.

### `permissions` — Rechte je Rolle/Objekt
- **Zweck:** wer darf was (lesen/bestätigen/freigeben/löschen/exportieren).
- **Felder:** permission_id, role_id, ressource, aktion, scope.
- **Sensible Felder:** keine.
- **Löschlogik:** Änderungen protokolliert.

### `user_settings` — Bedienpräferenzen
- **Zweck:** wie AILIZA für diesen Nutzer arbeitet.
- **Felder:** user_id, answer_length, tone, language, output_format, ui_prefs,
  notifications, active_remember_enabled, storage_mode.
- **Sensible Felder:** keine PII, aber nutzerbezogen.
- **Löschlogik:** mit Account gelöscht; jederzeit vom Nutzer änderbar.

### `memory_items` — inhaltliche Fakten (Kern des Gedächtnisses)
- **Zweck:** bestätigtes, wiederverwendbares Wissen (Firma + Nutzer).
- **Felder:** item_id, owner_type (user/org), owner_id, content (Zusammenfassung),
  category, purpose, source_id, visibility, status, expires_at, last_used_at,
  created_at, confirmed_at.
- **Sensible Felder:** content (verschlüsselt at rest).
- **Löschlogik:** Ablaufdatum + manuelle Löschung + „nicht mehr verwenden"
  (Status statt Hard-Delete möglich, dann bei Ablauf endgültig entfernt).

### `memory_suggestions` — Erinnerungs-Vorschläge (unbestätigt)
- **Zweck:** von AILIZA vorgeschlagene, noch nicht bestätigte Merk-Kandidaten.
- **Felder:** suggestion_id, user_id, content, category, source_context_ref,
  created_at, status (offen/bestätigt/abgelehnt/abgelaufen).
- **Sensible Felder:** content (verschlüsselt, kurze Aufbewahrung).
- **Löschlogik:** automatischer Verfall nach kurzer Frist (z.B. 14 Tage), wenn
  nicht bestätigt; bei Bestätigung → wird zu `memory_items`.

### `memory_sources` — Quellen
- **Zweck:** woher ein Eintrag stammt (Nutzerbestätigung, Dokument,
  Admin-Freigabe).
- **Felder:** source_id, type, reference, freigegeben_von, freigegeben_am.
- **Sensible Felder:** ggf. Dokumentverweis.
- **Löschlogik:** an zugehörige memory_items gebunden.

### `memory_visibility` — Sichtbarkeitsregeln
- **Zweck:** wer einen Eintrag sehen/nutzen darf.
- **Felder:** item_id, scope (privat/team/org), team_id (optional).
- **Sensible Felder:** keine.
- **Löschlogik:** mit item gelöscht.

### `consent_records` — Einwilligungen/aktive Einstellungen
- **Zweck:** Nachweis, dass eine Speicher-/Merk-Funktion aktiv erlaubt wurde.
- **Felder:** consent_id, user_id, art_der_einwilligung, aktiv_ab, widerrufen_am.
- **Sensible Felder:** keine PII außer Bezug.
- **Löschlogik:** aufbewahrungspflichtig als Nachweis (nur Codes/Zeitstempel).

### `audit_log` — Nachvollziehbarkeit
- **Zweck:** lückenlose Protokollierung von Aktionen (nie Inhalte).
- **Felder:** id, timestamp, action_code, actor_role, reason_code, hash_chain.
- **Sensible Felder:** keine — bewusst nur Codes.
- **Löschlogik:** nie vorzeitig (Integritätskette); rechtliche Aufbewahrung.

### `deletion_requests` — Löschanträge
- **Zweck:** Art.-17-Anfragen dokumentieren und abarbeiten.
- **Felder:** request_id, subject_user_id, requested_by, status, requested_at,
  completed_at.
- **Sensible Felder:** Bezug auf Nutzer.
- **Löschlogik:** Nachweis bleibt (Code), Inhalte werden entfernt.

### `export_requests` — Exportanträge (Art. 20)
- **Zweck:** Datenexport dokumentieren.
- **Felder:** request_id, user_id, status, requested_at, delivered_at.
- **Sensible Felder:** Bezug auf Nutzer.
- **Löschlogik:** Exportdatei nach Übergabe/Frist löschen.

**Kernprinzip:** Arbeitspräferenzen → `user_settings`. Inhaltliche Fakten →
`memory_items`. Nicht alles in `users`. Chat-Zusammenfassungen nur als
bestätigte/erlaubte Memory-Einträge, nie als Roh-Chat-Profil.

---

## 6. Rollen-/Rechtemodell

| Rolle | Profildaten sichtbar | Einstellungen ändern | Gedächtnis bestätigen | Org-Einträge freigeben | Export auslösen | Löschen/Sperren |
|---|---|---|---|---|---|---|
| **System-Admin** | alle | technisch/alle | alle Bereiche | ja | ja | ja (voll) |
| **Organisations-Admin** | eigene Org | eigene | Firmen + eigene | ja (Org) | ja (Org-Daten) | ja (Org, berechtigt) |
| **Teamleitung** | eigenes Team (begrenzt) | eigene | Team + eigene | nein | nein (Standard) | nein (fremde Nutzer) |
| **Mitarbeiter** | eigene | eigene | eigene Vorschläge | nein | eigene (anfordern) | eigene / anfordern |
| **Externer Nutzer** | eigene | eigene | eigene | nein | eigene | eigene |
| **Datenschutz-/Auditrolle** | alle (zweckgebunden, protokolliert) | nein | nein (prüft) | nein | prüfen/auslösen | prüfen/anstoßen |

Ergänzende Regeln:
- **System-Admin** muss besonders auditierbar sein (jede Aktion protokolliert).
- **Teamleitung** darf **keine** privaten Nutzergedächtnisse anderer Mitarbeiter
  ändern.
- **Externer Nutzer** hat **keinen** Standardzugriff auf internes
  Firmengedächtnis — nur explizit freigegebene Projekt-/Firmeninfos.
- **Datenschutz-/Auditrolle** hat zweckgebundenen, protokollierten
  Inhaltszugriff — kein freies Stöbern.

---

## 7. Entscheidungslogik

Wenn AILIZA eine Information erkennt, durchläuft sie diese Prüfkette:

1. Ist sie sensibel (Art. 9/10)? → wenn ja ohne Grundlage: **blockieren/schwärzen**
2. Ist sie technisch notwendig? → **automatisch speichern** (nur Codes/Metadaten)
3. Ist sie nur eine Einstellung? → **in `user_settings`**
4. Ist sie inhaltliches Wissen? → weiter
5. Ist sie wiederverwendbar? → wenn nein: **nur temporär**
6. Gibt es eine Quelle? → wenn nein: **nicht dauerhaft**
7. Gibt es eine Berechtigung? → prüfen (Rolle/Scope)
8. Passt der Speichermodus? → „nie automatisch" = **nur Vorschlag/temporär**
9. Muss der Nutzer gefragt werden? → **als Vorschlag anzeigen**
10. Muss ein Admin freigeben? → **Admin-Freigabe anfordern**
11. Ergebnis festlegen.

### Ergebnismatrix

| Situation | Ergebnis |
|---|---|
| Sensibel ohne Grundlage | **blockieren/schwärzen** |
| Technisch notwendig | **automatisch speichern** (nur Code) |
| Bedienpräferenz | **als Einstellung speichern** |
| Wiederverwendbar + Quelle + aktives Merken an | **als Vorschlag anzeigen** |
| Vom Nutzer bestätigt | **als memory_item speichern** |
| Organisationsweit | **Admin-Freigabe anfordern** |
| Einmalig / unbestätigt | **nur temporär nutzen** |
| Kein Nutzen / keine Grundlage | **verwerfen** |

**Grundregel:** Im Zweifel die restriktivere Entscheidung (fail-closed).

---

## 8. RAG- und Quellenlogik

AILIZA darf gespeichertes Wissen in einer Antwort **nur** nutzen, wenn **alle**
Bedingungen erfüllt sind:
- Eintrag ist **bestätigt**,
- Status ist **aktiv**,
- **Zweck** passt zur Anfrage,
- **Sichtbarkeit** passt zur Rolle des Fragenden,
- **Quelle** vorhanden/plausibel dokumentiert,
- **Ablaufdatum** nicht überschritten,
- **Rolle** erlaubt Zugriff.

AILIZA soll ihre Wissensnutzung erklären können:
- „Ich nutze deine Einstellung für kurze Antworten."
- „Ich nutze gespeichertes Projektwissen. Quelle: Nutzerbestätigung vom [Datum]."
- „Quelle: freigegebenes Dokument [X]."
- „Das ist eine Vermutung und wurde nicht gespeichert."
- „Ich habe dazu keine gespeicherte Information."

Weitere Regeln:
- **Firmengedächtnis** vor jeder Nutzung auf Berechtigung prüfen.
- **Nutzergedächtnis** nur für den jeweiligen Nutzer, außer explizit freigegeben.
- **Keine** freie LLM-Suche über alle Unternehmensdaten.
- **Keine** Nutzung gelöschter, veralteter oder unbestätigter Einträge.

---

## 9. Datenschutz, DSGVO und EU-AI-Act

Technische und organisatorische Leitplanken:
- **Datenminimierung** — festes Profil klein, Rest löschbar.
- **Zweckbindung** — jeder Eintrag trägt einen Zweck.
- **Transparenz** — sichtbares Gedächtnis, erklärbare Nutzung.
- **Berichtigung** — Einträge änderbar.
- **Löschung** — Art. 17, inkl. Account-Löschung.
- **Export** — Art. 20, Nutzer-Datenexport.
- **Einwilligung/aktive Einstellung** — aktives Merken nur bei Opt-in.
- **Protokollierung** — Audit ohne Inhalte.
- **Zugriffsbeschränkung** — Rolle + Scope.
- **Menschliche Kontrolle** — Vorschläge statt Automatik.
- **Keine** automatisierte Personenbewertung ohne klare Grundlage.
- **Keine** sensiblen Daten (Art. 9/10) ohne ausdrückliche Grundlage.

> AILIZA ist DSGVO- und EU-AI-Act-**orientiert** zu gestalten. Dieses Konzept
> ersetzt keine juristische Prüfung und bestätigt keine abschließende
> Konformität.

---

## 10. UI-Konzept: „Mein AILIZA-Gedächtnis"

Bereiche:
- Mein Profil
- Einstellungen
- Gespeicherte Fakten
- Erinnerungs-Vorschläge
- Quellen
- Berechtigungen
- Datenschutz & KI
- Export & Löschen
- Verlauf / Audit

Sichtbar getrennt: **Firmengedächtnis** vs. **Nutzergedächtnis**.

Der Nutzer sieht zu jedem Eintrag jederzeit: **was** gespeichert wurde, **warum**,
**woher** es stammt, **wer** es sehen darf, **wie lange** es bleibt, **wann** es
zuletzt genutzt wurde — und wie man es **ändert / löscht / nicht mehr verwenden**
lässt.

Aktionen pro Eintrag: Bearbeiten · Löschen · Nicht mehr verwenden · Quelle
anzeigen · Ablaufdatum ändern · Sichtbarkeit ändern · Vorschlag bestätigen ·
Vorschlag ablehnen · Export anfordern.

Schalter für aktives Merken:
- „Wichtige Informationen automatisch vorschlagen" (an/aus)
- „Wichtige Termine, Absprachen und Veränderungen merken" (an/aus)
- Hinweis: „AILIZA speichert keine vollständigen Chats als Profil. Bestätigte
  Zusammenfassungen können als Erinnerung gespeichert werden."

---

## 11. Mini-PR-Roadmap

### PR 1 — Kleines Nutzerprofil und Einstellungen trennen
- **Ziel:** `users` klein halten, `user_settings` einführen.
- **Umfang:** neue Tabelle `user_settings`; Bedienpräferenzen dorthin; Profil
  bleibt technisch.
- **Akzeptanz:** Einstellungen änderbar ohne Profiländerung; Baseline grün;
  keine Präferenz landet in `users`.
- **Nicht im Scope:** Gedächtnis-Funktionen, UI-Ausbau.

### PR 2 — Memory-Policy und Entscheidungslogik
- **Ziel:** klare Speicherentscheidung (Profil / Einstellung / Gedächtnis /
  temporär / verwerfen).
- **Umfang:** Entscheidungslogik aus Abschnitt 7 als serverseitige Policy;
  `memory_items` + Pflichtfelder.
- **Akzeptanz:** sensible Daten ohne Grundlage werden nie dauerhaft; jede
  Speicherung hat Quelle+Zweck; fail-closed getestet.
- **Nicht im Scope:** automatische Befüllung, UI.

### PR 3 — Erinnerungs-Vorschläge und aktives Merken
- **Ziel:** aktive Merken-Funktion aus `user_settings` umsetzen, ohne heimliches
  Profiling.
- **Umfang:** `memory_suggestions`; Vorschlag nur bei aktivem Opt-in; Verfall
  unbestätigter Vorschläge.
- **Akzeptanz:** ohne Opt-in kein Vorschlag; jeder Vorschlag sichtbar +
  bestätig-/ablehnbar; nichts wird ohne Bestätigung dauerhaft.
- **Nicht im Scope:** vollständige UI, RAG-Nutzung.

### PR 4 — „Mein-AILIZA-Gedächtnis"-Oberfläche
- **Ziel:** Firmen- und Nutzergedächtnis sichtbar, bearbeitbar, löschbar.
- **Umfang:** UI-Panel (Abschnitt 10) auf bestehenden Endpoints.
- **Akzeptanz:** jeder Eintrag zeigt Zweck/Quelle/Ablauf/Sichtbarkeit; alle
  Aktionen funktionieren; Trennung Firma/Nutzer sichtbar.
- **Nicht im Scope:** neue Datenklassen, Auto-Merken-Logik.

### PR 5 — Audit, Export und Löschung
- **Ziel:** Admin-Löschung, Nutzerexport (Art. 20), Account-Löschung (Art. 17),
  Audit-Nachvollziehbarkeit.
- **Umfang:** `deletion_requests`, `export_requests`, `/api/me/export`,
  `DELETE /api/me`.
- **Akzeptanz:** Export liefert eigene Daten; Löschung entfernt Inhalte,
  Audit-Code bleibt; alles protokolliert.
- **Nicht im Scope:** automatische Retention-Jobs (separater Auftrag).

---

## 12. Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| Zu viel Profilwissen | Festes Profil auf Stammdaten begrenzen; Präferenzen in `user_settings`. |
| Verstecktes Profiling | Aktives Merken nur per Opt-in; jeder Eintrag sichtbar + löschbar. |
| Falsche Zuordnung | Quelle + Bestätigung pflicht; Nutzer kann korrigieren. |
| Veraltete Informationen | Ablaufdatum + „letzte Nutzung" + automatischer Verfall. |
| Unklare Quellen | `memory_sources` verpflichtend; ohne Quelle keine Dauerspeicherung. |
| Rechtefehler | Rollen-/Scope-Prüfung vor jeder Nutzung; Audit. |
| Nutzervertrauen verloren | Volle Transparenz + einfache Löschung im UI. |
| Datenschutzrisiken | Datenminimierung, Verschlüsselung at rest, fail-closed. |
| Falsche KI-Schlussfolgerungen | Vermutungen nie speichern; als Vermutung kennzeichnen. |

---

## 13. Nicht im Scope für v1

- Keine automatische Speicherung kompletter Chats (bestätigte/erlaubte
  Zusammenfassungen sind möglich).
- Kein großes Persönlichkeitsprofil, keine Persönlichkeitsanalyse.
- Keine Leistungsbewertung.
- Kein Wissensgraph als Pflichtbestandteil.
- Keine freie LLM-Suche über alle Unternehmensdaten.
- Keine versteckten Profile.
- Keine Speicherung sensibler Daten (Art. 9/10) ohne ausdrückliche Grundlage.

---

*Konzept, kein Code. Wartet auf Karo-Entscheidung, welcher Mini-PR (1–5) zuerst
umgesetzt wird. Empfehlung: PR 1 (Profil/Einstellungen trennen) als kleinste,
risikoärmste Grundlage.*
