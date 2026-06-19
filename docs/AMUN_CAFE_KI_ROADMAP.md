# AMUN CAFÉ — KI-STRATEGIE ROADMAP
## Basierend auf dem KIUSCA-Framework (WBS Tage 01–03)
**Datum:** 19.06.2026 | **Erstellt von:** AILIZA / Amun-Online

---

## ZUSAMMENFASSUNG AUS DEN KIUSCA-KURSDATEN

Die folgenden Frameworks und Methoden wurden aus dem Kurs extrahiert und direkt auf das **Amun Café** übertragen:

- **Tag 01:** KI-Roadmap, Grundlagen (Supervised/Unsupervised/Generative AI), Bedarfsanalyse, Expertenteam
- **Tag 02:** Process Mining, Use Case Discovery, Data Readiness (GIGO-Prinzip), Best-Practice-Case-Studies
- **Tag 03:** Systematische Bewertung (Consultant-Scorecard), MoSCoW-Methode, Impact-Effort-Matrix

---

## TEIL 1 — UNTERNEHMENSPROFIL: AMUN CAFÉ

**Konzept:** Top-Café mit Fokus auf Premium-Kundenerlebnis, Effizienz und Nachhaltigkeit  
**Eigentümer:** Amun-Online (service@amun-online.de)  
**Zielgruppe:** Anspruchsvolle Kaffeegäste, Business-Kunden, Lifestyle-orientierte Stammgäste  

### Strategische Säulen (Top-Down-Ansatz)

| Strategie | Ziel | KI-Übersetzung |
|---|---|---|
| **Maximale Profitabilität** | Kosten senken, Umsatz steigern | KI-gestützte Bedarfsvorhersage (Zutaten, Personal) |
| **Zero Waste & Nachhaltigkeit** | Lebensmittelverschwendung stoppen | Predictive Analytics für Einkauf & Lager |
| **Premium Kundenerlebnis** | Wartezeiten minimieren, Frust vermeiden | KI-Chatbot, smarte Bestellsysteme |

---

## TEIL 2 — SCHMERZ-ANALYSE (Pain Points) AMUN CAFÉ

### Bottom-Up-Identifikation der größten Probleme:

**Pain Point 1: Überproduktion & Food Waste**
- Problem: Täglich werden zu viele Croissants, Sandwiches und Tagesgerichte vorbereitet → enden im Müll
- KI-Ziel: Predictive Analytics berechnet täglich die benötigte Menge basierend auf Wochentag, Wetter, Ereignissen
- KI-Typ: **Supervised Learning** (lernt aus historischen Kassendaten)
- Vorbild: IKEA + Winnow Vision → 75% weniger Food Waste

**Pain Point 2: Lange Wartezeiten im Tagesgeschäft**
- Problem: Stoßzeiten (7–9 Uhr, 12–13 Uhr) führen zu langen Schlangen → Gäste verlassen das Café
- KI-Ziel: Echtzeitanzeige der Wartezeit + proaktive Benachrichtigung per App
- KI-Typ: **Unsupervised Learning** (erkennt Muster in Besucherströmen)
- Vorbild: Disney MagicBand → proaktive Besucherlenkung

**Pain Point 3: Ineffizienter Kundenservice / häufige Standardfragen**
- Problem: Personal beantwortet täglich dieselben Fragen (Öffnungszeiten, Speisekarte, Allergene)
- KI-Ziel: Chatbot auf Website/WhatsApp beantwortet Standardfragen rund um die Uhr
- KI-Typ: **Generative AI** (NLU + Chatbot)
- Vorbild: Lufthansa "Elisa" → Hunderttausende Anfragen ohne Personal gelöst

**Pain Point 4: Personaleinsatzplanung**
- Problem: Zu viel Personal an ruhigen Tagen, zu wenig in Stoßzeiten
- KI-Ziel: KI berechnet optimalen Personalbedarf pro Schicht
- KI-Typ: **Supervised Learning** (Vorhersage-Modell)

**Pain Point 5: Lagerbestandsmanagement**
- Problem: Zutaten werden zu früh oder zu spät bestellt → Engpässe oder Übervorräte
- KI-Ziel: Automatische Bestellvorschläge basierend auf Verbrauchsprognosen
- KI-Typ: **Supervised Learning**

---

## TEIL 3 — KI-EXPERTENTEAM FÜR AMUN CAFÉ

Gemäß KIUSCA-Framework (Tag 01, Block 03):

| Rolle | Person / Funktion im Café | Verantwortung |
|---|---|---|
| **Product Owner (PO)** | Inhaber / Geschäftsführer (Amun) | Budget, Business-Case, Projektziel |
| **Domain Expert** | Café-Manager / Head Barista | Kennt den Alltag, nutzt die KI täglich |
| **Data Steward** | Kassensystem-Administrator | Verwaltet Kassendaten, Bestellhistorie, DSGVO |
| **Tech Lead** | Externer KI-Berater / AILIZA | Plattformwahl, technische Bewertung |
| **Change Manager** | Teamleitung / Schichtleitung | Akzeptanz bei Mitarbeitern, Schulungen |

---

## TEIL 4 — PROCESS MINING FÜR AMUN CAFÉ

### Die 3 Analyse-Methoden (Tag 02, Block 01):

**1. Process Mining (Digitale System-Ebene)**
- Was analysieren wir? Kassensystem-Logs (Event Logs): Bestellaufnahme → Zubereitung → Ausgabe
- Zwingende Parameter: Case ID (Bestellnummer), Activity (z.B. "Kaffee bestellt"), Timestamp
- Ziel: Flaschenhälse im Bestellprozess sichtbar machen

**2. Task Mining (Desktop-Ebene)**
- Was analysieren wir? Wie lange klickt das Personal im POS-System?
- Ziel: Menüführung im Kassensystem optimieren, Klickwege reduzieren

**3. Gemba-Walk (Physische Realität)**
- Was beobachten wir? Laufwege der Baristas, Positionierung der Kaffeemaschinen, Milchschaum-Engpässe
- Ziel: Physische Hindernisse identifizieren, die kein System erfasst

### Consultant-Workflow für Amun Café:
1. **Daten laden:** Anonymisierten Export aus der Kasse (CSV) in KI-Tool laden
2. **Prompten & Finden:** "Zeige den Prozessfluss von Bestellung bis Ausgabe und markiere den größten Flaschenhals"
3. **Ursache klären:** Liegt der Stau beim Bezahlvorgang, bei der Zubereitung, oder beim Ausgabe-Tresen?
4. **Use Case Matching:** Edge-KI für Kassensystem (Echtzeit, kein Internetausfall), Cloud-KI für Tagesprognosen

---

## TEIL 5 — DATA READINESS AUDIT (GIGO-CHECK)

Vor jedem KI-Projekt: Sind unsere Daten KI-bereit?

| Dimension | Status Amun Café | Maßnahme |
|---|---|---|
| **Verfügbarkeit** | Kassendaten vorhanden? Wetter-API? | Kassendaten exportieren, Wetter-API integrieren |
| **Volumen** | Mind. 12 Monate Transaktionsdaten? | Historische Kassenberichte sichern |
| **Struktur** | CSV/SQL oder Papier-/Freitext? | Digitales POS-System sicherstellen |
| **Zugänglichkeit** | API-Zugriff auf Kassendaten? | Kassensystem-Schnittstelle prüfen |

**GIGO-Regel:** Schlechte Daten → schlechte KI-Entscheidungen. Zuerst Datenbasis aufbauen, dann KI.

---

## TEIL 6 — SYSTEMATISCHE BEWERTUNG (Consultant-Scorecard, Tag 03)

### 4-Dimensionen-Bewertung aller Use Cases:

| Use Case | Dim. A: ROI-Dringlichkeit | Dim. B: Architektur | Dim. C: Data Readiness | Dim. D: Risiko/Fallback |
|---|---|---|---|---|
| **Food Waste Vorhersage** | HOCH — tägl. Verluste | Cloud-KI (keine Echtzeit nötig) | MITTEL — Kassendaten vorhanden | Fallback: manuelle Planung |
| **Wartezeit-Chatbot** | HOCH — Umsatzverlust in Stoßzeiten | Edge-KI am Tresen | GUT — Echtzeit-Daten | Fallback: Personal übernimmt |
| **KI-Chatbot Website** | MITTEL — Servicequalität | Cloud-KI (ChatGPT API) | GUT — FAQs verfügbar als PDF | Fallback: E-Mail/Telefon |
| **Personaleinsatzplanung** | HOCH — Überkosten Personal | Cloud-KI (Nacht-Berechnung) | MITTEL — Dienstpläne digitalisieren | Fallback: Excel-Planung |
| **Lagerbestellung KI** | MITTEL — Kostensenkung | Cloud-KI | NIEDRIG — erst aufbauen | Fallback: manuelle Bestellung |

---

## TEIL 7 — MOSCOW-PRIORISIERUNG FÜR AMUN CAFÉ

### Must Have (Kritisch — ohne diese geht nichts):
- **Digitales Kassensystem mit API** — ohne Daten keine KI
- **Food Waste Vorhersage** — direkte tägliche Kostenersparnis
- **KI-Chatbot für Website/WhatsApp** — 24/7 Kundenkommunikation (sofort umsetzbar mit Custom GPT)

### Should Have (Wichtig, manuell überbrückbar):
- **Personaleinsatzplanung KI** — senkt Personalkosten signifikant
- **Wartezeit-Anzeige Echtzeit** — verbessert Kundenerlebnis

### Could Have (Nett, wenn Budget vorhanden):
- **Stammkunden-Erkennung per App** (personalisierte Empfehlungen)
- **Social Media Content-Generator** (KI erstellt Posts aus Tagesangeboten)
- **Bewertungsanalyse** (KI liest Google/TripAdvisor-Reviews und fasst Trends zusammen)

### Won't Have (Jetzt bewusst ausgeschlossen):
- **Gesichtserkennung für VIP-Stammkunden** — Datenschutz (DSGVO) nicht geklärt
- **Vollautomatische Bestellung beim Lieferanten** — Data Readiness noch nicht ausreichend
- **KI-Roboter-Barista** — hoher Effort, geringer Impact für Premiumcafé-Erlebnis

---

## TEIL 8 — IMPACT-EFFORT-MATRIX FÜR AMUN CAFÉ

```
HIGH IMPACT
     │
     │  MAJOR PROJECTS          │  QUICK WINS
     │  ─────────────────────   │  ──────────────────────
     │  Personaleinsatz-KI      │  ✅ KI-Chatbot (Custom GPT)
     │  Food-Waste-System       │  ✅ Food-Waste Vorhersage
     │  (Daten-Engineering      │  (wenn Kassendaten ready)
     │   nötig)                 │
     │                          │
 ────┼──────────────────────────┼────────────────────────
     │                          │
     │  MONEY PITS              │  FILL-INS
     │  ─────────────────────   │  ──────────────────────
     │  ❌ KI-Roboter-Barista   │  Social Media Generator
     │  ❌ Gesichtserkennung    │  Bewertungsanalyse
     │                          │
LOW IMPACT
          HIGH EFFORT ◄──────────────────► LOW EFFORT
```

### Quick Wins sofort starten (Woche 1–4):
1. **Custom GPT / Chatbot** für Amun Café Website aufbauen
   - Füttere es mit: Speisekarte PDF, FAQ, Öffnungszeiten, Allergene
   - Tool: ChatGPT (Custom GPT) oder Claude API — kein Code nötig!
   - Aufwand: 2–4 Stunden | Impact: sofort 24/7 Kundenkommunikation

2. **Food Waste Dashboard** (wenn 3+ Monate Kassendaten vorhanden)
   - Kassendaten-Export als CSV → Upload in ChatGPT/Claude
   - Prompt: "Analysiere welche Produkte täglich übrig bleiben und zeige Muster"
   - Aufwand: 1 Tag Einrichtung | Impact: 20–40% weniger Verschwendung möglich

---

## TEIL 9 — ARCHITEKTUR-ENTSCHEIDUNGEN

### Cloud-KI (API) verwenden für:
- Chatbot (ChatGPT API / Claude API) — braucht Rechenleistung, kein Echtzeit-Zwang
- Nacht-Berechnungen: Morgenplanung (Wie viel backen? Wie viel Personal?)
- Social Media Content-Generierung

### Edge-KI (Lokal) verwenden für:
- Kassensystem-Integration (kein Internet-Ausfall darf Kasse stoppen)
- Echtzeit-Wartezeitenanzeige am Tresen

---

## TEIL 10 — DATENSCHUTZ & COMPLIANCE (DSGVO)

Gemäß KIUSCA Tag 02, Realitäts-Check:

- **NIEMALS** echte Kundendaten (Namen, Zahlungsdaten) in öffentliche Cloud-KIs laden
- **Kassendaten anonymisieren** bevor sie in ChatGPT/Claude hochgeladen werden
- **Geschlossene Lizenzen nutzen:** ChatGPT Enterprise oder Gemini Business (kein Datentraining)
- **Alternative:** Wenn Daten Amun nicht verlassen sollen → lokale KI (On-Premise) evaluieren

---

## TEIL 11 — FALLBACK-PROTOKOLL (Human-in-the-loop)

Für jeden KI-Use-Case gilt:

| Trigger (rote Linie) | Eskalation | Plan B (manuell) | Rückkehr zur KI |
|---|---|---|---|
| Chatbot beantwortet Frage falsch (> 5% Eskalationsrate) | Inhaber wird benachrichtigt | Mitarbeiter übernimmt Chat | FAQ-Update + KI-Retest |
| Food-Waste-Vorhersage weicht > 30% ab | Manager prüft manuell | Erfahrungswert des Teams | Daten-Audit + Neutraining |
| Kassensystem-KI fällt aus | Sofort-Alarm | Manuelle Kasse | Tech-Lead prüft + Restart |

---

## TEIL 12 — 10-TAGE UMSETZUNGSPLAN (Quick Start)

| Tag | Aktion | Verantwortlich |
|---|---|---|
| 1–2 | Kassendaten-Export (CSV, mind. 3 Monate) sicherstellen | Data Steward |
| 3–4 | Custom GPT Chatbot für Amun Café aufbauen (Speisekarte + FAQ als PDF hochladen) | Tech Lead |
| 5 | Chatbot testen, DSGVO prüfen, auf Website einbinden | Change Manager + PO |
| 6–7 | Kassendaten anonymisieren + erste Food-Waste-Analyse via KI | Tech Lead + Data Steward |
| 8 | Team-Schulung: Wie nutzen wir die KI-Tools täglich? | Change Manager |
| 9 | Erste Wochenprognose: "Was backen wir morgen?" mit KI erstellen | Domain Expert |
| 10 | Review: Ergebnisse messen, MoSCoW-Liste anpassen | Product Owner (Amun) |

---

## GLOSSAR (Alle 3 Tage zusammengefasst)

| Begriff | Bedeutung für Amun Café |
|---|---|
| **KI-Roadmap** | Strukturierter Plan zur KI-Einführung im Café |
| **Pain Point** | Z.B. tägliche Lebensmittelverschwendung, lange Wartezeiten |
| **Supervised Learning** | KI lernt aus alten Kassendaten → sagt Morgen-Bedarf voraus |
| **Generative AI** | ChatGPT-basierter Chatbot beantwortet Kundenfragen |
| **Edge-KI** | KI läuft lokal am Kassensystem, kein Internet nötig |
| **Cloud-KI** | KI läuft auf externen Servern (ChatGPT, Claude API) |
| **GIGO** | Schlechte Daten = schlechte KI-Entscheidungen |
| **Data Readiness** | Sind Kassendaten strukturiert, vollständig, zugänglich? |
| **MoSCoW** | Priorisierungsmethode: Must / Should / Could / Won't |
| **Quick Win** | Chatbot = hoher Nutzen, geringer Aufwand |
| **Money Pit** | KI-Roboter-Barista = riesiger Aufwand, wenig Mehrwert |
| **Human-in-the-loop** | Mitarbeiter übernimmt wenn KI-Fehler erkannt wird |
| **Proof of Concept (PoC)** | Erst kleinen Chatbot testen, dann skalieren |
| **Process Mining** | Kassendaten-Analyse: Wo dauert die Bestellung am längsten? |
| **Change Manager** | Person, die dem Team die Angst vor KI nimmt |

---

*Erstellt auf Basis der KIUSCA-Kursmaterialien (WBS), Tag 01–03, Jenny Grünwald*  
*Angepasst für: Amun Café | Amun-Online | service@amun-online.de*
