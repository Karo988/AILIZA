import { useState } from "react"
import { login } from "../api"

export default function LoginPage({ onLogin }) {
  const [userId, setUserId] = useState("")
  const [password, setPassword] = useState("")
  const [tenantId, setTenantId] = useState("default")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const data = await login(userId, password, tenantId)
      if (data) onLogin(data)
    } catch (err) {
      setError(err.message || "Anmeldung fehlgeschlagen.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <h2>AILIZA</h2>
            <p>Governance AI</p>
          </div>
        </div>

        <h1>Anmelden</h1>
        <p className="subtitle">EU-KI-Akt- und DSGVO-konformes Agentensystem.</p>

        <form onSubmit={handleSubmit} autoComplete="off">
          <label>
            Nutzer-ID
            <input
              type="text"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              autoComplete="username"
              required
              minLength={1}
              maxLength={64}
            />
          </label>

          <label>
            Passwort
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          <label>
            Mandant (optional)
            <input
              type="text"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="default"
            />
          </label>

          {error && <p className="error-msg">{error}</p>}

          <button type="submit" disabled={loading}>
            {loading ? "Anmelden …" : "Anmelden"}
          </button>
        </form>

        <p className="login-note">
          ⚠️ Du interagierst mit einem KI-System (EU AI Act Art. 50).
        </p>
      </div>
    </div>
  )
}
