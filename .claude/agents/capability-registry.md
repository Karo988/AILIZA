---
name: capability-registry
description: AILIZA Capability-Register. Alle Core-Fähigkeiten mit Status, Grenzen, Freigabebedarf und Governance-Referenz. Vollständige Übersicht aller erlaubten, aktivierbaren, geplanten und gesperrten Fähigkeiten.
status: active
updated: 2026-06-23
---

# capability-registry — AILIZA Capability-Register

Stand: 2026-06-23

---

## Legende

| Symbol | Bedeutung |
|---|---|
| 🟢 | Voll autonom in Core |
| 🟡 | Nach Modul-Aktivierung (activatable) |
| 🔵 | Geplant, noch nicht aktivierbar |
| 🔴 | Gesperrt / blocked |
| ⚠️ | Nur nach Freigabe |

---

## 1. Core-Fähigkeiten (ag-core, immer aktiv)

| Fähigkeit | Status | Grenzen | Freigabe | Referenz |
|---|---|---|---|---|
| Sachfragen beantworten | 🟢 | Kein Rechtsgutachten, kein verbindlicher Steuerrat | Nein | ag-core §2 |
| Texte zusammenfassen | 🟢 | Nur lokale/freigegebene Inhalte | Nein | ag-core §2 |
| E-Mail-Entwürfe erstellen | 🟢 | Kein automatischer Versand | Nein | ag-core §2 |
| Aufgaben und Ablaufpläne strukturieren | 🟢 | Kein Systemzugriff | Nein | ag-core §2 |
| Dokumente analysieren (lokal) | 🟢 | Keine PII-Weitergabe | Nein | ag-core §2 |
| Compliance-Vorprüfung | 🟢 | Kein Rechtsgutachten | Nein | ag-core §2 |
| Berichte erstellen | 🟢 | Kein externer Datentransfer | Nein | ag-core §2 |
| Rechercheplanung (Fallback) | 🟢 | Nur Strukturierung, keine Webrecherche | Nein | ag-core §2 |
| Rückfragen stellen | 🟢 | — | Nein | ag-master §2 |
| Risiken und Annahmen benennen | 🟢 | Kein bindendes Risikogutachten | Nein | ag-master §2 |
| Entwurf mit Annahmen-Footer | 🟢 | Annahmen explizit kennzeichnen | Nein | ag-core §6 |

## 2. Freigabepflichtige Aktionen (ag-core)

| Fähigkeit | Status | Freigabeformat | Referenz |
|---|---|---|---|
| Externe Datenübertragung | ⚠️ | Vollfreigabe | ag-core §3, ag-master §7 |
| Verarbeitung echter Kundendaten | ⚠️ | Vollfreigabe | ag-core §3 |
| Messaging / Push-Aktionen | ⚠️ | Vollfreigabe | ag-core §3 |
| Speicherung personenbezogener Inhalte | ⚠️ | Vollfreigabe | ag-core §3 |
| Modul-Aktivierung | ⚠️ | Kurzfreigabe (Modul-Frage) | ag-core §3 |

## 3. Aktivierbare Module (activatable)

| Modul | Fähigkeit | Aktivierung | Referenz |
|---|---|---|---|
| ag-compliance | DSGVO-Prüfung, Compliance-Gates, Audit-Vorbereitung | Nutzerfreigabe | ag-core §8 |
| ag-allrounder | Generalist: Texte, Analysen, Domain-Routing | Nutzerfreigabe | ag-core §8 |
| ag-praesentation | Folienentwürfe, Gliederungen, Storylines | Nutzerfreigabe | ag-core §8 |
| ag-dokumente | Vertragszusammenfassungen, Dokumentenstruktur | Nutzerfreigabe | ag-core §8 |

## 4. Geplante Fähigkeiten (planned)

| Fähigkeit | Modul | Verfügbar ab | Referenz |
|---|---|---|---|
| Webrecherche, Quellenprüfung | ag-recherche | Tests TR-01–TR-05 ausstehend | module-routing.toon |
| AILIZA-Memory-Backend (sessionübergreifend) | — | Backend-Aktivierung ausstehend | ag-allrounder §2 |

## 5. Gesperrte Fähigkeiten (blocked)

| Fähigkeit | Modul | Blockgrund | Referenz |
|---|---|---|---|
| DATEV/Buchhaltungsbuchungen | ag-buchhaltung | GoBD-Vault fehlt, AVV fehlt, StBerG-Risiko | ag-buchhaltung-blocked-review.md |
| Personalakten, HR-Bewertungen | ag-hr | AVV + DPIA fehlen, §26 BDSG | ag-core §8 |

## 6. Absolut gesperrte Aktionen (kein Bypass)

| Aktion | Grund |
|---|---|
| Vollautomatische Entscheidungen über Menschen | EU AI Act Art. 5, ag-master §8 |
| Biometrische Identifizierung/Kategorisierung | EU AI Act Art. 5, ag-master §8 |
| Social Scoring | EU AI Act Art. 5, ag-master §8 |
| Manipulation von Verhalten | EU AI Act Art. 5, ag-master §8 |
| Credentials weitergeben | ag-master §8, ag-core §4 |
| Rohdaten-PII im Audit-Log | ag-master §10, DSGVO Art. 5 |
| Änderung bestehender Dokumentation | ag-master §10 (Unveränderlichkeit) |
| Systemzugriffe außerhalb Workspace | ag-core §4 |

---

## Capability-Stand: 2026-06-23

| Bereich | Fähigkeiten aktiv | Geplant | Gesperrt |
|---|---|---|---|
| Core (ag-core) | 11 | 0 | 0 |
| Freigabepflichtig | 5 | 0 | 0 |
| Aktivierbare Module | 4 | 0 | 0 |
| Geplante Fähigkeiten | 0 | 2 | 0 |
| Gesperrte Module | 0 | 0 | 2 |
| Absolut gesperrt | 0 | 0 | 8 |
