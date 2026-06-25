# AMUN CAFÉ — GÄSTEBETREUUNG
## Phase 3: Service-Standards, KI-Chatbot, Bewertungen, Stammkunden
**Stand: Juni 2026 | Doberaner Platz, Rostock**

---

## LEITPRINZIP: ORIENTALISCHE GASTFREUNDSCHAFT, MODERN UMGESETZT

Im Orient ist der Gast heilig. Nicht als Floskelbegriff, sondern als echte Haltung:
Der Gast wird gesehen, willkommen geheißen und gut behandelt — unabhängig davon,
ob er einen Espresso oder ein 3-Gang-Menü bestellt.

Das Amun Café trägt diesen Gedanken in einen modernen, schnellen Betrieb.

**Drei Prinzipien:**
1. **Erkennen** — Der Stammgast wird erkannt und begrüßt, bevor er bestellt.
2. **Beraten** — Wer unsicher ist, bekommt echte Empfehlungen, kein Upselling-Geschwätz.
3. **Lösen** — Wenn etwas nicht stimmt, wird es sofort und ohne Diskussion gelöst.

---

## 1. SERVICE-STANDARDS IM CAFÉ

### Begrüßung:
- Augenkontakt und Lächeln sobald der Gast eintritt — auch wenn man gerade beschäftigt ist
- *"Hallo, herzlich willkommen! Ich bin gleich bei Ihnen."* ist besser als Ignorieren
- Stammkunden: Name kennen, Lieblingsbestellung kennen

### Bestellaufnahme:
- Aktiv fragen wenn der Gast zögert: *"Darf ich etwas empfehlen?"*
- Bei Allergie-Fragen: Unverbindlicher Hinweis + **immer** ergänzen: *"Für eine verbindliche Auskunft schaue ich kurz in unsere Zutatenliste."*
- Niemals raten bei Allergenen — lieber nachschlagen und sicher sein

### Wartezeit kommunizieren:
- Sandwich < 3 Min. → *"Ihr Sandwich ist in ca. 2 Minuten fertig."*
- Kaffee < 90 Sek. → kein Kommentar nötig
- Länger als erwartet? → Gast proaktiv informieren, nicht warten lassen ohne Bescheid

### Übergabe:
- Produkt mit kurzem Hinweis übergeben: *"Das ist Ihr Fleisch-Sandwich — mit Harissa-Mayo, scharf aber nicht zu scharf. Guten Appetit!"*
- Bei To-go: *"Alles dabei? Serviette? Ich wünsche einen schönen Tag!"*

### Verabschiedung:
- Jeder Gast wird verabschiedet — auch wenn er nur kurz an der Theke stand
- *"Tschüss, bis bald!"* ist Programm — nicht Pflicht, sondern Haltung

---

## 2. BESCHWERDEMANAGEMENT

### Grundsatz: Das ASAP-Modell

```
A — Anhören      Ausreden lassen. Nicht unterbrechen. Nicht verteidigen.
S — Sorry        Entschuldigen. Auch wenn wir Recht haben. Der Gast hat sein Erlebnis.
A — Abhilfe      Sofort lösen. Neues Produkt, Gutschein, Rückerstattung — egal was es kostet.
P — Protokoll    Nach dem Gespräch kurz notieren was passiert ist → Muster erkennen
```

### Beispiel-Situationen:

| Problem | Falsche Reaktion | Richtige Reaktion |
|---|---|---|
| Kaffee ist kalt | *"Der war doch heiß als ich ihn gemacht habe."* | *"Das tut mir leid — ich mache Ihnen sofort einen neuen."* |
| Sandwich falsch belegt | *"Sie haben aber nicht gesagt ohne..."* | *"Entschuldigung — ich mache das sofort neu."* |
| Zu lange Wartezeit | *"Wir sind heute sehr voll."* | *"Ich weiß, es hat zu lange gedauert. Das Sandwich geht auf uns."* |
| Falsches Produkt | Diskussion | Wechseln + ein kleines Extra als Geste |

**Regel:** Kein Gast verlässt unzufrieden das Café ohne dass wir etwas getan haben. Eine Geste (Kaffee kostenlos, kleines Stück Kuchen) kostet 80 Cent und erhält einen Stammkunden.

### Beschwerden online (Google/Instagram):
- Jede negative Bewertung wird beantwortet — innerhalb von 24 Stunden
- Niemals defensiv oder aggressiv
- Schema: *"Danke für Ihr Feedback. Es tut uns leid, dass [Problem]. Wir würden uns freuen, Sie noch einmal bei uns begrüßen zu dürfen."*

---

## 3. STAMMKUNDEN-KULTUR

**Philosophie:** Keine Stempelkarte. Stattdessen: Echter Kontakt.

### Was Stammkunden brauchen:

| Bedürfnis | Was wir tun |
|---|---|
| Wiedererkannt werden | Name merken, Lieblingsgetränk merken |
| Vertrauen | Gleiche Qualität jeden Tag |
| Kleine Überraschungen | Gelegentlich ein Extra-Stück Kuchen, ein Probierhäppchen |
| Gehört werden | Feedback aktiv einholen und umsetzen |

### Praktische Umsetzung:
- **Notizbuch an der Kasse** (digital oder analog): Stammgäste mit Vorlieben notieren
- **Saisonale Ankündigungen** per Instagram: *"Ab morgen gibt es Zuckerrohr-Saft!"* — Stammkunden kommen extra deswegen
- **Tages-Specials kommunizieren:** *"Heute haben wir zum ersten Mal den Rosenwasser-Cheesecake — möchten Sie probieren?"*

---

## 4. KI-CHATBOT — GÄSTEBETREUUNG DIGITAL

Der AMUN KI-Gästeberater läuft auf Website und optional WhatsApp.
Basis: `amun-ki-berater/` (StarterKit bereits im Repository)

### Was der Chatbot macht:
- Produktempfehlungen (Café + Store) basierend auf Stimmung, Anlass, Budget
- Allergen-Hinweise (immer mit HITL-Verweis ans Team)
- Öffnungszeiten, Standort, Kontakt beantworten
- Auf Deutsch (und auf Englisch, falls eingestellt)

### Was der Chatbot NICHT macht:
- Reservierungen (kein PII-Handling)
- Verbindliche Allergen-Zusagen
- Preisverhandlungen oder Rabatte gewähren
- Themen außerhalb von AMUN beantworten

### Eskalationsweg (wenn Chatbot nicht weiterweiß):
```
Chatbot erkennt Unsicherheit
        ↓
"Dazu hilft Ihnen unser Team am besten weiter."
        ↓
Verweis auf: WhatsApp +49... | service@amun-online.de | Vor Ort
        ↓
Mensch beantwortet innerhalb von 2 Stunden (Mo–Fr)
```

### Chatbot-KPIs (monatlich prüfen):
| KPI | Ziel |
|---|---|
| Beratungs-Completion-Rate | ≥ 70% |
| Allergen-HITL-Weiterleitung | 100% (kein einziges Mal vergessen!) |
| Fallback-Rate (Bot weiß es nicht) | ≤ 15% |
| Antwortzeit auf Eskalations-Anfragen | ≤ 2 Stunden |

---

## 5. ONLINE-REPUTATION

### Google Business (wichtigster Kanal):

**Sofortmaßnahmen nach Eröffnung:**
- Fotos hochladen: Innenraum, Produkte, Team (kein Handy-Schnappschuss — gutes Licht!)
- Beschreibung: *"Modernes orientalisches Café in Rostock — Sandwiches, Specialty Coffee, hausgemachte Limonaden und frisch gepresster Zuckerrohr-Saft."*
- Öffnungszeiten korrekt + regelmäßig aktualisieren (Feiertage!)
- Google-Posts nutzen: Wochenspecial, neue Produkte, Events

**Bewertungs-Strategie:**
- Zufriedene Stammkunden freundlich bitten: *"Wenn Sie mögen, freuen wir uns über eine kurze Google-Bewertung."*
- QR-Code am Kassenbereich der direkt zur Google-Bewertung führt
- Ziel: 4,5+ Sterne, mind. 50 Bewertungen im ersten Jahr

### Instagram (@amun.cafe.rostock):

**Content-Plan (Minimalstandard):**

| Format | Frequenz | Inhalt |
|---|---|---|
| Stories | Täglich | Hinter-den-Kulissen, Tagesspecial, Zuckerrohrpresse live |
| Feed-Post | 3x/Woche | Produkt-Fotos, Café-Atmosphäre, Rezept-Hinweis |
| Reels | 1x/Woche | Zubereitung, Coffee Art, Workflow (Sandwiches in 3 Min.) |

**Content-Ideen:**
- *"Mise-en-place Montag"* — Wochenvorbereitung zeigen
- *"Frage der Woche"* — Gäste abstimmen lassen (z.B. Welcher neue Kuchen soll kommen?)
- *"Behind the Cup"* — Kaffeezubereitung in 30 Sekunden
- *"Zuckerrohr Live"* — Gast-Reaktionen beim ersten Mal

**Regel:** Lieber 3 gute Posts pro Woche als 7 schlechte.

### WhatsApp Business:

**Einrichten:**
- Geschäftsprofil mit Öffnungszeiten, Adresse, Kurzinfo
- Automatische Antwort außerhalb der Öffnungszeiten:
  *"Hallo! Wir sind gerade nicht da. Öffnungszeiten: Mo–Fr 07–18h, Sa 09–17h. Wir melden uns spätestens am nächsten Werktag. Bis dahin hilft euch unser Chatbot: [Link]"*
- Anfragen innerhalb von 2 Stunden beantworten (Mo–Fr)

---

## 6. EVENTS & BESONDERE ANLÄSSE

### Wiederkehrende Formate (Ideen zum Ausprobieren):

| Format | Wann | Was |
|---|---|---|
| **Frühstücks-Special** | Sa/So 09–11h | Erweitertes Frühstücksangebot für 1–2h extra |
| **Coffee Tasting** | 1x/Monat | 45 Min., 5 Kaffeesorten, erklärt vom Barista |
| **Orientalischer Abend** | Saisonal | Spezielle Speisen, Musik, Duft-Atmosphäre |
| **Pop-Up Kooperation** | Nach Bedarf | Lokale Künstler, Buchverkauf, Schmuck-Ausstellung |

### Planung eines Events:
1. Idee → 4 Wochen vorher auf Instagram ankündigen
2. Kapazität festlegen (max. Sitzplätze = max. Anmeldungen)
3. Mise-en-place anpassen (mehr Kuchen, besondere Getränke)
4. Fotos/Stories während des Events
5. Feedback-Runde danach: Was hat gut funktioniert?

---

## 7. BARRIEREFREIHEIT & INKLUSION

| Thema | Standard |
|---|---|
| Rollstuhl-Zugänglichkeit | Eingang und Thekenbereich zugänglich? Prüfen und kommunizieren |
| Allergene | Immer transparent, immer HITL — kein Gast wird ausgeschlossen |
| Sprache | Karte und Chatbot auf Deutsch + Englisch |
| Preise | Sichtbar ausgehängt (Pflicht laut Preisangabenverordnung) |

---

## 8. BESCHWERDEPROTOKOLL (Vorlage)

```
DATUM: ___________    UHRZEIT: ___________

Beschreibung des Problems:
__________________________________________________

Wie hat der Gast reagiert?
__________________________________________________

Was wurde als Lösung angeboten?
__________________________________________________

Hat der Gast angenommen?    ☐ Ja    ☐ Nein

Maßnahme zur Vermeidung in Zukunft:
__________________________________________________

Unterschrift Dienst-Person: ___________
```

→ Protokolle monatlich auswerten: Gibt es Muster? Immer dieselbe Beschwerde → systematisch lösen.

---

## 9. SONDERFALL: SCHWIERIGER GAST

Manchmal kommen Gäste, die grundlos unfreundlich oder fordernd sind.

**Protokoll:**
1. Ruhig bleiben. Nicht eskalieren.
2. Sachlich reagieren: *"Ich verstehe Ihren Unmut. Was kann ich konkret für Sie tun?"*
3. Wenn der Gast respektlos bleibt: *"Ich helfe Ihnen gern, aber ich bitte Sie, unsere Mitarbeiter freundlich zu behandeln."*
4. Im Extremfall: Hausrecht wahrnehmen, ruhig und klar.

**Wichtig:** Personal schützen ist genauso wichtig wie Gäste schützen. Kein Mitarbeiter muss Beleidigungen hinnehmen.

---

*Teil des Amun Café Betriebssystems | Stand: Juni 2026*
*← `docs/AMUN_CAFE_BETRIEBSHANDBUCH.md` | Masterplan: `docs/AMUN_CAFE_MASTERPLAN.md`*
*service@amun-online.de*
