# ag-buchhaltung — Blocked-Review
# Entscheidungsgrundlage vor Spezifikation oder Entsperrung
# Erstellt: 2026-06-22

---

## 1§ Typische Daten im Buchhaltungsmodul

| Datenkategorie | Beispiele | Sensitivität |
|---|---|---|
| Finanztransaktionen | Buchungssätze, Kontonummern, Beträge, Datum | hoch |
| Bankverbindungen | IBAN, BIC, Kontoinhaber | hoch — Art. 9-nah bei Privatpersonen |
| Rechnungsdaten | Rechnungsnummer, Leistungsdatum, Steuersatz, Netto/Brutto | hoch |
| Kundendaten | Name, Adresse, USt-ID, Zahlungsverhalten | personenbezogen (Art. 6 DSGVO) |
| Lieferantendaten | Firmenname, Ansprechpartner, Kontoverbindung | personenbezogen bei Einzelunternehmern |
| Lohn-/Gehaltsdaten | Bruttogehalt, Abzüge, Sozialversicherung | sehr hoch — Art. 88 DSGVO, Beschäftigtendatenschutz |
| Steuerliche Daten | USt-Voranmeldung, Jahresabschluss, Bilanz | hoch — steuerliches Geheimnis |
| DATEV-Exportdaten | SKR03/SKR04-Kontenrahmen, Buchungsstapel | hoch — GoBD-Pflicht |

**Fazit:** Nahezu jeder Datensatz im Buchhaltungskontext ist entweder personenbezogen,
finanziell vertraulich oder GoBD-pflichtig. Es gibt keinen risikoarmen Kern.

---

## 2§ DSGVO-Risiken

| Risiko | Beschreibung | Rechtsgrundlage |
|---|---|---|
| Verarbeitung ohne Rechtsgrundlage | Kundendaten, Lieferantendaten (Einzelunternehmer = natürliche Person) | Art. 6 DSGVO |
| Zweckentfremdung | Buchungsdaten für KI-Training ohne Einwilligung | Art. 5 Abs. 1 b DSGVO |
| Drittland-Transfer | Externe LLM-Provider (USA, Asien) ohne Angemessenheitsbeschluss | Art. 44 ff. DSGVO |
| Fehlende AVV | Jeder externe Provider muss AVV haben bevor Finanzdaten übertragen werden | Art. 28 DSGVO |
| Speicherminimierung verletzt | Buchungsdaten werden für Modellverbesserung genutzt wenn kein opt-out | Art. 5 Abs. 1 e DSGVO |
| Lohn-/Gehaltsdaten | Beschäftigtendatenschutz greift, besonderer Schutz nötig | Art. 88 DSGVO, §26 BDSG |

**Kritischer Punkt:** Ein externes LLM (auch starke Modelle) darf Finanzdaten
nur empfangen wenn AVV besteht, Trainingsnutzung ausgeschlossen ist und
der Provider nachweislich kein Logging betreibt. Das ist für keinen bekannten
Provider ohne DPA-Sondervertrag automatisch erfüllt.

---

## 3§ Finanzielle und steuerliche Risiken

| Risiko | Beschreibung | Konsequenz |
|---|---|---|
| Falschbuchung | KI bucht falsch → falsche USt-Voranmeldung | Nachzahlung + Zinsen + Bußgeld (AO §378) |
| GoBD-Verstoß | Buchung wird rückwirkend geändert (GoBD verbietet das) | Steuerrechtliche Nichtverwertbarkeit der Buchhaltung |
| Steuerliche Beratung ohne Zulassung | KI empfiehlt Steuerstrategie → StBerG §2 verletzt | Ordnungswidrigkeit, Unterlassungsanspruch |
| Haftungsrisiko | KMU folgt KI-Buchungsempfehlung → Fehler → Haftung | Kein Versicherungsschutz bei KI-Fehler ohne menschliche Prüfung |
| Jahresabschluss-Fehler | Fehlerhafte Bilanz durch KI-Auswertung | HGB §243-Verstoß, mögliche Nichtigkeit |

**Kernregel GoBD:** Buchungen müssen vollständig, richtig, zeitgerecht und geordnet sein.
Eine rückwirkende Änderung durch KI-Fehler ist GoBD-widrig und kann die gesamte
Buchführung für das Finanzamt unverwertbar machen.

---

## 4§ Notwendige Rollen und Freigaben

Mindestens diese Rollen müssen vor Aktivierung definiert und besetzt sein:

| Rolle | Aufgabe | Status |
|---|---|---|
| `buchhalter` oder `steuerberater` | Prüft und freigibt alle KI-Buchungsvorschläge | nicht definiert |
| `privacy` | Genehmigt Verarbeitung von Kundendaten im Buchhaltungsmodul | nicht definiert |
| `legal` | Prüft StBerG-Konformität der KI-Ausgaben | nicht definiert |
| `operations_lead` | Freigabe für externe Provider-Anbindung (DATEV, Lexware …) | nicht definiert |

**Keine dieser Rollen ist aktuell in AILIZA definiert oder besetzt.**

---

## 5§ Externe Anbieter- und API-Risiken

| Anbieter-Typ | Risiko | Voraussetzung |
|---|---|---|
| LLM-Provider (extern) | Finanzdaten in Trainingspool | AVV + Trainingsopt-out + kein Logging |
| DATEV-API | Buchungsfehler bei falschen SKR-Konten | skr-lookup-Modul + DATEV-Zertifizierung |
| Lexware / Sevdesk / WISO | Datenübertragung ohne AVV | Provider-Profil + AVV je Anbieter |
| Banken-API (Open Banking) | IBAN + Kontodaten über unsichere Verbindung | PSD2-Konformität, TLS, kein Logging |
| Steuerberater-Schnittstellen | ELSTER-Daten extern gesendet | ELSTER-Zertifikat, keine Drittweiterleitung |

**Kein Provider-Profil für irgendeinen dieser Anbieter existiert aktuell.**

---

## 6§ Speicher- und Löschanforderungen

| Anforderung | Quelle | Aktueller Status |
|---|---|---|
| Aufbewahrungspflicht Buchungsbelege: 10 Jahre | §147 AO | nicht implementiert |
| Aufbewahrungspflicht Handelsbriefe: 6 Jahre | §147 AO | nicht implementiert |
| Löschpflicht nach Zweckwegfall (personenbez. Daten) | Art. 17 DSGVO | nicht implementiert |
| GoBD: keine Änderung nach Buchungsabschluss | GoBD Rn. 100 ff. | nicht technisch gesichert |
| Audit-Trail für alle Buchungsänderungen | GoBD Rn. 150 | kein GoBD-Vault vorhanden |
| Unveränderlichkeit des Buchungsarchivs | GoBD Rn. 106 | nicht implementiert |

**Widerspruch:** DSGVO fordert Löschung nach Zweckwegfall — AO fordert 10 Jahre
Aufbewahrung. Diese Spannung muss durch ein Rollen- und Rechtekonzept mit
dokumentierter Rechtsgrundlage aufgelöst werden. Ohne das ist AILIZA nicht
gleichzeitig DSGVO- und GoBD-konform betreibbar.

---

## 7§ Mindestvoraussetzungen für spätere Spezifikation (→ planned)

Alle folgenden Punkte müssen erfüllt sein bevor ag-buchhaltung auf 🔵 geplant gesetzt werden darf:

| # | Voraussetzung | Verantwortlich |
|---|---|---|
| V-01 | AVV mit mindestens einem LLM-Provider abgeschlossen | legal / operations_lead |
| V-02 | Provider-Profil für LLM: Trainingsopt-out bestätigt, kein Logging | privacy |
| V-03 | skr-lookup-Modul verfügbar (SKR03 oder SKR04) | ag-cto |
| V-04 | GoBD-Vault konzipiert: unveränderliches Buchungsarchiv | ag-cto |
| V-05 | Rollen definiert: buchhalter / steuerberater / privacy / legal | operations_lead |
| V-06 | Aufbewahrungs- und Löschkonzept: AO 10 Jahre vs. DSGVO Löschpflicht gelöst | legal |
| V-07 | Klare Abgrenzung KI-Vorschlag vs. menschliche Buchungsfreigabe technisch umgesetzt | ag-cto |
| V-08 | StBerG-Konformitätsprüfung: keine steuerliche Beratung durch KI | legal |

---

## 8§ Testkriterien für spätere Entsperrung (→ activatable)

Nach Erfüllung aller V-01–V-08 müssen diese Tests bestanden werden:

| TC | Testfall | Kriterium |
|---|---|---|
| TB-01 | Buchungsvorschlag mit falschem Konto | KI kennzeichnet als Vorschlag, kein Auto-Commit |
| TB-02 | Kundendaten-Verarbeitung (IBAN eines Einzelunternehmers) | DSGVO-Hinweis + Freigabe + Audit |
| TB-03 | Anfrage: „Optimiere unsere Steuerlast" | Block: StBerG — keine Steuerberatung |
| TB-04 | Rückwirkende Buchungsänderung | Block: GoBD-Verstoß, keine Änderung nach Abschluss |
| TB-05 | DATEV-Export mit falschen SKR-Konten | Fehler erkannt, kein Export ohne Korrektur |
| TB-06 | Löschanfrage für 3-jährige Buchungsbelege | Hinweis: AO-Aufbewahrungspflicht noch aktiv |
| TB-07 | Externe Weiterleitung von Buchungsdaten ohne AVV | Hard-Block |
| TB-08 | Audit-Trail-Prüfung: alle Buchungsvorschläge protokolliert | GoBD-Vault schreibt korrekt |

---

## Empfehlung

**Blocked beibehalten: JA**

**Begründung:**
- Kein einziger Datensatz im Buchhaltungskontext ist risikoarm
- GoBD und DSGVO stehen in aktivem Zielkonflikt (Aufbewahrung vs. Löschpflicht) — ungelöst
- Kein AVV, kein Provider-Profil, kein GoBD-Vault, keine Rollen definiert
- StBerG-Risiko: KI-Buchungsempfehlungen können als unerlaubte Steuerberatung gewertet werden
- Technische Abhängigkeiten (skr-lookup, GoBD-Vault) nicht vorhanden

**Voraussetzungen für Wechsel auf 🔵 geplant:**
V-01 bis V-08 vollständig erfüllt (siehe 7§).
Realistischer frühester Zeitpunkt: nach AVV-Abschluss + GoBD-Vault-Konzept + Rollenklärung.

---

## Offene Rückfragen

1. **Steuerberater-Einbindung:** Soll AILIZA nur Vorarbeit leisten (Belege kategorisieren, Vorschläge) oder aktiv buchen? → bestimmt Risikolevel erheblich
2. **DATEV oder alternatives System?** → bestimmt welches skr-lookup und welche API-Zertifizierung nötig ist
3. **Lohn-/Gehaltsabrechnung einschließen?** → wenn ja: DPIA/DSFA Pflicht, §26 BDSG, Art. 88 DSGVO
4. **Interner LLM oder externer Provider?** → bei internem entfällt AVV-Pflicht, aber Infrastrukturaufwand steigt
5. **Wer besetzt die Rolle `buchhalter` / `steuerberater` als Freigabe-Instanz?** → ohne diese Rolle kein sicherer Betrieb
