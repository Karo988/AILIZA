# AILIZA — EU AI Act Use-Case-Klassifikation

**Version:** 1.0  
**Stand:** 2026-06-23  
**Nächste Überprüfung:** 2026-12-23  
**Rechtsgrundlage:** EU AI Act (Verordnung (EU) 2024/1689), insb. Art. 5, Art. 6, Anhang III, Art. 50, Art. 52  
**Verantwortlich:** System Owner (SO), Datenschutzverantwortliche/r (DSV)  
**Hinweis:** Diese Klassifikation ist eine interne Einschätzung zum aktuellen Implementierungsstand. Sie ersetzt keine rechtliche Prüfung. Wo die Einschätzung unsicher ist, wird dies ausdrücklich als offen markiert.

---

## Einstufungsskala

| Kürzel | Bedeutung |
|---|---|
| **minimal_risk** | Keine besonderen AI-Act-Anforderungen. Gute Praxis empfohlen. |
| **transparency_risk** | Art. 50 EU AI Act: Nutzer muss wissen, dass er mit KI interagiert. |
| **high_risk_candidate** | Möglicherweise Anhang III EU AI Act. Rechtsprüfung erforderlich. Nicht aktivierbar ohne Prüfung. |
| **prohibited** | Art. 5 EU AI Act: Verbotene Praxis. Nicht implementierbar. |
| **responsibility_handoff** | AILIZA ist kein geeignetes System für diesen Use Case. Weiterleitung an Fachpersonen oder spezialisierte geprüfte Systeme. |

---

## Use-Case-Übersicht

| Nr. | Use Case | Einstufung | Status |
|---|---|---|---|
| UC01 | Core Chat (local_only) | transparency_risk | ✅ aktiv |
| UC02 | Dokument-Scan | minimal_risk | ✅ aktiv |
| UC03 | Prompt-Injection-Erkennung | minimal_risk | ✅ aktiv |
| UC04 | Audit-Vault | minimal_risk | ✅ aktiv |
| UC05 | Präsentation / Erklärung | transparency_risk | ✅ aktiv (lokal) |
| UC06 | Recherche | transparency_risk | ⚠️ local_only (kein Provider) |
| UC07 | Dokumentenverarbeitung | transparency_risk | ⚠️ Scan aktiv, Analyse geplant |
| UC08 | Schulung / Erklärung | transparency_risk | ⚠️ geplant |
| UC09 | Buchhaltung | responsibility_handoff | 🔲 nicht aktiviert |
| UC10 | HR / Personal | responsibility_handoff | 🔲 nicht aktiviert |

---

## Detailbeschreibung je Use Case

---

### UC01 — Core Chat (local_only-Modus)

| Feld | Inhalt |
|---|---|
| **Beschreibung** | Nutzer stellt Fragen, AILIZA antwortet ohne externen Provider. Keine LLM-Calls, kein Netzwerkzugang. |
| **AI-Act-Einstufung** | transparency_risk |
| **Begründung** | Art. 50 EU AI Act: System interagiert mit natürlichen Personen und muss sich als KI erkennbar machen. Kein Hochrisiko-Tatbestand erkennbar. |
| **Menschliche Aufsicht** | Nutzer sieht alle Antworten direkt. Kein autonomes Handeln. |
| **Erlaubter Status** | ✅ Aktiv und zulässig |
| **Grenzen** | Keine Rechtsberatung. Keine Entscheidungen mit rechtlichen Folgen für Dritte. Keine sensiblen Daten eingeben (Passwörter, Gesundheitsdaten etc.). |
| **Offene Punkte** | KI-Kennzeichnung im UI prüfen (Art. 50 Nachweis) |

---

### UC02 — Dokument-Scan

| Feld | Inhalt |
|---|---|
| **Beschreibung** | Hochgeladene Dateien werden auf Typ, Größe, Prompt-Injection, Risikoklasse und Datenklassen geprüft. |
| **AI-Act-Einstufung** | minimal_risk |
| **Begründung** | Rein technische Sicherheitsfilterung, kein eigenständiges KI-Modell zur Entscheidungsfindung über Personen. |
| **Menschliche Aufsicht** | Scan-Ergebnis wird dem Nutzer angezeigt. Kein automatisches Löschen oder Blockieren ohne Anzeige. |
| **Erlaubter Status** | ✅ Aktiv und zulässig |
| **Grenzen** | Kein vollständiges Antivirensystem. Ersetzt keine professionelle Dokument-Sicherheitsprüfung. |
| **Offene Punkte** | Regelmäßige Überprüfung der Erkennungsmuster empfohlen |

---

### UC03 — Prompt-Injection-Erkennung

| Feld | Inhalt |
|---|---|
| **Beschreibung** | Automatische Erkennung von Injection-Mustern in Nutzereingaben und Dokumenten (Gate 6). |
| **AI-Act-Einstufung** | minimal_risk |
| **Begründung** | Sicherheitsmaßnahme, keine Entscheidung über Personen, keine autonomen Auswirkungen auf Dritte. |
| **Menschliche Aufsicht** | Erkennungsergebnis wird protokolliert. Nutzer wird informiert. |
| **Erlaubter Status** | ✅ Aktiv und zulässig |
| **Grenzen** | Erkennt musterbasiert — kein vollständiger Schutz vor unbekannten Angriffsvektoren. |
| **Offene Punkte** | Musterpflege: Neue Injection-Patterns ergänzen |

---

### UC04 — Audit-Vault

| Feld | Inhalt |
|---|---|
| **Beschreibung** | Append-only Protokollierung aller Systemereignisse, Admin-lesbar, kein Löschen durch System. |
| **AI-Act-Einstufung** | minimal_risk |
| **Begründung** | Art. 12 EU AI Act: Protokollierungspflicht für KI-Systeme. Audit-Vault erfüllt diese Anforderung. Kein KI-Modell im Audit-Pfad. |
| **Menschliche Aufsicht** | Alle Einträge sind durch Admin prüfbar. Löschung nur mit DSGVO-Art.-17-Dokumentation und Vier-Augen. |
| **Erlaubter Status** | ✅ Aktiv und zulässig |
| **Grenzen** | Stufe 1 nur lesend. Stufe 2 (Retention-Cleanup) noch nicht implementiert. |
| **Offene Punkte** | Stufe 2 nach Freigabe implementieren. DSGVO-Art.-17-Prozess formalisieren. |

---

### UC05 — Präsentation / Erklärung

| Feld | Inhalt |
|---|---|
| **Beschreibung** | AILIZA erklärt Sachverhalte, gibt Übersichten, beantwortet allgemeine Fragen — als lokales System ohne Provider. |
| **AI-Act-Einstufung** | transparency_risk |
| **Begründung** | Art. 50: Interaktion mit natürlichen Personen. Keine autonomen Entscheidungen. Kein Hochrisiko-Tatbestand. |
| **Menschliche Aufsicht** | Nutzer liest und bewertet jede Antwort selbst. |
| **Erlaubter Status** | ✅ Zulässig im local_only-Modus |
| **Grenzen** | Kein Ersatz für Fachberatung. KI-Kennzeichnung erforderlich. Keine Gewähr auf Richtigkeit. |
| **Offene Punkte** | KI-Kennzeichnung im UI formal dokumentieren |

---

### UC06 — Recherche

| Feld | Inhalt |
|---|---|
| **Beschreibung** | AILIZA erstellt Rechercheplan oder führt Websuche durch (mit Provider: Tavily). |
| **AI-Act-Einstufung** | transparency_risk |
| **Begründung** | Keine Entscheidung über Personen. Art. 50: KI-Kennzeichnung erforderlich. |
| **Menschliche Aufsicht** | Rechercheergebnis wird angezeigt. Nutzer entscheidet über Verwendung. |
| **Erlaubter Status** | ⚠️ Local-Modus aktiv (Rechercheplan ohne Websuche). Provider-Aktivierung erst nach AVV. |
| **Grenzen** | Keine Faktengarantie. Quellen immer kritisch prüfen. Kein Ersatz für professionelle Recherche bei rechtsrelevanten Themen. |
| **Offene Punkte** | Tavily-AVV prüfen. Provider nur nach Freigabe aktivieren. |

---

### UC07 — Dokumentenverarbeitung

| Feld | Inhalt |
|---|---|
| **Beschreibung** | Analyse, Zusammenfassung oder Extraktion aus hochgeladenen Dokumenten mit LLM-Unterstützung. |
| **AI-Act-Einstufung** | transparency_risk |
| **Begründung** | Abhängig vom Dokumentinhalt: Bei Verträgen, Personalakten oder Gesundheitsdaten möglicherweise höheres Risiko. Aktuelle Nutzung: nur Scan ohne LLM-Analyse. |
| **Menschliche Aufsicht** | Analyse-Ergebnis immer durch Nutzer prüfen. Kein automatisches Weiterleiten. |
| **Erlaubter Status** | ⚠️ Scan aktiv. LLM-Analyse noch nicht aktiv — Aktivierung erst nach Provider-Freigabe. |
| **Grenzen** | Keine rechtlich verbindliche Dokumentenprüfung. Kein Ersatz für Anwalt oder Steuerberater. |
| **Offene Punkte** | Bei Aktivierung der LLM-Analyse: Dokumenttypen einschränken, Redaction sicherstellen. |

---

### UC08 — Schulung / Lernen / Erklärung

| Feld | Inhalt |
|---|---|
| **Beschreibung** | AILIZA erklärt Konzepte, gibt Lernhilfen, beantwortet Fragen zu Gesetzen, Prozessen, Systemen. |
| **AI-Act-Einstufung** | transparency_risk |
| **Begründung** | Bildungsunterstützung ohne Entscheidungswirkung. Art. 50: KI-Kennzeichnung. Kein Hochrisiko-Tatbestand (Bildung ist Anhang III — prüfen ob Bewertungsfunktion vorhanden). |
| **Menschliche Aufsicht** | Nutzer entscheidet über Annahme der Inhalte. Keine automatische Bewertung von Personen. |
| **Erlaubter Status** | ⚠️ Geplant. Aktivierung nach Provider-Freigabe. Keine Benotung oder Bewertung von Personen. |
| **Grenzen** | AILIZA darf keine Menschen bewerten, einstufen oder Entscheidungen über Lernfortschritte treffen. Solche Funktionen wären high_risk_candidate (Anhang III Bildung). |
| **Offene Punkte** | Vor Aktivierung: Sicherstellen dass keine Personenbewertung implementiert wird. |

---

### UC09 — Buchhaltung

| Feld | Inhalt |
|---|---|
| **Beschreibung** | Buchhaltungsaufgaben wie Belegerfassung, Kategorisierung, Zahlungsvorschläge mit KI-Unterstützung. |
| **AI-Act-Einstufung** | responsibility_handoff |
| **Begründung** | Buchhaltung hat unmittelbare rechtliche und finanzielle Folgen. Fehler können Steuerpflichten und Haftungsrisiken auslösen. AILIZA ist kein geprüftes Buchhaltungssystem. Anhang III (Critical Infrastructure / Access to essential services) möglicherweise relevant — rechtliche Prüfung erforderlich. |
| **Menschliche Aufsicht** | Vollständige menschliche Prüfung und Verantwortung für alle Buchungen. |
| **Erlaubter Status** | 🔲 Nicht aktiviert. Nur mit expliziter Nutzerfreigabe, Rechtsprüfung und Dokumentation aktivierbar. |
| **Grenzen** | Kein automatisches Erstellen oder Verbuchen von Buchungssätzen. Kein Ersatz für Steuerberater oder DATEV-zertifiziertes System. |
| **Offene Punkte** | Rechtsprüfung durch Steuerberater erforderlich. Keine Aktivierung ohne schriftliche Freigabe. |

---

### UC10 — HR / Personal

| Feld | Inhalt |
|---|---|
| **Beschreibung** | Personalaufgaben wie Bewerbungsscreening, Mitarbeiterbewertung, Gehaltsvorschläge mit KI-Unterstützung. |
| **AI-Act-Einstufung** | responsibility_handoff (Tendenz: high_risk_candidate) |
| **Begründung** | Anhang III EU AI Act: KI-Systeme für Personalentscheidungen sind explizit als Hochrisiko-KI gelistet (Art. 6 i.V.m. Anhang III Nr. 4). AILIZA ist nicht als Hochrisiko-KI nach EU AI Act konformitätsbewertet. Einsatz ohne vollständige Konformitätsprüfung verboten. |
| **Menschliche Aufsicht** | Alle Personalentscheidungen müssen von qualifizierten Fachpersonen getroffen werden. KI-Unterstützung nur als Hilfsmittel, nie als Entscheidungsgrundlage. |
| **Erlaubter Status** | 🔴 Nicht aktivierbar ohne vollständige AI-Act-Hochrisiko-Konformitätsprüfung, Datenschutz-Folgenabschätzung (DSFA) und schriftliche Freigabe durch DSV, SO und Rechtsberatung. |
| **Grenzen** | Kein Bewerbungsscreening. Keine Mitarbeiterbewertung. Keine Gehaltsempfehlung mit Entscheidungswirkung. |
| **Offene Punkte** | Vor jeder Nutzung im HR-Bereich: Rechtsberatung, DSFA, AVV, Konformitätsprüfung. |

---

## Zusammenfassung: Was ist aktuell zulässig?

| Use Case | Status |
|---|---|
| Fragen stellen (local_only) | ✅ Zulässig |
| Dokument scannen | ✅ Zulässig |
| Prompt-Injection-Schutz | ✅ Zulässig |
| Audit einsehen (Admin) | ✅ Zulässig |
| Erklärungen / Präsentationen (lokal) | ✅ Zulässig |
| Recherche lokal (Rechercheplan) | ✅ Zulässig (kein Provider) |
| Recherche mit Websuche | ⚠️ Erst nach Provider-AVV |
| Dokumentenanalyse mit LLM | ⚠️ Erst nach Provider-AVV |
| Schulung/Erklärung ohne Bewertung | ⚠️ Erst nach Provider-AVV |
| Buchhaltung | 🔲 Erst nach Freigabe + Rechtsprüfung |
| HR/Personal | 🔴 Nicht ohne Hochrisiko-Konformitätsprüfung |

---

*Stand: 2026-06-23 — Diese Klassifikation ist eine interne Einschätzung, keine Rechtsberatung. Fehlende Prüfungen sind offen markiert.*
