# AILIZA v1.0 Beta Ready — Release-Gate-Checkliste

Kein Release ohne alle Kritisch-Punkte auf ✅.

---

## Kritisch (Blocker)

| # | Kriterium | Status |
|---|---|---|
| C1 | TLS-Terminierung aktiv (kein HTTP in Produktion) | 🔲 offen |
| C2 | CORS kein Wildcard (`*`) — nur explizite Origins | 🔲 offen |
| C3 | `AILIZA_SECRET_KEY` ≥ 32 Zeichen zufällig gesetzt | ⚠️ geprüft beim Start |
| C4 | Alle Admin-Endpunkte hinter `require_role(Role.ADMIN)` oder höher | ✅ |
| C5 | Kill-Switch funktioniert (`AILIZA_EXTERNAL_LLM_ENABLED=false` blockiert alle ext. Calls) | ✅ |
| C6 | Kein LLM-Call ohne Provider-Profil mit `avv_signed=True` | ✅ |
| C7 | Audit-Vault Stufe 2 aktiv (Hash-Chain für alle neuen Einträge) | ✅ |
| C8 | Freigabe-UI für Human Oversight vorhanden (Approval-Flow) | 🔲 offen |

---

## Hoch

| # | Kriterium | Status |
|---|---|---|
| H1 | Backup-Strategie für SQLite definiert und getestet | 🔲 offen |
| H2 | Memory-Governance UI (Einsicht + Löschung für Nutzer) | 🔲 offen |
| H3 | Fehlende Audit-Events vollständig (`provider.blocked`, `capability.blocked`, etc.) | 🔲 offen |
| H4 | Incident-Response-Tabletop (simulierter Ablauf) durchgeführt | 🔲 offen |
| H5 | Rollenprüfung durch zweite Person (Vier-Augen) | 🔲 offen |

---

## Mittel

| # | Kriterium | Status |
|---|---|---|
| M1 | Alle Provider-Profile mit `admin_disabled=True` (bis AVV vorliegt) | ✅ |
| M2 | `responsibility_handoff` für Buchhaltung (UC09) und HR (UC10) dokumentiert | ✅ |
| M3 | Governance-Dokumentation vollständig (TOM, DPA, AI-Act, Incident, Review) | ✅ |
| M4 | 635+ Tests grün | ✅ |
| M5 | `VITE_DEBUG_ERRORS` auf `false` in Produktion | ✅ (`.env.example`) |

---

## Dauerhafte Sperren (immer ✅ — nie freigeben ohne Dokumentation)

| Sperre | Status |
|---|---|
| Autonome HR-Entscheidungen | 🔒 permanent blocked |
| Autonome Buchhaltungsentscheidungen | 🔒 permanent blocked |
| Automatische Vertragsfreigaben | 🔒 permanent blocked |
| Gesundheitsdaten | 🔒 permanent blocked |
| Tools ohne AVV/DPA | 🔒 permanent blocked |
| Alle Provider (Groq, Anthropic, Tavily) | 🔒 kein AVV vorliegend |

---

## Beta-Ready-Definition

AILIZA v1.0 ist Beta Ready, wenn:
> Kein externer Zugriff ohne Provider-Profil, Policy, Freigabeprüfung und Audit möglich ist.

Aktueller Stand: **6 von 8 Kritisch-Kriterien erfüllt** (C1, C2, C8 offen).
