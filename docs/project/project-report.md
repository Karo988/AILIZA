# AILIZA — Projektbericht für Präsentation und Demo

Projekt: AILIZA  
Repository: https://github.com/m-imica/ailiza  
Branch: main  
Fokus: Präsentation, Projektbericht, Demo-Stand  
Status: Entwurf für Präsentation

---

## 1. Was ist AILIZA?

AILIZA ist eine geplante AI-Governance-Plattform.

Ziel ist es, Organisationen dabei zu unterstützen, KI-Anwendungsfälle strukturiert, nachvollziehbar und verantwortbar zu prüfen.

Die Plattform soll insbesondere helfen bei:

- Governance-Prüfungen
- QA- und Audit-Strukturen
- Dokumentation von KI-Use-Cases
- AI-Act-orientierter Einordnung
- DSGVO-orientierter Datenschutzprüfung
- Nachvollziehbarkeit von Entscheidungen
- Vorbereitung von Demo-, Review- und späteren Freigabeprozessen

AILIZA ist aktuell als Projekt- und Demo-Grundlage zu verstehen, nicht als produktiv freigegebenes System.

---

## 2. Welches Problem lösen wir?

Unternehmen stehen vor der Herausforderung, KI-Systeme nicht nur technisch, sondern auch organisatorisch, rechtlich, ethisch und qualitativ verantwortbar einzusetzen.

Typische Probleme sind:

- unklare Zuständigkeiten
- fehlende Dokumentation
- uneinheitliche Bewertung von KI-Use-Cases
- fehlende Nachweise für Entscheidungen
- Unsicherheit bei EU AI Act und DSGVO
- fehlende Governance- und QA-Prüflogik
- Risiko der Verwechslung von Demo, Test und Produktivsystem
- fehlende Transparenz zu offenen technischen Punkten

AILIZA soll dafür eine strukturierte Plattformlogik bereitstellen.

Der Kernnutzen liegt darin, KI-Vorhaben nicht zufällig oder rein technisch zu bewerten, sondern anhand eines wiederholbaren Governance- und QA-Prozesses.

---

## 3. Warum EU AI Act und DSGVO?

Der EU AI Act schafft einen risikobasierten Rahmen für KI-Systeme im EU-Raum.

Die DSGVO regelt weiterhin die Verarbeitung personenbezogener Daten.

Für AILIZA bedeutet das:

- KI-Use-Cases müssen risikobasiert eingeordnet werden.
- Personenbezogene Daten müssen erkannt und bewertet werden.
- Datenschutzstatus und Verantwortlichkeiten müssen dokumentiert werden.
- Kritische Fälle müssen eskaliert werden können.
- Entscheidungen müssen nachvollziehbar und prüfbar sein.
- Governance darf nicht nur beschrieben, sondern als Prozess abgebildet werden.

Wichtig:

AILIZA ersetzt keine Rechtsberatung und keine Datenschutz-Folgenabschätzung durch zuständige Rollen. Die Plattform soll jedoch helfen, Prüfungen vorzubereiten, zu strukturieren und nachvollziehbar zu dokumentieren.

---

## 4. Was wurde bisher umgesetzt?

### Dokumentation

Bisher wurden Grundlagen für eine strukturierte Projektdokumentation vorbereitet.

Dazu gehören:

- README als Einstiegspunkt
- Onboarding-Informationen
- Team-Workflow
- Governance- und QA-Dokumentation
- Demo-Review
- EMAVE-basierte Prüfstruktur
- Status- und Auditlogik

### Governance

Governance wurde als wiederholbarer Prüfprozess vorbereitet.

Zentrale Elemente:

- EMAVE-Prozess
- Governance- und Audit-Prinzipien
- Prüffragen je Dimension
- Statuslogik mit Ampelprinzip
- Risiko- und Gegenmaßnahmenmatrix
- Schutz vor Halluzinationen
- Schutz vor Manipulation und Prompt Injection
- Schutz vor Hacking und technischen Angriffen

### QA

QA wurde als Review- und Nachweisprozess vorbereitet.

Zentrale Elemente:

- Prüfung von GitHub Workflow
- Prüfung von Branch Workflow
- Dokumentation offener Punkte
- Demo-Review-Struktur
- bekannte Risiken
- nächste Schritte
- Definition von Demo-Fähigkeit mit Einschränkungen

### Demo-Review

Für die Demo wurde eine QA- und Governance-Zusammenfassung erstellt.

Bewertung:

- QA-Review fertig: Ja
- Demo-fähig: Ja, mit Einschränkungen

Einschränkungen:

- Authentifizierung offen
- Persistenz offen
- produktive Tests offen
- Agent Runtime offen

---

## 5. Aktueller Stand der Demo

Die Demo ist aus Governance-/QA-Sicht präsentationsfähig, sofern klar kommuniziert wird, dass es sich nicht um ein produktiv freigegebenes System handelt.

Aktuell demonstrierbar:

- Projektidee
- Governance-Ansatz
- QA-/Audit-Prüflogik
- EMAVE-Prozess
- Dokumentationsstruktur
- Statuslogik
- Risiko- und Gegenmaßnahmenlogik
- Abgrenzung technischer offener Punkte

Nicht als produktiv fertig zu bewerten:

- Authentifizierung
- Persistenz
- produktive Tests
- Agent Runtime
- vollständige technische Durchsetzung aller Governance-Regeln

---

## 6. Governance- und QA-Leitlogik

Die Governance-/QA-Logik basiert auf dem EMAVE-Prozess.

EMAVE steht für:

| Dimension | Bedeutung |
|---|---|
| E | Engpass lösen |
| M | Mitarbeitende entlasten |
| A | Arbeitsplatzattraktivität steigern |
| V | Verantwortbar machen |
| E | Entscheidungsfähigkeit herstellen |

Diese Logik stellt sicher, dass KI-Anwendungsfälle nicht nur technisch, sondern auch organisatorisch und verantwortungsbezogen geprüft werden.

Leitfrage:

Welcher menschliche, organisatorische und kundenseitige Engpass soll durch KI-gestützte Prozesse verantwortungsvoll entschärft werden?

---

## 7. Bekannte Risiken

| Risiko | Bewertung | Umgang |
|---|---|---|
| Authentifizierung offen | Hoch | Zuständigkeit klären, nicht als produktiv darstellen |
| Persistenz offen | Mittel | Demo mit Test-/Beispieldaten abgrenzen |
| Produktive Tests offen | Hoch | Keine Produktivfreigabe kommunizieren |
| Agent Runtime offen | Mittel | Runtime-Core-Zuständigkeit klären |
| Governance noch nicht vollständig technisch erzwungen | Mittel | Als nächsten Entwicklungsschritt aufnehmen |
| Verwechslung von Demo und Produktivsystem | Hoch | Präsentation ausdrücklich als Demo-Stand kennzeichnen |

---

## 8. Nächste Entwicklungsschritte

| Schritt | Aufgabe | Zuständig | Priorität |
|---|---|---|---|
| 1 | Projektbericht finalisieren | Governance/QA | Hoch |
| 2 | Demo-Abgrenzung in Präsentation aufnehmen | Projektteam | Hoch |
| 3 | Authentifizierung klären | Runtime Core | Hoch |
| 4 | Persistenzkonzept klären | Runtime Core | Mittel |
| 5 | Produktive Teststrategie definieren | QA + Runtime Core | Mittel |
| 6 | Agent Runtime Status klären | Runtime Core | Mittel |
| 7 | Governance-Regeln später technisch operationalisieren | Product + Runtime Core + QA | Mittel |
| 8 | EMAVE-Dashboard als unterstützende Review-Oberfläche prüfen | Governance/QA | Mittel |

---

## 9. Fehlende Informationen

Für die nächste Projektphase fehlen noch:

- finaler Status der Authentifizierung
- finales Persistenzkonzept
- genauer Status der Agent Runtime
- definierte produktive Teststrategie
- finale Rollenklärung für technische Umsetzung
- finale Entscheidung, welche Governance-Regeln zuerst technisch umgesetzt werden
- Entscheidung, ob das EMAVE-Dashboard in die Projektdokumentation aufgenommen wird

---

## 10. Zusammenfassung für die Präsentation

AILIZA ist eine AI-Governance-Plattform im Aufbau.

Das Projekt adressiert die wachsende Notwendigkeit, KI-Anwendungen nicht nur technisch, sondern auch verantwortbar, prüfbar und dokumentiert einzusetzen.

Bisher wurden zentrale Grundlagen geschaffen:

- Projekt- und Workflow-Dokumentation
- Governance- und QA-Struktur
- EMAVE-Prüfprozess
- Demo-Review
- Risiko- und Statuslogik
- klare Abgrenzung offener technischer Punkte

Der aktuelle Stand ist präsentationsfähig, aber nicht produktiv freigegeben.

---

## 11. Abschlussstatus

Projektbericht fertig: Ja

Fehlende Informationen:

- Authentifizierung
- Persistenz
- produktive Tests
- Agent Runtime
- technische Durchsetzung der Governance-Regeln

Nächste Schritte:

- Bericht reviewen
- Präsentationsfassung ableiten
- offene technische Punkte mit Runtime Core klären
- Demo klar als Review- und Konzeptstand kennzeichnen
