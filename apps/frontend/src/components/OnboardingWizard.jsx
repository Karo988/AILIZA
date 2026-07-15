import { useState } from "react"
import { userApi, keyApi } from "../api/ailizaClient"

export default function OnboardingWizard({ userId, sessionId, onDone }) {
  const [step, setStep] = useState(0)
  const [name, setName] = useState("")
  const [company, setCompany] = useState("")
  const [language, setLanguage] = useState("de")
  const [provider, setProvider] = useState("groq")
  const [apiKey, setApiKey] = useState("")
  const [saving, setSaving] = useState(false)
  const [aiActAccepted, setAiActAccepted] = useState(false)

  async function finish() {
    setSaving(true)
    await userApi.onboarding(userId, name, company, language)
    if (apiKey.trim()) {
      await keyApi.store(sessionId, provider, apiKey.trim())
    }
    setSaving(false)
    onDone({ name, company, language, hasKey: !!apiKey.trim() })
  }

  const steps = [
    // Step 0: EU AI Act Hinweis (Art. 50)
    <div key="aiact" className="wizard-step">
      <div className="wizard-icon">⚖️</div>
      <h2>EU AI Act — Art. 50 Transparenzpflicht</h2>
      <p>
        AILIZA ist ein KI-System nach EU AI Act Art. 50. Sie interagieren mit einer
        künstlichen Intelligenz. AILIZA trifft <strong>keine</strong> automatisierten
        Kreditentscheidungen, Personalentscheidungen oder medizinischen Diagnosen.
        Sie behalten jederzeit die Kontrolle.
      </p>
      <p className="wizard-hint">
        Diese Hinweispflicht gilt für jede KI-gestützte Anwendung in der EU.
      </p>
      <label className="wizard-checkbox">
        <input
          type="checkbox"
          checked={aiActAccepted}
          onChange={(e) => setAiActAccepted(e.target.checked)}
        />
        Ich habe den Hinweis zur Kenntnis genommen.
      </label>
      <button
        className="wizard-btn"
        disabled={!aiActAccepted}
        onClick={() => setStep(1)}
      >
        Weiter
      </button>
    </div>,

    // Step 1: Name & Firma
    <div key="profile" className="wizard-step">
      <div className="wizard-icon">👤</div>
      <h2>Willkommen bei AILIZA</h2>
      <p>Kurze Einrichtung — dauert unter einer Minute.</p>
      <label>Ihr Name
        <input value={name} onChange={(e) => setName(e.target.value)}
          placeholder="z.B. Anna Müller" autoFocus />
      </label>
      <label>Unternehmen (optional)
        <input value={company} onChange={(e) => setCompany(e.target.value)}
          placeholder="z.B. Muster GmbH" />
      </label>
      <label>Sprache
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="de">Deutsch</option>
          <option value="en">English</option>
          <option value="fr">Français</option>
          <option value="es">Español</option>
          <option value="it">Italiano</option>
        </select>
      </label>
      <div className="wizard-nav">
        <button className="wizard-btn secondary" onClick={() => setStep(0)}>Zurück</button>
        <button className="wizard-btn" disabled={!name.trim()} onClick={() => setStep(2)}>Weiter</button>
      </div>
    </div>,

    // Step 2: API-Key (optional)
    <div key="apikey" className="wizard-step">
      <div className="wizard-icon">🔑</div>
      <h2>KI-Zugang (optional)</h2>
      <p>
        Für echte KI-Antworten benötigt AILIZA einen API-Key. Ohne Key läuft AILIZA
        im <strong>Basis-Modus</strong> (regelbasiert, kein LLM).
      </p>
      <p className="wizard-hint">
        Der Key wird <strong>verschlüsselt im RAM</strong> gespeichert — niemals in der Datenbank.
        Er wird beim Beenden der Sitzung gelöscht.
      </p>
      <label>Anbieter
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="groq">Groq (kostenlos, schnell)</option>
          <option value="anthropic">Anthropic Claude</option>
          <option value="openai">OpenAI</option>
          <option value="mistral">Mistral</option>
        </select>
      </label>
      <label>API-Key
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="gsk_... / sk-... (optional)"
        />
      </label>
      <div className="wizard-nav">
        <button className="wizard-btn secondary" onClick={() => setStep(1)}>Zurück</button>
        <button className="wizard-btn" onClick={() => setStep(3)}>Weiter</button>
      </div>
    </div>,

    // Step 3: Fertig
    <div key="done" className="wizard-step">
      <div className="wizard-icon">✅</div>
      <h2>AILIZA ist bereit</h2>
      <ul className="wizard-summary">
        <li>Name: <strong>{name}</strong></li>
        {company && <li>Unternehmen: <strong>{company}</strong></li>}
        <li>Sprache: <strong>{language.toUpperCase()}</strong></li>
        <li>KI-Modus: <strong>{apiKey ? `${provider} (verschlüsselt)` : "Basis-Modus"}</strong></li>
      </ul>
      <div className="wizard-nav">
        <button className="wizard-btn secondary" onClick={() => setStep(2)}>Zurück</button>
        <button className="wizard-btn" disabled={saving} onClick={finish}>
          {saving ? "Speichere..." : "Starten"}
        </button>
      </div>
    </div>,
  ]

  return (
    <div className="wizard-overlay">
      <div className="wizard-card">
        <div className="wizard-progress">
          {steps.map((_, i) => (
            <div key={i} className={`wizard-dot ${i <= step ? "active" : ""}`} />
          ))}
        </div>
        {steps[step]}
      </div>
    </div>
  )
}
