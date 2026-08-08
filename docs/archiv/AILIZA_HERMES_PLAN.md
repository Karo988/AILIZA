# AILIZA Hermes Plan

Stand: 2026-06-08

## Kurz gesagt

AILIZA Phase 1 ist bereit zum Weiterbauen.

Das System hat jetzt:
- Policy Gateway
- Approval Workflow
- Audit Log
- Agent Runtime
- Streaming per SSE
- Async Approval
- gespeicherte Agent Runs

Prinzip: leicht, klar, schnell.

## Info-Update

Wichtige Projektentscheidung:

```text
AILIZA ist das Hauptprojekt.
Hermes ist nur Vorbild.
AILIZA wird kein Fork des originalen Hermes Agenten.
```

Ziel:
- einen neuen EU-konformen Agenten bauen
- inspiriert von Hermes
- von Anfang an mit DSGVO
- von Anfang an mit EU AI Act
- mit Human Oversight
- mit Audit Trail
- mit Policy Gateway
- mit Approval Workflow

Sprache:
- Frontend: Englisch
- Zusammenarbeit und Erklaerungen: Deutsch

Namensklaerung:
- `AILIZA` ist der Projektname
- der aktuelle Arbeitsordner ist der lokale AILIZA-Workspace
- `hermes-agent` ist Referenz und Inspirationsquelle

Wichtig:

```text
Nicht kopieren.
Nicht forken.
Verstehen, neu bauen, EU-konform machen.
```

## Was fertig ist

### 1. Sicherheit

Jeder Tool-Aufruf laeuft durch:

```text
Agent -> Policy -> Approval -> Tool -> Audit
```

Blockiert wird:
- localhost
- private IPs
- interne Domains
- sensible Suchanfragen
- unbekannte oder riskante Tool-Aufrufe ohne Freigabe

### 2. Approval

Riskante Aufrufe werden nicht sofort ausgefuehrt.

Sie landen als Approval Request im Status:

```text
pending
```

Nach Freigabe:

```text
approved -> Tool wird ausgefuehrt
```

Nach Ablehnung:

```text
rejected -> Agent stoppt sauber
```

### 3. Agent Runtime

Der Agent kann Aufgaben annehmen und daraus Tool-Aufrufe planen.

Beispiel:

```text
Read https://example.com
```

wird zu:

```text
fetch(url)
```

Ohne URL wird daraus:

```text
search(query)
```

### 4. Streaming

Der Agent kann live Ereignisse senden:

```text
run_started
tool_planned
tool_started
approval_required
approval_waiting
approval_granted
tool_completed
run_completed
```

Der Browser muss nicht warten, bis alles fertig ist.

### 5. Async Approval

Der Stream kann offen bleiben, waehrend du entscheidest.

Wenn du freigibst, laeuft der Agent automatisch weiter.

Wenn du ablehnst, stoppt der Agent sauber.

## Wichtige Endpunkte

```text
POST /agent/run
GET  /agent/runs
GET  /agent/runs/{run_id}
GET  /agent/run/stream?task=...&wait_for_approval=true
POST /agent/run/stream?wait_for_approval=true
POST /approvals/{approval_id}/approve
POST /approvals/{approval_id}/reject
```

## Wann kannst du weiter?

Jetzt.

Der naechste sinnvolle Schritt ist:

```text
React Dashboard
```

Ziel:
- laufende Agent Runs anzeigen
- Stream live anzeigen
- Approval Buttons direkt im UI
- klare Statusfarben
- keine komplizierte Bedienung

## Hermes-Regel

Alles bleibt:
- leicht
- schnell
- lesbar
- sicher
- ohne unnoetigen Umbau

Erst sichtbar machen.
Dann schoener machen.
Dann skalieren.

## Naechster Klick

Baue als Naechstes:

```text
Frontend Dashboard fuer Agent Runs + Live Stream + Approval
```

Danach:

```text
Docker + VPS
```
