# AILIZA v1.0 Beta Ready – Baustein 1: Provider-Profil-System

## Ziel

Dieses Dokument definiert das Provider-Profil-System für AILIZA.

Das Provider-Profil beschreibt, welche KI-Anbieter, Modelle und Tools grundsätzlich verwendet werden dürfen.

Wichtig:
Das Provider-Profil trifft keine endgültige Sicherheitsentscheidung zur Laufzeit.  
Die endgültige Entscheidung trifft immer das Tool-Gateway.

## Grundregel

Datenschutz und Sicherheit haben Vorrang vor:

- Kosten
- Geschwindigkeit
- Komfort
- technischer Bequemlichkeit

Wenn eine Information unklar ist, gilt die restriktivere Entscheidung.

## Trennung der Verantwortlichkeiten

### Agent

Der Agent darf:

- Nutzeranfragen verstehen
- Aufgaben vorbereiten
- Risiken vorprüfen
- Vorschläge machen
- Erklärungen liefern

Der Agent darf nicht:

- Sicherheitsregeln endgültig umgehen
- allein über externe Verarbeitung entscheiden
- Freigaben ersetzen
- sensible Daten eigenständig an externe Anbieter senden

### Provider-Profil

Das Provider-Profil enthält:

- Anbietername
- Modellname
- Hosting-Region
- Datenverarbeitung
- Trainingsnutzung
- Risikoklasse
- Vertrauensstufe
- Mindestfreigabe
- erlaubte Datenklassen
- verbotene Datenklassen

Das Provider-Profil ist Konfiguration, kein Laufzeit-Gateway.

### Tool-Gateway

Das Tool-Gateway entscheidet zur Laufzeit:

- ob ein Tool genutzt werden darf
- ob Daten extern verarbeitet werden dürfen
- ob lokale Verarbeitung erzwungen wird
- ob eine Freigabe nötig ist
- ob eine Aktion blockiert wird

Die strengste Regel gewinnt.

## Datenklassen

### L0 – Öffentlich

Beispiele:

- öffentliche Produkttexte
- öffentlich sichtbare Webseiteninhalte
- allgemeine Informationen

Verarbeitung:
Darf grundsätzlich extern verarbeitet werden, wenn der Provider freigegeben ist.

### L1 – Intern

Beispiele:

- interne Notizen
- nicht öffentliche Prozessinformationen
- interne Arbeitsdokumente

Verarbeitung:
Nur mit freigegebenen Providern.

### L2 – Vertraulich

Beispiele:

- Verträge
- Rechtsdokumente
- interne Kalkulationen
- geschäftskritische Informationen

Verarbeitung:
Externe Verarbeitung nur mit erhöhter Freigabe.

### L3 – Personenbezogen / Zahlungsdaten

Beispiele:

- Name
- Adresse
- E-Mail
- Telefonnummer
- IBAN
- Kreditkartendaten

Verarbeitung:
Standardmäßig restriktiv.  
Externe Verarbeitung nur bei klarer Rechtsgrundlage, Freigabe und geeignetem Provider.

### L4 – Besonders kritisch

Beispiele:

- Bewerbungsdaten
- Gesundheitsbezug
- Minderjährigendaten
- sensible Kundenfälle

Verarbeitung:
Vorrangig lokal. Extern nur mit ausdrücklicher Freigabe und dokumentierter Prüfung.

### L5 – Verboten / Höchstrisiko

Beispiele:

- Zugangsdaten
- Passwörter
- API-Schlüssel
- besondere Kategorien nach Art. 9 DSGVO
- strafrechtliche Daten nach Art. 10 DSGVO
- unbekannte oder nicht klassifizierbare Hochrisikodaten

Verarbeitung:
Nicht extern verarbeiten.  
Fail-closed.

## Provider-Risikoklassen

### niedrig

Geeignet für einfache, nicht sensible Aufgaben.

### mittel

Geeignet für interne und teilweise vertrauliche Aufgaben bei passenden Schutzmaßnahmen.

### hoch

Nur für klar begrenzte Aufgaben mit Freigabe.

### gesperrt

Darf nicht verwendet werden.

## Vertrauensstufen

### unknown

Unbekannter Status.  
Wird restriktiv behandelt.

### basic

Grunddaten bekannt.  
Nur für niedrige Datenklassen.

### verified

Provider wurde geprüft.  
Geeignet für definierte interne Aufgaben.

### trusted

Provider erfüllt hohe Anforderungen an Datenschutz, Sicherheit und Nachvollziehbarkeit.

## Mindestfreigabe

Das Feld `approval_floor` beschreibt die niedrigste erforderliche Freigabestufe.

Wichtig:
`approval_floor` ist nur die Mindestgrenze.  
Das Tool-Gateway kann zur Laufzeit eine strengere Freigabe verlangen.

## Pflichtfelder eines Provider-Profils

```yaml
provider_id:
provider_name:
model_name:
hosting_region:
data_residency:
training_use:
logging:
provider_risk_class:
trust_level:
approval_floor:
allowed_data_classes:
blocked_data_classes:
notes:
last_reviewed:
