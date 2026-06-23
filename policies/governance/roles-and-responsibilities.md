# AILIZA Rollen und Verantwortlichkeiten
# Stand: 2026-06-22
# Teil von: AILIZA Governance Pack v1

---

## Grundsatz

Keine Aktion mit Außenwirkung, rechtlicher Relevanz oder sensiblen Daten ohne
identifizierte und besetzte verantwortliche Rolle.
AILIZA bereitet vor und unterstützt — Entscheidungen und Ausführung liegen beim Menschen.

---

## Rolle 1: Nutzer

**Beschreibung:** Person, die AILIZA im Arbeitsalltag verwendet.

| Feld | Inhalt |
|---|---|
| **Aufgaben** | Anfragen stellen, Ergebnisse prüfen, Freigaben erteilen oder verweigern, Rückmeldung geben |
| **Darf** | Alle Core-Aufgaben nutzen; activatable-Module nach Freigabefrage aktivieren; Freigabeformat für blocked-Module verwenden |
| **Darf nicht** | Governance-Regeln umgehen; Sperren aufheben ohne Freigabeformat; PII oder Credentials direkt eingeben ohne Notwendigkeit |
| **Freigaberechte** | Eigene Aktionen im Core-Bereich; Modul-Aktivierung für eigene Session |
| **Dokumentationspflicht** | Freigaben für wirkungsrelevante Aktionen; Verantwortungsübernahme bei blocked-Modulen im Freigabeformat |

---

## Rolle 2: Admin

**Beschreibung:** Verwaltet AILIZA-Konfiguration, Zugänge und Provider-Anbindungen.

| Feld | Inhalt |
|---|---|
| **Aufgaben** | Konfiguration von Modulen und Routing; Verwaltung von Provider-Zugängen; Einrichtung von Audit-Vault; Rollenzuweisungen verwalten |
| **Darf** | Modulstatus ändern (activatable ↔ planned); Provider-Profile anlegen; Nutzerkonten verwalten; Konfigurationsdateien ändern |
| **Darf nicht** | blocked-Module ohne Erfüllung der Voraussetzungen aktivieren; Governance-Regeln in ag-master.md ohne Freigabe durch Compliance-Verantwortlichen ändern; AVV-Pflicht umgehen |
| **Freigaberechte** | Technische Konfiguration; Modul-Statuswechsel nach Prüfung; Provider-Anbindung nach AVV-Abschluss |
| **Dokumentationspflicht** | Alle Konfigurationsänderungen mit Datum, Grund, Prüfer; Provider-Anbindungen mit AVV-Referenz |

---

## Rolle 3: Technischer Betreiber

**Beschreibung:** Verantwortet Infrastruktur, Deployment, Logging und Audit-Vault-Betrieb.

| Feld | Inhalt |
|---|---|
| **Aufgaben** | Betrieb und Wartung der AILIZA-Infrastruktur; Audit-Vault implementieren und betreiben; Logging sicherstellen; Datensicherung; Sicherheitspatches |
| **Darf** | Systemzugriffe im Rahmen des Betriebs; Logs lesen (kein Roh-PII); technische Änderungen nach Freigabe durch Admin |
| **Darf nicht** | Audit-Vault-Einträge ändern, löschen oder überschreiben; Personendaten aus Logs extrahieren; Konfigurationsänderungen ohne Admin-Freigabe |
| **Freigaberechte** | Technischer Betrieb und Infrastruktur-Entscheidungen; Incident-Erstreaktion |
| **Dokumentationspflicht** | Deployment-Änderungen; Incidents; Wartungsarbeiten am Audit-Vault; Ausfallzeiten |

---

## Rolle 4: Datenschutzverantwortlicher

**Beschreibung:** Verantwortet DSGVO-Konformität und Datenschutzfragen im AILIZA-Betrieb.

| Feld | Inhalt |
|---|---|
| **Aufgaben** | VVT pflegen und prüfen; DPIA/DSFA bei risikoreichen Modulen; AVV prüfen und freigeben; Lösch- und Aufbewahrungskonzept erstellen; Datenpannen melden; Betroffenenrechte bearbeiten |
| **Darf** | Verarbeitungstätigkeiten genehmigen oder sperren; AVV-Anforderungen definieren; Provider-Profile auf DSGVO-Konformität prüfen; Datenminimierungsanforderungen setzen |
| **Darf nicht** | Verarbeitungen ohne Rechtsgrundlage genehmigen; blocked-Module ohne DPIA aktivieren (HR, Buchhaltung); Betroffenenrechte verweigern |
| **Freigaberechte** | Neue Verarbeitungstätigkeiten; Provider-Anbindungen mit Personenbezug; Aktivierung von HR- und Buchhaltungsmodul (nach DPIA) |
| **Dokumentationspflicht** | VVT-Einträge; DPIA-Dokumentationen; AVV-Nachweise; Datenpannen-Meldungen; Betroffenenrechtsanfragen |

---

## Rolle 5: Compliance-Verantwortlicher

**Beschreibung:** Verantwortet EU-AI-Act-Konformität, interne Compliance und Governance-Updates.

| Feld | Inhalt |
|---|---|
| **Aufgaben** | AI-Act-Klassifizierung prüfen und pflegen; Governance-Dokumente aktualisieren; Compliance-Update-Checks durchführen; Schulungen koordinieren; Risikobewertungen erstellen |
| **Darf** | Governance-Dokumente in policies/ ändern; ag-master.md in Abstimmung mit Admin ändern; Compliance-Update-Checks freigeben |
| **Darf nicht** | Modul-Aktivierungen ohne Datenschutzverantwortlichen; AI-Act-Hochrisiko-Klassifizierung eigenmächtig herabstufen; laufende Verarbeitungen ohne VVT-Eintrag genehmigen |
| **Freigaberechte** | Governance-Dokumente; Compliance-Klassifizierungen; Update-Check-Freigaben |
| **Dokumentationspflicht** | Compliance-Update-Checks (Datum, Quellen, betroffene Module); Risikobewertungen; Schulungsnachweise |

---

## Rolle 6: Fachrolle Buchhaltung

**Beschreibung:** Fachverantwortliche für buchhalterische Verarbeitungen — solange ag-buchhaltung blocked ist, ist diese Rolle die operative Ausführungsinstanz.

| Feld | Inhalt |
|---|---|
| **Aufgaben** | Buchungsvorschläge von AILIZA prüfen und freigeben; DATEV-Buchungen selbst vornehmen; Rechnungsbelege verwalten; GoBD-Konformität sicherstellen |
| **Darf** | Buchungsvorschläge von AILIZA als Arbeitsbasis verwenden; AILIZA für Strukturierung und Vorlagen nutzen; Freigabe für tiefere AILIZA-Unterstützung erteilen |
| **Darf nicht** | AILIZA-Ausgaben ohne eigene Prüfung direkt verbuchen; steuerliche Empfehlungen von AILIZA als verbindlich behandeln |
| **Freigaberechte** | Freigabe für AILIZA-Buchhaltungs-Unterstützung (nach Risikohinweis); operative Buchungsfreigabe in DATEV o.ä. |
| **Dokumentationspflicht** | Alle Buchungsfreigaben die auf AILIZA-Vorarbeit basieren; Korrekturen und Abweichungen von AILIZA-Vorschlägen |

---

## Rolle 7: Fachrolle HR

**Beschreibung:** Fachverantwortliche für HR-Verarbeitungen — solange ag-hr blocked ist, ist diese Rolle die operative Ausführungsinstanz.

| Feld | Inhalt |
|---|---|
| **Aufgaben** | HR-Entscheidungen eigenständig treffen; AILIZA nur für risikoarme Vorarbeit nutzen (Textentwürfe, Strukturen); DPIA-Anforderungen für HR-Modul klären |
| **Darf** | AILIZA für allgemeine Texte, Vorlagen, Strukturierungen nutzen; Freigabe für limitierte AILIZA-Unterstützung erteilen |
| **Darf nicht** | Personalentscheidungen auf Basis von AILIZA-Ausgaben ohne eigene Prüfung treffen; Gesundheits- oder Leistungsdaten an AILIZA weitergeben (kein AVV vorhanden) |
| **Freigaberechte** | Freigabe für risikoarme AILIZA-Unterstützung im HR-Kontext; operative HR-Entscheidungen |
| **Dokumentationspflicht** | HR-Entscheidungen mit AILIZA-Bezug; Abweichungen von AILIZA-Vorschlägen |

---

## Rolle 8: Externer Steuerberater / Rechtsberater

**Beschreibung:** Externe Fachrolle für rechtliche und steuerliche Endprüfung.

| Feld | Inhalt |
|---|---|
| **Aufgaben** | Rechtliche oder steuerliche Endprüfung von AILIZA-Ausgaben; Freigabe für Buchhaltungsmodul-Entsperrung (V-01–V-08); AVV-Prüfung |
| **Darf** | AILIZA-Ausgaben als Arbeitsbasis für eigene Prüfung verwenden; Empfehlungen zur Governance und Compliance geben |
| **Darf nicht** | AILIZA-Ausgaben als verbindliche Rechts- oder Steuerberatung behandeln oder weiterreichen; Endverantwortung an AILIZA delegieren |
| **Freigaberechte** | Freigabeempfehlung für Buchhaltungsmodul-Entsperrung; Freigabe für AVV-Abschlüsse |
| **Dokumentationspflicht** | Prüfungsergebnisse; Abweichungen und Korrekturen; Freigabeempfehlungen mit Datum |

---

## Rollenmatrix — Freigaben im Überblick

| Aktion | Nutzer | Admin | Datenschutz | Compliance | Fachrolle | Extern |
|---|---|---|---|---|---|---|
| Core-Anfrage | ✅ | — | — | — | — | — |
| Modul aktivieren (activatable) | ✅ | ✅ | — | — | — | — |
| Modul entsperren (blocked→activatable) | — | ✅ | ✅ (DPIA) | ✅ | — | ✅ (Empfehlung) |
| Buchungsvorschlag freigeben | — | — | — | — | ✅ | ✅ |
| AVV abschließen | — | ✅ | ✅ | — | — | ✅ |
| Governance-Dokumente ändern | — | — | ✅ | ✅ | — | — |
| Audit-Vault-Eintrag erstellen | AILIZA | AILIZA | — | — | — | — |
| Audit-Vault-Eintrag lesen | — | ✅ | ✅ | ✅ | — | — |
| Audit-Vault-Eintrag ändern | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## Offene Punkte

- Besetzung der Rollen 4 (Datenschutzverantwortlicher) und 5 (Compliance) im eigenen Betrieb klären
- Externe Berater (Rolle 8) und ihre Einbindung in AVV-Prozesse vertraglich regeln
- Vertretungsregeln für alle Rollen bei Abwesenheit definieren
