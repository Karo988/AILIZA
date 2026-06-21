import { useState, useEffect } from "react"
import "./App.css"
import ChatInterface from "./components/ChatInterface"
import OnboardingWizard from "./components/OnboardingWizard"
import RuleManager from "./components/RuleManager"
import { auditApi, complianceApi, userApi } from "./api/ailizaClient"

const DEFAULT_USER_ID = "user-1"
const DEFAULT_SESSION_ID = () => {
  let s = sessionStorage.getItem("ailiza_session")
  if (!s) { s = crypto.randomUUID(); sessionStorage.setItem("ailiza_session", s) }
  return s
}

export default function App() {
  const [activePage, setActivePage] = useState("Chat")
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [profile, setProfile] = useState(null)
  const [auditLogs, setAuditLogs] = useState([])
  const [agents, setAgents] = useState([])
  const userId = DEFAULT_USER_ID
  const sessionId = DEFAULT_SESSION_ID()

  const pages = ["Chat", "Agenten", "Audit", "Regeln", "Einstellungen"]

  useEffect(() => {
    userApi.profile(userId).then((p) => {
      if (!p.onboarding_done) setShowOnboarding(true)
      else setProfile(p)
    }).catch(() => setShowOnboarding(true))
  }, [userId])

  useEffect(() => {
    if (activePage === "Audit") {
      auditApi.list(50).then((d) => setAuditLogs(d.logs || []))
    }
    if (activePage === "Agenten") {
      complianceApi.agents().then((d) => setAgents(d.agents || []))
    }
  }, [activePage])

  function handleOnboardingDone(data) {
    setShowOnboarding(false)
    setProfile(data)
  }

  function PageHeader({ label, title, text }) {
    return (
      <div className="page-header">
        <p className="eyebrow">{label}</p>
        <h1>{title}</h1>
        {text && <p className="subtitle">{text}</p>}
      </div>
    )
  }

  function renderPage() {
    if (activePage === "Chat") {
      return (
        <>
          <PageHeader
            label="AILIZA Assistent"
            title={profile?.display_name ? `Hallo, ${profile.display_name}` : "Chat"}
            text={profile?.company || "Intelligenter KI-Assistent für Ihr Unternehmen"}
          />
          <ChatInterface userId={userId} sessionId={sessionId} />
        </>
      )
    }

    if (activePage === "Agenten") {
      return (
        <section className="panel">
          <PageHeader label="Sub-Agenten" title="Verfügbare Agenten"
            text="Spezialisierte Agenten werden automatisch für passende Aufgaben aktiviert." />
          {agents.length === 0 ? (
            <p className="loading-text">Lade Agenten…</p>
          ) : (
            <div className="demo-grid">
              {agents.map((a) => (
                <div className="demo-card" key={a.name}>
                  <span className="agent-status">● Aktiv</span>
                  <h3>{a.name}</h3>
                  <p>{a.description}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      )
    }

    if (activePage === "Audit") {
      return (
        <section className="panel">
          <PageHeader label="Audit Trail" title="Audit-Protokolle"
            text="Alle Aktionen werden DSGVO-konform protokolliert." />
          <div className="table-card">
            {auditLogs.length === 0 && <p className="loading-text">Lade Protokolle…</p>}
            {auditLogs.map((log, i) => (
              <div className="table-row" key={i}>
                <span>{new Date(log.timestamp).toLocaleTimeString("de")}</span>
                <strong>{log.action}</strong>
                <p>{typeof log.metadata === "object" ? JSON.stringify(log.metadata).slice(0, 80) : log.metadata}</p>
              </div>
            ))}
          </div>
        </section>
      )
    }

    if (activePage === "Regeln") {
      return (
        <section className="panel">
          <PageHeader label="Lernmodul" title="Meine Regeln"
            text="AILIZA lernt aus Ihrem Feedback und wendet Ihre Präferenzen automatisch an." />
          <RuleManager userId={userId} />
        </section>
      )
    }

    return (
      <section className="panel">
        <PageHeader label="System" title="Einstellungen"
          text="Konfiguration Ihres AILIZA-Assistenten." />
        <div className="demo-grid">
          <div className="demo-card">
            <h3>Ihr Profil</h3>
            {profile ? (
              <>
                <p>Name: <strong>{profile.display_name}</strong></p>
                {profile.company && <p>Firma: <strong>{profile.company}</strong></p>}
                <p>Sprache: <strong>{profile.language || "de"}</strong></p>
              </>
            ) : <p>Nicht eingerichtet</p>}
            <button className="settings-btn" onClick={() => setShowOnboarding(true)}>
              Profil bearbeiten
            </button>
          </div>
          <div className="demo-card">
            <h3>Datenschutz (DSGVO)</h3>
            <p>AILIZA pseudonymisiert Personennamen, E-Mails und IBANs vor KI-Verarbeitung.</p>
            <p><strong>Platzhalter-System aktiv</strong></p>
          </div>
          <div className="demo-card">
            <h3>Datenlöschung (Art. 17)</h3>
            <p>Alle Ihre Daten vollständig löschen.</p>
            <button
              className="settings-btn danger"
              onClick={() => {
                if (window.confirm("Alle Daten unwiderruflich löschen?")) {
                  userApi.deleteAll(userId).then(() => setShowOnboarding(true))
                }
              }}
            >
              Alle Daten löschen
            </button>
          </div>
          <div className="demo-card">
            <h3>EU AI Act Art. 52</h3>
            <p>Sie interagieren mit einem KI-System. AILIZA trifft keine automatisierten Entscheidungen zu Kredit, Personal oder Medizin.</p>
            <strong>Transparenzpflicht erfüllt</strong>
          </div>
        </div>
      </section>
    )
  }

  return (
    <div className="app-shell">
      {showOnboarding && (
        <OnboardingWizard
          userId={userId}
          sessionId={sessionId}
          onDone={handleOnboardingDone}
        />
      )}

      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <h2>AILIZA</h2>
            <p>{profile?.company || "KMU Assistent"}</p>
          </div>
        </div>
        <nav>
          {pages.map((page) => (
            <button
              key={page}
              className={activePage === page ? "nav-item active" : "nav-item"}
              onClick={() => setActivePage(page)}
            >
              {page}
            </button>
          ))}
        </nav>
        {profile?.display_name && (
          <div className="sidebar-user">
            <span>👤 {profile.display_name}</span>
          </div>
        )}
      </aside>

      <main className="main-content">{renderPage()}</main>
    </div>
  )
}
