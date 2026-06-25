import { useState } from "react"

const STEPS = [
  {
    id: "groq_key",
    title: "Alter API-Schlüssel gelöscht",
    responsible: "Betreiber / Admin",
    effort: "ca. 2 Minuten",
    risk: "Hoch",
    question: "Bist du bereit für Schritt 1 — den alten Groq-Key zu löschen?",
    warning: "Solange der alte Key aktiv ist, kann er missbraucht werden. Lösche ihn zuerst, bevor du einen neuen Key setzt.",
    explanation:
      "Ein alter Schlüssel, der versehentlich sichtbar war, muss ungültig gemacht werden. Sonst könnte ihn jemand unberechtigt nutzen.",
    confirmLabel: "Ich habe den alten Key gelöscht",
    helpLabel: "Zeig mir, wo ich das finde",
    nextHint: "Möchtest du jetzt den neuen Groq-Key in Render setzen?",
    nextHintWhy: "Der alte Schlüssel ist ungültig. Jetzt braucht AILIZA einen neuen sicheren Schlüssel, der nur in Render gespeichert wird.",
    help: [
      "Öffne groq.com und melde dich an.",
      'Gehe zu "API Keys".',
      "Klicke auf den alten Schlüssel und wähle „Löschen" oder „Revoke".",
      "Erstelle danach einen neuen Schlüssel.",
    ],
  },
  {
    id: "groq_key_new",
    title: "Neuer API-Schlüssel eingetragen",
    responsible: "Betreiber / Admin",
    effort: "ca. 3 Minuten",
    risk: "Hoch",
    question: "Hast du den neuen Groq-Schlüssel in Render eingetragen?",
    warning: "Ohne gültigen Key funktioniert die KI-Anbindung nicht.",
    explanation:
      "Der neue Schlüssel darf nur als geheime Umgebungsvariable in Render stehen — nie im Code.",
    confirmLabel: "Ja, neuer Key ist eingetragen",
    helpLabel: "Zeig mir, wie das geht",
    nextHint: "Möchtest du jetzt die sichere HTTPS-Verbindung aktivieren?",
    nextHintWhy: "Damit niemand die Verbindung zwischen Browser und App abhören kann.",
    help: [
      'Öffne dein Render-Dashboard und wähle dein Backend-Service.',
      'Gehe zu "Environment" → "Environment Variables".',
      'Trage ein: Name = GROQ_API_KEY, Wert = dein neuer Schlüssel.',
      "Speichern. Render startet die App automatisch neu.",
    ],
  },
  {
    id: "https",
    title: "Sichere Verbindung aktiviert",
    responsible: "Betreiber / Admin",
    effort: "ca. 2 Minuten",
    risk: "Mittel",
    question: "Hast du in Render die sichere HTTPS-Verbindung als Pflicht gesetzt?",
    warning: "Ohne HTTPS können Daten zwischen Browser und App abgehört werden.",
    explanation:
      "Damit wird sichergestellt, dass niemand die Verbindung zwischen Browser und App abhören kann.",
    confirmLabel: "Ja, HTTPS ist aktiviert",
    helpLabel: "Zeig mir, wie das geht",
    nextHint: "Möchtest du jetzt die erlaubte Frontend-Adresse eintragen?",
    nextHintWhy: "Ohne diese Einschränkung kann jede fremde Seite mit dem Backend sprechen.",
    help: [
      'Öffne dein Render-Backend-Service und gehe zu "Environment Variables".',
      "Trage ein: Name = AILIZA_FORCE_HTTPS, Wert = true",
      "Das bedeutet: Die App lässt nur noch sichere Verbindungen zu.",
    ],
  },
  {
    id: "cors",
    title: "Erlaubte Adresse eingetragen",
    responsible: "Betreiber / Admin",
    effort: "ca. 2 Minuten",
    risk: "Mittel",
    question: "Hast du die Adresse deines Frontends in Render eingetragen?",
    warning: "Ohne diese Einschränkung kann jede fremde Seite mit deinem Backend sprechen.",
    explanation:
      "Nur deine echte App-Adresse darf mit dem Backend kommunizieren — fremde Seiten werden blockiert.",
    confirmLabel: "Ja, Adresse ist eingetragen",
    helpLabel: "Zeig mir, wie das geht",
    nextHint: "Möchtest du jetzt die Zugriffsschlüssel für Operatoren und Admins setzen?",
    nextHintWhy: "Ohne Zugriffsschlüssel hat jeder Zugriff auf die Freigaben-Seite.",
    help: [
      'Gehe in Render zu "Environment Variables" deines Backends.',
      "Trage ein: Name = AILIZA_CORS_ORIGINS, Wert = https://deine-app.onrender.com",
      "Ersetze 'deine-app' durch den echten Namen deines Frontend-Services.",
    ],
  },
  {
    id: "keys",
    title: "Zugriffsschlüssel gesetzt",
    responsible: "Admin / Datenschutzverantwortliche",
    effort: "ca. 5 Minuten",
    risk: "Hoch",
    question: "Hast du die Zugriffsschlüssel für Operatoren und Admins in Render eingetragen?",
    warning: "Ohne diese Schlüssel hat jeder Zugriff auf die Freigaben-Seite.",
    explanation:
      "Operatoren dürfen Freigaben sehen. Admins dürfen Freigaben erteilen oder ablehnen. Beide brauchen einen eigenen sicheren Schlüssel.",
    confirmLabel: "Ja, Schlüssel sind gesetzt",
    helpLabel: "Zeig mir, wie das geht",
    nextHint: "Möchtest du jetzt die App kurz testen, bevor sie live geht?",
    nextHintWhy: "Ein kurzer Test stellt sicher, dass Freigaben und Datenschutz wirklich greifen.",
    help: [
      'Gehe in Render zu "Environment Variables" deines Backends.',
      "Trage ein: Name = AILIZA_OPERATOR_KEY, Wert = ein langes zufälliges Passwort",
      "Trage ein: Name = AILIZA_ADMIN_KEY, Wert = ein anderes langes zufälliges Passwort",
      "Tipp: Nutze einen Passwort-Generator für beide Werte.",
    ],
  },
  {
    id: "smoke",
    title: "Smoke Tests bestanden",
    responsible: "Betreiber / Datenschutzverantwortliche",
    effort: "ca. 10 Minuten",
    risk: "Mittel",
    question: "Hast du die App nach dem Deploy kurz getestet?",
    warning: "Ohne Test weißt du nicht, ob Freigaben und Datenschutz wirklich greifen.",
    explanation:
      "Ein kurzer Schnelltest stellt sicher, dass alles wie erwartet funktioniert.",
    confirmLabel: "Ja, Tests bestanden",
    helpLabel: "Was soll ich testen?",
    nextHint: null,
    nextHintWhy: null,
    help: [
      "Öffne die App im Browser und stelle eine normale Frage → Antwort kommt direkt.",
      "Stelle eine Frage mit einer E-Mail-Adresse → Die App antwortet, aber die E-Mail taucht nicht in Logs auf.",
      "Stelle eine Frage zur Kündigung eines Mitarbeiters → App stoppt und fragt nach Freigabe.",
      "Öffne die Freigaben-Seite und melde dich mit dem Admin-Schlüssel an → Freigabe sichtbar.",
      "Erteile oder lehne die Freigabe ab → Audit-Eintrag erscheint.",
    ],
  },
]

const STATUS_COLORS = {
  done: "#4ade80",
  open: "#fbbf24",
  blocked: "#f87171",
}

export default function PreStagingPage() {
  const [completed, setCompleted] = useState({})
  const [showHelp, setShowHelp] = useState({})
  const [currentStep, setCurrentStep] = useState(0)

  function markDone(id) {
    setCompleted((prev) => ({ ...prev, [id]: true }))
    if (currentStep < STEPS.length - 1) setCurrentStep((s) => s + 1)
  }

  function toggleHelp(id) {
    setShowHelp((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  const doneCount = Object.values(completed).filter(Boolean).length
  const allDone = doneCount === STEPS.length

  function statusColor() {
    if (allDone) return STATUS_COLORS.done
    if (doneCount === 0) return STATUS_COLORS.blocked
    return STATUS_COLORS.open
  }

  function statusText() {
    if (allDone) return "Bereit für Staging"
    if (doneCount === 0) return "Noch nicht gestartet"
    return `${doneCount} von ${STEPS.length} Schritten erledigt`
  }

  return (
    <section className="panel">
      <div className="page-header">
        <p className="eyebrow">Deployment</p>
        <h1>Bereit für die Veröffentlichung?</h1>
        <p className="subtitle">
          Diese Checkliste führt dich durch alle Schritte bevor AILIZA live geht.
          Du musst keine technischen Begriffe kennen — alles wird erklärt.
        </p>
      </div>

      <div className="staging-status" style={{ borderColor: statusColor() }}>
        <span className="staging-dot" style={{ background: statusColor() }} />
        <strong>{statusText()}</strong>
      </div>

      <div className="staging-steps">
        {STEPS.map((step, index) => {
          const done = !!completed[step.id]
          const active = index === currentStep && !done
          const justDone = done && index === currentStep - 1
          const nextStep = STEPS[index + 1]
          return (
            <div
              key={step.id}
              className={`staging-card ${done ? "staging-done" : ""} ${active ? "staging-active" : ""}`}
            >
              <div className="staging-card-header">
                <span className="staging-number">
                  {done ? "✓" : index + 1}
                </span>
                <strong>{step.title}</strong>
              </div>

              {(active || done) && (
                <>
                  <div className="staging-meta">
                    <span className="staging-responsible">Zuständig: {step.responsible}</span>
                    <span className="staging-effort">⏱ {step.effort}</span>
                    <span className={`staging-risk ${step.risk === "Hoch" ? "risk-high-badge" : "risk-medium-badge"}`}>
                      Risiko, wenn offen: {step.risk}
                    </span>
                  </div>

                  <p className="staging-label">Warum ist das wichtig?</p>
                  <p className="staging-explanation">{step.explanation}</p>

                  <p className="staging-label">Ist das erledigt?</p>
                  <p className="staging-question">{step.question}</p>
                  {step.warning && !done && (
                    <p className="staging-warning"><strong>Sicherheitswarnung:</strong> {step.warning}</p>
                  )}

                  {!done && (
                    <div className="staging-actions">
                      <button className="btn-approve" onClick={() => markDone(step.id)}>
                        {step.confirmLabel}
                      </button>
                      <button className="btn-help" onClick={() => toggleHelp(step.id)}>
                        {showHelp[step.id] ? "Anleitung ausblenden" : step.helpLabel}
                      </button>
                    </div>
                  )}

                  {showHelp[step.id] && !done && (
                    <>
                      <p className="staging-label">So geht es:</p>
                      <ol className="staging-help">
                        {step.help.map((line, i) => (
                          <li key={i}>{line}</li>
                        ))}
                      </ol>
                    </>
                  )}

                  {done && step.nextHint && nextStep && (
                    <div className="staging-next-hint">
                      <p className="staging-next-question">{step.nextHint}</p>
                      <p className="staging-next-why"><strong>Warum jetzt?</strong> {step.nextHintWhy}</p>
                    </div>
                  )}
                </>
              )}
            </div>
          )
        })}
      </div>

      {allDone && (
        <div className="staging-complete">
          <p>Alle Schritte abgeschlossen.</p>
          <p>AILIZA ist bereit für den Staging-Betrieb.</p>
        </div>
      )}
    </section>
  )
}
