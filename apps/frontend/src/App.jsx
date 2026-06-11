import { useState } from "react"
import "./App.css"
import DashboardCard from "./components/DashboardCard"

function App() {
  const [activePage, setActivePage] = useState("Dashboard")
  const [taskInput, setTaskInput] = useState("")
const [agentResult, setAgentResult] = useState(null)

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

  const auditLogs = [
    ["14:02", "Agent gestartet", "Runtime-Agent initialisiert"],
    ["14:05", "Governance-Prüfung bestanden", "EU-AI-Act Gate erfolgreich"],
    ["14:07", "Audit-Eintrag erstellt", "Aktion nachvollziehbar protokolliert"],
    ["14:15", "Compliance-Check bestanden", "DSGVO-Status aktiv"],
  ]
  function startAgentDemo() {
  if (!taskInput.trim()) {
    return
  }

  setAgentResult({
    title: "Demo-Agentenlauf abgeschlossen",
    risk: "Mittel",
    status: "Governance-Prüfung bestanden",
    summary:
      "Die Aufgabe wurde simuliert durch Governance-Agent, Audit-Agent und Runtime-Agent geprüft. Es wurden keine kritischen Compliance-Verstöße erkannt.",
  })
}

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
            <div className="kpi-card"><p className="kpi-label">Audit Logs</p><p className="kpi-value">324</p></div>
            <div className="kpi-card"><p className="kpi-label">Workflows</p><p className="kpi-value">12</p></div>
          </div>
          <div className="demo-runner">
  <h2>Agentenlauf simulieren</h2>
  <p>
    Gib eine Beispielaufgabe ein und starte einen simulierten Governance-Check.
  </p>

  <textarea
    value={taskInput}
    onChange={(event) => setTaskInput(event.target.value)}
    placeholder="Beispiel: Prüfe ein Dokument auf DSGVO- und EU-AI-Act-Konformität."
  />

  <button onClick={startAgentDemo}>
    Agent starten
  </button>

  {agentResult && (
    <div className="result-box">
      <h3>{agentResult.title}</h3>
      <p><strong>Status:</strong> {agentResult.status}</p>
      <p><strong>Risiko:</strong> {agentResult.risk}</p>
      <p>{agentResult.summary}</p>
    </div>
  )}
</div>

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
            {auditLogs.map(([time, event, detail]) => (
              <div className="table-row" key={time}>
                <span>{time}</span>
                <strong>{event}</strong>
                <p>{detail}</p>
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
        <PageHeader
          label="System"
          title="Einstellungen"
          text="Konfiguration der Demo-Umgebung."
        />

        <div className="demo-grid">
          <div className="demo-card"><h3>Dark Mode</h3><p>Aktiviert für Demo und Dashboard.</p><strong>Aktiv</strong></div>
          <div className="demo-card"><h3>Audit Logging</h3><p>Protokollierung aller Aktionen.</p><strong>Aktiv</strong></div>
          <div className="demo-card"><h3>Runtime Monitoring</h3><p>Überwachung der Agentenlaufzeit.</p><strong>Aktiv</strong></div>
          <div className="demo-card"><h3>Demo Mode</h3><p>Mock-Daten für Präsentation.</p><strong>Aktiv</strong></div>
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
      </aside>

      <main className="main-content">{renderPage()}</main>
    </div>
  )
}

export default App