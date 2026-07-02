# AILIZA Governance- und Dokumentationslogik

AILIZA bearbeitet grundsätzlich jede Anfrage.

Nicht-unproblematische Fälle werden dokumentiert. Dazu gehören insbesondere sensible Daten, Hochrisiko-Fälle, Freigabefälle, externe KI-/Websuche-Nutzung und entscheidungsrelevante Anfragen.

Hochrisiko- und Freigabefälle werden nicht blockiert, sondern als Entwurf, Entscheidungsgrundlage oder Handlungsvorschlag vorbereitet. Menschliche Freigabe wird markiert. Die Bearbeitung und die Freigabeanforderung werden dokumentiert.

Sensible Daten werden lokal temporär maskiert. Externe KI- oder Websuchanbieter erhalten nur bereinigte Inhalte. Nach der Antwort werden die sensiblen Daten lokal wieder eingesetzt.

Dokumentiert werden mindestens:
- Zeitpunkt
- Anfrage-ID
- Risikostufe
- erkannte Datenklassen
- Maskierung ja/nein
- verwendeter Anbieter: Groq, OpenAI, Tavily oder lokal
- Modellname
- Websuche ja/nein
- Grund der Providerwahl
- Freigabe erforderlich ja/nein
- Ergebnisstatus

Blockiert wird nur bei eindeutig rechtswidrigen, missbräuchlichen oder technisch gefährlichen Anweisungen.

---

## Umsetzungsstand

| Regel | Status |
|-------|--------|
| BLOCKED nur bei Rechtsverstößen | ✅ umgesetzt (`classifier.py`) |
| HIGH als Entwurf vorbereiten | ✅ umgesetzt (`agent_runtime._precheck`) |
| PII lokal maskieren vor LLM-Call | ✅ umgesetzt (`redactor.py`) |
| Audit-Log pro Anfrage | ✅ umgesetzt (`write_audit_entry`) |
| Erweitertes Audit-Log (Anbieter, Modell, Websuche) | ✅ umgesetzt (`agent_runtime.run`) |
| PII nach Antwort lokal wieder einsetzen | ✅ umgesetzt (`governance/redaction.reinsert`, `main.run_agent`) |
| `_governance_pre_check` als zentraler Einstiegspunkt | ✅ umgesetzt (`main._governance_pre_check`) |
