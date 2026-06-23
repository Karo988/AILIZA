import { useState, useEffect } from "react"
import "./App.css"
import DashboardCard from "./components/DashboardCard"
import LoginPage from "./components/LoginPage"
import AgentChat from "./components/AgentChat"
import { getSession, logout, apiFetch } from "./api"

function App() {
  const [session, setSession] = useState(null)          // null = nicht geprüft, false = nicht eingeloggt
  const [activePage, setActivePage] = useState("Dashboard")
  const [auditLogs, setAuditLogs] = useState([])

  // Session prüfen beim Start
  useEffect(() => {
    getSession().then((s) => setSession(s || false))
  }, [])

  // Audit-Logs laden wenn eingeloggt
  useEffect(() => {
    if (!session) return
    apiFetch("/audit-logs?limit=20")
      .then((data) => {
        if (Array.isArray(data)) setAuditLogs(data)
      })
      .catch(() => {})
  }, [session])

  function handleLogin(data) {
    setSession({ user_id: data.user_id, role: data.role, tenant_id: "default" })
  }

  // Noch nicht geprüft — kurz warten
  if (session === null) {
    return <div className="loading-screen">AILIZA wird geladen …</div>
  }

  // Nicht eingeloggt → Login-Seite
  if (session === false) {
    return <LoginPage onLogin={handleLogin} />
  }

  const pages = ["Dashboard", "Governance", "Audit", "Agenten", "Einstellungen"]

  const dashboardData = [
    { title: "Frontend", value: "Online", detail: "Vite UI aktiv", color: "blue" },
    { title: "Governance", value: "Aktiv", detail: "EU-AI-Act Checks", color: "green" },
    { title: "Audit", value: "Logging", detail: "Protokollierung aktiv", color: "purple" },
    { title: "Compliance", value: "98%", detail: "DSGVO / EU-KI-konform", color: "red" },
  ]

  const agents = [
    ["Governance-Agent", "Online", "EU-AI-Act Compliance, Human Oversight, Risikoklassen"],
    ["Audit-Agent", "Online", "Audit Logging, Nachvollziehbarkeit, Entscheidungsprotokolle"],
    ["Runtime-Agent", "Online", "Workflow-Ausführung, Runtime-Monitoring, Task-Status"],
    ["Monitoring-Agent", "Online", "Health Checks, Warnungen, Systemüberwachung"],
  ]

  function PageHeader({ label, title, text }) {
    return (
      <div className="page-header">
        <p className="eyebrow">{label}</p>
        <h1>{title}</h1>
        <p className="subtitle">{text}</p>
      </div>
    )
  }

  function renderPage() {
    if (activePage === "Dashboard") {
      return (
        <>
          <PageHeader
            label="AILIZA Control Center"
            title="Governance Dashboard"
            text="EU-KI-Gesetz- und DSGVO-konformes autonomes Agentensystem."
          />
          <div className="kpi-grid">
            <div className="kpi-card"><p className="kpi-label">Agenten</p><p className="kpi-value">4</p></div>
            <div className="kpi-card"><p className="kpi-label">Compliance</p><p className="kpi-value">98%</p></div>
            <div className="kpi-card"><p className="kpi-label">Audit Logs</p><p className="kpi-value">{auditLogs.length}</p></div>
            <div className="kpi-card"><p className="kpi-label">Nutzer</p><p className="kpi-value">{session.user_id}</p></div>
          </div>
          <AgentChat onRunComplete={() =>
            apiFetch("/audit-logs?limit=20")
              .then((d) => { if (Array.isArray(d)) setAuditLogs(d) })
              .catch(() => {})
          } />
          <div className="card-grid">
            {dashboardData.map((card) => (
              <DashboardCard key={card.title} {...card} />
            ))}
          </div>
        </>
      )
    }

    if (activePage === "Governance") {
      return (
        <section className="panel">
          <PageHeader
            label="Governance Layer"
            title="Governance"
            text="Kontrollschicht für sichere, prüfbare und EU-konforme Agenten."
          />
          <div className="demo-grid">
            <div className="demo-card"><h3>Human Oversight</h3><p>Aktiviert für kritische Aktionen.</p><strong>Aktiv</strong></div>
            <div className="demo-card"><h3>Risk Classification</h3><p>Risikoklasse wird vor Ausführung geprüft.</p><strong>Vorhanden</strong></div>
            <div className="demo-card"><h3>DSGVO</h3><p>Datenschutzstatus und Protokollierung aktiv.</p><strong>Konform</strong></div>
            <div className="demo-card"><h3>Audit Gate</h3><p>Aktionen werden nachvollziehbar gespeichert.</p><strong>Aktiv</strong></div>
          </div>
        </section>
      )
    }

    if (activePage === "Audit") {
      return (
        <section className="panel">
          <PageHeader
            label="Audit Trail"
            title="Audit-Protokolle"
            text="Nachvollziehbare Ereignisse für Entscheidungen, Prüfungen und Agentenaktionen."
          />
          <div className="table-card">
            {auditLogs.length === 0 && <p>Keine Einträge vorhanden.</p>}
            {auditLogs.map((log, i) => (
              <div className="table-row" key={log.id || i}>
                <span>{log.created_at ? new Date(log.created_at).toLocaleTimeString("de-DE") : "—"}</span>
                <strong>{log.action}</strong>
                <p>{log.metadata ? JSON.stringify(log.metadata) : ""}</p>
              </div>
            ))}
          </div>
        </section>
      )
    }

    if (activePage === "Agenten") {
      return (
        <section className="panel">
          <PageHeader
            label="Agent Runtime"
            title="Agenten"
            text="Aktive AILIZA-Systemagenten für Governance, Audit, Runtime und Monitoring."
          />
          <div className="demo-grid">
            {agents.map(([name, status, task]) => (
              <div className="demo-card" key={name}>
                <span className="agent-status">● {status}</span>
                <h3>{name}</h3>
                <p>{task}</p>
              </div>
            ))}
          </div>
        </section>
      )
    }

    return (
      <section className="panel">
        <PageHeader label="System" title="Einstellungen" text="Konfiguration." />
        <div className="demo-grid">
          <div className="demo-card">
            <h3>Session</h3>
            <p>Nutzer: <strong>{session.user_id}</strong></p>
            <p>Rolle: <strong>{session.role}</strong></p>
            <button onClick={logout} style={{ marginTop: "0.75rem" }}>Abmelden</button>
          </div>
          <div className="demo-card"><h3>Audit Logging</h3><p>Protokollierung aller Aktionen.</p><strong>Aktiv</strong></div>
          <div className="demo-card"><h3>EU AI Act Art. 50</h3><p>KI-Kennzeichnung aktiv.</p><strong>Konform</strong></div>
          <div className="demo-card"><h3>Kill-Switch</h3><p>Externe KI steuerbar über Env-Variable.</p><strong>Fail-Closed</strong></div>
        </div>
      </section>
    )
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <h2>AILIZA</h2>
            <p>Governance AI</p>
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
        <div className="sidebar-footer">
          <span>{session.user_id} · {session.role}</span>
          <button onClick={logout} className="logout-btn">Abmelden</button>
        </div>
      </aside>
      <main className="main-content">{renderPage()}</main>
    </div>
  )
}

export default App
