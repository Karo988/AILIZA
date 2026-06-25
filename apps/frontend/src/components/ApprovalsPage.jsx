import { useState, useEffect, useCallback } from "react"

const API = import.meta.env.VITE_API_URL ?? ""

const RISK_LABEL = {
  low: { text: "Niedrig", cls: "risk-low" },
  medium: { text: "Mittel", cls: "risk-medium" },
  high: { text: "Hoch", cls: "risk-high" },
}

function RiskBadge({ level }) {
  const { text, cls } = RISK_LABEL[level] ?? { text: level, cls: "risk-medium" }
  return <span className={`risk-badge ${cls}`}>{text}</span>
}

function ApprovalRow({ item, apiKey, onResolved }) {
  const [note, setNote] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function resolve(action) {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/approvals/${item.id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-api-key": apiKey },
        body: JSON.stringify({ note }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? `HTTP ${res.status}`)
      }
      onResolved(item.id, action)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const params = item.input_params ?? {}
  const task = params.task ?? JSON.stringify(params).slice(0, 120)
  const categories = params.risk_categories ?? []

  return (
    <div className="approval-card">
      <div className="approval-header">
        <span className="approval-id">#{item.id}</span>
        <RiskBadge level={item.risk_level} />
        <span className="approval-time">{new Date(item.created_at).toLocaleString("de-DE")}</span>
      </div>

      <p className="approval-reason"><strong>Grund:</strong> {item.risk_reason}</p>
      <p className="approval-task"><strong>Anfrage:</strong> {task}</p>

      {categories.length > 0 && (
        <p className="approval-categories">
          <strong>Kategorien:</strong> {categories.join(", ")}
        </p>
      )}

      <div className="approval-actions">
        <textarea
          placeholder="Begründung (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={loading}
          rows={2}
        />
        <div className="approval-buttons">
          <button
            className="btn-approve"
            onClick={() => resolve("approve")}
            disabled={loading}
          >
            Freigeben
          </button>
          <button
            className="btn-reject"
            onClick={() => resolve("reject")}
            disabled={loading}
          >
            Ablehnen
          </button>
        </div>
        {error && <p className="approval-error">{error}</p>}
      </div>
    </div>
  )
}

export default function ApprovalsPage() {
  const [apiKey, setApiKey] = useState("")
  const [authenticated, setAuthenticated] = useState(false)
  const [approvals, setApprovals] = useState([])
  const [loading, setLoading] = useState(false)
  const [authError, setAuthError] = useState(null)

  const loadApprovals = useCallback(async (key) => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/approvals?status=pending`, {
        headers: { "x-api-key": key },
      })
      if (res.status === 401 || res.status === 403) {
        setAuthenticated(false)
        setAuthError("Ungültiger API-Key.")
        return
      }
      const data = await res.json()
      setApprovals(data)
    } finally {
      setLoading(false)
    }
  }, [])

  async function login() {
    setAuthError(null)
    const res = await fetch(`${API}/approvals?status=pending`, {
      headers: { "x-api-key": apiKey },
    })
    if (res.status === 401 || res.status === 403) {
      setAuthError("Ungültiger API-Key.")
      return
    }
    const data = await res.json()
    setAuthenticated(true)
    setApprovals(data)
  }

  function handleResolved(id, action) {
    setApprovals((prev) => prev.filter((a) => a.id !== id))
  }

  useEffect(() => {
    if (!authenticated) return
    const interval = setInterval(() => loadApprovals(apiKey), 15000)
    return () => clearInterval(interval)
  }, [authenticated, apiKey, loadApprovals])

  if (!authenticated) {
    return (
      <section className="panel">
        <div className="page-header">
          <p className="eyebrow">Human Oversight</p>
          <h1>Freigaben</h1>
          <p className="subtitle">
            Anfragen, die wegen ihres Risikoprofils menschliche Freigabe erfordern.
            Nur Operatoren und Administratoren können hier entscheiden.
          </p>
        </div>

        <div className="login-card">
          <p>Bitte API-Key eingeben um fortzufahren:</p>
          <input
            type="password"
            placeholder="x-api-key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && login()}
          />
          <button onClick={login}>Anmelden</button>
          {authError && <p className="approval-error">{authError}</p>}
        </div>
      </section>
    )
  }

  return (
    <section className="panel">
      <div className="page-header">
        <p className="eyebrow">Human Oversight — EU AI Act Art. 14</p>
        <h1>Freigaben</h1>
        <p className="subtitle">
          Offene Anfragen: {approvals.length} — wird alle 15 Sekunden aktualisiert.
        </p>
      </div>

      <div className="approval-toolbar">
        <button onClick={() => loadApprovals(apiKey)} disabled={loading}>
          {loading ? "Lädt…" : "Aktualisieren"}
        </button>
        <button className="btn-logout" onClick={() => { setAuthenticated(false); setApiKey("") }}>
          Abmelden
        </button>
      </div>

      {approvals.length === 0 && !loading && (
        <div className="approval-empty">
          Keine offenen Freigaben.
        </div>
      )}

      <div className="approvals-list">
        {approvals.map((item) => (
          <ApprovalRow
            key={item.id}
            item={item}
            apiKey={apiKey}
            onResolved={handleResolved}
          />
        ))}
      </div>
    </section>
  )
}
