# AILIZA – Bausteine-Board und sicherer Modellkern

Stand: 22.08.2026

## Verbindlicher Ablauf

1. Der Modellradar legt ausschließlich einen **Kandidaten** mit offizieller Evidenz an.
2. Der erste Benchmark verwendet synthetische oder ausdrücklich freigegebene Testdaten.
3. Der Bewertungslauf besitzt eine eigene `evaluation_run_id`; sein Ergebnisartefakt eine eigene `artifact_checksum`.
4. Der Kandidat wird über `candidate_object_hash` gebunden. Anbieterbedingungen werden separat durch `provider_profile_version` und `provider_profile_hash` gebunden.
5. Eigene Geschäftsdaten dürfen erst nach einer befristeten Probefreigabe verarbeitet werden. Umfang, Datenklassen, Zweck, Kosten und Ablaufdatum sind Teil dieser Freigabe.
6. Eine Vollfreigabe gilt nur für ein benanntes Aufgabenpaket. `approved` ist ausdrücklich nicht `active`.
7. Vor der Aktivierung werden Kandidat, Anbieterprofil und vollständiger `approval_basis_hash` erneut geprüft.
8. Der produktive Router berücksichtigt ausschließlich aktive, nicht abgelaufene und unveränderte Freigaben.
9. Vor einem kostenpflichtigen Provideraufruf wird Budget reserviert. Ohne Budgetregel oder bei erreichtem Maximum findet kein Aufruf statt.
10. Beim Abschalten bleiben Grund, betroffener Ablauf und Rückfallkandidat nachvollziehbar erhalten. Eine spätere Aktivierung ist möglich; nur eine aktive Belegung je Aufgabenpaket ist zulässig.

## Bedienmodell

Das Board besitzt genau drei Reiter: **Empfohlen**, **Aktiv** und **Nicht einsetzbar**. Offene Entscheidungen gehören weiterhin in das Entscheidungs-Postfach. Die Ampel bewertet ausschließlich die Zulässigkeit im aktuell gewählten Daten- und Aufgaben-Kontext. Qualität, Geschwindigkeit und Kosten dürfen die Farbe nicht verbessern.

Beschäftigte sehen nur aktive, für ihre Arbeit relevante Einträge. Anbieter-, Vertrags-, Budget- und Freigabeentscheidungen bleiben der berechtigten Administration vorbehalten. Programme behalten einen getrennten Verbindungs- und Rechteweg; das hier implementierte Radar nimmt nur KI-Modelle auf.

## Solo-Unternehmen

Die Inhaberin verwendet die vorhandene Rolle `ADMIN`. `solo_compensated` ist nur möglich bei ausdrücklich konfiguriertem Einpersonenbetrieb, genau einem aktiven ADMIN, bestätigtem TOTP, ausführlicher Begründung, benanntem Aufgabenpaket, positivem Kostenlimit, höchstens 90 Tagen Gültigkeit, abgeschlossenem Benchmark und `privacy_score >= 0.8`. Externe Vollfreigaben besitzen zusätzlich 24 Stunden Abkühlfrist.

## Sichere Grenzen

- Unbekannte Datenklassen, Anbieter, Zustände und Memory-Scopes werden abgewiesen.
- `session` und `personal` werden auf den nutzergebundenen Speicher geroutet; `project` und `company` auf den Unternehmensspeicher. Fehlende Nutzer- oder Projektbindungen blockieren die Speicherung.
- Geschützte lokale Pfade können nicht als autonomer Workspace konfiguriert werden.
- Der Radar genehmigt oder aktiviert niemals selbstständig.
- Connector Hub, automatische Programmintegration und selbstständiges Aufräumen bleiben eigenständige, spätere HANDOFF-Pakete.

## Betrieb vor Produktion

Die lokale Umsetzung ersetzt keine Betreiberunterlagen. Vor einem echten externen Modell müssen der konkrete AVV/DPA-Status, Transferprüfung, Region, Endpunkt, Lösch-/Logging-Regeln und belastbare Preise im versionierten Anbieterprofil dokumentiert werden. Erst danach darf die Freigabekette für diesen Anbieter durchlaufen werden.
